/* ==========================================================================
   seahorse_phys.js -- model laminar profiles for the Seahorse tab
   (BARRY.shPhys).

   NOT recordings. Each event is a handful of current sinks and sources
   placed in the layers the literature puts them in; the probe's 64
   contacts read the layer they sit in, and the potential each contact
   would see is computed from that current source density with the usual
   disc model of a laminar structure:

       phi(z) = 1 / (2 sigma) * sum_z' C(z') (sqrt((z - z')^2 + R^2) - |z - z'|) dz

   (C > 0 a source, R the radius of the active disc; Nicholson & Freeman
   1975). So the picture is right in shape -- where the sink is, where the
   potential reverses -- and says nothing about amplitude. Every panel is
   labelled "model".
   ========================================================================== */
'use strict';

BARRY.shPhys = (function () {
  const ML = ['oml1', 'oml2'], MM = ['mml1', 'mml2'], GC = ['gcl1', 'gcl2'];
  /* comps: {layers, amp (sink < 0), t (ms), w (ms), osc (Hz), phase, burst} */
  const EVENTS = {
    ds1: {
      label: 'DS1', kind: 'ds', ms: 70, tok: '--call-ds',
      comps: [{ layers: ML, amp: -1.0, t: 24, w: 6.5 }, { layers: MM.concat(GC), amp: 0.42, t: 24, w: 7.5 }, { layers: ['hil'], amp: 0.12, t: 25, w: 8 }],
      say: 'A lateral perforant-path volley: a current sink in the outer molecular layer of both blades, the return current (source) toward the granule cells. In the hilus the field goes strongly positive.',
      refs: ['bragin1995', 'penttonen1997'], drives: [{ src: 'lec', t: 22 }, { src: 'burst', t: 27 }],
    },
    ds2: {
      label: 'DS2', kind: 'ds', ms: 70, tok: '--call-ds',
      comps: [{ layers: MM, amp: -1.25, t: 24, w: 6.5 }, { layers: ML.concat(GC), amp: 0.5, t: 24, w: 7.5 }, { layers: ['hil'], amp: 0.14, t: 25, w: 8 }],
      say: 'A medial perforant-path volley: the sink moves in to the middle third, flanked by sources in the outer third and the granule layer. Usually the larger dentate spike.',
      refs: ['bragin1995', 'penttonen1997'], drives: [{ src: 'mec', t: 22 }, { src: 'burst', t: 27 }],
    },
    swr: {
      label: 'Sharp-wave ripple', kind: 'swr', ms: 160, tok: '--accent',
      comps: [{ layers: ['ca1sr'], amp: -1.0, t: 72, w: 20 }, { layers: ['ca1sp', 'ca1so'], amp: 0.45, t: 72, w: 22 },
              { layers: ['ca1sp'], amp: 0.32, t: 72, w: 13, osc: 180 }],
      say: 'A CA3 population burst drives a sink in CA1 stratum radiatum (the sharp wave) while a 140-200 Hz ripple rides on stratum pyramidale.',
      refs: ['buzsaki2015', 'ylinen1995'], cells: ['ca3', 'ca1'], drives: [{ src: 'ca3', t: 62 }],
    },
    theta: {
      label: 'Theta', kind: 'theta', ms: 500, tok: '--accent',
      comps: [{ layers: ['ca1slm'].concat(ML), amp: -0.8, osc: 8, phase: 0 }, { layers: ['ca1sp', 'ca1so'], amp: 0.45, osc: 8, phase: 0 },
              { layers: ['hil', 'iml1', 'iml2'].concat(GC), amp: 0.18, osc: 70, phase: 0, thetaLocked: true }],
      say: 'Theta (6-10 Hz): alternating sinks at the distal dendrites (entorhinal input, near the fissure) and the cell bodies; the rhythm reverses across stratum radiatum and is largest near the fissure. Gamma rides on it in the dentate.',
      refs: ['buzsaki2002'], drives: [{ src: 'theta', t: 0 }, { src: 'theta', t: 125 }, { src: 'theta', t: 250 }, { src: 'theta', t: 375 }],
    },
    pspike: {
      label: 'P-spike', kind: 'pspike', ms: 220, tok: '--call-p',
      comps: [{ layers: ['ca3sr', 'ca3so', 'ca1sr', 'ca1so'], amp: -2.0, t: 70, w: 14 }, { layers: ['ca3sp', 'ca1sp'], amp: 0.9, t: 70, w: 16 },
              { layers: ['ca3sp', 'ca1sp'], amp: -0.7, t: 64, w: 1.6, burst: [0, 7, 14] }],
      say: 'A model interictal spike: a synchronous CA3 burst (where they start in slices; Wong & Traub 1983) with population spikes in the pyramidal layers and a large sink in radiatum and oriens. Replace with the lab\'s own P-spike profile once recordings are linked.',
      refs: ['wongtraub1983'], cells: ['ca3', 'ca3_b', 'ca1'],
    },
  };

  function envelope(c, t) {
    if (c.burst) {
      let v = 0;
      for (const d of c.burst) { const x = (t - c.t - d) / c.w; v += Math.exp(-x * x); }
      return v;
    }
    let v = c.t == null ? 1 : Math.exp(-Math.pow((t - c.t) / c.w, 2));
    if (c.osc) {
      if (c.thetaLocked) v *= 0.5 + 0.5 * Math.cos(2 * Math.PI * 8 * t / 1000);
      v *= Math.cos(2 * Math.PI * c.osc * t / 1000 + (c.phase || 0));
    }
    return v;
  }

  /* Your own event: sources switched on, each with a strength and an onset
     (ms). Each puts its sink where the presets put it. */
  function compose(sp) {
    const comps = [], drives = [], said = [], refs = new Set();
    let ms = 70;
    const on = (k) => sp[k] && sp[k].on && +sp[k].amp > 0;
    if (on('lec')) {
      const a = +sp.lec.amp, t = +sp.lec.t;
      comps.push({ layers: ML, amp: -1.0 * a, t, w: 6.5 }, { layers: MM.concat(GC), amp: 0.42 * a, t, w: 7.5 }, { layers: ['hil'], amp: 0.12 * a, t: t + 1, w: 8 });
      drives.push({ src: 'lec', t: Math.max(0, t - 2) }, { src: 'burst', t: t + 3 });
      said.push('LEC II at ' + t + ' ms'); refs.add('bragin1995'); ms = Math.max(ms, t + 46);
    }
    if (on('mec')) {
      const a = +sp.mec.amp, t = +sp.mec.t;
      comps.push({ layers: MM, amp: -1.25 * a, t, w: 6.5 }, { layers: ML.concat(GC), amp: 0.5 * a, t, w: 7.5 }, { layers: ['hil'], amp: 0.14 * a, t: t + 1, w: 8 });
      drives.push({ src: 'mec', t: Math.max(0, t - 2) }, { src: 'burst', t: t + 3 });
      said.push('MEC II at ' + t + ' ms'); refs.add('bragin1995'); ms = Math.max(ms, t + 46);
    }
    if (on('ca3')) {
      const a = +sp.ca3.amp, t = +sp.ca3.t;
      comps.push({ layers: ['ca1sr'], amp: -1.0 * a, t, w: 20 }, { layers: ['ca1sp', 'ca1so'], amp: 0.45 * a, t, w: 22 });
      drives.push({ src: 'ca3', t: Math.max(0, t - 10) });
      said.push('a CA3 burst at ' + t + ' ms'); refs.add('buzsaki2015'); ms = Math.max(ms, t + 80);
    }
    if (sp.ripple) {
      const t = on('ca3') ? +sp.ca3.t : 72;
      comps.push({ layers: ['ca1sp'], amp: 0.32 * (on('ca3') ? +sp.ca3.amp : 1), t, w: 13, osc: 180 });
      said.push('a ripple'); refs.add('ylinen1995'); ms = Math.max(ms, t + 60);
    }
    if (on('ec3')) {
      const a = +sp.ec3.amp, t = +sp.ec3.t;
      comps.push({ layers: ['ca1slm'], amp: -1.0 * a, t, w: 9 }, { layers: ['ca1sr'], amp: 0.35 * a, t, w: 10 });
      drives.push({ src: 'ec3', t: Math.max(0, t - 4) });
      said.push('EC III at ' + t + ' ms'); refs.add('buzsaki2002'); ms = Math.max(ms, t + 46);
    }
    if (sp.theta) {
      EVENTS.theta.comps.forEach((c) => comps.push(Object.assign({}, c)));
      ms = Math.max(ms, 500);
      for (let t = 0; t < ms; t += 125) drives.push({ src: 'theta', t });
      said.push('theta under it all'); refs.add('buzsaki2002');
    }
    if (!comps.length) return null;
    ms = Math.ceil(ms / 10) * 10;
    return { label: 'Your event', kind: 'custom', ms, comps, drives, custom: true, refs: [...refs],
             say: 'Your event: ' + said.join(', ') + '. Each source puts its sink in the layers the literature names for it.' };
  }
  /* The current source density in each layer at time t (ms). */
  function layerCsd(ev, t) {
    const out = new Map();
    for (const c of ev.comps) { const v = c.amp * envelope(c, t); for (const k of c.layers) out.set(k, (out.get(k) || 0) + v); }
    return out;
  }

  /* layers: the lamina key under each contact, contact 1 (nearest the tip)
     first; z: each contact's distance from the tip (um). */
  function compute(key, layers, z) {
    const ev = typeof key === 'string' ? EVENTS[key] : key;
    const n = layers.length;
    const dt = ev.ms > 300 ? 2 : 0.5;
    const T = Math.round(ev.ms / dt);
    const csd = new Float32Array(n * T), lfp = new Float32Array(n * T);
    for (let ti = 0; ti < T; ti++) {
      const t = ti * dt;
      for (let i = 0; i < n; i++) {
        let v = 0;
        for (const c of ev.comps) if (c.layers.includes(layers[i])) v += c.amp * envelope(c, t);
        csd[i * T + ti] = v;
      }
    }
    // forward model, R = 400 um
    const R = 400;
    const pitch = n > 1 ? Math.abs(z[1] - z[0]) : 20;
    let mx = 1e-9;
    for (let i = 0; i < n; i++) {
      for (let ti = 0; ti < T; ti++) {
        let v = 0;
        for (let j = 0; j < n; j++) {
          const c = csd[j * T + ti];
          if (!c) continue;
          const d = Math.abs(z[i] - z[j]);
          v += c * (Math.sqrt(d * d + R * R) - d) * pitch;
        }
        lfp[i * T + ti] = v;
        if (Math.abs(v) > mx) mx = Math.abs(v);
      }
    }
    for (let k = 0; k < lfp.length; k++) lfp[k] /= mx;
    let cm = 1e-9;
    for (let k = 0; k < csd.length; k++) cm = Math.max(cm, Math.abs(csd[k]));
    return { key, ev, n, T, dt, csd, lfp, cmax: cm, layers };
  }

  /* The panel: CSD as a colour sheet (red sink, blue source; contacts top
     to bottom from the shallowest), LFP traces over it, a time cursor. */
  function draw(cv, m, o) {
    o = o || {};
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const r = cv.getBoundingClientRect();
    const Wc = Math.max(10, Math.round(r.width * dpr)), Hc = Math.max(10, Math.round(r.height * dpr));
    if (cv.width !== Wc || cv.height !== Hc) { cv.width = Wc; cv.height = Hc; }
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, Wc, Hc);
    const padL = 54 * dpr, padR = 8 * dpr, padT = 6 * dpr, padB = 18 * dpr;
    const w = Wc - padL - padR, h = Hc - padT - padB;
    const n = m.n, T = m.T;
    const rowH = h / n;
    // CSD sheet
    const img = ctx.createImageData(Math.max(1, Math.round(w)), Math.max(1, Math.round(h)));
    const iw = img.width, ih = img.height;
    // the sink and source colors the stage paints with (so the panel and the sections agree)
    const rgb = (h, f) => { if (!h || h[0] !== '#') return f; const n = parseInt(h.slice(1, 7), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
    const SK = rgb(o.sink, [214, 54, 46]), SR = rgb(o.source, [46, 112, 214]);
    for (let y = 0; y < ih; y++) {
      const ci = n - 1 - Math.min(n - 1, Math.floor(y / ih * n));     // shallowest at the top
      for (let x = 0; x < iw; x++) {
        const ti = Math.min(T - 1, Math.floor(x / iw * T));
        const v = m.csd[ci * T + ti] / m.cmax;
        const a = Math.min(1, Math.abs(v)) * 0.85;
        const o2 = (y * iw + x) * 4;
        const c = v < 0 ? SK : SR;
        img.data[o2] = c[0]; img.data[o2 + 1] = c[1]; img.data[o2 + 2] = c[2];
        img.data[o2 + 3] = Math.round(a * 255);
      }
    }
    ctx.putImageData(img, padL, padT);
    // layer runs on the left
    const LC = o.layerColors || {};
    let i0 = 0;
    ctx.font = (10 * dpr) + 'px ' + (o.font || 'sans-serif');
    ctx.textBaseline = 'middle';
    for (let i = 1; i <= n; i++) {
      if (i < n && m.layers[i] === m.layers[i0]) continue;
      const k = m.layers[i0];
      const yTop = padT + (n - i) * rowH, yBot = padT + (n - i0) * rowH;
      ctx.fillStyle = LC[k] || 'rgba(128,128,128,0.4)';
      ctx.globalAlpha = k ? 0.9 : 0.25;
      ctx.fillRect(padL - 7 * dpr, yTop + 0.5, 5 * dpr, yBot - yTop - 1);
      ctx.globalAlpha = 1;
      if (yBot - yTop > 9 * dpr) {
        ctx.fillStyle = o.ink || '#888';
        ctx.textAlign = 'right';
        ctx.fillText((o.labelOf && o.labelOf(k)) || k || '', padL - 10 * dpr, (yTop + yBot) / 2);
      }
      i0 = i;
    }
    // LFP traces (every other contact)
    ctx.strokeStyle = o.ink || '#222';
    ctx.lineWidth = 1 * dpr;
    ctx.globalAlpha = 0.85;
    for (let ci = 0; ci < n; ci += 2) {
      const y0 = padT + (n - 1 - ci + 0.5) * rowH;
      ctx.beginPath();
      for (let ti = 0; ti < T; ti++) {
        const x = padL + ti / (T - 1) * w;
        const y = y0 - m.lfp[ci * T + ti] * rowH * 5;
        if (ti) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    // time axis + cursor
    ctx.fillStyle = o.ink || '#888';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.fillText('0', padL, Hc - 4 * dpr);
    ctx.textAlign = 'right';
    ctx.fillText(m.ev.ms + ' ms', padL + w, Hc - 4 * dpr);
    if (o.cursor != null) {
      const x = padL + Math.min(1, o.cursor / m.ev.ms) * w;
      ctx.strokeStyle = o.accent || '#e5a823';
      ctx.lineWidth = 2 * dpr;
      ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + h); ctx.stroke();
    }
  }

  return { EVENTS, compute, compose, layerCsd, draw };
})();
