"""Undo for where the detail frames land.

Placing the frames is the craft work in this application: each position is
chosen by looking at one photograph, and `Even` discards every one of them
in a single press. This is the way back.

No Qt and no I/O, so it is tested in memory the way `geometry` is. It holds
*states* rather than edits -- the whole plan is a handful of floats, so
storing the picture is cheaper than storing the difference and cannot drift
from it.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_STEPS = 50
"""How far back you can walk.

A snapshot is a handful of floats, so this is nothing to hold and far more
than anyone walks back. The bound exists so a long session cannot grow the
list without limit, not because the memory matters."""


@dataclass(frozen=True)
class Snapshot:
    """A plan: where the detail frames are, and how frame 1 is laid out.

    Deliberately not the selection, which is which frame you are looking at
    rather than work you have done, and not the border or the ratio, which
    have their own ways back.
    """

    positions: tuple[float, ...]
    rows: int


class History:
    """A list of plans with a cursor on the one currently on screen."""

    def __init__(self) -> None:
        self._states: list[Snapshot] = []
        # `_labels[i]` names the action that produced `_states[i]`. The
        # baseline has no action behind it, so its label is empty.
        self._labels: list[str] = []
        self._cursor = 0

    def start(self, snapshot: Snapshot) -> None:
        """Set the baseline: the plan as it arrived, before any change.

        Does nothing when there is already a history. A source's header is
        re-read whenever the ratio changes, and wiping the stack on that
        would throw away work in response to a setting that does not touch
        the plan.
        """
        if self._states:
            return
        self._states = [snapshot]
        self._labels = [""]
        self._cursor = 0

    def record(self, label: str, snapshot: Snapshot) -> None:
        """Note that `label` has just produced `snapshot`.

        Anything ahead of the cursor goes: a redo after a fresh change would
        restore a plan that no longer follows from what is on screen.
        """
        if not self._states:
            self.start(snapshot)
            return
        # A settle can fire without anything having moved -- an arrow key
        # held against the clamp, a drag that went nowhere. Recording those
        # would give undo presses that visibly do nothing.
        if self._states[self._cursor] == snapshot:
            return
        del self._states[self._cursor + 1 :]
        del self._labels[self._cursor + 1 :]
        self._states.append(snapshot)
        self._labels.append(label)
        self._cursor = len(self._states) - 1
        # One more state than steps: the baseline is a state nobody stepped
        # into.
        overflow = len(self._states) - (MAX_STEPS + 1)
        if overflow > 0:
            del self._states[:overflow]
            del self._labels[:overflow]
            # The oldest surviving state is now the baseline, whatever
            # produced it.
            self._labels[0] = ""
            self._cursor -= overflow

    def clear(self) -> None:
        """Forget everything. Said of a new source, whose plan this is not."""
        self._states = []
        self._labels = []
        self._cursor = 0

    @property
    def can_undo(self) -> bool:
        return self._cursor > 0

    @property
    def can_redo(self) -> bool:
        return self._cursor + 1 < len(self._states)

    @property
    def undo_label(self) -> str:
        """What undo would take back, named. Empty when there is nothing."""
        return self._labels[self._cursor] if self.can_undo else ""

    @property
    def redo_label(self) -> str:
        """What redo would put back, named. Empty when there is nothing."""
        return self._labels[self._cursor + 1] if self.can_redo else ""

    def undo(self) -> Snapshot | None:
        """Step back one plan, or `None` when there is nowhere to go."""
        if not self.can_undo:
            return None
        self._cursor -= 1
        return self._states[self._cursor]

    def redo(self) -> Snapshot | None:
        """Step forward one plan, or `None` when there is nowhere to go."""
        if not self.can_redo:
            return None
        self._cursor += 1
        return self._states[self._cursor]
