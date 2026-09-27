/* Open, close and focus handling shared by the dialogs.
 *
 * A modal takes over the page, so it has to behave like one: Escape and a click
 * on the backdrop close it, focus moves inside when it opens, Tab stays within
 * it, and focus returns to the control that opened it when it closes. The
 * dialog is announced as one to assistive technology. */

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export class ModalShell {
  /**
   * @param {HTMLElement} backdrop  the `.modal-backdrop`, holding one `.modal`
   * @param {{onClose?: Function, initialFocus?: () => HTMLElement|null}} options
   */
  constructor(backdrop, { onClose, initialFocus } = {}) {
    this.backdrop = backdrop;
    this.dialog = backdrop.querySelector('.modal') || backdrop;
    this.onClose = onClose || (() => {});
    this.initialFocus = initialFocus || (() => null);
    this.returnTo = null;

    this.dialog.setAttribute('role', 'dialog');
    this.dialog.setAttribute('aria-modal', 'true');

    backdrop.addEventListener('click', (event) => {
      if (event.target === backdrop) this.close();
    });
    document.addEventListener('keydown', (event) => {
      if (!this.isOpen) return;
      if (event.key === 'Escape') this.close();
      else if (event.key === 'Tab') this.keepFocusInside(event);
    });
  }

  get isOpen() {
    return !this.backdrop.hidden;
  }

  open() {
    if (this.isOpen) return;
    this.returnTo = document.activeElement;
    this.backdrop.hidden = false;
    const target = this.initialFocus() || this.focusable()[0];
    if (target) target.focus();
  }

  close() {
    if (!this.isOpen) return;
    this.backdrop.hidden = true;
    this.onClose();
    if (this.returnTo && typeof this.returnTo.focus === 'function') this.returnTo.focus();
    this.returnTo = null;
  }

  focusable() {
    return [...this.dialog.querySelectorAll(FOCUSABLE)]
      .filter((el) => !el.disabled && !el.closest('[hidden]'));
  }

  keepFocusInside(event) {
    const items = this.focusable();
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      last.focus();
      event.preventDefault();
    } else if (!event.shiftKey && document.activeElement === last) {
      first.focus();
      event.preventDefault();
    }
  }
}
