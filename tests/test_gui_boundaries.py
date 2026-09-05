"""Guard the frontend boundary without importing native widgets or any HID backend."""

import ast
import sys
import tomllib
from pathlib import Path

from aerox5_control.gui.main import main

ROOT = Path(__file__).resolve().parents[1]


def test_gui_modules_import_only_application_api_and_gui_libraries():
    for path in (ROOT / "src/aerox5_control/gui").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                assert (
                    module == "sys"
                    or module == "gi"
                    or module.startswith(
                        (
                            "gi.repository",
                            "aerox5_control.gui",
                            "aerox5_control.application",
                        )
                    )
                ), (path, module)
        # Widgets must neither construct reports nor open paths through builtins.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else (node.func.id if isinstance(node.func, ast.Name) else "")
                )
                assert name not in {
                    "open",
                    "open_path",
                    "write_output",
                    "read_input",
                    "write",
                    "send_feature_report",
                    "get_feature_report",
                    "bytes",
                    "bytearray",
                }, (path, name)
        assert "/dev/" not in path.read_text()


def test_gui_calls_only_existing_supported_application_operations():
    tree = ast.parse((ROOT / "src/aerox5_control/application/desktop.py").read_text())
    service_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "services"
    }
    assert service_calls == {"get_status", "set_dpi_presets", "set_polling_rate"}


def test_gui_launcher_is_separate_from_cli():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["scripts"] == {
        "aerox5-control": "aerox5_control.gui.main:main",
        "aerox5-control-cli": "aerox5_control.cli.main:main",
    }
    assert project["dependencies"] == ["hidapi>=0.14"]


def test_missing_pygobject_is_actionable_and_does_not_access_hid(
    monkeypatch, capsys, hid_backend
):
    monkeypatch.setitem(sys.modules, "gi", None)
    monkeypatch.delitem(sys.modules, "aerox5_control.gui._gtk", raising=False)
    assert main(["aerox5-control"]) == 1
    assert "--system-site-packages" in capsys.readouterr().err
    assert not hid_backend.mock_calls
