/* §2.3 Attribution channels and extensive conservation.
 *
 * Follows calosrv/query/planes.py (the nine planes and how each channel reads
 * them), query/density.py and query/panels.py (the co-registered and Absolute
 * renderers), db/ddl.py (RAW_CAMS), encode/quantize.py, encode/scale.py,
 * encode/topk.py and static/js/frame_views.js (CAM_NORMALISATION).
 * Content model and rules: data/dev/design/methodology/brief.md. */

import { C } from '../constants.js';

/* TeX and code spans in one string. String.raw keeps TeX's backslashes; an
 * escaped backtick becomes the plain one the renderer reads as a code span. */
const md = (strings, ...values) =>
  String.raw({ raw: strings.raw.map((s) => s.replaceAll('\\`', '`')) }, ...values);

// Derived from the codes, never typed: levels, steps and their relative size.
const CO_LEVELS = C.MAX_CODE - C.SIGNED_MIN_CODE;            // 253 levels from code 2
const SIGNED_LEVELS = C.SPLIT_CODE - C.SIGNED_MIN_CODE;      // 127 codes per sign
const SIGNED_STEPS = SIGNED_LEVELS - 1;                      // 126 steps between them
const NEG_TOP = C.SPLIT_CODE - 1;                            // 128 = −10^−decades
const pct = (decades, steps) => ((10 ** (decades / steps) - 1) * 100).toFixed(1);
const STEP_LAB = pct(C.LAB_DECADES, C.LEVELS);
const STEP_CO = pct(C.RAMP_DECADES, CO_LEVELS);
const STEP_SIGNED = pct(C.RAMP_DECADES, SIGNED_STEPS);
const FLOOR = `10^{-${C.RAMP_DECADES}}`;

export default {
  id: 'sec-attribution',
  title: 'Attribution channels and extensive conservation',
  blocks: [
    { kind: 'p', text: md`Every bin of a spatial panel reports one of five quantities, chosen by the display-channel control and computed from the selected hits that fall in it. Two of them are *means* over the bin's hits and three are *sums*, and the difference organises everything in this section. A mean is intensive: how strongly, on average, a network attends to the hits that land here, bounded by the values it averages and blind to how much of the shower is there. A sum is extensive: how much energy, or attention-weighted energy, lands here; it grows with the energy and the number of events, and it is what merging, resampling and smoothing must conserve. Writing $E_h$ for a hit's deposited energy and $\mathcal G_h$, $\mathcal S_h$ for its Grad-CAM [[cite:selvaraju2017]] and signed Shap-CAM [[cite:zheng2022]] values, the five channels are:` },
    { kind: 'list', ordered: false, items: [
      md`**Average Hit Density**, the ensemble density $\langle\rho\rangle$ of [[eq-density]]: the summed energy per cell in GeV in the Absolute (detector) frame, and $\sum E/(N\,\Delta A)$ in GeV mm⁻² per event in the co-registered frames.`,
      md`**Grad-CAM Model Attention**: the energy-weighted mean $\sum E\mathcal G/\sum E$ of the bin's hits, or on request the count-weighted mean $\sum\mathcal G/n$. Energy is the default weight because the sub-femto-GeV hits vastly outnumber the shower core, and a count-weighted map of them is nearly uniform and says nothing about where the energy went.`,
      md`**Energy-weighted Grad-CAM**: the sum $\sum E\,\mathcal G$, the attention carried by the deposited energy.`,
      md`**Shap-CAM Attribution**: the signed mean $\sum E\mathcal S/\sum E$ (or $\sum\mathcal S/n$), on $[-1, +1]$.`,
      md`**Energy-weighted Shap-CAM**: the signed sum $\sum E\,\mathcal S$, whose two signs are kept apart (below).`,
    ] },
    { kind: 'p', text: md`**Nine additive planes.** The service never stores a channel. Each scan sums, per native bin $b$ and for the selected network in the selected frame, nine plain sums over the bin's hits (\`query/planes.py\`), listed in [[tab-planes]]:` },
    { kind: 'eq', id: 'eq-planes', tex: String.raw`\begin{aligned}
P^{\mathrm e}_b &= \sum_{h\in b} E_h, & P^{\mathrm n}_b &= \sum_{h\in b} 1, & P^{\mathrm{fa}}_b &= \sum_{h\in b} E_h\,f_{A,h} \\
P^{\mathrm{eg}}_b &= \sum_{h\in b} E_h\,\mathcal G_h, & P^{\mathrm g}_b &= \sum_{h\in b}\mathcal G_h, & P^{\mathrm s}_b &= \sum_{h\in b}\mathcal S_h \\
P^{\mathrm{esp}}_b &= \sum_{h\in b} E_h\max(\mathcal S_h, 0), & P^{\mathrm{esn}}_b &= \sum_{h\in b} E_h\min(\mathcal S_h, 0)
\end{aligned}` },
    { kind: 'p', text: md`where $f_{A,h}$ is the segmentation network's voxel fraction of shower A, true or predicted (the planes \`efa_true\` and \`efa_pred\`). $f_A$ always comes from the frame's *segmentation* network, whatever network the CAM columns belong to: only segmentation predicts where the energy went. Because every plane is a plain sum, every plane resamples through the same conservative operators of [[sec-discretisation]], and a Bernoulli preview sample of the hits, served while a slider is dragged, estimates every one of them without bias after the same scale factor, the inverse of the sampling probability; such a payload is marked \`exact: false\`. A single-shower hit file carries no networks and its scans fill $P^{\mathrm e}$ and $P^{\mathrm n}$ only; the density channel is all it can serve. Each channel is then formed from the planes:` },
    { kind: 'eq', id: 'eq-channels', tex: String.raw`\begin{aligned}
\langle\rho\rangle_b &= \frac{P^{\mathrm e}_b}{N\,\Delta A_b}, & \bar{\mathcal G}_b &= \frac{P^{\mathrm{eg}}_b}{P^{\mathrm e}_b}, & \bar{\mathcal S}_b &= \frac{P^{\mathrm{esp}}_b + P^{\mathrm{esn}}_b}{P^{\mathrm e}_b} \\
(E\mathcal G)_b &= \frac{P^{\mathrm{eg}}_b}{N\,\Delta A_b}, & (E\mathcal S)_b &= \frac{P^{\mathrm{esp}}_b + P^{\mathrm{esn}}_b}{N\,\Delta A_b}
\end{aligned}` },
    { kind: 'p', text: md`with $P^{\mathrm g}/P^{\mathrm n}$ and $P^{\mathrm s}/P^{\mathrm n}$ for the count-weighted means. In the Absolute frame the extensive channels are the numerators themselves, in GeV per cell. The two means are reconstructed as normalised convolutions (\`reconstruct.apply_ratio\`): the same operator is applied to numerator and denominator before they are divided, so a displayed bin remains an energy-weighted mean of hits, a weighted mean of values in $[0, 1]$ or $[-1, +1]$ stays inside that range, and a constant attention field stays exactly constant. Resampling the mean itself would average averages and weight a source bin of dust as heavily as one in the core.` },
    { kind: 'table', id: 'tab-planes', caption: md`The nine measurement planes of every bundle (\`query/planes.py\` \`PLANES\`): what each sums over a bin's hits, and the channels and marks that read it.`,
      head: ['Plane', 'Sum over a bin’s hits', 'Read by'],
      rows: [
        [md`\`e\``, md`$E_h$`, md`$\langle\rho\rangle$; the energy weight of every mean`],
        [md`\`n\``, md`$1$`, md`count-weighted means; the hit share under a display mask`],
        [md`\`efa_true\``, md`$E_h\,f_{A,h}^{\mathrm{true}}$`, md`truth-voxel centroids, shower axes`],
        [md`\`efa_pred\``, md`$E_h\,f_{A,h}^{\mathrm{pred}}$`, md`predicted-voxel centroids`],
        [md`\`eg\``, md`$E_h\,\mathcal G_h$`, md`Grad-CAM mean (energy weight); energy-weighted Grad-CAM`],
        [md`\`g\``, md`$\mathcal G_h$`, md`Grad-CAM mean (count weight)`],
        [md`\`esp\``, md`$E_h\max(\mathcal S_h, 0)$`, md`Shap-CAM mean (energy weight); energy-weighted Shap-CAM, positive part`],
        [md`\`esn\``, md`$E_h\min(\mathcal S_h, 0)$`, md`Shap-CAM mean (energy weight); energy-weighted Shap-CAM, negative part`],
        [md`\`s\``, md`$\mathcal S_h$`, md`Shap-CAM mean (count weight)`],
      ],
      note: md`A single-shower experiment measures \`e\` and \`n\` only; its bundles carry the other planes at zero.` },
    { kind: 'p', text: md`**The sign split.** Shap-CAM attributions are signed, and 11–64% of hits carry a negative one, per network and frame, on the production \`hits_all_models\` file (CLAUDE.md §2). A single signed plane would conserve its net total but let positive and negative attributions cancel inside every merged bin, so a region of strong disagreement could read as zero. The service therefore sums the two parts as separate planes. Every resampling operator $W$ of [[eq-kernel-operator]] has non-negative weights whose columns each sum to one, so for each part separately, at every display resolution R from ${C.RESOLUTION_MIN} to ${C.RESOLUTION_MAX} and in both display modes,` },
    { kind: 'eq', id: 'eq-sign-conservation', tex: String.raw`\sum_r \sum_c W_{rc}\,P^{\pm}_c = \sum_c P^{\pm}_c, \qquad \sum_c W_{rc}\,P^{\mathrm{esp}}_c \ge 0 \ge \sum_c W_{rc}\,P^{\mathrm{esn}}_c` },
    { kind: 'p', text: md`each part keeps its sign in every displayed bin and its total over the grid, and their sum is the signed field. Both totals travel in the payload (\`positive_total\`, \`negative_total\`). README.md records the check on the production file: $\sum E\mathcal G$ and both $\sum E\mathcal S$ parts, inside plus outside each grid, equal direct DuckDB sums over the selected hits to within 3.3 × 10⁻¹³ in all four frames and for all three networks, and the served totals are identical at R = 50, 150, 300 and 400 and in both display modes.` },
    { kind: 'p', text: md`**The pre-weighted columns are never summed.** The input file also carries \`*_gradcam_energy\` and \`*_shapcam_energy\` columns, a CAM times the voxel energy rescaled per event or per shower. Like the raw CAMs, they are per-voxel values repeated on every hit of the voxel. For a voxel $v$ holding $n_v$ hit rows, with $\mathcal G_h = \mathcal G_v$ on each of them and $\widetilde{\mathcal G}{}^{E}_v$ the pre-weighted value,` },
    { kind: 'eq', id: 'eq-double-count', tex: String.raw`\sum_{h\in b} E_h\,\mathcal G_h = \sum_{v\in b}\mathcal G_v \sum_{h\in v} E_h = \sum_{v\in b}\mathcal G_v\,E_v, \qquad \sum_{h\in b}\widetilde{\mathcal G}{}^{E}_{v(h)} = \sum_{v\in b} n_v\,\widetilde{\mathcal G}{}^{E}_v` },
    { kind: 'p', text: md`so a sum of the pre-weighted column over hits multiplies each voxel by its row count. Split cells, which the file writes as two rows, are one instance. The columns therefore stay archival (\`db/ddl.py\` \`RAW_CAMS\` holds only \`gradcam\` and \`shapcam\`), and the energy-weighted channels are computed from the raw CAM and the hit energy, which reproduce $\mathcal G_v E_v$ exactly.` },
    { kind: 'p', text: md`**Normalisation of the maps.** The angle- and energy-network CAMs are normalised per shower and the segmentation CAMs per event (\`frame_views.js\` \`CAM_NORMALISATION\`). An ensemble map therefore mixes independently normalised maps: it shows *where* a network attends, not how strongly one event's attention compares with another's, and every CAM caption says so. The column read is the selected network's in the selected frame, \`{model}_{absolute|trans|local}_{gradcam|shapcam}\`; the D-frame reads the absolute-frame networks, and the payload's \`meta.cam\` names the column with its normalisation.` },
    { kind: 'p', text: md`**Encodings.** The co-registered frames draw $\langle\rho\rangle$ relative to a stated reference peak $\rho_{\mathrm{ref}}$ ([[eq-raw-peak]]), the selection's raw-grid peak by default or the whole dataset's when the density is normalised to it:` },
    { kind: 'eq', id: 'eq-relative-log', tex: md`\ell_b = \log_{10}\frac{\langle\rho\rangle_b}{\rho_{\mathrm{ref}}}, \qquad \ell_b \in \left[-${C.RAMP_DECADES},\ \max\left(0, \max_{b'}\ell_{b'}\right)\right], \qquad \text{bin drawn} \iff \ell_b \ge -${C.RAMP_DECADES}` },
    { kind: 'p', text: md`The top is raised above 0 only when a selection is brighter than the dataset reference, so nothing is clipped from above. A populated bin below the $${FLOOR}\,\rho_{\mathrm{ref}}$ floor receives code ${C.BELOW_CODE}, is not drawn, and is counted with the energy it holds; folding it into the opaque bottom colour painted the whole crop as a dark rectangle. The energy-weighted channels use the same ${C.RAMP_DECADES}-decade relative ramp against their own raw-grid peak. The Absolute frame keeps the density in GeV on a ${C.LAB_DECADES}-decade logarithmic ramp below the brightest cell (\`encode/scale.py\`), whose top is locked by default to the dataset's brightest cell, so a selection holding a tenth of the energy cannot render like the full dataset; cells below its bottom fold into the lowest colour and are counted as clipped. Its energy-weighted CAM channels take ${C.CAM_ENERGY_DECADES} decades below the panel's own peak, the two depth panels sharing one. Every logarithmic ramp is quantised to 8-bit codes, code ${C.EMPTY_CODE} meaning no deposit:` },
    { kind: 'eq', id: 'eq-quantise', tex: md`q_b = c_0 + \operatorname{rint}\left(L\,\operatorname{clip}\left(\frac{\ell_b - \ell_{\min}}{\ell_{\max} - \ell_{\min}},\, 0,\, 1\right)\right), \qquad (c_0, L) = \begin{cases} (${C.MIN_CODE}, ${C.LEVELS}) & \text{Absolute} \\ (${C.SIGNED_MIN_CODE}, ${CO_LEVELS}) & \text{co-registered} \end{cases}` },
    { kind: 'p', text: md`One step is $(\ell_{\max} - \ell_{\min})/L$ decades: ${C.LEVELS} levels over ${C.LAB_DECADES} decades are ${STEP_LAB}% in value per step and ${CO_LEVELS} over ${C.RAMP_DECADES} are ${STEP_CO}%, both finer than the hundred or so steps a continuous colormap lets the eye resolve (\`encode/quantize.py\`). The signed sum $\sum E\mathcal S$ is drawn on a diverging signed-log ramp $\pm(${FLOOR} \ldots 1)$ of the selection's peak magnitude, ${SIGNED_LEVELS} codes per sign split at \`SPLIT_CODE\` ${C.SPLIT_CODE}:` },
    { kind: 'eq', id: 'eq-signed-log', tex: md`q_b = \begin{cases} ${C.EMPTY_CODE} & \text{no hit in } b \\ ${C.BELOW_CODE} & |v_b| < ${FLOOR} \\ ${NEG_TOP} - \operatorname{rint}(${SIGNED_STEPS}\,t_b) & v_b < 0 \\ ${C.SPLIT_CODE} + \operatorname{rint}(${SIGNED_STEPS}\,t_b) & v_b > 0 \end{cases}, \qquad t_b = \frac{\log_{10}|v_b| + ${C.RAMP_DECADES}}{${C.RAMP_DECADES}}, \qquad v_b = \frac{(E\mathcal S)_b}{\max_{b'}\left|(E\mathcal S)_{b'}\right|}` },
    { kind: 'p', text: md`so the most negative bin takes code ${C.SIGNED_MIN_CODE}, the most positive ${C.MAX_CODE}, and a step is ${STEP_SIGNED}%. A logarithm cannot take a sign, so the sign selects the half and the magnitude the position within it; nothing is clipped, because the peak is the ramp's end by construction. The two means keep fixed linear scales, so that maps stay comparable across slider positions: $[-1, +1]$ for the raw Shap-CAM mean and $[0, 1]$ for Grad-CAM. Nothing can fall outside them, and the clipped counts are reported anyway. In a co-registered Continuous Field the means are not drawn where the reconstructed density falls below $${FLOOR}\,\rho_{\mathrm{ref}}$, because a kernel's tails would otherwise paint attention into bins that no measured energy reached; the payload reports the share of hits and the largest attention the mask hides. In Native Grid only bins without hits are transparent. The palettes themselves are the subject of [[sec-colour]].` },
    { kind: 'p', text: md`**Exact values.** Quantisation is invisible in the image but not in a tooltip, whose value a reader is about to write down. Each panel therefore ships its ${C.TOPK} brightest bins (by magnitude, with the sign, on a signed channel) exactly, at ${C.TOPK_SIGNIFICANT} significant figures, the precision of the float32 source columns (\`encode/topk.py\`). The rounding is toward zero, $\tilde v = \operatorname{sign}(v)\,\lfloor |v|\,10^{m}\rfloor / 10^{m}$ with $m = ${C.TOPK_SIGNIFICANT - 1} - \lfloor\log_{10}|v|\rfloor$, so a shipped magnitude never exceeds the bin's own and the brightest value never exceeds the panel's peak.` },
    { kind: 'links', id: 'lnk-attribution-channels', items: [
      { page: 'physics', panel: 'xy', set: { channel: 'shapcam_energy' }, label: 'XY entry panel, energy-weighted Shap-CAM' },
      { page: 'physics', panel: 'xy', set: { channel: 'gradcam_energy' }, label: 'XY entry panel, energy-weighted Grad-CAM' },
      { page: 'physics', panel: 'xz', set: { channel: 'shapcam' }, label: 'XZ depth panel, Shap-CAM attribution' },
    ] },
  ],
};
