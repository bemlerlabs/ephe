"""The one palette: the ink-ground tokens the terminal surface paints with.

Ten names, one value each. `ui/ephe.tcss` spells the same ten tokens in the
stylesheet language; the Python surface imports this module, so a colour is
written once and referenced everywhere else.
`tests/test_tui_black_forest.py` holds the two spellings equal and measures the
contrast ratios quoted below.

The values are the product's own palette: the brand in
`app/src/styles/globals.css` is red (``--color-brand`` hsl(7.46 78.6% 57.8%) =
#E8543F), so ACCENT here is that red and not a second brand colour.

State is read from a text colour plus the state's own label, not from colour
alone. There is exactly one tinted ground: the retired accent tint and error
tint measured 2.8 apart in dE2000, which is one colour written twice.
"""

from __future__ import annotations

# Ink ground.
GROUND = "#15120F"  # app and screen ground
PANEL = "#1D1917"  # raised surface: header, cards, status bar
TEXT = "#F2EFE8"  # primary text, 16.25:1 on GROUND
DIM = "#91877E"  # secondary text, 5.31:1 on GROUND
LINE = "#2E2926"  # borders and scrollbar track

# Signal.
ACCENT = "#E8543F"  # the product's brand red, 5.13:1 on GROUND
OK = "#5BAE90"  # connected and finished, 7.02:1 on GROUND
WARN = "#F6A328"  # context meter warning, 9.05:1 on GROUND
ERROR = "#F63B1E"  # failure, 4.94:1 on GROUND

# The one tinted ground: ACCENT at 18% over PANEL. Command mode stands on it
# while its completion hint names the state. The status bar stays on PANEL,
# because ACCENT (3.84:1) and ERROR (3.70:1) fall below the 4.5:1 text
# threshold on this tint and a state word has to stay readable.
STATE_GROUND = "#42241E"
