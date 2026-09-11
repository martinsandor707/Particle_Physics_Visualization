/* Client-side controller.
 *
 * All geometry was resolved during the build: hits arrive as pre-quantised
 * integer cell indices, so the only work here is filtering event scalars,
 * accumulating the hit slices that pass, and handing matrices to plotly.
 *
 * Several plotly behaviours are load-bearing and easy to get wrong:
 *
 *  - Plotly.react compares data arrays by reference. Reusing a buffer and
 *    mutating it in place renders nothing unless layout.datarevision changes.
 *    REVISION is bumped once per frame in draw() so no panel can forget.
 *  - Heatmap z must be an array of rows, not a flat buffer. Row views are
 *    built once via subarray() and reused.
 *  - log10(0) is -Infinity, which a Float64Array cannot distinguish from a
 *    real value. Empty cells are written as NaN and hoverongaps is disabled so
 *    they render as background.
 *  - scaleanchor defaults to constrain:'range', which silently widens an axis
 *    to satisfy the aspect ratio, so the drawn extent stops matching the binned
 *    extent. Every spatial axis sets constrain:'domain'.
 *  - There is no logarithmic colour axis for heatmaps, so log10 is applied to
 *    the values and the colourbar ticks are formatted by hand.
 */
(function () {
  'use strict';

  var P = JSON.parse(document.getElementById('calodash-payload').textContent);
  var G = P.grid;
  var T = P.theme;

  // ---------------------------------------------------------------- decode

  function decode(field) {
    var binary = atob(field.b64);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    switch (field.dtype) {
      case '<u1': return bytes;
      case '<u2': return new Uint16Array(bytes.buffer);
      case '<i4': return new Int32Array(bytes.buffer);
      case '<f4': return new Float32Array(bytes.buffer);
      default: throw new Error('Unsupported dtype ' + field.dtype);
    }
  }

  var HIT = {
    ix: decode(P.hits.ix),
    iy: decode(P.hits.iy),
    iz: decode(P.hits.iz),
    e: decode(P.hits.energy)
  };
  var EV = {
    p: decode(P.events.p_true),
    theta: decode(P.events.theta),
    phi: decode(P.events.phi),
    n: decode(P.events.n_hits),
    eDep: decode(P.events.e_dep),
    eReco: decode(P.events.e_reco),
    entry: decode(P.events.entry_layer)
  };
  var N_EVENTS = P.events.count;
  var N_HITS = P.hits.count;

  // Hits are ordered by event, so each event owns a contiguous slice. The
  // start offsets are the exclusive prefix sum of the hit counts; computing
  // them here rather than shipping them saves a redundant array.
  var HIT_START = new Int32Array(N_EVENTS + 1);
  for (var e = 0; e < N_EVENTS; e++) HIT_START[e + 1] = HIT_START[e] + EV.n[e];

  // ----------------------------------------------------------------- grids

  var NXY = G.nXY, NZ = G.nZ, OUTSIDE = G.outside;
  var accXY = new Float64Array(NXY * NXY);
  var accYZ = new Float64Array(NXY * NZ);
  var accXZ = new Float64Array(NXY * NZ);
  var entryHist = new Float64Array(NZ + 1);
  var accept = new Float64Array(NZ);

  function rowViews(buffer, rows, cols) {
    var out = new Array(rows);
    for (var r = 0; r < rows; r++) out[r] = buffer.subarray(r * cols, (r + 1) * cols);
    return out;
  }
  var logXY = new Float64Array(NXY * NXY);
  var logYZ = new Float64Array(NXY * NZ);
  var logXZ = new Float64Array(NXY * NZ);
  var VIEW = {
    xy: rowViews(logXY, NXY, NXY),
    yz: rowViews(logYZ, NXY, NZ),
    xz: rowViews(logXZ, NXY, NZ)
  };

  var selectedEvents = new Int32Array(N_EVENTS);
  var bandAValues = new Float64Array(N_EVENTS);
  var bandATruth = new Float64Array(N_EVENTS);
  var bandBValues = new Float64Array(N_EVENTS);
  var bandBTruth = new Float64Array(N_EVENTS);
  var counts = { selected: 0, hits: 0, a: 0, b: 0 };

  // ------------------------------------------------------------- colormaps

  var TURBO = [
    [0.000, '#30123b'], [0.071, '#4145ab'], [0.143, '#4675ed'], [0.214, '#39a2fc'],
    [0.286, '#1bcfd4'], [0.357, '#24eca6'], [0.429, '#61fc6c'], [0.500, '#a4fc3b'],
    [0.571, '#d1e834'], [0.643, '#f3c63a'], [0.714, '#fe9b2d'], [0.786, '#f36315'],
    [0.857, '#d93806'], [0.929, '#b11901'], [1.000, '#7a0403']
  ];
  function colorscale(name) { return name === 'Turbo' ? TURBO : name; }

  // ------------------------------------------------------------- controls

  function $(id) { return document.getElementById(id); }

  function Dual(prefix, lo, hi, step, digits, unit) {
    var elLo = $(prefix + '-lo'), elHi = $(prefix + '-hi');
    var fill = $(prefix + '-fill'), out = $(prefix + '-readout');
    [elLo, elHi].forEach(function (el) {
      el.min = lo; el.max = hi; el.step = step;
    });
    elLo.value = lo; elHi.value = hi;

    function sync() {
      var a = parseFloat(elLo.value), b = parseFloat(elHi.value);
      if (a > b) { var t = a; a = b; b = t; }
      var span = hi - lo;
      fill.style.left = (100 * (a - lo) / span) + '%';
      fill.style.width = (100 * (b - a) / span) + '%';
      out.textContent = a.toFixed(digits) + ' – ' + b.toFixed(digits) + ' ' + unit;
    }
    function value() {
      var a = parseFloat(elLo.value), b = parseFloat(elHi.value);
      return a <= b ? [a, b] : [b, a];
    }
    [elLo, elHi].forEach(function (el) {
      el.addEventListener('input', function () { sync(); schedule(); });
    });
    sync();
    return { value: value, sync: sync, set: function (a, b) { elLo.value = a; elHi.value = b; sync(); } };
  }

  var R = P.ranges;
  var e1 = Dual('e1', R.p[0], R.p[1], 0.001, 3, 'GeV');
  var e2 = Dual('e2', R.p[0], R.p[1], 0.001, 3, 'GeV');
  var theta = Dual('theta', R.theta[0], R.theta[1], 0.001, 3, 'rad');
  var phi = Dual('phi', R.phi[0], R.phi[1], 0.001, 3, 'rad');

  // Opening bands come from quantiles of the truth spectrum (computed at build
  // time), so both land in the populated region and the panel opens on two
  // well-sampled, visibly distinct reference populations.
  e1.set(R.defaultA[0], R.defaultA[1]);
  e2.set(R.defaultB[0], R.defaultB[1]);

  $('minhits').max = R.maxHits;
  $('d-readout').textContent = 'N/A';

  var MODEL_CAPTIONS = {
    segmentation:
      'Separates overlapping showers into per-particle deposits. Its input is the ' +
      'energy density shown in the three spatial panels.',
    energy:
      'Regresses incident energy from the deposit pattern. Compare against the ' +
      'conventional calibrated-sum reconstruction in the fourth panel.',
    angle:
      'Estimates the incident direction. The dashed overlay is the observed ' +
      'energy-weighted shower axis, fitted from deposits — not extrapolated from ' +
      'truth angles, which a magnetic field makes unreliable here.'
  };

  function state() {
    var a = e1.value(), b = e2.value();
    return {
      a: a, b: b,
      theta: theta.value(),
      phi: phi.value(),
      minHits: Math.max(1, parseInt($('minhits').value, 10) || 1),
      excludeSeed: $('opt-exclude-seed').checked,
      normalise: $('opt-normalise').checked,
      frontOnly: $('opt-frontface').checked,
      residual: $('opt-residual').checked,
      cmap: $('colormap').value,
      model: document.querySelector('input[name="model"]:checked').value
    };
  }

  // ------------------------------------------------------------ accumulate

  function recompute(s) {
    accXY.fill(0); accYZ.fill(0); accXZ.fill(0);
    entryHist.fill(0);
    counts.selected = 0; counts.hits = 0; counts.a = 0; counts.b = 0;

    for (var i = 0; i < N_EVENTS; i++) {
      if (EV.n[i] < s.minHits) continue;
      if (s.frontOnly && EV.entry[i] !== 0) continue;
      var th = EV.theta[i];
      if (th < s.theta[0] || th > s.theta[1]) continue;
      var ph = EV.phi[i];
      if (ph < s.phi[0] || ph > s.phi[1]) continue;

      var p = EV.p[i];
      var inA = p >= s.a[0] && p <= s.a[1];
      var inB = p >= s.b[0] && p <= s.b[1];
      if (!inA && !inB) continue;

      if (inA) { bandAValues[counts.a] = EV.eReco[i]; bandATruth[counts.a] = p; counts.a++; }
      if (inB) { bandBValues[counts.b] = EV.eReco[i]; bandBTruth[counts.b] = p; counts.b++; }

      selectedEvents[counts.selected++] = i;
      entryHist[EV.entry[i]] += 1;

      var start = HIT_START[i], end = HIT_START[i + 1];
      for (var h = start; h < end; h++) {
        var ix = HIT.ix[h], iy = HIT.iy[h], iz = HIT.iz[h];
        var energy = HIT.e[h];
        counts.hits++;
        if (ix === OUTSIDE || iy === OUTSIDE) continue;
        if (!(s.excludeSeed && iz === 0)) accXY[iy * NXY + ix] += energy;
        accYZ[iy * NZ + iz] += energy;
        accXZ[ix * NZ + iz] += energy;
      }
    }

    // Acceptance per local depth layer. An event entering at global layer g can
    // reach at most local layer NZ-1-g, so the number of events able to
    // populate local layer L is the count with entry layer <= NZ-1-L.
    var running = 0;
    var prefix = new Float64Array(NZ + 1);
    for (var g = 0; g < NZ; g++) { running += entryHist[g]; prefix[g + 1] = running; }
    for (var L = 0; L < NZ; L++) accept[L] = prefix[NZ - L];
  }

  var LOG_FLOOR = P.color.floorLog;

  function toLog(source, target, rows, cols, scale, perColumn) {
    for (var r = 0; r < rows; r++) {
      for (var c = 0; c < cols; c++) {
        var idx = r * cols + c;
        var denom = perColumn ? (perColumn[c] > 0 ? perColumn[c] : 0) : scale;
        var v = denom > 0 ? source[idx] / denom : 0;
        // NaN, not -Infinity: an empty cell is absence of data, and plotly
        // renders gaps in the background colour when hoverongaps is off.
        target[idx] = v > 0 ? Math.max(Math.log10(v), LOG_FLOOR) : NaN;
      }
    }
  }

  // ------------------------------------------------------------- plotting

  var REVISION = 0;

  function baseLayout(xTitle, yTitle, xRange, yRange) {
    return {
      paper_bgcolor: T.card,
      plot_bgcolor: T.canvas,
      font: { color: T.text, size: 11, family: 'Inter, Segoe UI, system-ui, sans-serif' },
      margin: { l: 58, r: 12, t: 6, b: 46 },
      showlegend: false,
      hovermode: 'closest',
      datarevision: 0,
      xaxis: {
        title: { text: xTitle, font: { size: 11 } },
        range: xRange, autorange: false, constrain: 'domain',
        gridcolor: T.border, zerolinecolor: T.border, linecolor: T.border,
        tickfont: { size: 10, color: T.muted }
      },
      yaxis: {
        title: { text: yTitle, font: { size: 11 } },
        range: yRange, autorange: false, constrain: 'domain',
        scaleanchor: 'x', scaleratio: 1,
        gridcolor: T.border, zerolinecolor: T.border, linecolor: T.border,
        tickfont: { size: 10, color: T.muted }
      }
    };
  }

  function colorbar(title) {
    var ticks = [], labels = [];
    for (var d = Math.ceil(LOG_FLOOR); d <= 0; d++) {
      ticks.push(d);
      labels.push('10' + String(d).replace(/-/g, '⁻').replace(/[0-9]/g, function (n) {
        return '⁰¹²³⁴⁵⁶⁷⁸⁹'[+n];
      }));
    }
    return {
      title: { text: title, side: 'right', font: { size: 10 } },
      tickvals: ticks, ticktext: labels,
      tickfont: { size: 9, color: T.muted },
      thickness: 11, len: 0.92, outlinewidth: 0, bgcolor: 'rgba(0,0,0,0)'
    };
  }

  function heatmap(z, x0, dx, y0, dy, zmin, zmax, cmap, showscale, cbTitle, hoverX, hoverY) {
    return {
      type: 'heatmap', z: z,
      x0: x0, dx: dx, y0: y0, dy: dy,
      zmin: zmin, zmax: zmax, zauto: false,
      colorscale: colorscale(cmap),
      showscale: showscale,
      colorbar: showscale ? colorbar(cbTitle) : undefined,
      hoverongaps: false,
      hovertemplate: hoverX + ' %{x:.0f} mm<br>' + hoverY +
        ' %{y:.0f} mm<br>log₁₀ mean ΣE %{z:.2f}<extra></extra>'
    };
  }

  var XY_EXTENT = G.extentXY;
  var DEPTH_MAX = G.depthMax;
  // The depth panels use a narrower transverse window so that the 1:1 aspect
  // ratio yields a near-square panel: 1212 mm transverse against 1209.5 mm of
  // instrumented depth. |transverse| p99 is 610 mm, so almost nothing is lost.
  var DEPTH_TRANSVERSE = 12 * G.binXY;

  function fiducialShape() {
    return [{
      type: 'rect', xref: 'x', yref: 'y', layer: 'above',
      x0: 0, x1: DEPTH_MAX, y0: -DEPTH_TRANSVERSE, y1: -DEPTH_TRANSVERSE * 0.86,
      fillcolor: 'rgba(230,237,243,0.07)', line: { width: 0 }
    }];
  }

  function init() {
    var cmap = $('colormap').value;
    var half = G.binXY / 2;

    Plotly.newPlot('plot-xy', [
      heatmap(VIEW.xy, -XY_EXTENT + half, G.binXY, -XY_EXTENT + half, G.binXY,
        P.color.xy[0], P.color.xy[1], cmap, true, 'Mean ΣE per event [GeV]', 'x′', 'y′'),
      {
        type: 'scatter', mode: 'markers', name: 'Shower A entry',
        x: [0], y: [0], hoverinfo: 'skip',
        marker: { symbol: 'star', size: 15, color: T.showerA, line: { width: 1, color: T.canvas } }
      },
      {
        type: 'scatter', mode: 'markers', name: 'Shower B entry',
        x: [0], y: [0], hoverinfo: 'skip',
        marker: { symbol: 'star-open', size: 19, color: T.showerB, line: { width: 2 } }
      }
    ], (function () {
      var l = baseLayout('x′ (mm)', 'y′ (mm)', [-XY_EXTENT, XY_EXTENT], [-XY_EXTENT, XY_EXTENT]);
      // Placed in the corner rather than at the origin, where it would sit on
      // top of the shower core it is describing.
      l.annotations = [{
        x: 0.02, y: 0.98, xref: 'paper', yref: 'paper',
        xanchor: 'left', yanchor: 'top',
        text: 'Separation D = N/A — single isolated shower',
        showarrow: false, font: { size: 9.5, color: T.muted },
        bgcolor: 'rgba(13,17,23,0.7)', borderpad: 3
      }];
      return l;
    })(), { displayModeBar: false, responsive: true });

    ['yz', 'xz'].forEach(function (key) {
      var isY = key === 'yz';
      Plotly.newPlot('plot-' + key, [
        heatmap(VIEW[key], 0, G.binZ, -XY_EXTENT + half, G.binXY,
          P.color[key][0], P.color[key][1], cmap, true,
          'Mean ΣE per event [GeV]', 'depth z′', isY ? 'y′' : 'x′'),
        {
          type: 'scatter', mode: 'lines', name: 'Observed shower axis',
          x: [0, DEPTH_MAX],
          y: [0, DEPTH_MAX * (isY ? P.axis.slopeY : P.axis.slopeX)],
          hoverinfo: 'skip',
          line: { color: T.showerA, width: 1.4, dash: 'dash' }
        }
      ], (function () {
        var l = baseLayout('Depth z′ (mm)', (isY ? 'y′' : 'x′') + ' (mm)',
          [0, DEPTH_MAX], [-DEPTH_TRANSVERSE, DEPTH_TRANSVERSE]);
        l.shapes = fiducialShape();
        l.annotations = [{
          x: DEPTH_MAX / 2, y: -DEPTH_TRANSVERSE * 0.93, xref: 'x', yref: 'y',
          text: 'Calorimeter active region — ' + G.nZ + ' layers @ ' +
            G.binZ.toFixed(1) + ' mm', showarrow: false,
          font: { size: 9, color: T.muted }
        }];
        return l;
      })(), { displayModeBar: false, responsive: true });
    });

    Plotly.newPlot('plot-energy', [], {
      paper_bgcolor: T.card, plot_bgcolor: T.canvas,
      font: { color: T.text, size: 11, family: 'Inter, Segoe UI, system-ui, sans-serif' },
      margin: { l: 58, r: 12, t: 6, b: 46 },
      datarevision: 0,
      legend: { font: { size: 9.5 }, bgcolor: 'rgba(13,17,23,0.75)', x: 0.02, y: 0.98 },
      xaxis: { gridcolor: T.border, linecolor: T.border, tickfont: { size: 10, color: T.muted } },
      yaxis: { gridcolor: T.border, linecolor: T.border, tickfont: { size: 10, color: T.muted },
               rangemode: 'tozero' }
    }, { displayModeBar: false, responsive: true });
  }

  // ------------------------------------------------- reconstruction panel
  //
  // These estimators mirror calodash/stats.py, which transcribes them from
  // plan-viz.ipynb. Keep the two implementations in step.

  function describe(values, count, lo, hi) {
    var kept = [], i;
    for (i = 0; i < count; i++) {
      if (values[i] >= lo && values[i] <= hi) kept.push(values[i]);
    }
    if (kept.length < 10) return null;
    var sum = 0;
    for (i = 0; i < kept.length; i++) sum += kept[i];
    var mu = sum / kept.length;
    var acc = 0;
    for (i = 0; i < kept.length; i++) acc += (kept[i] - mu) * (kept[i] - mu);
    var sigma = Math.sqrt(acc / kept.length);   // ddof = 0, as in the notebook
    return { values: kept, n: kept.length, mu: mu, sigma: sigma };
  }

  function histogram(values, lo, hi, bins) {
    var counts = new Float64Array(bins), width = (hi - lo) / bins, i;
    for (i = 0; i < values.length; i++) {
      var b = Math.floor((values[i] - lo) / width);
      if (b === bins) b = bins - 1;
      if (b >= 0 && b < bins) counts[b]++;
    }
    var centres = new Float64Array(bins), density = new Float64Array(bins);
    var norm = values.length * width;
    for (i = 0; i < bins; i++) {
      centres[i] = lo + (i + 0.5) * width;
      density[i] = norm > 0 ? counts[i] / norm : 0;
    }
    return { x: Array.from(centres), y: Array.from(density) };
  }

  function gaussianCurve(mu, sigma, lo, hi, points) {
    var x = [], y = [], amp = 1 / (sigma * Math.sqrt(2 * Math.PI));
    for (var i = 0; i < points; i++) {
      var v = lo + (hi - lo) * i / (points - 1);
      x.push(v);
      y.push(amp * Math.exp(-0.5 * Math.pow((v - mu) / sigma, 2)));
    }
    return { x: x, y: y };
  }

  function drawEnergy(s) {
    var lo = s.residual ? -1 : 0;
    var hi = s.residual ? 4 : P.energy.max;
    var label = s.residual
      ? 'Fractional residual (E_reco − p) / p'
      : 'Reconstructed energy (GeV)';

    var aVals = bandAValues, bVals = bandBValues;
    if (s.residual) {
      aVals = new Float64Array(counts.a); bVals = new Float64Array(counts.b);
      for (var i = 0; i < counts.a; i++) aVals[i] = bandAValues[i] / bandATruth[i] - 1;
      for (var j = 0; j < counts.b; j++) bVals[j] = bandBValues[j] / bandBTruth[j] - 1;
    }

    var bands = [
      { key: 'A', color: T.showerA, values: aVals, n: counts.a, truth: bandATruth },
      { key: 'B', color: T.showerB, values: bVals, n: counts.b, truth: bandBTruth }
    ];

    var traces = [], rows = [], peak = 0;
    bands.forEach(function (band) {
      var stats = describe(band.values, band.n, lo, hi);
      if (!stats) { rows.push({ key: band.key, color: band.color, stats: null }); return; }

      // Binned density, drawn faintly behind the fitted curve and kept out of
      // the legend so the key stays readable.
      var h = histogram(stats.values, lo, hi, P.energy.bins);
      traces.push({
        type: 'scatter', mode: 'lines', showlegend: false,
        x: h.x, y: h.y, line: { shape: 'hvh', width: 1.1, color: band.color },
        opacity: 0.4, hoverinfo: 'skip'
      });

      // A degenerate selection (every event identical) would divide by zero in
      // the Gaussian; the histogram alone still describes it correctly.
      if (stats.sigma > 0) {
        peak = Math.max(peak, 1 / (stats.sigma * Math.sqrt(2 * Math.PI)));
        var g = gaussianCurve(stats.mu, stats.sigma, lo, hi, 400);
        traces.push({
          type: 'scatter', mode: 'lines',
          name: 'Isolated reference (no overlap) — band ' + band.key,
          x: g.x, y: g.y, line: { width: 2.2, color: band.color },
          hovertemplate: '%{x:.3f}<br>density %{y:.3f}<extra></extra>'
        });
      }

      // Truth marker. Drawn as a vertical line rather than a probability
      // density: within a narrow selection the truth spectrum is far narrower
      // than the reconstruction, so as a PDF it would tower an order of
      // magnitude above the curves it is meant to be compared against and
      // flatten them to nothing. A line answers the same question -- where
      // should the reconstruction peak -- without distorting the density axis.
      var truthMu = 0;
      if (!s.residual) {
        var t = 0, count = 0;
        for (var q = 0; q < band.n; q++) { t += band.truth[q]; count++; }
        truthMu = count ? t / count : 0;
      }
      band.truthMu = truthMu;
      rows.push({ key: band.key, color: band.color, stats: stats, truthMu: truthMu });
    });

    var yTop = peak > 0 ? peak * 1.25 : 1;
    rows.forEach(function (row) {
      if (!row.stats) return;
      traces.push({
        type: 'scatter', mode: 'lines',
        name: s.residual
          ? 'Perfect reconstruction — band ' + row.key
          : 'True incident energy ⟨p⟩ = ' + row.truthMu.toFixed(3) + ' GeV — band ' + row.key,
        x: [row.truthMu, row.truthMu], y: [0, yTop], hoverinfo: 'skip',
        line: { width: 1.4, color: row.color, dash: 'dash' }, opacity: 0.8
      });
    });

    // Legend-only placeholder. The AI series is absent from the input schema
    // and is never synthesised; showing the empty slot keeps the comparison the
    // panel exists to make legible.
    traces.push({
      type: 'scatter', mode: 'lines', x: [null], y: [null],
      name: 'AI-based reconstruction — PENDING RUNS',
      line: { width: 2, color: T.disabled, dash: 'dashdot' }, hoverinfo: 'skip'
    });

    Plotly.react('plot-energy', traces, {
        paper_bgcolor: T.card, plot_bgcolor: T.canvas,
        font: { color: T.text, size: 11, family: 'Inter, Segoe UI, system-ui, sans-serif' },
        margin: { l: 58, r: 12, t: 6, b: 46 },
        datarevision: REVISION,
        legend: { font: { size: 9.5 }, bgcolor: 'rgba(13,17,23,0.8)',
                  x: 0.985, y: 0.985, xanchor: 'right', yanchor: 'top',
                  bordercolor: T.border, borderwidth: 1 },
        xaxis: {
          title: { text: label, font: { size: 11 } }, range: [lo, hi], autorange: false,
          gridcolor: T.border, linecolor: T.border, zerolinecolor: T.border,
          tickfont: { size: 10, color: T.muted }
        },
        yaxis: {
          title: { text: 'Probability density', font: { size: 11 } },
          // Scaled to the reconstruction curves and anchored at zero
          // (CLAUDE.md section 2: densities start strictly at zero).
          range: [0, yTop], autorange: false,
          gridcolor: T.border, linecolor: T.border,
          tickfont: { size: 10, color: T.muted }
        }
      });

    renderInset(rows, s);
    return rows;
  }

  function renderInset(rows, s) {
    var unit = s.residual ? '' : ' GeV';
    var html = '<table><tr><th class="name" style="text-align:left">Fitted parameters</th>' +
      '<th>μ' + unit + '</th><th>σ' + unit + '</th><th>σ/μ</th>' +
      (s.residual ? '<th>—</th>' : '<th>⟨p⟩ truth</th>') +
      (s.residual ? '<th>—</th>' : '<th>response</th>') + '<th>N</th></tr>';
    rows.forEach(function (row) {
      var st = row.stats;
      html += '<tr><td class="name"><span class="swatch" style="background:' +
        row.color + '"></span>Band ' + row.key + '</td>';
      if (!st) {
        html += '<td colspan="6">insufficient events in range</td></tr>';
        return;
      }
      html += '<td>' + st.mu.toFixed(3) + '</td><td>' + st.sigma.toFixed(3) + '</td>' +
        '<td>' + (st.mu !== 0 ? (100 * st.sigma / Math.abs(st.mu)).toFixed(1) + '%' : '—') + '</td>';
      html += s.residual
        ? '<td>—</td><td>—</td>'
        : '<td>' + row.truthMu.toFixed(3) + '</td><td>' +
          (row.truthMu ? (st.mu / row.truthMu).toFixed(3) : '—') + '</td>';
      html += '<td>' + st.n.toLocaleString() + '</td></tr>';
    });
    html += '</table>';
    $('inset-table').innerHTML = html;

    $('foot-energy').innerHTML = s.residual
      ? 'Fractional residual per event. This is the quantity that measures ' +
        'resolution: the absolute scale cannot, because a single global sampling ' +
        'fraction fitted on this sample forces ⟨E<sub>reco</sub>⟩ = ⟨p⟩ across the ' +
        'whole population by construction. The dashed line marks a perfect reconstruction.'
      : 'Conventional reconstruction: E<sub>reco</sub> = ΣE<sub>hit</sub> / f, with ' +
        'f = ' + P.calibration.f.toFixed(6) + ' fitted from this dataset. Every event here ' +
        'is isolated, so these curves <em>are</em> the no-overlap reference; the dashed ' +
        'verticals mark the true incident energy, and the gap to each peak is the response ' +
        'non-linearity of a single global calibration. μ and σ are moment estimates over ' +
        'the in-range subset, following plan-viz.ipynb.';
  }

  // ------------------------------------------------------------- KPI cards

  function renderKPIs(rows, s) {
    var a = rows[0] && rows[0].stats, b = rows[1] && rows[1].stats;
    // The counts quoted here are the in-range subset the moments were taken
    // over, matching the inset table. They can sit just below the status bar's
    // selection count, which includes events past the axis maximum.
    var cards = [
      { label: 'E₁ band response', value: a ? a.mu.toFixed(3) + ' GeV' : '—',
        sub: a ? a.n.toLocaleString() + ' events in range' : 'no events in band' },
      { label: 'E₂ band response', value: b ? b.mu.toFixed(3) + ' GeV' : '—',
        sub: b ? b.n.toLocaleString() + ' events in range' : 'no events in band' },
      { label: 'Resolution σ/μ (E₁)', value: a ? (100 * a.sigma / a.mu).toFixed(1) + '%' : '—',
        sub: 'conventional reconstruction' },
      { label: 'Resolution σ/μ (E₂)', value: b ? (100 * b.sigma / b.mu).toFixed(1) + '%' : '—',
        sub: 'conventional reconstruction' },
      { label: 'Separation D', value: 'N/A', sub: 'single-particle dataset', pending: true },
      { label: 'Predicted energy residual', value: 'PENDING RUNS',
        sub: 'no model outputs in schema', pending: true }
    ];
    $('kpis').innerHTML = cards.map(function (c) {
      return '<div class="kpi' + (c.pending ? ' pending' : '') + '">' +
        '<div class="label">' + c.label + '</div>' +
        '<div class="value">' + c.value + '</div>' +
        '<div class="sub">' + c.sub + '</div></div>';
    }).join('');

    var metrics = [];
    if (s.model === 'segmentation') {
      metrics = [
        ['Shower separation IoU', null], ['Cluster purity', null],
        ['Assigned energy fraction', null]
      ];
    } else if (s.model === 'energy') {
      metrics = [
        ['Conventional σ/μ (E₁)', a ? (100 * a.sigma / a.mu).toFixed(1) + '%' : '—'],
        ['Conventional σ/μ (E₂)', b ? (100 * b.sigma / b.mu).toFixed(1) + '%' : '—'],
        ['Sampling fraction f', P.calibration.f.toFixed(6)],
        ['AI energy residual', null], ['AI confidence', null]
      ];
    } else {
      metrics = [
        ['Observed axis slope dx/dz', P.axis.slopeX.toFixed(4)],
        ['Observed axis slope dy/dz', P.axis.slopeY.toFixed(4)],
        ['AI angular residual', null], ['AI confidence', null]
      ];
    }
    $('metrics').innerHTML = metrics.map(function (m) {
      return '<div class="metric"><span class="k">' + m[0] + '</span>' +
        (m[1] === null
          ? '<span class="v pending">PENDING RUNS</span>'
          : '<span class="v">' + m[1] + '</span>') + '</div>';
    }).join('');

    $('model-caption').textContent = MODEL_CAPTIONS[s.model];
  }

  // ----------------------------------------------------------------- draw

  function draw() {
    var s = state();
    recompute(s);

    var perEvent = counts.selected > 0 ? counts.selected : 1;
    toLog(accXY, logXY, NXY, NXY, perEvent, null);
    toLog(accYZ, logYZ, NXY, NZ, perEvent, s.normalise ? accept : null);
    toLog(accXZ, logXZ, NXY, NZ, perEvent, s.normalise ? accept : null);

    REVISION++;
    var cmap = colorscale(s.cmap);

    // restyle rather than react for the heatmaps. Plotly.react compares data
    // arrays by reference, so mutating a reused buffer in place would render
    // nothing without also bumping layout.datarevision; restyle bypasses that
    // diffing entirely and costs one pass instead of a react plus a relayout.
    Plotly.restyle('plot-xy', { z: [VIEW.xy], colorscale: [cmap] }, [0]);
    Plotly.restyle('plot-yz', { z: [VIEW.yz], colorscale: [cmap] }, [0]);
    Plotly.restyle('plot-xz', { z: [VIEW.xz], colorscale: [cmap] }, [0]);

    var rows = drawEnergy(s);
    renderKPIs(rows, s);

    $('stat-events').textContent = counts.selected.toLocaleString() + ' / ' + N_EVENTS.toLocaleString();
    $('stat-hits').textContent = counts.hits.toLocaleString() + ' / ' + N_HITS.toLocaleString();
    $('stat-a').textContent = counts.a.toLocaleString();
    $('stat-b').textContent = counts.b.toLocaleString();
    $('stat-f').textContent = P.calibration.f.toFixed(6);

    $('foot-xy').innerHTML =
      'Energies summed per transverse cell with z collapsed to the entrance plane, ' +
      'averaged over selected events. Bins are ' + G.binXY.toFixed(1) + ' mm — the ' +
      'detector cell pitch; finer bins alias against the staggered lattice. ' +
      (s.excludeSeed
        ? '<b>Entry layer excluded.</b> Compare with it enabled to see the artifact.'
        : '<b>Note:</b> ' + (100 * P.artifacts.singleEntryFraction).toFixed(1) +
          '% of events deposit a single hit in their entry layer, so recentring pins ' +
          'that hit to exactly (0, 0) by construction — ' +
          (100 * P.artifacts.originHitFraction).toFixed(1) + '% of all hits sit at the ' +
          'origin for that reason rather than a physical one.');
  }

  // Range inputs fire at pointer-move rate. Coalescing on animation frames
  // renders once per frame from the freshest state, which stays responsive
  // where a timeout-based debounce would feel laggy.
  var pending = false;
  function schedule() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () { pending = false; draw(); });
  }

  // ---------------------------------------------------------------- export

  function exportCSV() {
    var s = state();
    var lines = ['event_index,incident_momentum_GeV,theta_rad,phi_rad,n_hits,' +
                 'deposited_energy_GeV,reconstructed_energy_GeV,fractional_residual,entry_layer,band'];
    for (var k = 0; k < counts.selected; k++) {
      var i = selectedEvents[k];
      var p = EV.p[i];
      var inA = p >= s.a[0] && p <= s.a[1];
      var inB = p >= s.b[0] && p <= s.b[1];
      lines.push([
        i, p.toPrecision(8), EV.theta[i].toPrecision(8), EV.phi[i].toPrecision(8),
        EV.n[i], EV.eDep[i].toPrecision(8), EV.eReco[i].toPrecision(8),
        (EV.eReco[i] / p - 1).toPrecision(8), EV.entry[i],
        inA && inB ? 'A+B' : (inA ? 'A' : 'B')
      ].join(','));
    }
    var blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = 'filtered_events.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    // Revoking synchronously races the download in Firefox.
    setTimeout(function () { URL.revokeObjectURL(url); }, 0);
  }

  // ------------------------------------------------------------------ wire

  ['minhits', 'opt-exclude-seed', 'opt-normalise', 'opt-frontface',
   'opt-residual', 'colormap'].forEach(function (id) {
    $(id).addEventListener('input', schedule);
    $(id).addEventListener('change', schedule);
  });
  Array.prototype.forEach.call(
    document.querySelectorAll('input[name="model"]'),
    function (el) { el.addEventListener('change', schedule); });
  $('export').addEventListener('click', exportCSV);
  window.addEventListener('resize', function () {
    ['plot-xy', 'plot-yz', 'plot-xz', 'plot-energy'].forEach(function (id) {
      Plotly.Plots.resize($(id));
    });
  });

  $('dataset-name').textContent = P.meta.dataset;
  init();
  draw();
})();
