/* ---- tiny DSP kit used by every interactive panel on the page ---- */
function fftInPlace(re, im, inverse){
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { let t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (inverse ? 2 : -2) * Math.PI / len;
    const wr = Math.cos(ang), wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < len / 2; k++) {
        const ur = re[i+k], ui = im[i+k];
        const vr = re[i+k+len/2]*cr - im[i+k+len/2]*ci;
        const vi = re[i+k+len/2]*ci + im[i+k+len/2]*cr;
        re[i+k] = ur + vr; im[i+k] = ui + vi;
        re[i+k+len/2] = ur - vr; im[i+k+len/2] = ui - vi;
        const ncr = cr*wr - ci*wi; ci = cr*wi + ci*wr; cr = ncr;
      }
    }
  }
  if (inverse) for (let i = 0; i < n; i++) { re[i] /= n; im[i] /= n; }
}

function rfft(x){
  const n = x.length;
  const re = Float64Array.from(x), im = new Float64Array(n);
  fftInPlace(re, im, false);
  return {re, im, n};
}

/* Analytic signal of one band, straight from the spectrum:
   keep only positive frequencies inside [lo,hi], double them, inverse FFT.
   The result's modulus is the envelope and its argument is the phase —
   the same thing abs(hilbert(eegfilt(...))) and angle(hilbert(eegfilt(...)))
   give in the MATLAB, just done in one step. */
function bandAnalytic(X, sr, lo, hi){
  const n = X.n;
  const re = new Float64Array(n), im = new Float64Array(n);
  const df = sr / n;
  const k1 = Math.max(1, Math.floor(lo/df)), k2 = Math.min(n/2 - 1, Math.ceil(hi/df));
  const taper = Math.max(1, Math.round((k2 - k1) * 0.15));
  for (let k = k1; k <= k2; k++){
    let w = 1;
    if (k - k1 < taper) w = 0.5 - 0.5*Math.cos(Math.PI*(k - k1)/taper);
    if (k2 - k < taper) w = Math.min(w, 0.5 - 0.5*Math.cos(Math.PI*(k2 - k)/taper));
    re[k] = 2*w*X.re[k]; im[k] = 2*w*X.im[k];
  }
  fftInPlace(re, im, true);
  return {re, im};
}

function envelope(a){ const n=a.re.length, o=new Float64Array(n);
  for(let i=0;i<n;i++) o[i]=Math.hypot(a.re[i],a.im[i]); return o; }
function phaseOf(a){ const n=a.re.length, o=new Float64Array(n);
  for(let i=0;i<n;i++) o[i]=Math.atan2(a.im[i],a.re[i]); return o; }

const NBIN = 18;
function meanAmpByPhase(phase, amp, from, to){
  const s = new Float64Array(NBIN), c = new Float64Array(NBIN);
  const a = from|0, b = (to === undefined ? phase.length : to)|0;
  for (let i = a; i < b; i++){
    let j = Math.floor((phase[i] + Math.PI) * NBIN / (2*Math.PI));
    if (j < 0) j = 0; else if (j >= NBIN) j = NBIN - 1;
    s[j] += amp[i]; c[j]++;
  }
  for (let j = 0; j < NBIN; j++) s[j] = c[j] ? s[j]/c[j] : 0;
  return s;
}
function modIndexFromMeanAmp(ma){
  let tot = 0; for (let j=0;j<NBIN;j++) tot += ma[j];
  if (!(tot > 0)) return {mi:0, P:new Float64Array(NBIN), H:Math.log(NBIN)};
  const P = new Float64Array(NBIN); let H = 0;
  for (let j=0;j<NBIN;j++){ P[j] = ma[j]/tot; if (P[j] > 0) H -= P[j]*Math.log(P[j]); }
  return {mi:(Math.log(NBIN) - H)/Math.log(NBIN), P, H};
}

/* deterministic RNG so the page looks the same for everyone */
function rng(seed){ let s = seed >>> 0; return () => {
  s ^= s << 13; s >>>= 0; s ^= s >> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; }
function gauss(r){ let u=0,v=0; while(!u) u=r(); while(!v) v=r();
  return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v); }

function pinkNoise(n, seed){
  const r = rng(seed);
  const re = new Float64Array(n), im = new Float64Array(n);
  for (let i=0;i<n;i++) re[i] = gauss(r);
  fftInPlace(re, im, false);
  for (let k=1;k<n;k++){ const f = Math.min(k, n-k); const g = 1/Math.sqrt(f);
    re[k]*=g; im[k]*=g; }
  re[0]=0; im[0]=0;
  fftInPlace(re, im, true);
  let m=0, s=0; for(let i=0;i<n;i++) m+=re[i]; m/=n;
  for(let i=0;i<n;i++) s+=(re[i]-m)*(re[i]-m); s=Math.sqrt(s/n)||1;
  const o=new Float64Array(n); for(let i=0;i<n;i++) o[i]=(re[i]-m)/s;
  return o;
}

/* One synthetic channel: a wandering slow rhythm, a fast oscillation whose
   loudness follows the slow rhythm's phase, background noise, and optional
   sharp interictal-like transients. */
function makeLFP(opt){
  const {n, sr, fp, fa, depth, noise, spikeRate, seed} = opt;
  const t0 = pinkNoise(n, seed);
  const Xn = rfft(t0);
  const slowA = bandAnalytic(Xn, sr, Math.max(0.5, fp-1.5), fp+1.5);
  const slow = new Float64Array(n); let sd=0;
  for(let i=0;i<n;i++) slow[i]=slowA.re[i];
  for(let i=0;i<n;i++) sd += slow[i]*slow[i]; sd = Math.sqrt(sd/n)||1;
  for(let i=0;i<n;i++) slow[i] /= sd;
  const ph = phaseOf(slowA);
  const bg = pinkNoise(n, seed + 977);
  const out = new Float64Array(n);
  for (let i=0;i<n;i++){
    const mod = 1 + depth*Math.sin(ph[i] - Math.PI/2);
    out[i] = slow[i] + 0.45*mod*Math.sin(2*Math.PI*fa*i/sr) + noise*bg[i];
  }
  if (spikeRate > 0){
    const r = rng(seed + 31), nev = Math.round(spikeRate * n/sr);
    const w = Math.round(0.010*sr), half = 4*w;
    for (let e=0;e<nev;e++){
      const c = Math.floor(r()*(n - 2*half)) + half;
      for (let k=-half;k<=half;k++){
        const tt = k/sr;
        const v = Math.exp(-0.5*Math.pow(tt/(0.010/2.5),2))
                - 0.45*Math.exp(-0.5*Math.pow((tt-2.2*0.010)/(0.010*1.6),2));
        out[c+k] += 5*v;
      }
    }
  }
  return out;
}

/* A biquad bandpass, used only by the filtfilt demo, because an IIR filter
   is where "runs it twice" is easiest to see. */
function biquadBandpass(sr, f0, Q){
  const w0 = 2*Math.PI*f0/sr, a = Math.sin(w0)/(2*Q), c = Math.cos(w0);
  const b0 = a, b1 = 0, b2 = -a, a0 = 1+a, a1 = -2*c, a2 = 1-a;
  return {b:[b0/a0,b1/a0,b2/a0], a:[1,a1/a0,a2/a0]};
}
function lfilter(co, x){
  const {b,a} = co, n = x.length, y = new Float64Array(n);
  let x1=0,x2=0,y1=0,y2=0;
  for (let i=0;i<n;i++){
    const v = b[0]*x[i] + b[1]*x1 + b[2]*x2 - a[1]*y1 - a[2]*y2;
    x2=x1; x1=x[i]; y2=y1; y1=v; y[i]=v;
  }
  return y;
}
function filtfilt(co, x){
  const f = lfilter(co, x);
  const rev = Float64Array.from(f).reverse();
  const b2 = lfilter(co, rev);
  return Float64Array.from(b2).reverse();
}
if (typeof module !== "undefined") module.exports = {fftInPlace,rfft,bandAnalytic,envelope,phaseOf,
  meanAmpByPhase,modIndexFromMeanAmp,makeLFP,pinkNoise,biquadBandpass,lfilter,filtfilt,NBIN};
