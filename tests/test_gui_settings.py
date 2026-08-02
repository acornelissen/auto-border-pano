"""The stored border settings, and what happens when the file lies."""

import os
from pathlib import Path

import pytest

from maskingframe import pipeline
from maskingframe.gui import settings
from tests import conftest

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


def test_a_preset_round_trips(isolated_settings: Path) -> None:
    style = pipeline.FrameStyle(border_percent=12.5, border_colour="#102030")
    settings.save_preset(settings.SPLIT, "Warm white", style)

    assert settings.load_presets(settings.SPLIT)["Warm white"] == style


def test_presets_come_back_alphabetically_whatever_order_they_went_in(
    isolated_settings: Path,
) -> None:
    # The list grows, and insertion order stops being findable once it does.
    for name in ("zinc", "Alder", "mahogany"):
        settings.save_preset(settings.SPLIT, name, pipeline.DEFAULT_STYLE)

    assert list(settings.load_presets(settings.SPLIT)) == ["Alder", "mahogany", "zinc"]


def test_the_two_scopes_keep_separate_lists(isolated_settings: Path) -> None:
    # A split border and a composite border are different decisions.
    settings.save_preset(settings.SPLIT, "Mine", pipeline.DEFAULT_STYLE)

    assert "Mine" in settings.load_presets(settings.SPLIT)
    assert "Mine" not in settings.load_presets(settings.COMPOSE)


def test_saving_under_an_existing_name_replaces_it(isolated_settings: Path) -> None:
    settings.save_preset(settings.SPLIT, "Mine", pipeline.DEFAULT_STYLE)
    wider = pipeline.FrameStyle(border_percent=20.0)
    settings.save_preset(settings.SPLIT, "Mine", wider)

    presets = settings.load_presets(settings.SPLIT)
    assert len(presets) == 1
    assert presets["Mine"] == wider


def test_deleting_removes_only_that_preset(isolated_settings: Path) -> None:
    settings.save_preset(settings.SPLIT, "Keep", pipeline.DEFAULT_STYLE)
    settings.save_preset(settings.SPLIT, "Drop", pipeline.DEFAULT_STYLE)

    settings.delete_preset(settings.SPLIT, "Drop")

    assert list(settings.load_presets(settings.SPLIT)) == ["Keep"]


def test_deleting_something_that_is_not_there_is_quiet(isolated_settings: Path) -> None:
    settings.delete_preset(settings.SPLIT, "Never existed")


def test_a_malformed_preset_is_dropped_without_taking_its_neighbours(
    isolated_settings: Path,
) -> None:
    # Losing four good presets over one bad one would be worse than the bug,
    # which is why this does not fall back whole the way load_style does.
    settings.save_preset(settings.SPLIT, "Good", pipeline.DEFAULT_STYLE)
    settings.save_preset(settings.SPLIT, "Bad", pipeline.DEFAULT_STYLE)
    store = settings._store()
    store.setValue(f"{settings.SPLIT}/presets/Bad/border_colour", "not a colour")
    store.sync()

    presets = settings.load_presets(settings.SPLIT)

    assert list(presets) == ["Good"]


def test_a_preset_named_only_whitespace_is_dropped(isolated_settings: Path) -> None:
    # Nothing here writes such a name, but a hand-edited or foreign-written
    # store can hold one, and the interface has no way to delete it: the row
    # strips it to nothing and `delete_preset` finds nothing to remove.
    settings.save_preset(settings.SPLIT, "Good", pipeline.DEFAULT_STYLE)
    store = settings._store()
    store.setValue(f"{settings.SPLIT}/presets/  /border_colour", "#ffffff")
    store.sync()

    assert list(settings.load_presets(settings.SPLIT)) == ["Good"]


def test_a_name_is_trimmed_and_bounded() -> None:
    assert settings.clean_name("  Warm white  ") == "Warm white"
    assert len(settings.clean_name("x" * 100)) == settings.MAX_NAME


def test_an_empty_name_is_refused() -> None:
    with pytest.raises(ValueError, match="name"):
        settings.clean_name("   ")


def test_seeding_puts_the_built_ins_in(isolated_settings: Path) -> None:
    settings.seed_presets()

    for scope in (settings.SPLIT, settings.COMPOSE):
        assert set(settings.load_presets(scope)) == set(settings.BUILT_INS[scope])


def test_a_deleted_built_in_stays_deleted(isolated_settings: Path) -> None:
    # Seeding once and then leaving them alone is what makes a built-in an
    # ordinary preset rather than furniture.
    settings.seed_presets()
    settings.delete_preset(settings.SPLIT, "Gallery")

    settings.seed_presets()

    assert "Gallery" not in settings.load_presets(settings.SPLIT)


def test_an_edited_built_in_is_not_put_back(isolated_settings: Path) -> None:
    settings.seed_presets()
    mine = pipeline.FrameStyle(border_percent=33.0)
    settings.save_preset(settings.SPLIT, "Gallery", mine)

    settings.seed_presets()

    assert settings.load_presets(settings.SPLIT)["Gallery"] == mine


def test_the_split_built_ins_carry_no_gap_decision(isolated_settings: Path) -> None:
    # Split has no gap to set, so a split preset must not smuggle one in.
    for style in settings.BUILT_INS[settings.SPLIT].values():
        assert style.gutter_percent == pipeline.DEFAULT_STYLE.gutter_percent
        assert style.gutter_colour == pipeline.DEFAULT_STYLE.gutter_colour


@pytest.mark.parametrize("separator", ["/", "\\"])
def test_a_name_with_a_separator_is_rejected(separator: str) -> None:
    with pytest.raises(ValueError, match="/"):
        settings.clean_name(f"a{separator}b Portrait")


def test_a_rejected_name_does_not_disturb_a_good_neighbour(isolated_settings: Path) -> None:
    settings.save_preset(settings.SPLIT, "Good", pipeline.DEFAULT_STYLE)

    with pytest.raises(ValueError):
        settings.save_preset(settings.SPLIT, "a/b Portrait", pipeline.DEFAULT_STYLE)

    presets = settings.load_presets(settings.SPLIT)
    assert list(presets) == ["Good"]
    assert presets["Good"] == pipeline.DEFAULT_STYLE


def test_deleting_an_unusable_name_is_quiet(isolated_settings: Path) -> None:
    settings.save_preset(settings.SPLIT, "Good", pipeline.DEFAULT_STYLE)

    settings.delete_preset(settings.SPLIT, "a/b Portrait")
    settings.delete_preset(settings.SPLIT, "   ")

    assert list(settings.load_presets(settings.SPLIT)) == ["Good"]


# --- remembered detail-frame plans -------------------------------------------


def _source(tmp_path: Path, name: str = "pano.jpg", width: int = 3000) -> Path:
    path = tmp_path / name
    conftest.synthetic_panorama(width, 1000).save(path, "JPEG", quality=95)
    return path


def test_a_plan_round_trips(tmp_path: Path) -> None:
    source = _source(tmp_path)
    settings.save_plan(source, (0.0, 0.3, 0.62))

    assert settings.load_plan(source) == (0.0, 0.3, 0.62)


def test_a_source_with_no_plan_returns_nothing(tmp_path: Path) -> None:
    assert settings.load_plan(_source(tmp_path)) is None


def test_a_missing_file_returns_nothing_rather_than_raising(tmp_path: Path) -> None:
    assert settings.load_plan(tmp_path / "gone.jpg") is None


def test_a_plan_is_dropped_when_the_file_has_been_edited(tmp_path: Path) -> None:
    """Crops taken from different pixels are not the crops that were saved."""
    source = _source(tmp_path)
    settings.save_plan(source, (0.0, 0.4))

    conftest.synthetic_panorama(3200, 1000).save(source, "JPEG", quality=95)

    assert settings.load_plan(source) is None


def test_a_plan_is_dropped_when_only_the_mtime_moves(tmp_path: Path) -> None:
    source = _source(tmp_path)
    settings.save_plan(source, (0.0, 0.4))
    stat = source.stat()

    os.utime(source, (stat.st_atime + 120, stat.st_mtime + 120))

    assert settings.load_plan(source) is None


def test_two_sources_keep_their_own_plans(tmp_path: Path) -> None:
    one = _source(tmp_path, "one.jpg")
    two = _source(tmp_path, "two.jpg", width=2400)
    settings.save_plan(one, (0.0, 0.5))
    settings.save_plan(two, (0.1, 0.2, 0.3))

    assert settings.load_plan(one) == (0.0, 0.5)
    assert settings.load_plan(two) == (0.1, 0.2, 0.3)


def test_a_malformed_plan_is_dropped_on_its_own(tmp_path: Path) -> None:
    """`load_presets` drops one bad entry rather than falling back whole,
    and a plan follows it: losing forty-nine good plans over one bad one
    would be worse than the bug that wrote it."""
    good = _source(tmp_path, "good.jpg")
    bad = _source(tmp_path, "bad.jpg", width=2400)
    settings.save_plan(good, (0.0, 0.5))
    settings.save_plan(bad, (0.0, 0.5))

    store = settings._store()
    store.setValue(f"{settings.PLANS}/{settings._plan_key(bad)}/positions", "not a plan")
    store.sync()

    assert settings.load_plan(good) == (0.0, 0.5)
    assert settings.load_plan(bad) is None


@pytest.mark.parametrize(
    "positions",
    [
        (),
        (0.5, 0.2),  # descending
        (-0.1, 0.5),  # outside 0..1
        (0.5, 1.5),
    ],
)
def test_a_plan_that_is_not_a_plan_is_refused(tmp_path: Path, positions: tuple[float, ...]) -> None:
    source = _source(tmp_path)
    settings.save_plan(source, (0.0, 0.5))
    store = settings._store()
    store.setValue(f"{settings.PLANS}/{settings._plan_key(source)}/positions", list(positions))
    store.sync()

    assert settings.load_plan(source) is None


def test_the_store_keeps_only_the_most_recent_plans(tmp_path: Path) -> None:
    sources = [
        _source(tmp_path, f"s{i}.jpg", width=2000 + i) for i in range(settings.MAX_PLANS + 5)
    ]
    for source in sources:
        settings.save_plan(source, (0.0, 0.5))

    kept = [source for source in sources if settings.load_plan(source) is not None]

    assert len(kept) == settings.MAX_PLANS
    assert kept == sources[-settings.MAX_PLANS :], "the wrong end was evicted"


def test_reading_a_plan_counts_as_using_it(tmp_path: Path) -> None:
    """Otherwise reopening the same panorama every day would still see it
    evicted by files you only ever saved once."""
    sources = [_source(tmp_path, f"s{i}.jpg", width=2000 + i) for i in range(settings.MAX_PLANS)]
    for source in sources:
        settings.save_plan(source, (0.0, 0.5))

    settings.load_plan(sources[0])
    newcomer = _source(tmp_path, "new.jpg", width=2500)
    settings.save_plan(newcomer, (0.0, 0.5))

    assert settings.load_plan(sources[0]) == (0.0, 0.5)
    assert settings.load_plan(sources[1]) is None
