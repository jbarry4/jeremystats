/* ==========================================================================
   seahorse3d.js -- the 3D stage of the Seahorse tab (an ES module).

   Imported by seahorse.js the first time 3D is opened, so three.js costs
   nothing to anyone who never looks. Nothing here fetches: seahorse.js
   loads and unpacks the blobs and hands this module typed arrays.

   World frame: millimetres, X = right (CCF ML - 5700 um), Y = dorsal
   (4000 - DV), Z = posterior (AP - 6600). Right-handed, so the brain is
   never drawn mirrored.

   It renders only when something changed or something is moving: a still
   brain costs no frames, and Jarvis Light / reduced motion stop the pulses.
   ========================================================================== */
import * as THREE from '../vendor/three/three.module.min.js';
import { OrbitControls } from '../vendor/three/OrbitControls.js';

export const W = (ap, dv, ml) => [(ml - 5700) / 1000, (4000 - dv) / 1000, (ap - 6600) / 1000];

function rimMaterial(color, opacity) {
  return new THREE.ShaderMaterial({
    uniforms: { color: { value: new THREE.Color(color) }, opacity: { value: opacity },
                dim: { value: 1.0 } },
    vertexShader: `
      varying vec3 vN; varying vec3 vV;
      #include <clipping_planes_pars_vertex>
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
        #include <clipping_planes_vertex>
      }`,
    fragmentShader: `
      uniform vec3 color; uniform float opacity; uniform float dim;
      varying vec3 vN; varying vec3 vV;
      #include <clipping_planes_pars_fragment>
      void main() {
        #include <clipping_planes_fragment>
        float rim = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.2);
        gl_FragColor = vec4(color * (0.55 + 0.6 * rim), (opacity * 0.35 + opacity * 1.6 * rim) * dim);
      }`,
    transparent: true, depthWrite: false, side: THREE.DoubleSide, clipping: true,
  });
}

/* A soft travelling glow along an arbor: each vertex knows its path length
   from the soma; a band of light moves outward. */
function pulseMaterial(color) {
  return new THREE.ShaderMaterial({
    uniforms: { color: { value: new THREE.Color(color) }, t: { value: -1 }, base: { value: 0.55 },
                width: { value: 120 } },
    vertexShader: `
      attribute float plen; varying float vL;
      #include <clipping_planes_pars_vertex>
      void main() { vL = plen; vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_Position = projectionMatrix * mv;
        #include <clipping_planes_vertex>
      }`,
    fragmentShader: `
      uniform vec3 color; uniform float t; uniform float base; uniform float width; varying float vL;
      #include <clipping_planes_pars_fragment>
      void main() {
        #include <clipping_planes_fragment>
        float g = t < 0.0 ? 0.0 : exp(-pow((vL - t) / width, 2.0));
        gl_FragColor = vec4(mix(color, vec3(1.0), g * 0.75), base + g * (1.0 - base));
      }`,
    transparent: true, depthWrite: false, clipping: true,
  });
}

function meshFromBlob(pos16, idx) {
  const n = pos16.length / 3;
  const p = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const w = W(pos16[i * 3] * 10, pos16[i * 3 + 1] * 10, pos16[i * 3 + 2] * 10);
    p[i * 3] = w[0]; p[i * 3 + 1] = w[1]; p[i * 3 + 2] = w[2];
  }
  // Make the winding point outward whatever the source did (signed volume).
  let vol = 0;
  for (let t = 0; t < idx.length; t += 3) {
    const a = idx[t] * 3, b = idx[t + 1] * 3, c = idx[t + 2] * 3;
    vol += p[a] * (p[b + 1] * p[c + 2] - p[b + 2] * p[c + 1])
         - p[a + 1] * (p[b] * p[c + 2] - p[b + 2] * p[c])
         + p[a + 2] * (p[b] * p[c + 1] - p[b + 1] * p[c]);
  }
  const I = idx.length > 65535 * 3 || n > 65535 ? new Uint32Array(idx) : new Uint16Array(idx);
  if (vol < 0) for (let t = 0; t < I.length; t += 3) { const s = I[t + 1]; I[t + 1] = I[t + 2]; I[t + 2] = s; }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(p, 3));
  g.setIndex(new THREE.BufferAttribute(I, 1));
  g.computeVertexNormals();
  g.computeBoundingBox();
  g.computeBoundingSphere();
  return g;
}

/* Tubes for dendrites (a 5-sided prism per segment, merged), lines for the
   axon (with path length for the pulse), a sphere for the soma. */
function buildCell(cell, arr, color) {
  const P = arr.p, T = arr.t, R = arr.r, A = arr.a;
  const n = T.length;
  const w = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const v = W(P[i * 3], P[i * 3 + 1], P[i * 3 + 2]);
    w[i * 3] = v[0]; w[i * 3 + 1] = v[1]; w[i * 3 + 2] = v[2];
  }
  const plen = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const p = A[i];
    if (p < 0) continue;
    const dx = P[i * 3] - P[p * 3], dy = P[i * 3 + 1] - P[p * 3 + 1], dz = P[i * 3 + 2] - P[p * 3 + 2];
    plen[i] = plen[p] + Math.sqrt(dx * dx + dy * dy + dz * dz);
  }
  const group = new THREE.Group();
  group.userData = { kind: 'cell', key: cell.key };
  // dendrites
  const SIDES = 5;
  const dpos = [], didx = [];
  const tmp = new THREE.Vector3(), a = new THREE.Vector3(), b = new THREE.Vector3();
  const u = new THREE.Vector3(), v = new THREE.Vector3(), d = new THREE.Vector3();
  for (let i = 0; i < n; i++) {
    const p = A[i];
    if (p < 0 || (T[i] !== 3 && T[i] !== 4)) continue;
    a.set(w[p * 3], w[p * 3 + 1], w[p * 3 + 2]);
    b.set(w[i * 3], w[i * 3 + 1], w[i * 3 + 2]);
    d.subVectors(b, a);
    if (d.lengthSq() < 1e-12) continue;
    d.normalize();
    tmp.set(Math.abs(d.x) < 0.9 ? 1 : 0, Math.abs(d.x) < 0.9 ? 0 : 1, 0);
    u.crossVectors(d, tmp).normalize();
    v.crossVectors(d, u);
    const ra = Math.max(0.0006, Math.min(0.004, (R[p] || 0.6) / 1000 * 0.9));
    const rb = Math.max(0.0005, Math.min(0.004, (R[i] || 0.5) / 1000 * 0.9));
    const base = dpos.length / 3;
    for (let k = 0; k < SIDES; k++) {
      const ang = (k / SIDES) * Math.PI * 2, c = Math.cos(ang), s = Math.sin(ang);
      dpos.push(a.x + (u.x * c + v.x * s) * ra, a.y + (u.y * c + v.y * s) * ra, a.z + (u.z * c + v.z * s) * ra);
      dpos.push(b.x + (u.x * c + v.x * s) * rb, b.y + (u.y * c + v.y * s) * rb, b.z + (u.z * c + v.z * s) * rb);
    }
    for (let k = 0; k < SIDES; k++) {
      const k2 = (k + 1) % SIDES;
      const a0 = base + k * 2, b0 = a0 + 1, a1 = base + k2 * 2, b1 = a1 + 1;
      didx.push(a0, a1, b0, b0, a1, b1);
    }
  }
  if (dpos.length) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(dpos, 3));
    g.setIndex(dpos.length / 3 > 65535 ? new THREE.Uint32BufferAttribute(didx, 1) : new THREE.Uint16BufferAttribute(didx, 1));
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color, roughness: 0.45, metalness: 0.05,
      emissive: new THREE.Color(color).multiplyScalar(0.18) }));
    m.userData = { kind: 'cell', key: cell.key, part: 'dend' };
    group.add(m);
  }
  // axon
  const apos = [], apl = [];
  for (let i = 0; i < n; i++) {
    const p = A[i];
    if (p < 0 || T[i] !== 2) continue;
    apos.push(w[p * 3], w[p * 3 + 1], w[p * 3 + 2], w[i * 3], w[i * 3 + 1], w[i * 3 + 2]);
    apl.push(plen[p], plen[i]);
  }
  if (apos.length) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(apos, 3));
    g.setAttribute('plen', new THREE.Float32BufferAttribute(apl, 1));
    const m = new THREE.LineSegments(g, pulseMaterial(new THREE.Color(color).lerp(new THREE.Color('#ffffff'), 0.25)));
    m.userData = { kind: 'cell', key: cell.key, part: 'axon', maxlen: apl.reduce((x, y) => Math.max(x, y), 0) };
    group.add(m);
  }
  // soma
  const sv = W(cell.soma_um[0], cell.soma_um[1], cell.soma_um[2]);
  const sm = new THREE.Mesh(new THREE.SphereGeometry(0.009, 20, 14),
    new THREE.MeshStandardMaterial({ color, roughness: 0.3, emissive: new THREE.Color(color).multiplyScalar(0.35) }));
  sm.position.set(sv[0], sv[1], sv[2]);
  sm.userData = { kind: 'cell', key: cell.key, part: 'soma' };
  group.add(sm);
  group.userData.soma = sm.position.clone();
  return group;
}

export function create(host, opts) {
  const onPick = opts.onPick || (() => {});
  const reduced = () => (window.BARRY && BARRY.ui && BARRY.ui.reducedMotion && BARRY.ui.reducedMotion())
    || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: false });
  renderer.localClippingEnabled = true;
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  host.appendChild(renderer.domElement);
  renderer.domElement.className = 'sh3-canvas';
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 200);
  camera.position.set(9, 7, 13);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.12;
  controls.target.set(0, 0, 0);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.1));
  const key = new THREE.DirectionalLight(0xffffff, 1.5);
  key.position.set(4, 8, -6);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.5);
  fill.position.set(-6, -2, 6);
  scene.add(fill);

  const groups = { brain: new THREE.Group(), hpf: new THREE.Group(), lamina: new THREE.Group(),
                   cells: new THREE.Group(), fx: new THREE.Group(), probe: new THREE.Group() };
  Object.values(groups).forEach((g) => scene.add(g));
  const byKey = { brain: {}, hpf: {}, lamina: {}, cells: {} };
  const slabPlanes = [new THREE.Plane(new THREE.Vector3(0, 0, 1), 0), new THREE.Plane(new THREE.Vector3(0, 0, -1), 0)];
  let slabOn = false;
  let dirty = true;
  let raf = 0;
  let running = false;
  const anims = new Set();
  let level = 'brain';
  let facePlane = null;

  function size() {
    const r = host.getBoundingClientRect();
    const w = Math.max(10, r.width), h = Math.max(10, r.height);
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    dirty = true;
  }
  const ro = new ResizeObserver(size);
  ro.observe(host);
  size();
  controls.addEventListener('change', () => { dirty = true; });

  function frame(now) {
    raf = 0;
    if (!running) return;
    const moving = controls.update();
    for (const a of Array.from(anims)) {
      if (a(now) === false) anims.delete(a);
      dirty = true;
    }
    if (dirty || moving) { renderer.render(scene, camera); dirty = false; }
    raf = requestAnimationFrame(frame);
  }
  function start() { if (!running) { running = true; raf = requestAnimationFrame(frame); } }
  function stop() { running = false; if (raf) cancelAnimationFrame(raf); raf = 0; }
  start();

  function theme(colors) {
    const shell = byKey.brain.root;
    if (shell) shell.material.uniforms.color.value.set(colors.shell);
    dirty = true;
  }

  function addBrain(blob) {
    for (const m of blob.header.meshes) {
      const g = meshFromBlob(blob.arrays['p:' + m.key], blob.arrays['i:' + m.key]);
      const isRoot = m.key === 'root';
      const mat = rimMaterial(isRoot ? opts.colors.shell : m.color, isRoot ? 0.16 : 0.28);
      const mesh = new THREE.Mesh(g, mat);
      mesh.userData = { kind: 'region', key: m.key, allen: m.key, name: m.name };
      mesh.renderOrder = isRoot ? 1 : 2;
      mesh.visible = isRoot || m.key === 'HPF';
      if (m.key === 'HPF') mat.uniforms.color.value.set(opts.colors.hpf);
      groups.brain.add(mesh);
      byKey.brain[m.key] = mesh;
    }
    dirty = true;
  }
  function addHpf(blob, colorOf) {
    for (const m of blob.header.meshes) {
      const g = meshFromBlob(blob.arrays['p:' + m.key], blob.arrays['i:' + m.key]);
      const mat = new THREE.MeshStandardMaterial({ color: colorOf(m.key) || m.color, roughness: 0.55,
        metalness: 0.0, transparent: true, opacity: 0.55, depthWrite: false, side: THREE.DoubleSide,
        clippingPlanes: slabPlanes, clipIntersection: false });
      const mesh = new THREE.Mesh(g, mat);
      mesh.userData = { kind: 'region', key: m.key, allen: m.key, name: m.name };
      mesh.renderOrder = 3;
      mesh.visible = ['DG', 'CA1', 'CA2', 'CA3', 'SUB', 'ProS', 'ENTl', 'ENTm', 'PRE', 'POST', 'PAR'].includes(m.key);
      groups.hpf.add(mesh);
      byKey.hpf[m.key] = mesh;
    }
    dirty = true;
  }
  function addLamina(blob, colors) {
    for (const m of blob.header.meshes) {
      const g = meshFromBlob(blob.arrays['p:' + m.key], blob.arrays['i:' + m.key]);
      const mat = new THREE.MeshStandardMaterial({ color: colors[m.key] || '#999', roughness: 0.5,
        metalness: 0.02, transparent: true, opacity: 0.9, side: THREE.DoubleSide,
        clippingPlanes: slabPlanes });
      const mesh = new THREE.Mesh(g, mat);
      mesh.userData = { kind: 'lamina', key: m.key, name: m.name, label: m.label };
      mesh.renderOrder = 4;
      groups.lamina.add(mesh);
      byKey.lamina[m.key] = mesh;
    }
    dirty = true;
  }
  function addCells(blob, colorOf) {
    for (const c of blob.header.cells) {
      const arr = { p: blob.arrays['p:' + c.key], t: blob.arrays['t:' + c.key], r: blob.arrays['r:' + c.key],
                    a: blob.arrays['a:' + c.key] };
      const grp = buildCell(c, arr, colorOf(c.key));
      grp.traverse((o) => { if (o.material) o.material.clippingPlanes = null; });
      groups.cells.add(grp);
      byKey.cells[c.key] = grp;
    }
    dirty = true;
  }

  /* ---------- levels ---------- */
  function fly(pos, target, ms) {
    const p0 = camera.position.clone(), t0 = controls.target.clone();
    const p1 = new THREE.Vector3(...pos), t1 = new THREE.Vector3(...target);
    if (reduced() || !ms) {
      camera.position.copy(p1); controls.target.copy(t1); controls.update(); dirty = true; return;
    }
    const s = performance.now();
    anims.add((now) => {
      const k = Math.min(1, (now - s) / ms);
      const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      camera.position.lerpVectors(p0, p1, e);
      controls.target.lerpVectors(t0, t1, e);
      return k < 1;
    });
    start();
  }
  function setSlab(apUm, thickUm) {
    const z0 = (apUm - thickUm / 2 - 6600) / 1000, z1 = (apUm + thickUm / 2 - 6600) / 1000;
    slabPlanes[0].set(new THREE.Vector3(0, 0, 1), -z0);
    slabPlanes[1].set(new THREE.Vector3(0, 0, -1), z1);
    dirty = true;
  }
  function useSlab(on) {
    slabOn = on;
    const planes = on ? slabPlanes : [];
    for (const g of [groups.lamina, groups.hpf]) g.traverse((o) => { if (o.material) { o.material.clippingPlanes = planes; o.material.needsUpdate = true; } });
    groups.cells.traverse((o) => { if (o.material) { o.material.clippingPlanes = on ? slabCellPlanes() : []; o.material.needsUpdate = true; } });
    dirty = true;
  }
  function slabCellPlanes() {
    // cells keep a wider window than the tissue so their arbors read
    const z0 = -slabPlanes[0].constant, z1 = slabPlanes[1].constant;
    const pad = 0.6;
    return [new THREE.Plane(new THREE.Vector3(0, 0, 1), -(z0 - pad)), new THREE.Plane(new THREE.Vector3(0, 0, -1), z1 + pad)];
  }
  function setLevel(lv, o) {
    level = lv;
    o = o || {};
    const B = byKey.brain;
    if (lv === 'brain') {
      groups.brain.visible = true;
      Object.entries(B).forEach(([k, m]) => { m.material.uniforms.dim.value = 1; });
      groups.hpf.visible = !!o.hpf; groups.lamina.visible = false; groups.cells.visible = false;
      useSlab(false);
      fly([8.5, 6.5, 11.5], [0, 0.2, 0.6], 1200);
    } else if (lv === 'hpf') {
      groups.brain.visible = true;
      Object.values(B).forEach((m) => { m.material.uniforms.dim.value = 0.35; });
      if (B.HPF) B.HPF.visible = false;
      groups.hpf.visible = true; groups.lamina.visible = !!o.lamina; groups.cells.visible = false;
      useSlab(false);
      fly([5.4, 3.6, 5.4], [1.6, 1.6, 1.2], 1400);
    } else if (lv === 'slab') {
      groups.brain.visible = false;
      groups.hpf.visible = false; groups.lamina.visible = true; groups.cells.visible = true;
      useSlab(true);
      const z = -slabPlanes[0].constant;
      fly([1.35, 2.25, z - 3.4], [1.45, 1.75, z], 1400);
    }
    dirty = true;
  }

  /* The section face: the slice image laid in the slab's front plane. */
  function setFace(canvas, box) {
    if (facePlane) { groups.fx.remove(facePlane); facePlane.geometry.dispose(); facePlane.material.map.dispose(); facePlane.material.dispose(); facePlane = null; }
    if (!canvas) { dirty = true; return; }
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    const a = W(box.ap, box.dv0, box.ml0), b = W(box.ap, box.dv1, box.ml1);
    const g = new THREE.PlaneGeometry(Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
    const m = new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 0.92, side: THREE.DoubleSide, depthWrite: false });
    facePlane = new THREE.Mesh(g, m);
    facePlane.position.set((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, a[2] - 0.001);
    facePlane.renderOrder = 0;
    groups.fx.add(facePlane);
    dirty = true;
  }

  /* ---------- emphasis ---------- */
  function focus(f) {
    // f: { cells:Set, regions:Set (allen acronyms), layers:Set } or null
    const on = f && (f.cells.size || f.regions.size || f.layers.size);
    for (const [k, grp] of Object.entries(byKey.cells)) {
      const lit = !on || f.cells.has(k);
      grp.traverse((o) => {
        if (!o.material) return;
        if (o.material.uniforms && o.material.uniforms.base) o.material.uniforms.base.value = lit ? 0.6 : 0.06;
        else { o.material.transparent = !lit; o.material.opacity = lit ? 1 : 0.12; o.material.depthWrite = lit; }
      });
    }
    for (const [k, m] of Object.entries(byKey.lamina)) {
      const lit = !on || f.layers.has(k);
      m.material.opacity = lit ? 0.9 : 0.12;
      m.material.depthWrite = lit;
    }
    for (const [k, m] of Object.entries(byKey.hpf)) {
      const lit = !on || f.regions.has(k);
      m.material.opacity = lit ? 0.62 : 0.08;
      if (on && f.regions.has(k)) m.visible = true;
    }
    dirty = true;
  }
  function showOnly(kind, keys, visible) {
    const map = byKey[kind];
    for (const [k, m] of Object.entries(map)) if (keys.includes(k)) m.visible = visible;
    dirty = true;
  }
  function setVisible(kind, key, v) {
    const m = byKey[kind] && byKey[kind][key];
    if (m) { m.visible = v; dirty = true; }
  }
  function setOpacity(kind, v) {
    for (const m of Object.values(byKey[kind] || {})) { if (m.material && 'opacity' in m.material) m.material.opacity = v; }
    dirty = true;
  }

  /* A pulse out along a cell's axon (the tracer's 'via'). */
  function pulseCell(key, ms) {
    const grp = byKey.cells[key];
    if (!grp) return;
    const ax = grp.children.find((o) => o.userData.part === 'axon');
    if (!ax) return;
    const u = ax.material.uniforms;
    if (reduced()) { u.t.value = -1; u.base.value = 1.0; dirty = true; return; }
    const len = ax.userData.maxlen || 2000;
    const s = performance.now();
    const dur = ms || 2600;
    u.width.value = Math.max(80, len / 25);
    anims.add((now) => {
      const k = (now - s) / dur;
      if (k > 1) { u.t.value = -1; return false; }
      u.t.value = k * len * 1.1;
      return true;
    });
    start();
  }

  /* A population volley between two places (region-level 'via'): sparks
     along an arc. */
  function volley(from, to, color, ms) {
    const a = new THREE.Vector3(...from), b = new THREE.Vector3(...to);
    const mid = a.clone().add(b).multiplyScalar(0.5);
    mid.y += a.distanceTo(b) * 0.35 + 0.2;
    const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
    const pts = curve.getPoints(80);
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.55, depthTest: false }));
    line.renderOrder = 20;
    groups.fx.add(line);
    const N = 14;
    const sparks = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({
      color, size: 0.09, transparent: true, opacity: 0.95, depthTest: false, sizeAttenuation: true }));
    sparks.geometry.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(N * 3), 3));
    sparks.renderOrder = 21;
    groups.fx.add(sparks);
    const s = performance.now();
    const dur = ms || 2200;
    const done = () => { groups.fx.remove(line); groups.fx.remove(sparks); line.geometry.dispose(); sparks.geometry.dispose(); dirty = true; };
    if (reduced()) { setTimeout(done, dur); return; }
    anims.add((now) => {
      const k = (now - s) / dur;
      if (k > 1.25) { done(); return false; }
      const pos = sparks.geometry.attributes.position;
      for (let i = 0; i < N; i++) {
        const q = Math.min(1, Math.max(0, k * 1.2 - i * 0.035));
        const p = curve.getPoint(q);
        pos.setXYZ(i, p.x, p.y, p.z);
      }
      pos.needsUpdate = true;
      line.material.opacity = 0.55 * Math.max(0, 1 - Math.max(0, k - 1) * 4);
      return true;
    });
    start();
  }

  function centroid(kind, key, rightOnly) {
    const m = byKey[kind] && byKey[kind][key];
    if (!m) return null;
    if (kind === 'cells') return m.userData.soma.toArray();
    const p = m.geometry.attributes.position;
    let x = 0, y = 0, z = 0, n = 0;
    for (let i = 0; i < p.count; i += 7) {
      if (rightOnly && p.getX(i) < 0) continue;
      x += p.getX(i); y += p.getY(i); z += p.getZ(i); n++;
    }
    return n ? [x / n, y / n, z / n] : null;
  }

  /* ---------- the probe ---------- */
  function setProbe(pr) {
    while (groups.probe.children.length) {
      const o = groups.probe.children.pop();
      o.geometry && o.geometry.dispose();
    }
    if (!pr || !pr.on) { dirty = true; return; }
    const tip = W(pr.ap, pr.dv, pr.ml);
    const top = W(pr.ap, Math.max(0, pr.dv - 3200), pr.ml);
    const shank = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, Math.abs(top[1] - tip[1]), 10),
      new THREE.MeshStandardMaterial({ color: opts.colors.probe, roughness: 0.35, metalness: 0.4 }));
    shank.position.set(tip[0], (tip[1] + top[1]) / 2, tip[2]);
    groups.probe.add(shank);
    const dots = [];
    for (let i = 0; i < pr.contacts; i++) {
      const c = W(pr.ap, pr.dv - i * pr.pitch, pr.ml);
      dots.push(c[0] + 0.019, c[1], c[2]);
    }
    const pts = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ color: opts.colors.contact, size: 0.012 }));
    pts.geometry.setAttribute('position', new THREE.Float32BufferAttribute(dots, 3));
    groups.probe.add(pts);
    dirty = true;
  }

  /* ---------- picking ---------- */
  const ray = new THREE.Raycaster();
  let downAt = null;
  renderer.domElement.addEventListener('pointerdown', (e) => { downAt = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener('pointerup', (e) => {
    if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 4) return;
    const r = renderer.domElement.getBoundingClientRect();
    const v = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(v, camera);
    const pool = [];
    [groups.cells, groups.lamina, groups.hpf, groups.brain].forEach((g) => {
      if (!g.visible) return;
      g.traverse((o) => { if (o.isMesh && o.visible && o.userData.kind && (!o.material.opacity || o.material.opacity > 0.2 || o.userData.kind === 'region')) pool.push(o); });
    });
    const hits = ray.intersectObjects(pool, false).filter((h) => !slabOn || h.object.userData.kind === 'cell' || isInSlab(h.point));
    // Prefer cells, then laminae, then the smallest region under the cursor.
    const order = { cell: 0, lamina: 1, region: 2 };
    hits.sort((x, y) => (order[x.object.userData.kind] - order[y.object.userData.kind]) || (x.distance - y.distance));
    const shellOnly = hits.filter((h) => h.object.userData.key !== 'root');
    const h = shellOnly[0] || hits[0];
    onPick(h ? h.object.userData : null);
  });
  function isInSlab(p) { return slabPlanes.every((pl) => pl.distanceToPoint(p) >= -1e-4); }

  function snapshot(scale, transparent) {
    const r = host.getBoundingClientRect();
    const pr = renderer.getPixelRatio();
    renderer.setPixelRatio(scale || 3);
    renderer.setSize(r.width, r.height, false);
    if (!transparent) renderer.setClearColor(new THREE.Color(opts.colors.bg), 1);
    renderer.render(scene, camera);
    const url = renderer.domElement.toDataURL('image/png');
    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(pr);
    size();
    renderer.render(scene, camera);
    return url;
  }

  function dispose() {
    stop();
    ro.disconnect();
    controls.dispose();
    scene.traverse((o) => { o.geometry && o.geometry.dispose(); if (o.material) { o.material.map && o.material.map.dispose(); o.material.dispose(); } });
    renderer.dispose();
    renderer.domElement.remove();
  }

  return { addBrain, addHpf, addLamina, addCells, setLevel, setSlab, useSlab, focus, showOnly, setVisible,
           setOpacity, pulseCell, volley, centroid, setProbe, setFace, snapshot, theme, dispose,
           pause: stop, resume: () => { dirty = true; start(); }, has: (k) => Object.keys(byKey[k] || {}).length > 0,
           get level() { return level; }, fly, poke: () => { dirty = true; } };
}
