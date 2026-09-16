function [MI, MeanAmp] = ModIndexFast(Phase, Amp, nbin)
%MODINDEXFAST  Drop-in replacement for ModIndex_v2, vectorised over bands.
%
%   [MI, MeanAmp] = ModIndexFast(Phase, Amp, nbin)
%
%   Phase  1 x n   phase time series, radians, as angle(hilbert(.))
%   Amp    m x n   one or more amplitude envelopes on the same time base
%   nbin           phase bins, default 18
%
%   MI       m x 1
%   MeanAmp  m x nbin
%
%   Same numbers as ModIndex_v2.m to machine precision -- that is gate 4, and
%   it is asserted in test/test_ModIndexFast.m rather than promised here.
%
%   Convenience wrapper. Inside CFC.m the two halves are called separately so
%   the binning is computed once per (slow band, epoch) and reused across all
%   37 fast bands and every surrogate:
%
%       B = PhaseBins(phase, nbin);
%       MI = MIFromBins(Amp, B);

if nargin < 3, nbin = 18; end
B = PhaseBins(Phase, nbin);
[MI, MeanAmp] = MIFromBins(Amp, B);
end
