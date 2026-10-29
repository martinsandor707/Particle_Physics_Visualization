/* §2.1 Coordinate reference frames and SE(3) co-registration.
 * Content model and rules: data/dev/design/methodology/brief.md.
 *
 * Sources: calosrv/grid/frame.py (all of it), grid/lattice.py, grid/slab.py,
 * query/canonical.py, query/shower_frames.py, query/frame_sql.py,
 * query/window.py, query/window_axis.py, query/ensemble.py, query/summary.py,
 * stats/circular.py; static/js/frame_views.js (anchorExplainer),
 * static/js/labels.js (FRAME_TREE); CLAUDE.md §2 ("Never Average a Circular
 * Quantity", "Outlier Clipping" and its recorded exceptions) and §5; README
 * "Reference frames", "Separation-Aligned (D-Frame)", "Per-shower frames",
 * "Direction overlays", "The z convention". Measured figures are quoted with
 * the file they were measured on. */

import { C } from '../constants.js';

// Constants this section quotes that constants.js does not hold yet.
const LOCAL = {
  SLAB_MM: 120, // TODO(constants): calosrv.grid.slab:DEFAULT_SLAB_MM
  FADE_P: 0.05, // TODO(constants): calosrv.query.ensemble:FADE_P
  COORDINATE_TOLERANCE_MM: 0.01, // TODO(constants): calosrv.query.shower_frames:COORDINATE_TOLERANCE_MM
};

const BT = '`';
/** A code span in the article's inline syntax. */
const code = (s) => `${BT}${s}${BT}`;
/** The depth of the last layer below the first: the back face of the co-registered depth axis. */
const BACK_FACE_MM = ((C.N_LAYERS - 1) * C.Z_PITCH_MM).toFixed(1);
/** The robust window floor: two footprints of the wider cell side, snapped up to whole bins. */
const ROBUST_FLOOR_MM = Math.ceil((C.WINDOW_FLOOR_FOOTPRINTS * Math.max(C.CELL_X_MM, C.CELL_Y_MM)) / C.CANONICAL_PITCH_MM - 1e-9)
  * C.CANONICAL_PITCH_MM;

export default {
  id: 'sec-frames',
  title: 'Coordinate reference frames and SE(3) co-registration',
  blocks: [
    { kind: 'p', text: String.raw`Every hit is recorded in the detector's own coordinates, but most questions a reader brings to an ensemble of showers concern relative positions: where the energy of one shower sits with respect to the other, and which way the showers of a selection lean. The dashboard therefore offers four reference frames ([[tab-frames]]). Each is a rigid motion of the detector coordinates, applied per event or per shower, and each states what may be averaged in it. The governing rule (CLAUDE.md §2, "Never Average a Circular Quantity") is that a direction or a position is averaged only where a measurement shows the ensemble to share one, and that the measurement is printed beside the mark it licenses.` },
    { kind: 'table', id: 'tab-frames',
      caption: String.raw`The four reference frames. The interface labels follow ${code('static/js/labels.js')} ${code('FRAME_TREE')}; the API key is the flat value stored in the URL hash and the admin default. "Splat" is how a hit's energy reaches the accumulation grid ([[sec-discretisation]]).`,
      head: ['Frame (interface label)', 'API key', 'Origin', 'Rotation', 'Splat', 'Depth axis', 'Ensemble direction'],
      rows: [
        [String.raw`Absolute (detector coordinates)`, code('lab'), String.raw`detector origin`, String.raw`none`,
          String.raw`one bin per cell; Continuous Field: area-weighted overlap ([[eq-splat]])`,
          String.raw`raw $z$, ${C.N_LAYERS} native layers`,
          String.raw`trajectories for $N \le ${C.MAX_TRAJECTORY_EVENTS}$, else $\bar R$ stated; windowed axis when zoomed`],
        [String.raw`Separation-Aligned (D-Frame) › Translated`, code('canonical'), String.raw`entry midpoint $\mathbf m$ at $z_{\mathrm f}$ ([[eq-dframe-params]])`,
          String.raw`$\mathbf R_z(\psi)$ per event`, String.raw`$k \times k$ rotated sub-deposits, $k \ge ${C.MIN_SUBSAMPLE}$`,
          String.raw`$z' = z - z_{\mathrm f}$, native layers`,
          String.raw`two ensemble axes with SD band and Student-t envelope; faded when $P_{\mathrm{Ray}} > ${LOCAL.FADE_P}$`],
        [String.raw`Separation-Aligned (D-Frame) › Local (shower-fixed)`, code('local'), String.raw`each shower's $P_0$`,
          String.raw`$\mathbf R(\theta,\varphi)$ per shower`, String.raw`$k \times k \times k_z$ rotated sub-deposits, $k_z = ${C.LOCAL_K_Z}$`,
          String.raw`$w$, uniform bins at the layer pitch`, String.raw`none: every direction is $+w$`],
        [String.raw`Per-shower translated (legacy)`, code('trans'), String.raw`each shower's $P_0$`, String.raw`none`,
          String.raw`exact area-weighted box overlap ([[eq-box-moments]])`,
          String.raw`$\Delta z$, the shower's own layers from its first`,
          String.raw`trajectories from the origin for $N \le ${C.MAX_TRAJECTORY_EVENTS}$, else $\bar R$ stated`],
      ],
      note: String.raw`The legacy frame has no radio of its own: a ${code('#frame=trans')} link or a saved default opens it and reveals a hidden sub-option while it is active. In every frame $D$ is the Absolute-frame 3-D centroid distance ([[eq-separation]]).` },
  ],
  sections: [
    {
      id: 'sec-frames-detector',
      title: 'Detector coordinates and the depth convention',
      blocks: [
        { kind: 'p', text: String.raw`The Absolute coordinates $x, y, z$ are the detector's, in millimetres, with $z$ the raw longitudinal depth. Both hit schemas share one lattice, whose layers are exactly uniform:` },
        { kind: 'eq', id: 'eq-zlattice', tex: String.raw`z_k = ${C.FIRST_LAYER_Z_MM} + ${C.Z_PITCH_MM}\,(k - 1)\,\mathrm{mm}, \qquad k = 1, \ldots, ${C.N_LAYERS}, \qquad z_{\mathrm f} \equiv z_1` },
        { kind: 'p', text: String.raw`The front face $z_{\mathrm f}$ is the plane of the first layer, a fixed piece of hardware rather than a per-event minimum (${code('grid/slab.py')}); the entry panels show the energy of a ${LOCAL.SLAB_MM} mm slab behind it. Every file, the Parquet archive and every derived table keep raw $z$ (README "The z convention"): measured on the production file, raw $z$ reproduces all 17 absolute-frame features of the producer's aggregate to $\le 10^{-11}$, while the shifted depth disagrees in every event. The offset ${code('CORE_SHIFT_Z_MM')} $= ${C.CORE_SHIFT_Z_MM}$ mm (${code('db/ddl.py')}) is therefore a display label only: where a card quotes depth below the front face it writes $z_{\mathrm{disp}} = z - ${C.CORE_SHIFT_Z_MM}\,\mathrm{mm}$ and says so, while volumes, densities and centroids stay raw. In the per-shower frames, depth zero is each shower's own first populated layer.` },
        { kind: 'p', text: String.raw`A hit $h$ has position $\mathbf p_h$ and deposited energy $E_h$. Each shower $j \in \{A, B\}$ carries its incident polar and azimuthal angles $\theta_j, \varphi_j$, whose unit direction points into the calorimeter,` },
        { kind: 'eq', id: 'eq-direction', tex: String.raw`\hat{\mathbf n}(\theta,\varphi) = (\sin\theta\cos\varphi,\ \sin\theta\sin\varphi,\ \cos\theta)^{\top}` },
        { kind: 'p', text: String.raw`and its energy-weighted 3-D centroid $\mathbf c_j$ over all of its cells (the file's ${code('centroid_A/B_x, _y, _z')}; a cell labelled ${code('A+B')} counts with shower B). The separation $D$ that the global slider filters on is the distance between the two centroids,` },
        { kind: 'eq', id: 'eq-separation', tex: String.raw`D = \lVert \mathbf c_A - \mathbf c_B \rVert, \qquad \mathbf c_j = \frac{\sum_{h \in j} E_h\,\mathbf p_h}{\sum_{h \in j} E_h}` },
        { kind: 'p', text: String.raw`and it is this quantity, ${code('centroid_AB_distance')}, in every frame. The centroids sit a median 253 mm behind the front face on the production file (${code('grid/frame.py')}), so $D$ is a 3-D distance between shower bodies, not a separation of entry points. The file's ${code('centroid_AB_distance_trans')} and ${code('_local')} compare two centroids each expressed relative to its own shower's entry point; they are offsets between two different frames and are never presented as a separation.` },
      ],
    },
    {
      id: 'sec-frames-absolute',
      title: 'The Absolute (detector) frame',
      blocks: [
        { kind: 'p', text: String.raw`The Absolute frame (API ${code('lab')}, the cold-boot default) draws the measured lattice as it is: the entrance slab in $x, y$ and the full depth in $y, z$ and $x, z$, one bin per cell ([[sec-discretisation]]). It is the only frame in which the separation vector between the two centroids is drawn, because it is the only one in which both centroids keep their detector positions.` },
        { kind: 'p', text: String.raw`What this frame cannot draw is an averaged direction. The incident azimuth wraps, and its mean resultant length ([[eq-resultant]]) measured on the production file is $\bar R = 0.012$ over the full dataset, 0.042 for a 122-event momentum window and only 0.178 for 7 events (${code('query/summary.py')}, ${code('angular_coherence')}). The direction is near-uniform at every selection size the filters can reach, so an "average trajectory" would point somewhere arbitrary while looking authoritative [[cite:mardia2000]]. For $N \le ${C.MAX_TRAJECTORY_EVENTS}$ selected events the depth panels draw each event's own trajectory, projected from its centroid along $\hat{\mathbf n}$; above that they state $\bar R$ and draw the per-layer energy-weighted centroid of the summed deposit, named *centre of deposited energy*: a property of the summed picture, never a direction.` },
        { kind: 'p', text: String.raw`The azimuth is uniform over the face, but it is not random. Measured on the production event table, every shower's incident direction points back at the detector origin (${code('summary.pointing')}, reported on every Absolute and D-frame response):` },
        { kind: 'eq', id: 'eq-pointing', tex: String.raw`\begin{aligned} \varepsilon_j &= \operatorname{atan2}\big(\sin(\varphi_j - \alpha_j),\ \cos(\varphi_j - \alpha_j)\big), \qquad \alpha_j = \operatorname{atan2}(c_{j,y},\ c_{j,x}) \\ z^{\star}_j &= \frac{\sqrt{c_{j,x}^2 + c_{j,y}^2}}{\tan\theta_j} \approx c_{j,z} \end{aligned}` },
        { kind: 'p', text: String.raw`The residual $\varepsilon_j$ between a shower's azimuth and the azimuth $\alpha_j$ of its own centroid has a resultant length of 1.000 and an SD of 1.8°, and the median $z^{\star}$ is 3,860 mm against a median centroid depth of 3,892 mm. The azimuth is uniform only because the entry positions are; conditioned on position it is nearly deterministic. That licenses a recorded exception (${code('query/window_axis.py')}): when a depth panel is zoomed to a transverse window narrower than the detector, the service draws the mean trajectory of the selected events whose back-projected entry point ([[eq-backproject]]) lies in the window. With $\beta_i$ the projected slope of event $i$ ($\tan\theta_i\cos\varphi_i$ on the $x, z$ panel, $\tan\theta_i\sin\varphi_i$ on the $y, z$ panel) and $\xi_i$ its entry coordinate,` },
        { kind: 'eq', id: 'eq-window-axis', tex: String.raw`\begin{aligned} \bar\xi + \bar\beta\,(z - z_{\mathrm f}) &\pm \sqrt{\operatorname{Var}\xi + 2\,(z - z_{\mathrm f})\operatorname{Cov}(\xi, \beta) + (z - z_{\mathrm f})^2\operatorname{Var}\beta} \\ \text{drawn in full} &\iff \lvert\bar\beta\rvert \ge ${C.LEAN_RATIO_MIN}\cdot\operatorname{SD}(\beta) \end{aligned}` },
        { kind: 'p', text: String.raw`The square root, with sample variances and covariance (ddof = 1), is the SD of the per-event trajectories at each depth, drawn as an uncapped band; the Student-t 95% interval of the mean, the same band times $t_{0.975,N-1}/\sqrt N$ ([[eq-t-interval]]), is drawn as a thin envelope. They are two marks for two quantities, each named in its tooltip. Measured on production in ${C.WINDOW_AXIS_MM} mm windows of the entry position, 262 windows hold 20 events or more; their median azimuth resultant is 0.999 and the mean lean over the depth is 346 mm against a 33 mm dispersion band. The gate is the lean against the fan, not a Rayleigh test: a depth panel's window is a strip across the whole face, and for a strip through $y = 0$ the azimuth flips between 0 and $\pi$ while every projected slope stays the same, so the Rayleigh $p$ is reported but does not decide. An axis that fails the gate is drawn faded with the reason stated. One event gets its own trajectory labelled as such, two get a band labelled with one degree of freedom, fewer than ${C.PROVISIONAL_N} are labelled weak ([[tab-low-n]]), and at full extent nothing of the kind is drawn.` },
        { kind: 'links', id: 'lnk-frames-absolute', items: [
          { page: 'physics', panel: 'xy', set: { frame: 'lab' }, label: 'XY entry panel, Absolute frame' },
        ] },
      ],
    },
    {
      id: 'sec-frames-motion',
      title: 'Rigid co-registration',
      blocks: [
        { kind: 'p', text: String.raw`Every co-registered view of the service is one rigid motion per event or per shower, an element of SE(3) that takes an anchor $\mathbf a$ to the origin:` },
        { kind: 'eq', id: 'eq-se3', tex: String.raw`\mathbf p' = \mathbf R\,(\mathbf p - \mathbf a), \qquad \mathbf R^{\top}\mathbf R = \mathbf I,\ \det\mathbf R = 1 \quad\Rightarrow\quad \lVert \mathbf p'_1 - \mathbf p'_2 \rVert = \lVert \mathbf p_1 - \mathbf p_2 \rVert` },
        { kind: 'p', text: String.raw`Because the motion preserves distances, transverse widths and longitudinal profiles exactly, the energy of different events placed by it can be added bin by bin, and an ensemble picture means what a single event's picture means. The three instantiations below are built from one object (${code('Se3')} in ${code('grid/frame.py')}: ${code('per_event_canonical')}, ${code('per_shower_translated')}, ${code('per_shower_local')}). The accumulation scans run inside DuckDB, so ${code('query/frame_sql.py')} emits the same nine rotation entries and three anchor coordinates as SQL, once, for every scan; a test pins the SQL to the NumPy definition on the fixture.` },
      ],
    },
    {
      id: 'sec-frames-dframe',
      title: 'The Separation-Aligned (D-Frame)',
      blocks: [
        { kind: 'p', text: String.raw`The D-frame (interface *Separation-Aligned (D-Frame) › Translated*, API ${code('canonical')}) co-registers each *event* so that its two showers sit where every other event's do. It needs one entry point per shower on the front face, and the file records none, so the service offers two stated definitions. The default back-projects the 3-D centroid along the shower's own incident direction:` },
        { kind: 'eq', id: 'eq-backproject', tex: String.raw`\mathbf e_j = (c_{j,x},\ c_{j,y}) - (c_{j,z} - z_{\mathrm f})\tan\theta_j\,(\cos\varphi_j,\ \sin\varphi_j), \qquad j \in \{A, B\}` },
        { kind: 'p', text: String.raw`The sign is fixed by the data, not by convention: on the production file this lands a median 82 mm (A) and 69 mm (B) from the per-event energy-weighted entrance-slab centroid, and the opposite sign 181 mm (README). The alternative, the reference notebook's origin, starts from the shower's first-layer entry point $P_0 = (\bar x_0, \bar y_0, z_0)$, the energy-weighted transverse centroid of the cells of its first populated layer $L_0$, at that layer's depth (a cell labelled ${code('A+B')} counts for both showers), and slides it the short distance to the face:` },
        { kind: 'eq', id: 'eq-p0-anchor', tex: String.raw`\mathbf e_j = (\bar x_{0,j},\ \bar y_{0,j}) - (z_{0,j} - z_{\mathrm f})\tan\theta_j\,(\cos\varphi_j,\ \sin\varphi_j), \qquad (\bar x_0, \bar y_0) = \frac{\sum_{h \in L_0} E_h\,(x_h, y_h)}{\sum_{h \in L_0} E_h}` },
        { kind: 'p', text: String.raw`The first uses every cell of the shower but carries any sideways offset of its energy over the long extrapolation; the second needs almost no extrapolation but rests on one layer's cells. Measured on the production file the two land a median 46.5 mm (A) and 45.2 mm (B) apart at the face, 90th percentile 133.5 and 132.6 mm, with 9,620 and 9,382 of 20,268 showers more than one cell footprint apart. With no true entry point to check against, that distance is the size of the ambiguity, not the error of either; it is measured on every D-frame response and printed in the entry panel's Details drawer (${code('frame_views.js')}, ${code('anchorExplainer')}), and the choice travels in the link (${code('anchor=p0')}). From the two entry points the frame takes the midpoint, the A→B azimuth and the entry separation,` },
        { kind: 'eq', id: 'eq-dframe-params', tex: String.raw`\mathbf m = \tfrac{1}{2}(\mathbf e_A + \mathbf e_B), \qquad \psi = \operatorname{atan2}(e_{B,y} - e_{A,y},\ e_{B,x} - e_{A,x}), \qquad D_{\mathrm{entry}} = \lVert \mathbf e_B - \mathbf e_A \rVert` },
        { kind: 'p', text: String.raw`and moves every hit of the event by the passive rotation about the detector axis that turns the A→B line onto $+x'$, after translating the midpoint on the front face to the origin:` },
        { kind: 'eq', id: 'eq-dframe-rotation', tex: String.raw`\begin{pmatrix} x' \\ y' \\ z' \end{pmatrix} = \mathbf R_z(\psi) \begin{pmatrix} x - m_x \\ y - m_y \\ z - z_{\mathrm f} \end{pmatrix}, \qquad \mathbf R_z(\psi) = \begin{pmatrix} \cos\psi & \sin\psi & 0 \\ -\sin\psi & \cos\psi & 0 \\ 0 & 0 & 1 \end{pmatrix}` },
        { kind: 'p', text: String.raw`Shower A then sits at $(-D_{\mathrm{entry}}/2, 0)$ and B at $(+D_{\mathrm{entry}}/2, 0)$, and directions transform by $\mathbf R_z(\psi)$ alone. $\mathbf R_z(\psi)$ is the Local rotation ([[eq-local-rotation]]) at $\theta = 0$ with $\psi$ in place of $\varphi$. The entry panel writes its horizontal axis as $D$, the signed $x'$ coordinate along the separation with the anchors at $D = \mp\langle D_{\mathrm{entry}}\rangle/2$ and tick values in millimetres; the depth panels keep $x', y', z'$, with the back face at $z' = ${BACK_FACE_MM}$ mm. $D_{\mathrm{entry}}$ is not $D$: over the full production file $\langle D_{\mathrm{entry}}\rangle = 757$ mm against $\langle D\rangle = 842$ mm, differing by up to 726 mm in one event, so both are printed side by side, the mean $D_{\mathrm{entry}}$ with its Student-t 95% interval. Events with no shower-A centroid have no frame; they are excluded from $N$ and counted.` },
        { kind: 'figure', id: 'fig-se3', exhibit: 'se3', caption: String.raw`Schematic of the D-frame co-registration of two events, not drawn from data. Left: each event in Absolute coordinates, with its entry points $\mathbf e_A$ and $\mathbf e_B$ on the front face, their midpoint $\mathbf m$ and the azimuth $\psi$ of the A→B line ([[eq-dframe-params]]). Right: both events after the motion of [[eq-dframe-rotation]], superimposed, with every midpoint at the origin, every A at $x' = -D_{\mathrm{entry}}/2$ and every B at $x' = +D_{\mathrm{entry}}/2$. Equal scales on both axes.` },
        { kind: 'p', text: String.raw`When the two entry points lie closer than ${C.ILL_CONDITIONED_D_MM} mm, $\psi$ is dominated by the anchor residual and is effectively random (${code('ILL_CONDITIONED_D_MM')}). On the production file this is 32.3% of all events. It is harmless to the ensemble density, which those events enter averaged over azimuth, but their directions enter the axis statistics below as noise; the entry panel's drawer counts them.` },
        { kind: 'p', text: String.raw`**The sanctioned averaged direction.** After the motion the directions can become coherent, and this is the one place the Absolute-frame prohibition admits an averaged axis (CLAUDE.md §2). Per shower the service computes the per-event projected slopes $\beta' = u'_t/u'_z$ of the rotated direction for each depth panel, and the transverse mean resultant length $\bar R'$ of the unit vectors $(u'_x, u'_y)/\lVert(u'_x, u'_y)\rVert$ with its Rayleigh $P_{\mathrm{Ray}} = \exp(-N\bar R'^2)$ [[cite:rayleigh1880]] (${code('query/canonical.py')}, ${code('stats/circular.py')}). Each depth panel then draws two dashed axes from $(\mp\langle D_{\mathrm{entry}}\rangle/2, 0)$ along the mean slope, each with two separate marks (${code('query/ensemble.py')}): a shaded, uncapped wedge for the sample SD of the slopes (where individual showers go) and a thin envelope for the Student-t 95% interval of the mean slope (how well the axis is known). $\bar R'$, $P_{\mathrm{Ray}}$ and $N$ are printed beside each axis, and an axis with $P_{\mathrm{Ray}} > ${LOCAL.FADE_P}$ is drawn faded, never hidden. The license is the measurement, repeated on every response: on the production file $\bar R'_A / \bar R'_B$ is 0.779 / 0.819 for $D$ = 2700–3000 mm ($N = 500$) and 0.123 / 0.125 for $D$ = 20–40 mm ($N = 950$, every event below the ill-conditioning threshold, still $P_{\mathrm{Ray}} \approx 5 \times 10^{-7}$), against 0.012 in the Absolute frame. One event gets its own two incident lines labelled *single event, not an ensemble*, with no band and $\bar R'$ undefined; two events get the band labelled with one degree of freedom; below ${C.PROVISIONAL_N} the coherence is labelled weak and the fitted ranges provisional ([[tab-low-n]]). Part of each band is geometry rather than physics: because directions point at the detector origin ([[eq-pointing]]), a shower's lean grows with its radius, so the band mixes the spread of entry radii with anything physical, and the depth panels' drawers say so.` },
        { kind: 'links', id: 'lnk-frames-dframe', items: [
          { page: 'physics', panel: 'xy', set: { frame: 'canonical' }, label: 'D–Y′ entry panel, D-frame' },
          { page: 'physics', panel: 'yz', set: { frame: 'canonical' }, label: 'Y′Z′ depth panel with the ensemble axes' },
        ] },
      ],
    },
    {
      id: 'sec-frames-pershower',
      title: 'Per-shower frames: Local and the legacy translated frame',
      blocks: [
        { kind: 'p', text: String.raw`Two frames co-register each *shower* on its own entry point $P_0$, so the two showers of every event are superimposed at the origin. The per-shower translated frame (legacy, API ${code('trans')}; never called plain "Translated", which names the D-frame) translates without rotating,` },
        { kind: 'eq', id: 'eq-trans', tex: String.raw`(\Delta x,\ \Delta y,\ \Delta z) = \mathbf p - P_0 = (x - \bar x_0,\ y - \bar y_0,\ z - z_0)` },
        { kind: 'p', text: String.raw`so its depth is the shower's own layers counted from its first. Local (shower-fixed, API ${code('local')}) then rotates by the shower's own incident direction, with the reference notebook's rotation:` },
        { kind: 'eq', id: 'eq-local-rotation', tex: String.raw`\begin{aligned} (u,\ v,\ w)^{\top} &= \mathbf R(\theta,\varphi)\,(\mathbf p - P_0), \qquad \mathbf R(\theta,\varphi) = \mathbf R_y(\theta)\,\mathbf R_z(\varphi) \\ \mathbf R(\theta,\varphi) &= \begin{pmatrix} \cos\theta\cos\varphi & \cos\theta\sin\varphi & -\sin\theta \\ -\sin\varphi & \cos\varphi & 0 \\ \sin\theta\cos\varphi & \sin\theta\sin\varphi & \cos\theta \end{pmatrix}, \qquad \mathbf R(\theta,\varphi)\,\hat{\mathbf n}(\theta,\varphi) = \hat{\mathbf e}_w \end{aligned}` },
        { kind: 'p', text: String.raw`$\mathbf R$ is orthonormal with determinant $+1$ for every argument, so its inverse is its transpose. Both frames are the input file's own ${code('*_trans')} and ${code('*_local')} coordinates, and every response also applies the motion itself to the lattice positions and reports the largest difference between the two over the selection against a ${LOCAL.COORDINATE_TOLERANCE_MM} mm tolerance (${code('query/shower_frames.py')}); on the production file it is 0.05 µm over 40,650 showers. Ingest separately verifies that $P_0$ *is* the first-layer energy-weighted centroid of [[eq-p0-anchor]].` },
        { kind: 'p', text: String.raw`Neither frame draws an ensemble direction. The per-shower translated frame keeps each shower's Absolute azimuth, still near-uniform ($\bar R = 0.012$), so it draws the individual incident directions from the origin for $N \le ${C.MAX_TRAJECTORY_EVENTS}$ events and otherwise states $\bar R$. In Local every incident direction is $+w$ by construction ([[eq-local-rotation]]), so an axis or a Rayleigh statistic would carry no information, and the panel says so. What does have a common centre in both frames is the per-event centroid offset from $P_0$: its mean is drawn with its sample SD as a faint uncapped cross and its Student-t 95% interval as capped whiskers, two separate marks, gated by the same low-N table. The A–B offset of the two superimposed ensemble centroids is labelled an *offset*: the separation stays $D$ of [[eq-separation]].` },
        { kind: 'links', id: 'lnk-frames-local', items: [
          { page: 'physics', panel: 'xz', set: { frame: 'local' }, label: 'uw depth panel, Local frame' },
          { page: 'models', panel: 'vox-ensemble', label: '3-D co-registered ensemble cloud' },
        ] },
      ],
    },
    {
      id: 'sec-frames-windows',
      title: 'Display windows of the co-registered frames',
      blocks: [
        { kind: 'p', text: String.raw`The accumulation grid of a co-registered frame must hold every hit of the selection and is therefore wide ([[sec-discretisation]]); what is drawn is a window of it. Outside these frames, every axis limit, histogram range and colour-scale bound defaults to the 1st–99th percentile of its data (CLAUDE.md §2, "Outlier Clipping for Readability"). The co-registered panels are a recorded exception: each transverse axis is cropped to a window symmetric about the origin, whose half-width $H$ covers the energy-weighted ${C.WINDOW_LOW_PERCENTILE}st–${C.WINDOW_HIGH_PERCENTILE}th percentile of that axis's energy marginal (${code('query/window.py')}, ${code('symmetric_axis')}):` },
        { kind: 'eq', id: 'eq-window', tex: String.raw`H = \min\Big( a\,\Big\lceil \tfrac{1}{a}\max\big(\lvert q_{${C.WINDOW_LOW_PERCENTILE}\%}\rvert,\ \lvert q_{${C.WINDOW_HIGH_PERCENTILE}\%}\rvert,\ H_{\min}(N)\big) \Big\rceil,\ H_{\mathrm{grid}} \Big), \qquad H_{\min}(N) = \begin{cases} ${C.SHOWER_RADIUS_MIN_MM}\,\mathrm{mm} & N < ${C.PROVISIONAL_N} \\ a\,\big\lceil ${C.WINDOW_FLOOR_FOOTPRINTS}\max(w_x, w_y)/a \big\rceil & N \ge ${C.PROVISIONAL_N} \end{cases}` },
        { kind: 'p', text: String.raw`Here $q_\alpha$ is the energy-weighted quantile, snapped outward to whole bins, $a = ${C.CANONICAL_PITCH_MM}$ mm the accumulation pitch, $w_x \times w_y = ${C.CELL_X_MM} \times ${C.CELL_Y_MM}$ mm the cell footprint and $H_{\mathrm{grid}}$ the grid's own half-width. The entry panel uses the slab energy along both axes; the depth panels use their own full-depth energy along their transverse axis, and depth is never cropped, because the longitudinal profile and the leakage into the back layers are what those panels show.` },
        { kind: 'p', text: String.raw`Three choices in [[eq-window]] are deliberate. *The percentiles.* These panels do not draw below $10^{-${C.RAMP_DECADES}}\,\rho_{\mathrm{ref}}$ ([[eq-relative-log]]). Measured on the production v37 file, a 1–99 crop cut the shower halo where it was still 15–110 times above that floor, leaving 14–99% of the entry panel's boundary bins above it, so the colour ended at the window edge and read as the edge of the shower; at ${C.WINDOW_LOW_PERCENTILE}–${C.WINDOW_HIGH_PERCENTILE} it is 2–11% of the boundary bins, with 0.12–0.33% of the entry panel's energy outside across seven selections from $N = 3$ to 20,143. The per-shower frames measure the same on the production ${code('hits_all_models')} file: 22–95% of the boundary bins above the floor at 1–99, 0–6.4% at ${C.WINDOW_LOW_PERCENTILE}–${C.WINDOW_HIGH_PERCENTILE}, with 0.15–0.31% of the energy outside. *The centring.* The origin is the midpoint of the two entry anchors, or every shower's own entry point, so a centred window keeps it in the middle of the panel. *The floor.* Below ${C.PROVISIONAL_N} events the range rests on weak evidence and is labelled provisional on the axis, and it is never narrower than ${C.SHOWER_RADIUS_MIN_MM} mm, the median single-shower $|y'|$ 98th percentile of the entrance slab, one shower's own extent. From ${C.PROVISIONAL_N} events the evidence sets the window, floored only at ${C.WINDOW_FLOOR_FOOTPRINTS} cell footprints (${ROBUST_FLOOR_MM} mm), the physical resolution: low-energy selections are genuinely narrower than one shower's 98th percentile (on production v37, $E_1, E_2 < 1$ GeV with $N = 468$ measures $y' \in \pm 80$ mm), and a fixed ${C.SHOWER_RADIUS_MIN_MM} mm floor would widen them for no statistical reason.` },
        { kind: 'p', text: String.raw`The disclosure duty is unchanged. The energy outside each panel's window is reported in its Details drawer, measured after display reconstruction because a kernel moves a little energy across the window edge in both directions, with the raw-grid figure beside it; it is excluded from the view but not from any statistic.` },
      ],
    },
    {
      id: 'sec-frames-single',
      title: 'Single-shower experiments',
      blocks: [
        { kind: 'p', text: String.raw`A single-shower experiment has one shower per event, stored under the shower-A names, and no A→B separation to align on. Its frame control is relabelled at run time (${code('labels.js')}, ${code('SINGLE_SHOWER_FRAME_LABELS')}): the aligned tier becomes "Shower-Aligned", each shower at its own entry point, and the per-shower frame of [[eq-trans]] is that kind's own "Translated" sub-option rather than a legacy one; Local keeps its name and its rotation. The D-frame's radio stays, disabled with the server's reason. The event-level aggregate carries no hits, so its feature explorer offers the Absolute, per-shower translated and Local frames of the producer's features, never the D-frame. No stored key is renamed: a link written for one kind means the same frame on another.` },
      ],
    },
  ],
};
