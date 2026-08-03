"""Tests for the undo stack behind the Split tab's frame placement.

No Qt here on purpose: the history is plain data, so it is tested in memory
the way `geometry` is.
"""

from maskingframe.gui.history import MAX_STEPS, History, Snapshot


def plan(*positions: float, rows: int = 1) -> Snapshot:
    return Snapshot(tuple(positions), rows)


def test_a_fresh_history_offers_nothing_in_either_direction() -> None:
    history = History()

    assert not history.can_undo
    assert not history.can_redo
    assert history.undo_label == ""
    assert history.redo_label == ""


def test_undoing_an_empty_history_returns_nothing_rather_than_raising() -> None:
    history = History()

    assert history.undo() is None
    assert history.redo() is None


def test_undo_returns_the_state_before_the_recorded_one() -> None:
    history = History()
    history.start(plan(0.0, 0.5))
    history.record("Even", plan(0.1, 0.6))

    assert history.undo() == plan(0.0, 0.5)


def test_the_label_names_the_action_being_undone() -> None:
    history = History()
    history.start(plan(0.0, 0.5))
    history.record("Even", plan(0.1, 0.6))

    assert history.undo_label == "Even"


def test_redo_puts_back_what_undo_took_away() -> None:
    history = History()
    history.start(plan(0.0, 0.5))
    history.record("move", plan(0.2, 0.5))
    history.undo()

    assert history.redo_label == "move"
    assert history.redo() == plan(0.2, 0.5)
    assert not history.can_redo


def test_the_row_count_travels_with_the_positions() -> None:
    """A snapshot is the plan, and the plan is both facts."""
    history = History()
    history.start(plan(0.0, 0.5, rows=1))
    history.record("rows", plan(0.0, 0.5, rows=3))

    assert history.undo() == plan(0.0, 0.5, rows=1)


def test_recording_after_an_undo_discards_the_redo_tail() -> None:
    """Otherwise a redo would restore a plan that no longer follows from
    what is on screen."""
    history = History()
    history.start(plan(0.0))
    history.record("move", plan(0.1))
    history.undo()

    history.record("add frame", plan(0.0, 0.5))

    assert not history.can_redo
    assert history.undo() == plan(0.0)


def test_recording_the_state_already_on_screen_is_ignored() -> None:
    """A settle can fire without anything having moved -- an arrow key held
    against the clamp. Recording it would give an undo press that does
    nothing visible."""
    history = History()
    history.start(plan(0.4))
    history.record("move", plan(0.4))

    assert not history.can_undo


def test_the_bound_keeps_the_newest_steps_and_drops_from_the_front() -> None:
    history = History()
    history.start(plan(0.0))
    for step in range(MAX_STEPS + 10):
        history.record("move", plan(float(step + 1) / 1000))

    undone = 0
    while history.can_undo:
        history.undo()
        undone += 1

    assert undone == MAX_STEPS


def test_clear_empties_both_directions() -> None:
    history = History()
    history.start(plan(0.0))
    history.record("move", plan(0.1))
    history.undo()

    history.clear()

    assert not history.can_undo
    assert not history.can_redo


def test_start_leaves_an_existing_history_alone() -> None:
    """Re-reading the same source's header must not wipe work."""
    history = History()
    history.start(plan(0.0))
    history.record("move", plan(0.1))

    history.start(plan(0.9))

    assert history.can_undo
    assert history.undo() == plan(0.0)
