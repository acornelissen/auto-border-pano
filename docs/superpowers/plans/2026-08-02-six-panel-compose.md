# Composing up to six panels — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise the compose ceiling from three panels to six, replacing the hand-written arrangement list with a generative one-level solver.

**Architecture:** `layout.candidates` becomes generative: a root Row or Column whose parts are consecutive blocks of the images in input order, each block a leaf or a group of the opposite orientation. Names are generated from the tree as `R(1,C(2,3))` notation. `solve` ranks by score, then depth, then name. Everything above `layout` follows: suffixes, CLI copy, GUI limits, and the rail's English.

**Tech Stack:** Python 3.13, PySide6, Pillow, pytest, mypy --strict, ruff.

**Spec:** `docs/superpowers/specs/2026-08-02-six-panel-compose-design.md`

## Global Constraints

- Dependency direction is one-way: `geometry` and `layout` are leaves; `compose` uses both; `pipeline` uses all three; `cli` and `gui/` use only `pipeline`. **`gui/` and `cli.py` must never import `layout` directly** — `pipeline` re-exports what they need.
- Half-up rounding is `math.floor(v + 0.5)`. Never Python's `round()`.
- `mise run check` (ruff lint, ruff format check, mypy --strict, pytest) must pass before every commit.
- Input order is never permuted: image *i* always lands in panel *i*.
- Nothing is ever cropped: a box always carries its image's own aspect ratio.
- Commits are conventional (`<type>(<scope>): <subject>`, imperative). **No Claude attribution trailers and no emoji** anywhere in commit messages — a hook rejects them.
- Work straight on `master`. No feature branches, no PRs.
- Any test touching `QSettings` must use the `isolated_settings` fixture.
- `MIN_PANELS = 2`, `MAX_PANELS = 6`, tie tolerance `1e-9`.
- Candidate counts are exactly 2, 6, 14, 30, 62 for two through six panels.

---

### Task 1: Generative candidates and notation names

**Files:**
- Modify: `src/maskingframe/layout.py:68-87` (replace `candidates`)
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `Leaf`, `Row`, `Column`, `Node` (already in `layout.py`, unchanged).
- Produces: `MIN_PANELS`, `MAX_PANELS`, `candidates(count) -> Iterator[tuple[str, Node]]`, `name_of(node) -> str`, `node_depth(node) -> int`. Task 2 uses `node_depth` and `candidates`; Task 3 re-exports `MIN_PANELS`/`MAX_PANELS` through `pipeline`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_layout.py`:

```python
def test_candidate_counts_are_the_one_level_arrangements() -> None:
    """Compositions of n into two or more consecutive blocks, times two
    orientations: 2^(n-1) - 1 doubled. Worked by hand rather than read off
    the implementation, so a change in the recursion fails here."""
    counts = {n: len(list(layout.candidates(n))) for n in range(2, 7)}
    assert counts == {2: 2, 3: 6, 4: 14, 5: 30, 6: 62}


def test_every_candidate_name_is_unique() -> None:
    for count in range(2, 7):
        names = [name for name, _ in layout.candidates(count)]
        assert len(set(names)) == len(names)


def test_the_three_panel_set_is_what_the_hand_written_list_gave() -> None:
    """The old list, renamed. Nothing at the current ceiling may move."""
    assert {name for name, _ in layout.candidates(3)} == {
        "R(1,2,3)",
        "C(1,2,3)",
        "R(1,C(2,3))",
        "R(C(1,2),3)",
        "C(1,R(2,3))",
        "C(R(1,2),3)",
    }


def test_the_two_panel_set_is_the_pair() -> None:
    assert {name for name, _ in layout.candidates(2)} == {"R(1,2)", "C(1,2)"}


def test_a_six_panel_grid_is_offered() -> None:
    names = {name for name, _ in layout.candidates(6)}
    assert "C(R(1,2,3),R(4,5,6))" in names
    assert "R(C(1,2),C(3,4),C(5,6))" in names
    assert "R(1,2,3,4,5,6)" in names


def _leaves(node: layout.Node) -> list[int]:
    if isinstance(node, layout.Leaf):
        return [node.index]
    return [index for child in node.children for index in _leaves(child)]


def test_every_candidate_uses_each_image_once_in_order() -> None:
    for count in range(2, 7):
        for name, node in layout.candidates(count):
            assert _leaves(node) == list(range(count)), name


def test_no_candidate_nests_more_than_one_level() -> None:
    for count in range(2, 7):
        for name, node in layout.candidates(count):
            assert layout.node_depth(node) <= 2, name


def test_a_group_never_repeats_its_parent_orientation() -> None:
    """R(R(1,2),3) and R(1,2,3) are the same picture. The alternation is
    what stops both being generated, so it is asserted directly."""
    for count in range(2, 7):
        for name, node in layout.candidates(count):
            assert not isinstance(node, layout.Leaf)
            for child in node.children:
                assert not isinstance(child, type(node)), name


@pytest.mark.parametrize("count", [0, 1, 7, 12])
def test_a_count_outside_the_range_is_refused_by_number(count: int) -> None:
    with pytest.raises(ValueError, match=f"got {count}"):
        list(layout.candidates(count))


def test_a_name_reads_the_tree_with_images_numbered_from_one() -> None:
    node = layout.Row((layout.Leaf(0), layout.Column((layout.Leaf(1), layout.Leaf(2)))))
    assert layout.name_of(node) == "R(1,C(2,3))"
    assert layout.name_of(layout.Leaf(3)) == "4"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `mise run test -- tests/test_layout.py -x -q`
Expected: FAIL — `layout` has no attribute `node_depth`, and `candidates(4)` raises.

- [ ] **Step 3: Replace `candidates`**

In `src/maskingframe/layout.py`, delete the existing `candidates` function (lines 68-87) and put this in its place:

```python
MIN_PANELS = 2
MAX_PANELS = 6


def name_of(node: Node) -> str:
    """This arrangement's canonical name, images numbered from one.

    `R(1,C(2,3))` is image 1 beside images 2 and 3 stacked. The numbering
    matches the numerals the sources list draws, so a name read off the
    interface points at the panels it names. Generated rather than written
    down: at six panels there are 62 of these.
    """
    if isinstance(node, Leaf):
        return str(node.index + 1)
    letter = "R" if isinstance(node, Row) else "C"
    return f"{letter}({','.join(name_of(child) for child in node.children)})"


def node_depth(node: Node) -> int:
    """How many levels of grouping this arrangement has. A leaf is 0."""
    if isinstance(node, Leaf):
        return 0
    return 1 + max(node_depth(child) for child in node.children)


def _blocks(count: int) -> Iterator[tuple[int, ...]]:
    """Every way to cut `count` ordered images into two or more blocks.

    These are the compositions of `count`, less the single-block one:
    2^(count-1) - 1 of them.
    """

    def walk(remaining: int, taken: tuple[int, ...]) -> Iterator[tuple[int, ...]]:
        if remaining == 0:
            if len(taken) >= 2:
                yield taken
            return
        for size in range(1, remaining + 1):
            yield from walk(remaining - size, (*taken, size))

    yield from walk(count, ())


def candidates(count: int) -> Iterator[tuple[str, Node]]:
    """Every arrangement considered, generated rather than listed.

    An arrangement is one root -- a row or a column -- whose parts are
    consecutive blocks of the images in input order. A block of one image is
    a leaf; a block of more is a group of the *opposite* orientation holding
    only leaves. There is no third level.

    The alternation is what makes the set canonical: without it `R(R(1,2),3)`
    and `R(1,2,3)` would both be generated for the same picture.

    One level is a restriction, not a consequence. Deeper trees exist -- 394
    of them at six panels rather than 62 -- and they fill the frame better,
    by up to 13 points. They are left out because the arrangements they win
    with, `C(R(C(R(1,C(2,3)),4),5),6)` and its like, are not ones anybody
    would lay out. The two- and three-panel sets are unaffected: every
    arrangement the old hand-written list held has one level of grouping.
    """
    if not MIN_PANELS <= count <= MAX_PANELS:
        raise ValueError(f"expected {MIN_PANELS} to {MAX_PANELS} images, got {count}")
    for root, inner in ((Row, Column), (Column, Row)):
        for sizes in _blocks(count):
            parts: list[Node] = []
            start = 0
            for size in sizes:
                leaves = tuple(Leaf(index) for index in range(start, start + size))
                parts.append(leaves[0] if size == 1 else inner(leaves))
                start += size
            node = root(tuple(parts))
            yield name_of(node), node
```

- [ ] **Step 4: Run the tests**

Run: `mise run test -- tests/test_layout.py -q`
Expected: the new tests PASS. Existing tests that assert old names (`"row"`, `"row-one-then-two"`) FAIL — that is expected and Step 5 fixes them.

- [ ] **Step 5: Rename in the existing layout tests**

Update every assertion in `tests/test_layout.py` that names an arrangement, using this mapping and nothing else:

| Old | New |
|---|---|
| `row` | `R(1,2)` at two panels, `R(1,2,3)` at three |
| `column` | `C(1,2)` at two panels, `C(1,2,3)` at three |
| `row-one-then-two` | `R(1,C(2,3))` |
| `row-two-then-one` | `R(C(1,2),3)` |
| `column-one-then-two` | `C(1,R(2,3))` |
| `column-two-then-one` | `C(R(1,2),3)` |

Do not change what any test asserts beyond the name string.

- [ ] **Step 6: Run the whole gate**

Run: `mise run check`
Expected: PASS, except for failures in `tests/test_compose.py`, `tests/test_pipeline.py`, `tests/test_cli.py` or `tests/test_compose_tab.py` that assert old arrangement names. Apply the same mapping to those and re-run. Do not change any other behaviour in those files — the later tasks own them.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(layout): generate arrangements instead of listing them

candidates was hand-written for two and three panels and raised for
anything else. It now generates every one-level arrangement -- a root row
or column whose parts are consecutive blocks of the images in order --
which is 2, 6, 14, 30 and 62 candidates for two through six panels.

Names come from the tree as R(1,C(2,3)) notation, numbered from one to
match the sources list. That renames the six three-panel arrangements;
the set itself is unchanged."
```

---

### Task 2: Rank by score, then depth, then name

**Files:**
- Modify: `src/maskingframe/layout.py` (`solve`, currently lines 233-256)
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `candidates`, `node_depth`, `evaluate` from Task 1.
- Produces: `TIE_TOLERANCE = 1e-9`. `solve`'s signature and return type are unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_layout.py`:

```python
def test_a_tie_is_won_by_the_flatter_arrangement() -> None:
    """Six frames from one camera share an aspect, so many arrangements
    fill the frame identically. Between them the flat one is the one a
    person would have laid out."""
    solved = layout.solve([1.0] * 6, geometry.RATIOS["1:1"])
    tied = _names_within(1e-9, [1.0] * 6, geometry.RATIOS["1:1"])
    assert len(tied) > 1, "no tie to break -- the test proves nothing"
    assert layout.node_depth(_node_named(solved.name, 6)) == min(
        layout.node_depth(_node_named(name, 6)) for name in tied
    )


def test_a_tie_at_equal_depth_is_won_by_the_first_name() -> None:
    aspects = [1.0] * 4
    ratio = geometry.RATIOS["1:1"]
    solved = layout.solve(aspects, ratio)
    shallowest = min(
        layout.node_depth(_node_named(name, 4)) for name in _names_within(1e-9, aspects, ratio)
    )
    rivals = sorted(
        name
        for name in _names_within(1e-9, aspects, ratio)
        if layout.node_depth(_node_named(name, 4)) == shallowest
    )
    assert solved.name == rivals[0]


def test_a_clear_win_on_score_beats_a_shallower_arrangement() -> None:
    """Depth only ever breaks a tie. A flat row of six 3:2 frames at 4:5
    fills 5% of the frame; it must not win over a grid filling 88%."""
    solved = layout.solve([1.5] * 6, geometry.RATIOS["4:5"])
    assert solved.name != "R(1,2,3,4,5,6)"
    assert solved.score > 0.5
```

And these helpers, near the top of the file:

```python
def _node_named(name: str, count: int) -> layout.Node:
    for candidate_name, node in layout.candidates(count):
        if candidate_name == name:
            return node
    raise AssertionError(f"no candidate named {name}")


def _names_within(
    tolerance: float, aspects: list[float], ratio: geometry.AspectRatio
) -> list[str]:
    """Every candidate scoring within `tolerance` of the best."""
    scored = {}
    for name, node in layout.candidates(len(aspects)):
        solved = layout.evaluate(node, name, aspects, ratio, geometry.DEFAULT_STYLE)
        if solved is not None:
            scored[name] = solved.score
    best = max(scored.values())
    return [name for name, score in scored.items() if best - score <= tolerance]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `mise run test -- tests/test_layout.py -k tie -q`
Expected: FAIL — the first-generated candidate wins ties today, which is not the flattest.

- [ ] **Step 3: Rewrite `solve`**

Replace the body of `solve` in `src/maskingframe/layout.py`, keeping its signature and docstring opening line. The constant goes just above it:

```python
# Two fill scores are the same score when they are this close. Exact float
# equality would let a rounding artefact one part in 10^16 decide which
# arrangement wins, which is precisely what the depth preference below
# exists to stop.
TIE_TOLERANCE = 1e-9


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
    """
    for index, aspect in enumerate(aspects):
        if not math.isfinite(aspect) or aspect <= 0:
            raise ValueError(f"aspect at index {index} must be finite and positive, got {aspect!r}")

    ranked: list[tuple[int, str, Layout]] = []
    best_score: float | None = None
    for name, node in candidates(len(aspects)):
        solved = evaluate(node, name, aspects, ratio, style)
        if solved is None:
            continue
        ranked.append((node_depth(node), name, solved))
        if best_score is None or solved.score > best_score:
            best_score = solved.score
    if best_score is None:
        raise ValueError(f"no usable layout for aspects {list(aspects)} at {ratio.name}")

    tied = [entry for entry in ranked if best_score - entry[2].score <= TIE_TOLERANCE]
    tied.sort(key=lambda entry: (entry[0], entry[1]))
    return tied[0][2]
```

- [ ] **Step 4: Run the tests**

Run: `mise run check`
Expected: PASS. If a compose or pipeline test now expects a different winning arrangement, check by hand that the new winner is genuinely tied-or-better before updating it; a changed winner that scores *worse* is a bug in this task, not a test to update.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(layout): break a tie on depth rather than generation order

Frames from one camera share an aspect ratio, so whole families of
arrangements fill the frame identically. The first one generated used to
win, which made the winner an artefact of the recursion.

solve now takes every candidate within 1e-9 of the best score and prefers
the shallower tree, then the earlier name. Both are properties of the
arrangement, so generation order no longer decides anything."
```

---

### Task 3: The count contract and the Greek

**Files:**
- Modify: `src/maskingframe/pipeline.py:33` area (re-exports), `:341` (`COMPOSITE_SUFFIXES`), `:407` and `:531` (count checks)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `layout.MIN_PANELS`, `layout.MAX_PANELS` from Task 1.
- Produces: `pipeline.MIN_IMAGES`, `pipeline.MAX_IMAGES`, and a five-entry `COMPOSITE_SUFFIXES`. Tasks 4, 5 and 6 read these and must not import `layout`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
def test_every_composable_count_has_a_filename() -> None:
    """A count the solver accepts but that has no suffix would raise at the
    moment of writing, after all the work is done."""
    assert set(pipeline.COMPOSITE_SUFFIXES) == set(
        range(pipeline.MIN_IMAGES, pipeline.MAX_IMAGES + 1)
    )


def test_the_suffixes_carry_the_greek_on() -> None:
    assert pipeline.COMPOSITE_SUFFIXES == {
        2: "_diptych.jpg",
        3: "_triptych.jpg",
        4: "_tetraptych.jpg",
        5: "_pentaptych.jpg",
        6: "_hexaptych.jpg",
    }


def test_the_bounds_come_from_the_solver() -> None:
    """cli and gui read these rather than importing layout, so they have to
    be the solver's own numbers and not a second copy of them."""
    assert (pipeline.MIN_IMAGES, pipeline.MAX_IMAGES) == (2, 6)


def test_six_sources_compose_into_a_hexaptych(tmp_path: Path) -> None:
    sources = []
    for index, (width, height) in enumerate(
        [(600, 400), (400, 600), (500, 500), (600, 400), (400, 600), (900, 400)]
    ):
        path = tmp_path / f"s{index}.jpg"
        synthetic_panorama(width, height).save(path, "JPEG", quality=95)
        sources.append(path)

    result = pipeline.compose_images(sources, tmp_path / "out", pipeline.DEFAULT_RATIO)

    assert result.path.name == "out_hexaptych.jpg"
    assert result.path.exists()
    assert result.layout_name.startswith(("R(", "C("))
```

- [ ] **Step 2: Run them and watch them fail**

Run: `mise run test -- tests/test_pipeline.py -k "hexaptych or greek or composable or bounds" -q`
Expected: FAIL — `pipeline` has no `MIN_IMAGES`, and six paths are refused.

- [ ] **Step 3: Add the bounds and the suffixes**

In `src/maskingframe/pipeline.py`, beside the existing `MAX_PERCENT = geometry.MAX_PERCENT` re-export, add:

```python
# Re-exported for the same reason as the ratio and style names: `cli.py` and
# `gui/` must be able to state how many sources compose without importing
# `layout` directly, which the dependency direction forbids.
MIN_IMAGES = layout.MIN_PANELS
MAX_IMAGES = layout.MAX_PANELS
```

Replace `COMPOSITE_SUFFIXES` with:

```python
# One entry per composable count. `test_every_composable_count_has_a_filename`
# holds this to exactly MIN_IMAGES..MAX_IMAGES, so raising the ceiling cannot
# leave a count with nowhere to write to.
COMPOSITE_SUFFIXES = {
    2: "_diptych.jpg",
    3: "_triptych.jpg",
    4: "_tetraptych.jpg",
    5: "_pentaptych.jpg",
    6: "_hexaptych.jpg",
}
```

Leave the two `if len(paths) not in COMPOSITE_SUFFIXES:` checks as they are — they now cover two through six. Update the message each raises so it names the range and the count given; if a message currently says "two or three", make it read:

```python
raise ValueError(
    f"expected {MIN_IMAGES} to {MAX_IMAGES} images, got {len(paths)}"
)
```

- [ ] **Step 4: Run the gate**

Run: `mise run check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(pipeline): compose four, five and six panels

COMPOSITE_SUFFIXES gains tetraptych, pentaptych and hexaptych, carrying on
the Greek diptych and triptych started, and a test holds the table to
exactly the counts the solver accepts.

MIN_IMAGES and MAX_IMAGES are re-exported from layout so cli and gui can
state the range without importing layout directly."
```

---

### Task 4: The CLI says two to six

**Files:**
- Modify: `src/maskingframe/cli.py:155` (compose help), `:196` (`-o` help), and the compose count check
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `pipeline.MIN_IMAGES`, `pipeline.MAX_IMAGES`, `pipeline.COMPOSITE_SUFFIXES` from Task 3.
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def test_compose_help_names_the_range() -> None:
    parser = cli.build_compose_parser()
    assert "two to six" in parser.format_help()


def test_too_many_sources_are_refused_by_number(tmp_path: Path, capsys: Any) -> None:
    paths = []
    for index in range(7):
        path = tmp_path / f"s{index}.jpg"
        synthetic_panorama(400, 300).save(path, "JPEG", quality=95)
        paths.append(str(path))

    with pytest.raises(SystemExit):
        cli.main(["compose", *paths, "-o", str(tmp_path / "out")])

    message = capsys.readouterr().err
    assert "got 7" in message
    assert "2 to 6" in message


def test_six_sources_are_accepted(tmp_path: Path) -> None:
    paths = []
    for index in range(6):
        path = tmp_path / f"s{index}.jpg"
        synthetic_panorama(400, 300).save(path, "JPEG", quality=95)
        paths.append(str(path))

    cli.main(["compose", *paths, "-o", str(tmp_path / "out")])

    assert (tmp_path / "out_hexaptych.jpg").exists()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `mise run test -- tests/test_cli.py -k "compose_help or too_many or six_sources" -q`
Expected: FAIL — the help still says "two or three" and six sources are refused.

- [ ] **Step 3: Update the copy and the check**

In `src/maskingframe/cli.py`, change the compose parser's description from
`"join two or three images into a single diptych or triptych."` to:

```python
"join two to six images into a single composite."
```

Change the `-o` help to name the suffixes it can write:

```python
help=(
    "output prefix; one of the suffixes "
    + ", ".join(pipeline.COMPOSITE_SUFFIXES[count] for count in sorted(pipeline.COMPOSITE_SUFFIXES))
    + " is added"
),
```

The positional is `inputs`, not `sources`. Line 190's `help="two or three images"`
becomes `help="two to six images"`, line 185's description becomes "Compose two to
six images into a single frame at the target ", and the check at line 212 becomes:

```python
if not pipeline.MIN_IMAGES <= len(args.inputs) <= pipeline.MAX_IMAGES:
    parser.error(
        f"expected {pipeline.MIN_IMAGES} to {pipeline.MAX_IMAGES} images, "
        f"got {len(args.inputs)}"
    )
```

There are three places saying "two or three" in this file (lines 155, 185, 190).
All three change.

- [ ] **Step 4: Run the gate**

Run: `mise run check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(cli): accept two to six sources for a composite

The help states the range, the -o help lists every suffix it can write,
and the count error names how many were given alongside what was expected."
```

---

### Task 5: The rail reads the notation

**Files:**
- Modify: `src/maskingframe/gui/compose_tab.py:57-127` (`_composite_noun`, `_NUMBER_WORDS`, `present_layout`)
- Test: `tests/test_compose_tab.py`

**Interfaces:**
- Consumes: `pipeline.COMPOSITE_SUFFIXES`, `pipeline.MIN_IMAGES`, `pipeline.MAX_IMAGES` from Task 3; arrangement names from Task 1.
- Produces: `present_layout(name, count) -> str` with an unchanged signature. Task 6 leaves it alone.

Keep `_AXIS`, `_TWO_UP_PHRASING` and `_split_arrangement` exactly as they are — the parser in front of them changes, they do not.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_compose_tab.py`:

```python
@pytest.mark.parametrize(
    ("name", "count", "expected"),
    [
        # Rule 1: a pair is not "a row of two".
        ("R(1,2)", 2, "Side by side"),
        ("C(1,2)", 2, "One above the other"),
        # Rule 2: no grouping.
        ("R(1,2,3)", 3, "Row of three"),
        ("C(1,2,3,4,5,6)", 6, "Column of six"),
        # Rule 3: even grouping.
        ("C(R(1,2,3),R(4,5,6))", 6, "Two rows of three"),
        ("R(C(1,2),C(3,4),C(5,6))", 6, "Three columns of two"),
        # Rule 4: two uneven parts keep today's positional wording.
        ("R(1,C(2,3))", 3, "One left, two stacked right"),
        ("R(C(1,2),3)", 3, "Two stacked left, one right"),
        ("C(1,R(2,3))", 3, "One on top, two side by side below"),
        ("C(R(1,2),3)", 3, "Two side by side on top, one below"),
        # Rule 5: three or more uneven parts are listed in order.
        ("C(1,R(2,3),R(4,5,6))", 6, "Column of three: one, two side by side, three side by side"),
        ("R(1,C(2,3),4)", 4, "Row of three: one, two stacked, one"),
    ],
)
def test_present_layout_reads_a_notation_name(name: str, count: int, expected: str) -> None:
    assert compose_tab.present_layout(name, count) == expected


def test_an_unreadable_name_is_shown_rather_than_swallowed() -> None:
    assert compose_tab.present_layout("nonsense", 3) == "nonsense"
    assert compose_tab.present_layout("", 3) == ""


def test_the_save_button_names_every_composable_count() -> None:
    labels = {count: compose_tab._save_label(count) for count in range(2, 7)}
    assert labels == {
        2: "Save diptych",
        3: "Save triptych",
        4: "Save tetraptych",
        5: "Save pentaptych",
        6: "Save hexaptych",
    }
```

Update the existing test that walks the solver's candidate list so it covers every composable count:

```python
def test_present_layout_reads_the_solver_name_as_a_sentence() -> None:
    """Walks the solver's own list, so an arrangement it cannot read fails
    the suite rather than reaching the rail as a formula."""
    for count in range(pipeline.MIN_IMAGES, pipeline.MAX_IMAGES + 1):
        for name, _ in layout.candidates(count):
            words = compose_tab.present_layout(name, count)
            assert words
            assert words != name, f"{name} was not read"
            assert words[0].isupper()
```

Note: this test file may import `layout` directly — that is allowed in tests, which are not part of the dependency graph. Production code in `gui/` still must not.

- [ ] **Step 2: Run them and watch them fail**

Run: `mise run test -- tests/test_compose_tab.py -k "present_layout or save_button" -q`
Expected: FAIL — the parser reads hyphenated slugs, so `R(1,2)` falls through to the "does not parse" branch.

- [ ] **Step 3: Replace the noun table and the parser**

In `src/maskingframe/gui/compose_tab.py`, replace `MIN_IMAGES`/`MAX_IMAGES` with the re-exports and rewrite the naming:

```python
MIN_IMAGES = pipeline.MIN_IMAGES
MAX_IMAGES = pipeline.MAX_IMAGES

EMPTY_STATE = "Add two to six sources."

# What this many sources makes, read off the filename it would be written
# to. One table rather than two: a suffix and a button that disagreed about
# what a five-panel composite is called would be a bug nobody would notice
# until they went looking for the file.
_COMPOSITE_NOUNS = {
    count: suffix.removeprefix("_").removesuffix(".jpg")
    for count, suffix in pipeline.COMPOSITE_SUFFIXES.items()
}

_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}

_PLURAL_AXIS = {"row": "rows", "column": "columns"}


def _composite_noun(count: int) -> str:
    """What this many sources makes. Empty when it makes nothing yet."""
    noun = _COMPOSITE_NOUNS.get(count, "")
    return noun[:1].upper() + noun[1:]


def _save_label(count: int) -> str:
    """Name what Save will actually write, live as the list changes."""
    noun = _COMPOSITE_NOUNS.get(count)
    return f"Save {noun}" if noun else "Save composite"
```

Then replace `present_layout` (keeping `_AXIS`, `_TWO_UP_PHRASING` and `_split_arrangement` untouched above it):

```python
def _read_name(name: str) -> tuple[str, tuple[int, ...]] | None:
    """Read a solver name into its root axis and its parts' sizes.

    `R(1,C(2,3))` reads as `("row", (1, 2))`. Only the shape is wanted, not
    which image sits where, because that is all the copy below says.

    Returns None for anything that is not a name this solver produces, so an
    arrangement from a future solver reaches the rail as itself rather than
    as a wrong sentence.
    """
    axis = {"R": "row", "C": "column"}.get(name[:1])
    if axis is None or not name.startswith(f"{name[:1]}(") or not name.endswith(")"):
        return None
    sizes: list[int] = []
    size = 0
    depth = 0
    in_number = False
    for char in name[2:-1]:
        if char == "(":
            depth += 1
            in_number = False
        elif char == ")":
            depth -= 1
            in_number = False
        elif char == "," and depth == 0:
            sizes.append(size)
            size = 0
            in_number = False
        elif char.isdigit():
            # Count numbers, not digits: a two-digit image number is one
            # image. Unreachable at six panels, and cheaper than the bug.
            if not in_number:
                size += 1
            in_number = True
        elif char == ",":
            in_number = False
        else:
            return None
    sizes.append(size)
    if depth != 0 or len(sizes) < 2 or any(size < 1 for size in sizes):
        return None
    return axis, tuple(sizes)


def present_layout(name: str, count: int) -> str:
    """Turn the solver's own name for an arrangement into human copy.

    The solver names an arrangement exactly, in notation the CLI prints and
    a future override will accept; the rail says the same thing in English.
    Derived from the name's shape rather than looked up, so a new
    arrangement cannot arrive unnamed -- the only thing that changes with
    six panels rather than three is how many shapes there are to describe.

    `test_present_layout_reads_the_solver_name_as_a_sentence` walks the
    solver's whole candidate list, so an arrangement this cannot read fails
    the suite.
    """
    if not name:
        return ""
    read = _read_name(name)
    if read is None:
        return name
    axis, sizes = read
    positions, pairing = _AXIS[axis]

    if all(size == 1 for size in sizes):
        # A pair is not "a row of two" -- it is side by side, or one above
        # the other. Only two panels get that, and only because a diptych
        # has an everyday name for its arrangement that nothing above it has.
        if count == MIN_IMAGES and axis in _TWO_UP_PHRASING:
            words = _TWO_UP_PHRASING[axis]
        else:
            words = f"{axis} of {_NUMBER_WORDS.get(len(sizes), str(len(sizes)))}"
    elif len(set(sizes)) == 1:
        inner = _PLURAL_AXIS["column" if axis == "row" else "row"]
        words = f"{_NUMBER_WORDS[len(sizes)]} {inner} of {_NUMBER_WORDS[sizes[0]]}"
    elif len(sizes) == 2:
        # Two parts have two sides, so the existing positional phrasing
        # applies and the three-panel copy is preserved exactly.
        words = _split_arrangement(axis, [_NUMBER_WORDS[size] for size in sizes])
    else:
        # Three or more parts and positional words run out. List them in
        # order instead, which is the order the images are in.
        listed = ", ".join(
            _NUMBER_WORDS[size] if size == 1 else f"{_NUMBER_WORDS[size]} {pairing}"
            for size in sizes
        )
        words = f"{axis} of {_NUMBER_WORDS[len(sizes)]}: {listed}"
    return words[0].upper() + words[1:]
```

- [ ] **Step 4: Run the tests**

Run: `mise run test -- tests/test_compose_tab.py -q`
Expected: PASS. If a rule-4 string differs from the parametrised expectation, the expectation is right and `_split_arrangement` must not be edited to suit it — check the axis words instead.

- [ ] **Step 5: Run the gate**

Run: `mise run check`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(gui): read the notation names into English for the rail

present_layout parsed hyphenated slugs, which the solver no longer
produces. It now reads a name into its root axis and its parts' sizes and
describes that: a pair keeps its everyday phrasing, an even grouping reads
as two rows of three, two uneven parts keep the positional wording the
three-panel copy already used, and three or more are listed in order.

The composite noun and the Save label both come from the suffix table, so
a filename and a button cannot disagree about what a composite is called."
```

---

### Task 6: The tab and the list take six

**Files:**
- Modify: `src/maskingframe/gui/compose_tab.py` (the Add-button guard and any remaining `== MAX_IMAGES` special case), `src/maskingframe/gui/sources.py:70` (`EMPTY_CAPTION`) and its own limit
- Test: `tests/test_compose_tab.py`, `tests/test_sources.py`

**Interfaces:**
- Consumes: `MIN_IMAGES`/`MAX_IMAGES` from Task 5's edit to `compose_tab`.
- Produces: nothing further depends on this.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_compose_tab.py`:

Replace the existing `test_add_stops_at_three_sources` (line 65) with:

```python
def test_add_stops_at_six_sources(tab: ComposeTab) -> None:
    tab._accept([WIDE, TALL, SQUARE, WIDE, TALL])
    assert tab.add_btn.isEnabled()

    tab._accept([SQUARE])

    assert not tab.add_btn.isEnabled()
    assert tab.can_compose()
```

and add:

```python
def test_a_seventh_source_is_left_out_and_said_so(tab: ComposeTab) -> None:
    tab._accept([WIDE, TALL, SQUARE, WIDE, TALL, SQUARE, WIDE])

    assert len(tab.images) == 6
    assert "at most 6" in tab.status.text()
```

Match `tab.status` to whatever the hint label is actually called — the
existing `test_the_reason_save_is_off_is_stated_in_the_status_line` shows it.
`_accept`, `add_btn`, `images` and `can_compose` are the real names.

Add to `tests/test_sources.py`:

```python
def test_the_empty_caption_names_the_range() -> None:
    assert "six" in sources.EMPTY_CAPTION
```

- [ ] **Step 2: Run them and watch them fail**

Run: `mise run test -- tests/test_compose_tab.py tests/test_sources.py -q`
Expected: FAIL — Add disables at three.

- [ ] **Step 3: Make the changes**

In `src/maskingframe/gui/compose_tab.py`, find any remaining place that treats `MAX_IMAGES` as "three" in copy or logic other than the guards already generalised, and make it read off the constant. `self.add_btn.setEnabled(count < MAX_IMAGES)` and `MIN_IMAGES <= len(self.images) <= MAX_IMAGES` already generalise and need no edit.

In `src/maskingframe/gui/sources.py`, change `EMPTY_CAPTION` to:

```python
EMPTY_CAPTION = "Add two to six sources."
```

and raise any hard-coded limit in that module to `pipeline.MAX_IMAGES`.

- [ ] **Step 4: Run the gate**

Run: `mise run check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(gui): let the Compose tab hold six sources

The Add button now stops at six rather than three, and the empty state in
both the tab and the sources list names the range it accepts."
```

---

### Task 7: Record it

**Files:**
- Modify: `CLAUDE.md`
- Test: none — documentation only.

**Interfaces:** none.

- [ ] **Step 1: Update the architecture notes**

In `CLAUDE.md`, make these edits:

1. In the Project Overview, change "compose two or three images" to "compose two to six images".
2. In the `layout.py` bullet, replace the sentence beginning "For two images it tries a row and a column; for three it tries..." with a description of the generative rule: one root row or column whose parts are consecutive blocks in input order, each block a leaf or a group of the opposite orientation; 2, 6, 14, 30 and 62 candidates for two through six panels; names generated as `R(1,C(2,3))` notation numbered from one.
3. Add to that bullet why the set is restricted to one level: deeper trees exist and fill better by up to 13 points, but they win with arrangements like `C(R(C(R(1,C(2,3)),4),5),6)`, and the two- and three-panel sets are unaffected because every arrangement the hand-written list held already had one level.
4. Add that `solve` ranks by score, then depth, then name, with a `1e-9` tie tolerance, and why: frames from one camera share an aspect, so ties are the common case, and generation order should not decide the winner.
5. In the `pipeline.py` bullet, update the composite filename contract to name all five suffixes and note that a test holds the table to exactly `MIN_IMAGES..MAX_IMAGES`.
6. Add a line to "Behaviour changes from the pre-refactor scripts" recording that arrangement names changed from `row-one-then-two` to `R(1,C(2,3))` notation.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: record the generative solver and the six-panel ceiling"
```

---

## Verification

- [ ] `mise run check` passes.
- [ ] `layout.candidates` yields 2, 6, 14, 30 and 62 arrangements for two through six panels, every name unique, every image used once in input order.
- [ ] The three-panel arrangement set is the same six pictures it was, renamed.
- [ ] `maskingframe compose a.jpg b.jpg c.jpg d.jpg e.jpg f.jpg -o out` writes `out_hexaptych.jpg` and prints a notation name.
- [ ] Seven sources are refused with a message naming both 7 and the range.
- [ ] The Compose tab accepts six sources, its Save button reads "Save hexaptych", and the rail reads the arrangement as English rather than notation.
- [ ] No production file under `gui/` or `cli.py` imports `layout`.
