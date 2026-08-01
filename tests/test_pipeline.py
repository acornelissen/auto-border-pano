"""Tests for the file-I/O layer."""

from pathlib import Path

import pytest
from PIL import Image

from maskingframe import layout, pipeline
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


def test_process_image_reports_every_frame_in_written_order(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg", 3000, 1250)
    seen: list[tuple[int, int, Path]] = []
    written = pipeline.process_image(
        source,
        tmp_path / "out",
        pipeline.RATIOS["4:5"],
        on_frame=lambda index, total, path: seen.append((index, total, path)),
    )

    assert [s[2] for s in seen] == written
    assert [s[0] for s in seen] == list(range(len(written)))
    # The frame is on disk by the time the callback runs, which is what lets
    # a contact strip fill itself in one thumbnail at a time.
    assert all(path.exists() for _, _, path in seen)


def test_process_image_frame_total_tracks_the_ratio(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg", 3000, 1250)
    for ratio in pipeline.RATIOS.values():
        seen: list[tuple[int, int, Path]] = []

        def record(
            index: int, total: int, path: Path, seen: list[tuple[int, int, Path]] = seen
        ) -> None:
            seen.append((index, total, path))

        written = pipeline.process_image(source, tmp_path / ratio.name, ratio, on_frame=record)
        expected = len(pipeline.output_paths(tmp_path / ratio.name, len(written) - 1))
        assert len(seen) == expected == len(written)
        assert {s[1] for s in seen} == {expected}


def test_process_image_frame_callback_is_optional(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg", 3000, 1250)
    written = pipeline.process_image(source, tmp_path / "out")
    assert all(p.exists() for p in written)


def test_process_image_survives_a_raising_frame_callback(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "pano.jpg", 3000, 1250)

    def explode(index: int, total: int, path: Path) -> None:
        raise RuntimeError("main thread is gone")

    # A broken display callback must not fail a conversion whose frames are
    # already written, so the error is swallowed and every frame still lands.
    written = pipeline.process_image(source, tmp_path / "out", on_frame=explode)
    assert len(written) == 1 + 3
    assert all(p.exists() for p in written)


def test_process_image_rejects_portrait_input(tmp_path: Path) -> None:
    source = _write_panorama(tmp_path / "tall.jpg", 800, 3000)
    with pytest.raises(ValueError, match="portrait"):
        pipeline.process_image(source, tmp_path / "out")


def test_process_image_honours_explicit_positions(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    left = pipeline.process_image(source, tmp_path / "left", positions=(0.0, 0.0))
    spread = pipeline.process_image(source, tmp_path / "spread", positions=(0.0, 0.6))

    # Both runs asked for two detail frames, so both wrote three files.
    assert len(left) == 3 and len(spread) == 3
    # Same position, same picture; different position, different picture.
    assert left[1].read_bytes() == left[2].read_bytes()
    assert spread[1].read_bytes() != spread[2].read_bytes()


def geometry_default_positions(width: int, height: int) -> tuple[float, ...]:
    from maskingframe import geometry

    return geometry.default_positions(width, height, pipeline.DEFAULT_RATIO)


def test_process_image_without_positions_uses_the_even_default(tmp_path: Path) -> None:
    source = tmp_path / "pano.jpg"
    synthetic_panorama(2000, 1000).save(source, "JPEG", quality=95)

    implicit = pipeline.process_image(source, tmp_path / "implicit")
    explicit = pipeline.process_image(
        source,
        tmp_path / "explicit",
        positions=geometry_default_positions(2000, 1000),
    )
    assert [p.read_bytes() for p in implicit] == [p.read_bytes() for p in explicit]


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
        on_frame: pipeline.FrameCallback | None = None,
        positions: object = None,
        style: pipeline.FrameStyle = pipeline.DEFAULT_STYLE,
    ) -> list[Path]:
        if Path(input_path).name == "huge.jpg":
            raise Image.DecompressionBombError("synthetic bomb")
        return real_process_image(input_path, output_prefix, ratio, on_frame, style=style)

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
#   from maskingframe import pipeline
#   for name, ratio in pipeline.RATIOS.items():
#       out = pipeline.process_image(
#           'tests/fixtures/golden_wide.jpg', f'/tmp/g/{name}', ratio
#       )
#       for p in out:
#           print(name, p.name, hashlib.sha256(p.read_bytes()).hexdigest())
#   "
# and confirm the change is expected before updating.
#
# Re-baselined on 2026-08-01: a detail frame is now a full-height crop at
# exactly the output aspect (`pano_height * ratio`) rather than a
# `width // count` tile, so the section digests moved. The padded-frame
# digests did not, and must not.
GOLDEN_HASHES: dict[str, dict[str, str]] = {
    "1:1": {
        "1-1_1_padded.jpg": "b04d5f8f04006521a690d517aa63a6a07a523892ccc1eea16f82783405a0a4ad",
        "1-1_2_section1.jpg": "1754339d45c7d4a7c4bb4621e5a105c8f474c38f66b6450660768495fce9fcab",
        "1-1_3_section2.jpg": "270bdf23c3aee8b2324d2cdd67a77e850de29458271f18bf4f0821e2550e59a0",
    },
    "4:5": {
        "4-5_1_padded.jpg": "5ae4dfa62c8e83d6f753c5c2c78ce1b00da341ed137a08ab57bbec65731cec34",
        "4-5_2_section1.jpg": "2bb1d8d14889b0cc447844f93e974776d8e9c7162c501433293b47ed7d449dcb",
        "4-5_3_section2.jpg": "0d650c8b3fddfb51af1cf1db83fa09ed3268b3ceee340cde06e9354f8a240928",
        "4-5_4_section3.jpg": "9d72470b98e949a32635d0aeacbde45786ec1f5e672f8e2ec0a41d28a11a1812",
    },
    "1.91:1": {
        "1.91-1_1_padded.jpg": "f58e8f599ea7ea905f3cb40c041c3b2d0fdaa8e99eb73a3c00903b611fcb816f",
        "1.91-1_2_section1.jpg": "079ff919cfc95d7475fb20c54f3e067bbad4413af92d1ad2bf207bed14465c93",
        "1.91-1_3_section2.jpg": "9f7c29ed6ab1b95fad1761a935411e619f20d6288a2a91986d52ac6581eec7b9",
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
    "4:5": "6c7af4ab9f6585f353c0598161015fd4fa41542a9010cf8937bd9f9549902128",
    "1:1": "f6b6fa3fdcd9b5914075d3060af419264bf88528cf0693f77d2148ca0172cbd5",
    "1.91:1": "1d0e662f631ff54a4c13b0c192e691511c520c74045b94147bc4c709e65b9442",
}


def test_composite_outputs_are_byte_identical(tmp_path: Path) -> None:
    import hashlib

    for name, expected in COMPOSITE_GOLDEN_HASHES.items():
        result = pipeline.compose_images(
            COMPOSE_FIXTURES, tmp_path / name.replace(":", "-"), pipeline.RATIOS[name]
        )
        actual = hashlib.sha256(result.path.read_bytes()).hexdigest()
        assert actual == expected, f"composite changed at {name}"


PANORAMA_FIXTURE = Path(__file__).parent / "fixtures" / "golden_wide.jpg"

RED_STYLE = pipeline.FrameStyle(border_percent=12.0, border_colour="#c9302a")


def test_process_image_honours_the_style(tmp_path: Path) -> None:
    written = pipeline.process_image(
        PANORAMA_FIXTURE, tmp_path / "out", pipeline.DEFAULT_RATIO, None, style=RED_STYLE
    )
    with Image.open(written[0]) as padded:
        assert padded.convert("RGB").getpixel((0, 0)) == (201, 48, 42)


def test_process_folder_honours_the_style(tmp_path: Path) -> None:
    sources = tmp_path / "in"
    sources.mkdir()
    _write_panorama(sources / "pano.jpg")
    result = pipeline.process_folder(
        sources, tmp_path / "out", pipeline.DEFAULT_RATIO, None, RED_STYLE
    )
    assert result.written
    with Image.open(result.written[0]) as padded:
        assert padded.convert("RGB").getpixel((0, 0)) == (201, 48, 42)


def test_preview_frames_honours_the_style() -> None:
    frames = pipeline.preview_frames(PANORAMA_FIXTURE, pipeline.DEFAULT_RATIO, RED_STYLE)
    assert frames[0].getpixel((0, 0)) == (201, 48, 42)


def test_compose_images_honours_the_style(tmp_path: Path) -> None:
    style = pipeline.FrameStyle(border_colour="#000000", gutter_colour="#c9302a")
    result = pipeline.compose_images(
        COMPOSE_FIXTURES[:2], tmp_path / "out", pipeline.DEFAULT_RATIO, style
    )
    with Image.open(result.path) as composite:
        assert composite.convert("RGB").getpixel((0, 0)) == (0, 0, 0)


def test_compose_preview_and_compose_images_agree_under_a_style(tmp_path: Path) -> None:
    style = pipeline.FrameStyle(border_percent=15.0, gutter_percent=8.0)
    canvas, name = pipeline.compose_preview(COMPOSE_FIXTURES, pipeline.DEFAULT_RATIO, style)
    result = pipeline.compose_images(
        COMPOSE_FIXTURES, tmp_path / "out", pipeline.DEFAULT_RATIO, style
    )
    assert result.layout_name == name
    with Image.open(result.path) as written:
        assert written.size == canvas.size


def test_name_layout_honours_the_style() -> None:
    # A large gutter can change which arrangement wins; the name must follow
    # the style the caller actually rendered with.
    name = pipeline.name_layout(COMPOSE_FIXTURES, pipeline.DEFAULT_RATIO, RED_STYLE)
    solved_name = pipeline.compose_preview(COMPOSE_FIXTURES, pipeline.DEFAULT_RATIO, RED_STYLE)[1]
    assert name == solved_name


def test_style_is_re_exported() -> None:
    assert pipeline.FrameStyle is not None
    assert pipeline.DEFAULT_STYLE.border_percent == 9.0
    assert pipeline.parse_colour("#FFF") == "#ffffff"
    assert pipeline.MAX_PERCENT == 40.0


def test_composite_rects_normalises_the_solved_layout() -> None:
    """The GUI may import pipeline and nothing else, so the gaps have to
    arrive as plain fractions with the arithmetic already done."""
    aspects = [1.5, 0.75]
    ratio = pipeline.RATIOS["4:5"]
    style = pipeline.FrameStyle(border_percent=8.0, gutter_percent=4.0)

    rects = pipeline.composite_rects(aspects, ratio, style)
    solved = layout.solve(aspects, ratio, style)

    assert rects.name == solved.name
    assert rects.panels == tuple(
        (
            box.x / ratio.width,
            box.y / ratio.height,
            box.width / ratio.width,
            box.height / ratio.height,
        )
        for box in solved.boxes
    )
    assert rects.gaps == tuple(
        (
            box.x / ratio.width,
            box.y / ratio.height,
            box.width / ratio.width,
            box.height / ratio.height,
        )
        for box in solved.gutters
    )
    assert all(0.0 <= value <= 1.0 for rect in rects.gaps for value in rect)


def test_composite_rects_has_no_gaps_when_there_is_no_gap() -> None:
    """A zero gap is nothing to draw, not a hairline to draw."""
    rects = pipeline.composite_rects(
        [1.5, 0.75], pipeline.RATIOS["1:1"], pipeline.FrameStyle(gutter_percent=0.0)
    )

    assert rects.gaps == ()
    assert len(rects.panels) == 2


def test_composite_rects_opens_no_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """It is called on every slider move, on the GUI thread. The user's
    scans reach 132MP, so a header read here would stall exactly them."""

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("composite_rects must not touch the filesystem")

    monkeypatch.setattr(Image, "open", forbidden)

    assert pipeline.composite_rects([1.5, 0.75], pipeline.RATIOS["1:1"]).panels
