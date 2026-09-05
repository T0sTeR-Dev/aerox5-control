"""Desktop presentation and validation, with no dependency on GTK.

All hardware operations delegate to the existing application services. The
receiver's presence alone does not establish that the mouse is awake/connected.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from aerox5_control.application import services
from aerox5_control.devices.aerox5 import DpiPresetsResult, PollingRateResult
from aerox5_control.protocol.aerox5 import (
    MAX_DPI_PRESETS,
    SUPPORTED_POLLING_RATES,
    validate_dpi_presets,
)

PRESET_COUNTS = tuple(range(1, MAX_DPI_PRESETS + 1))
POLLING_RATES = SUPPORTED_POLLING_RATES
DEVICE_NAME = "SteelSeries Aerox 5 Wireless"


@dataclass(frozen=True, slots=True)
class Overview:
    name: str = DEVICE_NAME
    state: str = "Not refreshed"
    connection: str = "Unavailable"
    vendor_id: str = "Unavailable"
    product_id: str = "Unavailable"
    battery: str = "Unavailable"
    charging: str = "Unavailable"
    message: str = "Use Refresh to check the receiver and mouse."


@dataclass(frozen=True, slots=True)
class Feedback:
    message: str
    error: bool = False
    connection_state: str | None = None


def parse_dpi_inputs(inputs: Sequence[str]) -> tuple[int, ...]:
    """Preserve raw entry text; never coerce decimals, truncate, or round."""
    if isinstance(inputs, (str, bytes)) or len(inputs) not in PRESET_COUNTS:
        raise ValueError("Enter between 1 and 5 DPI presets.")
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,5}", value.strip())
        for value in inputs
    ):
        raise ValueError("Enter a whole DPI number in each active preset.")
    return validate_dpi_presets(tuple(int(value.strip()) for value in inputs))


def validate_polling_input(rate_hz: int | None) -> int:
    if type(rate_hz) is not int or rate_hz not in POLLING_RATES:
        raise ValueError("Choose a polling rate: 125, 250, 500, or 1000 Hz.")
    return rate_hz


def hardware_problem(reason: str | Exception) -> Feedback:
    """Translate existing backend diagnostics without exposing paths in the UI.

    Device results currently carry text diagnostics. These hints identify common
    failures; an unknown failure never becomes a claim that the link is alive.
    """
    text = str(reason).lower()
    if isinstance(reason, PermissionError) or any(
        word in text
        for word in ("permission", "access denied", "operation not permitted")
    ):
        return Feedback(
            "Permission denied. Check device access for your desktop user, "
            "then use Refresh.",
            True,
            "Connection unavailable",
        )
    if any(word in text for word in ("multiple receiver", "conflicting metadata")):
        return Feedback(
            "The receiver cannot be selected unambiguously. Connect one supported "
            "receiver and use Refresh.",
            True,
            "Connection unavailable",
        )
    if any(
        word in text
        for word in (
            "not found",
            "disconnected",
            "no such device",
            "no such file",
            "asleep/off",
        )
    ):
        return Feedback(
            "Receiver or mouse unavailable. Reconnect the receiver, wake the mouse, "
            "and use Refresh.",
            True,
            "Disconnected",
        )
    if isinstance(reason, TimeoutError) or any(
        word in text for word in ("timed out", "timeout")
    ):
        return Feedback(
            "The device did not respond in time. Wake or reconnect the mouse, "
            "then use Refresh.",
            True,
            "Connection unavailable",
        )
    if "battery" in text:
        return Feedback(
            "Battery and charging information are unavailable. Wake the mouse "
            "and use Refresh.",
            True,
            "Connection unavailable",
        )
    if "write" in text:
        return Feedback(
            "The setting request could not be completed. Check the receiver "
            "connection and use Refresh.",
            True,
            "Connection unavailable",
        )
    return Feedback(
        "Device communication failed. Check the receiver connection and device "
        "access, then use Refresh. CLI status provides diagnostic details.",
        True,
        "Connection unavailable",
    )


class DesktopService:
    """Small synchronous adapter; the controller runs these calls on a worker."""

    def refresh(self) -> Overview:
        status = services.get_status()
        fields = {}
        if status.interface is not None:
            interface = status.interface
            fields = {
                "name": interface.hid.product_string or DEVICE_NAME,
                "connection": interface.connection,
                "vendor_id": f"0x{interface.hid.vendor_id:04x}",
                "product_id": f"0x{interface.hid.product_id:04x}",
            }
        if status.interface is not None and status.battery.available:
            charging = status.battery.charging
            return Overview(
                **fields,
                state="Connected",
                battery=f"{status.battery.level}%",
                charging="Unavailable"
                if charging is None
                else "Yes"
                if charging
                else "No",
                message="Connection and battery reflect the last refresh.",
            )
        problem = hardware_problem(status.battery.reason or "Battery unavailable")
        return Overview(
            **fields, state=problem.connection_state, message=problem.message
        )

    def apply_dpi(self, presets: tuple[int, ...]) -> Feedback:
        return self._setting_feedback(
            services.set_dpi_presets(presets), "DPI preset request sent"
        )

    def apply_polling(self, rate_hz: int) -> Feedback:
        return self._setting_feedback(
            services.set_polling_rate(rate_hz), "Polling-rate request sent"
        )

    @staticmethod
    def _setting_feedback(
        result: DpiPresetsResult | PollingRateResult, success: str
    ) -> Feedback:
        if result.completed:
            return Feedback(f"{success}. The active setting has not been read back.")
        problem = hardware_problem(result.error or "Setting operation failed")
        message = problem.message
        if result.write_attempted:
            message += " The setting may already have changed. No retry was sent."
        return Feedback(message, True, problem.connection_state)
