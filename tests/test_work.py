"""Tests for running slow work off the GUI thread.

The interesting case is not the happy path -- every tab exercises that --
but the one Qt does not handle for us: a callback that is a closure has no
receiver for Qt to drop it against, so an answer arriving after its widget
has gone would reach a deleted C++ object. `submit` takes an `owner` so it
can decline to deliver.
"""

from typing import Any

import pytest
import shiboken6
from PySide6.QtWidgets import QWidget

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

    submit(lambda: "late", seen.append, owner=_dead())

    qtbot.wait(300)
    assert seen == []


def test_a_destroyed_owner_gets_no_failure_callback(qtbot: Any) -> None:
    seen: list[BaseException] = []

    def boom() -> None:
        raise OSError("no")

    submit(boom, lambda _value: None, seen.append, owner=_dead())

    qtbot.wait(300)
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
