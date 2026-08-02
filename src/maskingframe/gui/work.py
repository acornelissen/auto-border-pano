"""Running slow work off the GUI thread.

This replaces the tkinter rule wholesale rather than restating it. There,
nothing on a worker could touch any tk object and `root.after()` was the
only sanctioned crossing back -- so every worker hand-rolled that crossing.
Here a job returns plain data and the callback runs on the GUI thread: no
marshalling, and the rule is one sentence.

The window-closed guard, though, did not go away, and an earlier version of
this docstring wrongly said it had. Qt drops a queued signal only when the
slot is a bound method of a QObject that has since been destroyed -- it has
a receiver to check. Every callback here is a closure, which has no
receiver, and `submit` deliberately holds the job alive until its callback
runs, so the callback always fires. Close the window during a batch run and
an unguarded closure reaches a `self.strip` whose C++ half has gone, and
raises `RuntimeError` on the GUI thread.

So `submit` takes an `owner`: the widget the callbacks will touch. If it has
been destroyed by the time the answer lands, neither callback is called.
Pass one wherever a callback touches a widget. `shiboken6.isValid` is how
that is asked, and this is the one module that asks it.

One thing `owner` cannot cover is the process itself going away. `run()`
ends in `sys.exit(app.exec())`, which fires the moment the last window
closes, so a job still in flight finds its own signals object destroyed
underneath it and `emit` raises on the worker thread -- a traceback on
stderr that reads as a crash on quit, for an answer nobody was left to
receive. `_Job._emit` drops exactly that case and nothing else.

What also does not go away is staleness. A user can pick a second file
before the first inspection returns, and the older answer must not overwrite
the newer one, so callers still carry a token and compare it in the callback.
"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, SignalInstance
from shiboken6 import isValid

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
            self._emit(self.signals.failed, error)
            return
        self._emit(self.signals.done, result)

    def _emit(self, signal: SignalInstance, payload: object) -> None:
        """Announce the answer, unless there is no longer anybody to tell.

        `submit` holds the job alive until its callback has run, so the only
        way the signals object goes while this is still inside `run` is the
        process itself going: `run()` ends in `sys.exit(app.exec())`, which
        fires the moment the last window closes, and a preview still in
        flight then finds its C++ half destroyed underneath it.

        Nothing is lost by dropping it. The work had already finished, and
        the callback it could not reach was going to touch a window that no
        longer exists. What is lost by *not* dropping it is only a traceback
        on stderr that reads as a crash on quit.

        Deliberately narrow: `RuntimeError` from a dead sender, on a worker
        thread, at teardown. An exception from the work itself is caught
        above and reported like any other.
        """
        try:
            signal.emit(payload)
        except RuntimeError:
            return


def submit(
    work: Callable[[], Any],
    on_done: Callable[[Any], None],
    on_failed: Callable[[BaseException], None] | None = None,
    owner: QObject | None = None,
) -> None:
    """Run `work` off the GUI thread; deliver its result back on it.

    `work` must touch no widget. `on_done` and `on_failed` are called on the
    GUI thread, so they may do whatever they like.

    `owner` is the widget those callbacks touch. If it has been destroyed by
    the time the answer arrives, neither is called -- see this module's
    docstring for why Qt will not do that for a closure. Omit it only when
    the callbacks touch no widget at all.

    A failure is always reported. A job whose exception went nowhere is how
    the tkinter build could leave a button disabled and a status line saying
    "Working..." forever.
    """
    job = _Job(work)

    def alive() -> bool:
        return owner is None or isValid(owner)

    def deliver_done(value: object) -> None:
        if alive():
            on_done(value)

    def deliver_failed(error: BaseException) -> None:
        if not alive():
            return
        if on_failed is not None:
            on_failed(error)
        else:
            on_done(None)

    # Qt deletes a finished QRunnable, which takes its signals object with
    # it -- and a queued signal whose sender has been destroyed is dropped,
    # so the result silently never arrives. Hold the job until its callback
    # has actually run.
    _in_flight.add(job)

    def release(_value: object) -> None:
        _in_flight.discard(job)

    job.signals.done.connect(deliver_done)
    job.signals.failed.connect(deliver_failed)
    job.signals.done.connect(release)
    job.signals.failed.connect(release)
    job.setAutoDelete(False)
    QThreadPool.globalInstance().start(job)
