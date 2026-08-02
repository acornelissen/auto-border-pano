# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Masking Frame.** A masking frame is the darkroom device that holds printing paper under an enlarger: its blades mask the paper's edges, setting the format and leaving the white border. The name is the product, so keep the interface's vocabulary in that world — frames, formats, sources, the contact sheet.

Python tool that turns a panoramic JPG into a set of Instagram-ready images at a chosen aspect ratio (`4:5`/Portrait, `1:1`/Square, or `1.91:1`/Landscape): one bordered frame holding the whole panorama, plus a variable number of zoomed detail frames derived from the ratio and the panorama's shape (minimum two). It can also compose two or three images — any mix of orientations — into a single diptych or triptych at one of those same ratios, with the arrangement chosen automatically. Ships as a CLI and a two-tab Qt (PySide6) GUI (Split, Compose).

## Commands

Setup (installs Python and uv via mise, then syncs dependencies):

```bash
mise install
mise run setup
```

`mise run setup` also installs the pre-commit hooks (`pre-commit install --hook-type pre-commit --hook-type pre-push`), so a fresh clone gets `ruff`/`ruff-format` on commit and `mypy`/`pytest` on push per `.pre-commit-config.yaml`.

Run:

```bash
mise run gui                    # GUI
mise run split -- <input.jpg> [output_prefix] --ratio 4:5   # single file
mise run split -- <input_dir> [output_dir] --ratio 1:1      # batch, defaults output_dir to ./output
mise run split -- compose <a.jpg> <b.jpg> [c.jpg] -o <prefix>   # diptych or triptych
```

Verify:

```bash
mise run check   # ruff lint, mypy --strict, pytest — run this before committing
```

`mise run check` is the single command that must pass. It runs `lint`, `fmtcheck`, `typecheck`, and `test` (see `mise.toml` for the individual tasks).

Every hook runs the project's own tool through `scripts/run-tool`, ruff included. There is deliberately no second, separately pinned ruff: when the commit hook had one and `mise run check` had another, they drifted, and a file the hook had just formatted would be reformatted the other way by the next manual run. `fmtcheck` is in the gate for the same reason -- without it the gate passed on a tree the hook would go on to rewrite. `docs` is excluded from ruff, because newer ruff formats Python inside Markdown fences and the plan documents are a record rather than source.

## Architecture

Src-layout package at `src/maskingframe/`. Dependency direction is explicit and one-way: `geometry` and `layout` are leaves (neither imports the other, or anything else in the package); `compose` uses both `geometry` and `layout`; `pipeline` uses all three (`geometry`, `layout`, `compose`); `cli` and `gui/` use only `pipeline`, never `geometry`, `layout`, or `compose` directly.

- `geometry.py` — pure image transforms. Takes and returns `PIL.Image` objects, never touches the filesystem. Owns `AspectRatio` (the target-shape dataclass, with a `label` like "Portrait" and a `display` property like "Portrait (4:5)"), the `RATIOS` registry and `DEFAULT_RATIO`, `section_count()` (how many detail frames a panorama gets, floored at 2), `frame_width()`, `position_travel()`, `clamp_position()`, `normalise_positions()` and `default_positions()` — the position model, `make_padded_frame()`, and `make_section()` (takes a position, a ratio, and a style). It also owns the border model: `FrameStyle` (a frozen dataclass of `border_percent`, `border_colour`, `gutter_percent`, `gutter_colour` and `border_detail_frames`, with `border_px(ratio)` and `gutter_px(ratio)` to resolve a percent into output pixels), `DEFAULT_STYLE`, `MAX_PERCENT` (40.0) and `parse_colour()`. There is one colour parser, so a colour is normalised to lowercase `#rrggbb` at the boundary and can never reach PIL malformed. The style is always a parameter with a default, never module state, so a preview and the run it previews cannot disagree about the border. `RATIOS` is insertion-ordered Portrait, Square, Landscape (narrowest to widest) — that is the presentation order everywhere; never `sorted()` it, since alphabetical order puts `1.91:1` first and reads as noise. Fast to test in memory.
- `layout.py` — pure arithmetic, no PIL and no I/O. Solves composite arrangements by expressing each node's width as an affine function of its height, then scoring candidates on frame fill. For two images it tries a row and a column; for three it tries a row, a column, and the four variants with one large panel beside two stacked ones, and keeps whichever fills the frame best. Never crops, never permutes input order. `solve()` and `evaluate()` take a `FrameStyle`, and a solved `Layout` reports `gutters` — the exact rectangles between adjacent panels — alongside `boxes`, so the renderer can paint them a second colour without redoing the arithmetic. Each gutter rectangle is inflated by a pixel at both ends along the gutter axis, because a panel's rounded edge can land a pixel off the rounded gutter edge; the cross axis is not inflated, since bleeding there would put gutter colour into the outer border.
- `compose.py` — PIL in, PIL out, like `geometry.py`. Three passes in this order: the whole exact-size canvas takes the border colour, the gutter rectangles take the gutter colour, then the panels land on top. That order is what lets the gutters be inflated without ever showing. Refuses a box whose aspect disagrees with its image rather than distorting it.
- `pipeline.py` — the only module that touches the filesystem. Re-exports `AspectRatio`, `RATIOS`, `DEFAULT_RATIO`, `FrameStyle`, `DEFAULT_STYLE`, `parse_colour` and `MAX_PERCENT` from `geometry` specifically so `cli.py` and `gui/` can offer ratio and border selection without importing `geometry` directly — that preserves the stated dependency direction. Do not "simplify" these re-exports away; that would force `cli`/`gui` to import `geometry` directly and break the invariant. `pipeline.py` also owns the output-filename contract (`{prefix}_1_padded.jpg`, `{prefix}_2_section1.jpg`, `{prefix}_3_section2.jpg`, ... one entry per detail frame) via `output_paths()`, plus `process_image()`, `find_panoramas()`, and `process_folder()`. `process_folder()` reports per-file failures in the returned `BatchResult` instead of raising, so one bad image doesn't abort a batch; callers (CLI, GUI) decide how to surface them. It also owns `compose_images()`, which solves a layout via `layout.solve()` and renders it via `compose.render()`, writing `{prefix}_diptych.jpg` or `{prefix}_triptych.jpg` and returning a `CompositeResult(path, layout_name)`. Unlike `process_image()`, `compose_images()` accepts portrait input — mixing orientations is the point. Six entry points take a `FrameStyle` (`process_image`, `preview_frames`, `name_layout`, `compose_preview`, `compose_images`, `process_folder`), and in each one `style` is the last parameter with a default, so a new option goes in front of it rather than displacing it. That is a rule about where `style` lives, not a promise that nothing moves: adding `positions` ahead of it did break positional calls, and `cli.py` had to start spelling `style=style`. It also re-exports the position model (`default_positions`, `normalise_positions`, `move_position`, `insert_position`, `drop_position`, `frame_width`, `position_travel`) for the same reason, and `ribbon_thumbnail()` decodes the small copy of the panorama the ribbon draws — separate from `cached_preview_source()`, which holds a much larger copy for cutting frames from.
- `cli.py` — argparse entry points (`maskingframe`, `maskingframe-gui`). Exposes `--ratio` (default `4:5`/Portrait) via a `type=` converter, not `choices=`, so it accepts both the bare ratio (`4:5`) and the name (`portrait`), case-insensitively; an unknown value is rejected with a message naming every accepted spelling. `--help` lists them in presentation order as `portrait|4:5, square|1:1, landscape|1.91:1`. It also exposes `--border`, `--border-colour`, `--gutter`, `--gutter-colour` and `--border-detail-frames`, assembled into a `FrameStyle` by `_style_from_args()`. `--border-color` and `--gutter-color` are accepted as aliases so nobody has to guess the spelling, but the British form is the one documented. Widths and colours are validated by `type=` converters at parse time, so a typo fails with argparse's own message instead of at render time. There is a `compose` subcommand, and there is deliberately no `split` one: splitting stays at the top level so `maskingframe pano.jpg out` keeps working exactly as it always has, which also rules out argparse subparsers (the `input` positional would compete with the command name). `main()` therefore dispatches on the literal first word — if it is `compose`, the rest goes to `build_compose_parser()`, otherwise to `build_parser()`. The one cost is that a file named exactly `compose` in the working directory is shadowed and has to be spelled `./compose`. `_add_style_arguments()` attaches the ratio and framing flags to both parsers from one definition, so the two commands can't drift apart. Compose takes its sources as `nargs="+"` and checks the count afterwards, because argparse can't express "2 or 3" without mis-assigning arguments, and the error then names how many were actually given. Its output is `-o`/`--output` (default `output`), not a trailing positional, which after a variable-length list would be ambiguous. It prints the winning layout name from `CompositeResult` — the automatic arrangement is the interesting part — and, unlike the split path, applies no landscape check. Never exits on import; the PySide6-availability guard lives in `gui_main()`, not at module scope, so importing the package can never terminate the host process. Imports `run` from `gui`, the package, not from any specific submodule inside it.
- `gui/` — Qt (PySide6) front end. `theme.py` (the palette and one stylesheet; see "The theme" below), `shell.py` (the skeleton both tabs share: `RebateBand`, `TwoColumn`, the `section`/`help_label`/`data_label` helpers, `PathRow`, two hand-drawn widgets — `Combo`, because flattening a combobox takes Qt's themed arrow with it, and `TabBand`, because `QTabWidget` centres its bar on macOS — plus `Swatch`, a flat block of colour that opens the picker, and `BorderControls`, the border section both tabs show in the same place), `settings.py` (the only module that touches `QSettings`), `work.py` (running slow work off the GUI thread — read it before adding any), `app.py` (`MainWindow` and `run()`), `split_tab.py`, `compose_tab.py`, `strip.py` (`ContactStrip`), `ribbon.py` (`FrameRibbon`, the whole panorama with a draggable window per detail frame) and `sources.py` (`SourcesList`). `gui/__init__.py` re-exports `run` and `MainWindow`; `cli.gui_main` imports `run` from the package, so that name must keep working. Only `pipeline` is imported from outside the package, never `geometry`, `layout` or `compose` directly.

Both tabs expose `subject`, `detail` and a `band_changed` signal to the shell, and nothing else. The band belongs to the shell rather than to either tab, so the tabs never know about the band or about each other.

### Remembering the border

`gui/settings.py` is the only module that constructs a `QSettings`, so a reader and a writer can never end up on different files. It states its format and scope explicitly: the two-argument `QSettings(organisation, application)` constructor pins itself to the platform's native format and then ignores `setDefaultFormat` and `setPath`, which on macOS means a plist a test cannot redirect.

A stored value is untrusted input — the file is plain text the user can edit, and it outlives any release — so `load_style()` validates every field through `FrameStyle` and falls back to `DEFAULT_STYLE` whole if any of it is wrong. Half a remembered setting is more confusing than none.

Split and Compose store their styles under separate scopes (`settings.SPLIT`, `settings.COMPOSE`). A split border and a composite border are different decisions, and sharing one value would surprise whichever tab the user touched second.

`BorderControls.frame_style()` is deliberately not called `style()`: `QWidget` already owns that name for its `QStyle`, and shadowing it would return a different type from an inherited method. `set_style()` restores stored state without emitting, so a tab that saves on `style_changed` does not write back what it has just read.

### Concurrency

**This replaced the tkinter rule; it does not restate it.** There, nothing on a worker could touch any tk object and `root.after()` was the only sanctioned crossing back, so every worker hand-rolled that crossing with its own guard against the window closing mid-flight.

Qt queues a signal emitted from a worker thread to the receiver's thread automatically, and only auto-disconnects it when the slot is a bound method of a destroyed `QObject`. Every caller here passes a closure instead, which has no receiver to drop against, so that protection does not apply. The rule is: **a job returns plain data, and the callback runs on the GUI thread.** Use `work.submit(job, on_done, on_failed)`, and pass `owner=self` whenever the callback touches a widget — `submit` then skips the callback if `owner` has already been destroyed, and otherwise holds the job alive until the callback runs. Never touch a widget inside a job.

Two things that did *not* go away:

- **Staleness.** A user can pick a second file before the first inspection returns, so every background answer carries a monotonically increasing token that the callback compares before it writes anything.
- **Passing context with the answer.** `inspect_source` runs off the GUI thread; if the callback re-read the ratio combobox it could caption one ratio's frame count with another ratio's name. Whatever the job was computed *for* travels back with its result.

### Re-rendering a preview in place

A preview has its border rendered *into* the frames, so a changed setting makes it a picture of settings nobody has any more. It is made again rather than dropped, and three things keep that honest:

- **Cheap on every move, expensive only when the hand stops.** `shell.PercentSlider` emits `valueChanged` on every movement and `settled` once the value is chosen (slider release, or any change arriving with the handle up — an arrow key, Page, Home/End, a programmatic `setValue`). `BorderControls` mirrors that split as `style_changed` (drives the live overlay) and `style_settled` (drives the re-render). `set_style()` is silent on both.
- **The old picture stays up.** A settle never calls `clear_images()` when a re-render is coming; the new frames swap in when they land. The strip is only put back to the overlay when a re-render is impossible (source gone, a run in flight), and `shell.STALE_PREVIEW` says so. `shell.UPDATING_PREVIEW` covers the interval.
- **The decoded source is cached.** `pipeline.cached_preview_source()` holds one decode, keyed on path plus mtime and size, bounded to `PREVIEW_MAX_PIXELS` (28MP, ~84MB, against ~400MB for a full 132MP decode). The bound is set by the detail frames, which are cut from the source and scaled *up* to the ratio's full width — see the comment on the constant for the arithmetic. Only `preview_frames(..., cached=True)` uses it; anything that writes to disk goes on reading the full-resolution original. `compose_preview` needs no cache of its own: `_load_for_box` already drafts each source down toward its solved box.

### The theme

`gui/theme.py` is the design system, and it is presentation only. Two things about it are load-bearing:

- **The palette has range on purpose.** An earlier version was three greys within a few percent of each other with no white and no dark surface, and the whole interface read as a wash. `TABLE` → `PANEL` → `WELL` → `EDGE` → `INK`/`REBATE` spans white to near-black, and every text pairing clears WCAG AA. Don't add a value that sits between two existing ones without a reason.
- **`CHINAGRAPH` is the marking-up layer, and nothing else.** Think about what a grease pencil is actually for on a contact sheet: numbering the frames, ringing the select, marking the one to print, crossing out the one that failed. So chinagraph carries the primary action, the current selection (a selected list row, a checked radio, selected text), the frame and source numbering, the progress bar while a run is in flight, and error text. Chrome does not get it: surfaces, fields, sliders, dividers and rules stay greyscale. The primary action keeps its primacy under that rule because it is the only large filled block of chinagraph in the app — everything else is a hairline, a numeral or an indicator a few pixels across. A second saturated hue costs it that primacy, and so does filling another large area with this one. It is also why field focus is `INK` rather than red — a field turning red when you click into it reads as invalid.

No rounded corners, no drop shadows, no animation, anywhere. The direction is a light table and film rebate, both hard-edged; Qt making all three trivial is not a reason to spend them. `docs/design/2026-07-31-qt-port.md` records why the port happened and what the tkinter build got wrong.

### Border behaviour worth knowing

`make_padded_frame()` fits the panorama inside the target output frame, inset on all four sides by `style.border_px(ratio)`, preserving the panorama's own aspect ratio, then centres it on a full-size canvas filled with the border colour.

The border is a percent of the frame's **short** side, 9% by default, not an absolute pixel count. A fixed width cannot read the same at every ratio: 100px is a modest edge on a 1350px-tall portrait frame and a heavy one on a 566px-tall landscape frame. At 9% that resolves to 97px at `4:5` and `1:1`, and 51px at `1.91:1`. The default gutter is 4%: 43px and 23px.

The border describes the finished output frame, not the source image — whichever axis binds gets exactly the border, and the other axis gets whatever's left over. For a wide panorama at `1:1` or `4:5` that's the width. At `1.91:1` the default inset box is 978x464, ratio 2.108:1, so a panorama flatter than that binds on height instead; this project's own 2.33:1 samples are steeper and bind on width. The threshold moves with the border width, so work out the inset box before assuming the border means "left and right".

That asymmetry is inherent: the panorama's aspect doesn't match the frame's, and frame 1 must show the whole panorama uncropped, so the border can't be made even without cropping content away.

At a tall ratio like `4:5`, most of the padded frame is border — that is the intended aesthetic, not a bug.

`make_padded_frame()` scales the panorama directly to its fitted size with `Image.Resampling.LANCZOS` and pastes it onto a canvas already sized to `(ratio.width, ratio.height)` — the same pixel size as every detail frame — rather than compositing at source scale and downscaling. That keeps a large-format scan from briefly allocating a huge intermediate canvas as well as avoiding a many-megabyte first frame beside sub-megabyte detail frames.

Detail frames are full-bleed by default. The border is what makes frame 1 the establishing shot, and giving every frame one flattens that distinction. `style.border_detail_frames` turns it on for people who want the whole carousel to read as one object; the crop then targets the inset box and the border is drawn around it.

### Where the detail frames land

A detail frame is one number: its left edge as a fraction of the panorama's
width. The width is derived, not stored — `pano_height * ratio` — so every
detail frame is a full-height crop at exactly the output aspect and moving one
frame never resizes another.

Positions are held ascending, and a frame dragged past its neighbour stops at
it rather than swapping with it: the frames are numbered, and a carousel
running backwards along the picture is confusing. Overlap is allowed, because
two tight crops on one subject is a legitimate choice.

`section_count()` is unchanged and still gives the opening count. It is a first
guess now, not a constraint.

The ribbon (`gui/ribbon.py`) sits above the contact strip and shows where the
frames come from; the strip shows what they are. Both write to one tuple owned
by `SplitTab`, so they cannot disagree. Folder mode hides the ribbon and cuts
with the even default — a position is chosen by looking at one photograph — and
says so where the ribbon would be, because silence would read as a missing
feature. The CLI has no position flags for the same reason.

Both views also take focus and handle keys, because a feature that decides what
every output frame contains must not need a pointer. The line under the ribbon
says so (`split_tab.KEY_HELP`): with the ribbon up it states the keys, and with
it hidden it says why there is nothing to place. Left and Right move the
selected frame by `split_tab.KEY_STEP` (1% of the panorama's width), Shift makes
that ten steps, Home and End send it to the ends of its travel, and Up and Down
move the selection, stopping at the ends rather than wrapping. A key press goes
through `geometry.move_position`, the same rule both drags obey, so the two
cannot disagree.

The widgets emit a count of steps rather than a distance. How far a step moves
is policy, and the tab is the only thing that knows what a percent of this
panorama is — so `ribbon.py` and `strip.py` stay presentation only. Each widget
speaks its own numbering: the ribbon's windows are detail frames, the strip's
frames include frame 1, and the tab converts, exactly as it does for the drags.

The selection is marked in chinagraph on the selected frame's edge — the
ribbon window's border, the strip frame's aperture — and stated in words in the
rail (`Frame 3 · 42% along`). Both, not either: a state carried by colour alone
fails the WCAG 2.2 AA floor this project holds. Every numeral in both widgets
stays chinagraph whatever is selected, as the sources list's do: the numbering
is the marked-up sheet, and demoting it to ink to make one numeral stand out
spends the thing that made it read that way.

Focus is a different state from selection and the two can be present at once,
so focus takes the widget's own outer edge in `INK`, two pixels wide
(`strip.FOCUS_EDGE`), exactly as a focused field does. `ContactStrip.edge_pen`,
`ContactStrip.aperture_pen`, `ContactStrip.numeral_colour` and
`FrameRibbon.edge_pen` are the decisions themselves, exposed so a test can
assert the colour rather than re-derive the geometry.
The rail's sentence is also what a screen reader hears: `SplitTab` pushes it
verbatim into both widgets with `setAccessibleDescription`, so the two views and
the rail cannot say different things about the same frame. `setAccessibleName`
stays each widget's plain identity — "Panorama overview", "Contact strip". The
widgets compose no sentence of their own: a percent of the panorama's width is
knowledge neither has ever had, which is the whole reason the tab converts for
them, and the strip's old "Frame 3 of 5" said the same words after every arrow
press.

A selection is dropped at the cause, not guarded at every reader.
`FrameRibbon.set_plan` and `ContactStrip.set_frames` both drop a selection the
incoming plan or frame list can no longer support, and `SplitTab._set_positions`
makes the same decision for the tab's own copy. That is why no reader of the
selection needs a bounds check. The alternative — clamping frame 3 to frame 2 —
was rejected: it silently substitutes a different frame for the one the user
picked, which looks like the same selection but points at different content.

Focus announces the selection it makes. Both widgets emit `selection_changed`
when focus is what selected the frame. Without that, a single Tab press marked
a frame in chinagraph while the tab still held nothing and the rail was empty —
the state was carried by colour alone, which is the failure this work exists to
remove. `set_selected` stays silent on both widgets, so the tab adopting the
selection and echoing it back cannot loop.

A held key settles rather than rendering per repeat. `split_tab.NUDGE_SETTLE_MS`
is 120 ms, comfortably longer than a single auto-repeat interval (the platform
fires 25 to 30 times a second), so one render happens when the key stops, the
way a drag renders once on release. Positions and the spoken names still update
on every keystroke; only the picture waits. The timer is stopped when a run or
a preview starts, so a pending settle cannot fire into one.

A source narrower than one output tile (a 1.5:1 image at `1.91:1`) has no
travel at all: every position clamps to zero and the crop is the whole width.
Degenerate, but it must not raise.

### The two colours on a composite

A composite has a border colour and a gutter colour, and they cover different things. The gutter colour fills **only** the strips between adjacent panels — the rectangles `layout` reports in `Layout.gutters`. Everything else is the border colour: the outer margin, and the slack left over from centring the assembled block inside it. Set both to the same value and the composite looks exactly as it did before the two were separable, which is why the default for both is white.

### Behaviour changes from the pre-refactor scripts

- `find_panoramas()` no longer double-counts files on case-insensitive filesystems (the old code globbed `*.jpg` and `*.JPG` separately, matching the same file twice).
- Folder mode defaults its output to `./output` when omitted; the old CLI required it and errored otherwise.
- Batch failures are reported rather than silently swallowed: the CLI exits non-zero and prints failures to stderr, and the GUI status reads "Wrote N of M images at {ratio.display}, K failed" instead of always claiming success. The GUI also names the ratio and frame count for single-file runs ("Wrote N detail frames at {ratio.display}"), and shows an explicit "No panoramas found" dialog instead of a green success dialog when a folder has no JPEGs.
- `process_image()` converts the source to RGB (`.convert("RGB")`) before processing, so a grayscale or RGBA/P-mode source now produces RGB sections instead of preserving its original mode. The legacy script had no such conversion and crashed with "cannot write mode RGBA as JPEG" on non-RGB inputs; the refactor fixes that but means the "byte-identical to the legacy output" guarantee is scoped to RGB inputs.
- The output is no longer a fixed four images (one padded square plus three 1080x1080 sections). It is one padded frame plus a variable number of detail frames — never fewer than two — derived from the chosen ratio and the panorama's aspect ratio via `section_count()`. The frames after the first are a zoom, not a tiling, which is why the count floors at two rather than one.
- A detail frame is no longer a `pano_width // count` tile. It is a full-height crop exactly `pano_height * ratio` wide, placed by a position — its left edge as a fraction of the panorama's width. The tiles no longer meet edge to edge, which they never needed to: the detail frames are a zoom, not a tiling. The gain is that nothing vertical is discarded. Before, a 2.4:1 panorama at `1.91:1` got two 1.2:1 tiles that `make_section` scaled to cover and then centre-cropped the top and bottom away from. The golden hashes were re-baselined on 2026-08-01; the padded frame is unaffected.
- Portrait input (width < height) is rejected with a `ValueError` naming the offending file; in a batch this is caught per-file so the rest of the batch still runs.
- `Image.MAX_IMAGE_PIXELS` is set to `None` in `pipeline.py`. The user's own large-format scans can exceed Pillow's ~178MP decompression-bomb guard (the largest sample here is 132MP); lifting the guard stops a legitimate scan being reported as a corrupt file. Malformed input is still caught by the per-file exception handling in `process_folder()`.
- The padded output was renamed from `{prefix}_1_padded_square.jpg` to `{prefix}_1_padded.jpg`, since it is only square when the target ratio is `1:1`.
- The border and the composite gutter are settings rather than constants. The `SIDE_PADDING`, `GUTTER` and `BACKGROUND` constants are gone, replaced by a `FrameStyle` passed down the call chain. Both widths and both colours are set from the CLI flags or the GUI's Border section, and the GUI remembers them between launches.
- The default border at `1.91:1` changed from 100px to 51px. That is the point of measuring in percent: the old fixed 100px took a third of a 566px-tall frame, while the same constant was a thin edge at `4:5`. Output at `4:5` and `1:1` moved too, from 100px to 97px.


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:6cd5cc61 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->
