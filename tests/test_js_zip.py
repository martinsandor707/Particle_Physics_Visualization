"""``static/js/zip.js``: the stored-zip writer and its CRC-32, read back by Python.

The Methodology page's Export button builds its archive with ``zipStore``, so
what is checked here is what an unzip will see:

* ``crc32`` is zlib's CRC-32, on the empty string, the standard check string
  and random bytes, and over a sub-range;
* the archive opens in ``zipfile``, ``testzip()`` finds no bad CRC, and every
  entry is STORED, flagged UTF-8, named and filled exactly as given, in order,
  with the given time as its MS-DOS timestamp (two-second resolution);
* a non-ASCII name survives, an empty file is allowed, and a duplicate,
  absolute or climbing name throws.

Skipped when ``node`` is not on the PATH.
"""

from __future__ import annotations

import base64
import io
import os
import zipfile
import zlib

import pytest
from test_js_physics_shell import JS, NODE, _run

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

_URL = (JS / "zip.js").as_uri()

_SCRIPT = r"""
const [url, samples, files] = JSON.parse(process.argv[1]);
const zip = await import(url);
const bytes = (b64) => new Uint8Array(Buffer.from(b64, 'base64'));
const out = {};
out.crc = samples.map((b64) => zip.crc32(bytes(b64)));
const check = new TextEncoder().encode('xx123456789yy');
out.crcRange = zip.crc32(check, 2, 11);
const archive = zip.zipStore(files.map(([name, b64]) => ({ name, bytes: bytes(b64) })),
  { date: new Date(2026, 9, 29, 14, 37, 51) });
out.archive = Buffer.from(archive).toString('base64');
out.refused = [];
for (const bad of [[{ name: 'a', bytes: new Uint8Array() }, { name: 'a', bytes: new Uint8Array() }],
  [{ name: '/abs', bytes: new Uint8Array() }], [{ name: 'x/../y', bytes: new Uint8Array() }], [{ name: '', bytes: new Uint8Array() }]]) {
  try { zip.zipStore(bad); out.refused.push(null); } catch (error) { out.refused.push(String(error.message)); }
}
console.log(JSON.stringify(out));
"""

_SAMPLES = [b"", b"123456789", b"The quick brown fox jumps over the lazy dog", os.urandom(5000)]
_FILES = [
    ("calosrv-methodology/methodology.tex", b"\\documentclass{article}\n"),
    ("calosrv-methodology/references.bib", b""),
    ("calosrv-methodology/figures/fig-ramps.png", os.urandom(70_000)),
    ("calosrv-methodology/figures/Sándor–ψ.svg", "<svg>ψ − 1</svg>".encode()),
]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@pytest.fixture(scope="module")
def result() -> dict:
    return _run(_SCRIPT, [_URL, [_b64(s) for s in _SAMPLES], [[n, _b64(d)] for n, d in _FILES]])


def test_crc32_is_zlibs(result):
    assert result["crc"] == [zlib.crc32(s) for s in _SAMPLES]
    assert result["crc"][1] == 0xCBF43926   # the standard check value
    assert result["crcRange"] == 0xCBF43926


def test_the_archive_reads_back_entry_for_entry(result):
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(result["archive"])))
    assert archive.testzip() is None
    infos = archive.infolist()
    assert [i.filename for i in infos] == [n for n, _ in _FILES]
    for info, (name, data) in zip(infos, _FILES):
        assert info.compress_type == zipfile.ZIP_STORED
        assert info.flag_bits & 0x0800, "the UTF-8 name flag"
        assert info.file_size == info.compress_size == len(data)
        assert info.CRC == zlib.crc32(data)
        assert info.date_time == (2026, 10, 29, 14, 37, 50)
        assert archive.read(name) == data


def test_bad_names_are_refused(result):
    duplicate, absolute, climbing, empty = result["refused"]
    assert duplicate and "duplicate" in duplicate
    assert absolute and climbing and empty
