"""One worker, no polling or queued writes; UI callbacks use a main-loop dispatcher."""

from collections.abc import Callable, Sequence
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass, replace

from aerox5_control.application.desktop import (
    DesktopService,
    Feedback,
    Overview,
    hardware_problem,
    parse_dpi_inputs,
    validate_polling_input,
)


@dataclass(frozen=True, slots=True)
class DesktopState:
    overview: Overview = Overview()
    busy: bool = False
    message: str = ""
    error: bool = False


class DesktopController:
    """Public methods and dispatched completions belong to the UI/main thread.

    dispatch must enqueue callbacks onto that thread (GLib.idle_add in GTK).
    Only service calls run on the worker. Rejecting actions while busy prevents
    double clicks from queueing writes, and closing discards late completions.
    """

    def __init__(
        self,
        on_change: Callable[[DesktopState], None],
        dispatch: Callable[[Callable[[], bool]], object],
        *,
        service: DesktopService | None = None,
        executor: Executor | None = None,
    ) -> None:
        self.state = DesktopState()
        self._on_change = on_change
        self._dispatch = dispatch
        self._service = service if service is not None else DesktopService()
        self._executor = (
            executor
            if executor is not None
            else ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="aerox5-operation"
            )
        )
        self._closed = False

    def refresh(self) -> None:
        self._start(self._service.refresh, "Refreshing…", is_refresh=True)

    def apply_dpi(self, inputs: Sequence[str]) -> None:
        if self._closed or self.state.busy:
            return
        try:
            presets = parse_dpi_inputs(inputs)
        except ValueError as error:
            self._validation_error(error)
            return
        self._start(lambda: self._service.apply_dpi(presets), "Sending DPI presets…")

    def apply_polling(self, rate_hz: int | None) -> None:
        if self._closed or self.state.busy:
            return
        try:
            rate = validate_polling_input(rate_hz)
        except ValueError as error:
            self._validation_error(error)
            return
        self._start(lambda: self._service.apply_polling(rate), "Sending polling rate…")

    def _validation_error(self, error: ValueError) -> None:
        self.state = replace(self.state, message=str(error), error=True)
        self._on_change(self.state)

    def _start(
        self,
        operation: Callable[[], Overview | Feedback],
        message: str,
        *,
        is_refresh: bool = False,
    ) -> None:
        if self._closed or self.state.busy:
            return
        self.state = replace(self.state, busy=True, message=message, error=False)
        self._on_change(self.state)
        try:
            future = self._executor.submit(operation)
        except Exception as error:
            future = Future()
            future.set_exception(error)
        future.add_done_callback(
            lambda done: self._dispatch(lambda: self._finish(done, is_refresh))
        )

    def _finish(self, future: Future, is_refresh: bool) -> bool:
        if self._closed:
            return False
        try:
            result = future.result()
        except Exception as error:
            # Last-resort boundary: unexpected backend failures must not kill GTK.
            result = hardware_problem(error)
            if not is_refresh:
                result = replace(
                    result,
                    message=result.message
                    + " The setting may already have changed. No retry was sent.",
                )
        overview = self.state.overview
        if isinstance(result, Overview):
            overview = result
            failed = result.state != "Connected"
            message = result.message if failed else "Refresh complete."
        else:
            message, failed = result.message, result.error
            if result.connection_state:
                # Never keep a stale battery/Connected display after an I/O error.
                overview = replace(
                    Overview() if is_refresh else overview,
                    state=result.connection_state,
                    battery="Unavailable",
                    charging="Unavailable",
                    message=result.message,
                )
        self.state = DesktopState(overview, False, message, failed)
        self._on_change(self.state)
        return False  # GLib idle callbacks run exactly once.

    def close(self) -> None:
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
