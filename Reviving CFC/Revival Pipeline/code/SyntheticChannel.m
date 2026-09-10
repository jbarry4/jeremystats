function sig = SyntheticChannel(durSec, fs, opts)
%SYNTHETICCHANNEL  A channel with known coupling, shaped like a real one.
%
%   sig = SyntheticChannel(durSec, fs, opts)
%
%   Produces the same struct LoadCSC returns, so every downstream step can be
%   exercised without touching a recording. The point is that you set the
%   ground truth and then check what the pipeline reports about it: if the
%   blob does not land at (fSlow, fFast), the bug is in the code, not the rat.
%
%   opts.fSlow    modulating rhythm, Hz          (default 7)
%   opts.fFast    modulated carrier, Hz          (default 65)
%   opts.depth    modulation depth, 0..1         (default 0.8)
%   opts.noise    pink background, x SD          (default 0.8)
%   opts.spikes   sharp transients per second    (default 0, set >0 to test panel G)
%   opts.seed
%
%   The slow rhythm is bandpass-filtered pink noise rather than a pure sine,
%   so its frequency and phase wander the way real theta does. This matters
%   for the surrogate test: circularly shifting an amplitude series against a
%   PERFECT sine changes only the preferred phase, not the coupling strength,
%   so the null collapses onto the observed value and the test says nothing.

arguments
    durSec (1,1) double = 120
    fs     (1,1) double = 3255.6
    opts.fSlow  (1,1) double = 7
    opts.fFast  (1,1) double = 65
    opts.depth  (1,1) double = 0.8
    opts.noise  (1,1) double = 0.8
    opts.spikes (1,1) double = 0
    opts.seed   (1,1) double = 7
end

rng(opts.seed, 'twister');
n = round(durSec * fs);
t = (0:n-1) / fs;

% --- slow rhythm: filtered pink noise, so phase wanders -----------------
slow = localPink(n, opts.seed + 1);
slow = eegfilt(slow, fs, opts.fSlow - 1.5, opts.fSlow + 1.5);
slow = slow / std(slow);
phi  = angle(hilbert(slow')');

% --- carrier, amplitude-modulated by that phase -------------------------
env  = 1 + opts.depth * sin(phi - pi/2);        % trough of slow -> quiet
fast = 0.45 * env .* sin(2*pi*opts.fFast*t);

% --- background ---------------------------------------------------------
bg = localPink(n, opts.seed + 99);
x  = slow + fast + opts.noise * bg;

% --- optional sharp transients (nothing is dropped; panel G shows them) --
nSpk = round(opts.spikes * durSec);
if nSpk > 0
    w = round(0.010 * fs);
    k = (-4*w:4*w) / fs;
    spike = exp(-0.5*(k/(0.010/2.5)).^2) - 0.45*exp(-0.5*((k-0.022)/(0.016)).^2);
    spike = spike / max(abs(spike));
    at = sort(randi([2*numel(k), n - 2*numel(k)], 1, nSpk));
    for a = at
        i0 = a - floor(numel(k)/2);
        x(i0:i0+numel(k)-1) = x(i0:i0+numel(k)-1) + 6*std(x)*spike;
    end
end

x = 60 * x;      % put it in a plausible microvolt range

sig = struct();
sig.lfp      = x;
sig.fs       = fs;
sig.T        = n;
sig.durSec   = n / fs;
sig.path     = sprintf('synthetic:%gHz-phase_%gHz-amp_depth%g', ...
                       opts.fSlow, opts.fFast, opts.depth);
sig.headerFs = fs;
sig.gaps     = table();
sig.clipRuns = 0;
sig.clipFrac = 0;
sig.loadedAt = datetime('now');
sig.truth    = struct('fSlow', opts.fSlow, 'fFast', opts.fFast, ...
                      'depth', opts.depth, 'spikes', nSpk);

fprintf('SyntheticChannel: %.0f s at %.1f Hz, coupling %g Hz -> %g Hz, depth %g\n', ...
        sig.durSec, fs, opts.fSlow, opts.fFast, opts.depth);
end


% =======================================================================
function y = localPink(n, seed)
rng(seed, 'twister');
x = randn(1, n);
X = fft(x);
f = (0:n-1) / n;
f(1) = f(2);
f(f > 0.5) = 1 - f(f > 0.5);
X = X ./ sqrt(max(f, eps));
y = real(ifft(X));
y = y / std(y);
end
