/* ==========================================================================
   seahorse3d.js -- the stage of the Seahorse tab (an ES module).

   One WebGL renderer draws both views:
     3D     clay structures (opaque, outlined) with a section cut whose face
            is painted by the slice shader, real cells as tubes, a crowd of
            somata, the probe, and the rides.
     Slice  an orthographic camera looking straight at a plane; the same
            slice shader paints the plane, the same cells are clipped to a
            slab around it. Smooth at any zoom, redrawn every frame on the
            GPU (the CPU never touches a pixel).

   The slice shader samples the label volumes with "soft labels": the eight
   voxels around a point vote with their trilinear weights, so boundaries
   come out as smooth curves instead of stair steps, and the margin between
   the two strongest labels gives a crisp, anti-aliased outline.

   Imported by seahorse.js the first time a view needs it. Nothing here
   fetches; seahorse.js hands over typed arrays.

   World frame: millimetres, X = right (CCF ML - 5700 um), Y = dorsal
   (4000 - DV), Z = posterior (AP - 6600). Right-handed.

   It renders only when something changed or something moves.
   ========================================================================== */
import * as THREE from '../vendor/three/three.module.min.js';
import { OrbitControls } from '../vendor/three/OrbitControls.js';

export const W = (ap, dv, ml) => [(ml - 5700) / 1000, (4000 - dv) / 1000, (ap - 6600) / 1000];
export const toCcf = (x, y, z) => [z * 1000 + 6600, 4000 - y * 1000, x * 1000 + 5700];
const wv = (c) => new THREE.Vector3((c[2] - 5700) / 1000, (4000 - c[1]) / 1000, (c[0] - 6600) / 1000);
const dirW = (d) => new THREE.Vector3(d[2], -d[1], d[0]).normalize();      // a CCF direction in world
const dirC = (v) => [v.z, -v.y, v.x];                                       // a world direction in CCF
const reduced = () => {
  try { if (typeof BARRY !== 'undefined' && BARRY.ui && BARRY.ui.reducedMotion && BARRY.ui.reducedMotion()) return true; } catch (e) { /* no BARRY */ }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
};
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const ease = (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);

/* ------------------------------------------------------------------------
   Materials
   ------------------------------------------------------------------------ */
function rimMaterial(color, opacity) {
  return new THREE.ShaderMaterial({
    uniforms: { color: { value: new THREE.Color(color) }, opacity: { value: opacity }, dim: { value: 1.0 } },
    vertexShader: `
      varying vec3 vN; varying vec3 vV;
      #include <clipping_planes_pars_vertex>
      void main() {
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal); vV = normalize(-mvPosition.xyz);
        gl_Position = projectionMatrix * mvPosition;
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

/* Opaque clay: soft matte shading, a touch of rim, a hover/selection glow. */
function clayMaterial(color) {
  const m = new THREE.MeshStandardMaterial({ color, roughness: 0.82, metalness: 0.0, side: THREE.DoubleSide });
  m.userData.base = new THREE.Color(color);
  return m;
}

/* The outline: back faces pushed out along their normals by a fixed number
   of screen pixels -- a crisp silhouette at any zoom (the "inverted hull"). */
function outlineMaterial(color, px) {
  return new THREE.ShaderMaterial({
    uniforms: { color: { value: new THREE.Color(color) }, px: { value: px || 1.4 }, res: { value: new THREE.Vector2(1000, 800) },
                alpha: { value: 0.75 } },
    vertexShader: `
      uniform float px; uniform vec2 res;
      #include <clipping_planes_pars_vertex>
      void main() {
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        vec4 clip = projectionMatrix * mvPosition;
        vec3 nv = normalize(normalMatrix * normal);
        vec4 cn = projectionMatrix * vec4(nv, 0.0);
        vec2 d = normalize(cn.xy + 1e-6);
        clip.xy += d * px * 2.0 / res * clip.w;
        gl_Position = clip;
        #include <clipping_planes_vertex>
      }`,
    fragmentShader: `
      uniform vec3 color; uniform float alpha;
      #include <clipping_planes_pars_fragment>
      void main() {
        #include <clipping_planes_fragment>
        gl_FragColor = vec4(color, alpha);
      }`,
    side: THREE.BackSide, clipping: true, transparent: true, depthWrite: false,
  });
}

/* The slice shader: paints any plane through the atlas. */
const SLICE_VS = `
  varying vec3 vCcf;
  #include <clipping_planes_pars_vertex>
  void main() {
    vec4 wp = modelMatrix * vec4(position, 1.0);
    vCcf = vec3(wp.z * 1000.0 + 6600.0, 4000.0 - wp.y * 1000.0, wp.x * 1000.0 + 5700.0);
    vec4 mvPosition = viewMatrix * wp;
    gl_Position = projectionMatrix * mvPosition;
    #include <clipping_planes_vertex>
  }`;
const SLICE_FS = `
  precision highp float; precision highp int;
  precision highp usampler3D; precision highp sampler3D;
  varying vec3 vCcf;
  uniform usampler3D labF; uniform usampler3D labH; uniform usampler3D labB;
  uniform sampler3D nisF; uniform sampler3D nisH; uniform sampler3D nisB;
  uniform vec3 orgF; uniform vec3 orgH;                 // um, (AP, DV, ML)
  uniform vec3 dimF; uniform vec3 dimH; uniform vec3 dimB;   // voxels, (AP, DV, ML)
  uniform float hasF; uniform float hasH;
  uniform sampler2D lamLut; uniform sampler2D alLut;    // 256 x 1, 1024 x 1 (a = inside HPF)
  uniform sampler2D hiLut; uniform sampler2D alHi;      // highlights
  uniform sampler2D pulseLut;                           // pulsing highlights (DS sinks)
  uniform float pulse;
  uniform int mode;                                     // 0 layers, 1 Allen, 2 Nissl
  uniform int mask;                                     // 0 everything, 1 hippocampal formation only
  uniform vec3 paper; uniform vec3 ink;
  uniform float lineK; uniform float alpha;
  #include <clipping_planes_pars_fragment>

  bool inside(vec3 p, vec3 org, float um, vec3 dim) {
    vec3 q = (p - org) / um;
    return all(greaterThanEqual(q, vec3(1.0))) && all(lessThan(q, dim - 1.0));
  }
  uint fetchL(usampler3D t, ivec3 v, vec3 dim) {
    ivec3 c = clamp(v, ivec3(0), ivec3(dim) - 1);
    return texelFetch(t, ivec3(c.z, c.y, c.x), 0).r;
  }
  // soft label: the eight voxels vote with their trilinear weights
  void soft(vec3 p, usampler3D t, vec3 org, float um, vec3 dim, out uint best, out float margin) {
    vec3 q = (p - org) / um - 0.5;
    vec3 b = floor(q); vec3 f = q - b;
    uint L[8]; float Wt[8];
    for (int i = 0; i < 8; i++) {
      ivec3 o = ivec3(i & 1, (i >> 1) & 1, (i >> 2) & 1);
      L[i] = fetchL(t, ivec3(b) + o, dim);
      vec3 w3 = mix(1.0 - f, f, vec3(o));
      Wt[i] = w3.x * w3.y * w3.z;
    }
    float A[8]; int bi = 0;
    for (int i = 0; i < 8; i++) {
      float a = 0.0;
      for (int j = 0; j < 8; j++) a += (L[j] == L[i]) ? Wt[j] : 0.0;
      A[i] = a;
      if (a > A[bi]) bi = i;
    }
    float second = 0.0;
    for (int i = 0; i < 8; i++) if (L[i] != L[bi]) second = max(second, A[i]);
    best = L[bi]; margin = A[bi] - second;
  }
  float nis(vec3 p, sampler3D t, vec3 org, float um, vec3 dim) {
    vec3 q = (p - org) / um / dim;
    return texture(t, vec3(q.z, q.y, q.x)).r;
  }
  vec4 lut(sampler2D t, uint i, float n) { return texture(t, vec2((float(i) + 0.5) / n, 0.5)); }

  void main() {
    #include <clipping_planes_fragment>
    // The laminae exist for the right hemisphere; the CCFv3 annotation is
    // symmetric, so the left reads them mirrored. Its Nissl stays its own.
    vec3 pm = vCcf;
    bool left = pm.z < 5700.0;
    if (left) pm.z = 11400.0 - pm.z;
    uint lam = 0u; float lm = 1.0; bool inHip = false; float um = 50.0; float n = -1.0;
    if (hasF > 0.5 && inside(pm, orgF, 10.0, dimF)) { soft(pm, labF, orgF, 10.0, dimF, lam, lm); inHip = true; um = 10.0; if (!left) n = nis(pm, nisF, orgF, 10.0, dimF); }
    else if (hasH > 0.5 && inside(pm, orgH, 20.0, dimH)) { soft(pm, labH, orgH, 20.0, dimH, lam, lm); inHip = true; um = 20.0; if (!left) n = nis(pm, nisH, orgH, 20.0, dimH); }
    uint al; float am;
    soft(vCcf, labB, vec3(0.0), 50.0, dimB, al, am);
    if (n < 0.0) n = nis(vCcf, nisB, vec3(0.0), 50.0, dimB);
    // derivatives first: after a discard they are not to be trusted
    float pxum = length(fwidth(vCcf));
    float wl = fwidth(lm);
    float wa = fwidth(am);
    if (al == 0u && lam == 0u) discard;
    vec4 ac = lut(alLut, al, 1024.0);
    if (mask == 1 && lam == 0u && ac.a < 0.5) discard;
    // Nissl backdrop: dense = ink, sparse = paper
    vec3 col = mix(paper, ink, clamp(n * 0.9, 0.0, 0.88));
    if (mode == 0) {
      if (lam > 0u) col = mix(col, lut(lamLut, lam, 256.0).rgb, 0.62);
      else col = mix(col, ac.rgb, 0.11);
    } else if (mode == 1) {
      col = mix(col, ac.rgb, 0.7);
    }
    vec4 h = lam > 0u ? lut(hiLut, lam, 256.0) : lut(alHi, al, 1024.0);
    col = mix(col, h.rgb, h.a);
    vec4 p = lut(pulseLut, lam, 256.0);
    col = mix(col, p.rgb, p.a * pulse);
    // outlines: where the two strongest labels are close to a tie
    float fadeL = smoothstep(0.9, 2.6, um / max(pxum, 1e-3));
    float fadeA = smoothstep(0.9, 2.6, 50.0 / max(pxum, 1e-3));
    float lineL = 0.0;
    if (inHip) lineL = (1.0 - smoothstep(0.0, max(wl * lineK, 1e-4), lm)) * fadeL;
    float lineA = 0.0;
    // the Allen labels are 50 um: close up their outlines are coarse, so they step back
    float closeA = 1.0 - 0.6 * smoothstep(8.0, 20.0, 50.0 / max(pxum, 1e-3));
    if (lam == 0u) lineA = (1.0 - smoothstep(0.0, max(wa * lineK, 1e-4), am)) * fadeA * closeA;
    col = mix(col, ink * 0.55, max(lineL * 0.62, lineA * (mode == 1 ? 0.45 : 0.22)));
    gl_FragColor = vec4(col, alpha);
  }`;

function sliceMaterial(U) {
  // No glslVersion: on WebGL2 three.js compiles every ShaderMaterial as GLSL
  // ES 3.00 anyway (texelFetch and integer samplers work) and, unlike with
  // GLSL3 set, keeps gl_FragColor defined.
  return new THREE.ShaderMaterial({
    uniforms: U, vertexShader: SLICE_VS, fragmentShader: SLICE_FS,
    side: THREE.DoubleSide, clipping: true, transparent: false,
  });
}

/* Cells: tubes whose radius never drops below a few screen pixels, with the
   signal drawn in: an axon pulse travels out (pulseT, um from the soma), a
   dendritic glow travels in from the synapse (glowT, um from it). */
const CELL_VS = `
  attribute float rad; attribute vec3 dir; attribute float plen; attribute float dsyn; attribute float part;
  uniform float uMinPx; uniform float uPxPersp; uniform float uPxOrtho; uniform float uOrtho; uniform float uRadScale;
  varying vec3 vN; varying float vPlen; varying float vDsyn; varying float vPart;
  #include <clipping_planes_pars_vertex>
  void main() {
    vec4 mvC = modelViewMatrix * vec4(position, 1.0);
    float pxw = uOrtho > 0.5 ? uPxOrtho : max(1e-6, -mvC.z) * uPxPersp;
    float mp = part > 1.5 ? uMinPx * 2.6 : (part > 0.5 ? uMinPx * 0.75 : uMinPx);
    float r = max(rad * uRadScale, mp * pxw);
    vec4 mvPosition = modelViewMatrix * vec4(position + dir * r, 1.0);
    vN = normalize(normalMatrix * dir);
    vPlen = plen; vDsyn = dsyn; vPart = part;
    gl_Position = projectionMatrix * mvPosition;
    #include <clipping_planes_vertex>
  }`;
const CELL_FS = `
  uniform vec3 color; uniform vec3 glowCol; uniform float dim;
  uniform float pulseT; uniform float pulseW; uniform float tail;
  uniform float glowT; uniform float glowW; uniform float flash; uniform float hot; uniform float dark; uniform float mark; uniform float axonAlpha;
  varying vec3 vN; varying float vPlen; varying float vDsyn; varying float vPart;
  #include <clipping_planes_pars_fragment>
  void main() {
    #include <clipping_planes_fragment>
    vec3 n = normalize(vN);
    float diff = 0.5 + 0.5 * max(dot(n, normalize(vec3(0.35, 0.8, 0.5))), 0.0);
    float rim = pow(1.0 - abs(n.z), 2.0);
    vec3 c = color * (diff + 0.15 * rim);
    float g = 0.0;
    if (vPart > 0.5 && vPart < 1.5 && pulseT >= 0.0) {
      float d = vPlen - pulseT;
      g = exp(-d * d / (pulseW * pulseW)) + (d < 0.0 ? 0.5 * exp(d / tail) : 0.0);
    }
    if (vPart < 0.5 && glowT >= 0.0) {
      float d = vDsyn - glowT;
      g = max(g, exp(-d * d / (glowW * glowW)) * (0.35 + 0.65 * exp(-vDsyn / 600.0)) + (d < 0.0 ? 0.3 * exp(d / tail) : 0.0));
    }
    if (vPart > 1.5) g = max(g, flash);
    if (mark > 0.0 && vDsyn < 0.5) g = max(g, 0.8 * mark);
    g = clamp(g + hot * 0.35, 0.0, 1.0);
    c = mix(c, glowCol, g * 0.85) + glowCol * g * 0.35 * (1.0 + dark);
    // axons are long and many: faint unless this cell is in focus or a signal runs on them
    float a = dim;
    if (vPart > 0.5 && vPart < 1.5) a *= max(axonAlpha, min(1.0, g * 1.4));
    gl_FragColor = vec4(c, a);
  }`;

function cellMaterial(color) {
  return new THREE.ShaderMaterial({
    uniforms: {
      color: { value: new THREE.Color(color) }, glowCol: { value: new THREE.Color('#fff4c2') }, dim: { value: 1 },
      pulseT: { value: -1 }, pulseW: { value: 60 }, tail: { value: 400 }, glowT: { value: -1 }, glowW: { value: 40 },
      flash: { value: 0 }, hot: { value: 0 }, dark: { value: 0 }, mark: { value: 0 }, axonAlpha: { value: 0.3 },
      uMinPx: { value: 1.2 }, uPxPersp: { value: 0.001 }, uPxOrtho: { value: 0.001 }, uOrtho: { value: 0 }, uRadScale: { value: 1 },
    },
    vertexShader: CELL_VS, fragmentShader: CELL_FS, clipping: true, transparent: true, depthWrite: true,
  });
}

/* The crowd: round somata as point sprites. */
function crowdMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { uScale: { value: 400 }, uOrtho: { value: 0 }, uPx: { value: 1 }, alpha: { value: 0.85 } },
    vertexShader: `
      attribute float size; attribute vec3 col;
      uniform float uScale; uniform float uOrtho; uniform float uPx;
      varying vec3 vC; varying float vFade;
      #include <clipping_planes_pars_vertex>
      void main() {
        vC = col;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        float s = uOrtho > 0.5 ? size / uPx : size * uScale / max(1e-4, -mvPosition.z);
        // dots smaller than a couple of pixels are noise, not cells: let them go
        vFade = smoothstep(1.4, 3.2, s);
        gl_PointSize = clamp(s, 1.0, 26.0);
        gl_Position = projectionMatrix * mvPosition;
        #include <clipping_planes_vertex>
      }`,
    fragmentShader: `
      uniform float alpha; varying vec3 vC; varying float vFade;
      #include <clipping_planes_pars_fragment>
      void main() {
        #include <clipping_planes_fragment>
        if (vFade < 0.02) discard;
        vec2 d = gl_PointCoord * 2.0 - 1.0;
        float r = dot(d, d);
        if (r > 1.0) discard;
        float shade = 0.75 + 0.25 * (1.0 - r);
        gl_FragColor = vec4(vC * shade, alpha * vFade * smoothstep(1.0, 0.7, r));
      }`,
    transparent: true, depthWrite: false, clipping: true,
  });
}

function pickMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { id: { value: 0 }, uMinPx: { value: 3 }, uPxPersp: { value: 0.001 }, uPxOrtho: { value: 0.001 }, uOrtho: { value: 0 }, uRadScale: { value: 1 } },
    vertexShader: `
      attribute float rad; attribute vec3 dir;
      uniform float uMinPx; uniform float uPxPersp; uniform float uPxOrtho; uniform float uOrtho; uniform float uRadScale;
      #include <clipping_planes_pars_vertex>
      void main() {
        vec4 mvC = modelViewMatrix * vec4(position, 1.0);
        float pxw = uOrtho > 0.5 ? uPxOrtho : max(1e-6, -mvC.z) * uPxPersp;
        float r = max(rad * uRadScale, uMinPx * pxw);
        vec4 mvPosition = modelViewMatrix * vec4(position + dir * r, 1.0);
        gl_Position = projectionMatrix * mvPosition;
        #include <clipping_planes_vertex>
      }`,
    fragmentShader: `
      uniform float id;
      #include <clipping_planes_pars_fragment>
      void main() {
        #include <clipping_planes_fragment>
        float v = id;
        gl_FragColor = vec4(mod(v, 256.0) / 255.0, mod(floor(v / 256.0), 256.0) / 255.0, floor(v / 65536.0) / 255.0, 1.0);
      }`,
    clipping: true, side: THREE.DoubleSide,
  });
}
function pickMeshMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { id: { value: 0 } },
    vertexShader: `
      #include <clipping_planes_pars_vertex>
      void main() { vec4 mvPosition = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * mvPosition;
        #include <clipping_planes_vertex>
      }`,
    fragmentShader: `
      uniform float id;
      #include <clipping_planes_pars_fragment>
      void main() {
        #include <clipping_planes_fragment>
        float v = id;
        gl_FragColor = vec4(mod(v, 256.0) / 255.0, mod(floor(v / 256.0), 256.0) / 255.0, floor(v / 65536.0) / 255.0, 1.0);
      }`,
    clipping: true, side: THREE.DoubleSide,
  });
}

/* ------------------------------------------------------------------------
   Geometry
   ------------------------------------------------------------------------ */
function meshFromBlob(pos16, idx) {
  const n = pos16.length / 3;
  const p = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const w = W(pos16[i * 3] * 10, pos16[i * 3 + 1] * 10, pos16[i * 3 + 2] * 10);
    p[i * 3] = w[0]; p[i * 3 + 1] = w[1]; p[i * 3 + 2] = w[2];
  }
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

const SOMA_UM = { gc: 5.5, sgc: 6.5, mc: 11, hipp: 7, pvbc: 8, aac: 7.5, stel: 9, fan: 9, ca3: 10, ca1: 8.5, olm: 7 };

/* One geometry per cell: dendrite tubes (5 sides), axon tubes (3 sides) and
   the soma, with per-vertex path length from the soma (plen), the node each
   vertex belongs to (node, for the dendritic glow) and the part (0 dendrite,
   1 axon, 2 soma). Positions are the tube's axis; dir * radius is added in
   the shader, so the tubes stay legible at any zoom. */
function buildCell(cell, arr, type) {
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
  let nv = 0, ni = 0;
  for (let i = 0; i < n; i++) {
    if (A[i] < 0 || T[i] === 1) continue;
    const s = T[i] === 2 ? 3 : 5;
    nv += s * 2; ni += s * 6;
  }
  const SPH = new THREE.SphereGeometry(1, 16, 12);
  const sp = SPH.attributes.position.array, si = SPH.index.array;
  nv += sp.length / 3; ni += si.length;
  const pos = new Float32Array(nv * 3), dir = new Float32Array(nv * 3), rad = new Float32Array(nv),
        pl = new Float32Array(nv), node = new Float32Array(nv), part = new Float32Array(nv), ds = new Float32Array(nv).fill(1e9);
  const idx = nv > 65535 ? new Uint32Array(ni) : new Uint16Array(ni);
  let v = 0, k = 0;
  const a = new THREE.Vector3(), b = new THREE.Vector3(), d = new THREE.Vector3(), u = new THREE.Vector3(), q = new THREE.Vector3(), t = new THREE.Vector3();
  for (let i = 0; i < n; i++) {
    const p = A[i];
    if (p < 0 || T[i] === 1) continue;
    a.set(w[p * 3], w[p * 3 + 1], w[p * 3 + 2]);
    b.set(w[i * 3], w[i * 3 + 1], w[i * 3 + 2]);
    d.subVectors(b, a);
    if (d.lengthSq() < 1e-14) d.set(0, 1, 0);
    d.normalize();
    t.set(Math.abs(d.x) < 0.9 ? 1 : 0, Math.abs(d.x) < 0.9 ? 0 : 1, 0);
    u.crossVectors(d, t).normalize();
    q.crossVectors(d, u);
    const ax = T[i] === 2;
    const S = ax ? 3 : 5;
    const ra = (ax ? 0.35 : Math.max(0.45, Math.min(3, (R[p] || 0.6)))) / 1000;
    const rb = (ax ? 0.35 : Math.max(0.4, Math.min(3, (R[i] || 0.5)))) / 1000;
    const base = v;
    for (let s = 0; s < S; s++) {
      const ang = (s / S) * Math.PI * 2, c = Math.cos(ang), sn = Math.sin(ang);
      const ox = u.x * c + q.x * sn, oy = u.y * c + q.y * sn, oz = u.z * c + q.z * sn;
      for (let e = 0; e < 2; e++) {
        const src = e ? b : a;
        pos[v * 3] = src.x; pos[v * 3 + 1] = src.y; pos[v * 3 + 2] = src.z;
        dir[v * 3] = ox; dir[v * 3 + 1] = oy; dir[v * 3 + 2] = oz;
        rad[v] = e ? rb : ra; pl[v] = e ? plen[i] : plen[p]; node[v] = e ? i : p; part[v] = ax ? 1 : 0;
        v++;
      }
    }
    for (let s = 0; s < S; s++) {
      const s2 = (s + 1) % S;
      const a0 = base + s * 2, b0 = a0 + 1, a1 = base + s2 * 2, b1 = a1 + 1;
      idx[k++] = a0; idx[k++] = a1; idx[k++] = b0; idx[k++] = b0; idx[k++] = a1; idx[k++] = b1;
    }
  }
  // soma
  let si0 = 0;
  for (let i = 0; i < n; i++) if (T[i] === 1) { si0 = i; break; }
  const sw = W(cell.soma_um[0], cell.soma_um[1], cell.soma_um[2]);
  const sr = (SOMA_UM[type] || 7) / 1000;
  const sbase = v;
  for (let j = 0; j < sp.length / 3; j++) {
    pos[v * 3] = sw[0]; pos[v * 3 + 1] = sw[1]; pos[v * 3 + 2] = sw[2];
    dir[v * 3] = sp[j * 3]; dir[v * 3 + 1] = sp[j * 3 + 1]; dir[v * 3 + 2] = sp[j * 3 + 2];
    rad[v] = sr; pl[v] = 0; node[v] = si0; part[v] = 2; v++;
  }
  for (let j = 0; j < si.length; j++) idx[k++] = sbase + si[j];
  SPH.dispose();
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('dir', new THREE.BufferAttribute(dir, 3));
  g.setAttribute('rad', new THREE.BufferAttribute(rad, 1));
  g.setAttribute('plen', new THREE.BufferAttribute(pl, 1));
  g.setAttribute('node', new THREE.BufferAttribute(node, 1));
  g.setAttribute('part', new THREE.BufferAttribute(part, 1));
  g.setAttribute('dsyn', new THREE.BufferAttribute(ds, 1));
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  g.computeBoundingSphere();
  // the tree, for the dendritic glow
  const kids = Array.from({ length: n }, () => []);
  for (let i = 0; i < n; i++) if (A[i] >= 0) kids[A[i]].push(i);
  return { geometry: g, world: w, plen, parent: A, kids, type: T, somaNode: si0, somaW: new THREE.Vector3(sw[0], sw[1], sw[2]) };
}

/* A plain tube along a world polyline (drawn paths). */
function pathTube(pts, rad) {
  const n = pts.length;
  const S = 4;
  const pos = new Float32Array(n * S * 3), dir = new Float32Array(n * S * 3), r = new Float32Array(n * S),
        pl = new Float32Array(n * S), part = new Float32Array(n * S).fill(1), ds = new Float32Array(n * S).fill(1e9), node = new Float32Array(n * S);
  const idx = [];
  let L = 0;
  const d = new THREE.Vector3(), u = new THREE.Vector3(), q = new THREE.Vector3(), t = new THREE.Vector3();
  for (let i = 0; i < n; i++) {
    if (i) L += pts[i].distanceTo(pts[i - 1]) * 1000;
    d.subVectors(pts[Math.min(n - 1, i + 1)], pts[Math.max(0, i - 1)]);
    if (d.lengthSq() < 1e-14) d.set(0, 1, 0);
    d.normalize();
    t.set(Math.abs(d.x) < 0.9 ? 1 : 0, Math.abs(d.x) < 0.9 ? 0 : 1, 0);
    u.crossVectors(d, t).normalize(); q.crossVectors(d, u);
    for (let s = 0; s < S; s++) {
      const ang = (s / S) * Math.PI * 2, c = Math.cos(ang), sn = Math.sin(ang);
      const j = i * S + s;
      pos[j * 3] = pts[i].x; pos[j * 3 + 1] = pts[i].y; pos[j * 3 + 2] = pts[i].z;
      dir[j * 3] = u.x * c + q.x * sn; dir[j * 3 + 1] = u.y * c + q.y * sn; dir[j * 3 + 2] = u.z * c + q.z * sn;
      r[j] = rad; pl[j] = L; node[j] = i;
    }
    if (i < n - 1) for (let s = 0; s < S; s++) {
      const a0 = i * S + s, a1 = i * S + (s + 1) % S, b0 = a0 + S, b1 = a1 + S;
      idx.push(a0, a1, b0, b0, a1, b1);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('dir', new THREE.BufferAttribute(dir, 3));
  g.setAttribute('rad', new THREE.BufferAttribute(r, 1));
  g.setAttribute('plen', new THREE.BufferAttribute(pl, 1));
  g.setAttribute('part', new THREE.BufferAttribute(part, 1));
  g.setAttribute('dsyn', new THREE.BufferAttribute(ds, 1));
  g.setAttribute('node', new THREE.BufferAttribute(node, 1));
  g.setIndex(idx);
  g.computeBoundingSphere();
  return { geometry: g, length: L };
}

/* Sample a polyline (world points) at arc length s (mm). */
function polyAt(pts, cum, s) {
  if (s <= 0) return pts[0].clone();
  const L = cum[cum.length - 1];
  if (s >= L) return pts[pts.length - 1].clone();
  let lo = 0, hi = cum.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (cum[m] < s) lo = m; else hi = m; }
  const f = (s - cum[lo]) / Math.max(1e-9, cum[hi] - cum[lo]);
  return pts[lo].clone().lerp(pts[hi], f);
}
function cumLen(pts) {
  const c = [0];
  for (let i = 1; i < pts.length; i++) c.push(c[i - 1] + pts[i].distanceTo(pts[i - 1]));
  return c;
}

/* ==========================================================================
   The stage
   ========================================================================== */
export function create(host, opts) {
  const cb = Object.assign({ onPick() {}, onHover() {}, onCamera() {}, onFrame: null, onRide() {}, onProbe() {}, sample: null }, opts || {});
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: false });
  const shaderErrors = [];
  renderer.debug.onShaderError = (gl, program, vs, fs) => {
    const log = (sh) => (gl.getShaderInfoLog(sh) || '').trim();
    const msg = [gl.getProgramInfoLog(program), log(vs), log(fs)].filter(Boolean).join(' | ').slice(0, 600);
    shaderErrors.push(msg);
    console.error('Seahorse shader:', msg);
  };
  renderer.localClippingEnabled = true;
  renderer.autoClear = false;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  host.appendChild(renderer.domElement);
  renderer.domElement.className = 'sh3-canvas';
  const sceneT = new THREE.Scene();            // tissue: depth-tested among itself
  const sceneC = new THREE.Scene();            // cells, crowd, probe, fx: drawn over the tissue
  const camera = new THREE.PerspectiveCamera(35, 1, 0.005, 200);
  camera.position.set(13.5, 9.5, 17.5);
  const ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 400);
  const miniCam = new THREE.PerspectiveCamera(30, 1, 0.01, 200);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.12;
  controls.target.set(0, 0.3, 0.6);
  const lights = {
    hemi: new THREE.HemisphereLight(0xffffff, 0x445566, 1.15),
    key: new THREE.DirectionalLight(0xffffff, 1.4),
    fill: new THREE.DirectionalLight(0xffffff, 0.45),
  };
  lights.key.position.set(4, 8, -6);
  lights.fill.position.set(-6, -2, 6);
  Object.values(lights).forEach((l) => sceneT.add(l));

  const G = { brain: new THREE.Group(), hpf: new THREE.Group(), lamina: new THREE.Group(), caps: new THREE.Group(),
              cells: new THREE.Group(), crowd: new THREE.Group(), probe: new THREE.Group(), fx: new THREE.Group(), plane: new THREE.Group() };
  ['brain', 'hpf', 'lamina', 'caps', 'plane'].forEach((k) => sceneT.add(G[k]));
  ['cells', 'crowd', 'probe', 'fx'].forEach((k) => sceneC.add(G[k]));
  const byKey = { brain: {}, hpf: {}, lamina: {}, cells: {} };
  const outlines = [];
  const S = {
    view: '3d', level: 'brain', colors: Object.assign({}, opts.colors || {}),
    cut: { kind: 'none', pos: 0, thick: 300 }, cutPlanes: [], cellPlanes: [],
    slice: null, story: true, exploded: 0, explodeTarget: 0, crowdOn: true, dark: 0, darkTarget: 0,
    focus: null, hover: null, manual: false, ride: null, recording: null, mini: true,
  };
  let dirty = true, raf = 0, running = false;
  const anims = new Set();
  const U = sliceUniforms();
  const capMat = sliceMaterial(U);
  capMat.uniforms = U;
  let volumesReady = false;

  /* ---------- sizing ---------- */
  let Wpx = 10, Hpx = 10;
  function size() {
    const r = host.getBoundingClientRect();
    Wpx = Math.max(10, r.width); Hpx = Math.max(10, r.height);
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.setSize(Wpx, Hpx, false);
    camera.aspect = Wpx / Hpx;
    camera.updateProjectionMatrix();
    outlines.forEach((o) => o.material.uniforms.res.value.set(Wpx, Hpx));
    if (S.slice) applySlice();
    dirty = true;
  }
  const ro = new ResizeObserver(size);
  ro.observe(host);
  size();
  controls.addEventListener('start', () => { if (S.ride) S.manual = true; });
  controls.addEventListener('change', () => { dirty = true; camMoved(); });
  let camTimer = 0;
  function camMoved() {
    if (camTimer) return;
    camTimer = setTimeout(() => { camTimer = 0; cb.onCamera(getCam()); }, 180);
  }

  /* ---------- the slice shader's inputs ---------- */
  function sliceUniforms() {
    const blank3u = new THREE.Data3DTexture(new Uint8Array(1), 1, 1, 1);
    blank3u.format = THREE.RedIntegerFormat; blank3u.type = THREE.UnsignedByteType; blank3u.internalFormat = 'R8UI'; blank3u.needsUpdate = true;
    const blank3f = new THREE.Data3DTexture(new Uint8Array(1), 1, 1, 1);
    blank3f.format = THREE.RedFormat; blank3f.type = THREE.UnsignedByteType; blank3f.needsUpdate = true;
    const lut = (n) => { const t = new THREE.DataTexture(new Uint8Array(n * 4), n, 1, THREE.RGBAFormat); t.needsUpdate = true; return t; };
    return {
      labF: { value: blank3u }, labH: { value: blank3u }, labB: { value: blank3u },
      nisF: { value: blank3f }, nisH: { value: blank3f }, nisB: { value: blank3f },
      orgF: { value: new THREE.Vector3() }, orgH: { value: new THREE.Vector3() },
      dimF: { value: new THREE.Vector3(1, 1, 1) }, dimH: { value: new THREE.Vector3(1, 1, 1) }, dimB: { value: new THREE.Vector3(1, 1, 1) },
      hasF: { value: 0 }, hasH: { value: 0 },
      lamLut: { value: lut(256) }, alLut: { value: lut(1024) }, hiLut: { value: lut(256) }, alHi: { value: lut(1024) }, pulseLut: { value: lut(256) },
      pulse: { value: 0 }, mode: { value: 0 }, mask: { value: 0 },
      paper: { value: new THREE.Color('#fbfaf6') }, ink: { value: new THREE.Color('#1d2421') },
      lineK: { value: 1.2 }, alpha: { value: 1 },
    };
  }
  function tex3(data, dims, integer, bytes) {
    // dims: [AP, DV, ML] -> texture (x = ML, y = DV, z = AP)
    const t = new THREE.Data3DTexture(data, dims[2], dims[1], dims[0]);
    if (integer) {
      t.format = THREE.RedIntegerFormat;
      t.type = bytes === 2 ? THREE.UnsignedShortType : THREE.UnsignedByteType;
      t.internalFormat = bytes === 2 ? 'R16UI' : 'R8UI';
      t.minFilter = t.magFilter = THREE.NearestFilter;
    } else {
      t.format = THREE.RedFormat; t.type = THREE.UnsignedByteType;
      t.minFilter = t.magFilter = THREE.LinearFilter;
    }
    t.generateMipmaps = false;
    t.unpackAlignment = 1;
    t.needsUpdate = true;
    return t;
  }
  /* vols: {brain: {labels: Uint16Array, nissl: Uint8Array, dims},
            hip: {labels, nissl, dims, origin}, fine: {labels, nissl, dims, origin} | null} */
  function setVolumes(vols) {
    const b = vols.brain;
    U.labB.value = tex3(b.labels, b.dims, true, 2);
    U.nisB.value = tex3(b.nissl, b.dims, false);
    U.dimB.value.set(b.dims[0], b.dims[1], b.dims[2]);
    if (vols.hip) {
      const h = vols.hip;
      U.labH.value = tex3(h.labels, h.dims, true, 1);
      U.nisH.value = tex3(h.nissl, h.dims, false);
      U.orgH.value.set(h.origin[0], h.origin[1], h.origin[2]);
      U.dimH.value.set(h.dims[0], h.dims[1], h.dims[2]);
      U.hasH.value = 1;
    }
    if (vols.fine) {
      const f = vols.fine;
      U.labF.value = tex3(f.labels, f.dims, true, 1);
      U.nisF.value = tex3(f.nissl, f.dims, false);
      U.orgF.value.set(f.origin[0], f.origin[1], f.origin[2]);
      U.dimF.value.set(f.dims[0], f.dims[1], f.dims[2]);
      U.hasF.value = 1;
    }
    volumesReady = true;
    rebuildCaps();
    dirty = true;
  }
  function setLuts(l) {
    const put = (t, data) => { t.image.data.set(data.subarray(0, t.image.data.length)); t.needsUpdate = true; };
    if (l.lam) put(U.lamLut.value, l.lam);
    if (l.allen) put(U.alLut.value, l.allen);
    dirty = true;
  }
  /* Highlights painted into the section: {lam: Map(code -> [r,g,b,a 0..1]), allen: Map(index -> ...), pulse: Map(code -> ...)} */
  function setHighlights(h) {
    const fill = (t, m) => {
      const d = t.image.data;
      d.fill(0);
      if (m) for (const [i, c] of m) { d[i * 4] = c[0]; d[i * 4 + 1] = c[1]; d[i * 4 + 2] = c[2]; d[i * 4 + 3] = Math.round((c[3] == null ? 0.5 : c[3]) * 255); }
      t.needsUpdate = true;
    };
    fill(U.hiLut.value, h && h.lam);
    fill(U.alHi.value, h && h.allen);
    fill(U.pulseLut.value, h && h.pulse);
    if (h && h.pulse && h.pulse.size && !reduced()) startPulse(); else stopPulse();
    dirty = true;
  }
  let pulseAnim = null;
  function startPulse() {
    if (pulseAnim) return;
    const s = performance.now();
    pulseAnim = (now) => { U.pulse.value = 0.55 + 0.45 * Math.sin((now - s) / 1400 * Math.PI * 2); return true; };
    anims.add(pulseAnim);
    start();
  }
  function stopPulse() {
    if (pulseAnim) { anims.delete(pulseAnim); pulseAnim = null; }
    U.pulse.value = 1;
  }
  function setSliceMode(m) { U.mode.value = { lamina: 0, allen: 1, nissl: 2 }[m] || 0; dirty = true; }

  /* ---------- theme ---------- */
  function theme(colors) {
    Object.assign(S.colors, colors || {});
    const shell = byKey.brain.root;
    if (shell) shell.material.uniforms.color.value.set(S.colors.shell);
    if (S.colors.paper) U.paper.value.set(S.colors.paper);
    if (S.colors.ink) U.ink.value.set(S.colors.ink);
    outlines.forEach((o) => o.material.uniforms.color.value.set(S.colors.ink || '#222'));
    contactMat.color.set(S.colors.contact || '#e5a823');
    dirty = true;
  }

  /* ---------- the frame ---------- */
  const clearCol = new THREE.Color();
  const darkCol = new THREE.Color('#05080c');
  function frame(now) {
    raf = 0;
    if (!running) return;
    const moving = S.view === '3d' ? controls.update() : false;
    for (const a of Array.from(anims)) {
      if (a(now) === false) anims.delete(a);
      dirty = true;
    }
    if (S.ride) { rideTick(now); dirty = true; }
    if (dirty || moving) {
      draw();
      dirty = false;
      if (S.recording) S.recording.grab();
      if (cb.onFrame) cb.onFrame();
    }
    raf = requestAnimationFrame(frame);
  }
  function draw() {
    const d = S.dark;
    clearCol.set(S.colors.bg || '#000');
    if (d > 0) clearCol.lerp(darkCol, d);
    const transparentBg = d < 0.01 && !S.recording;
    renderer.setClearColor(clearCol, transparentBg ? 0 : 1);
    lights.hemi.intensity = 1.15 * (1 - 0.6 * d);
    lights.key.intensity = 1.4 * (1 - 0.5 * d);
    renderer.setScissorTest(false);
    renderer.setViewport(0, 0, Wpx, Hpx);
    renderer.clear();
    const cam = S.view === 'slice' ? ortho : camera;
    updateCellUniforms(cam);
    renderer.render(sceneT, cam);
    renderer.clearDepth();
    renderer.render(sceneC, cam);
    if (S.view === 'slice' && S.mini && S.slice) drawMini();
  }
  function start() { if (!running) { running = true; raf = requestAnimationFrame(frame); } }
  function stop() { running = false; if (raf) cancelAnimationFrame(raf); raf = 0; }
  start();

  function updateCellUniforms(cam) {
    const isO = cam === ortho;
    const pxPersp = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) / Hpx;
    const pxOrtho = (ortho.top - ortho.bottom) / Hpx;
    const set = (u) => {
      u.uOrtho.value = isO ? 1 : 0; u.uPxPersp.value = pxPersp; u.uPxOrtho.value = pxOrtho;
    };
    for (const c of Object.values(byKey.cells)) { set(c.mesh.material.uniforms); c.mesh.material.uniforms.dark.value = S.dark; }
    G.fx.children.forEach((o) => { if (o.material && o.material.uniforms && o.material.uniforms.uOrtho) set(o.material.uniforms); });
    if (crowd) {
      crowd.material.uniforms.uOrtho.value = isO ? 1 : 0;
      crowd.material.uniforms.uPx.value = pxOrtho;
      crowd.material.uniforms.uScale.value = 1 / pxPersp;
      // the crowd steps back while a ride plays or a cell is in the spotlight
      const quiet = S.ride || (S.focus && S.focus.cells && S.focus.cells.size);
      crowd.material.uniforms.alpha.value = quiet ? 0.32 : 0.85;
    }
    // the sections go dark-field on the dark stage: dense Nissl glows
    if (S.colors.paper) {
      const d = S.dark;
      U.paper.value.set(S.colors.paper).lerp(darkPaper, d);
      U.ink.value.set(S.colors.ink || '#1d2421').lerp(darkInk, d);
    }
  }
  const darkPaper = new THREE.Color('#0b1016'), darkInk = new THREE.Color('#e9e1cf');

  /* ---------- adding things ---------- */
  function addOutline(mesh, px) {
    const o = new THREE.Mesh(mesh.geometry, outlineMaterial(S.colors.ink || '#222', px));
    o.material.uniforms.res.value.set(Wpx, Hpx);
    o.renderOrder = (mesh.renderOrder || 0) - 1;
    o.userData = { outlineOf: mesh };
    mesh.add(o);
    outlines.push(o);
    return o;
  }
  function addBrain(blob) {
    for (const m of blob.header.meshes) {
      const g = meshFromBlob(blob.arrays['p:' + m.key], blob.arrays['i:' + m.key]);
      const isRoot = m.key === 'root';
      let mesh;
      if (isRoot || m.key !== 'HPF') {
        mesh = new THREE.Mesh(g, rimMaterial(isRoot ? S.colors.shell : m.color, isRoot ? 0.16 : 0.28));
        mesh.renderOrder = isRoot ? 50 : 49;
      } else {
        mesh = new THREE.Mesh(g, clayMaterial(S.colors.hpf || '#e5a823'));
        addOutline(mesh, 1.2);
        mesh.renderOrder = 2;
      }
      mesh.userData = { kind: 'region', key: m.key, allen: m.key, name: m.name, pickable: m.key !== 'root' };
      mesh.visible = isRoot || m.key === 'HPF';
      G.brain.add(mesh);
      byKey.brain[m.key] = mesh;
    }
    applyClipping();
    dirty = true;
  }
  function addHpf(blob, colorOf) {
    for (const m of blob.header.meshes) {
      const g = meshFromBlob(blob.arrays['p:' + m.key], blob.arrays['i:' + m.key]);
      const mesh = new THREE.Mesh(g, clayMaterial(colorOf(m.key) || m.color));
      addOutline(mesh, 1.1);
      mesh.userData = { kind: 'region', key: m.key, allen: m.key, name: m.name, pickable: true };
      mesh.renderOrder = 3;
      mesh.visible = ['DG', 'CA1', 'CA2', 'CA3', 'SUB', 'ProS', 'ENTl', 'ENTm', 'PRE', 'POST', 'PAR'].includes(m.key);
      G.hpf.add(mesh);
      byKey.hpf[m.key] = mesh;
    }
    applyClipping();
    dirty = true;
  }
  function addLamina(blob, colors) {
    for (const m of blob.header.meshes) {
      const g = meshFromBlob(blob.arrays['p:' + m.key], blob.arrays['i:' + m.key]);
      const mesh = new THREE.Mesh(g, clayMaterial(colors[m.key] || '#999'));
      addOutline(mesh, 0.9);
      mesh.userData = { kind: 'lamina', key: m.key, name: m.name, label: m.label, pickable: true };
      g.computeBoundingBox();
      mesh.userData.center = g.boundingBox.getCenter(new THREE.Vector3());
      mesh.renderOrder = 4;
      mesh.visible = false;
      G.lamina.add(mesh);
      byKey.lamina[m.key] = mesh;
    }
    applyClipping();
    dirty = true;
  }
  /* cells: blob from cells.shb.gz; colorOf(type); story: {key: world shift to undo} */
  function addCells(blob, colorOf) {
    for (const c of blob.header.cells) {
      const arr = { p: blob.arrays['p:' + c.key], t: blob.arrays['t:' + c.key], r: blob.arrays['r:' + c.key], a: blob.arrays['a:' + c.key] };
      const built = buildCell(c, arr, c.type);
      const mat = cellMaterial(colorOf(c.type || c.key));
      const mesh = new THREE.Mesh(built.geometry, mat);
      mesh.renderOrder = 30;
      mesh.frustumCulled = false;
      mesh.userData = { kind: 'cell', key: c.key, type: c.type, pickable: true };
      G.cells.add(mesh);
      const shift = c.story && c.story.shift_um && c.story.moved ? c.story.shift_um : null;
      byKey.cells[c.key] = Object.assign(built, { mesh, info: c, shiftW: shift ? new THREE.Vector3(shift[2] / 1000, -shift[1] / 1000, shift[0] / 1000) : null });
    }
    applyStory();
    applyClipping();
    dirty = true;
  }

  /* ---------- levels, cuts, the section face ---------- */
  function setLevel(lv, o) {
    S.level = lv;
    o = o || {};
    const B = byKey.brain;
    if (lv === 'brain') {
      G.brain.visible = true;
      Object.values(B).forEach((m) => { if (m.material.uniforms) m.material.uniforms.dim.value = 1; });
      if (B.HPF) B.HPF.visible = true;
      G.hpf.visible = false; G.lamina.visible = false; G.cells.visible = false; G.crowd.visible = false;
    } else {
      G.brain.visible = true;
      Object.values(B).forEach((m) => { if (m.material.uniforms) m.material.uniforms.dim.value = 0.32; });
      if (B.HPF) B.HPF.visible = false;
      G.hpf.visible = lv === 'hpf'; G.lamina.visible = lv === 'slab' || S.exploded > 0;
      G.cells.visible = true; G.crowd.visible = S.crowdOn;
      if (lv === 'slab') Object.values(byKey.lamina).forEach((m) => { m.visible = !['alv', 'fi'].includes(m.userData.key); });
    }
    if (!o.keepCam && !S.ride) {
      if (lv === 'brain') fly([13.5, 9.5, 17.5], [0, 0.3, 0.6], 1200);
      else if (lv === 'hpf') fly(o.cam || [7.8, 5.6, -2.6], o.target || [2.1, 0.9, 1.9], 1400);
      else if (lv === 'slab') {
        const z = (S.cut.pos - 6600) / 1000;
        fly([2.0, 2.2, z - 3.6], [2.1, 1.25, z], 1400);
      }
    }
    applyClipping();
    dirty = true;
  }
  /* cut: {kind: 'none'|'coronal'|'sagittal'|'horizontal'|'slab'|'view', pos (um), thick (um), normal?, point?} */
  function setCut(c) {
    Object.assign(S.cut, c);
    applyClipping();
    rebuildCaps();
    dirty = true;
  }
  function cutPlanesFor(c) {
    const k = c.kind;
    if (k === 'none' || !k) return [];
    if (k === 'coronal') return [new THREE.Plane(new THREE.Vector3(0, 0, 1), -((c.pos - 6600) / 1000))];
    if (k === 'sagittal') return [new THREE.Plane(new THREE.Vector3(1, 0, 0), -((c.pos - 5700) / 1000))];
    if (k === 'horizontal') return [new THREE.Plane(new THREE.Vector3(0, -1, 0), (4000 - c.pos) / 1000)];
    if (k === 'slab') {
      const z0 = (c.pos - c.thick / 2 - 6600) / 1000, z1 = (c.pos + c.thick / 2 - 6600) / 1000;
      return [new THREE.Plane(new THREE.Vector3(0, 0, 1), -z0), new THREE.Plane(new THREE.Vector3(0, 0, -1), z1)];
    }
    if (k === 'view' && c.normal && c.point) {
      const n = c.normal.clone().normalize();
      return [new THREE.Plane().setFromNormalAndCoplanarPoint(n, c.point)];
    }
    return [];
  }
  function applyClipping() {
    S.cutPlanes = S.view === '3d' ? cutPlanesFor(S.cut) : [];
    const tissue = S.cutPlanes;
    for (const g of [G.brain, G.hpf, G.lamina]) {
      g.traverse((o) => { if (o.material) { o.material.clippingPlanes = tissue; o.material.clipIntersection = false; o.material.needsUpdate = true; } });
    }
    // cells: in the slice view, a slab around the plane; in 3D, the slab level only
    let cp = [];
    if (S.view === 'slice' && S.slice) cp = sliceSlabPlanes(150);
    else if (S.cut.kind === 'slab') {
      const pad = 600;
      cp = cutPlanesFor({ kind: 'slab', pos: S.cut.pos, thick: S.cut.thick + pad * 2 });
    }
    S.cellPlanes = cp;
    G.cells.traverse((o) => { if (o.material) { o.material.clippingPlanes = cp; o.material.needsUpdate = true; } });
    G.fx.traverse((o) => { if (o.material && o.userData.clipLikeCells) { o.material.clippingPlanes = cp; o.material.needsUpdate = true; } });
    // the crowd lives in a thin sheet at the cut or the section
    let crowdPlanes = [];
    if (S.view === 'slice' && S.slice) crowdPlanes = sliceSlabPlanes(14);
    else if (S.cutPlanes.length) {
      const p0 = S.cutPlanes[0];
      const back = p0.clone();
      back.normal.negate(); back.constant = -back.constant + 0.09;
      crowdPlanes = [p0.clone(), back];
      if (S.cut.kind === 'slab') crowdPlanes = cutPlanesFor({ kind: 'slab', pos: S.cut.pos, thick: S.cut.thick });
    }
    if (crowd) { crowd.material.clippingPlanes = crowdPlanes; crowd.material.needsUpdate = true; crowd.visible = S.crowdOn && S.level !== 'brain' && crowdPlanes.length > 0; }
    dirty = true;
  }
  /* The section faces: a quad on each cut plane, painted by the slice shader. */
  function rebuildCaps() {
    while (G.caps.children.length) { const o = G.caps.children.pop(); o.geometry.dispose(); }
    if (!volumesReady || S.view !== '3d') return;
    const planes = cutPlanesFor(S.cut);
    if (!planes.length) return;
    const list = S.cut.kind === 'slab' ? [planes[0]] : planes;
    for (const pl of list) {
      const geo = new THREE.PlaneGeometry(16, 16);
      const m = new THREE.Mesh(geo, capMat);
      const n = pl.normal.clone();
      const p = n.clone().multiplyScalar(-pl.constant);
      m.position.copy(p).addScaledVector(n, 0.0004);
      m.lookAt(p.clone().sub(n));
      m.userData = { kind: 'cap', pickable: true, plane: pl };
      m.renderOrder = 1;
      G.caps.add(m);
    }
    U.mask.value = S.level === 'brain' ? 0 : 1;
    dirty = true;
  }

  /* ---------- the slice view ---------- */
  // state: {N, U, V: CCF unit vectors; C: centre point (CCF um); k: um per CSS px}
  function sliceSlabPlanes(halfUm) {
    const s = S.slice;
    const n = dirW(s.N), c = wv(s.C);
    const h = halfUm / 1000;
    const a = new THREE.Plane().setFromNormalAndCoplanarPoint(n, c.clone().addScaledVector(n, -h));
    const b = new THREE.Plane().setFromNormalAndCoplanarPoint(n.clone().negate(), c.clone().addScaledVector(n, h));
    return [a, b];
  }
  let sliceQuad = null, planeMark = null;
  function setSlice(s) {
    S.slice = Object.assign({}, S.slice || {}, s);
    applySlice();
  }
  function applySlice() {
    const s = S.slice;
    if (!s) return;
    const Uw = dirW(s.U), Vw = dirW(s.V);
    const c = wv(s.C);
    const z = new THREE.Vector3().crossVectors(Vw, Uw).normalize();       // camera back axis
    ortho.position.copy(c).addScaledVector(z, 60);
    ortho.up.copy(Vw).negate();
    ortho.lookAt(c);
    const hw = Wpx * s.k / 2000, hh = Hpx * s.k / 2000;
    ortho.left = -hw; ortho.right = hw; ortho.top = hh; ortho.bottom = -hh;
    ortho.near = 1; ortho.far = 120;
    ortho.updateProjectionMatrix();
    ortho.updateMatrixWorld();
    if (!sliceQuad) {
      sliceQuad = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), capMat);
      sliceQuad.userData = { kind: 'cap', pickable: true };
      sliceQuad.renderOrder = 1;
    }
    sliceQuad.position.copy(c);
    sliceQuad.quaternion.copy(ortho.quaternion);
    sliceQuad.scale.set(hw * 2.4, hh * 2.4, 1);
    sliceQuad.updateMatrixWorld();
    if (S.view === 'slice') { if (!sliceQuad.parent) sceneT.add(sliceQuad); }
    applyClipping();
    // the plane marker for the mini 3D
    if (!planeMark) {
      planeMark = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ color: S.colors.accent || '#e5a823', transparent: true, opacity: 0.28, side: THREE.DoubleSide, depthWrite: false }));
      planeMark.renderOrder = 60;
    }
    planeMark.position.copy(c);
    planeMark.quaternion.copy(ortho.quaternion);
    planeMark.scale.set(9, 7, 1);
    dirty = true;
  }
  function sliceToCcf(px, py) {
    const s = S.slice;
    const du = (px - Wpx / 2) * s.k, dv = (py - Hpx / 2) * s.k;
    return [0, 1, 2].map((i) => s.C[i] + s.U[i] * du + s.V[i] * dv);
  }
  function ccfToSlicePx(p) {
    const s = S.slice;
    const d = [p[0] - s.C[0], p[1] - s.C[1], p[2] - s.C[2]];
    const du = d[0] * s.U[0] + d[1] * s.U[1] + d[2] * s.U[2];
    const dv = d[0] * s.V[0] + d[1] * s.V[1] + d[2] * s.V[2];
    const dn = d[0] * s.N[0] + d[1] * s.N[1] + d[2] * s.N[2];
    return [Wpx / 2 + du / s.k, Hpx / 2 + dv / s.k, dn];
  }
  function drawMini() {
    const w = Math.round(Math.min(220, Wpx * 0.24)), h = Math.round(w * 0.78);
    const x = 12, y = 12;
    miniCam.aspect = w / h;
    const c = wv(S.slice.C);
    const n = dirW(S.slice.N);
    // look at the brain from a corner, so the plane is seen at an angle, never edge-on
    const c0 = new THREE.Vector3(0, 0.2, 0.8);
    const up = new THREE.Vector3(0, 1, 0);
    const side = new THREE.Vector3().crossVectors(up, n);
    if (side.lengthSq() < 0.01) side.set(1, 0, 0);
    side.normalize();
    const dirv = n.clone().multiplyScalar(0.6).add(side.multiplyScalar(0.7)).add(up.clone().multiplyScalar(0.5)).normalize();
    miniCam.position.copy(c0).addScaledVector(dirv, 17);
    miniCam.up.set(0, 1, 0);
    miniCam.lookAt(c0);
    miniCam.updateProjectionMatrix();
    renderer.setScissorTest(true);
    renderer.setScissor(x, y, w, h);
    renderer.setViewport(x, y, w, h);
    renderer.setClearColor(clearCol.set(S.colors.bg2 || S.colors.bg || '#000'), 1);
    renderer.clear();
    const vis = { cells: G.cells.visible, crowd: G.crowd.visible, probe: G.probe.visible, quad: sliceQuad && sliceQuad.visible };
    if (sliceQuad) sliceQuad.visible = false;
    const shell = byKey.brain.root, hpfm = byKey.brain.HPF;
    const was = { gb: G.brain.visible, gh: G.hpf.visible, gl: G.lamina.visible, hpf: hpfm && hpfm.visible };
    G.brain.visible = true; G.hpf.visible = false; G.lamina.visible = false; if (hpfm) hpfm.visible = true;
    if (shell) shell.material.uniforms.dim.value = 1.4;
    G.plane.add(planeMark);
    renderer.render(sceneT, miniCam);
    G.plane.remove(planeMark);
    G.brain.visible = was.gb; G.hpf.visible = was.gh; G.lamina.visible = was.gl; if (hpfm) hpfm.visible = was.hpf;
    if (sliceQuad) sliceQuad.visible = vis.quad;
    renderer.setScissorTest(false);
    renderer.setViewport(0, 0, Wpx, Hpx);
  }
  function setView(v) {
    S.view = v;
    controls.enabled = v === '3d';
    if (v === 'slice') {
      if (sliceQuad && !sliceQuad.parent) sceneT.add(sliceQuad);
      G.brain.visible = false; G.hpf.visible = false; G.lamina.visible = false;
      G.cells.visible = true;
      U.mask.value = 0;
      U.lineK.value = 1.25;
    } else {
      if (sliceQuad && sliceQuad.parent) sceneT.remove(sliceQuad);
      setLevel(S.level, { keepCam: true });
      U.lineK.value = 1.1;
    }
    applyClipping();
    rebuildCaps();
    dirty = true;
  }

  /* ---------- emphasis ---------- */
  /* f: {cells: Set(instance keys), regions: Set(Allen acronyms), layers: Set(lamina keys), ghost: bool} or null */
  function focus(f) {
    S.focus = f;
    const on = f && ((f.cells && f.cells.size) || (f.regions && f.regions.size) || (f.layers && f.layers.size));
    for (const [k, c] of Object.entries(byKey.cells)) {
      const chosen = on && f.cells && f.cells.size && f.cells.has(k);
      const lit = !on || !f.cells || !f.cells.size || chosen;
      const u = c.mesh.material.uniforms;
      u.dim.value = lit ? 1 : 0.13;
      u.axonAlpha.value = chosen ? 1 : 0.3;
      c.mesh.material.depthWrite = lit;
      c.mesh.renderOrder = lit ? 31 : 30;
    }
    for (const [k, m] of Object.entries(byKey.hpf)) {
      const lit = !on || !f.regions || !f.regions.size || f.regions.has(k);
      tint(m, lit ? 1 : 0.42);
    }
    for (const [k, m] of Object.entries(byKey.lamina)) {
      const lit = !on || !f.layers || !f.layers.size || f.layers.has(k);
      tint(m, lit ? 1 : 0.42);
    }
    dirty = true;
  }
  function tint(mesh, k) {
    const m = mesh.material;
    if (!m.userData.base) return;
    m.color.copy(m.userData.base);
    if (k < 1) m.color.lerp(new THREE.Color(S.colors.bg || '#888'), 1 - k);
    m.emissive.setRGB(0, 0, 0);
  }
  /* hover glow: the hovered thing lights up (and nothing else changes) */
  function hoverGlow(ud) {
    if (S.hover && S.hover !== ud) {
      const prev = S.hover;
      if (prev.kind === 'cell' && byKey.cells[prev.key]) byKey.cells[prev.key].mesh.material.uniforms.hot.value = 0;
      else if (prev._mesh && prev._mesh.material.emissive) prev._mesh.material.emissive.setRGB(0, 0, 0);
    }
    S.hover = ud || null;
    for (const c of Object.values(byKey.cells)) {
      const u = c.mesh.material.uniforms;
      if (u.axonAlpha.value > 0.3 && !(S.focus && S.focus.cells && S.focus.cells.has(c.mesh.userData.key))) u.axonAlpha.value = 0.3;
    }
    if (ud) {
      if (ud.kind === 'cell' && byKey.cells[ud.key]) { const u = byKey.cells[ud.key].mesh.material.uniforms; u.hot.value = 1; u.axonAlpha.value = 1; }
      else if (ud._mesh && ud._mesh.material.emissive) ud._mesh.material.emissive.set(S.colors.accent || '#e5a823').multiplyScalar(0.28);
    }
    dirty = true;
  }
  /* Light the part of one cell's arbor where test(ccf) holds (e.g. its axon
     in the layers its targets live in). test null clears it. */
  function markArbor(key, test, arbor) {
    const c = byKey.cells[key];
    if (!c) return;
    const u = c.mesh.material.uniforms;
    if (!test) { if (u.mark.value) { u.mark.value = 0; dirty = true; } return; }
    const g = c.mesh.geometry;
    const node = g.attributes.node.array, ds = g.attributes.dsyn.array;
    const n = c.type.length, w = c.world, off = c.mesh.position;
    const ok = new Uint8Array(n);
    const want = arbor === 'axon' ? (t) => t === 2 : (t) => t === 3 || t === 4;
    for (let i = 0; i < n; i++) {
      if (!want(c.type[i])) continue;
      ok[i] = test(toCcf(w[i * 3] + off.x, w[i * 3 + 1] + off.y, w[i * 3 + 2] + off.z)) ? 1 : 0;
    }
    for (let v = 0; v < ds.length; v++) ds[v] = ok[node[v]] ? 0 : 1e9;
    g.attributes.dsyn.needsUpdate = true;
    u.glowT.value = -1;
    u.mark.value = 1;
    dirty = true;
  }
  function glowCells(keys, on) {
    for (const k of keys) if (byKey.cells[k]) byKey.cells[k].mesh.material.uniforms.hot.value = on ? 1 : 0;
    dirty = true;
  }
  function setVisible(kind, key, v) {
    const m = byKey[kind] && byKey[kind][key];
    if (!m) return;
    if (kind === 'cells') m.mesh.visible = v; else m.visible = v;
    dirty = true;
  }

  /* story vs true positions */
  function setStory(on) {
    S.story = !!on;
    applyStory();
  }
  function applyStory() {
    for (const c of Object.values(byKey.cells)) {
      if (!c.shiftW) continue;
      c.mesh.position.copy(S.story ? new THREE.Vector3() : c.shiftW.clone().negate());
      c.mesh.updateMatrixWorld();
    }
    dirty = true;
  }

  /* ---------- the crowd ---------- */
  let crowd = null;
  function setCrowd(data) {
    // data: {pos: Float32Array (world), col: Float32Array (rgb 0..1), size: Float32Array (mm)}
    if (crowd) { G.crowd.remove(crowd); crowd.geometry.dispose(); crowd = null; }
    if (!data) { dirty = true; return; }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(data.pos, 3));
    g.setAttribute('col', new THREE.BufferAttribute(data.col, 3));
    g.setAttribute('size', new THREE.BufferAttribute(data.size, 1));
    g.computeBoundingSphere();
    crowd = new THREE.Points(g, crowdMaterial());
    crowd.renderOrder = 20;
    crowd.frustumCulled = false;
    G.crowd.add(crowd);
    applyClipping();
  }
  function showCrowd(on) { S.crowdOn = !!on; applyClipping(); }

  /* ---------- exploded layers ---------- */
  const RANK = { hil: 0, gcl1: 1, iml1: 2, mml1: 3, oml1: 4, gcl2: -1, iml2: -2, mml2: -3, oml2: -4,
                 ca1slm: 6, ca1sr: 7, ca1sp: 8, ca1so: 9, ca2slm: 6, ca2sr: 7, ca2sp: 8, ca2so: 9,
                 ca3slm: 6, ca3sr: 7, ca3slu: 7.5, ca3sp: 8, ca3so: 9, alv: 10, fi: 10, sub: 8, pros: 8, fc: 5, ig: 5 };
  function explode(f) {
    S.explodeTarget = clamp(f, 0, 1);
    const on = S.explodeTarget > 0;
    if (on) { G.lamina.visible = true; Object.values(byKey.lamina).forEach((m) => { m.visible = !['alv', 'fi'].includes(m.userData.key); }); }
    // the section face and the region clay would not line up with displaced layers
    G.caps.visible = !on;
    G.hpf.visible = !on && S.level === 'hpf';
    const s0 = S.exploded, s1 = S.explodeTarget, t0 = performance.now();
    const done = () => {
      if (s1 === 0 && S.level !== 'slab') G.lamina.visible = false;
      if (on) {
        const pts = [];
        for (const m of Object.values(byKey.lamina)) {
          if (!m.visible) continue;
          const b = m.geometry.boundingBox;
          pts.push(b.min.clone().add(m.position), b.max.clone().add(m.position));
        }
        if (pts.length) frameOn(pts, 1100);
      }
    };
    if (reduced()) { S.exploded = s1; placeLayers(); done(); return; }
    anims.add((now) => {
      const k = Math.min(1, (now - t0) / 900);
      S.exploded = s0 + (s1 - s0) * ease(k);
      placeLayers();
      if (k >= 1) done();
      return k < 1;
    });
    start();
  }
  function placeLayers() {
    const f = S.exploded;
    for (const [k, m] of Object.entries(byKey.lamina)) {
      const r = RANK[k] == null ? 0 : RANK[k];
      m.position.set(0, r * 0.16 * f, 0);
      m.updateMatrixWorld();
    }
    dirty = true;
  }

  /* ---------- the probe ---------- */
  const probeMat = new THREE.MeshStandardMaterial({ color: '#b9c2cb', roughness: 0.45, metalness: 0.1, transparent: true, opacity: 0.82,
                                                     emissive: new THREE.Color('#3a4652') });
  const contactMat = new THREE.MeshBasicMaterial({ color: S.colors.contact || '#e5a823', depthTest: false });
  /* pr: {tip: [ap,dv,ml], dir: [dap,ddv,dml] (unit, into the brain), contacts, pitch, first (um), length (um)} */
  function setProbe(pr) {
    while (G.probe.children.length) { const o = G.probe.children.pop(); o.geometry.dispose(); }
    if (!pr) { dirty = true; return; }
    const tip = wv(pr.tip);
    const d = dirW(pr.dir);
    const L = (pr.length || 3000) / 1000;
    const top = tip.clone().addScaledVector(d, -L);
    const shank = new THREE.Mesh(new THREE.CylinderGeometry(0.019, 0.019, L, 12), probeMat);
    shank.position.copy(tip).add(top).multiplyScalar(0.5);
    shank.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.clone().negate());
    shank.renderOrder = 40;
    G.probe.add(shank);
    const tipCone = new THREE.Mesh(new THREE.ConeGeometry(0.019, 0.05, 12), probeMat);
    tipCone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.clone().negate());
    tipCone.position.copy(tip).addScaledVector(d, -0.025);
    G.probe.add(tipCone);
    const box = new THREE.BoxGeometry(0.014, 0.008, 0.004);
    const inst = new THREE.InstancedMesh(box, contactMat, pr.contacts);
    const mtx = new THREE.Matrix4(), qq = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.clone().negate());
    const side = new THREE.Vector3().crossVectors(d, new THREE.Vector3(0, 1, 0));
    if (side.lengthSq() < 1e-6) side.set(1, 0, 0);
    side.normalize().multiplyScalar(0.0);
    for (let i = 0; i < pr.contacts; i++) {
      const p = tip.clone().addScaledVector(d, -((pr.first || 40) + i * pr.pitch) / 1000).add(side);
      mtx.compose(p, qq, new THREE.Vector3(1, 1, 1));
      inst.setMatrixAt(i, mtx);
    }
    inst.instanceMatrix.needsUpdate = true;
    inst.renderOrder = 46;              // the contacts read through the shank
    G.probe.add(inst);
    G.probe.userData.tip = tip;
    dirty = true;
  }

  /* ---------- fx: flares, volleys, drawn paths ---------- */
  function flare(p, color, ms) {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ color: color || '#fff4c2', transparent: true, depthTest: false, opacity: 1,
      map: glowTexture() }));
    s.position.copy(p);
    s.renderOrder = 80;
    G.fx.add(s);
    const t0 = performance.now(), dur = ms || 1400;
    const base = Math.max(0.02, camera.position.distanceTo(p) * 0.04);
    anims.add((now) => {
      const k = (now - t0) / dur;
      if (k > 1) { G.fx.remove(s); s.material.dispose(); return false; }
      const e = Math.sin(Math.min(1, k * 2.2) * Math.PI / 2);
      s.scale.setScalar(base * (0.4 + 1.6 * e));
      s.material.opacity = 1 - k * k;
      return true;
    });
    start();
  }
  let glowTex = null;
  function glowTexture() {
    if (glowTex) return glowTex;
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const x = c.getContext('2d');
    const g = x.createRadialGradient(32, 32, 0, 32, 32, 32);
    g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.25, 'rgba(255,240,190,0.85)'); g.addColorStop(1, 'rgba(255,220,120,0)');
    x.fillStyle = g; x.fillRect(0, 0, 64, 64);
    glowTex = new THREE.CanvasTexture(c);
    return glowTex;
  }
  function volley(from, to, color, ms) {
    const a = new THREE.Vector3(...from), b = new THREE.Vector3(...to);
    const mid = a.clone().add(b).multiplyScalar(0.5);
    mid.y += a.distanceTo(b) * 0.35 + 0.2;
    const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
    const pts = curve.getPoints(80);
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.55, depthTest: false }));
    line.renderOrder = 20;
    G.fx.add(line);
    const N = 14;
    const sparks = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ color, size: 0.09, transparent: true, opacity: 0.95, depthTest: false }));
    sparks.geometry.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(N * 3), 3));
    G.fx.add(sparks);
    const s = performance.now(), dur = ms || 2200;
    const done = () => { G.fx.remove(line); G.fx.remove(sparks); line.geometry.dispose(); sparks.geometry.dispose(); dirty = true; };
    if (reduced()) { setTimeout(done, dur); return; }
    anims.add((now) => {
      const k = (now - s) / dur;
      if (k > 1.25) { done(); return false; }
      const pos = sparks.geometry.attributes.position;
      for (let i = 0; i < N; i++) { const p = curve.getPoint(Math.min(1, Math.max(0, k * 1.2 - i * 0.035))); pos.setXYZ(i, p.x, p.y, p.z); }
      pos.needsUpdate = true;
      line.material.opacity = 0.55 * Math.max(0, 1 - Math.max(0, k - 1) * 4);
      return true;
    });
    start();
  }
  /* A soma flash, and every axon of the cell lit by a pulse out (no ride). */
  function pulseCell(key, ms) {
    const c = byKey.cells[key];
    if (!c) return;
    const u = c.mesh.material.uniforms;
    let maxL = 0;
    for (let i = 0; i < c.plen.length; i++) if (c.type[i] === 2 && c.plen[i] > maxL) maxL = c.plen[i];
    const dur = ms || 2600, t0 = performance.now();
    if (reduced()) { u.flash.value = 0.6; setTimeout(() => { u.flash.value = 0; dirty = true; }, dur); dirty = true; return; }
    u.pulseW.value = Math.max(60, maxL / 25);
    anims.add((now) => {
      const k = (now - t0) / dur;
      if (k > 1) { u.pulseT.value = -1; u.flash.value = 0; return false; }
      u.flash.value = Math.max(0, 1 - k * 5);
      u.pulseT.value = k * maxL * 1.1;
      return true;
    });
    start();
  }

  /* ---------- camera ---------- */
  function fly(pos, target, ms) {
    const p0 = camera.position.clone(), t0 = controls.target.clone();
    const p1 = new THREE.Vector3(...pos), t1 = new THREE.Vector3(...target);
    if (reduced() || !ms) { camera.position.copy(p1); controls.target.copy(t1); controls.update(); dirty = true; camMoved(); return; }
    const s = performance.now();
    anims.add((now) => {
      const k = Math.min(1, (now - s) / ms);
      const e = ease(k);
      camera.position.lerpVectors(p0, p1, e);
      controls.target.lerpVectors(t0, t1, e);
      if (k >= 1) camMoved();
      return k < 1;
    });
    start();
  }
  function frameOn(worldPts, ms) {
    const box = new THREE.Box3().setFromPoints(worldPts);
    const c = box.getCenter(new THREE.Vector3());
    const r = Math.max(0.15, box.getSize(new THREE.Vector3()).length() / 2);
    const dirv = camera.position.clone().sub(controls.target).normalize();
    const dist = r / Math.sin(THREE.MathUtils.degToRad(camera.fov) / 2) * 0.9;
    fly(c.clone().addScaledVector(dirv, dist).toArray(), c.toArray(), ms == null ? 1100 : ms);
  }
  function getCam() {
    return { pos: camera.position.toArray().map((v) => +v.toFixed(4)), target: controls.target.toArray().map((v) => +v.toFixed(4)) };
  }
  function setCam(c, ms) { if (c && c.pos && c.target) fly(c.pos, c.target, ms == null ? 900 : ms); }
  function project(world) {
    const cam = S.view === 'slice' ? ortho : camera;
    const v = (world.isVector3 ? world.clone() : new THREE.Vector3(...world)).project(cam);
    return [(v.x + 1) / 2 * Wpx, (1 - v.y) / 2 * Hpx, v.z];
  }
  function cellSomaW(key) { const c = byKey.cells[key]; return c ? c.somaW.clone().add(c.mesh.position) : null; }
  function cellBounds(key) {
    const c = byKey.cells[key];
    if (!c) return null;
    const pts = [];
    for (let i = 0; i < c.world.length; i += 3 * 7) pts.push(new THREE.Vector3(c.world[i], c.world[i + 1], c.world[i + 2]).add(c.mesh.position));
    return pts;
  }
  function centroid(kind, key, rightOnly) {
    if (kind === 'cells') { const s = cellSomaW(key); return s ? s.toArray() : null; }
    const m = byKey[kind] && byKey[kind][key];
    if (!m) return null;
    const p = m.geometry.attributes.position;
    let x = 0, y = 0, z = 0, n = 0;
    for (let i = 0; i < p.count; i += 7) {
      if (rightOnly && p.getX(i) < 0) continue;
      x += p.getX(i); y += p.getY(i); z += p.getZ(i); n++;
    }
    return n ? [x / n, y / n, z / n] : null;
  }

  /* ---------- picking (on the GPU) ---------- */
  const pickTarget = new THREE.WebGLRenderTarget(1, 1);
  const pickCellMat = pickMaterial(), pickMeshMat = pickMeshMaterial();
  const pickBuf = new Uint8Array(4);
  const ids = [];
  /* One pick material per object, made once (cloning per hover would build
     and throw away shader programs). */
  function pickMatFor(o) {
    let m = o.userData._pick;
    if (!m) { m = (o.userData.kind === 'cell' ? pickCellMat : pickMeshMat).clone(); o.userData._pick = m; }
    m.clippingPlanes = o.material.clippingPlanes || [];
    if (o.userData.kind === 'cell') {
      const u = o.material.uniforms;
      ['uPxPersp', 'uPxOrtho', 'uOrtho', 'uRadScale'].forEach((k2) => { m.uniforms[k2].value = u[k2].value; });
      m.uniforms.uMinPx.value = 4.5;
    }
    return m;
  }
  function visibleUp(o) {
    for (let p = o; p; p = p.parent) if (!p.visible) return false;
    return true;
  }
  function pickPass(scene, cam) {
    ids.length = 1;
    const swaps = [];
    scene.traverse((o) => {
      if (!(o.isMesh || o.isPoints || o.isSprite || o.isLine)) return;
      swaps.push([o, o.material, o.visible]);
    });
    for (const [o] of swaps) {
      if (!o.visible) continue;
      if (o.userData.outlineOf || !o.userData.pickable || !o.isMesh || o.isInstancedMesh || !visibleUp(o)) { o.visible = false; continue; }
      ids.push(o);
      const m = pickMatFor(o);
      m.uniforms.id.value = ids.length - 1;
      o.material = m;
    }
    renderer.setRenderTarget(pickTarget);
    renderer.setClearColor(0x000000, 0);
    renderer.clear();
    renderer.render(scene, cam);
    renderer.readRenderTargetPixels(pickTarget, 0, 0, 1, 1, pickBuf);
    renderer.setRenderTarget(null);
    for (const [o, mat, vis] of swaps) { o.material = mat; o.visible = vis; }
    const id = pickBuf[3] ? pickBuf[0] + pickBuf[1] * 256 + pickBuf[2] * 65536 : 0;
    return id && ids[id] ? ids[id] : null;
  }
  function pickAt(px, py) {
    const cam = S.view === 'slice' ? ortho : camera;
    const dpr = renderer.getPixelRatio();
    const W2 = Math.round(Wpx * dpr), H2 = Math.round(Hpx * dpr);
    cam.setViewOffset(W2, H2, Math.round(px * dpr), Math.round(py * dpr), 1, 1);
    let hit = null;
    try {
      if (G.cells.visible) hit = pickPass(sceneC, cam);
      if (!hit) hit = pickPass(sceneT, cam);
    } finally {
      cam.clearViewOffset();
      renderer.setViewport(0, 0, Wpx, Hpx);
    }
    dirty = true;
    if (!hit) return null;
    const ud = Object.assign({}, hit.userData, { _mesh: hit });
    delete ud._pick;
    if (ud.kind === 'cap') {
      const p = pointOnCap(px, py, hit);
      if (p) { ud.ccf = toCcf(p.x, p.y, p.z); ud.world = p; }
    }
    return ud;
  }
  const rc = new THREE.Raycaster();
  function pointOnCap(px, py, mesh) {
    const cam = S.view === 'slice' ? ortho : camera;
    rc.setFromCamera(new THREE.Vector2(px / Wpx * 2 - 1, -(py / Hpx) * 2 + 1), cam);
    const n = new THREE.Vector3(0, 0, 1).applyQuaternion(mesh.getWorldQuaternion(new THREE.Quaternion()));
    const pl = new THREE.Plane().setFromNormalAndCoplanarPoint(n, mesh.getWorldPosition(new THREE.Vector3()));
    return rc.ray.intersectPlane(pl, new THREE.Vector3());
  }

  /* pointer handling: hover, click, the slice view's pan/zoom, the probe tip */
  const el = renderer.domElement;
  let down = null, hoverT = 0, lastMove = null;
  el.addEventListener('pointerdown', (e) => {
    const r = el.getBoundingClientRect();
    const px = e.clientX - r.left, py = e.clientY - r.top;
    down = { x: e.clientX, y: e.clientY, px, py, moved: false };
    if (S.view === 'slice' && S.slice) {
      el.setPointerCapture(e.pointerId);
      const tip = G.probe.children.length ? G.probe.userData.tip : null;
      if (tip) {
        const sp = project(tip);
        if (Math.hypot(sp[0] - px, sp[1] - py) < 14) { down.probe = true; return; }
      }
      down.C = S.slice.C.slice();
    }
  });
  el.addEventListener('pointermove', (e) => {
    const r = el.getBoundingClientRect();
    const px = e.clientX - r.left, py = e.clientY - r.top;
    if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 3) down.moved = true;
    if (down && down.probe) {
      cb.onProbe(sliceToCcf(px, py));
      return;
    }
    if (down && S.view === 'slice' && down.C && down.moved) {
      const s = S.slice;
      const dx = (px - down.px) * s.k, dy = (py - down.py) * s.k;
      s.C = [0, 1, 2].map((i) => down.C[i] - s.U[i] * dx - s.V[i] * dy);
      applySlice();
      cb.onCamera(null);
      return;
    }
    if (down) return;
    lastMove = { px, py, cx: e.clientX, cy: e.clientY };
    if (hoverT) return;
    // a pick is a render + a read-back: about fifteen a second is plenty
    hoverT = setTimeout(() => {
      hoverT = 0;
      if (!lastMove || down) return;
      const ud = pickAt(lastMove.px, lastMove.py);
      hoverGlow(ud && ud.kind !== 'cap' ? ud : null);
      cb.onHover(ud, lastMove.cx, lastMove.cy);
    }, 66);
  });
  el.addEventListener('pointerleave', () => { lastMove = null; hoverGlow(null); cb.onHover(null); });
  el.addEventListener('pointerup', (e) => {
    const d = down;
    down = null;
    if (!d) return;
    if (d.probe) { cb.onProbe(null, true); return; }
    if (d.moved) return;
    const r = el.getBoundingClientRect();
    const ud = pickAt(e.clientX - r.left, e.clientY - r.top);
    cb.onPick(ud);
  });
  el.addEventListener('wheel', (e) => {
    if (S.view !== 'slice' || !S.slice) return;
    e.preventDefault();
    const r = el.getBoundingClientRect();
    const px = e.clientX - r.left, py = e.clientY - r.top;
    const s = S.slice;
    const at = sliceToCcf(px, py);
    const k2 = clamp(s.k * Math.exp(e.deltaY * 0.0015), 0.25, 60);
    const f = k2 / s.k;
    s.C = [0, 1, 2].map((i) => at[i] + (s.C[i] - at[i]) * f);
    s.k = k2;
    applySlice();
    cb.onCamera(null);
  }, { passive: false });

  /* ---------- the stage goes dark for rides ---------- */
  let darkAnim = null;
  function setDark(on) {
    S.darkTarget = on ? 1 : 0;
    if (darkAnim) { anims.delete(darkAnim); darkAnim = null; }     // one fade at a time
    const d0 = S.dark, d1 = S.darkTarget, t0 = performance.now();
    if (reduced() || d0 === d1) { S.dark = d1; dirty = true; return; }
    darkAnim = (now) => { const k = Math.min(1, (now - t0) / 900); S.dark = d0 + (d1 - d0) * ease(k); if (k >= 1) darkAnim = null; return k < 1; };
    anims.add(darkAnim);
    start();
  }

  /* ==================================================================
     Rides: the signal along real cells, with the camera behind it
     ================================================================== */
  /* steps: from rides.json (paths in CCF um). opts: {onStep(i, step), onSynapse(i, step, worldPoint),
     onDone(), paused} */
  function ride(steps, o) {
    stopRide(true);
    for (const c of Object.values(byKey.cells)) { const u = c.mesh.material.uniforms; u.mark.value = 0; u.hot.value = 0; u.dim.value = 1; u.axonAlpha.value = 0.22; }
    const R = { steps: steps.map((s) => prepStep(s)), i: -1, t0: 0, paused: !!(o && o.paused), o: o || {}, pauseAt: 0, tmp: [] };
    S.ride = R;
    S.manual = false;
    setStory(true);
    setDark(true);
    controls.enableDamping = false;
    gotoStep(0);
    start();
  }
  function prepStep(s) {
    const st = Object.assign({}, s);
    if (s.path && s.path.length) {
      st.pts = s.path.map((c) => wv(c));
      st.cum = cumLen(st.pts);
      st.len = st.cum[st.cum.length - 1];
    }
    // other cells firing along with this one (a volley): their own path lengths
    if (s.also && s.also.paths) {
      st.extra = Object.entries(s.also.paths).map(([k, p]) => { const pts = p.map((c) => wv(c)); const cum = cumLen(pts); return { key: k, len: cum[cum.length - 1] }; });
    }
    const k = s.kind;
    st.dur = k === 'fire' ? 1.3 : k === 'synapse' ? 2.6 : k === 'axon' ? clamp((st.len || 0.5) / 1.1, 1.8, 7.5)
      : k === 'dend' ? clamp((st.len || 0.1) / 0.12, 1.3, 3.2) : 3.0;
    if (reduced()) st.dur = Math.min(st.dur, 1.2);
    return st;
  }
  function gotoStep(i) {
    const R = S.ride;
    if (!R) return;
    if (i >= R.steps.length) {
      if (!R.done) { R.done = true; finishRide(); }
      return;
    }
    cleanStep(R);
    R.done = false;
    R.hold = false;
    R.i = Math.max(0, i);
    R.t0 = performance.now();
    R.pauseAt = 0;
    const st = R.steps[R.i];
    const prev = R.steps[R.i - 1];
    // where the step happens
    if (st.kind === 'synapse') st.at = prev && prev.pts ? prev.pts[prev.pts.length - 1].clone() : (cellSomaW(st.cell) || new THREE.Vector3());
    if (st.kind === 'fire') st.at = cellSomaW(st.cell) || (st.pts ? st.pts[0] : null);
    if (st.kind === 'dend' && st.cell && byKey.cells[st.cell]) prepDendGlow(st);
    if (st.kind === 'axon' && !st.cell && st.pts) {
      // a drawn path: a temporary tube
      const t = pathTube(st.pts, 0.0007);
      const m = cellMaterial(S.colors.drawn || '#c9c2a8');
      m.uniforms.uMinPx.value = 1.6;
      const mesh = new THREE.Mesh(t.geometry, m);
      mesh.renderOrder = 32;
      mesh.frustumCulled = false;
      mesh.userData = { clipLikeCells: true };
      G.fx.add(mesh);
      R.tmp.push(mesh);
      st.tube = mesh;
    }
    if (st.kind === 'fire') {
      (st.also && st.also.cells || []).concat(st.cell ? [st.cell] : []).forEach((k) => flashSoma(k));
    }
    if (st.kind === 'synapse' && st.at) flare(st.at, st.sign === 'inh' ? (S.colors.err || '#e05555') : '#fff4c2', 1800);
    if (st.kind === 'burst') (st.also && st.also.cells || []).forEach((k) => pulseCell(k, 1600));
    if (R.o.onStep) R.o.onStep(R.i, st);
    if (st.kind === 'synapse' && R.o.onSynapse) R.o.onSynapse(R.i, st, st.at);
    dirty = true;
  }
  function cleanStep(R) {
    for (const c of Object.values(byKey.cells)) {
      const u = c.mesh.material.uniforms;
      u.pulseT.value = -1; u.glowT.value = -1;
    }
    for (const m of R.tmp) { G.fx.remove(m); m.geometry.dispose(); m.material.dispose(); }
    R.tmp = [];
  }
  function flashSoma(key) {
    const c = byKey.cells[key];
    if (!c) return;
    const u = c.mesh.material.uniforms, t0 = performance.now();
    anims.add((now) => { const k = (now - t0) / 1100; u.flash.value = k > 1 ? 0 : Math.sin(Math.min(1, k) * Math.PI); return k <= 1; });
    flare(cellSomaW(key), '#fff4c2', 900);
  }
  /* The dendritic glow: distance from the synapse to every node of the
     cell, along the tree. */
  function prepDendGlow(st) {
    const c = byKey.cells[st.cell];
    const p0 = st.pts ? st.pts[0] : null;
    if (!p0) return;
    const w = c.world;
    const off = c.mesh.position;
    let best = 0, bd = 1e9;
    for (let i = 0; i < c.type.length; i++) {
      if (c.type[i] !== 3 && c.type[i] !== 4) continue;
      const dx = w[i * 3] + off.x - p0.x, dy = w[i * 3 + 1] + off.y - p0.y, dz = w[i * 3 + 2] + off.z - p0.z;
      const d = dx * dx + dy * dy + dz * dz;
      if (d < bd) { bd = d; best = i; }
    }
    const n = c.type.length;
    const dist = new Float32Array(n).fill(1e9);
    dist[best] = 0;
    const queue = [best];
    const P = c.parent;
    const um = (a, b) => Math.hypot(w[a * 3] - w[b * 3], w[a * 3 + 1] - w[b * 3 + 1], w[a * 3 + 2] - w[b * 3 + 2]) * 1000;
    while (queue.length) {
      const i = queue.shift();
      const nb = c.kids[i].slice();
      if (P[i] >= 0) nb.push(P[i]);
      for (const j of nb) {
        const d = dist[i] + um(i, j);
        if (d < dist[j]) { dist[j] = d; queue.push(j); }
      }
    }
    const g = c.mesh.geometry;
    const node = g.attributes.node.array, ds = g.attributes.dsyn.array;
    for (let v = 0; v < ds.length; v++) ds[v] = dist[node[v]];
    g.attributes.dsyn.needsUpdate = true;
    st.somaD = dist[c.somaNode];
  }
  const camWant = new THREE.Vector3(), tgtWant = new THREE.Vector3(), tan = new THREE.Vector3();
  function rideTick(now) {
    const R = S.ride;
    if (!R || R.i < 0) return;
    const st = R.steps[R.i];
    if (R.done) { if (R.head) driveCamera(R.head, st, 1); return; }
    if (R.paused) { if (!R.pauseAt) R.pauseAt = now; return; }
    if (R.pauseAt) { R.t0 += now - R.pauseAt; R.pauseAt = 0; }
    const t = (now - R.t0) / 1000;
    const k = clamp(t / st.dur, 0, 1);
    let head = null;
    if (st.pts) {
      const s = st.len * (st.kind === 'axon' ? ease(k) * 0.98 + 0.02 * k : k);
      head = polyAt(st.pts, st.cum, s);
      const ahead = polyAt(st.pts, st.cum, Math.min(st.len, s + 0.08));
      const behind = polyAt(st.pts, st.cum, Math.max(0, s - 0.08));
      tan.subVectors(ahead, behind);
      if (tan.lengthSq() < 1e-10) tan.set(0, 0, 1);
      tan.normalize();
      if (st.kind === 'axon') {
        const c = st.cell ? byKey.cells[st.cell] : null;
        const u = c ? c.mesh.material.uniforms : st.tube ? st.tube.material.uniforms : null;
        if (u) { u.pulseT.value = s * 1000; u.pulseW.value = 45; u.tail.value = 380; }
        for (const x of st.extra || []) {
          const cx = byKey.cells[x.key];
          if (cx) { const ux = cx.mesh.material.uniforms; ux.pulseT.value = (s / Math.max(1e-6, st.len)) * x.len * 1000; ux.pulseW.value = 45; ux.tail.value = 380; }
        }
      }
      if (st.kind === 'dend' && st.cell && byKey.cells[st.cell]) {
        const u = byKey.cells[st.cell].mesh.material.uniforms;
        u.glowT.value = (st.somaD || st.len * 1000) * k; u.glowW.value = 35; u.tail.value = 260;
      }
    } else if (st.at) {
      head = st.at.clone();
      tan.set(0, 0, 1);
    }
    R.head = head;
    if (head) {
      // one bright point where the signal is, a few pixels across at any distance
      if (!R.marker) {
        R.marker = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), color: '#fff6d0', transparent: true, depthTest: false }));
        R.marker.renderOrder = 90;
        G.fx.add(R.marker);
      }
      R.marker.visible = st.kind === 'axon' || st.kind === 'dend';
      R.marker.position.copy(head);
      R.marker.scale.setScalar(Math.max(0.004, camera.position.distanceTo(head) * 0.045));
      driveCamera(head, st, k);
    }
    if (t >= st.dur && !R.hold) {
      if (R.o.auto === false) { R.hold = true; return; }
      gotoStep(R.i + 1);
    }
  }
  let lastHead = null;
  function driveCamera(head, st, k) {
    // the cut: a plane through the signal, facing the camera, cutting away the tissue in front of it
    const toCam = camera.position.clone().sub(head).normalize();
    S.cut.kind = 'view';
    S.cut.normal = toCam.clone().negate();
    S.cut.point = head.clone().addScaledVector(toCam, 0.03);
    applyClippingFast();
    if (S.manual) return;
    const near = st.kind === 'synapse' || st.kind === 'fire' ? 0.16 : st.kind === 'dend' ? 0.22 : 0.42;
    const up = new THREE.Vector3(0, 1, 0);
    const side = new THREE.Vector3().crossVectors(tan, up);
    if (side.lengthSq() < 1e-6) side.set(1, 0, 0);
    side.normalize();
    camWant.copy(head).addScaledVector(tan, -near).addScaledVector(up, near * 0.55).addScaledVector(side, near * 0.35);
    if (st.kind === 'synapse' || st.kind === 'fire') {
      const a = (performance.now() / 1000) * 0.35;
      camWant.copy(head).add(new THREE.Vector3(Math.cos(a) * near, near * 0.55, Math.sin(a) * near));
    }
    tgtWant.copy(head);
    const f = reduced() ? 1 : 0.075;
    camera.position.lerp(camWant, f);
    controls.target.lerp(tgtWant, f * 1.6);
    camera.lookAt(controls.target);
    lastHead = head;
  }
  function applyClippingFast() {
    const planes = cutPlanesFor(S.cut);
    S.cutPlanes = planes;
    for (const g of [G.brain, G.hpf, G.lamina]) g.traverse((o) => { if (o.material) o.material.clippingPlanes = planes; });
    // the cap follows the plane
    if (!volumesReady) return;
    let cap = G.caps.children[0];
    if (!cap) { rebuildCaps(); cap = G.caps.children[0]; if (!cap) return; }
    U.mask.value = 0;          // a ride flies through a whole section, not a cut-out
    const pl = planes[0];
    const n = pl.normal.clone();
    const p = S.cut.point.clone();
    cap.position.copy(p).addScaledVector(n, 0.0004);
    cap.lookAt(p.clone().sub(n));
    cap.scale.setScalar(0.5);
    if (crowd) {
      const back = pl.clone(); back.normal.negate(); back.constant = -back.constant + 0.09;
      crowd.material.clippingPlanes = [pl.clone(), back];
      crowd.visible = S.crowdOn;
    }
  }
  function pauseRide(p) { if (S.ride) { S.ride.paused = p == null ? !S.ride.paused : !!p; dirty = true; } return S.ride ? S.ride.paused : false; }
  function stepRide(d) { if (S.ride) { S.ride.hold = false; gotoStep(clamp(S.ride.i + d, 0, S.ride.steps.length)); } }
  function reframe() { S.manual = false; }
  function finishRide() {
    const R = S.ride;
    if (!R) return;
    if (R.o.onDone) R.o.onDone();
  }
  function stopRide(quiet) {
    const R = S.ride;
    if (!R) return;
    cleanStep(R);
    if (R.marker) { G.fx.remove(R.marker); R.marker.material.dispose(); R.marker = null; }
    S.ride = null;
    S.manual = false;
    controls.enableDamping = true;
    setDark(false);
    S.cut = { kind: 'none', pos: 0, thick: 300 };
    applyClipping();
    rebuildCaps();
    if (!quiet && R.o.onStop) R.o.onStop();
    dirty = true;
  }

  /* ---------- figures and video ---------- */
  function snapshot(scale) {
    const pr = renderer.getPixelRatio();
    renderer.setPixelRatio(scale || 3);
    renderer.setSize(Wpx, Hpx, false);
    draw();
    const url = renderer.domElement.toDataURL('image/png');
    renderer.setPixelRatio(pr);
    size();
    draw();
    return url;
  }
  /* Record what the stage shows (with an optional caption painter) into a
     video. Returns a controller {stop() -> Promise<Blob>}. */
  function record(o) {
    o = o || {};
    const w = o.width || 1920, h = o.height || 1080;
    const out = document.createElement('canvas');
    out.width = w; out.height = h;
    const ctx = out.getContext('2d');
    const stream = out.captureStream(o.fps || 30);
    const types = ['video/mp4;codecs=avc1.640028', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
    const mime = types.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime, videoBitsPerSecond: 12e6 } : undefined);
    const chunks = [];
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    const R = {
      mime: mime || 'video/webm',
      grab() {
        const src = renderer.domElement;
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, w, h);
        const sc = Math.max(w / src.width, h / src.height);
        const dw = src.width * sc, dh = src.height * sc;
        ctx.drawImage(src, (w - dw) / 2, (h - dh) / 2, dw, dh);
        if (o.paint) o.paint(ctx, w, h);
      },
      stop() {
        return new Promise((res) => {
          rec.onstop = () => res(new Blob(chunks, { type: R.mime.split(';')[0] }));
          rec.stop();
          S.recording = null;
          dirty = true;
        });
      },
    };
    S.recording = R;
    rec.start(250);
    // keep frames coming even when nothing moves, so the video has a steady clock
    const keep = () => { if (S.recording === R) { dirty = true; return true; } return false; };
    anims.add(keep);
    start();
    return R;
  }

  function dispose() {
    stop();
    ro.disconnect();
    controls.dispose();
    [sceneT, sceneC].forEach((sc) => sc.traverse((o) => { o.geometry && o.geometry.dispose(); if (o.material) { o.material.map && o.material.map.dispose(); o.material.dispose && o.material.dispose(); } }));
    renderer.dispose();
    renderer.domElement.remove();
  }

  return {
    addBrain, addHpf, addLamina, addCells, setVolumes, setLuts, setHighlights, setSliceMode,
    setLevel, setCut, setView, setSlice, sliceToCcf, ccfToSlicePx,
    focus, glowCells, markArbor, hoverGlow, setVisible, setStory, setCrowd, showCrowd, explode, setProbe,
    flare, volley, pulseCell, fly, frameOn, getCam, setCam, project, cellSomaW, cellBounds, centroid,
    ride, pauseRide, stepRide, stopRide, reframe, setDark,
    snapshot, record, theme, dispose,
    pause: stop, resume: () => { dirty = true; start(); },
    has: (k) => Object.keys(byKey[k] || {}).length > 0,
    get level() { return S.level; }, get view() { return S.view; }, get slice() { return S.slice; },
    get rideState() { return S.ride ? { i: S.ride.i, n: S.ride.steps.length, paused: S.ride.paused, manual: S.manual, head: S.ride.head } : null; },
    poke: () => { dirty = true; },
    diag: () => ({ shaderErrors: shaderErrors.slice(), programs: renderer.info.programs.length, calls: renderer.info.render.calls,
                   tris: renderer.info.render.triangles, view: S.view, quad: !!(sliceQuad && sliceQuad.parent), caps: G.caps.children.length,
                   volumes: volumesReady, cut: S.cut.kind, gl2: renderer.capabilities.isWebGL2 }),
    set mini(v) { S.mini = !!v; dirty = true; },
    toCcf, W,
  };
}
