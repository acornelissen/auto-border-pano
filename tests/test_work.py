"""Tests for running slow work off the GUI thread.

The interesting case is not the happy path -- every tab exercises that --
but the one Qt does not handle for us: a callback that is a closure has no
receiver for Qt to drop it against, so an answer arriving after its widget
has gone would reach a deleted C++ object. `submit` takes an `owner` so it
can decline to deliver.
"""

import threading
from typing import Any

import pytest
import shiboken6
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QWidget

from maskingframe.gui import work
from maskingframe.gui.work import submit

pytest.importorskip("pytestqt")


def test_a_result_arrives_on_the_gui_thread(qtbot: Any) -> None:
    seen: list[object] = []
    owner = QWidget()
    qtbot.addWidget(owner)

    submit(lambda: "done", seen.append, owner=owner)

    qtbot.waitUntil(lambda: seen == ["done"], timeout=3000)


def test_a_failure_is_always_reported(qtbot: Any) -> None:
    """A job whose exception went nowhere is how a button stays disabled
    and a status line says "Working..." forever."""
    seen: list[BaseException] = []
    owner = QWidget()
    qtbot.addWidget(owner)

    def boom() -> None:
        raise OSError("no")

    submit(boom, lambda _value: None, seen.append, owner=owner)

    qtbot.waitUntil(lambda: len(seen) == 1, timeout=3000)
    assert str(seen[0]) == "no"


def test_a_destroyed_owner_gets_no_callback(qtbot: Any) -> None:
    """Close the window during a run and the callback must not fire: it
    would reach a widget whose C++ half has gone and raise on the GUI
    thread. Qt cannot do this for us, because the callback is a closure."""
    seen: list[object] = []
    ran: list[object] = []

    def late() -> str:
        ran.append(None)
        return "late"

    submit(late, seen.append, owner=_dead())

    # Wait on the job, not on the clock: a fixed pause would pass just as
    # happily if the job had never run at all, which proves nothing about
    # the callback being declined. The answer has been delivered on the GUI
    # thread by the time the job is let go of, so the callback has had its
    # chance and passed it up.
    qtbot.waitUntil(lambda: ran != [], timeout=3000)
    qtbot.waitUntil(lambda: not work._in_flight, timeout=3000)
    assert seen == []


def test_a_destroyed_owner_gets_no_failure_callback(qtbot: Any) -> None:
    seen: list[BaseException] = []
    ran: list[object] = []

    def boom() -> None:
        ran.append(None)
        raise OSError("no")

    submit(boom, lambda _value: None, seen.append, owner=_dead())

    qtbot.waitUntil(lambda: ran != [], timeout=3000)
    qtbot.waitUntil(lambda: not work._in_flight, timeout=3000)
    assert seen == []


def test_no_owner_still_delivers(qtbot: Any) -> None:
    """`owner` is optional: a callback touching no widget needs no guard."""
    seen: list[object] = []

    submit(lambda: 1, seen.append)

    qtbot.waitUntil(lambda: seen == [1], timeout=3000)


def _dead() -> QWidget:
    """A widget whose C++ half has been destroyed, wrapper still in hand.

    Exactly the state a tab is in when a run outlives the window that
    started it.
    """
    widget = QWidget()
    # `delete`, not `destroy`: destroy only drops the native window, and the
    # C++ QWidget -- the thing a callback would reach into -- stays valid.
    shiboken6.delete(widget)
    return widget


def test_a_job_whose_signals_have_gone_does_not_raise(qtbot: Any) -> None:
    """The process going away is not a failure worth a traceback.

    `sys.exit(app.exec())` runs the moment the last window closes, so a
    preview still in flight finds its signals object destroyed underneath
    it and `emit` raises on the worker thread. Nothing is lost -- the work
    had finished, and the callback it could not reach was going to touch a
    window that no longer exists -- but Qt prints the traceback to stderr,
    where it reads as a crash on quit.
    """
    started = threading.Event()
    release = threading.Event()

    def slow() -> str:
        started.set()
        release.wait(5)
        return "done"

    job = work._Job(slow)
    QThreadPool.globalInstance().start(job)
    assert started.wait(5)

    # Exactly what teardown does: the C++ half goes while the worker is
    # still inside `run`.
    shiboken6.delete(job.signals)
    release.set()

    assert QThreadPool.globalInstance().waitForDone(5000)


def test_a_failing_job_whose_signals_have_gone_does_not_raise(qtbot: Any) -> None:
    started = threading.Event()
    release = threading.Event()

    def broken() -> str:
        started.set()
        release.wait(5)
        raise ValueError("nobody is listening")

    job = work._Job(broken)
    QThreadPool.globalInstance().start(job)
    assert started.wait(5)

    shiboken6.delete(job.signals)
    release.set()

    assert QThreadPool.globalInstance().waitForDone(5000)
