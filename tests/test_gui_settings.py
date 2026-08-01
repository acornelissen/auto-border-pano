"""The stored border settings, and what happens when the file lies."""

from pathlib import Path

import pytest

from maskingframe import pipeline
from maskingframe.gui import settings

pytestmark = pytest.mark.usefixtures("isolated_settings")


def test_the_store_lives_in_the_isolated_directory(isolated_settings: Path) -> None:
    # If this fails, every other test here is writing the developer's real
    # preferences, and the fallback tests below prove nothing.
    settings.save_style(settings.SPLIT, pipeline.FrameStyle(border_percent=11.0))
    written = list(isolated_settings.rglob("*.ini"))
    assert written, f"nothing written under {isolated_settings}"
    assert settings._store().fileName().startswith(str(isolated_settings))


def test_missing_settings_fall_back_to_the_default() -> None:
    assert settings.load_style(settings.SPLIT) == pipeline.DEFAULT_STYLE


def test_a_style_round_trips() -> None:
    style = pipeline.FrameStyle(
        border_percent=12.5,
        border_colour="#c9302a",
        gutter_percent=1.0,
        gutter_colour="#000000",
        border_detail_frames=True,
    )
    settings.save_style(settings.SPLIT, style)
    assert settings.load_style(settings.SPLIT) == style


def test_a_stored_style_without_the_detail_flag_round_trips() -> None:
    style = pipeline.FrameStyle(border_percent=3.0, border_detail_frames=False)
    settings.save_style(settings.COMPOSE, style)
    assert settings.load_style(settings.COMPOSE) == style


def test_the_two_scopes_are_independent() -> None:
    settings.save_style(settings.SPLIT, pipeline.FrameStyle(border_percent=20.0))
    assert settings.load_style(settings.COMPOSE) == pipeline.DEFAULT_STYLE
    assert settings.load_style(settings.SPLIT).border_percent == 20.0


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("border_percent", "not-a-number"),
        ("border_percent", "999"),
        ("border_colour", "chartreuse"),
        ("gutter_percent", "-4"),
        ("gutter_colour", ""),
    ],
)
def test_a_corrupt_value_falls_back_to_the_default(key: str, value: str) -> None:
    # Start from a good style so the fallback is a real change of answer,
    # not the default being returned because nothing was ever stored.
    good = pipeline.FrameStyle(border_percent=12.5, border_colour="#c9302a", gutter_percent=1.0)
    settings.save_style(settings.SPLIT, good)
    assert settings.load_style(settings.SPLIT) == good

    store = settings._store()
    store.setValue(f"{settings.SPLIT}/{key}", value)
    store.sync()
    assert settings._store().value(f"{settings.SPLIT}/{key}") == value

    assert settings.load_style(settings.SPLIT) == pipeline.DEFAULT_STYLE


def test_a_corrupt_value_in_one_scope_does_not_poison_the_other() -> None:
    settings.save_style(settings.COMPOSE, pipeline.FrameStyle(border_percent=20.0))
    store = settings._store()
    store.setValue(f"{settings.SPLIT}/border_colour", "chartreuse")
    store.sync()
    assert settings.load_style(settings.SPLIT) == pipeline.DEFAULT_STYLE
    assert settings.load_style(settings.COMPOSE).border_percent == 20.0
