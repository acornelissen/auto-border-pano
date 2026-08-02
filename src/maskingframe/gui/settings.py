"""Remembering the user's border choices between launches.

The only module in the GUI package that touches QSettings. A stored value
is untrusted input -- the file is plain text a user can edit, and it
outlives any release -- so every field is validated on read and the whole
style falls back to the default rather than failing the launch.
"""

import hashlib
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path

from PySide6.QtCore import QSettings

from maskingframe import pipeline

ORGANISATION = "maskingframe"
APPLICATION = "Masking Frame"

# A split border and a compose border are different decisions, so they are
# stored separately rather than sharing one value that surprises whichever
# tab the user touches second.
SPLIT = "split"
COMPOSE = "compose"


def _store() -> QSettings:
    """The one place a QSettings is constructed.

    Every reader and writer goes through here so they cannot end up on
    different files -- a bare `QSettings()` picks up whatever names the
    QApplication happens to carry, which is not the same store as an
    explicitly named one, and a test that isolates one would silently leave
    the other pointed at the real preferences.

    Format and scope are stated rather than left to the default, because
    the two-argument `QSettings(organisation, application)` constructor
    pins itself to the platform's native format and then ignores both
    `setDefaultFormat` and `setPath` -- on macOS it writes a plist under
    ~/Library/Preferences no matter what a test asks for. Naming the format
    here is what makes the store both plain text and redirectable.
    """
    return QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        ORGANISATION,
        APPLICATION,
    )


def configure() -> None:
    """Name the settings store. Called once, from `run()`.

    `_store()` states its own names and format, so this exists for the
    stores the application does not construct itself -- Qt's own dialog
    geometry, for one -- and to make INI the default there too, keeping
    everything this application writes plain text and in one place.
    """
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    seed_presets()


def _percent(store: QSettings, key: str, fallback: float) -> float:
    return float(store.value(key, fallback))  # type: ignore[arg-type]


def _flag(store: QSettings, key: str) -> bool:
    """Read a boolean the way an INI file actually stores one.

    Qt writes `true`/`false` and reads them back as strings, so a plain
    `bool()` on the value would call the string "false" true.
    """
    value = store.value(key, False)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def load_style(scope: str) -> pipeline.FrameStyle:
    """Read a stored style, or the default if anything about it is wrong.

    A single bad field discards the whole stored style rather than being
    patched over in isolation: half a remembered setting is more confusing
    than none, and the default is always safe to render with.
    """
    store = _store()
    default = pipeline.DEFAULT_STYLE
    try:
        return pipeline.FrameStyle(
            border_percent=_percent(store, f"{scope}/border_percent", default.border_percent),
            border_colour=str(store.value(f"{scope}/border_colour", default.border_colour)),
            gutter_percent=_percent(store, f"{scope}/gutter_percent", default.gutter_percent),
            gutter_colour=str(store.value(f"{scope}/gutter_colour", default.gutter_colour)),
            border_detail_frames=_flag(store, f"{scope}/border_detail_frames"),
        )
    except (TypeError, ValueError):
        return default


def save_style(scope: str, style: pipeline.FrameStyle) -> None:
    """Store a style for this scope.

    Synced immediately, because the GUI can be killed rather than closed
    and an unwritten preference is indistinguishable from one that was
    never set.
    """
    store = _store()
    store.setValue(f"{scope}/border_percent", style.border_percent)
    store.setValue(f"{scope}/border_colour", style.border_colour)
    store.setValue(f"{scope}/gutter_percent", style.gutter_percent)
    store.setValue(f"{scope}/gutter_colour", style.gutter_colour)
    store.setValue(f"{scope}/border_detail_frames", style.border_detail_frames)
    store.sync()


MAX_NAME = 40
"""How long a preset's name may be.

Long enough for a description, short enough that the combobox in a 320px
rail does not have to elide every entry.
"""

_SEEDED = "presets_seeded"
"""Records that the built-ins have been offered once.

Offered, not maintained: after the first run they are ordinary presets, so
deleting one keeps it deleted and editing one keeps the edit. The cost is
that a preset added in a later release will not appear for an existing
install -- accepted, because the alternative is a tombstone list and two
kinds of preset the interface then has to tell apart.
"""

BUILT_INS: dict[str, dict[str, pipeline.FrameStyle]] = {
    SPLIT: {
        "Plain white": pipeline.FrameStyle(),
        "Gallery": pipeline.FrameStyle(border_percent=18.0),
        "Black surround": pipeline.FrameStyle(border_colour="#14171a"),
    },
    COMPOSE: {
        "Plain white": pipeline.FrameStyle(),
        "Gallery": pipeline.FrameStyle(border_percent=18.0),
        "Black surround": pipeline.FrameStyle(border_colour="#14171a", gutter_colour="#14171a"),
    },
}
"""A few to start from, one set per tab.

Each carries only what its own tab can show: the split entries leave the
gap at its default because Split has no gap control, and neither touches
`border_detail_frames`, which is a decision about a particular carousel
rather than about a look.
"""


def clean_name(name: str) -> str:
    """The name as it will be stored. Raises if there is nothing left of it.

    Rejects `/` and `\\` rather than escaping them: both are group
    separators to `QSettings` on some backends, and a preset name is a
    label a person types and reads back -- a silently escaped name that
    later displays differently from what was typed is its own confusion.
    """
    cleaned = name.strip()[:MAX_NAME].strip()
    if not cleaned:
        raise ValueError("a preset needs a name")
    if "/" in cleaned or "\\" in cleaned:
        raise ValueError("a preset name cannot contain / or \\")
    return cleaned


def _preset_key(scope: str, name: str) -> str:
    return f"{scope}/presets/{name}"


def load_presets(scope: str) -> dict[str, pipeline.FrameStyle]:
    """Every stored preset for this scope, alphabetically.

    A malformed preset is dropped on its own rather than the whole list
    falling back the way `load_style` does. Half a remembered style is more
    confusing than none, but losing four good presets over one bad one
    would be worse than the bug that wrote it.

    Sorted case-insensitively because the list grows: insertion order stops
    being findable once there are more than a handful.
    """
    store = _store()
    store.beginGroup(f"{scope}/presets")
    names = store.childGroups()
    store.endGroup()

    presets: dict[str, pipeline.FrameStyle] = {}
    default = pipeline.DEFAULT_STYLE
    for name in sorted(names, key=str.casefold):
        # A name this application cannot have written -- blank, or all
        # whitespace -- would otherwise be undeletable: the row strips it to
        # nothing, which disables the delete button, and `delete_preset`
        # normalises through the same rule and finds nothing to remove.
        # Dropping it on read is the same posture the fields already take.
        try:
            clean_name(name)
        except ValueError:
            continue
        key = _preset_key(scope, name)
        try:
            presets[name] = pipeline.FrameStyle(
                border_percent=_percent(store, f"{key}/border_percent", default.border_percent),
                border_colour=str(store.value(f"{key}/border_colour", default.border_colour)),
                gutter_percent=_percent(store, f"{key}/gutter_percent", default.gutter_percent),
                gutter_colour=str(store.value(f"{key}/gutter_colour", default.gutter_colour)),
                border_detail_frames=_flag(store, f"{key}/border_detail_frames"),
            )
        except (TypeError, ValueError):
            continue
    return presets


def save_preset(scope: str, name: str, style: pipeline.FrameStyle) -> None:
    """Store one preset, replacing any of the same name."""
    key = _preset_key(scope, clean_name(name))
    store = _store()
    store.setValue(f"{key}/border_percent", style.border_percent)
    store.setValue(f"{key}/border_colour", style.border_colour)
    store.setValue(f"{key}/gutter_percent", style.gutter_percent)
    store.setValue(f"{key}/gutter_colour", style.gutter_colour)
    store.setValue(f"{key}/border_detail_frames", style.border_detail_frames)
    store.sync()


def delete_preset(scope: str, name: str) -> None:
    """Remove one preset. Quiet if it was not there, or was never valid.

    Normalises through `clean_name`, the same path `save_preset` uses, so
    there is one notion of what a preset's name is rather than two. A name
    that `clean_name` rejects cannot have been saved under, so there is
    nothing to remove -- that is a no-op, not an error worth reporting.
    """
    try:
        key = _preset_key(scope, clean_name(name))
    except ValueError:
        return
    store = _store()
    store.remove(key)
    store.sync()


def seed_presets() -> None:
    """Offer the built-ins, once ever.

    Guarded by a flag rather than by whether the list is empty: a user who
    deletes all three has said what they think of them, and putting them
    back on the next launch would be the application arguing.
    """
    store = _store()
    if _flag(store, _SEEDED):
        return
    for scope, presets in BUILT_INS.items():
        for name, style in presets.items():
            save_preset(scope, name, style)
    store.setValue(_SEEDED, True)
    store.sync()


# --- remembered detail-frame plans -------------------------------------------

PLANS = "plans"

MAX_PLANS = 50
"""How many sources' plans are kept.

A plan is a path, two numbers and a handful of floats -- a few hundred bytes
-- so fifty is tens of kilobytes and far more than anyone revisits. The
point of a count rather than an age is that the ceiling is a number that can
be stated, instead of one that depends on how much work you happen to do.
"""

_USED = "used"


def _plan_key(path: Path) -> str:
    """A `QSettings` group name for a source path.

    Hashed rather than used directly: a path is full of the separators
    `QSettings` reads as group boundaries, which is the same trap a preset
    name containing a slash fell into. A hash has none of them, is a fixed
    length, and never needs escaping rules that a reader and a writer could
    implement differently.
    """
    return hashlib.sha256(str(Path(path).resolve()).encode("utf-8")).hexdigest()[:32]


def _file_facts(path: Path) -> tuple[int, int] | None:
    """This file's mtime and size, or None if it is not there.

    The same two facts `pipeline.cached_preview_source` keys its decode on,
    so there is one answer in this codebase to "is this the same file". A
    stat, never a read: deciding whether to restore a handful of floats must
    not cost hundreds of megabytes of I/O on a 132MP scan.
    """
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return (int(stat.st_mtime), int(stat.st_size))


def _read_positions(value: object) -> tuple[float, ...] | None:
    """Validate a stored plan, or refuse it.

    A stored plan is untrusted input, like a stored style: the file is plain
    text that outlives any release. Refused whole for this one source and
    dropped on its own, following `load_presets` rather than `load_style` --
    losing forty-nine good plans over one bad one would be worse than the bug
    that wrote it.
    """
    if not isinstance(value, list | tuple):
        return None
    try:
        positions = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if not positions or any(not 0.0 <= place <= 1.0 for place in positions):
        return None
    if any(later < earlier for earlier, later in pairwise(positions)):
        return None
    return positions


def load_plan(path: Path | str) -> tuple[float, ...] | None:
    """The remembered frames for this source, or None.

    None whenever anything disagrees -- no plan, a plan for a file that has
    since changed, or a plan that does not read as one. The caller then opens
    on the even spread, which is what it did before any of this existed.

    Reading counts as using: otherwise the panorama you reopen every day
    would still be evicted by files you saved once and never came back to.
    """
    facts = _file_facts(Path(path))
    if facts is None:
        return None
    store = _store()
    group = f"{PLANS}/{_plan_key(Path(path))}"
    if not store.contains(f"{group}/positions"):
        return None
    try:
        stored = (
            int(str(store.value(f"{group}/mtime", -1))),
            int(str(store.value(f"{group}/size", -1))),
        )
    except (TypeError, ValueError):
        return None
    if stored != facts:
        return None
    positions = _read_positions(store.value(f"{group}/positions"))
    if positions is None:
        return None
    _touch(store, group)
    return positions


def _number(value: object) -> int:
    """An integer out of whatever the INI file gave back, or zero.

    Qt hands numbers back as strings from an INI store, and a plan edited by
    hand can hold anything at all -- neither is worth raising over when the
    only question being asked is which plan is oldest.
    """
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _counter(store: QSettings) -> int:
    return _number(store.value(f"{PLANS}/counter", 0))


def _touch(store: QSettings, group: str) -> None:
    """Mark this plan the most recently used, by a counter rather than a clock.

    A counter cannot go backwards when the machine's time does, and the only
    question ever asked of it is which plan is oldest.
    """
    counter = _counter(store) + 1
    store.setValue(f"{PLANS}/counter", counter)
    store.setValue(f"{group}/{_USED}", counter)


def _evict(store: QSettings) -> None:
    """Drop the least recently used plans until MAX_PLANS remain."""
    store.beginGroup(PLANS)
    groups = store.childGroups()
    used = {group: _number(store.value(f"{group}/{_USED}", 0)) for group in groups}
    store.endGroup()
    for group in sorted(used, key=lambda name: used[name])[: max(0, len(used) - MAX_PLANS)]:
        store.remove(f"{PLANS}/{group}")


def save_plan(path: Path | str, positions: Sequence[float]) -> None:
    """Remember where this source's frames are.

    Silently does nothing for a file that is not there or a plan that does
    not validate: this runs on every settle, and a storage problem must not
    interrupt somebody placing frames.
    """
    source = Path(path)
    facts = _file_facts(source)
    checked = _read_positions(list(positions))
    if facts is None or checked is None:
        return
    store = _store()
    group = f"{PLANS}/{_plan_key(source)}"
    store.setValue(f"{group}/mtime", facts[0])
    store.setValue(f"{group}/size", facts[1])
    store.setValue(f"{group}/positions", [str(place) for place in checked])
    _touch(store, group)
    _evict(store)
    store.sync()
