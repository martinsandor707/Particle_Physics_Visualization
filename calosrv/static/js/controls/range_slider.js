/* Dual-ended range slider built from two overlaid native range inputs.
 *
 * Two callbacks rather than one, and the distinction is what makes the
 * interface feel fast on a multi-gigabyte dataset:
 *
 *   onInput   fires continuously while dragging -> debounced preview request,
 *             served from the 10% unbiased sample
 *   onCommit  fires on release -> the exact query
 *
 * So a drag produces a stream of cheap estimates and exactly one exact result,
 * instead of sixty full scans.
 */

export class RangeSlider {
  constructor({ loId, hiId, fillId, readoutId, format, onInput, onCommit }) {
    this.lo = document.getElementById(loId);
    this.hi = document.getElementById(hiId);
    this.fill = document.getElementById(fillId);
    this.readout = document.getElementById(readoutId);
    this.format = format || ((v) => v.toFixed(2));
    this.onInput = onInput || (() => {});
    this.onCommit = onCommit || (() => {});
    this.min = 0;
    this.max = 1;

    const handleInput = () => {
      this.enforceOrder();
      this.paint();
      this.onInput(this.value());
    };
    const handleCommit = () => {
      this.enforceOrder();
      this.paint();
      this.onCommit(this.value());
    };

    for (const input of [this.lo, this.hi]) {
      input.addEventListener('input', handleInput);
      input.addEventListener('change', handleCommit);
      // Keyboard users never fire pointerup, so commit on blur as well.
      input.addEventListener('blur', handleCommit);
    }
  }

  /**
   * Set the physical bounds of the axis.
   *
   * The underlying inputs work in integer steps so the two thumbs compare
   * exactly; physical values are mapped on and off that integer domain. 1000
   * steps is finer than the slider is pixels wide, so nothing is lost.
   */
  setBounds(min, max, value = null) {
    this.min = min;
    this.max = max;
    const span = max - min;
    this.steps = 1000;

    for (const input of [this.lo, this.hi]) {
      input.min = 0;
      input.max = this.steps;
      input.step = 1;
      input.disabled = !(span > 0);
    }

    const [vlo, vhi] = value || [min, max];
    this.lo.value = this.toStep(vlo);
    this.hi.value = this.toStep(vhi);
    this.paint();
  }

  toStep(physical) {
    const span = this.max - this.min;
    if (!(span > 0)) return 0;
    const fraction = (physical - this.min) / span;
    return Math.round(Math.min(1, Math.max(0, fraction)) * this.steps);
  }

  toPhysical(step) {
    const span = this.max - this.min;
    return this.min + (Number(step) / this.steps) * span;
  }

  enforceOrder() {
    if (Number(this.lo.value) > Number(this.hi.value)) {
      const swap = this.lo.value;
      this.lo.value = this.hi.value;
      this.hi.value = swap;
    }
  }

  value() {
    return [this.toPhysical(this.lo.value), this.toPhysical(this.hi.value)];
  }

  paint() {
    const loPercent = (Number(this.lo.value) / this.steps) * 100;
    const hiPercent = (Number(this.hi.value) / this.steps) * 100;
    this.fill.style.left = `${loPercent}%`;
    this.fill.style.width = `${Math.max(0, hiPercent - loPercent)}%`;
    const [a, b] = this.value();
    this.readout.textContent = `${this.format(a)} – ${this.format(b)}`;
  }

  setDisabled(disabled, message) {
    const control = this.lo.closest('.control');
    if (control) control.classList.toggle('is-disabled', disabled);
    if (disabled && message && this.readout) this.readout.textContent = message;
  }
}
