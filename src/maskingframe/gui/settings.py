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
