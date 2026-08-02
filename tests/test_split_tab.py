"""Tests for the Qt Split tab.

Widget visibility is asserted with `isVisibleTo(tab)` rather than
`isVisible()`: the tab is never shown in a headless run, so `isVisible()` is
False for everything and would pass whatever the code did.
"""

from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QRadioButton, QWidget
from pytestqt.qtbot import QtBot

from maskingframe import pipeline
from maskingframe.gui import settings, shell, split_tab
from maskingframe.gui.split_tab import NO_COUNT, UNCOUNTED_ACTION, SplitTab, preview_titles
from tests import conftest
from tests.conftest import synthetic_panorama

pytest.importorskip("pytestqt")

# The tab reads and writes the stored border style, so every test here must
# be pointed at a throwaway store or it would edit the developer's own
# preferences.
pytestmark = pytest.mark.usefixtures("isolated_settings")


@pytest.fixture
def tab(qtbot: Any) -> SplitTab:
    widget = SplitTab()
    qtbot.addWidget(widget)
    return widget


def _panorama(tmp_path: Path, name: str = "pano.jpg") -> Path:
    source = tmp_path / name
    synthetic_panorama(600, 200).save(source, "JPEG", quality=95)
    return source


@pytest.mark.parametrize("ratio_name", list(pipeline.RATIOS))
def test_frame_count_readout_matches_what_the_pipeline_writes(
    qtbot: Any, tab: SplitTab, tmp_path: Path, ratio_name: str
) -> None:
    """The count in the rail is a promise about files on disk. Check it
    against the real pipeline, for every ratio, not against a stub."""
    source = _panorama(tmp_path)
    ratio = pipeline.RATIOS[ratio_name]
    written = pipeline.process_image(source, tmp_path / f"out-{ratio_name}", ratio)

    tab.ratio_box.setCurrentText(ratio.display)
    tab.source_row.setText(str(source))

    qtbot.waitUntil(lambda: tab.count_label.text() == f"{len(written)} frames")
    assert tab.action_btn.text() == f"Cut {len(written)} frames"
    assert tab.facts_label.text() == "600 × 200 · 3.00:1"  # noqa: RUF001
    assert tab.detail == f"{ratio_name} · {len(written)} frames"
    assert tab.subject == "pano.jpg"


def test_the_readouts_reset_with_no_file_and_in_folder_mode(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    source = _panorama(tmp_path)

    assert tab.count_label.text() == NO_COUNT
    assert tab.facts_label.text() == ""

    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.count_label.text() == "5 frames")
    assert tab.facts_label.text() == "600 × 200 · 3.00:1"  # noqa: RUF001

    tab.folder_radio.setChecked(True)
    assert tab.count_label.text() == NO_COUNT
    assert tab.facts_label.text() == ""
    assert tab.action_btn.text() == UNCOUNTED_ACTION

    tab.single_radio.setChecked(True)
    qtbot.waitUntil(lambda: tab.count_label.text() == "5 frames")

    tab.source_row.setText("")
    assert tab.count_label.text() == NO_COUNT
    assert tab.facts_label.text() == ""


def test_the_mode_radios_actually_switch_mode(tab: SplitTab) -> None:
    """The old build reported the mode with a label describing a control that
    did not exist. These are real radios."""
    radios = tab.findChildren(QRadioButton)
    assert [radio.text() for radio in radios] == ["One frame", "Whole folder"]

    radios[1].setChecked(True)
    assert tab.folder_radio.isChecked() is True
    radios[0].setChecked(True)
    assert tab.folder_radio.isChecked() is False


def test_an_unreadable_source_shows_no_count(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not a jpeg")
    tab.source_row.setText(str(broken))
    qtbot.waitUntil(lambda: tab.subject == "broken.jpg")
    assert tab.count_label.text() == NO_COUNT
    assert tab.action_btn.text() == UNCOUNTED_ACTION


def test_a_stale_inspection_never_overwrites_a_newer_one(tab: SplitTab) -> None:
    """The user can pick a second source before the first header read comes
    back. The older answer must be dropped entirely."""
    tab._inspect_token = 2

    tab._apply_facts(2, pipeline.SourceFacts(4000, 1000, "4.00:1", 5), "4:5", "new.jpg")
    tab._apply_facts(1, pipeline.SourceFacts(100, 100, "1.00:1", 2), "1:1", "old.jpg")

    assert tab.facts_label.text() == "4000 × 1000 · 4.00:1"  # noqa: RUF001
    assert tab.count_label.text() == "5 frames"
    assert tab.action_btn.text() == "Cut 5 frames"
    assert tab.detail == "4:5 · 5 frames"


def test_the_band_detail_uses_the_ratio_the_facts_were_computed_for(tab: SplitTab) -> None:
    """By the time facts arrive the combobox may have moved on. Captioning
    one ratio's frame count with another ratio's name would be a quiet lie."""
    tab.ratio_box.setCurrentText(pipeline.RATIOS["1:1"].display)
    token = tab._inspect_token

    tab._apply_facts(token, pipeline.SourceFacts(600, 200, "3.00:1", 5), "4:5", "pano.jpg")

    assert tab.detail == "4:5 · 5 frames"


def test_the_band_signal_fires_when_the_subject_or_detail_changes(
    qtbot: Any, tab: SplitTab
) -> None:
    seen: list[tuple[str, str]] = []
    tab.band_changed.connect(lambda subject, detail: seen.append((subject, detail)))

    facts = pipeline.SourceFacts(600, 200, "3.00:1", 5)
    tab._apply_facts(tab._inspect_token, facts, "4:5", "a.jpg")

    assert seen == [("a.jpg", "4:5 · 5 frames")]


def test_the_button_label_tracks_the_count(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    source = _panorama(tmp_path)
    assert tab.action_btn.text() == UNCOUNTED_ACTION

    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.action_btn.text() == "Cut 5 frames")

    tab.folder_radio.setChecked(True)
    assert tab.action_btn.text() == UNCOUNTED_ACTION


def test_a_single_run_reports_every_frame_in_order_to_the_strip(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    """Progress *is* the strip: each frame appears as it lands on disk."""
    source = _panorama(tmp_path)
    seen: list[tuple[int, int]] = []
    tab.frame_written.connect(lambda done, total, _path: seen.append((done, total)))

    tab.source_row.setText(str(source))
    tab.dest_row.setText(str(tmp_path / "out"))
    tab.process_images()

    qtbot.waitUntil(lambda: tab.action_btn.isEnabled())
    expected = pipeline.inspect_source(source, pipeline.DEFAULT_RATIO).frame_count
    assert seen == [(n, expected) for n in range(expected)]
    assert tab.strip.frame_count == expected
    assert tab.strip.errors == []
    assert tab.status_label.text() == f"Cut {expected} frames at 4:5 into out"
    assert tab.error_label.text() == ""


def test_a_run_uses_no_modal_for_success_or_failure(
    qtbot: Any, tab: SplitTab, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every messagebox was deleted once already. This is the guard that
    stops one coming back unnoticed."""
    built: list[str] = []
    for cls in (QMessageBox, QDialog):
        original = cls.__init__

        def spy(
            self: Any, *args: Any, _cls: Any = cls, _orig: Any = original, **kwargs: Any
        ) -> None:
            built.append(_cls.__name__)
            _orig(self, *args, **kwargs)

        monkeypatch.setattr(cls, "__init__", spy)

    source = _panorama(tmp_path)
    tab.source_row.setText(str(source))
    tab.dest_row.setText(str(tmp_path / "out"))
    tab.process_images()
    qtbot.waitUntil(lambda: tab.action_btn.isEnabled())

    # And a failure the user did not cause.
    def boom(*_args: Any, **_kwargs: Any) -> list[Path]:
        raise Image.DecompressionBombError("synthetic bomb")

    monkeypatch.setattr(pipeline, "process_image", boom)
    tab.process_images()
    qtbot.waitUntil(lambda: tab.error_label.text() == "synthetic bomb")

    assert tab.status_label.text() == "Could not cut pano.jpg — synthetic bomb"
    assert built == []


def test_the_progress_bar_is_hidden_at_rest_and_shown_during_a_run(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    """At rest the bar was a dead grey slab saying nothing."""
    assert tab.progress_bar.isVisibleTo(tab) is False

    source = _panorama(tmp_path)
    tab.source_row.setText(str(source))
    tab.dest_row.setText(str(tmp_path / "out"))
    tab.process_images()
    assert tab.progress_bar.isVisibleTo(tab) is True

    qtbot.waitUntil(lambda: tab.action_btn.isEnabled())
    assert tab.progress_bar.isVisibleTo(tab) is False


def test_process_images_reports_a_missing_input_inline(tab: SplitTab, tmp_path: Path) -> None:
    tab.source_row.setText(str(tmp_path / "gone.jpg"))
    tab.dest_row.setText(str(tmp_path / "out"))

    tab.process_images()

    assert tab.error_label.text() == "That file is not there any more. Choose another source."
    assert tab.progress_bar.isVisibleTo(tab) is False


def test_process_images_rejects_an_empty_destination(tab: SplitTab, tmp_path: Path) -> None:
    tab.source_row.setText(str(_panorama(tmp_path)))
    tab.dest_row.setText("")

    tab.process_images()

    assert tab.error_label.text() == "Choose where the frames should go."


def test_a_batch_run_names_every_source_and_counts_the_frames(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    folder = tmp_path / "in"
    folder.mkdir()
    _panorama(folder, "a.jpg")
    _panorama(folder, "b.jpg")

    tab.folder_radio.setChecked(True)
    tab.source_row.setText(str(folder))
    tab.dest_row.setText(str(tmp_path / "out"))
    tab.process_images()

    qtbot.waitUntil(lambda: tab.action_btn.isEnabled())
    assert tab.status_label.text() == "Cut 2 sources at 4:5. 10 frames written."
    assert tab.error_label.text() == ""


def test_a_batch_never_claims_success_when_a_source_failed(tab: SplitTab) -> None:
    result = pipeline.BatchResult(
        written=[Path("/tmp/a_1_padded.jpg")],
        failed=[(Path("/tmp/b.jpg"), "portrait input")],
        last_prefix=None,
        last_count=None,
        succeeded_count=1,
    )

    tab._finish_batch(result, "1.91:1")

    assert tab.status_label.text() == "Cut 1 of 2 sources. b.jpg could not be read."
    assert tab.error_label.text() == "b.jpg: portrait input"


def test_an_empty_folder_says_so(tab: SplitTab) -> None:
    tab._finish_batch(pipeline.BatchResult(), pipeline.DEFAULT_RATIO.name)

    expected = "No JPGs in that folder. Masking Frame reads .jpg and .jpeg."
    assert tab.status_label.text() == expected
    assert tab.action_btn.isEnabled() is True


def test_preview_titles_name_the_whole_panorama_first() -> None:
    assert preview_titles(2) == [
        "FRAME 1 · WHOLE PANORAMA",
        "FRAME 2 · DETAIL",
        "FRAME 3 · DETAIL",
    ]


# --- previewing ---------------------------------------------------------------


def test_preview_fills_the_strip_and_writes_nothing(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    """The frames a run would write, on screen, with the disk untouched."""
    source = _panorama(tmp_path)
    before = sorted(tmp_path.iterdir())
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.preview_btn.isEnabled())

    tab.preview()
    qtbot.waitUntil(lambda: tab.preview_btn.isEnabled(), timeout=20000)

    expected = pipeline.inspect_source(source, pipeline.DEFAULT_RATIO).frame_count
    assert tab.strip.frame_count == expected
    assert tab.strip.exposed == expected
    assert tab.strip.errors == []
    assert tab.status_label.text() == f"Preview of {expected} frames at 4:5"
    assert tab.error_label.text() == ""
    # Previewing renders in memory; nothing may land beside the source.
    assert sorted(tmp_path.iterdir()) == before


def test_preview_does_not_need_a_destination(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    """Nothing is written, so there is nothing to ask where to put."""
    source = _panorama(tmp_path)
    tab.source_row.setText(str(source))
    tab.dest_row.setText("")
    qtbot.waitUntil(lambda: tab.preview_btn.isEnabled())

    tab.preview()
    qtbot.waitUntil(lambda: tab.strip.exposed > 0, timeout=20000)

    assert tab.error_label.text() == ""


def test_preview_is_off_without_a_source_and_in_folder_mode(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    assert tab.preview_btn.isEnabled() is False

    source = _panorama(tmp_path)
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.preview_btn.isEnabled())

    # A folder has no one panorama to preview.
    tab.folder_radio.setChecked(True)
    assert tab.preview_btn.isEnabled() is False

    tab.single_radio.setChecked(True)
    assert tab.preview_btn.isEnabled() is True

    tab.source_row.setText(str(tmp_path / "gone.jpg"))
    assert tab.preview_btn.isEnabled() is False


def test_preview_cannot_be_pressed_twice_and_reports_failure_inline(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    portrait = tmp_path / "tall.jpg"
    synthetic_panorama(200, 600).save(portrait, "JPEG", quality=95)
    tab.source_row.setText(str(portrait))
    qtbot.waitUntil(lambda: tab.preview_btn.isEnabled())

    tab.preview()
    # In flight: neither action may be started again.
    assert tab.preview_btn.isEnabled() is False
    assert tab.action_btn.isEnabled() is False

    qtbot.waitUntil(lambda: tab.preview_btn.isEnabled(), timeout=20000)
    assert tab.status_label.text().startswith("Could not preview tall.jpg — ")
    assert "portrait" in tab.error_label.text()


def test_preview_sits_below_the_primary_and_is_not_a_peer_of_it(tab: SplitTab) -> None:
    """Mirrors the Compose tab's own test, so the two rails cannot drift."""
    rail = tab.columns.rail_layout
    order = []
    for index in range(rail.count()):
        item = rail.itemAt(index)
        order.append(None if item is None else item.widget())
    assert order.index(tab.preview_btn) > order.index(tab.action_btn)
    assert tab.action_btn.objectName() == "Primary"
    # An outlined button, not bare text: it still has to read as pressable.
    assert tab.preview_btn.objectName() == "Secondary"


def test_split_tab_restores_the_stored_style(qtbot: Any) -> None:
    settings.save_style(settings.SPLIT, pipeline.FrameStyle(border_percent=17.0))
    restored = SplitTab()
    qtbot.addWidget(restored)
    assert restored._style().border_percent == 17.0


def test_split_tab_stores_a_changed_style(tab: SplitTab) -> None:
    tab.border_controls.border_slider.setValue(21.0)
    assert settings.load_style(settings.SPLIT).border_percent == 21.0


def test_the_rail_shows_every_line_of_its_help_text(qtbot: Any, tab: SplitTab) -> None:
    """Help text that wraps has to be given room for every line it wraps to.

    The border section's labels sit one layout deeper than the rest of the
    rail's, which is exactly where `heightForWidth` stops propagating.
    """
    # The worst case a real window can actually be put in: Qt derives a
    # window's minimum size from its children and refuses to go below it, so
    # the tab is shown at exactly that minimum. Settling it takes a couple of
    # passes, because the wrapped labels only learn their width once they
    # have been laid out at it.
    tab.show()
    qtbot.waitExposed(tab)
    for _ in range(3):
        tab.resize(1100, tab.minimumSizeHint().height())
        qtbot.wait(1)
    clipped = [
        label.text()
        for label in tab.findChildren(QLabel)
        if label.wordWrap()
        and label.text()
        and label.height() < label.heightForWidth(label.width())
    ]
    assert clipped == []


def test_split_tab_offers_the_detail_frame_toggle(tab: SplitTab) -> None:
    assert tab.border_controls.detail_check is not None
    assert tab.border_controls.gutter_slider is None


def test_border_controls_sit_between_the_format_and_the_destination(tab: SplitTab) -> None:
    rail = tab.columns.rail_layout
    order = []
    for index in range(rail.count()):
        item = rail.itemAt(index)
        order.append(None if item is None else item.widget())
    assert order.index(tab.count_label) < order.index(tab.border_controls)
    assert order.index(tab.border_controls) < order.index(tab.dest_row)


def test_preview_honours_the_border_colour(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    """The style has to reach the pipeline, not just the settings file."""
    tab.source_row.setText(str(_panorama(tmp_path)))
    tab.border_controls.border_slider.setValue(10.0)
    tab.border_controls.border_swatch.set_colour("#c9302a")
    qtbot.waitUntil(lambda: tab.preview_btn.isEnabled())

    tab.preview()
    qtbot.waitUntil(lambda: tab.preview_btn.isEnabled(), timeout=20000)
    frames = pipeline.preview_frames(
        str(_panorama(tmp_path)), pipeline.RATIOS[tab._ratio_name()], tab._style()
    )
    assert frames[0].getpixel((0, 0)) == (201, 48, 42)
    assert tab.status_label.text().startswith("Preview of ")


def test_a_run_honours_the_border_colour(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    tab.source_row.setText(str(_panorama(tmp_path)))
    tab.dest_row.setText(str(tmp_path / "out"))
    tab.border_controls.border_swatch.set_colour("#000000")
    qtbot.waitUntil(lambda: tab.preview_btn.isEnabled())

    tab.process_images()
    qtbot.waitUntil(lambda: tab.action_btn.isEnabled(), timeout=20000)
    with Image.open(tmp_path / "out_1_padded.jpg") as padded:
        assert padded.convert("RGB").getpixel((0, 0)) == (0, 0, 0)


def test_a_batch_run_honours_the_border_colour(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    sources = tmp_path / "in"
    sources.mkdir()
    synthetic_panorama(600, 200).save(sources / "one.jpg", "JPEG", quality=95)
    destination = tmp_path / "out"
    tab.folder_radio.setChecked(True)
    tab.source_row.setText(str(sources))
    tab.dest_row.setText(str(destination))
    tab.border_controls.border_swatch.set_colour("#000000")

    tab.process_images()
    qtbot.waitUntil(lambda: tab.action_btn.isEnabled(), timeout=20000)
    with Image.open(destination / "one_1_padded.jpg") as padded:
        assert padded.convert("RGB").getpixel((0, 0)) == (0, 0, 0)


def test_the_border_is_previewed_before_anything_is_loaded(qtbot: Any, tab: SplitTab) -> None:
    """Dialling a border in before choosing a file is the main reason to
    want a live preview, so it has to draw into the empty apertures."""
    tab.strip.resize(900, 400)
    tab.border_controls.border_slider.setValue(10.0)
    tab.border_controls.border_swatch.set_colour("#ff0000")

    preview = tab.strip.border_preview
    assert preview is not None
    assert preview.border == pytest.approx(0.1)
    assert preview.colour == "#ff0000"
    assert tab.strip.exposed == 0
    assert tab.strip.border_rects(0), "an empty frame still has a frame to border"


def test_the_ratio_decides_the_shape_the_border_is_drawn_around(qtbot: Any, tab: SplitTab) -> None:
    tab.ratio_box.setCurrentText(pipeline.RATIOS["4:5"].display)
    portrait = tab.strip.border_preview
    tab.ratio_box.setCurrentText(pipeline.RATIOS["1.91:1"].display)
    landscape = tab.strip.border_preview

    assert portrait is not None and landscape is not None
    assert portrait.aspect == pytest.approx(1080 / 1350)
    assert landscape.aspect == pytest.approx(1080 / 566)


def test_the_detail_frames_toggle_changes_which_frames_show_a_border(
    qtbot: Any, tab: SplitTab
) -> None:
    """A split borders frame 1 always and the details only on request. A
    preview that showed them all would be promising a frame the run will
    not write."""
    tab.strip.resize(900, 400)
    tab.border_controls.border_slider.setValue(10.0)
    check = tab.border_controls.detail_check
    assert check is not None

    check.setChecked(False)
    assert tab.strip.border_rects(0)
    assert tab.strip.border_rects(1) == []

    check.setChecked(True)
    assert tab.strip.border_rects(0)
    assert tab.strip.border_rects(1)


def test_a_zero_border_previews_nothing(qtbot: Any, tab: SplitTab) -> None:
    tab.strip.resize(900, 400)
    tab.border_controls.border_slider.setValue(0.0)

    assert tab.strip.border_rects(0) == []


# --- a render must never outlive the settings it was made under --------------
#
# It is remade rather than dropped: the old frames stay on the table, a
# moment out of date, until the new ones land.


def _previewed(qtbot: Any, tab: SplitTab, tmp_path: Path) -> None:
    source = _panorama(tmp_path)
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.preview_btn.isEnabled())
    tab.preview()
    qtbot.waitUntil(lambda: tab.strip.exposed > 0, timeout=20000)


def _captured_renders(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, Any, Any, Any]]:
    """Hold every submitted job instead of running it.

    The only way to land two answers in a chosen order, which is what a
    staleness test is about.
    """
    captured: list[tuple[Any, Any, Any, Any]] = []
    monkeypatch.setattr(
        split_tab,
        "submit",
        lambda job, done, failed=None, owner=None: captured.append((job, done, failed, owner)),
    )
    return captured


def test_every_job_names_the_widget_its_callbacks_touch(
    qtbot: Any, tab: SplitTab, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Qt drops a queued signal only for a destroyed *bound method*, and
    `submit` connects closures, so a callback with no `owner` reaches a
    widget whose C++ half has gone and raises on the GUI thread."""
    captured = _captured_renders(monkeypatch)
    tab.source_row.setText(str(_panorama(tmp_path)))
    tab.dest_row.setText(str(tmp_path / "out"))
    tab.preview()
    tab.process_images()
    tab.folder_radio.setChecked(True)
    tab.process_images()

    assert captured, "no job was submitted, so nothing was checked"
    assert [owner for *_rest, owner in captured] == [tab] * len(captured)


def test_changing_the_border_renders_the_frames_again(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    """The frames on screen have the old border rendered into them, so they
    are made again under the new one."""
    _previewed(qtbot, tab, tmp_path)
    frames = tab.strip.frame_count
    caption = tab.strip.caption_at(0)

    tab.border_controls.border_slider.setValue(20)

    # No blanking: the old picture is still there while the new one is made.
    assert tab.strip.exposed == frames
    assert tab.status_label.text() == shell.UPDATING_PREVIEW
    qtbot.waitUntil(lambda: tab.status_label.text() != shell.UPDATING_PREVIEW, timeout=20000)
    assert tab.strip.exposed == frames
    # The run itself is untouched: same frames, same numbering, same names.
    assert tab.strip.frame_count == frames
    assert tab.strip.caption_at(0) == caption
    # And a rendered frame still carries no overlay -- its border is in the
    # pixels, and a second band over the first would be wrong.
    assert tab.strip.border_rects(0) == []


def test_dragging_the_slider_does_not_render(
    qtbot: Any, tab: SplitTab, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A render per pixel of drag is the thing the settle exists to stop."""
    _previewed(qtbot, tab, tmp_path)
    captured = _captured_renders(monkeypatch)

    slider = tab.border_controls.border_slider.slider
    slider.setSliderDown(True)
    tab.border_controls.border_slider.setValue(12.0)
    tab.border_controls.border_slider.setValue(14.0)
    assert captured == []
    # The overlay still follows every move.
    preview = tab.strip.border_preview
    assert preview is not None and preview.border == pytest.approx(0.14)

    slider.setSliderDown(False)
    assert len(captured) == 1


def test_changing_the_ratio_renders_the_frames_again(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    _previewed(qtbot, tab, tmp_path)
    before = tab.strip.exposed

    tab.ratio_box.setCurrentText(pipeline.RATIOS["1:1"].display)

    assert tab.strip.exposed == before
    qtbot.waitUntil(lambda: "1:1" in tab.status_label.text(), timeout=20000)
    assert tab.strip.exposed > 0
    assert tab.strip.border_rects(0) == []


def test_a_ratio_change_leaves_the_strip_agreeing_with_the_plan(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    """What the preview shows is what a run writes. A new ratio gives the
    panorama a new count, and the strip has to be rendered from that count
    rather than from the one the old ratio had."""
    _previewed(qtbot, tab, tmp_path)

    tab.ratio_box.setCurrentText(pipeline.RATIOS["1.91:1"].display)

    qtbot.waitUntil(lambda: "1.91:1" in tab.status_label.text(), timeout=20000)
    assert tab.strip.frame_count == len(tab.positions()) + 1
    assert tab.action_btn.text() == f"Cut {tab.strip.frame_count} frames"


def test_the_detail_toggle_renders_the_frames_again(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    _previewed(qtbot, tab, tmp_path)
    assert tab.strip.frame_count > 1
    detail_check = tab.border_controls.detail_check
    assert detail_check is not None

    detail_check.setChecked(True)

    assert tab.strip.exposed > 0
    qtbot.waitUntil(lambda: tab.status_label.text() != shell.UPDATING_PREVIEW, timeout=20000)
    assert tab.strip.border_rects(1) == []


def test_nothing_is_rendered_when_there_is_nothing_on_the_table(
    tab: SplitTab, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty apertures are already showing the live overlay, which is
    exactly what the rail says. There is nothing to redo."""
    captured = _captured_renders(monkeypatch)
    before = tab.status_label.text()

    tab.border_controls.border_slider.setValue(20)

    assert captured == []
    assert tab.status_label.text() == before


def test_a_render_that_cannot_be_made_again_says_so(
    qtbot: Any, tab: SplitTab, tmp_path: Path
) -> None:
    """When the source has gone there is no way back to a true picture, so
    the strip returns to the overlay and the status line accounts for it."""
    _previewed(qtbot, tab, tmp_path)
    (tmp_path / "pano.jpg").unlink()

    tab.border_controls.border_slider.setValue(20)

    assert tab.strip.exposed == 0
    assert tab.strip.border_rects(0)
    assert tab.status_label.text() == shell.STALE_PREVIEW


def test_a_stale_render_does_not_overwrite_a_newer_one(
    qtbot: Any, tab: SplitTab, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two settles in quick succession: the first answer is slower and must
    not land on top of the second."""
    _previewed(qtbot, tab, tmp_path)
    captured = _captured_renders(monkeypatch)

    tab.border_controls.border_slider.setValue(12.0)
    tab.border_controls.border_slider.setValue(20.0)
    assert len(captured) == 2

    newest = pipeline.preview_frames(_panorama(tmp_path), cached=True)
    captured[1][1](newest)
    settled = [tab.strip.caption_at(index) for index in range(tab.strip.frame_count)]
    status = tab.status_label.text()

    # The older job returns last, and is dropped.
    captured[0][1](pipeline.preview_frames(_panorama(tmp_path), pipeline.RATIOS["1:1"]))

    assert tab.strip.frame_count == len(settled)
    assert [tab.strip.caption_at(i) for i in range(tab.strip.frame_count)] == settled
    assert tab.status_label.text() == status


def test_a_failed_re_render_leaves_the_old_frames_up(
    qtbot: Any, tab: SplitTab, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Out of date beats an empty table."""
    _previewed(qtbot, tab, tmp_path)
    captured = _captured_renders(monkeypatch)
    tab.border_controls.border_slider.setValue(20.0)
    exposed = tab.strip.exposed

    captured[0][2](OSError("no"))

    assert tab.strip.exposed == exposed
    assert tab.error_label.text() == "no"


NO_POSITIONS = "Frames are spread evenly. Load one panorama to place them by hand."


def test_the_ribbon_is_hidden_until_a_panorama_is_loaded(qtbot: Any) -> None:
    tab = SplitTab()
    qtbot.addWidget(tab)
    assert not tab.ribbon.isVisibleTo(tab)


def test_loading_a_panorama_shows_the_ribbon(qtbot: Any, tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    assert tab.ribbon.isVisibleTo(tab)
    assert len(tab.positions()) >= 2


def test_folder_mode_hides_the_ribbon_and_says_why(qtbot: Any, tmp_path: Path) -> None:
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.folder_radio.setChecked(True)
    tab.source_row.setText(str(tmp_path))

    assert not tab.ribbon.isVisibleTo(tab)
    assert tab.ribbon_note.isVisibleTo(tab)
    assert tab.ribbon_note.text() == NO_POSITIONS


def test_dragging_in_the_strip_moves_the_matching_position(qtbot: Any, tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    before = tab.positions()
    # Strip frame 1 is detail frame 0. A quarter of a frame width to the right.
    tab.strip.frame_dragged.emit(1, 0.25)

    after = tab.positions()
    assert after[0] > before[0]
    assert after[1:] == before[1:]
    # And the ribbon was told, so the two views cannot disagree.
    assert tab.ribbon.positions() == after


def test_a_strip_drag_stops_at_the_neighbour_instead_of_pushing_it(
    qtbot: Any, tmp_path: Path
) -> None:
    """The far end of the same drag. A strip drag used to hand a raw list to
    a running maximum, which carried every later frame along with it."""
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(3000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: len(tab.positions()) > 2, timeout=3000)

    before = tab.positions()
    # Strip frame 2 is detail frame 1, dragged five frame widths right --
    # well past frame 3.
    tab.strip.frame_dragged.emit(2, 5.0)

    after = tab.positions()
    assert after[1] == pytest.approx(before[2])
    assert after[2:] == before[2:]


def test_a_ribbon_drag_stops_at_the_neighbour_instead_of_pushing_it(
    qtbot: Any, tmp_path: Path
) -> None:
    """The same rule from the other view: one plan, one ordering."""
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(3000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: len(tab.positions()) > 2, timeout=3000)

    before = tab.positions()
    tab.ribbon.frame_moved.emit(1, 5.0)

    after = tab.positions()
    assert after[1] == pytest.approx(before[2])
    assert after[2:] == before[2:]


def test_the_ribbon_and_the_tab_agree_after_a_ribbon_drag(qtbot: Any, tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    tab.ribbon.frame_moved.emit(0, 0.1)

    assert tab.positions()[0] == pytest.approx(0.1)


def test_a_run_cuts_at_the_chosen_positions(
    qtbot: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    seen: dict[str, object] = {}
    real = pipeline.process_image

    # `Any`, not `object`: the arguments are handed straight back to the real
    # function, and --strict will not pass an unpacked `object` tuple to it.
    def spy(*args: Any, **kwargs: Any) -> object:
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline, "process_image", spy)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)
    tab.ribbon.frame_moved.emit(0, 0.1)
    tab.dest_row.setText(str(tmp_path / "out"))
    tab.process_images()
    qtbot.waitUntil(lambda: "positions" in seen, timeout=5000)

    # The value the test itself set, not just whatever the tab happens to
    # hold: if the emit had quietly not landed, both sides of an identity
    # check would be the even defaults and it would still pass.
    forwarded = seen["positions"]
    assert isinstance(forwarded, tuple)
    assert forwarded[0] == pytest.approx(0.1)
    assert forwarded == tab.positions()

    # The run is real, so it has to be let finish: a worker still writing
    # frames when the tab is torn down would report progress to a widget
    # that has gone, and the next test would wear the exception.
    qtbot.waitUntil(lambda: tab.action_btn.isEnabled(), timeout=10000)


def test_adding_a_frame_lands_it_between_the_others(qtbot: Any, tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    before = tab.positions()
    tab.add_frame()

    after = tab.positions()
    assert len(after) == len(before) + 1
    assert list(after) == sorted(after)


def test_removing_a_frame_takes_the_last_one(qtbot: Any, tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    tab.add_frame()
    before = tab.positions()
    tab.remove_frame()

    assert tab.positions() == before[:-1]


def test_the_remove_button_is_dead_at_two_frames(qtbot: Any, tmp_path: Path) -> None:
    # Two is the floor: one detail frame would just restate frame 1.
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    while len(tab.positions()) > 2:
        tab.remove_frame()

    assert not tab.remove_btn.isEnabled()
    tab.remove_frame()
    assert len(tab.positions()) == 2


def test_changing_the_frame_count_restates_the_band(qtbot: Any, tmp_path: Path) -> None:
    """The band is the one thing on screen naming what you are working on.
    Left at the loaded count it would contradict the rail beside it."""
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)

    loaded = len(tab.positions()) + 1
    assert tab.detail == f"4:5 · {loaded} frames"

    tab.add_frame()
    assert tab.detail == f"4:5 · {loaded + 1} frames"
    assert tab.count_label.text() == f"{loaded + 1} frames"

    tab.remove_frame()
    assert tab.detail == f"4:5 · {loaded} frames"


def loaded_tab(qtbot: Any, tmp_path: Path) -> SplitTab:
    """A tab with a panorama loaded and its plan settled."""
    source = tmp_path / "pano.jpg"
    conftest.synthetic_panorama(3000, 1000).save(source, "JPEG", quality=95)
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.source_row.setText(str(source))
    qtbot.waitUntil(lambda: tab.positions() != (), timeout=3000)
    return tab


def test_a_step_moves_the_selected_frame_one_percent(qtbot: Any, tmp_path: Path) -> None:
    tab = loaded_tab(qtbot, tmp_path)
    tab.ribbon.set_selected(1)
    before = tab.positions()

    tab.ribbon.frame_nudged.emit(1, 1)

    after = tab.positions()
    assert after[1] == pytest.approx(before[1] + 0.01)
    assert after[0] == before[0]
    assert after[2:] == before[2:]


def test_a_coarse_step_moves_it_ten_percent(qtbot: Any, tmp_path: Path) -> None:
    tab = loaded_tab(qtbot, tmp_path)
    before = tab.positions()

    tab.ribbon.frame_nudged.emit(1, 10)

    assert tab.positions()[1] == pytest.approx(before[1] + 0.10)


def test_a_hundred_steps_reaches_the_end_of_the_travel(qtbot: Any, tmp_path: Path) -> None:
    tab = loaded_tab(qtbot, tmp_path)
    last = len(tab.positions()) - 1

    tab.ribbon.frame_nudged.emit(last, 100)

    # Clamped by the same rule a drag obeys, so it lands on the travel's end.
    assert tab.positions()[last] == pytest.approx(
        pipeline.position_travel(3000, 1000, pipeline.RATIOS[tab._ratio_name()])
    )


def test_a_key_press_clamps_at_a_neighbour_exactly_as_a_drag_does(
    qtbot: Any, tmp_path: Path
) -> None:
    tab = loaded_tab(qtbot, tmp_path)
    before = tab.positions()

    tab.ribbon.frame_nudged.emit(0, 100)

    after = tab.positions()
    assert after[0] == pytest.approx(before[1])
    assert after[1:] == before[1:]


def test_a_strip_nudge_moves_the_same_frame(qtbot: Any, tmp_path: Path) -> None:
    # Strip frame 2 is detail frame 1: frame 1 is the whole panorama.
    tab = loaded_tab(qtbot, tmp_path)
    before = tab.positions()

    tab.strip.frame_nudged.emit(2, 1)

    assert tab.positions()[1] == pytest.approx(before[1] + 0.01)


def test_the_two_views_mark_the_same_frame(qtbot: Any, tmp_path: Path) -> None:
    tab = loaded_tab(qtbot, tmp_path)

    tab.ribbon.selection_changed.emit(2)

    assert tab.selected() == 2
    assert tab.ribbon.selected() == 2
    # Strip indices are one further along: frame 1 is the whole panorama.
    assert tab.strip.selected() == 3


def test_a_strip_selection_reaches_the_ribbon(qtbot: Any, tmp_path: Path) -> None:
    tab = loaded_tab(qtbot, tmp_path)

    tab.strip.selection_changed.emit(3)

    assert tab.selected() == 2
    assert tab.ribbon.selected() == 2


def test_the_rail_states_the_selection_without_relying_on_colour(
    qtbot: Any, tmp_path: Path
) -> None:
    tab = loaded_tab(qtbot, tmp_path)

    tab.ribbon.selection_changed.emit(1)

    text = tab.selection_label.text()
    # Numbered as the carousel is: detail frame 1 is frame 3.
    assert "Frame 3" in text
    assert "%" in text


def test_the_rail_and_the_widgets_say_the_same_thing(qtbot: Any, tmp_path: Path) -> None:
    """The readout is the non-colour statement of the selection, so it has
    to agree with what a screen reader is told."""
    tab = loaded_tab(qtbot, tmp_path)

    tab.ribbon.selection_changed.emit(1)

    # 3000x1000 at 4:5 gets four detail frames, stepped evenly by a third of
    # the travel, which puts the second one at 24% of the width. Stated literally: agreeing on
    # a wrong number is still wrong.
    assert tab.selection_label.text() == "Frame 3 · 24% along"
    # Verbatim, into both views: one sentence, so a screen reader and the
    # screen cannot say different things about the same frame.
    assert tab.ribbon.accessibleDescription() == "Frame 3 · 24% along"
    assert tab.strip.accessibleDescription() == "Frame 3 · 24% along"
    # Each widget keeps its own plain identity beside that.
    assert tab.ribbon.accessibleName() == "Panorama overview"
    assert tab.strip.accessibleName() == "Contact strip"


def test_the_readout_clears_when_the_source_goes(qtbot: Any, tmp_path: Path) -> None:
    tab = loaded_tab(qtbot, tmp_path)
    tab.ribbon.selection_changed.emit(1)
    assert tab.selection_label.text() != ""

    tab.source_row.setText("")

    assert tab.selection_label.text() == ""
    assert tab.selected() is None


def test_a_shrinking_plan_drops_a_selection_it_can_no_longer_hold(
    qtbot: Any, tmp_path: Path
) -> None:
    """Both views drop a selection their new plan cannot support, so the tab
    must not be left holding a third opinion."""
    tab = loaded_tab(qtbot, tmp_path)
    last = len(tab.positions()) - 1
    tab.ribbon.selection_changed.emit(last)
    assert tab.selected() == last

    while len(tab.positions()) > 2:
        tab.remove_frame()

    assert tab.selected() is None
    assert tab.ribbon.selected() is None
    assert tab.strip.selected() is None
    assert tab.selection_label.text() == ""


def test_a_shrinking_plan_keeps_a_selection_it_still_holds(qtbot: Any, tmp_path: Path) -> None:
    tab = loaded_tab(qtbot, tmp_path)
    tab.ribbon.selection_changed.emit(0)

    tab.remove_frame()

    assert tab.selected() == 0
    assert tab.ribbon.selected() == 0
    assert tab.strip.selected() == 1


def test_the_ribbon_comes_before_the_strip_in_the_tab_order(qtbot: Any, tmp_path: Path) -> None:
    # Source, then results, matching how they sit on the table.
    tab = loaded_tab(qtbot, tmp_path)
    widget: QWidget | None = tab.ribbon
    for _ in range(20):
        assert widget is not None
        widget = widget.nextInFocusChain()
        if widget is tab.strip:
            break
        assert widget is not tab.ribbon, "walked the whole chain without reaching the strip"
    assert widget is tab.strip


def test_taking_focus_alone_states_the_selection_everywhere(qtbot: Any, tmp_path: Path) -> None:
    """A selection marked in chinagraph and nowhere else is carried by
    colour alone. One Tab press has to populate the rail too."""
    tab = loaded_tab(qtbot, tmp_path)

    tab.ribbon.setFocus()

    assert tab.selected() == 0
    assert tab.ribbon.selected() == 0
    assert tab.strip.selected() == 1
    assert tab.selection_label.text() == "Frame 2 · 0% along"


def test_taking_focus_on_the_strip_states_it_too(qtbot: Any, tmp_path: Path) -> None:
    tab = loaded_tab(qtbot, tmp_path)

    tab.strip.setFocus()

    assert tab.selected() == 0
    assert tab.ribbon.selected() == 0
    assert tab.selection_label.text() == "Frame 2 · 0% along"


def test_a_held_key_renders_once_rather_than_per_repeat(qtbot: Any, tmp_path: Path) -> None:
    tab = loaded_tab(qtbot, tmp_path)
    tab.strip.set_frames(preview_titles(len(tab.positions())))
    tab.strip.show_images([synthetic_panorama(40, 40)] * (len(tab.positions()) + 1))
    renders = 0
    original = tab._render

    def counted(*, updating: bool) -> None:
        nonlocal renders
        renders += 1
        original(updating=updating)

    tab._render = counted  # type: ignore[method-assign]

    for _ in range(10):
        tab.ribbon.frame_nudged.emit(0, 1)

    assert renders == 0, "a render per repeat is what the settle exists to prevent"
    qtbot.waitUntil(lambda: renders > 0, timeout=2000)
    assert renders == 1


def test_a_pending_settle_does_not_land_inside_a_run(qtbot: Any, tmp_path: Path) -> None:
    """The settle is a deferral, so a run started inside it would otherwise
    find the strip put back to the overlay under a status saying it is
    cutting frames."""
    tab = loaded_tab(qtbot, tmp_path)
    tab.dest_row.setText(str(tmp_path / "out"))
    tab.strip.set_frames(preview_titles(len(tab.positions())))
    tab.strip.show_images([synthetic_panorama(40, 40)] * (len(tab.positions()) + 1))
    exposed = tab.strip.exposed

    tab.ribbon.frame_nudged.emit(0, 1)
    tab.process_images()

    assert not tab._nudge_timer.isActive()
    assert tab.strip.exposed == exposed
    assert tab.status_label.text() == "Cutting frames"


def test_the_tab_refuses_a_selection_with_no_positions_behind_it(qtbot: Any) -> None:
    """Nothing is loaded, so there is nothing to select. A phantom kept here
    would be promoted into a selection the user never made as soon as a
    panorama arrived."""
    tab = SplitTab()
    qtbot.addWidget(tab)

    tab.strip.selection_changed.emit(1)

    assert tab.selected() is None
    assert tab.strip.selected() is None
    assert tab.ribbon.selected() is None
    assert tab.selection_label.text() == ""


def test_a_drag_keeps_the_spoken_selection_current(qtbot: Any, tmp_path: Path) -> None:
    """A drag moves the frame, so the sentence both widgets speak has to
    move with it -- it went stale between the drag and the drop."""
    tab = loaded_tab(qtbot, tmp_path)
    tab.ribbon.selection_changed.emit(1)
    before = tab.ribbon.accessibleDescription()

    tab.ribbon.frame_moved.emit(1, 0.5)

    assert tab.ribbon.accessibleDescription() != before
    assert tab.ribbon.accessibleDescription() == tab.selection_label.text()
    assert tab.strip.accessibleDescription() == tab.selection_label.text()


def test_the_widgets_say_nothing_when_nothing_is_selected(qtbot: Any, tmp_path: Path) -> None:
    tab = loaded_tab(qtbot, tmp_path)
    tab.ribbon.selection_changed.emit(1)

    tab.source_row.setText("")

    assert tab.ribbon.accessibleDescription() == ""
    assert tab.strip.accessibleDescription() == ""


def test_the_interface_says_the_keys_exist(qtbot: Any, tmp_path: Path) -> None:
    """A keyboard route nothing mentions is a keyboard route nobody finds.
    It belongs where the frames are placed, not in a manual."""
    tab = loaded_tab(qtbot, tmp_path)

    note = tab.ribbon_note.text()
    assert tab.ribbon_note.isVisibleTo(tab)
    for key in ("Left", "Right", "Shift", "Home", "End", "Up", "Down"):
        assert key in note


def test_choosing_a_preset_applies_the_whole_style(qtbot: QtBot, isolated_settings: Path) -> None:
    settings.save_preset(
        settings.SPLIT,
        "Wide",
        pipeline.FrameStyle(border_percent=20.0, border_colour="#102030"),
    )
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()

    tab.border_controls.presets.chosen.emit("Wide")

    style = tab.border_controls.frame_style()
    assert style.border_percent == 20.0
    assert style.border_colour == "#102030"


def test_choosing_a_preset_settles_once(qtbot: QtBot, isolated_settings: Path) -> None:
    # A preset is a user action, so the preview re-renders -- once, the way
    # a slider release does, not once per field it moved.
    settings.save_preset(settings.SPLIT, "Wide", pipeline.FrameStyle(border_percent=20.0))
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()
    settled: list[object] = []
    tab.border_controls.style_settled.connect(settled.append)

    tab.border_controls.presets.chosen.emit("Wide")

    assert len(settled) == 1


def test_saving_a_preset_stores_what_the_rail_shows(qtbot: QtBot, isolated_settings: Path) -> None:
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.border_controls.border_slider.setValue(15.0)

    tab.border_controls.presets.saved.emit("Mine")

    assert settings.load_presets(settings.SPLIT)["Mine"].border_percent == 15.0


def test_deleting_a_preset_takes_it_out_of_the_list(qtbot: QtBot, isolated_settings: Path) -> None:
    settings.save_preset(settings.SPLIT, "Mine", pipeline.DEFAULT_STYLE)
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()

    tab.border_controls.presets.deleted.emit("Mine")

    assert "Mine" not in settings.load_presets(settings.SPLIT)
    assert "Mine" not in [
        tab.border_controls.presets.box.itemText(i)
        for i in range(tab.border_controls.presets.box.count())
    ]


def test_moving_a_control_marks_the_preset_as_edited(qtbot: QtBot, isolated_settings: Path) -> None:
    settings.save_preset(settings.SPLIT, "Wide", pipeline.FrameStyle(border_percent=20.0))
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()
    tab.border_controls.presets.chosen.emit("Wide")

    tab.border_controls.border_slider.setValue(11.0)

    assert tab.border_controls.presets.box.currentText().endswith(shell.EDITED_SUFFIX)


def test_scope_cannot_be_passed_by_position(qtbot: QtBot) -> None:
    """A miscounted positional would give a Compose rail the Split list."""
    with pytest.raises(TypeError):
        shell.BorderControls(False, True, None, settings.COMPOSE)  # type: ignore[call-arg]


def test_saving_an_unusable_name_is_ignored(qtbot: QtBot, isolated_settings: Path) -> None:
    # The row will not emit this, but the handler must not raise out of a
    # slot if anything else does -- delete already swallows it.
    tab = SplitTab()
    qtbot.addWidget(tab)

    tab.border_controls.presets.saved.emit("a/b")

    assert settings.load_presets(settings.SPLIT) == {}


def test_a_restored_style_that_is_a_preset_is_named(qtbot: QtBot, isolated_settings: Path) -> None:
    style = pipeline.FrameStyle(border_percent=20.0)
    settings.save_preset(settings.SPLIT, "Wide", style)
    settings.save_style(settings.SPLIT, style)

    tab = SplitTab()
    qtbot.addWidget(tab)

    assert tab.border_controls.presets.box.currentText() == "Wide"


def test_a_chosen_preset_survives_a_relaunch(qtbot: QtBot, isolated_settings: Path) -> None:
    """The real path: choose one, then build a fresh tab on the same store.

    Writing both the style and the preset into the store by hand would prove
    nothing here -- that is a state choosing a preset never produced.
    """
    style = pipeline.FrameStyle(border_percent=20.0)
    settings.save_preset(settings.SPLIT, "Wide", style)
    tab = SplitTab()
    qtbot.addWidget(tab)
    tab.border_controls.reload_presets()

    tab.border_controls.presets.chosen.emit("Wide")

    relaunched = SplitTab()
    qtbot.addWidget(relaunched)
    assert relaunched.border_controls.frame_style() == style
    assert relaunched.border_controls.presets.box.currentText() == "Wide"


def test_a_restored_style_that_is_no_preset_names_nothing(
    qtbot: QtBot, isolated_settings: Path
) -> None:
    settings.save_preset(settings.SPLIT, "Wide", pipeline.FrameStyle(border_percent=20.0))
    settings.save_style(settings.SPLIT, pipeline.FrameStyle(border_percent=21.0))

    tab = SplitTab()
    qtbot.addWidget(tab)

    assert tab.border_controls.presets.box.currentText() == ""
