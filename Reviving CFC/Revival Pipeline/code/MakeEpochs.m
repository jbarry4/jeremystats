function ep = MakeEpochs(sig, P)
%MAKEEPOCHS  Cut the trace into non-overlapping blocks. Drop nothing.
%
%   ep = MakeEpochs(sig, P)
%
%   floor(T / epochSec) blocks, no overlap, no rejection. maxAbs and nSharp
%   are RECORDED so that if a transient ever turns out to dominate an epoch
%   you can find it in the table and test the assumption later -- without
%   re-running anything, and without having thrown data away first.
%
%   Columns
%     idx     1..nEp
%     t0,t1   epoch bounds in seconds from the start of the trace
%     i0,i1   sample indices, inclusive
%     maxAbs  max |lfp| in the epoch, microvolts
%     nSharp  samples exceeding P.sharpSD robust SDs of the whole trace
%
%   nSharp uses a robust SD (median absolute deviation) so that a handful of
%   large transients cannot inflate the threshold that is meant to find them.

if nargin < 2, P = params(); end

n    = round(P.epochSec * sig.fs);          % samples per epoch
nEp  = floor(sig.T / n);
assert(nEp > 0, 'MakeEpochs:tooShort', ...
      'Trace is %.1f s, shorter than one %g s epoch.', sig.durSec, P.epochSec);

idx = (1:nEp).';
i0  = (idx - 1) * n + 1;
i1  = i0 + n - 1;
t0  = (i0 - 1) / sig.fs;
t1  =  i1      / sig.fs;

% robust SD of the whole trace: 1.4826 * MAD
sd  = 1.4826 * median(abs(sig.lfp - median(sig.lfp)));
thr = P.sharpSD * sd;

maxAbs = zeros(nEp, 1);
nSharp = zeros(nEp, 1);
for k = 1:nEp
    seg        = sig.lfp(i0(k):i1(k));
    maxAbs(k)  = max(abs(seg));
    nSharp(k)  = sum(abs(seg) > thr);
end

ep = table(idx, t0, t1, i0, i1, maxAbs, nSharp);
ep.Properties.UserData = struct('epochSamples', n, 'robustSD', sd, ...
                                'sharpThreshold', thr, 'fs', sig.fs);

fprintf('MakeEpochs: %d epochs of %g s (%d samples each)\n', nEp, P.epochSec, n);
fprintf('   %d samples unused at the tail (%.3f s)\n', ...
        sig.T - nEp*n, (sig.T - nEp*n)/sig.fs);
fprintf('   robust SD = %.2f uV, sharp threshold = %.2f uV, %d sharp samples total\n', ...
        sd, thr, sum(nSharp));
end
