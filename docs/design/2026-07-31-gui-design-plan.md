# auto-border-pano — design audit and plan

Design lead review, grounded in two screenshots of the running app
(`/tmp/gui-split.png`, `/tmp/gui-compose.png`) and the current
`src/auto_border_pano/gui/` implementation.

---

## 1. Audit

### The thing you cannot unsee

**The empty preview box owns 45% of both windows and shows nothing.** On
Split it is a 1650x540pt sunken rectangle labelled "Preview (Last
Processed)" containing literally zero pixels. On Compose the same box is
labelled "Composite" and is equally empty. `PreviewPanes.__init__` builds
the `LabelFrame` but never calls `rebuild()`, so until the user's first
successful run the single most prominent element in the app is a void.
There is no empty state at all — not even the "No preview" text that
`rebuild()` would have produced. The app's largest visual gesture is
dedicated to absence.

Worse, once it *is* populated, `PREVIEW_MAX_PX = 150` caps thumbnails at
150pt inside a pane 540pt tall. So the fully-working state is a row of
postage stamps floating in the same void. The box is sized for an ambition
the thumbnails don't fulfil. For a user whose source files are
19921x6607, a 150px thumbnail cannot answer the only question they have —
*did the detail crop land on the right part of the frame?*

### Hierarchy

There is none. Every row on Split is the same weight, the same 13pt system
font, the same vertical rhythm. Scanning the tab top to bottom: label,
label, label, label, button, label, label. The only thing with visual
emphasis is "Process Images", and it gets that emphasis by being centred —
which is also the only centred thing on the tab, so it reads as an
alignment error rather than a hierarchy decision.

Compose is worse: "Preview" and "Save" sit side by side, same size, same
styling, giving equal billing to a free reversible action and a
writes-to-disk action.

### Alignment

Split has four alignment columns fighting: labels flush left at x=76,
entries at x=190, the "Browse File" button at x=1224, "Browse Folder"
ending at x=1714. Row 2's "Browse" is at x=1246 — 22pt off from row 1's
"Browse File" — because row 0 has two buttons in columns 2 and 3 while row
1 has one button in column 2, and the grid columns are sized by content.
The two Browse buttons on consecutive rows are visibly not aligned. The
right edge of the two entry fields (x=1197) aligns with nothing else on the
tab; the Progress and Preview frames end at x=1727.

On Compose, the listbox right edge (x=1503) aligns with nothing; the Output
entry runs to x=1539; the preview frame to x=1727; the button stack to
x=1712. Four different right edges in one 1800pt-wide tab.

Between the tabs there is no shared grid whatsoever. Switching tabs
re-lays-out the entire window.

### Spacing rhythm

`pady` values in `split_tab.py` run 5, 5, 10, 5, 20, 10, 10 with no system
behind them — 20 for the button, 10 for two frames, 5 for form rows, and a
uniform 5pt `padx`. There is no scale (no 4/8/16 or 6/12/24), so nothing
groups. "Mode: Single File" floats equidistant between the Output row and
the Aspect ratio row and therefore belongs to neither, when it is in fact a
consequence of the Input row directly above it.

### The Listbox

`tk.Listbox` is a raw Tk widget dropped among ttk widgets and it shows: on
Compose it renders as a **pure black rectangle with a hard 2pt sunken
border**, against the mid-grey ttk panel. Nothing else in the app is that
black or has that border. It reads like a terminal pasted into a dialog.
It also has no scrollbar, is `height=4` for a list that is hard-capped at 3
items (so one row is always dead space), and gives no indication that
order matters — which it does, since order determines left-to-right
placement in the composite.

The Up/Down/Remove buttons are always enabled even with nothing selected,
where they silently no-op (`move_up` returns early on `index is None`).
Buttons that do nothing when pressed are worse than disabled buttons.

### Copy

- **"3 image(s)"** — machine plural, and it reports a count the user can
  see by counting. It should report *consequence*: two images makes a
  diptych, three a triptych.
- **"detail frames are derived from this"** — passive, lowercase-only next
  to sentence-case labels everywhere else, greyed to `grey40` so it looks
  disabled, and it explains a mechanism instead of stating a result. It
  also sits alone at x=659 with no relationship to the combobox it
  describes. It's a footnote pretending to be a helper.
- **"Mode: Single File"** — flagged in the brief and correctly so. This is
  a *label reporting the state of a control that does not exist*. The
  actual control is which of the two Browse buttons you happened to press.
  A user cannot switch back to Single File without re-browsing. State the
  interface exposes read-only, but which the user obviously wants to
  change, is a missing control.
- **"Process Images"** — plural even in single-file mode, and generic. It
  should name what appears on disk.
- **"Preview (Last Processed)"** — parenthetical disclaimer in a title.
- **"Ready"** — the status line's resting state carries no information. It
  could hold the thing the user actually wants to know.
- **"Whole"** / **"Detail 1"** — "Whole" is an adjective doing a noun's
  job.
- Error dialogs titled **"Error"** with body **"Please select a valid
  input"** — "please" is filler, "valid" is unfalsifiable, and the title
  duplicates the icon.
- **"Limit" / "At most 3 images"** — a modal dialog to report a rule the
  interface should have made unbreakable by disabling Add.
- Window title **"Panorama Splitter"** is wrong on the Compose tab, which
  splits nothing.

### Things not in the brief's list

1. **Two tabs that share four concepts and duplicate none of the code or
   layout.** Both have an aspect ratio combobox, an output field, a Browse
   button, a run button, a status line and a preview pane — arranged
   differently, ordered differently, spaced differently. Aspect ratio is
   row 3 on Split and row 1 on Compose. Output is row 1 on Split and row 2
   on Compose. There is one product here, not two.

2. **The Progress `LabelFrame` never has anything to say on the Split
   tab in single-file mode.** `_run_single` never calls `_set_progress`,
   so the bar goes 0 → 100 with no intermediate state, for an operation on
   a 19921x6607 file that takes real seconds. The largest chrome element
   after the preview is a progress bar that, in the most common workflow,
   only ever shows empty or full.

3. **Success is reported by modal dialog.** `_finish` and `_finish_batch`
   both fire `messagebox.showinfo` on every successful run. The status
   line *already says the same sentence*. The user is required to dismiss a
   modal to see the previews the modal is covering. This is the single
   worst interaction in the app.

4. **No file metadata anywhere.** The app knows the panorama's pixel
   dimensions and its aspect ratio, and knows how many detail frames that
   implies — before processing. It shows none of it. The user picks a
   ratio blind and finds out how many frames they got from a past-tense
   status message.

5. **Input and output are both free-text entries** with no validation
   feedback until you press the button and get a modal. The path
   `/Users/albert/Pictures/horizons3-hp5-4.jpg` is set in the same
   proportional body font as the labels, so the filename — the only part
   that matters — has no prominence within it.

6. **No keyboard story.** No `Return` binding on the entries, no accelerator
   on the primary action, no explicit tab order, no visible focus ring
   under aqua on the Canvas-free widgets we have. Tab order currently
   follows grid creation order, which on Split means Input entry → Browse
   File → Browse Folder → Output entry → Browse, which is at least
   coherent, but nothing is documented or tested.

7. **Colour carries zero information.** The only saturated pixels in
   either screenshot are the two system-blue combobox arrows, which are the
   least important controls on screen. The primary action is the same grey
   as Browse.

8. **The dark grey window is inherited, not chosen** — it's macOS dark mode
   passing through `aqua`. In light mode this app is a different, equally
   unconsidered application.

---

## 2. Design direction

### The idea: **the light table, not the darkroom**

Every photo tool the user touches — Lightroom, Capture One, Photoshop,
Silverfast — is dark grey chrome. There's a real reason for that: dark
surrounds let you judge tone and colour without the UI biasing your eye.

**This app never asks you to judge tone.** It asks you to judge *layout*:
did the crop land right, is the border even, does the triptych balance.
Tone is fixed the moment the scan is made. So the dark chrome here is
inherited convention doing no work.

The direction is the other half of the film workflow: the **light table**.
A cool, even, daylight-balanced 5000K surface, with the strip laid on it
and read with a loupe. This is where a film photographer actually chooses
which frames to publish — which is precisely the job this app does.

**This is the risk.** Shipping a photo tool that is bright, cool white
when the entire category is dark grey will feel wrong for about ten
seconds. It's justified because the metaphor is literal rather than
decorative: you are selecting frames from a strip, and you do that on a
lightbox. It also does something dark chrome can't — a white UI lets the
white border in the *output* read as an actual white border, instead of
disappearing into a grey field. On the current dark UI, the padded frame's
white border is the brightest thing on screen and reads as glare. On a
light table it reads as the paper margin it's meant to be.

The tension the brief names — analogue craft vs. Instagram — is designed in
by keeping the *chrome* strictly analogue (rebate, sleeve, chinagraph) and
the *content* strictly digital (crisp 4:5 rectangles, exact pixel counts,
no skeuomorphic grain over the user's actual photographs). The app is a
light table; what's on it is a JPEG. Nothing is ever faked onto the
photographs themselves.

### Colour — 5 tokens

| Token | Hex | Role |
|---|---|---|
| `lightbox` | `#F1F4F6` | The table surface. Cool white, ~5200K. Window and panel background. |
| `sleeve` | `#DCE1E4` | Polypropylene negative sleeve. Recessed areas, input wells, the strip's backing. |
| `rebate` | `#1B1D1F` | Film base. The strip, the header band, primary text. |
| `sprocket` | `#8B9298` | Sprocket-hole grey. Secondary text, rules, disabled states, metadata. |
| `chinagraph` | `#D5372C` | The grease pencil an editor marks selects with. **The only saturated colour in the app.** Used for exactly two things: the active tab's frame number, and the primary action. Nothing else. |

No second accent. No gradient. `chinagraph` earns its salience by being
alone; the moment a second colour appears the primary action stops reading
as primary.

Errors use `chinagraph` at full strength with an inline rule, not a modal.
Success uses no colour at all — the preview appearing *is* the success
state.

Contrast: `rebate` on `lightbox` is 15.4:1. `sprocket` on `lightbox` is
3.3:1 — **fails AA for body text**, so `sprocket` is restricted to 12pt+
semibold utility text (3:1 large-text threshold) and non-text rules. Body
secondary text uses `rebate` at 70% composited over `lightbox` =
`#5A5F63`, 7.1:1. `chinagraph` on `lightbox` is 4.6:1, passes AA for
normal text; the primary button inverts to `lightbox` on `chinagraph` at
4.6:1.

### Type

Three roles, all with system-installed fallbacks so nothing has to ship.

| Role | Stack | Why |
|---|---|---|
| **Emulsion** (display) | `Avenir Next Condensed` → `Helvetica Neue Condensed` → `Oswald` → `Helvetica Neue` | Film edge markings are condensed sans caps: `ILFORD HP5 PLUS · 400`. Used **only** in the rebate band and the strip's frame numbers. All-caps, tracked wide. Never for prose. |
| **Body** | `Avenir Next` → `Inter` → `Helvetica Neue` | Humanist geometric, reads well small, doesn't compete with the condensed caps. Labels, buttons, status, help text. |
| **Data** | `SF Mono` → `Menlo` → `Courier New` | Paths, pixel dimensions, frame counts, ratios. Anything the machine measured is set in mono. This alone fixes the path entries: `horizons3-hp5-4.jpg` in mono against proportional labels immediately separates *what you chose* from *what we call it*. |

Scale (points, tkinter's unit):

```
26  emulsion  caps  tracking +180   filename in the rebate band
19  body      600                   tab / section headings
15  body      500                   primary action, section labels
13  body      400                   body default, entries, buttons
12  emulsion  caps  tracking +120   frame numbers, rebate stencils
11  data      400                   dimensions, ratios, counts
11  body      400                   help text, status
```

Small overall. This is a utility that gets used 30 seconds at a time; large
type would be posturing.

### Layout concept

**One shared skeleton for both tabs**, because there is one product. A
persistent rebate band across the top carrying identity and the loaded
file. Below it: a fixed 340pt control rail on the left, and the light table
filling everything to the right of it. The preview stops being a bottom
afterthought and becomes the subject of the window. Controls read
top-to-bottom as a sentence: *this file → at this ratio → to here → go.*

#### Split tab

```
┌──────────────────────────────────────────────────────────────────────────┐
│▓▓ 1 ▒▒ SPLIT  ▓▓ 2 ▒▒ DIPTYCH   HORIZONS3-HP5-4          ▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │ rebate band, canvas
├────────────────────────┬─────────────────────────────────────────────────┤
│                        │                                                 │
│  NEGATIVE              │   ┌──── contact strip, canvas ────────────────┐  │
│  ┌──────────────────┐  │   │ ▓1▓                                   ▓ │  │
│  │ horizons3-hp5-4  │  │   │ ▓ ┌───────────────────────────────┐   ▓ │  │
│  │ .jpg          [·]│  │   │ ▓ │                               │   ▓ │  │
│  └──────────────────┘  │   │ ▓ │      whole panorama           │   ▓ │  │
│  19921 × 6607   3.01:1 │   │ ▓ │      on its border            │   ▓ │  │
│   ○ one frame          │   │ ▓ └───────────────────────────────┘   ▓ │  │
│   ● whole folder       │   │ ▓  FRAME 1 · WHOLE           4:5     ▓ │  │
│                        │   └───────────────────────────────────────┘  │
│  FORMAT                │                                                 │
│  ┌──────────────────┐  │   ┌───────────┐ ┌───────────┐ ┌───────────┐    │
│  │ Portrait  4:5  ⌄ │  │   │▓2▓        │ │▓3▓        │ │▓4▓        │    │
│  └──────────────────┘  │   │▓ ┌─────┐  │ │▓ ┌─────┐  │ │▓ ┌─────┐  │    │
│  3 detail frames       │   │▓ │     │  │ │▓ │     │  │ │▓ │     │  │    │
│                        │   │▓ └─────┘  │ │▓ └─────┘  │ │▓ └─────┘  │    │
│  DESTINATION           │   │▓ DETAIL 1 │ │▓ DETAIL 2 │ │▓ DETAIL 3 │    │
│  ┌──────────────────┐  │   └───────────┘ └───────────┘ └───────────┘    │
│  │ …/horizons3-hp5- │  │                                                 │
│  │ 4_output      [·]│  │                                                 │
│  └──────────────────┘  │                                                 │
│                        │                                                 │
│  ┌──────────────────┐  │                                                 │
│  │  ▀▀ Cut 4 frames │  │  ← chinagraph, the only saturated thing         │
│  └──────────────────┘  │                                                 │
│                        │                                                 │
│  Ready                 │                                                 │
└────────────────────────┴─────────────────────────────────────────────────┘
```

Key moves: the ratio combobox now *tells you the consequence* ("3 detail
frames") before you commit, computed from the loaded file's real
dimensions. The dimensions and native ratio sit under the filename in
mono, so you know what you loaded. Single/folder is a real radio pair, not
a read-only label. The button counts the frames it will produce.

During a run, the progress bar is not a bar — the strip's frames fill in
one by one as they're written. Progress *is* the preview.

#### Diptych / Triptych tab

```
┌──────────────────────────────────────────────────────────────────────────┐
│▓▓ 1 ▒▒ SPLIT  ▓▓ 2 ▒▒ DIPTYCH   3 NEGATIVES              ▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
├────────────────────────┬─────────────────────────────────────────────────┤
│                        │                                                 │
│  NEGATIVES             │   ┌──── the composite, canvas ───────────────┐   │
│  ┌──────────────────┐  │   │ ▓                                     ▓ │   │
│  │▌1  horizons3-hp5 │  │   │ ▓  ┌─────────────┐                   ▓ │   │
│  │    -4.jpg   4000×│  │   │ ▓  │             │                   ▓ │   │
│  ├──────────────────┤  │   │ ▓  │   row of    │                   ▓ │   │
│  │▌2  horizons3-hp5 │  │   │ ▓  │   three     │                   ▓ │   │
│  │    -5.jpg   4000×│  │   │ ▓  │             │                   ▓ │   │
│  ├──────────────────┤  │   │ ▓  └─────────────┘                   ▓ │   │
│  │▌3  horizons3-hp5 │  │   │ ▓  TRIPTYCH · ROW OF THREE · 4:5     ▓ │   │
│  │    -6.jpg   4000×│  │   └───────────────────────────────────────┘   │
│  └──────────────────┘  │                                                 │
│   + Add    ↑  ↓   ×    │                                                 │
│  Left to right, in     │                                                 │
│  this order.           │                                                 │
│                        │                                                 │
│  FORMAT                │                                                 │
│  ┌──────────────────┐  │                                                 │
│  │ Portrait  4:5  ⌄ │  │                                                 │
│  └──────────────────┘  │                                                 │
│  Row of three          │  ← the solved layout, named, updating live      │
│                        │                                                 │
│  DESTINATION           │                                                 │
│  ┌──────────────────┐  │                                                 │
│  │ …_composite   [·]│  │                                                 │
│  └──────────────────┘  │                                                 │
│                        │                                                 │
│  ┌──────────────────┐  │                                                 │
│  │  ▀▀ Save triptych│  │                                                 │
│  └──────────────────┘  │                                                 │
│  Preview               │  ← secondary, text-weight, not a peer button    │
└────────────────────────┴─────────────────────────────────────────────────┘
```

The Listbox becomes a Canvas strip of numbered rows, where the number is a
chinagraph-red frame number in the same visual language as the contact
strip — so the ordering control and the result speak the same language.
Reordering moves a numbered frame; the number is the arrangement.

### Signature element: **the rebate**

The thing this app is remembered by is that **every frame in it is
surrounded by film rebate** — the black band outside the image area
carrying the frame number in chinagraph red and the stencilled emulsion
name in condensed caps.

It appears in exactly three places, and each time it carries real
information:

- **The header band** — the app's identity plus the loaded filename set in
  emulsion caps, exactly as a lab prints it on the edge of a strip. The
  tabs are frame numbers `1` and `2` in the rebate; the active one is
  marked chinagraph, the way an editor marks a select.
- **The contact strip** — the preview panes butted together in one
  continuous strip with a shared rebate running along it, frame numbers
  `1 2 3 4` in sequence, each frame's role and ratio stencilled beneath.
  This replaces four disconnected sunken boxes with one object.
- **The empty state** — an unexposed strip. Rebate, frame numbers, and
  nothing between them. Captioned `NOTHING ON THE STRIP YET`. The void
  becomes the most characteristic image in the app rather than its
  biggest failure.

The numbering here is *earned* — the brief's own output is a carousel where
frame 1 is the whole panorama and frames 2..N are details in order. The
sequence is real. That's why numbered markers are correct here and would
be decoration anywhere else.

Restraint check, Chanel's mirror: I am cutting the grain texture, the
sprocket-hole perforations, and the paper-fibre background I wanted. The
rebate band and the frame numbers carry the idea. Perforations would be
ornament on ornament, and grain over the user's own scans would be a lie.

### What I revised after self-critique

- **Killed a cream/serif/terracotta direction.** My first instinct was warm
  cream, a high-contrast serif, and a burnt-orange accent, because
  "analogue heritage". That is AI-design default #1 exactly, and worse, it
  is wrong for the subject — nothing in a darkroom or on a light table is
  warm cream, and the warm accent is a *safelight*, which is about
  *avoiding* seeing clearly. Replaced with the cool 5200K lightbox, which
  is the actual colour temperature of the surface this work happens on.
- **Rejected keeping the dark UI.** Dark grey + one bright accent is AI
  default #2 and is also the current app. Staying dark would have been the
  path of least resistance and would have produced another grey box.
- **Rejected an amber accent** for the same reason terracotta went — it
  reads as the default warm accent. `chinagraph` red is the mark an editor
  makes on a contact sheet to choose a frame, which is the app's entire
  purpose.
- **Rejected hairline-rule broadsheet layout** (default #3) for the
  control rail. The rail is grouped by labelled sections with whitespace,
  not by rules.

---

## 3. Copy rewrite

Every user-facing string in both tabs. Current → proposed.

### Shell

| Where | Current | Proposed |
|---|---|---|
| Window title | `Panorama Splitter` | `Auto Border Pano` |
| Tab 1 | `Split` | `Split` (with frame number `1`) |
| Tab 2 | `Diptych / Triptych` | `Compose` (with frame number `2`) |

`Compose` because the tab handles both diptychs and triptychs and the
result is named for you; the slash was doing the work a single verb does
better.

### Split tab

| Element | Current | Proposed |
|---|---|---|
| Input label | `Input:` | `NEGATIVE` (section heading) |
| Input placeholder | *(none)* | `Choose a panorama, or a folder of them` |
| Browse file | `Browse File` | `Choose file` |
| Browse folder | `Browse Folder` | `Choose folder` |
| Mode indicator | `Mode: Single File` | Radio: `○ One frame` / `○ Whole folder` |
| *(new)* file facts | — | `19921 × 6607 · 3.01:1` (mono) |
| Output label | `Output:` | `DESTINATION` (section heading) |
| Browse output | `Browse` | `Choose folder` |
| Ratio label | `Aspect ratio:` | `FORMAT` (section heading) |
| Ratio help | `detail frames are derived from this` | `3 detail frames` — live, computed, under the combobox |
| Ratio help, no file | — | `Load a negative to see the frame count` |
| Primary action | `Process Images` | `Cut 4 frames` (count live; `Cut frames` when unknown; `Cut 12 folders' worth` → `Cut 36 frames from 12 negatives` in folder mode) |
| Progress frame title | `Progress` | *(removed — the strip fills in instead)* |
| Status, idle | `Ready` | `Ready` when nothing loaded; `4 frames, 4:5, into horizons3-hp5-4_output` once configured |
| Status, running | `Working...` | `Cutting frame 2 of 4` |
| Status, batch | `Processing 1/3: x.jpg` | `Negative 1 of 3 · horizons3-hp5-4.jpg` |
| Done, single | `Wrote N detail frames at Portrait (4:5)` | `Cut 4 frames at 4:5 into horizons3-hp5-4_output` |
| Done, batch | `Wrote N of M images at Portrait (4:5)` | `Cut 3 negatives at 4:5. 12 frames written.` |
| Done, partial | `Wrote 2 of 3 images at …, 1 failed: x.jpg` | `Cut 2 of 3 negatives. horizons3-hp5-6.jpg could not be read.` |
| Empty folder | `No panoramas found` / `No JPG files found in the input folder` | `No JPGs in that folder. Auto Border Pano reads .jpg and .jpeg.` |
| Failure | `Failed` | `Could not cut horizons3-hp5-4.jpg — {reason}` |
| Invalid input | `Error` / `Please select a valid input` | `That file is not there any more. Choose another negative.` |
| Empty output | `Error` / `Please select a valid output` | `Choose where the frames should go.` |
| Success modal | `Success` / *(message)* | **Removed.** The strip filling in is the success state. |
| Preview title | `Preview (Last Processed)` | *(removed — the strip needs no title)* |
| Pane 1 | `Whole` | `FRAME 1 · WHOLE PANORAMA` |
| Pane N | `Detail 1` | `FRAME 2 · DETAIL` |
| Pane empty | `No preview` | `NOTHING ON THE STRIP YET` (once, across the whole strip) |
| Pane error | `Error: {e}` | `UNREADABLE` in the frame, reason in the status line |

### Compose tab

| Element | Current | Proposed |
|---|---|---|
| List heading | *(none)* | `NEGATIVES` |
| Empty list | *(none — bare black box)* | `Add two negatives for a diptych, three for a triptych.` |
| Add | `Add` | `+ Add` |
| Up / Down | `Up` / `Down` | `↑` / `↓` with tooltips `Move earlier` / `Move later` |
| Remove | `Remove` | `×` with tooltip `Remove` |
| *(new)* order hint | — | `Left to right, in this order.` |
| Ratio label | `Aspect ratio:` | `FORMAT` |
| *(new)* solved layout | *(only appears after Preview)* | `Row of three` — live, under the combobox |
| Output label | `Output:` | `DESTINATION` |
| Browse | `Browse` | `Choose folder` |
| Primary | `Save` | `Save triptych` / `Save diptych` |
| Secondary | `Preview` | `Preview` — demoted to text weight, not a peer button |
| Status, empty | `Add two or three images` | `Add two negatives for a diptych, three for a triptych.` |
| Status, 2 | `2 image(s)` | `Diptych, side by side, 4:5` |
| Status, 3 | `3 image(s)` | `Triptych, row of three, 4:5` |
| Status, running | `Working...` | `Composing` |
| Saved | `Saved x.jpg using the two-up layout` | `Saved composite.jpg — row of three, 4:5` |
| Previewing | `Previewing the two-up layout` | `Row of three` (in the strip's stencil, not the status line) |
| Over limit | `Limit` / `At most 3 images` | **Removed.** Add disables at 3. |
| Too few | `Error` / `Select 2 or 3 images` | **Removed.** Save is disabled with a reason under it: `Add one more negative.` |
| No prefix | `Error` / `Please choose an output prefix` | `Choose where the composite should go.` |
| Failure | `Failed` | `Could not compose — {reason}` |
| Preview title | `Composite` | *(removed — the stencil under the frame names the layout)* |

Rules applied throughout: the verb on the button is the verb in the
result (`Cut frames` → `Cut 4 frames at 4:5`); no `please`; no `Error` as a
title; nothing says `image(s)`; every error names the file and the fix;
every empty state is an invitation with a specific next action; the
interface says `negative` and `frame` because that is what the user calls
these things.

---

## 4. Feasibility in tkinter

Per element. **ttk** = achievable with `ttk.Style` under the `clam` theme.
**Canvas** = needs a hand-built Canvas widget with its own event bindings.
**No** = not realistically achievable.

### Achievable with ttk styling (clam theme)

| Element | Notes |
|---|---|
| Whole palette on frames, labels, entries, buttons | `clam` honours `background`, `foreground`, `fieldbackground`, `bordercolor`, `lightcolor`, `darkcolor`. Under `aqua` most of these are ignored — **switching to `clam` is a prerequisite for everything below.** |
| Three-role type system + scale | `tkinter.font.Font` per role, assigned via `style.configure('Body.TLabel', font=…)`. Font *availability* is checkable with `font.families()`, so a fallback chain is straightforward. |
| Section headings (`NEGATIVE`, `FORMAT`) | Caps + condensed font + `sprocket` foreground. Caps must be applied in the string, not by style — there is no text-transform. |
| Consistent spacing scale (6/12/24) | `padx`/`pady` per widget plus `style.configure(..., padding=)`. Purely discipline. |
| Two-column rail + table layout | `grid` with `columnconfigure(0, minsize=340, weight=0)` and `(1, weight=1)`. Trivial and high value. |
| Primary button in `chinagraph` | `clam` `TButton` honours `background`/`foreground`/`bordercolor`; needs `style.map` for `active`/`pressed`/`disabled`. |
| Secondary "Preview" as a text link | `TButton` with `relief=flat`, `borderwidth=0`, `background` = panel. |
| Flat entries with a bottom rule | Entry with `borderwidth=0` + a 1px `tk.Frame` beneath as the rule. |
| Mono paths / dimensions | Font assignment only. |
| Single/folder radio pair | `ttk.Radiobutton` bound to the existing `is_folder_mode` BooleanVar. Removes `mode_label` outright. |
| Live frame count under the combobox | Pure logic — geometry code already computes it; bind to `<<ComboboxSelected>>` and to the input path var. |
| Disabling Add at 3, Save below 2, Up/Down with no selection | `config(state=…)` in `_refresh_list`. Removes two modals. |
| Removing the success modals | Delete four `messagebox.showinfo` calls. |
| Inline errors instead of modals | A `chinagraph` `ttk.Label` under the rail. |
| Keyboard: Return on entries, `Cmd-Return` primary, explicit `takefocus` order | `bind`, `bind_all`. |
| Visible focus ring on ttk widgets | `clam` draws one via `focuscolor`; set it to `chinagraph`. |
| Progressbar restyle | `clam` `Horizontal.TProgressbar` honours `troughcolor`/`background`. Only needed if the strip-fill idea is deferred. |

### Needs a Canvas custom widget

| Element | Cost / notes |
|---|---|
| **The rebate header band** | Moderate. Static ornament: draw a filled rect, place emulsion-caps text, draw frame-number blocks. Tabs become click targets via `tag_bind` — you must hand-implement hover, active state, and keyboard focus/arrow navigation, which ttk's Notebook gave you free. **This is the single largest cost in the plan.** |
| **Letter-spacing on the emulsion caps** | Canvas only, by placing each character with `create_text` at computed x offsets from `font.measure()`. Fine for short static strings; do not do it for anything that reflows. |
| **The contact strip** | Moderate-high. One Canvas hosting composited thumbnails via `ImageTk`, plus rebate band, frame numbers and stencils drawn around them. Replaces `PreviewPanes` wholesale. Resize handling means rebinding `<Configure>` and redrawing. |
| **Unexposed-strip empty state** | Easy once the strip Canvas exists — it's the strip with no images. |
| **Numbered negatives list replacing the Listbox** | Moderate. 2–3 rows max, so no scrolling or virtualisation needed. Selection, click, and keyboard up/down are hand-written — roughly 80 lines. |
| **Progress as frames filling in** | Easy on the strip Canvas; the pipeline already reports per-frame progress in batch mode. Single-file mode currently reports nothing (`_run_single` never calls `_set_progress`), so **the pipeline needs a per-frame callback added** for this to work on the common path. |
| **Rounded corners anywhere** | Canvas only, via arcs or a pre-rendered Pillow image. Honestly: skip them. The direction is a light table and film rebate, both of which are hard-edged. |
| **Tooltips on the ↑ ↓ × buttons** | A borderless `tk.Toplevel` positioned on `<Enter>`, with an `after` delay. Standard, well-trodden, ~40 lines. |

### Not realistically achievable

| Element | Why, and what I'd do instead |
|---|---|
| **Real drop shadows** | No compositing layer. Fakeable by pre-rendering the shadow into a Pillow RGBA image and blitting it — but Tk Canvas has no alpha blending against the canvas background, so it only works over a *known solid* colour. Doable here (the lightbox is one flat colour) but brittle. **I'm cutting shadows from the design.** The strip sits on the table with a 1px `sprocket` rule, not a shadow. |
| **Crisp ornaments on Retina** | Real limitation. Canvas vector primitives scale, but any `ImageTk` bitmap blits at image pixels = points, so pre-rendered Pillow ornaments look soft on a 2x display. Mitigation: draw everything possible with native Canvas primitives, use images only for the user's own photographs (where softness is invisible at thumbnail size). **Accept the constraint; do not pre-render chrome as bitmaps.** |
| **Animation** | Only `after`-driven frame stepping. A 200ms ease on a button hover is not worth 30 lines and a timer. **Cut entirely.** The one motion in the app is frames appearing on the strip as they're written, which is discrete, not animated. |
| **`prefers-reduced-motion`** | No such signal. Moot, since there is no motion. |
| **Native macOS dark-mode following** | Under `clam` you lose the automatic appearance switch. `root.tk.call('tk::unsupported::MacWindowStyle', …)` doesn't help. You would hand-write a second palette and poll `defaults read -g AppleInterfaceStyle`. **Recommend: ship light-only, deliberately.** The light table is the design; a dark variant would undo it. |
| **Text selection / cursor styling inside the Canvas widgets** | The custom list rows won't have real text selection. Acceptable — nobody selects text in a 3-row list. |
| **VoiceOver / accessibility tree for Canvas widgets** | Tk has essentially no accessibility API on macOS, and Canvas-drawn controls are invisible to assistive tech. **This is a genuine regression** versus ttk widgets, which are at least somewhat exposed. Mitigation: keep every Canvas control reachable and operable by keyboard, and keep the *real* ttk widgets for anything a screen-reader user must operate — which argues for keeping the ttk Notebook rather than a Canvas tab bar. See the verdict. |

### Overall verdict

**tkinter carries about 70% of this direction, and the 70% is the part
that matters most.**

Stages 1–3 below — theme switch, palette, type system, two-column layout,
copy, killing the modals, real controls replacing state labels — are all
plain ttk. They will transform the app. None of them require a Canvas.
That is the honest good news: **most of what is wrong with this interface
is not a toolkit limitation, it's an absence of design decisions.**

The remaining 30% is the signature: the rebate band and the contact strip.
Both are achievable on Canvas, at real cost — you are hand-writing widget
behaviour that a real toolkit gives you free, and you lose the
accessibility tree while doing it. The contact strip is worth that cost;
it's the app's whole reason to exist and it replaces the worst element in
the current UI. **The Canvas tab bar is not worth it** — it buys a frame
number and costs you keyboard tab navigation, focus rings, and screen
reader support that `ttk.Notebook` provides. Recommend styling the
Notebook in `clam` and putting the rebate band *below* it, where it can be
a static drawn header carrying the filename with no interaction at all.

**Where the ceiling actually is.** Retina softness on any bitmap ornament,
no shadows, no animation, and no accessibility on custom widgets are hard
limits, and no amount of Canvas work moves them. If the user later wants
the version of this that feels genuinely crafted — precise hairlines at
2x, a strip that scrolls with momentum, a loupe that follows the cursor
over a full-resolution crop — that is a **PySide6/Qt** rewrite of the GUI
layer. Cost: roughly 2–3 days for a like-for-like port (the pipeline,
geometry and CLI are untouched — the GUI is only ~500 lines), a ~40 MB
dependency, LGPL obligations, and a more complicated packaging story on
Windows. The benefit is real: QSS stylesheets, proper high-DPI, real
compositing, `QGraphicsView` for the strip, and native accessibility.
**They have not asked for this and should not do it yet** — stages 1–3
below will close most of the visible gap for a fraction of the effort.
But they should know the ceiling is where it is, so they don't spend a
week fighting Canvas for something Qt does in an afternoon.

---

## 5. Staged plan

Ordered by visual improvement per unit of risk. Each stage ships and is
testable on its own.

### Stage 1 — Theme, palette, type (no structural change)

Switch to `clam`, define the five colour tokens and three font roles in one
new `gui/theme.py`, apply them via named `ttk.Style` classes. Set every
`pady`/`padx` to the 6/12/24 scale. Mono font on the path entries. Primary
button in `chinagraph`, everything else quiet. Focus ring set to
`chinagraph`.

Zero layout changes, zero logic changes. This alone takes the app from
"unconsidered grey" to "someone designed this".

**Risk:** low. The one real risk is `clam` looking non-native, which is the
intended trade. Verify the combobox dropdown and the `filedialog` (which
stays native regardless) still look acceptable.

**Tests:** none need changing. Add one: `theme.apply()` runs under real Tk
without raising, and every font in the fallback chain resolves to something.

### Stage 2 — Copy and modal removal

Apply the full copy table. Delete the four `messagebox.showinfo` success
calls. Replace error modals with an inline `chinagraph` status label.
Disable Add at 3, Save below 2, Up/Down/Remove with no selection, and
delete the two modals that were enforcing those rules.

Highest ratio of user-perceived quality to code changed in the whole plan.
The success modals in particular are removing a mandatory click from every
single run.

**Risk:** low, but this is the stage that **breaks tests**.
`tests/test_gui.py` asserts exact status strings — at minimum
`test_finish_message_reports_count_and_ratio`,
`test_finish_batch_reports_count_and_ratio` (asserts
`"Wrote 1 of 1 images at Landscape (1.91:1)"`),
`test_finish_batch_reports_no_panoramas_found_instead_of_success`, and
`test_preview_titles_track_the_frame_count` (asserts
`["Whole", "Detail 1", …]`). Update the expected strings; the assertions'
*shape* stays valid. Also check the tests that monkeypatch `messagebox` —
removing `showinfo` calls may leave assertions on a call that no longer
happens.

### Stage 3 — Two-column layout and the missing controls

Restructure both tabs onto the shared 340pt-rail / light-table grid.
Replace `mode_label` with a `ttk.Radiobutton` pair on the existing
`is_folder_mode` var. Add the live frame-count readout under the Split
ratio combobox and the live solved-layout name under the Compose one
(both read from existing geometry code). Add the `19921 × 6607 · 3.01:1`
readout, which means reading the image header on selection — do it with
`Image.open` without `load()`, which is fast even on a 20k-pixel file, but
do it off the main thread to be safe.

Fixes hierarchy, alignment and the "empty box owns the window" problem in
one move, because the preview area now occupies the right column by design
rather than by leftover space.

**Risk:** medium. This is real widget surgery.

**Tests:** the real-Tk construction tests will need attention —
`test_split_tab_builds_under_a_notebook_page_with_working_previews` and
`test_compose_tab_builds_a_working_ratio_combobox_under_real_tk` construct
the widget tree and will need their widget lookups updated. Tests that
poke `app.mode_label` must be rewritten against the radio's variable. Add
a test that the frame-count readout matches `pipeline`'s actual output
count for each ratio — that's a genuinely valuable new test, not just
churn.

### Stage 4 — The contact strip

Replace `PreviewPanes` with a Canvas-based `ContactStrip`: one continuous
strip, shared rebate, frame numbers, per-frame stencils, and the unexposed
empty state. Raise `PREVIEW_MAX_PX` and size frames from the available
width rather than a constant. Wire per-frame progress into the strip
(requires adding a per-frame callback to `pipeline.process_image`, which
currently reports nothing during single-file runs).

This is the signature. It's also where the empty-box problem is finally
*solved* rather than mitigated, because the empty state becomes the most
characteristic image in the app.

**Risk:** medium-high. Canvas resize handling, `PhotoImage` reference
retention (the current code's `_images` list exists for exactly this
reason — keep that discipline), and a new pipeline callback.

**Tests:** `PreviewPanes` tests are replaced —
`test_preview_panes_show_images_displays_a_pil_image_directly`,
`test_preview_titles_match_output_paths_length`, and the preview half of
the split-tab construction test. Write equivalents against `ContactStrip`.
The new pipeline callback needs its own test in `test_pipeline.py`.
Expect this stage to touch the most test code of any stage.

### Stage 5 — The numbered negatives list

Replace `tk.Listbox` with the Canvas row list: numbered frames, filenames
in mono, dimensions, click and keyboard selection, and the disabled-state
logic from Stage 2 carried over. Add the tooltips.

Deliberately last: it's the most hand-written behaviour for the smallest
area of screen, and Stage 1's `clam` restyle will already have made the
Listbox far less jarring (`clam` lets you set its `background`,
`selectbackground` and `borderwidth`, which is most of the clash).

**Risk:** medium. Reimplementing selection is where bugs live.

**Tests:** `test_compose_tab_requires_two_or_three_images` and
`test_compose_tab_reordering_changes_the_order` operate on
`tab.images` and `tab._selection` rather than the Listbox itself, so they
should survive. `_refresh_list` and `_on_select` need new tests against the
Canvas list's selection model.

### Deliberately not in the plan

The rebate header as a Canvas tab bar. Stage 1 styles the `ttk.Notebook`
and Stage 3 puts a static drawn header beneath it carrying the filename.
That gets most of the visual idea while keeping keyboard tab navigation
and whatever accessibility Tk affords. Revisit only if the Notebook proves
unstylable under `clam` in practice.

### Stop-and-reassess point

After Stage 3, look at it. If the app now reads as designed and the
remaining gap is only the strip, Stage 4 is worth it. If Stages 1–3 fight
`clam` harder than expected — particularly if the Notebook or Combobox
refuse to restyle cleanly — that is the signal that the toolkit is the
binding constraint, and the Qt conversation should happen before Stage 4
rather than after.
