"""Run native widget interactions on private Broadway, never the user's display.

The child scenario replaces both HID modules and all application services before
creating GTK widgets. No browser opens and no physical device can be accessed.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


def test_native_gui_with_fake_services(tmp_path):
    broadway = shutil.which("gtk4-broadwayd")
    if broadway is None:
        pytest.skip("Native widget test requires gtk4-broadwayd (part of GTK4)")
    # Arch keeps GI in system Python; CLI-only virtualenvs may not expose it.
    python = None
    for candidate in dict.fromkeys(
        (sys.executable, shutil.which("python3"), "/usr/bin/python3")
    ):
        if candidate and Path(candidate).exists():
            probe = subprocess.run(
                [
                    candidate,
                    "-c",
                    "import gi; gi.require_version('Gtk', '4.0'); "
                    "gi.require_version('Adw', '1')",
                ],
                capture_output=True,
                timeout=10,
            )
            if probe.returncode == 0:
                python = candidate
                break
    if python is None:
        pytest.skip("Native widget test requires system PyGObject and Libadwaita")

    root = Path(__file__).resolve().parents[1]
    # Short socket paths are required by AF_UNIX; pytest's nested paths can exceed
    # its limit. A temporary directory is also isolated from the host compositor.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="aerox5-gtk-") as directory:
        runtime = Path(directory)
        env = {
            **os.environ,
            "XDG_RUNTIME_DIR": str(runtime),
            "XDG_CONFIG_HOME": str(runtime / "config"),
            "XDG_CACHE_HOME": str(runtime / "cache"),
            "GDK_BACKEND": "broadway",
            "BROADWAY_DISPLAY": ":0",
            "GTK_A11Y": "none",
            "GSETTINGS_BACKEND": "memory",
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime}/no-session-bus",
            "DISPLAY": "",
            "WAYLAND_DISPLAY": "",
            "PYTHONPATH": str(root / "src"),
        }
        log_path = tmp_path / "broadway.log"
        with log_path.open("w") as log:
            server = subprocess.Popen(
                [broadway, "--unixsocket", str(runtime / "browser.socket"), ":0"],
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 5
                while not (runtime / "broadway1.socket").exists():
                    assert server.poll() is None, log_path.read_text()
                    assert time.monotonic() < deadline, log_path.read_text()
                    time.sleep(0.01)
                result = subprocess.run(
                    [python, str(root / "tests/gui_scenario.py")],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert result.returncode == 0, result.stdout + result.stderr
                assert "native GUI scenarios passed" in result.stdout
                assert "Traceback" not in result.stderr, result.stderr
                assert "CRITICAL" not in result.stderr, result.stderr
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
