/* The article as files: LaTeX, BibTeX and every figure as SVG and PNG, in one zip.
 *
 * The Methodology page's Export button (methodology_main.js) calls
 * `downloadArticle`. Everything happens in the reader's browser, from the
 * content modules the page is drawn from; nothing goes to the service.
 *
 * - The text: methodology/latex.js `latexDocument` writes `methodology.tex`
 *   and `references.bib`, and names the figures in document order.
 * - The figures: each is drawn again by methodology/exhibits.js with
 *   `medium: 'paper'` - white, self-contained, sized for the 160 mm LaTeX
 *   text width with no type below 9 pt - and serialised here as an SVG
 *   document. The PNG is that SVG rasterised by the browser at 300 dpi
 *   (160 mm is 1890 px), on white, with a `pHYs` chunk saying so, so a
 *   viewer or pdfLaTeX that reads the density lays it out at its true size.
 * - The archive: zip.js `zipStore`, every file STORED under
 *   `calosrv-methodology/`, downloaded through export/download.js.
 *
 * Only the rasteriser and the download need a browser; `exportFiles` takes
 * the rasteriser as a parameter, so tests/test_js_methodology_export.py runs
 * the rest under Node.
 */

import { EXHIBITS } from './exhibits.js';
import { latexDocument } from './latex.js';
import { crc32, zipStore } from '../zip.js';
import { downloadBlob } from '../export/download.js';

/** The folder every file of the archive sits in. */
export const EXPORT_FOLDER = 'calosrv-methodology';

/** The PNG density: 300 dpi, the usual journal floor for line art with colour. */
export const PNG_DPI = 300;

const SVG_NS = 'http://www.w3.org/2000/svg';
const MM_PER_INCH = 25.4;

/* ------------------------------------------------------------- SVG -- */

const XML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' };

/** `text` safe inside an XML element or a double-quoted attribute. */
export function xmlEscape(text) {
  return String(text).replace(/[&<>"']/g, (ch) => XML_ESCAPES[ch]);
}

/**
 * An exhibit's node tree as an SVG document: an XML declaration, the SVG
 * namespace on the root, every text and attribute escaped. Elements holding
 * only elements are indented; a text's content is written as it is, since
 * white space inside <text> is drawn.
 */
export function serialiseSvg(tree) {
  const lines = ['<?xml version="1.0" encoding="UTF-8" standalone="no"?>'];
  const attrsOf = (node, root) => {
    const attrs = { ...(node.attrs ?? {}) };
    if (root) attrs.xmlns = SVG_NS;
    return Object.entries(attrs)
      .filter(([, value]) => value !== null && value !== undefined && value !== false)
      .map(([name, value]) => ` ${name}="${xmlEscape(value === true ? '' : value)}"`)
      .join('');
  };
  const textOf = (node) => (typeof node.text === 'string' ? node.text : '');
  const write = (node, depth, root = false) => {
    const pad = '  '.repeat(depth);
    if (node.tag === undefined) {
      lines.push(`${pad}${xmlEscape(node.text ?? '')}`);
      return;
    }
    const children = node.children ?? [];
    const open = `<${node.tag}${attrsOf(node, root)}`;
    const inline = textOf(node) + children.filter((c) => c.tag === undefined).map((c) => String(c.text ?? '')).join('');
    if (children.every((c) => c.tag === undefined)) {
      lines.push(inline ? `${pad}${open}>${xmlEscape(inline)}</${node.tag}>` : `${pad}${open}/>`);
      return;
    }
    lines.push(`${pad}${open}>`);
    if (textOf(node)) lines.push(`${pad}  ${xmlEscape(textOf(node))}`);
    for (const child of children) write(child, depth + 1);
    lines.push(`${pad}</${node.tag}>`);
  };
  write(tree, 0, true);
  return `${lines.join('\n')}\n`;
}

/** A paper figure's printed size, from its root's `width`/`height` in millimetres, and its PNG size in pixels. */
export function paperSize(tree, dpi = PNG_DPI) {
  const mm = (value) => {
    const match = /^([\d.]+)mm$/.exec(String(value ?? ''));
    if (!match) throw new Error(`a paper figure is sized in millimetres, not ${JSON.stringify(value)}`);
    return Number(match[1]);
  };
  const widthMm = mm(tree?.attrs?.width);
  const heightMm = mm(tree?.attrs?.height);
  return {
    widthMm,
    heightMm,
    widthPx: Math.round((widthMm / MM_PER_INCH) * dpi),
    heightPx: Math.round((heightMm / MM_PER_INCH) * dpi),
  };
}

/* ------------------------------------------------------------- PNG -- */

const PNG_SIGNATURE = [137, 80, 78, 71, 13, 10, 26, 10];

/** The chunks of a PNG: [{type, start, end}], `start` at the length field, `end` after the CRC. */
export function pngChunks(bytes) {
  if (!PNG_SIGNATURE.every((b, i) => bytes[i] === b)) throw new Error('not a PNG: the signature is missing');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const chunks = [];
  let at = 8;
  while (at + 12 <= bytes.length) {
    const length = view.getUint32(at);
    const type = String.fromCharCode(...bytes.subarray(at + 4, at + 8));
    const end = at + 12 + length;
    if (end > bytes.length) throw new Error(`a truncated PNG chunk ${type}`);
    chunks.push({ type, start: at, end });
    at = end;
    if (type === 'IEND') break;
  }
  if (chunks[0]?.type !== 'IHDR') throw new Error('a PNG must open with IHDR');
  return chunks;
}

/**
 * `bytes` (a PNG) with one `pHYs` chunk of `dpi`, in pixels per metre, right
 * after IHDR, where the specification wants it (before any IDAT). Any pHYs
 * the encoder wrote is replaced.
 */
export function withPhys(bytes, dpi = PNG_DPI) {
  const chunks = pngChunks(bytes);
  const perMetre = Math.round(dpi / 0.0254);
  const chunk = new Uint8Array(21);
  const view = new DataView(chunk.buffer);
  view.setUint32(0, 9);
  chunk.set([0x70, 0x48, 0x59, 0x73], 4);   // 'pHYs'
  view.setUint32(8, perMetre);
  view.setUint32(12, perMetre);
  chunk[16] = 1;                            // the unit is the metre
  view.setUint32(17, crc32(chunk, 4, 17));
  const parts = [bytes.subarray(0, chunks[0].end), chunk];
  for (const c of chunks.slice(1)) if (c.type !== 'pHYs') parts.push(bytes.subarray(c.start, c.end));
  const out = new Uint8Array(parts.reduce((sum, p) => sum + p.length, 0));
  let at = 0;
  for (const part of parts) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}

/**
 * The browser's rasteriser: the SVG document drawn through an <img> onto a
 * white canvas of `widthPx` × `heightPx` (the browser renders an SVG image
 * at the size it is drawn, so the vector is sampled at 300 dpi, not
 * enlarged), encoded as PNG and given its pHYs.
 */
export async function rasterisePng(svgText, { widthPx, heightPx }) {
  const url = URL.createObjectURL(new Blob([svgText], { type: 'image/svg+xml' }));
  try {
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = () => reject(new Error('the browser could not draw a figure\'s SVG'));
      image.src = url;
    });
    const canvas = document.createElement('canvas');
    canvas.width = widthPx;
    canvas.height = heightPx;
    const context = canvas.getContext('2d');
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, widthPx, heightPx);
    context.drawImage(image, 0, 0, widthPx, heightPx);
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('the browser could not encode a figure as PNG'))), 'image/png');
    });
    return withPhys(new Uint8Array(await blob.arrayBuffer()), PNG_DPI);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/* ----------------------------------------------------------- files -- */

const utf8 = (text) => new TextEncoder().encode(text);

/**
 * The archive's files, in order: `methodology.tex`, `references.bib`, then
 * per figure its SVG and its PNG, every name under `EXPORT_FOLDER`.
 * `rasterise(svgText, {widthPx, heightPx, widthMm, heightMm})` returns the
 * PNG's bytes. The returned array also carries `errors`: latex.js's, and a
 * figure no exhibit draws (left out, never fatal).
 */
export async function exportFiles(article, { provenance = {}, rasterise = rasterisePng } = {}) {
  const document_ = latexDocument(article, { provenance, figurePath: (id) => `figures/${id}.png` });
  const errors = [...(document_.errors ?? [])];
  const files = [
    { name: `${EXPORT_FOLDER}/methodology.tex`, bytes: utf8(document_.tex) },
    { name: `${EXPORT_FOLDER}/references.bib`, bytes: utf8(document_.bib) },
  ];
  for (const { id, exhibit } of document_.figures ?? []) {
    const build = EXHIBITS[exhibit];
    if (!build) {
      errors.push(`figure ${id}: no exhibit is named ${exhibit}`);
      continue;
    }
    const tree = build(id, { medium: 'paper' });
    const svg = serialiseSvg(tree);
    files.push({ name: `${EXPORT_FOLDER}/figures/${id}.svg`, bytes: utf8(svg) });
    files.push({ name: `${EXPORT_FOLDER}/figures/${id}.png`, bytes: await rasterise(svg, paperSize(tree)) });
  }
  files.errors = errors;
  return files;
}

/**
 * Build the files, zip them and hand the archive to the browser as
 * `calosrv-methodology-<YYYY-MM-DD>.zip` (the reader's date). `onErrors`
 * receives the problems `exportFiles` found, which do not stop the download.
 * Returns the file name.
 */
export async function downloadArticle({ article, provenance = {}, onErrors = () => {} }) {
  const date = new Date();
  const files = await exportFiles(article, { provenance });
  const archive = zipStore(files, { date });
  const name = `${EXPORT_FOLDER}-${date.toLocaleDateString('en-CA')}.zip`;
  downloadBlob(new Blob([archive], { type: 'application/zip' }), name);
  onErrors(files.errors);
  return name;
}
