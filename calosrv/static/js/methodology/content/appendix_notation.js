/* Appendix A: the notation, one symbol with one meaning across the article.
 * Content model and rules: index.js. The last rows are the symbols §4
 * introduces. */

import { C } from '../constants.js';

const tx = (strings, ...values) => String.raw(strings, ...values).replace(/\\`/g, '`');

export default {
  id: 'app-notation',
  title: 'Notation',
  blocks: [
    { kind: 'p', text: tx`[[tab-notation]] lists every symbol the article uses, with the meaning it keeps in every section. Lengths are in millimetres and energies and momenta in GeV unless stated; a prime marks a D-frame coordinate, and bold marks a vector or a matrix.` },
    {
      kind: 'table',
      id: 'tab-notation',
      caption: tx`Symbols and their meanings.`,
      head: ['Symbol', 'Meaning'],
      rows: [
        [tx`$x, y, z$`, tx`Absolute (detector) coordinates, mm; $z$ is raw detector depth`],
        [tx`$z_{\mathrm f}$, $z_k$`, tx`the front face; the $k$-th layer, $z_k = ${C.FIRST_LAYER_Z_MM} + ${C.Z_PITCH_MM}\,(k - 1)\,\mathrm{mm}$`],
        [tx`$z_{\mathrm{disp}}$`, tx`display depth below the front face, $z - ${C.CORE_SHIFT_Z_MM}\,\mathrm{mm}$ (a label, never a coordinate)`],
        [tx`$\mathbf p$, $E$, $h$`, tx`a hit's position and deposited energy (GeV); $h$ indexes hits`],
        [tx`$j \in \{A, B\}$, $N$, $n$`, tx`the shower; $N$ events or showers (the text says which); $n$ a generic sample size`],
        [tx`$\theta$, $\varphi$`, tx`incident polar and azimuthal angle`],
        [tx`$\hat{\mathbf n}(\theta, \varphi)$`, tx`incident direction, $(\sin\theta\cos\varphi, \sin\theta\sin\varphi, \cos\theta)$`],
        [tx`$\mathbf c_j$, $D$`, tx`shower $j$'s energy-weighted 3-D centroid; $D = \lVert \mathbf c_A - \mathbf c_B \rVert$`],
        [tx`$\mathbf e_j$, $\mathbf m$, $\psi$, $D_{\mathrm{entry}}$`, tx`entry points at the front face, their midpoint, the A→B azimuth, their distance`],
        [tx`$P_0$, $z_0$`, tx`first-layer entry point and its layer`],
        [tx`$\mathbf a$`, tx`the anchor an SE(3) motion takes to the origin (bold; plain $a$ is the accumulation pitch)`],
        [tx`$\beta_i$, $\xi_i$`, tx`an event's projected slope and entry coordinate on a depth panel (in [[eq-rc]], $\alpha$ and $\beta$ are two generic azimuths)`],
        [tx`$x', y', z'$`, tx`D-frame coordinates; the entry panel writes $x'$ as $D$`],
        [tx`$\Delta x, \Delta y, \Delta z$`, tx`per-shower translated coordinates (legacy frame)`],
        [tx`$u, v, w$`, tx`Local coordinates; $w$ along the incident direction`],
        [tx`$\mathbf R(\theta, \varphi)$, $\mathbf R_y$, $\mathbf R_z$`, tx`rotation matrices; $R$ alone is the display resolution`],
        [tx`$\langle\rho\rangle$, $\rho_{\mathrm{ref}}$, $\ell$`, tx`ensemble density (GeV mm⁻² per event), its reference peak, $\ell = \log_{10}(\langle\rho\rangle / \rho_{\mathrm{ref}})$`],
        [tx`$a$, $W_{rc}$, $G_c$`, tx`accumulation pitch (${C.CANONICAL_PITCH_MM} mm), the resampling operator, source bin $c$'s cumulative mass`],
        [tx`$s_c$, $\bar s_c$; $d_r$`, tx`a source bin's edges and centre; a destination bin's edges (subscripted; plain $s$ is the sample SD)`],
        [tx`$\sigma_{\mathrm K}$`, tx`the Gaussian display kernel's width (${C.SMOOTH_SIGMA_MM} mm), never plain $\sigma$`],
        [tx`$\Phi$, $\Phi'$, $\Psi$`, tx`standard normal CDF, its density, and $\Psi(u) = u\,\Phi(u) + \Phi'(u)$`],
        [tx`$k$, $k_z$`, tx`sub-deposits per cell transversely and in depth`],
        [tx`$\mathcal G_h$, $\mathcal S_h$`, tx`a hit's Grad-CAM and (signed) Shap-CAM values`],
        [tx`$c_j$, $p$`, tx`calibration constant $\sum p / \sum E_{\mathrm{dep}}$ of shower $j$; $p$ incident momentum (GeV)`],
        [tx`$\hat\mu$, $s$, $s_{\mathrm{pop}}$`, tx`sample mean, SD with ddof = ${C.DDOF}, population SD`],
        [tx`$t_{0.975,\nu}$, $\chi^2_{q,\nu}$, $c_4(N)$`, tx`Student-t and $\chi^2$ quantiles; the bias factor of $s$`],
        [tx`$\kappa$`, tx`the core refit's truncation factor (${C.CORE_TRUNCATION_FACTOR.toFixed(4)}); never $k$`],
        [tx`$\tau$, $f(\tau)$`, tx`a truncation multiple and the variance factor of a Gaussian truncated at $\pm\tau\sigma$`],
        [tx`$\hat Q$`, tx`a ratio of sums, $\sum y_i / \sum x_i$, with its cluster interval`],
        [tx`$f_j$; $f_{A,h}$; $f_e(b)$, $F_e(b)$, $M_e$`, tx`sampling fraction of shower $j$; hit $h$'s voxel fraction of shower A; a profile's per-shower fraction in bin $b$, its sum over event $e$'s $M_e$ showers`],
        [tx`$\delta$; $h$ (as a width)`, tx`histogram bin width; KDE bandwidth (as an index, $h$ runs over hits)`],
        [tx`$\bar R$, $\bar\varphi$, $P_{\mathrm{Ray}}$`, tx`mean resultant length, mean direction, Rayleigh p-value`],
        [tx`$C$, $S$`, tx`the cosine and sine sums of a resultant, [[eq-resultant]]`],
        [tx`$r$, $r_c$, $\zeta$`, tx`Pearson r, circular r, Fisher's $\zeta = \operatorname{atanh} r$ (never $z$)`],
        [tx`$R_{\mathrm M}$`, tx`Mardia's circular–linear correlation (never plain $R$)`],
        [tx`$R^2$, $R^2_\circ$`, tx`coefficient of determination; its circular analogue for an azimuth`],
        [tx`$G$, $n_{\mathrm{eff}}$`, tx`jackknife groups or clusters; effective sample size`],
        [tx`$H_x$, $q_\alpha$`, tx`a window half-width; an energy-weighted quantile`],
        [tx`$\tilde o_j$, $W_{\mathrm d}$, $r_1$`, tx`detrended profile of column $j$, the detrend window, the lag-1 autocorrelation`],
        [tx`$P^{\mathrm e}, P^{\pm}, P^{\pm}_{\mathrm{out}}$; $P_{\mathcal S}$`, tx`accumulated planes, the signed parts and their share outside the display window; the reference peak of the signed-log ramp`],
        [tx`$W_{\mathrm{px}}, H_{\mathrm{px}}$; $L_{\mathrm c}, L_{\mathrm r}$; $\gamma$`, tx`a panel's size in pixels; its millimetre spans; the shared scale in px mm⁻¹`],
        [tx`$C_{\mathrm{WCAG}}$, $Y$, $\Lambda$`, tx`WCAG contrast ratio, relative luminance, a linear sRGB channel ($\Lambda_8$ its 8-bit value)`],
        [tx`$L$, $n_{\mathrm d}$, $\Delta\ell$`, tx`steps of an 8-bit colour ramp, the decades it spans, and the step in $\ell$ per code ([[sec-discussion]])`],
        [tx`$f_{\mathrm s}$, $I_h$`, tx`inclusion probability of the drag-preview sample; hit $h$'s Bernoulli inclusion indicator`],
        [tx`$\hat S_c$, $n_{\mathrm c}$`, tx`the preview's estimate of a cell's sum; the number of hits in cell $c$ ([[sec-discussion]])`],
      ],
    },
  ],
};
