/* Typography for rendered numbers. DOM-free, so it runs under Node.
 *
 * A negative number is set with the true minus sign U+2212, never the ASCII
 * hyphen-minus: the hyphen is shorter and sits lower, so "-0.05" beside
 * "+0.05" reads as a dash rather than a sign, and in exported SVG a figure
 * with hyphens is typographically wrong. This applies to every number a
 * reader sees - axis ticks, legend endpoints, tooltips, captions, footnotes
 * and exported text - and to exponents ("1.2e−5"). JSON numbers are
 * untouched: this is presentation only.
 */

export const MINUS = '−';

/** Replace every hyphen-minus that signs a number with U+2212. */
export function typographic(text) {
  return String(text).replace(/-(?=[\d.∞])/g, MINUS);
}

/**
 * A fixed-point number with a typographic sign.
 *
 * `plus: true` also marks positive values (+0.23), for quantities whose sign
 * is the point - a lag-1 autocorrelation, a signed attribution.
 */
export function formatSigned(value, digits = 2, { plus = false } = {}) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const text = Math.abs(value).toFixed(digits);
  const zero = Number(text) === 0;
  if (value < 0 && !zero) return `${MINUS}${text}`;
  return plus && !zero ? `+${text}` : text;
}
