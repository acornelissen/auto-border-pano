"""Tests for the file-I/O layer."""

from pathlib import Path

import pytest
from PIL import Image

from auto_border_pano import pipeline
from tests.conftest import synthetic_panorama


def _write_panorama(path: Path, width: int = 3000, height: int = 1250) -> Path:
    synthetic_panorama(width, height).save(path, "JPEG", quality=95)
    return path


def test_output_paths_follow_the_naming_contract() -> None:
    paths = pipeline.output_paths("/tmp/holiday", 3)
    assert [p.name for p in paths] == [
        "holiday_1_padded.jpg",
        "holiday_2_section1.jpg",
        "holiday_3_section2.jpg",
        "holiday_4_section3.jpg",
    ]


def test_output_paths_length_tracks_the_count() -> None:
    assert len(pipeline.output_paths("/tmp/x", 2)) == 3
    assert len(pipeline.output_paths("/tmp/x", 5)) == 6


def test_process_image_writes_frame_one_plus_detail_frames(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg", 3000, 1250)
    written = pipeline.process_image(source, tmp_path / "out", pipeline.RATIOS["4:5"])
    assert len(written) == 1 + 3
    assert all(p.exists() for p in written)


def test_process_image_output_sizes_match_the_ratio(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg", 3000, 1250)
    for ratio in pipeline.RATIOS.values():
        written = pipeline.process_image(source, tmp_path / ratio.name, ratio)
        with Image.open(written[0]) as frame:
            assert abs(frame.width / frame.height - ratio.value) < 0.01
        for detail in written[1:]:
            with Image.open(detail) as img:
                assert img.size == (ratio.width, ratio.height)


def test_process_image_rejects_portrait_input(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "tall.jpg", 800, 3000)
    with pytest.raises(ValueError, match="portrait"):
        pipeline.process_image(source, tmp_path / "out")


def test_find_panoramas_matches_all_jpeg_spellings(tmp_path: Path) -> None:
    for name in ("a.jpg", "b.JPG", "c.jpeg", "d.JPEG", "ignore.png"):
        (tmp_path / name).touch()
    found = {p.name for p in pipeline.find_panoramas(tmp_path)}
    assert found == {"a.jpg", "b.JPG", "c.jpeg", "d.JPEG"}


def test_find_panoramas_does_not_return_duplicates(tmp_path: Path) -> None:
    # On a case-insensitive filesystem (macOS default) naive globbing of
    # both *.jpg and *.JPG returns the same file twice.
    (tmp_path / "only.jpg").touch()
    assert len(pipeline.find_panoramas(tmp_path)) == 1


def test_process_folder_creates_output_dir_and_reports_progress(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "one.jpg", 3000, 1250)
    _write_panorama(source_dir / "two.jpg", 3000, 1250)
    out_dir = tmp_path / "out"

    seen: list[tuple[int, int, str]] = []
    result = pipeline.process_folder(
        source_dir,
        out_dir,
        on_progress=lambda done, total, path: seen.append((done, total, path.name)),
    )

    assert out_dir.is_dir()
    # At the default 4:5 ratio a 3000x1250 panorama produces 1 padded frame
    # plus 3 detail frames per source; sizing the fixtures rather than
    # recomputing via geometry.section_count keeps this test from passing
    # vacuously if both it and the production code were wrong together.
    assert len(result.written) == 2 * (1 + 3)
    assert result.failed == []
    assert result.succeeded_count == 2
    assert [s[:2] for s in seen] == [(0, 2), (1, 2)]


def test_process_folder_continues_after_a_bad_file(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "good.jpg", 3000, 1250)
    (source_dir / "broken.jpg").write_text("not an image")

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert len(result.written) == 1 + 3
    assert result.succeeded_count == 1
    assert len(result.failed) == 1
    failed_path, message = result.failed[0]
    assert failed_path.name == "broken.jpg"
    assert message
    assert result.last_prefix == tmp_path / "out" / "good"
    assert result.last_count == 3


def test_process_folder_fully_failing_batch_is_distinguishable(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    (source_dir / "broken1.jpg").write_text("not an image")
    (source_dir / "broken2.jpg").write_text("also not an image")

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert result.written == []
    assert result.succeeded_count == 0
    assert len(result.failed) == 2
    assert result.last_prefix is None
    assert result.last_count is None


def test_process_folder_continues_past_a_non_oserror_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PIL.Image.DecompressionBombError subclasses Exception directly, not
    # OSError or ValueError -- exactly what a huge panorama triggers. A
    # narrow except tuple here would abort the whole batch, which is the
    # one thing process_folder's docstring promises it prevents.
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "good.jpg", 3000, 1250)
    _write_panorama(source_dir / "huge.jpg", 3000, 1250)

    real_process_image = pipeline.process_image

    def fake_process_image(
        input_path: Path,
        output_prefix: Path,
        ratio: pipeline.AspectRatio = pipeline.DEFAULT_RATIO,
    ) -> list[Path]:
        if Path(input_path).name == "huge.jpg":
            raise Image.DecompressionBombError("synthetic bomb")
        return real_process_image(input_path, output_prefix, ratio)

    monkeypatch.setattr(pipeline, "process_image", fake_process_image)

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert result.succeeded_count == 1
    assert len(result.failed) == 1
    assert result.failed[0][0].name == "huge.jpg"
    assert "synthetic bomb" in result.failed[0][1]


def test_portrait_input_is_recorded_as_a_failure_not_an_abort(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "good.jpg", 3000, 1250)
    _write_panorama(source_dir / "tall.jpg", 800, 3000)

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert result.succeeded_count == 1
    assert [p.name for p, _ in result.failed] == ["tall.jpg"]
    assert "portrait" in result.failed[0][1]


def test_batch_result_counts_sources_not_files(tmp_path: Path) -> None:
    source_dir = tmp_path / "in"
    source_dir.mkdir()
    _write_panorama(source_dir / "a.jpg", 3000, 1250)
    _write_panorama(source_dir / "b.jpg", 3000, 1250)

    result = pipeline.process_folder(source_dir, tmp_path / "out")

    assert result.succeeded_count == 2
    assert result.total_count == 2
    assert result.last_count == 3


# Byte-identity guard for the project's core promise: a given input at a
# given ratio always produces the same images. Covers all three ratios, so
# both branches of the cover-crop are exercised -- 1.91:1 crops the sides of
# a wide section, 4:5 crops the top and bottom.
#
# These hashes are tied to the installed Pillow version's JPEG encoder. If a
# deliberate Pillow upgrade changes encoding, regenerate with:
#   mise exec -- uv run python -c "
#   import hashlib
#   from auto_border_pano import pipeline
#   for name, ratio in pipeline.RATIOS.items():
#       out = pipeline.process_image(
#           'tests/fixtures/golden_wide.jpg', f'/tmp/g/{name}', ratio
#       )
#       for p in out:
#           print(name, p.name, hashlib.sha256(p.read_bytes()).hexdigest())
#   "
# and confirm the change is expected before updating.
GOLDEN_HASHES: dict[str, dict[str, str]] = {
    "1:1": {
        "1-1_1_padded.jpg": "f9474e65db75b945deec39b8083625cbdd933c1acd1895152851dee1dc687c3f",
        "1-1_2_section1.jpg": "fdfca9e094879cd5d933c158a3f76c4f129c73bd9e52bc393243d76fad022b94",
        "1-1_3_section2.jpg": "91b87093c890ebb3ccc796464862357d2d3fa7059136710a21f47bc74c7dc579",
    },
    "4:5": {
        "4-5_1_padded.jpg": "8e6f908127f3c88bf996dd85de34c836dd335250b94a9b1cb0c411e845103930",
        "4-5_2_section1.jpg": "2bb1d8d14889b0cc447844f93e974776d8e9c7162c501433293b47ed7d449dcb",
        "4-5_3_section2.jpg": "0d650c8b3fddfb51af1cf1db83fa09ed3268b3ceee340cde06e9354f8a240928",
        "4-5_4_section3.jpg": "9d72470b98e949a32635d0aeacbde45786ec1f5e672f8e2ec0a41d28a11a1812",
    },
    "1.91:1": {
        "1.91-1_1_padded.jpg": "f703754fc7357a1778ac358d8452acc38618486f995fcea001dab1b6af4ecf64",
        "1.91-1_2_section1.jpg": "bc555a4f1f3b3e6634cdfbe467557829aa142babf9611cf125bb14b786a1bdfd",
        "1.91-1_3_section2.jpg": "72a3de48dd1f5453f92c77a8756c4a9b97f83edc3b70e83d70905096f8f247f3",
    },
}


def test_golden_outputs_are_byte_identical(tmp_path: Path) -> None:
    import hashlib

    golden_source = Path(__file__).parent / "fixtures" / "golden_wide.jpg"
    for name, expected in GOLDEN_HASHES.items():
        ratio = pipeline.RATIOS[name]
        written = pipeline.process_image(
            golden_source,
            tmp_path / name.replace(":", "-"),
            ratio,
        )
        actual = {
            p.name.split("_", 1)[1]: hashlib.sha256(p.read_bytes()).hexdigest() for p in written
        }
        expected_by_suffix = {k.split("_", 1)[1]: v for k, v in expected.items()}
        assert actual == expected_by_suffix, f"output changed at {name}"


COMPOSE_FIXTURES = [
    Path(__file__).parent / "fixtures" / name
    for name in ("compose_wide.jpg", "compose_square.jpg", "compose_tall.jpg")
]


def test_compose_two_images_writes_a_diptych(tmp_path: Path) -> None:
    result = pipeline.compose_images(COMPOSE_FIXTURES[:2], tmp_path / "out")
    assert result.path.name == "out_diptych.jpg"
    assert result.path.exists()
    assert result.layout_name


def test_compose_three_images_writes_a_triptych(tmp_path: Path) -> None:
    result = pipeline.compose_images(COMPOSE_FIXTURES, tmp_path / "out")
    assert result.path.name == "out_triptych.jpg"
    assert result.path.exists()


def test_composite_is_exactly_the_target_size(tmp_path: Path) -> None:
    for ratio in pipeline.RATIOS.values():
        result = pipeline.compose_images(
            COMPOSE_FIXTURES, tmp_path / ratio.name.replace(":", "-"), ratio
        )
        with Image.open(result.path) as img:
            assert img.size == (ratio.width, ratio.height), ratio.name


def test_compose_rejects_wrong_image_counts(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        pipeline.compose_images(COMPOSE_FIXTURES[:1], tmp_path / "out")
    with pytest.raises(ValueError):
        pipeline.compose_images(COMPOSE_FIXTURES * 2, tmp_path / "out")


def test_compose_accepts_portrait_images(tmp_path: Path) -> None:
    # Unlike the splitter, a composite has no notion of a panorama and
    # mixing orientations is the point of the feature.
    tall = COMPOSE_FIXTURES[2]
    result = pipeline.compose_images([tall, tall], tmp_path / "out")
    assert result.path.exists()


def test_compose_preview_renders_without_writing_a_file(tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())

    image, layout_name = pipeline.compose_preview(COMPOSE_FIXTURES[:2])

    assert image.size == (pipeline.DEFAULT_RATIO.width, pipeline.DEFAULT_RATIO.height)
    assert layout_name
    assert set(tmp_path.iterdir()) == before, "compose_preview must not touch the filesystem"


def test_compose_preview_matches_the_requested_ratio(tmp_path: Path) -> None:
    for ratio in pipeline.RATIOS.values():
        image, layout_name = pipeline.compose_preview(COMPOSE_FIXTURES, ratio)
        assert image.size == (ratio.width, ratio.height), ratio.name
        assert layout_name


def test_compose_images_and_compose_preview_agree(tmp_path: Path) -> None:
    # compose_images is a thin save-to-disk wrapper around compose_preview;
    # the pixels and chosen layout must not diverge between them.
    import hashlib
    from io import BytesIO

    preview_image, preview_layout = pipeline.compose_preview(
        COMPOSE_FIXTURES, pipeline.RATIOS["1:1"]
    )
    buffer = BytesIO()
    preview_image.save(buffer, "JPEG", quality=pipeline.JPEG_QUALITY)

    result = pipeline.compose_images(COMPOSE_FIXTURES, tmp_path / "out", pipeline.RATIOS["1:1"])

    assert preview_layout == result.layout_name
    assert (
        hashlib.sha256(buffer.getvalue()).hexdigest()
        == hashlib.sha256(result.path.read_bytes()).hexdigest()
    )


def test_compose_creates_the_output_directory(tmp_path: Path) -> None:
    result = pipeline.compose_images(COMPOSE_FIXTURES[:2], tmp_path / "nested" / "deeper" / "out")
    assert result.path.exists()


# Byte-identity guard for composites, matching the splitter's convention.
# Tied to the installed Pillow version's JPEG encoder; regenerate with the
# command in the plan if a deliberate Pillow upgrade changes encoding.
COMPOSITE_GOLDEN_HASHES: dict[str, str] = {
    "4:5": "b7be8e252cbca29afd49ae081258b3fa5bc62659f33f26821405900ac2c7d1bf",
    "1:1": "ecd4ccdc3bc210725400a05d87a0c647321ad27d4cf398be61890427dd539708",
    "1.91:1": "db881ac7f735c97b3b40d8f6ef1cb023b93369c3d0769ed3393f0550d7043403",
}


def test_composite_outputs_are_byte_identical(tmp_path: Path) -> None:
    import hashlib

    for name, expected in COMPOSITE_GOLDEN_HASHES.items():
        result = pipeline.compose_images(
            COMPOSE_FIXTURES, tmp_path / name.replace(":", "-"), pipeline.RATIOS[name]
        )
        actual = hashlib.sha256(result.path.read_bytes()).hexdigest()
        assert actual == expected, f"composite changed at {name}"
