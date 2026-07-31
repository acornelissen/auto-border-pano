"""Tests for the Qt Split tab.

Widget visibility is asserted with `isVisibleTo(tab)` rather than
`isVisible()`: the tab is never shown in a headless run, so `isVisible()` is
False for everything and would pass whatever the code did.
"""

from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from PySide6.QtWidgets import QDialog, QMessageBox, QRadioButton

from auto_border_pano import pipeline
from auto_border_pano.gui.split_tab import NO_COUNT, UNCOUNTED_ACTION, SplitTab, preview_titles
from tests.conftest import synthetic_panorama

pytest.importorskip("pytestqt")


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

    expected = "No JPGs in that folder. Auto Border Pano reads .jpg and .jpeg."
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
