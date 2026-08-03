"""The light-table design system, as Qt draws it.

The concept is unchanged from the tkinter build: this app never asks you to
judge tone -- tone is fixed the moment the scan is made -- it asks you to
judge layout, so the chrome is a light table rather than the dark grey every
other photo tool inherits.

What changed is the execution, and both changes were needed.

`clam` built a combobox out of a bevelled arrow button welded to a bordered
box, and a button out of a hard 1px border. Recolouring never touched that
vocabulary. A stylesheet does.

And the old palette had no range: three greys within a few percent of each
other, no white and no dark surface, so everything sat in one narrow tonal
band and read as a wash. That was a design error, not a toolkit one. This
palette runs white to near-black.

Presentation only. Nothing here knows what a panorama is.
"""

from PySide6.QtGui import QColor, QFont, QFontDatabase

# --- Colour -----------------------------------------------------------------

TABLE = "#FBFCFD"
"""The light table itself. Window background."""

PANEL = "#EEF1F4"
"""The control rail, sitting just below the table."""

WELL = "#FFFFFF"
"""Input fields. A field you type into should be paper."""

EDGE = "#D5DBE0"
"""Hairlines and dividers -- one device pixel, which Qt can actually do."""

REBATE = "#15171A"
"""Film base: the header band and the strip."""

INK = "#14171A"
"""Primary text. 16.1:1 on the table."""

INK_DIM = "#5C646B"
"""Secondary text. 5.9:1 on the panel, so it clears AA at any size."""

CHINAGRAPH = "#C9302A"
"""The grease pencil an editor marks selects with.

The marking-up layer, and nothing else. A grease pencil numbers the frames,
rings the select, marks the one to print and crosses out the one that
failed -- so this colour carries the primary action, the current selection,
the numbering, the progress bar while a run is in flight, and errors.
Chrome stays greyscale: surfaces, fields, sliders, dividers and rules.

The primary action keeps its primacy under that rule because it is the only
large filled block of chinagraph here; everything else is a hairline, a
numeral or an indicator a few pixels across. A second saturated hue would
cost it that, and so would filling another large area with this one.
"""

CHINAGRAPH_HOVER = "#B62923"
CHINAGRAPH_DOWN = "#9E221D"

# --- Spacing ----------------------------------------------------------------
# One scale. Everything that belongs together is spaced the same way.

S = 6
M = 12
L = 24

FIELD_LABEL_WIDTH = 68
"""How wide the label column in a rail field is.

Fixed rather than measured, so every field in every section lines its
control up on the same edge -- a label column that shifted per section
would read as four separate forms rather than one rail.

Sized to the longest label the rail uses, which is short because the
section heading above it already carries the topic: BORDER's slider is
"Width", not "Border width". At 92 the labels said the heading twice and
pushed the controls 35px past the rail's edge."""
XL = 36

RAIL_WIDTH = 340
"""How wide the control rail is.

Was 320 when the rail did not scroll. The scrollbar costs 8px of usable
width and the label column costs the rest: at 320 the controls ran 11px
past the edge, which clipped the ratio combo and the Choose button."""
BAND_HEIGHT = 52

# --- Type -------------------------------------------------------------------
# Three roles. Anything the machine measured -- paths, pixel counts, ratios --
# is set in `data`, which separates "the file you chose" from "what we call
# it" at a glance.

_STENCIL_STACK = ("Avenir Next Condensed", "Helvetica Neue", "Inter", "Helvetica")
_BODY_STACK = ("Avenir Next", "Inter", "Helvetica Neue", "Helvetica")
_DATA_STACK = ("SF Mono", "Menlo", "Courier New")


def _first_installed(stack: tuple[str, ...]) -> str:
    families = set(QFontDatabase.families())
    for name in stack:
        if name in families:
            return name
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()


def body_family() -> str:
    return _first_installed(_BODY_STACK)


def data_family() -> str:
    return _first_installed(_DATA_STACK)


def stencil_family() -> str:
    return _first_installed(_STENCIL_STACK)


def stencil_font(size: int = 11, tracking: float = 2.2) -> QFont:
    """Condensed caps with wide tracking, the way a lab prints an edge.

    Letter-spacing was Canvas-only under tkinter -- one text item per glyph
    at a measured offset. Qt just does it.
    """
    font = QFont(stencil_family(), size)
    font.setWeight(QFont.Weight.DemiBold)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking)
    font.setCapitalization(QFont.Capitalization.AllUppercase)
    return font


def data_font(size: int = 11) -> QFont:
    return QFont(data_family(), size)


def rgb(value: str) -> QColor:
    return QColor(value)


# --- Stylesheet -------------------------------------------------------------


def stylesheet() -> str:
    """One sheet for the whole app.

    Deliberately no rounded corners and no shadows anywhere, even though Qt
    makes both trivial. The direction is a light table and film rebate, and
    both are hard-edged. A toolkit removing a constraint is not a reason to
    spend it.
    """
    body = body_family()
    data = data_family()
    return f"""
    QWidget {{
        background: {TABLE};
        color: {INK};
        font-family: "{body}";
        font-size: 13px;
    }}

    #Rail {{
        background: {PANEL};
        border-right: 1px solid {EDGE};
    }}
    /* Layout containers carry no colour of their own; without this they
       inherit the global QWidget white and punch holes in the rail. */
    #Rail QWidget {{ background: transparent; }}
    #Rail QScrollArea {{ border: none; }}
    /* The rail scrolls when the window is shorter than the column. The bar
       is chrome, so it stays greyscale and hard-edged like every other
       hairline here -- chinagraph is for marking up, not for furniture. */
    #Rail QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0;
    }}
    #Rail QScrollBar::handle:vertical {{
        background: {EDGE};
        min-height: 32px;
    }}
    #Rail QScrollBar::add-line:vertical, #Rail QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    #Rail QScrollBar::add-page:vertical, #Rail QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    #Rail QLineEdit, #Rail QComboBox {{ background: {WELL}; }}
    #Rail QPushButton {{ background: {WELL}; }}
    #Rail QPushButton#Primary {{ background: {CHINAGRAPH}; }}
    #Rail QPushButton#Secondary {{ background: transparent; }}
    #Table {{ background: {TABLE}; }}

    QLabel {{ background: transparent; }}
    /* Names the control beside it. Quieter than body ink, because the
       control is the thing being looked at, not its name. */
    QLabel#FieldLabel {{ color: {INK_DIM}; }}
    QLabel#Section {{
        color: {INK_DIM};
        font-family: "{body}";
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 1.1px;
    }}
    QLabel#Help {{ color: {INK_DIM}; font-size: 12px; }}
    QLabel#Data {{ color: {INK_DIM}; font-family: "{data}"; font-size: 11px; }}
    QLabel#Error {{ color: {CHINAGRAPH}; font-size: 12px; }}

    QLineEdit {{
        background: {WELL};
        border: 1px solid {EDGE};
        padding: 7px 9px;
        font-family: "{data}";
        font-size: 12px;
        selection-background-color: {CHINAGRAPH};
        selection-color: {WELL};
    }}
    QLineEdit:focus {{ border: 1px solid {INK}; }}
    QLineEdit:disabled {{ background: {PANEL}; color: {INK_DIM}; }}

    /* A percentage is judged by eye, so it is set by dragging. The groove
       is a hairline like every other rule here and the handle is a plain
       ink block -- no radius, no bevel, no gradient, which is most of what
       a stock slider is made of.

       Not chinagraph: a slider is chrome, not a mark on the sheet, and a
       filled groove is a large enough area to compete with the primary
       action for salience. So focus is INK too, shown as
       a border on the widget rather than on the handle -- the transparent
       border is always there so nothing shifts when it lights up.

       Every rule here names a sub-control explicitly. Styling a slider at
       all makes Qt draw it from these rules instead of the native style,
       and a groove or handle left undescribed disappears. */
    QSlider {{
        background: transparent;
        border: 1px solid transparent;
        min-height: 24px;
    }}
    QSlider:focus {{ border: 1px solid {INK}; }}
    QSlider::groove:horizontal {{
        background: {EDGE};
        border: none;
        height: 1px;
        margin: 0 5px;
    }}
    QSlider::sub-page:horizontal {{
        background: {INK};
        border: none;
        height: 1px;
        margin: 0 0 0 5px;
    }}
    QSlider::handle:horizontal {{
        background: {INK};
        border: none;
        width: 10px;
        margin: -8px 0;
    }}
    QSlider::handle:horizontal:disabled {{ background: {EDGE}; }}
    QSlider::sub-page:horizontal:disabled {{ background: {EDGE}; }}

    /* A block of the colour it sets, so the border is the only chrome it
       carries. Focus is INK like every other field here: a control turning
       chinagraph when you click into it would read as an error. The ring
       thickens rather than changing hue, so it survives a swatch set to a
       colour close to INK itself. */
    #Swatch {{
        border: 1px solid {EDGE};
        min-width: 34px;
        min-height: 24px;
        padding: 0;
    }}
    #Swatch:hover {{ border-color: {INK_DIM}; }}
    #Swatch:focus {{ border: 2px solid {INK}; }}

    QPushButton {{
        background: {WELL};
        border: 1px solid {EDGE};
        padding: 7px 14px;
        color: {INK};
    }}
    QPushButton:hover {{ background: {PANEL}; }}
    QPushButton:pressed {{ background: {EDGE}; }}
    QPushButton:disabled {{ background: {PANEL}; color: #9AA2A9; border-color: {EDGE}; }}

    QPushButton#Primary {{
        background: {CHINAGRAPH};
        border: 1px solid {CHINAGRAPH};
        color: #FFFFFF;
        padding: 10px 16px;
        font-size: 14px;
    }}
    QPushButton#Primary:hover {{
        background: {CHINAGRAPH_HOVER};
        border-color: {CHINAGRAPH_HOVER};
    }}
    QPushButton#Primary:pressed {{
        background: {CHINAGRAPH_DOWN};
        border-color: {CHINAGRAPH_DOWN};
    }}
    QPushButton#Primary:disabled {{
        background: {EDGE};
        border-color: {EDGE};
        color: #FFFFFF;
    }}

    /* Free and reversible, so it must not read as a peer of the action
       that writes to disk -- but it is still a button, and styled as bare
       text it read as a caption hanging off the primary rather than as
       something to press. It keeps the outline and loses the fill. */
    QPushButton#Secondary {{
        background: transparent;
        border: 1px solid {EDGE};
        color: {INK};
        padding: 8px 14px;
    }}
    QPushButton#Secondary:hover {{ background: {WELL}; border-color: {INK_DIM}; }}
    QPushButton#Secondary:pressed {{ background: {PANEL}; }}
    QPushButton#Secondary:disabled {{ color: #9AA2A9; border-color: {EDGE}; }}

    /* The element that gave the old build away: ttk welded a bevelled
       arrow button onto a bordered box. Here the field is flat and the
       arrow is drawn by us, small and quiet. */
    QComboBox {{
        background: {WELL};
        border: 1px solid {EDGE};
        padding: 7px 9px;
        color: {INK};
    }}
    QComboBox:focus {{ border: 1px solid {INK}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox QAbstractItemView {{
        background: {WELL};
        border: 1px solid {EDGE};
        selection-background-color: {CHINAGRAPH};
        selection-color: #FFFFFF;
        outline: none;
        padding: 2px;
    }}

    /* The stock indicator is macOS system blue -- which was the original
       audit's complaint that the only saturated pixels in the app belonged
       to the least important controls. The selected state is chinagraph,
       like every other "this one" mark here. */
    QRadioButton {{ background: transparent; spacing: 8px; }}
    QRadioButton::indicator {{
        width: 13px;
        height: 13px;
        border: 1px solid #B9C1C8;
        border-radius: 7px;
        background: {WELL};
    }}
    QRadioButton::indicator:hover {{ border-color: {INK_DIM}; }}
    /* A thin border keeps the radius; a thick one squares the corners off,
       because Qt draws the radius on the outer edge only. */
    QRadioButton::indicator:checked {{
        border: 1px solid {CHINAGRAPH};
        background: {CHINAGRAPH};
    }}

    /* The same argument as the radio above, and it had been missed: an
       unstyled QCheckBox draws the stock macOS tick in system blue, which
       is a second saturated hue in an interface that spends exactly one.
       Square, because a checkbox is not a radio -- the shape is what says
       which of the two you are looking at. */
    QCheckBox {{ background: transparent; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 13px;
        height: 13px;
        border: 1px solid #B9C1C8;
        background: {WELL};
    }}
    QCheckBox::indicator:hover {{ border-color: {INK_DIM}; }}
    QCheckBox::indicator:checked {{
        border: 1px solid {CHINAGRAPH};
        background: {CHINAGRAPH};
    }}
    QCheckBox::indicator:disabled {{ border-color: {EDGE}; background: {PANEL}; }}
    QCheckBox:disabled {{ color: #9AA2A9; }}

    QProgressBar {{
        background: {EDGE};
        border: none;
        height: 3px;
        text-align: center;
    }}
    QProgressBar::chunk {{ background: {CHINAGRAPH}; }}

    QTabWidget::pane {{ border: none; background: {TABLE}; }}
    QTabBar {{ background: {REBATE}; qproperty-drawBase: 0; }}
    QTabBar::tab:first {{ margin-left: {L}px; }}
    QTabBar::tab {{
        background: transparent;
        color: #7E868D;
        padding: 9px 18px;
        margin-right: 2px;
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.8px;
    }}
    QTabBar::tab:selected {{ color: #FFFFFF; }}
    QTabBar::tab:hover:!selected {{ color: #B9C0C6; }}

    QToolTip {{
        background: {REBATE};
        color: {TABLE};
        border: none;
        padding: 5px 8px;
        font-size: 12px;
    }}
    """
