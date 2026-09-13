/* Dual-ended range control: two overlaid range inputs plus two number fields.
 *
 * Two callbacks rather than one, and the distinction is what makes the
 * interface feel fast on a multi-gigabyte dataset:
 *
 *   onInput   fires continuously while dragging or typing -> debounced preview
 *             request, served from the 10% unbiased sample
 *   onCommit  fires on release, Enter or blur -> the exact query
 *
 * So a gesture produces a stream of cheap estimates and exactly one exact
 * result, instead of sixty full scans.
 *
 * ## Why the slider is quantised to the number field's step
 *
 * The earlier version hard-coded a 1000-step integer domain. Across the E1
 * range of 0.408-19.999 GeV that is 0.0196 GeV per step, so a typed 2.05 could
 * only land on 2.0455 - the slider silently refused to represent the value the
 * user asked for, and the same arbitrary fractions then leaked into the URL.
 *
 * Here the slider's integer domain *is* the step grid: the physical range is
 * snapped outward to whole multiples of `step` (E1 becomes 0.40-20.00 in 392
 * steps of 0.05; D becomes 2-5308 in 5306 steps of 1), so every reachable
 * value is a clean multiple by construction. Typing and dragging address the
 * same grid, round-tripping exactly, and the URL needs no defensive rounding.
 */

export class RangeSlider {
  constructor({
    loId, hiId, fillId, numLoId, numHiId,
    step = 0.01, decimals = 2, unit = '',
    onInput, onCommit,
  }) {
    this.lo = document.getElementById(loId);
    this.hi = document.getElementById(hiId);
    this.fill = document.getElementById(fillId);
    this.numLo = document.getElementById(numLoId);
    this.numHi = document.getElementById(numHiId);

    this.step = step;
    this.decimals = decimals;
    this.unit = unit;
    this.onInput = onInput || (() => {});
    this.onCommit = onCommit || (() => {});

    this.min = 0;
    this.max = 1;
    this.steps = 1;

    this.bindSliders();
    this.bindNumbers();
  }

  bindSliders() {
    const onDrag = () => {
      this.enforceOrder();
      this.syncNumbers();
      this.paint();
      this.onInput(this.value());
    };
    const onRelease = () => {
      this.enforceOrder();
      this.syncNumbers();
      this.paint();
      this.onCommit(this.value());
    };

    for (const input of [this.lo, this.hi]) {
      if (!input) continue;
      input.addEventListener('input', onDrag);
      input.addEventListener('change', onRelease);
      // Keyboard users never fire pointerup, so commit on blur as well.
      input.addEventListener('blur', onRelease);
    }
  }

  bindNumbers() {
    for (const [field, which] of [[this.numLo, 'lo'], [this.numHi, 'hi']]) {
      if (!field) continue;

      // While typing, follow the value but do NOT clamp: typing "2" on the way
      // to "20" must not be rewritten to the minimum under the cursor.
      field.addEventListener('input', () => {
        const parsed = Number(field.value);
        if (field.value === '' || !Number.isFinite(parsed)) return;
        this.writeSlider(which, parsed);
        this.paint();
        // A half-typed bound can momentarily invert the range. Emitting it
        // would fire a request the server rightly rejects as inverted, so the
        // preview simply waits for the range to make sense again.
        if (this.isOrdered()) this.onInput(this.value());
      });

      const commit = () => {
        const parsed = Number(field.value);
        if (field.value === '' || !Number.isFinite(parsed)) {
          this.syncNumbers();
          return;
        }
        this.writeSlider(which, parsed);

        // Push the opposite bound rather than swapping. Swapping silently
        // reassigns what the user typed to the other field - entering a new
        // lower bound above the current upper one would move it to the upper
        // field and leave the old upper value as the new lower - which is both
        // surprising and, in a filter, wrong.
        if (which === 'lo' && Number(this.lo.value) > Number(this.hi.value)) {
          this.hi.value = this.lo.value;
        } else if (which === 'hi' && Number(this.hi.value) < Number(this.lo.value)) {
          this.lo.value = this.hi.value;
        }

        // Force only the field being committed, so its displayed value matches
        // what was actually applied after snapping. The opposite field is left
        // alone while focused - blurring out of one input must not overwrite
        // the value the user is part-way through typing into the other.
        this.syncNumbers({ forceField: which });
        this.paint();
        this.onCommit(this.value());
      };
      field.addEventListener('change', commit);
      field.addEventListener('blur', commit);
      field.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          field.blur();
        }
      });
    }
  }

  /**
   * Set the physical bounds, snapping the domain outward to the step grid.
   *
   * Snapping outward (floor the minimum, ceil the maximum) can only widen the
   * selectable range past the data, never narrow it, so no event becomes
   * unreachable.
   */
  setBounds(min, max, value = null) {
    const step = this.step;
    this.min = Math.floor(min / step) * step;
    this.max = Math.ceil(max / step) * step;
    this.steps = Math.max(1, Math.round((this.max - this.min) / step));

    for (const input of [this.lo, this.hi]) {
      if (!input) continue;
      input.min = 0;
      input.max = this.steps;
      input.step = 1;
      input.disabled = !(this.max > this.min);
    }
    for (const field of [this.numLo, this.numHi]) {
      if (!field) continue;
      field.min = this.round(this.min);
      field.max = this.round(this.max);
      field.step = step;
      field.disabled = !(this.max > this.min);
    }

    const [vlo, vhi] = value || [this.min, this.max];
    this.setValue(vlo, vhi, { silent: true });
  }

  /** The single place a value is written to the DOM, so binding cannot loop. */
  setValue(lo, hi, { silent = false } = {}) {
    this.writeSlider('lo', lo);
    this.writeSlider('hi', hi);
    this.enforceOrder();
    this.syncNumbers();
    this.paint();
    if (!silent) this.onCommit(this.value());
  }

  writeSlider(which, physical) {
    const target = which === 'lo' ? this.lo : this.hi;
    if (target) target.value = this.toStep(physical);
  }

  /**
   * Write the current range back into the number fields.
   *
   * A focused field is normally left alone so the caret is not disturbed
   * mid-edit; `force` overrides that on commit, when the value must reflect
   * what was actually applied - including any clamping to the step grid.
   * Assigning `.value` dispatches no input event, so this cannot recurse.
   */
  syncNumbers({ forceField = null } = {}) {
    const [a, b] = this.value();
    const writable = (field, which) =>
      field && (forceField === which || document.activeElement !== field);
    if (writable(this.numLo, 'lo')) this.numLo.value = this.round(a);
    if (this.numHi && (forceField === 'hi' || document.activeElement !== this.numHi)) {
      this.numHi.value = this.round(b);
    }
  }

  isOrdered() {
    return Number(this.lo.value) <= Number(this.hi.value);
  }

  toStep(physical) {
    if (!(this.max > this.min)) return 0;
    const index = Math.round((physical - this.min) / this.step);
    return Math.min(this.steps, Math.max(0, index));
  }

  toPhysical(index) {
    // Rounding to the declared precision removes the float dust that
    // 0.4 + 33 * 0.05 leaves behind, which is what used to reach the URL.
    return this.round(this.min + Number(index) * this.step);
  }

  round(value) {
    return Number(Number(value).toFixed(this.decimals));
  }

  enforceOrder() {
    if (!this.lo || !this.hi) return;
    if (Number(this.lo.value) > Number(this.hi.value)) {
      const swap = this.lo.value;
      this.lo.value = this.hi.value;
      this.hi.value = swap;
    }
  }

  value() {
    if (!this.lo || !this.hi) return [this.min, this.max];
    return [this.toPhysical(this.lo.value), this.toPhysical(this.hi.value)];
  }

  paint() {
    if (!this.fill) return;
    const loPercent = (Number(this.lo.value) / this.steps) * 100;
    const hiPercent = (Number(this.hi.value) / this.steps) * 100;
    this.fill.style.left = `${loPercent}%`;
    this.fill.style.width = `${Math.max(0, hiPercent - loPercent)}%`;
  }

  /** Whether the current selection spans the whole available range. */
  isFullRange() {
    const [a, b] = this.value();
    return a <= this.min && b >= this.max;
  }

  setDisabled(disabled, message) {
    const control = (this.lo || this.numLo)?.closest('.control');
    if (control) control.classList.toggle('is-disabled', disabled);
    for (const field of [this.numLo, this.numHi]) {
      if (field) field.placeholder = disabled && message ? message : '';
    }
  }
}
