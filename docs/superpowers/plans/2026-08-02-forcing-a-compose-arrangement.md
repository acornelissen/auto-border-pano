# Forcing a Compose Arrangement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the automatic compose arrangement be rejected, from the GUI and the CLI.

**Architecture:** `layout.solve` keeps its behaviour but is re-expressed on top of a new `rank()` that returns every solvable arrangement best first. Arrangements gain a shell-safe second spelling (`R4.2`). `pipeline` grows an `arrangement` parameter and an `arrangements()` listing. The Compose tab gets an ARRANGEMENT combo; the CLI gets `--arrangement`.

**Tech Stack:** Python 3.13, PySide6, Pillow, pytest, mypy --strict, ruff.

**Spec:** `docs/superpowers/specs/2026-08-02-forcing-a-compose-arrangement-design.md`

## Global Constraints

- Dependency direction is one-way: `geometry` and `layout` are leaves; `compose` uses both; `pipeline` uses all three; `cli` and `gui/` use only `pipeline`. **Production code in `cli.py` and under `gui/` must never import `layout`, `geometry` or `compose`.** Test files may.
- Half-up rounding is `math.floor(v + 0.5)`. Never Python's `round()` — except for the tie key in Task 1, where `round()` on a score is the documented tolerance and is correct.
- `mise run check` (ruff lint, ruff format check, mypy --strict, pytest) must pass before every commit. There is no `uv` on PATH; use `mise run check` and `mise run test -- <args>`.
- Input order is never permuted; nothing is ever cropped.
- In `pipeline`, `style` stays the LAST parameter with a default. `arrangement` goes in front of it.
- Conventional commits, imperative mood. **No Claude attribution trailers and no emoji** anywhere in a commit message — a hook rejects them.
- Work straight on `master`. No branches, no PRs.
- `MIN_PANELS`/`MIN_IMAGES` is 2, `MAX_PANELS`/`MAX_IMAGES` is 6.

---

### Task 1: Rank the arrangements, and give each a short name

**Files:**
- Modify: `src/maskingframe/layout.py` (`solve`, and new functions beside it)
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `candidates`, `evaluate`, `node_depth`, `name_of`, `TIE_TOLERANCE` (all present).
- Produces: `rank(aspects, ratio, style) -> tuple[Layout, ...]`, `short_name(node) -> str`, `parse_name(text, count) -> Node | None`, `TIE_DECIMALS = 9`. Task 2 uses all four.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_layout.py`:

```python
def test_rank_puts_solve_at_its_head() -> None:
    for aspects in ([1.5] * 6, [1.0, 2.0, 0.5], [3.0, 0.67, 1.0, 1.5]):
        for ratio in geometry.RATIOS.values():
            ranked = layout.rank(aspects, ratio, STYLE)
            assert ranked
            assert ranked[0].name == layout.solve(aspects, ratio, STYLE).name


def test_rank_is_ordered_best_first() -> None:
    ranked = layout.rank([1.5] * 6, geometry.SQUARE, STYLE)
    scores = [solved.score for solved in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_lists_every_placeable_arrangement_once() -> None:
    aspects = [1.5, 0.67, 1.0, 1.5]
    ranked = layout.rank(aspects, geometry.SQUARE, STYLE)
    names = [solved.name for solved in ranked]
    placeable = {
        name
        for name, node in layout.candidates(4)
        if layout.evaluate(node, name, aspects, geometry.SQUARE, STYLE) is not None
    }
    assert len(names) == len(set(names))
    assert set(names) == placeable


def test_rank_raises_when_nothing_can_be_placed() -> None:
    # Same inputs as test_no_usable_layout_raises: every candidate needs a
    # leaf under half a pixel, so the ranking is empty and solve must say so
    # rather than returning nothing.
    assert layout.rank([0.001, 0.001], geometry.LANDSCAPE, STYLE) == ()
    with pytest.raises(ValueError):
        layout.solve([0.001, 0.001], geometry.LANDSCAPE, STYLE)


def test_short_name_is_the_axis_and_the_block_sizes() -> None:
    row = layout.Row((layout.Column((layout.Leaf(0), layout.Leaf(1))), layout.Leaf(2)))
    assert layout.short_name(row) == "R2.1"
    column = layout.Column((layout.Leaf(0), layout.Row((layout.Leaf(1), layout.Leaf(2)))))
    assert layout.short_name(column) == "C1.2"


def test_short_names_are_unique_at_every_count() -> None:
    for count in range(layout.MIN_PANELS, layout.MAX_PANELS + 1):
        shorts = [layout.short_name(node) for _, node in layout.candidates(count)]
        assert len(set(shorts)) == len(shorts), count


def test_every_arrangement_round_trips_through_both_spellings() -> None:
    for count in range(layout.MIN_PANELS, layout.MAX_PANELS + 1):
        for name, node in layout.candidates(count):
            assert layout.parse_name(name, count) == node
            assert layout.parse_name(layout.short_name(node), count) == node


def test_a_name_is_read_case_insensitively_and_trimmed() -> None:
    assert layout.parse_name("  r2.2  ", 4) == layout.parse_name("R2.2", 4)
    assert layout.parse_name("r(c(1,2),c(3,4))", 4) == layout.parse_name("R2.2", 4)


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("", 4),
        ("nonsense", 4),
        ("R2.2", 3),  # well formed, but not an arrangement of three
        ("R9.9", 4),  # block sizes that do not add up
        ("R2.2", 1),  # a count the solver does not accept
        ("R2.2", 7),
    ],
)
def test_an_unknown_name_reads_as_nothing_rather_than_raising(text: str, count: int) -> None:
    """`parse_name` never raises: the caller decides what an unknown name
    means, and for the CLI that is a message rather than a traceback."""
    assert layout.parse_name(text, count) is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `mise run test -- tests/test_layout.py -k "rank or short_name or round_trips or unknown_name or case_insensitively" -q`
Expected: FAIL — `layout` has no attribute `rank`.

- [ ] **Step 3: Add the three functions and re-express `solve`**

In `src/maskingframe/layout.py`, put this immediately after the existing `TIE_TOLERANCE` comment and constant:

```python
TIE_DECIMALS = 9
"""`TIE_TOLERANCE` as a number of decimal places, so the same fact can be a
sort key as well as a comparison. Scores closer than the tolerance round to
the same value and fall through to depth, then to name."""


def short_name(node: Node) -> str:
    """The shell-safe spelling: the root axis, then its blocks' sizes.

    `R(C(1,2,3,4),C(5,6))` is `R4.2`. It says exactly as much, because one
    level of grouping means an arrangement *is* a root axis plus a list of
    block sizes -- and it contains nothing a shell reacts to, while the
    parenthesised form is a syntax error unquoted in both zsh and bash.

    A leaf has no axis and no blocks, so it has no short name. Every root
    `candidates` yields is a group, so this is a programming error rather
    than an input this has to tolerate.
    """
    if isinstance(node, Leaf):
        raise ValueError("a leaf has no short name; short_name takes an arrangement's root")
    letter = "R" if isinstance(node, Row) else "C"
    sizes = (1 if isinstance(child, Leaf) else len(child.children) for child in node.children)
    return letter + ".".join(str(size) for size in sizes)


def parse_name(text: str, count: int) -> Node | None:
    """Find the arrangement of `count` panels called `text`, in either
    spelling, or None.

    Matched against the generated list rather than parsed. A parser would be
    a second definition of what a name means and could disagree with
    `name_of` and `short_name`; comparing against what those two actually
    produce cannot. There are at most 62 to compare.

    Never raises, including for a count the solver does not accept: the
    caller decides what an unknown name means, and for the CLI that is a
    message rather than a traceback.
    """
    wanted = text.strip().upper()
    if not wanted or not MIN_PANELS <= count <= MAX_PANELS:
        return None
    for name, node in candidates(count):
        if wanted in (name.upper(), short_name(node).upper()):
            return node
    return None


def rank(
    aspects: Sequence[float],
    ratio: AspectRatio,
    style: FrameStyle = DEFAULT_STYLE,
) -> tuple[Layout, ...]:
    """Every arrangement that can be placed, best first.

    One sort key expresses the whole rule -- fill, then the shallower tree,
    then the earlier name -- because the score is rounded to the tie
    tolerance before it is compared. `solve` is this list's head, so the
    winner and the list a user picks from cannot disagree about the order.

    An arrangement that cannot be placed is absent, exactly as it is absent
    from the winner: `evaluate` returning None is a candidate declining to
    be one.
    """
    for index, aspect in enumerate(aspects):
        if not math.isfinite(aspect) or aspect <= 0:
            raise ValueError(f"aspect at index {index} must be finite and positive, got {aspect!r}")

    solved: list[tuple[float, int, str, Layout]] = []
    for name, node in candidates(len(aspects)):
        placed = evaluate(node, name, aspects, ratio, style)
        if placed is not None:
            solved.append((-round(placed.score, TIE_DECIMALS), node_depth(node), name, placed))
    solved.sort(key=lambda entry: entry[:3])
    return tuple(entry[3] for entry in solved)
```

Then replace the body of `solve` (keeping its signature and its docstring, and appending the new final paragraph):

```python
def solve(
    aspects: Sequence[float],
    ratio: AspectRatio,
    style: FrameStyle = DEFAULT_STYLE,
) -> Layout:
    """Choose the arrangement that fills the frame best without cropping.

    Every candidate keeps each panel at its own aspect ratio, so the first
    question is only which one wastes the least white space. Ties are
    common -- a set of frames from one camera shares an aspect ratio, and
    then whole families of arrangements fill the frame identically -- so
    they are broken by the shallower tree first and the earlier name
    second. Both are properties of the arrangement itself, so the winner
    does not depend on the order `candidates` happens to generate in.

    The head of `rank`, so the arrangement chosen automatically and the list
    a user overrides it from are ordered by one rule rather than two.
    """
    ranked = rank(aspects, ratio, style)
    if not ranked:
        raise ValueError(f"no usable layout for aspects {list(aspects)} at {ratio.name}")
    return ranked[0]
```

- [ ] **Step 4: Run the whole gate**

Run: `mise run check`
Expected: PASS, **including the existing tie tests unchanged**. `test_a_tie_is_won_by_the_shallowest_then_the_first_name`, `test_a_tie_at_equal_depth_is_won_by_the_first_name` and `test_a_clear_win_on_score_beats_a_shallower_arrangement` are the acceptance criterion for the re-expression: if any of them fails, the sort key is wrong. Do not edit them.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(layout): rank the arrangements instead of only winning one

solve computed every candidate and threw all but one away. rank returns
them all, best first, and solve is its head -- so the automatic pick and
the list a user overrides it from are ordered by one rule rather than two.

The tie filter becomes part of the sort key: rounding the score to the
tolerance makes near-ties compare equal and fall through to depth, then to
name. The existing tie tests pass unchanged.

Arrangements also gain a shell-safe spelling. R(C(1,2,3,4),C(5,6)) is a
syntax error unquoted in zsh and bash; R4.2 says the same thing, because
one level of grouping means an arrangement is an axis plus its block
sizes. parse_name matches either against the generated list rather than
parsing, so a second definition of a name cannot drift from the first."
```

---

### Task 2: Let the pipeline be told which arrangement

**Files:**
- Modify: `src/maskingframe/pipeline.py` (`name_layout`, `compose_preview`, `compose_images`, and a new `arrangements`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `layout.rank`, `layout.short_name`, `layout.parse_name`, `layout.name_of`, `layout.evaluate` from Task 1.
- Produces: `Arrangement` (frozen dataclass: `name: str`, `short_name: str`, `fill: float`), `arrangements(paths, ratio, style) -> tuple[Arrangement, ...]`, and an `arrangement: str = ""` parameter on `name_layout`, `compose_preview` and `compose_images`, positioned **before** `style`. Tasks 3 and 4 use these and must not import `layout`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
def _sources(tmp_path: Path, count: int) -> list[Path]:
    shapes = [(600, 400), (400, 600), (500, 500), (900, 400), (400, 900), (700, 500)]
    paths = []
    for index in range(count):
        width, height = shapes[index]
        path = tmp_path / f"s{index}.jpg"
        synthetic_panorama(width, height).save(path, "JPEG", quality=95)
        paths.append(path)
    return paths


def test_arrangements_lists_every_candidate_best_first(tmp_path: Path) -> None:
    options = pipeline.arrangements(_sources(tmp_path, 4), pipeline.DEFAULT_RATIO)

    assert len(options) == len({option.name for option in options})
    fills = [option.fill for option in options]
    assert fills == sorted(fills, reverse=True)
    assert options[0].name == pipeline.name_layout(_sources(tmp_path, 4), pipeline.DEFAULT_RATIO)


def test_arrangements_carries_both_spellings(tmp_path: Path) -> None:
    options = pipeline.arrangements(_sources(tmp_path, 4), pipeline.DEFAULT_RATIO)
    for option in options:
        assert option.name.startswith(("R(", "C("))
        assert option.short_name[0] in "RC"
        assert "(" not in option.short_name
        assert 0.0 < option.fill <= 1.0


def test_a_forced_arrangement_is_the_one_rendered(tmp_path: Path) -> None:
    """Forcing has to reach the pixels, not just the name -- the whole point
    is a different composite, so the boxes must differ from the automatic
    ones as well as the label."""
    paths = _sources(tmp_path, 4)
    automatic = pipeline.name_layout(paths, pipeline.DEFAULT_RATIO)
    other = next(
        option.short_name
        for option in pipeline.arrangements(paths, pipeline.DEFAULT_RATIO)
        if option.name != automatic
    )

    _, forced_name = pipeline.compose_preview(paths, pipeline.DEFAULT_RATIO, other)

    assert forced_name != automatic
    assert pipeline.name_layout(paths, pipeline.DEFAULT_RATIO, other) == forced_name


def test_a_forced_arrangement_is_written(tmp_path: Path) -> None:
    paths = _sources(tmp_path, 4)
    automatic = pipeline.name_layout(paths, pipeline.DEFAULT_RATIO)
    other = next(
        option.name
        for option in pipeline.arrangements(paths, pipeline.DEFAULT_RATIO)
        if option.name != automatic
    )

    result = pipeline.compose_images(paths, tmp_path / "out", pipeline.DEFAULT_RATIO, other)

    assert result.layout_name == other
    assert result.path.name == "out_tetraptych.jpg"


def test_an_empty_arrangement_means_automatic(tmp_path: Path) -> None:
    paths = _sources(tmp_path, 4)
    assert pipeline.name_layout(paths, pipeline.DEFAULT_RATIO, "") == pipeline.name_layout(
        paths, pipeline.DEFAULT_RATIO
    )


def test_an_unknown_arrangement_names_both_spellings(tmp_path: Path) -> None:
    paths = _sources(tmp_path, 4)
    with pytest.raises(ValueError) as caught:
        pipeline.compose_preview(paths, pipeline.DEFAULT_RATIO, "nonsense")

    message = str(caught.value)
    assert "nonsense" in message
    assert "4" in message
    assert "R2.2" in message


def test_an_arrangement_for_the_wrong_count_is_refused(tmp_path: Path) -> None:
    """R2.2 is four panels. Asked for with three sources it is not a typo,
    it is a different composite, and saying so beats silently ignoring it."""
    with pytest.raises(ValueError, match="R2.2"):
        pipeline.name_layout(_sources(tmp_path, 3), pipeline.DEFAULT_RATIO, "R2.2")
```

- [ ] **Step 2: Run them and watch them fail**

Run: `mise run test -- tests/test_pipeline.py -k "arrangement" -q`
Expected: FAIL — `pipeline` has no attribute `arrangements`.

- [ ] **Step 3: Add the dataclass, the listing and the forcing**

In `src/maskingframe/pipeline.py`, beside `CompositeResult`, add:

```python
@dataclass(frozen=True)
class Arrangement:
    """One arrangement offered to a user, in both spellings.

    No English: `present_layout` in the GUI turns a name into words, and
    moving that down here would put interface copy in a module that has
    none.
    """

    name: str
    short_name: str
    fill: float
```

Add these two helpers above `name_layout`:

```python
def _aspects_of(paths: Sequence[Path]) -> list[float]:
    """Each source's aspect ratio, read from its header and nothing more."""
    aspects = []
    for path in paths:
        with Image.open(path) as opened:
            width, height = opened.size
        aspects.append(width / height)
    return aspects


def _chosen_layout(
    arrangement: str,
    aspects: Sequence[float],
    ratio: AspectRatio,
    style: FrameStyle,
) -> layout.Layout:
    """Solve, or place the arrangement that was asked for.

    An arrangement named but not usable is an error rather than a fallback:
    silently composing something else would put a picture on disk that is
    not the one that was asked for.
    """
    if not arrangement:
        return layout.solve(aspects, ratio, style)
    node = layout.parse_name(arrangement, len(aspects))
    if node is None:
        example = layout.short_name(next(iter(layout.candidates(len(aspects))))[1])
        raise ValueError(
            f"unknown arrangement {arrangement!r} for {len(aspects)} images; "
            f"spell it like {example} (or the long form in quotes)"
        )
    placed = layout.evaluate(node, layout.name_of(node), aspects, ratio, style)
    if placed is None:
        raise ValueError(f"arrangement {arrangement!r} cannot be placed at {ratio.name}")
    return placed


def arrangements(
    input_paths: Sequence[Path | str],
    ratio: AspectRatio = DEFAULT_RATIO,
    style: FrameStyle = DEFAULT_STYLE,
) -> tuple[Arrangement, ...]:
    """Every arrangement these sources could take, best first.

    Reads headers and stops, like `name_layout`: choosing an arrangement
    must not cost a decode per candidate.
    """
    paths = [Path(p) for p in input_paths]
    if len(paths) not in COMPOSITE_SUFFIXES:
        raise ValueError(f"expected {MIN_IMAGES} to {MAX_IMAGES} images, got {len(paths)}")
    aspects = _aspects_of(paths)
    nodes = dict(layout.candidates(len(aspects)))
    return tuple(
        Arrangement(placed.name, layout.short_name(nodes[placed.name]), placed.score)
        for placed in layout.rank(aspects, ratio, style)
    )
```

Now change the three entry points. Each gains `arrangement: str = ""` **before** `style`, and uses `_chosen_layout`:

- `name_layout(input_paths, ratio=DEFAULT_RATIO, arrangement="", style=DEFAULT_STYLE) -> str` — replace its aspect-reading loop with `_aspects_of(paths)` and return `_chosen_layout(arrangement, aspects, ratio, style).name`.
- `compose_preview(input_paths, ratio=DEFAULT_RATIO, arrangement="", style=DEFAULT_STYLE)` — replace `solved = layout.solve(aspects, ratio, style)` with `solved = _chosen_layout(arrangement, aspects, ratio, style)`, and use `_aspects_of` for the sizes loop.
- `compose_images(input_paths, output_prefix, ratio=DEFAULT_RATIO, arrangement="", style=DEFAULT_STYLE)` — pass `arrangement` straight through to `compose_preview`.

Add to each docstring a sentence saying that an empty `arrangement` means the solver chooses, and that a named one is placed as given or refused.

**Every existing caller passing `style` positionally will now pass it as `arrangement`.** Find them — `cli.py` and `gui/compose_tab.py` — and make them spell `style=style`. Run the full suite before assuming there are no others.

- [ ] **Step 4: Run the gate**

Run: `mise run check`
Expected: PASS. If a test fails with a `FrameStyle` where a `str` was expected, that is a positional caller you have not converted yet.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(pipeline): compose the arrangement that was asked for

name_layout, compose_preview and compose_images take an arrangement name,
empty meaning the solver chooses. A name that does not parse, or that
names an arrangement these sources cannot have, is an error rather than a
fallback: silently composing something else would write a picture nobody
asked for.

arrangements() lists every candidate best first in both spellings, reading
headers only, so offering the choice costs no decodes."
```

---

### Task 3: `--arrangement` on the command line

**Files:**
- Modify: `src/maskingframe/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `pipeline.compose_images`, `pipeline.Arrangement` and the `arrangement` parameter from Task 2.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def _compose_sources(tmp_path: Path, count: int = 4) -> list[str]:
    paths = []
    for index in range(count):
        path = tmp_path / f"s{index}.jpg"
        synthetic_panorama(500 + index * 50, 400).save(path, "JPEG", quality=95)
        paths.append(str(path))
    return paths


def test_both_spellings_compose_the_same_arrangement(tmp_path: Path, capsys: Any) -> None:
    sources = _compose_sources(tmp_path)

    cli.main(["compose", *sources, "-o", str(tmp_path / "short"), "--arrangement", "R2.2"])
    cli.main(
        ["compose", *sources, "-o", str(tmp_path / "long"), "--arrangement", "R(C(1,2),C(3,4))"]
    )

    assert (tmp_path / "short_tetraptych.jpg").read_bytes() == (
        tmp_path / "long_tetraptych.jpg"
    ).read_bytes()


def test_the_success_line_shows_what_to_type_back(tmp_path: Path, capsys: Any) -> None:
    """A name you cannot copy is not an identifier. The long form needs
    quoting in a shell, so the line that offers it prints the short one."""
    sources = _compose_sources(tmp_path)

    cli.main(["compose", *sources, "-o", str(tmp_path / "out"), "--arrangement", "R2.2"])

    printed = capsys.readouterr().out
    assert "R(C(1,2),C(3,4))" in printed
    assert "--arrangement R2.2" in printed


def test_a_misspelt_arrangement_fails_at_parse_time(tmp_path: Path, capsys: Any) -> None:
    sources = _compose_sources(tmp_path)

    with pytest.raises(SystemExit):
        cli.main(["compose", *sources, "-o", str(tmp_path / "out"), "--arrangement", "sideways"])

    assert "sideways" in capsys.readouterr().err


def test_an_arrangement_for_the_wrong_count_names_both_numbers(
    tmp_path: Path, capsys: Any
) -> None:
    sources = _compose_sources(tmp_path, count=3)

    with pytest.raises(SystemExit):
        cli.main(["compose", *sources, "-o", str(tmp_path / "out"), "--arrangement", "R2.2"])

    message = capsys.readouterr().err
    assert "R2.2" in message
    assert "3" in message
```

- [ ] **Step 2: Run them and watch them fail**

Run: `mise run test -- tests/test_cli.py -k "arrangement or success_line" -q`
Expected: FAIL — `--arrangement` is not a recognised argument.

- [ ] **Step 3: Add the flag**

In `src/maskingframe/cli.py`, add a converter beside the other `type=` converters:

```python
_ARRANGEMENT = re.compile(r"^(?:[RC][0-9](?:\.[0-9])*|[RC]\(.+\))$", re.IGNORECASE)


def _arrangement(value: str) -> str:
    """Check the *spelling* here, not the arrangement.

    Whether an arrangement exists depends on how many sources there are,
    which argparse does not know: the inputs are `nargs="+"` and are counted
    afterwards. So a typo fails here with argparse's own message and a
    well-spelt name that no arrangement answers to fails in the run, where
    the count is known and can be named.
    """
    text = value.strip()
    if not _ARRANGEMENT.match(text):
        raise argparse.ArgumentTypeError(
            f"invalid arrangement '{value}': spell it like R2.2, "
            "or the long form 'R(C(1,2),C(3,4))' in quotes"
        )
    return text
```

Add `import re` at the top if it is not already there.

Register it on the compose parser only:

```python
parser.add_argument(
    "--arrangement",
    type=_arrangement,
    default="",
    help=(
        "force an arrangement instead of choosing the best fit, "
        "e.g. R2.2 (two columns of two). The long form needs quoting."
    ),
)
```

Pass it through the compose run — remembering that `style` must now be spelled as a keyword — and print both spellings on success:

```python
result = pipeline.compose_images(
    args.inputs, args.output, args.ratio, args.arrangement, style=style
)
print(f"Wrote {result.path} as {result.layout_name} at {args.ratio.display}")
short = next(
    option.short_name
    for option in pipeline.arrangements(args.inputs, args.ratio, style)
    if option.name == result.layout_name
)
print(f"  --arrangement {short}")
```

Wrap the `compose_images` call so a `ValueError` from an arrangement that no
count answers to becomes `parser.error(str(error))` rather than a traceback.

- [ ] **Step 4: Run the gate**

Run: `mise run check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(cli): force an arrangement with --arrangement

Takes either spelling. The short one is documented because the long one is
a syntax error unquoted in zsh and bash, and the success line prints it
beside the arrangement's own name so what you read is what you can type.

Spelling is checked at parse time and the count in the run, because
argparse counts the inputs afterwards and cannot know how many there are."
```

---

### Task 4: The ARRANGEMENT combo

**Files:**
- Modify: `src/maskingframe/gui/compose_tab.py`
- Test: `tests/test_compose_tab.py`

**Interfaces:**
- Consumes: `pipeline.arrangements`, `pipeline.Arrangement`, and the `arrangement` parameter on `name_layout`/`compose_preview`/`compose_images` from Task 2.
- Produces: `ComposeTab.arrangement_combo`, `ComposeTab.chosen_arrangement() -> str`, `AUTOMATIC`.

Read the file before starting. `_Solve` is the off-thread answer carrying `token`, `name`, `count`, `sizes`; `_solve_job` builds it; `_apply_layout_name` lands it on the GUI thread; `_request_layout_name` starts it. The options must be computed in `_solve_job` — `pipeline.arrangements` opens files and must never run on the GUI thread.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_compose_tab.py`:

```python
def _with_sources(qtbot: QtBot, built: ComposeTab, paths: list[Path]) -> None:
    built._accept(paths)
    _settled(qtbot, built)


def test_the_arrangement_list_opens_on_automatic(qtbot: QtBot, tab: ComposeTab) -> None:
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])

    assert tab.chosen_arrangement() == ""
    assert tab.arrangement_combo.currentIndex() == 0
    assert tab.arrangement_combo.itemText(0).startswith(compose_tab.AUTOMATIC)


def test_the_list_names_the_automatic_pick_in_its_first_entry(
    qtbot: QtBot, tab: ComposeTab
) -> None:
    """Choosing nothing still has to say what you are getting."""
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])

    words = compose_tab.present_layout(tab.layout_name(), 3)

    assert words.lower() in tab.arrangement_combo.itemText(0).lower()


def test_every_arrangement_is_offered_once(qtbot: QtBot, tab: ComposeTab) -> None:
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE, SQUARE])
    offered = [tab.arrangement_combo.itemText(i) for i in range(1, tab.arrangement_combo.count())]

    assert len(offered) == len(set(offered))
    assert len(offered) == len(pipeline.arrangements([WIDE, TALL, SQUARE, SQUARE], _ratio(tab)))


def test_choosing_an_arrangement_is_remembered_and_used(qtbot: QtBot, tab: ComposeTab) -> None:
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])
    tab.arrangement_combo.setCurrentIndex(2)

    chosen = tab.chosen_arrangement()

    assert chosen
    assert chosen != ""
    assert pipeline.name_layout([WIDE, TALL, SQUARE], _ratio(tab), chosen) == chosen


def test_adding_a_source_drops_the_chosen_arrangement(qtbot: QtBot, tab: ComposeTab) -> None:
    """An arrangement names a shape for exactly N panels. With a different
    N it means nothing, so it goes back to automatic rather than being
    quietly ignored."""
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])
    tab.arrangement_combo.setCurrentIndex(2)
    assert tab.chosen_arrangement()

    _with_sources(qtbot, tab, [SQUARE])

    assert tab.chosen_arrangement() == ""
    assert tab.arrangement_combo.currentIndex() == 0


def test_a_ratio_change_keeps_the_chosen_arrangement(qtbot: QtBot, tab: ComposeTab) -> None:
    """The arrangement is still valid, and dropping a deliberate choice for
    a reason the user did not ask about is what makes a control feel
    unreliable."""
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])
    tab.arrangement_combo.setCurrentIndex(2)
    chosen = tab.chosen_arrangement()

    tab.ratio_combo.setCurrentText(pipeline.RATIOS["1.91:1"].display)
    _settled(qtbot, tab)

    assert tab.chosen_arrangement() == chosen


def test_a_border_change_keeps_the_chosen_arrangement(qtbot: QtBot, tab: ComposeTab) -> None:
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])
    tab.arrangement_combo.setCurrentIndex(2)
    chosen = tab.chosen_arrangement()

    wider = pipeline.FrameStyle(border_percent=20.0)
    tab.border_controls.set_style(wider)
    tab._on_style_settled(wider)
    _settled(qtbot, tab)

    assert tab.chosen_arrangement() == chosen


def test_reordering_keeps_the_chosen_arrangement(qtbot: QtBot, tab: ComposeTab) -> None:
    _with_sources(qtbot, tab, [WIDE, TALL, SQUARE])
    tab.arrangement_combo.setCurrentIndex(2)
    chosen = tab.chosen_arrangement()

    tab.listbox.select(0)
    tab.move_down()
    _settled(qtbot, tab)

    assert tab.chosen_arrangement() == chosen
```

Add a `_ratio` helper near the top of the file if one does not exist:

```python
def _ratio(built: ComposeTab) -> pipeline.AspectRatio:
    return pipeline.RATIOS[built._ratio_name()]
```

`move_down`, `move_up`, `layout_name()`, `_ratio_name()`, `_style()` and the
test helper `_settled` are all real names, verified against the file.
`_on_style_settled` takes the style as an argument.

- [ ] **Step 2: Run them and watch them fail**

Run: `mise run test -- tests/test_compose_tab.py -k arrangement -q`
Expected: FAIL — `ComposeTab` has no `arrangement_combo`.

- [ ] **Step 3: Build the section**

Add the constant near `EMPTY_STATE`:

```python
AUTOMATIC = "Automatic"
"""The first entry, and the empty choice. Named rather than blank, because
a list whose first row is empty reads as a missing value rather than as a
decision the application has already made for you."""
```

Extend `_Solve` with the options, and fill them in `_solve_job` — it already
runs off the GUI thread and already has the sources, the ratio and the style:

```python
options: tuple[pipeline.Arrangement, ...] = ()
```

Build the section in `_build`, immediately after the `layout_label` and
before the `theme.L` spacing that precedes BORDER:

```python
rail.addSpacing(theme.L)
rail.addWidget(shell.section("Arrangement"))
rail.addSpacing(theme.S)
self.arrangement_combo = shell.Combo()
self.arrangement_combo.setAccessibleName("Arrangement")
self.arrangement_combo.currentIndexChanged.connect(self._on_arrangement_change)
rail.addWidget(self.arrangement_combo)
```

Hold the choice as a name, never an index:

```python
# The name, not the row: the ranking moves with the ratio and the border,
# and an index would quietly come to mean a different arrangement.
self._arrangement = ""
```

Fill the list in `_apply_layout_name`, where the options now arrive, and add:

```python
def chosen_arrangement(self) -> str:
    """The arrangement to compose with, or empty for the solver's own."""
    return self._arrangement

def _fill_arrangements(self, solved: _Solve) -> None:
    """Rebuild the list, keeping the choice if it still exists.

    Rebuilding fires `currentIndexChanged`, so the guard is a flag rather
    than a disconnect: a disconnect that raised in between would leave the
    combo permanently deaf.
    """
    self._filling = True
    try:
        self.arrangement_combo.clear()
        automatic = present_layout(solved.name, solved.count)
        self.arrangement_combo.addItem(f"{AUTOMATIC} — {automatic}" if automatic else AUTOMATIC)
        for option in solved.options:
            words = present_layout(option.name, solved.count)
            self.arrangement_combo.addItem(f"{words} · {option.fill:.0%}", option.name)
        names = [option.name for option in solved.options]
        if self._arrangement in names:
            self.arrangement_combo.setCurrentIndex(names.index(self._arrangement) + 1)
        else:
            # The count changed out from under it, so the shape it named no
            # longer exists. Back to automatic rather than silently ignored.
            self._arrangement = ""
            self.arrangement_combo.setCurrentIndex(0)
    finally:
        self._filling = False

def _on_arrangement_change(self, index: int) -> None:
    if self._filling:
        return
    self._arrangement = str(self.arrangement_combo.itemData(index) or "")
    self._request_layout_name()
    self._refresh_border_preview()
```

Initialise `self._filling = False` in `__init__` beside `self._arrangement`.

Pass the choice everywhere a composite is solved or rendered: `_solve_job`'s
`name_layout` call, the preview job's `compose_preview` call, and the save
job's `compose_images` call. Each takes it as the argument before `style`,
and `style` is spelled `style=style`.

- [ ] **Step 4: Run the gate**

Run: `mise run check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(gui): choose the compose arrangement instead of accepting it

An ARRANGEMENT combo above BORDER, listing every arrangement best first as
English with its fill. The first row is Automatic and names what the solver
picked, so choosing nothing still says what you are getting.

The choice is held as a name rather than a row, because the ranking moves
with the ratio and the border and an index would come to mean a different
arrangement. It survives a ratio, border, gutter or reorder change and is
dropped only when the number of sources changes, where the shape it names
stops existing."
```

---

### Task 5: Record it

**Files:**
- Modify: `CLAUDE.md`, `README.md`
- Test: none — documentation only.

- [ ] **Step 1: Update the notes**

In `CLAUDE.md`:

1. In the `layout.py` bullet, add that `rank()` returns every placeable arrangement best first and `solve()` is its head, with the tie rule now expressed as one sort key using `TIE_DECIMALS`.
2. Add that arrangements carry two spellings — `R(C(1,2,3,4),C(5,6))` and `R4.2` — that `short_name` and `parse_name` own them, that `parse_name` matches against the generated list rather than parsing so a second definition cannot drift, and why the short form exists (the long one is a shell syntax error unquoted).
3. In the `pipeline.py` bullet, record the `arrangement` parameter on `name_layout`, `compose_preview` and `compose_images` — empty meaning automatic, a bad name an error rather than a fallback — and `arrangements()`.
4. In the `gui/` notes, record that the Compose tab holds the choice as a name rather than an index and why, and the drop rule: only a change in the number of sources.
5. Add a behaviour-changes entry: the composite arrangement can now be forced, from the tab or with `--arrangement`.

In `README.md`, under the Composites section, add a short paragraph and an example showing `--arrangement R2.2` and that the tool prints the flag to type back.

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "docs: record forcing a compose arrangement"
```

---

## Verification

- [ ] `mise run check` passes.
- [ ] The existing tie tests pass unchanged, proving `rank` did not move the automatic winner.
- [ ] Every arrangement round-trips through both spellings at every count from two to six.
- [ ] `maskingframe compose a b c d -o out --arrangement R2.2` writes that arrangement, and prints `--arrangement R2.2` back.
- [ ] The same composite results from the short and the long spelling, byte for byte.
- [ ] A misspelt arrangement fails at parse time; a well-spelt one with the wrong number of sources fails naming both.
- [ ] In the Compose tab, the list opens on Automatic naming the solver's pick; choosing an entry changes the preview; adding a source returns it to Automatic; a ratio, border or reorder change does not.
- [ ] No production file under `gui/` or `cli.py` imports `layout`.
