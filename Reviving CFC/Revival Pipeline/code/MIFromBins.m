function [MI, MeanAmp] = MIFromBins(Amp, B)
%MIFROMBINS  Tort modulation index for many amplitude bands at once.
%
%   [MI, MeanAmp] = MIFromBins(Amp, B)
%
%   Amp  m x n  amplitude envelopes, m bands sharing one time base
%   B           output of PhaseBins for the matching phase series
%
%   MI       m x 1
%   MeanAmp  m x nbin, non-normalised, same as ModIndex_v2's second output
%
%   The arithmetic is identical to ModIndex_v2.m:
%
%       P_j = <A>_j / sum_k <A>_k
%       H   = -sum_j P_j log P_j
%       MI  = (log N - H) / log N
%
%   The only difference is that the mean amplitude per bin is obtained by one
%   sparse matrix product across all m bands instead of m * nbin find() calls.
%   Amp is cast to double for the product: MATLAB has no single sparse type,
%   and accumulating 19,530 terms in single would cost more precision than
%   gate 4's 1e-12 tolerance allows.

Amp = double(Amp);
if isvector(Amp), Amp = Amp(:).'; end

sums    = Amp * B.S;                 % m x nbin
MeanAmp = sums ./ B.counts;          % empty bin -> 0/0 -> NaN, as ModIndex_v2

Pp = MeanAmp ./ sum(MeanAmp, 2);
MI = (log(B.nbin) + sum(Pp .* log(Pp), 2)) / log(B.nbin);
end
