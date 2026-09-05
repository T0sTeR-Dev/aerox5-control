"""Deterministic UI scheduling plus a real worker test; all services are fake."""

from concurrent.futures import Future, ThreadPoolExecutor
from queue import Queue
from threading import Event, get_ident
from unittest.mock import Mock, call

import pytest

from aerox5_control.application.desktop import DesktopService, Feedback, Overview
from aerox5_control.application.desktop_controller import DesktopController


class ManualExecutor:
    def __init__(self):
        self.jobs = []
        self.shutdown = Mock()

    def submit(self, operation):
        future = Future()
        self.jobs.append((operation, future))
        return future

    def complete(self):
        operation, future = self.jobs.pop(0)
        try:
            result = operation()
        except Exception as error:
            future.set_exception(error)
        else:
            future.set_result(result)


@pytest.fixture
def desktop():
    executor = ManualExecutor()
    service = Mock(spec_set=DesktopService)
    service.refresh.return_value = Overview(
        state="Connected", battery="40%", charging="Yes"
    )
    service.apply_dpi.return_value = Feedback("DPI preset request sent")
    service.apply_polling.return_value = Feedback("Polling-rate request sent")
    changes, callbacks = [], []
    controller = DesktopController(
        changes.append, callbacks.append, service=service, executor=executor
    )
    yield controller, service, executor, callbacks, changes
    controller.close()


def finish(desktop):
    _, _, executor, callbacks, _ = desktop
    executor.complete()
    assert len(callbacks) == 1
    assert callbacks.pop()() is False


def test_constructing_application_state_never_accesses_hardware(desktop, hid_backend):
    controller, service, executor, _, changes = desktop
    assert controller.state.overview.state == "Not refreshed"
    assert controller.state.overview.battery == "Unavailable"
    assert not executor.jobs
    assert not service.mock_calls
    assert not changes
    assert not hid_backend.mock_calls


def test_refresh_is_async_and_updates_only_after_dispatch(desktop):
    controller, service, executor, callbacks, _ = desktop
    controller.refresh()
    assert controller.state.busy
    assert not service.mock_calls
    executor.complete()
    assert controller.state.busy
    assert controller.state.overview.state == "Not refreshed"
    callbacks.pop()()
    assert not controller.state.busy
    assert controller.state.overview.state == "Connected"
    assert controller.state.overview.battery == "40%"
    assert service.mock_calls == [call.refresh()]
    assert not executor.jobs  # No continuous polling.


@pytest.mark.parametrize(
    ("action", "args", "expected"),
    [
        ("apply_dpi", (["800", "1600"],), call.apply_dpi((800, 1600))),
        ("apply_polling", (1000,), call.apply_polling(1000)),
    ],
)
def test_one_apply_calls_one_service_without_refresh_or_retry(
    desktop, action, args, expected
):
    controller, service, executor, _, _ = desktop
    getattr(controller, action)(*args)
    # Duplicate signals, Refresh, and other writes cannot queue while busy.
    controller.refresh()
    controller.apply_dpi(["400"])
    controller.apply_polling(500)
    assert len(executor.jobs) == 1
    finish(desktop)
    assert service.mock_calls == [expected]
    assert not executor.jobs
    assert not controller.state.error


@pytest.mark.parametrize(
    ("action", "value"),
    [
        ("apply_dpi", []),
        ("apply_dpi", ["850"]),
        ("apply_dpi", ["800.0"]),
        ("apply_dpi", ["800"] * 6),
        ("apply_polling", None),
        ("apply_polling", 144),
    ],
)
def test_invalid_inputs_do_not_schedule_work(desktop, action, value):
    controller, service, executor, _, _ = desktop
    getattr(controller, action)(value)
    assert controller.state.error
    assert controller.state.message
    assert not executor.jobs
    assert not service.mock_calls


def test_disconnect_then_refresh_can_recover(desktop):
    controller, service, _, _, _ = desktop
    controller.refresh()
    finish(desktop)
    service.apply_dpi.return_value = Feedback(
        "Reconnect and use Refresh.", True, "Disconnected"
    )
    controller.apply_dpi(["800"])
    finish(desktop)
    assert controller.state.overview.state == "Disconnected"
    assert controller.state.overview.battery == "Unavailable"
    assert controller.state.overview.charging == "Unavailable"
    controller.refresh()
    finish(desktop)
    assert controller.state.overview.state == "Connected"
    assert controller.state.overview.battery == "40%"
    assert not controller.state.error


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (PermissionError(), "Permission denied"),
        (TimeoutError(), "did not respond in time"),
        (OSError("device disconnected"), "Reconnect"),
        (RuntimeError("unexpected library failure"), "Device communication failed"),
    ],
)
def test_unexpected_service_exceptions_do_not_kill_application(desktop, error, message):
    controller, service, executor, _, _ = desktop
    service.apply_polling.side_effect = error
    controller.apply_polling(1000)
    finish(desktop)
    assert not controller.state.busy
    assert controller.state.error
    assert message in controller.state.message
    assert "may already have changed" in controller.state.message
    assert service.mock_calls == [call.apply_polling(1000)]
    assert not executor.jobs


def test_failed_refresh_clears_old_identity_when_no_receiver_is_found(desktop):
    controller, service, _, _, _ = desktop
    controller.refresh()
    finish(desktop)
    service.refresh.return_value = Overview(
        state="Disconnected", message="Reconnect the receiver."
    )
    controller.refresh()
    finish(desktop)
    assert controller.state.overview.battery == "Unavailable"
    assert controller.state.overview.vendor_id == "Unavailable"
    assert controller.state.error


def test_closed_controller_discards_late_completion_and_rejects_new_actions(desktop):
    controller, service, executor, _, changes = desktop
    controller.refresh()
    controller.close()
    count = len(changes)
    finish(desktop)
    assert len(changes) == count
    controller.refresh()
    controller.apply_dpi(["800"])
    controller.apply_polling(1000)
    assert not executor.jobs
    assert service.mock_calls == [call.refresh()]
    executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)


def test_blocking_service_runs_off_main_thread_and_changes_are_dispatched():
    main_thread = get_ident()
    release, entered = Event(), Event()
    dispatches = Queue()
    callback_threads, worker_threads = [], []
    service = Mock(spec_set=DesktopService)

    def refresh():
        worker_threads.append(get_ident())
        entered.set()
        assert release.wait(5)
        return Overview(state="Disconnected")

    service.refresh.side_effect = refresh
    with ThreadPoolExecutor(max_workers=1) as executor:
        controller = DesktopController(
            lambda state: callback_threads.append(get_ident()),
            dispatches.put,
            service=service,
            executor=executor,
        )
        try:
            controller.refresh()
            assert entered.wait(5)
            assert controller.state.busy
            assert callback_threads == [main_thread]
            assert worker_threads[0] != main_thread
            release.set()
            dispatches.get(timeout=5)()
            assert callback_threads == [main_thread, main_thread]
            assert not controller.state.busy
        finally:
            release.set()
            controller.close()
