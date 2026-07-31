"""Running slow work off the GUI thread.

This replaces the tkinter rule wholesale rather than restating it. There,
nothing on a worker could touch any tk object and `root.after()` was the
only sanctioned crossing back -- so every worker hand-rolled that crossing,
and each one needed its own guard against the window closing mid-flight.

Qt queues a signal emitted from another thread to the receiver's thread
automatically, and drops queued events for a destroyed receiver. So the rule
is simply: **a job returns plain data, and the callback runs on the GUI
thread.** No marshalling, no window-closed guard.

What does not go away is staleness. A user can pick a second file before the
first inspection returns, and the older answer must not overwrite the newer
one, so callers still carry a token and compare it in the callback.
"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

_in_flight: set["_Job"] = set()


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Job(QRunnable):
    def __init__(self, work: Callable[[], Any]) -> None:
        super().__init__()
        self._work = work
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self._work()
        except Exception as error:
            self.signals.failed.emit(error)
            return
        self.signals.done.emit(result)


def submit(
    work: Callable[[], Any],
    on_done: Callable[[Any], None],
    on_failed: Callable[[BaseException], None] | None = None,
) -> None:
    """Run `work` off the GUI thread; deliver its result back on it.

    `work` must touch no widget. `on_done` and `on_failed` are called on the
    GUI thread, so they may do whatever they like.

    A failure is always reported. A job whose exception went nowhere is how
    the tkinter build could leave a button disabled and a status line saying
    "Working..." forever.
    """
    job = _Job(work)

    # Qt deletes a finished QRunnable, which takes its signals object with
    # it -- and a queued signal whose sender has been destroyed is dropped,
    # so the result silently never arrives. Hold the job until its callback
    # has actually run.
    _in_flight.add(job)

    def release(_value: object) -> None:
        _in_flight.discard(job)

    job.signals.done.connect(on_done)
    job.signals.failed.connect(on_failed or (lambda _error: on_done(None)))
    job.signals.done.connect(release)
    job.signals.failed.connect(release)
    job.setAutoDelete(False)
    QThreadPool.globalInstance().start(job)
