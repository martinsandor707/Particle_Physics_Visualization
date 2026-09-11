"""Physical, binning and presentation constants.

Every geometric number here was measured from the shipped dataset rather than
assumed; the comment on each records what the measurement was so a future reader
can re-derive it.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Detector geometry
# --------------------------------------------------------------------------

#: Longitudinal pitch between sampling layers. Measured: all 59 consecutive
#: gaps between the 60 unique ``z`` values are exactly 20.5 mm.
Z_PITCH_MM = 20.5

#: Number of sampling layers in the endcap stack (60 unique ``z`` values).
N_LAYERS = 60

#: Total instrumented depth, 59 pitches from the front face.
DEPTH_MM = (N_LAYERS - 1) * Z_PITCH_MM  # 1209.5 mm

# --------------------------------------------------------------------------
# Transverse display binning
# --------------------------------------------------------------------------
#
# The transverse lattice is staggered and NOT uniform. In ``y`` the spacing
# strictly alternates 48.6 / 52.4 mm, giving an exact 101.0 mm period holding
# two cells. In ``x`` cells sit in tight pairs ~4.4 mm apart with a group pitch
# alternating ~43.87 / ~48.27 mm, plus a handful of irregular module-boundary
# gaps.
#
# Binning finer than the cell size is therefore meaningless and actively
# harmful: it aliases against the lattice and produces a periodic empty-bin
# comb. This was verified directly on the shipped data by histogramming the
# recentred transverse coordinates. Central-region profiles:
#
#     12.5 mm bins -> 898, 222, 233, 1765, 2384, 288, 415, 2588   (comb)
#     25.0 mm bins -> 433, 808, 916, 1582, 1120, 1998, 2672, 3003 (comb)
#     50.5 mm bins -> 220, 279, 414, 659, 1071, 1739, 2687, 4695  (monotonic)
#
# 50.5 mm is half the exact ``y`` period and matches the mean ``x`` pair pitch
# (~50.47 mm), so it stays commensurate with the lattice instead of beating
# against it.
BIN_XY_MM = 50.5

#: Half-width of the transverse window, in bins. 16 * 50.5 = 808 mm, which is
#: the ``graphs.png`` window to within a bin. Measured: 99.3% of hits fall
#: inside +/-800 mm of the shower-local origin.
N_XY_HALF = 16
N_XY = 2 * N_XY_HALF  # 32 bins per transverse axis
XY_EXTENT_MM = N_XY_HALF * BIN_XY_MM  # 808.0 mm

#: Sentinel written into the packed index arrays for hits that fall outside the
#: transverse window. uint8 cannot hold a negative index, and clamping to the
#: edge would pile the tail onto the border bins.
OUTSIDE_WINDOW = 255

# --------------------------------------------------------------------------
# Energy reconstruction
# --------------------------------------------------------------------------

#: Lower clamp for the logarithmic colour scale, in GeV. Per-hit energies span
#: twelve orders of magnitude (9.9e-14 to 4.35e-2 GeV); without a floor, most of
#: the colour ramp is spent on cells around 0.1 meV that carry no physics.
COLOR_FLOOR_GEV = 1e-6

#: Histogram bin count for the reconstructed-energy panel. Transcribed from
#: ``plan-viz.ipynb`` cell 2 (``np.histogram(..., bins=120, ...)``).
ENERGY_BINS = 120

#: Separation bins, in mm. The notebook uses ``[0, 5, 10, 15, 20]`` in cm while
#: its coordinates are in mm; converted here. Unused until an overlap dataset is
#: supplied, but kept so the two code paths stay in step.
D_BINS_MM = (0.0, 50.0, 100.0, 150.0, 200.0)

# --------------------------------------------------------------------------
# Theme - CLAUDE.md section 2
# --------------------------------------------------------------------------

THEME = {
    "canvas": "#0d1117",
    "canvas_alt": "#161b22",
    "card": "#1c2128",
    "border": "#30363d",
    "text": "#e6edf3",
    "text_muted": "#8b949e",
    "accent": "#58a6ff",
    "warn": "#d29922",
    "shower_a": "#f778ba",
    "shower_b": "#58a6ff",
}

#: Panel title strings, kept together so the English-only rule is auditable in
#: one place (CLAUDE.md section 1).
PANEL_TITLES = {
    "xy": "XY Projection — Shower Entry (z′ = 0)",
    "yz": "YZ Projection — Longitudinal Evolution (x ≈ 0)",
    "xz": "XZ Projection — Lateral Profile (y ≈ 0)",
    "energy": "Reconstructed Energy Distribution",
}

DASHBOARD_TITLE = "Calorimeter Shower Reconstruction Diagnostic Interface"

BASELINE_WARNING = (
    "⚠ Model outputs absent from dataset — "
    "Operating in Ground-Truth Baseline Mode"
)
