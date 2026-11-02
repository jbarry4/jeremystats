function B = PhaseBins(Phase, nbin)
%PHASEBINS  Which of the nbin phase bins each sample falls into. Computed once.
%
%   B = PhaseBins(Phase, nbin)
%
%   This is the whole trick behind ModIndexFast. ModIndex_v2.m re-derives bin
%   membership with nbin separate find() passes for EVERY modulation index.
%   Membership depends only on the phase series, so for a given slow band and
%   epoch it can be computed once and reused for all 37 fast bands and all
%   100 surrogates. The saving is not in doing the comparisons faster -- they
%   are done here exactly as ModIndex_v2 does them -- it is in doing them
%   3,700 times fewer times.
%
%   The comparisons are deliberately the literal ones from ModIndex_v2:
%
%       find(Phase >= position(j)  &  Phase < position(j) + winsize)
%
%   NOT discretize() against [position, pi], and NOT floor((Phase+pi)/winsize).
%   Both of those are the "obvious" vectorisation and both are subtly wrong,
%   for the same reason: ModIndex_v2 recomputes each bin's upper edge as
%   position(j) + winsize, which is not bit-identical to position(j+1).
%   Where position(j)+winsize lands one ulp above position(j+1), a sample at
%   exactly position(j+1) satisfies BOTH bins' tests and is counted twice;
%   where it lands one ulp below, such a sample is counted in neither. So
%   ModIndex_v2's bins are not a partition, and reproducing it means
%   reproducing that, overlaps and gaps included.
%
%   This matters only for samples sitting exactly on an edge, which for real
%   LFP phase is a measure-zero event -- but test_ModIndexFast.m constructs
%   it on purpose, because an assertion that only holds for generic input is
%   not the assertion gate 4 claims to be making.
%
%   Fields
%     B.n        number of samples
%     B.nbin     number of bins
%     B.rows     sample index of every (sample, bin) assignment
%     B.cols     the bin of each assignment
%     B.counts   1 x nbin, assignments per bin (what ModIndex_v2 averages over)
%     B.S        n x nbin sparse indicator, so sums = Amp * S
%     B.nDropped samples in no bin at all
%     B.nDouble  samples counted in more than one bin

if nargin < 2, nbin = 18; end

Phase = Phase(:).';
n     = numel(Phase);

winsize  = 2*pi/nbin;
position = zeros(1, nbin);
for j = 1:nbin
    position(j) = -pi + (j-1)*winsize;      % built exactly as ModIndex_v2 builds it
end

per = cell(1, nbin);
for j = 1:nbin
    per{j} = find(Phase >= position(j) & Phase < position(j) + winsize);
end

counts  = cellfun(@numel, per);
allRows = [per{:}];
allCols = repelem(1:nbin, counts);

hits = accumarray(allRows(:), 1, [n 1]);

B          = struct();
B.n        = n;
B.nbin     = nbin;
B.rows     = allRows;
B.cols     = allCols;
B.counts   = counts;
B.S        = sparse(allRows, allCols, 1, n, nbin);
B.nDropped = sum(hits == 0);
B.nDouble  = sum(hits > 1);
B.position = position;
end
