/* The interface's name for every choice, shared by each place that lists them.
 *
 * The sidebar carries these as static markup (index.html) because it has to
 * render before any script runs; the Admin Settings panel builds its controls
 * from this map. A test compares the two, so a label renamed in one place and
 * not the other fails the suite instead of showing a reader two names for one
 * thing. `detail` is the muted qualifier after the label. */

export const CHOICE_LABELS = Object.freeze({
  frame: [
    { value: 'lab', label: 'Laboratory', detail: '(detector coordinates)' },
    { value: 'trans', label: 'Translated', detail: '(each shower from its own entry point P₀)' },
    { value: 'local', label: 'Local', detail: '(shower-fixed)' },
    { value: 'canonical', label: 'Canonical centre-of-separation', detail: '(SE(3) co-registered)' },
  ],
  model: [
    { value: 'segmentation', label: 'Segmentation Model' },
    { value: 'energy', label: 'Energy Estimation Model' },
    { value: 'angle', label: 'Incident Angle Estimation Model' },
  ],
  channel: [
    { value: 'density', label: 'Average Hit Density (Summed Energy)' },
    { value: 'gradcam', label: 'Grad-CAM Model Attention' },
    { value: 'gradcam_energy', label: 'Energy-weighted Grad-CAM', detail: '(Σ E·CAM)' },
    { value: 'shapcam', label: 'Shap-CAM Attribution', detail: '(signed)' },
    { value: 'shapcam_energy', label: 'Energy-weighted Shap-CAM', detail: '(Σ E·CAM, signed)' },
  ],
  rho_norm: [
    { value: 'selection', label: "Relative to this selection's peak" },
    { value: 'dataset', label: 'Relative to the dataset peak' },
  ],
});

/* Display mode, as the panel offers it. A saved mode applies to the default
 * frame only, so "each frame's own" is a choice in its own right: native in the
 * laboratory, the kernel reconstruction in the co-registered frames. The
 * sidebar's own labels change with the frame, so they are not repeated here. */
export const DISPLAY_CHOICES = Object.freeze([
  { value: null, label: "Frame's own", detail: '(native in Laboratory, continuous elsewhere)' },
  { value: 'native', label: 'Native', detail: '(detector lattice, or the raw 20 mm grid)' },
  { value: 'continuous', label: 'Continuous Field' },
]);
