/* The sidebar's filter block: the E₁, E₂ and D range sliders and the
 * undefined-D option, adopted per experiment.
 *
 * The axes come from the experiment's capability block (capabilities.js
 * `filterAxes`). A two-shower experiment filters on E₁, E₂ and D, as the
 * markup ships; a single-shower experiment has one axis, the shower's own
 * incident momentum, which the server takes as e1_min / e1_max. Its E₁
 * control is relabelled "p — incident momentum" at runtime, and the E₂, D,
 * logic-note and undefined-D controls are hidden - and, through
 * `State.restrictAxes`, never sent: the server refuses a filter it has no
 * axis for.
 *
 * Each axis is quantised to its numeric step, so typing 2.05 and dragging to
 * 2.05 address the same grid point and round-trip through the URL unchanged.
 * The slider domains are recorded (`State.adoptSnappedBounds`) before any
 * hash is written, so a link never carries a raw dataset bound such as 0.408
 * for an axis the user did not narrow.
 */

import { RangeSlider } from './range_slider.js';
import { TWO_SHOWER_AXES, filterAxes } from '../capabilities.js';
import { relabel, relabelAria, restoreLabel } from '../page_common.js';

/** The controls each axis owns, by element id (present in the markup of every page). */
const AXIS_IDS = {
  e1: { control: 'ctl-e1', lo: 'e1-lo', hi: 'e1-hi', fill: 'e1-fill', numLo: 'e1-num-lo', numHi: 'e1-num-hi' },
  e2: { control: 'ctl-e2', lo: 'e2-lo', hi: 'e2-hi', fill: 'e2-fill', numLo: 'e2-num-lo', numHi: 'e2-num-hi' },
  d: { control: 'ctl-d', lo: 'd-lo', hi: 'd-hi', fill: 'd-fill', numLo: 'd-num-lo', numHi: 'd-num-hi' },
};

/** Controls that belong to the two-shower filter set as a whole. */
const SEPARATION_IDS = ['filter-logic', 'ctl-undefined-d'];

export class FilterBlock {
  /**
   * @param {{state: State, onPreview?: () => void, onCommit: () => void}} options
   *   `onPreview` runs while a slider is dragged (the sampled preview),
   *   `onCommit` on release, Enter, blur or the undefined-D toggle.
   */
  constructor({ state, onPreview = null, onCommit }) {
    this.state = state;
    this.onPreview = onPreview || (() => {});
    this.onCommit = onCommit || (() => {});
    this.axes = TWO_SHOWER_AXES;
    this.byKey = {};
    for (const axis of TWO_SHOWER_AXES) {
      const ids = AXIS_IDS[axis.key];
      const update = ([lo, hi]) => {
        state.markTouched(axis.key);
        state.set({ [`${axis.key}_min`]: lo, [`${axis.key}_max`]: hi });
      };
      this.byKey[axis.key] = new RangeSlider({
        loId: ids.lo, hiId: ids.hi, fillId: ids.fill, numLoId: ids.numLo, numHiId: ids.numHi,
        step: axis.step, decimals: axis.digits, unit: axis.unit,
        onInput: (value) => { update(value); this.onPreview(); },
        onCommit: (value) => { update(value); this.onCommit(); },
      });
    }
    this.undefinedD = document.getElementById('opt-undefined-d');
    this.undefinedD?.addEventListener('change', () => {
      state.set({ include_undefined_d: this.undefinedD.checked });
      this.onCommit();
    });
  }

  /** The three sliders by axis key, whether or not the experiment uses them. */
  get sliders() {
    return this.byKey;
  }

  /**
   * Adopt an experiment: its axes, their labels and its bounds.
   *
   * Returns the active axis descriptors. The order matters: the state drops
   * the axes the experiment lacks first, the domains are recorded before the
   * one hash write, and the sliders then adopt values on the same snapped grid.
   */
  adopt(experiment, axes = filterAxes(experiment)) {
    const state = this.state;
    this.axes = axes;
    state.restrictAxes(axes);
    const active = new Set(axes.map((axis) => axis.key));

    for (const [key, ids] of Object.entries(AXIS_IDS)) {
      const control = document.getElementById(ids.control);
      if (control) control.hidden = !active.has(key);
    }
    for (const id of SEPARATION_IDS) {
      const element = document.getElementById(id);
      if (element) element.hidden = !active.has('d');
    }
    this.label(axes.find((axis) => axis.key === 'e1'));

    const bounds = experiment?.bounds ?? {};
    const domains = state.adoptSnappedBounds(bounds);
    const adopted = {};
    for (const axis of axes) {
      const slider = this.byKey[axis.key];
      if (!slider) continue;
      const range = bounds[axis.key];
      if (!domains[axis.key]) {
        // No defined range (every event without D, say): the control stays,
        // disabled, and says so.
        slider.setDisabled(true, 'N/A');
        continue;
      }
      slider.setDisabled(false);
      const v = state.values;
      const initial = state.isTouched(axis.key) ? [v[`${axis.key}_min`], v[`${axis.key}_max`]] : null;
      slider.setBounds(range[0], range[1], initial);
      // Adopt what the slider actually resolved to: a touched bound snaps to
      // the step grid, and state must agree with what the control shows.
      const [lo, hi] = slider.value();
      adopted[`${axis.key}_min`] = lo;
      adopted[`${axis.key}_max`] = hi;
    }
    state.set(adopted, { silent: true });
    if (this.undefinedD) this.undefinedD.checked = Boolean(state.get('include_undefined_d'));
    state.writeHash();
    return axes;
  }

  /** The E₁ control's label and hint: the axis's own, or the markup's. */
  label(axis) {
    const label = document.getElementById('e1-label');
    const hint = document.getElementById('e1-hint');
    const fields = [
      [document.getElementById('e1-num-lo'), 'minimum', 'GeV'],
      [document.getElementById('e1-num-hi'), 'maximum', 'GeV'],
      [document.getElementById('e1-lo'), 'minimum slider', null],
      [document.getElementById('e1-hi'), 'maximum slider', null],
    ];
    if (axis?.label) {
      relabel(label, axis.label);
      relabel(hint, axis.hint ?? '');
      for (const [field, what, unit] of fields) {
        relabelAria(field, `${axis.aria ?? axis.symbol} ${what}${unit ? ` [${unit}]` : ''}`);
      }
    } else {
      restoreLabel(label);
      restoreLabel(hint);
      for (const [field] of fields) restoreLabel(field);
    }
  }
}
