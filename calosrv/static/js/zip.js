/* A zip archive of stored (uncompressed) files, and the CRC-32 it needs.
 *
 * The Methodology page's Export button hands the reader one file - the
 * article as LaTeX, its references, its figures - and the browser has no zip
 * writer of its own. A vendored library would be the only other way, and the
 * archive needs none of what one brings: the PNGs are compressed already, and
 * the TeX and SVG are a few hundred kilobytes. So the files are STORED
 * (method 0), which is the whole of the format but the headers.
 *
 * What is written (PKWARE APPNOTE 6.3.x, §4.3): for each file a local header
 * and its bytes, then the central directory, then the end-of-central-directory
 * record. Names are UTF-8, flagged as such (general-purpose bit 11), so a
 * name outside ASCII unpacks under its own spelling. The timestamp is the
 * export time in MS-DOS form, local time, two-second resolution, as every
 * unzip expects. No zip64: an archive over 4 GiB or 65 535 entries throws,
 * which the article never comes near.
 *
 * `crc32` is zlib's CRC-32 (reflected polynomial 0xEDB88320), which the PNG
 * chunks use too (methodology/export.js). Pure: no DOM, no network;
 * tests/test_js_zip.py reads the archive back with Python's zipfile.
 */

/** The 256-entry table of the reflected CRC-32 polynomial, built once. */
const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

/** zlib's CRC-32 of `bytes` (a Uint8Array), as an unsigned 32-bit integer. */
export function crc32(bytes, start = 0, end = bytes.length) {
  let c = 0xFFFFFFFF;
  for (let i = start; i < end; i += 1) c = CRC_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}

/* Signatures and fields of the three records. */
const LOCAL_HEADER = 0x04034b50;
const CENTRAL_HEADER = 0x02014b50;
const END_OF_DIRECTORY = 0x06054b50;
/** Version 2.0: what every unzip reads; stored files need no more. */
const VERSION = 20;
/** General-purpose bit 11: the name is UTF-8. */
const UTF8_FLAG = 0x0800;
const STORED = 0;
const MAX_U32 = 0xFFFFFFFF;
const MAX_U16 = 0xFFFF;

/** `date` as MS-DOS time and date words (local time; 1980 to 2107, seconds halved). */
function dosTime(date) {
  const year = Math.min(2107, Math.max(1980, date.getFullYear()));
  return {
    time: (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2),
    date: ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate(),
  };
}

/**
 * A zip archive of `files` ([{name, bytes}], bytes a Uint8Array), every
 * entry STORED, in the order given, as a Uint8Array. `date` stamps every
 * entry. A name must be unique, relative and not empty.
 */
export function zipStore(files, { date = new Date() } = {}) {
  const encoder = new TextEncoder();
  const stamp = dosTime(date);
  const seen = new Set();
  const entries = files.map(({ name, bytes }) => {
    const text = String(name ?? '');
    if (!text || text.startsWith('/') || text.split('/').includes('..')) throw new Error(`zip: a bad entry name: ${JSON.stringify(text)}`);
    if (seen.has(text)) throw new Error(`zip: a duplicate entry name: ${text}`);
    seen.add(text);
    const data = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    const nameBytes = encoder.encode(text);
    if (nameBytes.length > MAX_U16) throw new Error(`zip: an entry name over 65 535 bytes: ${text.slice(0, 40)}…`);
    if (data.length > MAX_U32) throw new Error(`zip: ${text} is over 4 GiB, which needs zip64`);
    return { nameBytes, data, crc: crc32(data) };
  });
  if (entries.length > MAX_U16) throw new Error('zip: over 65 535 entries, which needs zip64');

  const localSize = entries.reduce((sum, e) => sum + 30 + e.nameBytes.length + e.data.length, 0);
  const centralSize = entries.reduce((sum, e) => sum + 46 + e.nameBytes.length, 0);
  if (localSize + centralSize + 22 > MAX_U32) throw new Error('zip: the archive is over 4 GiB, which needs zip64');

  const out = new Uint8Array(localSize + centralSize + 22);
  const view = new DataView(out.buffer);
  let at = 0;
  const u16 = (value) => { view.setUint16(at, value, true); at += 2; };
  const u32 = (value) => { view.setUint32(at, value >>> 0, true); at += 4; };
  const put = (bytes) => { out.set(bytes, at); at += bytes.length; };

  const offsets = [];
  for (const e of entries) {
    offsets.push(at);
    u32(LOCAL_HEADER);
    u16(VERSION);
    u16(UTF8_FLAG);
    u16(STORED);
    u16(stamp.time);
    u16(stamp.date);
    u32(e.crc);
    u32(e.data.length);   // compressed size: stored, so the same
    u32(e.data.length);
    u16(e.nameBytes.length);
    u16(0);               // no extra field
    put(e.nameBytes);
    put(e.data);
  }

  const centralStart = at;
  entries.forEach((e, i) => {
    u32(CENTRAL_HEADER);
    u16(VERSION);         // made by: MS-DOS attributes, version 2.0
    u16(VERSION);
    u16(UTF8_FLAG);
    u16(STORED);
    u16(stamp.time);
    u16(stamp.date);
    u32(e.crc);
    u32(e.data.length);
    u32(e.data.length);
    u16(e.nameBytes.length);
    u16(0);               // extra field
    u16(0);               // comment
    u16(0);               // disk number
    u16(0);               // internal attributes
    u32(0);               // external attributes
    u32(offsets[i]);
    put(e.nameBytes);
  });

  const directorySize = at - centralStart;
  u32(END_OF_DIRECTORY);
  u16(0);                 // this disk
  u16(0);                 // the disk holding the directory
  u16(entries.length);
  u16(entries.length);
  u32(directorySize);
  u32(centralStart);
  u16(0);                 // no archive comment
  return out;
}
