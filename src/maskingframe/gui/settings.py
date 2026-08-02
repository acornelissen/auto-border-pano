"""Remembering the user's border choices between launches.

The only module in the GUI package that touches QSettings. A stored value
is untrusted input -- the file is plain text a user can edit, and it
outlives any release -- so every field is validated on read and the whole
style falls back to the default rather than failing the launch.
"""

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
    """The name as it will be stored. Raises if there is nothing left of it."""
    cleaned = name.strip()[:MAX_NAME].strip()
    if not cleaned:
        raise ValueError("a preset needs a name")
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
    """Remove one preset. Quiet if it was not there."""
    store = _store()
    store.remove(_preset_key(scope, name.strip()))
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
