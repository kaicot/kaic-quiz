"""Run slow work (grading, PDFs, import, the update check) off the GUI thread.

The job runs on Qt's thread pool; its result comes back to a callback on the GUI thread. An
unexpected exception becomes an ``Err`` with a Korean message, so the window never crashes.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from quiz_reporter.errors import Err, ErrorInfo

LOG = logging.getLogger(__name__)


def unexpected_error(exc: BaseException) -> Err:
    return Err(
        (
            ErrorInfo(
                "UNEXPECTED_ERROR",
                "error.unexpected_error",
                None,
                context={"reason": f"예상하지 못한 오류가 났습니다. ({type(exc).__name__}: {exc})"},
            ),
        )
    )


class _Relay(QObject):
    """Lives on the GUI thread; a signal emitted from the pool is delivered there."""

    done = Signal(object)


class _Job(QRunnable):
    def __init__(self, work: Callable[[], object], relay: _Relay) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._work = work
        self._relay = relay

    def run(self) -> None:
        try:
            result = self._work()
        except Exception as exc:  # reported to the user, not swallowed
            LOG.error("background job failed\n%s", traceback.format_exc())
            result = unexpected_error(exc)
        self._relay.done.emit(result)


class TaskRunner(QObject):
    """One job at a time; ``busy_changed`` lets the window disable buttons meanwhile."""

    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._relay: _Relay | None = None

    @property
    def busy(self) -> bool:
        return self._relay is not None

    def run(self, work: Callable[[], object], on_done: Callable[[object], None]) -> bool:
        """Start ``work``; ``False`` (nothing started) while another job is running."""
        if self._relay is not None:
            return False
        relay = _Relay()
        self._relay = relay

        def finish(result: object) -> None:
            self._relay = None
            self.busy_changed.emit(False)
            on_done(result)

        relay.done.connect(finish)
        self.busy_changed.emit(True)
        self._pool.start(_Job(work, relay))
        return True

    def wait(self, milliseconds: int = 30000) -> bool:
        """For tests and shutdown: block until the pool is idle."""
        return self._pool.waitForDone(milliseconds)


__all__ = ["TaskRunner", "unexpected_error"]
