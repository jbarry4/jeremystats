function out = CFC(bank, ep, P, doSurrogates)
%CFC  Modulation index for every (slow band, fast band, epoch) cell.
%
%   out = CFC(bank, ep, P, doSurrogates)
%
%   out.MI   nSlow x nFast x nEp   single
%   out.z    nSlow x nFast x nEp   single, empty unless doSurrogates
%   out.surrMean, out.surrSD       the null each z was built from
%
%   Structure of the loop, and why it is this way round:
%
%     for each epoch
%       for each slow band
%          bin the phase ONCE                 <- PhaseBins
%          all 37 fast bands in one product   <- MIFromBins
%          for each surrogate
%             shift the bin positions, not the data, and redo the product
%
%   Shifting the bins rather than the amplitudes is what keeps the surrogate
%   step affordable: the bin structure is n numbers, the amplitude block is
%   37 x n. Circularly shifting the amplitude series by s and keeping the bins
%   fixed is exactly equivalent to keeping the amplitudes and shifting every
%   bin position by -s, and the second is 37 times less memory traffic.
%
%   The surrogate is a circular shift WITHIN the epoch. That destroys the
%   timing relationship between phase and envelope while leaving both signals'
%   own statistics -- spectrum, envelope shape, any transients -- untouched.
%   A shift smaller than P.minShiftSec is not used, because a tiny shift
%   leaves the relationship almost intact and biases the null upward.

if nargin < 4, doSurrogates = true; end

nSlow = P.nSlow;  nFast = P.nFast;  nEp = height(ep);
nbin  = P.nbin;

MI = zeros(nSlow, nFast, nEp, 'single');

wantZ = doSurrogates && P.nSurr > 0;
if wantZ
    surrMean = zeros(nSlow, nFast, nEp, 'single');
    surrSD   = zeros(nSlow, nFast, nEp, 'single');
    pVal     = zeros(nSlow, nFast, nEp, 'single');
else
    surrMean = [];  surrSD = [];  pVal = [];
end

if isfield(P, 'surrogate'), surrMode = P.surrogate; else, surrMode = 'within'; end

nSurr    = P.nSurr;
minShift = max(1, round(P.minShiftSec * bank.fs));
i0 = ep.i0;  i1 = ep.i1;

Phase = bank.Phase;   % nSlow x T
Amp   = bank.Amp;     % nFast x T

fprintf('CFC: %d slow x %d fast x %d epochs = %d cells\n', ...
        nSlow, nFast, nEp, nSlow*nFast*nEp);
if wantZ
    fprintf('   + %d surrogates each (%d modulation indices in total)\n', ...
            nSurr, nSlow*nFast*nEp*(nSurr+1));
end

tStart = tic;
for e = 1:nEp
    s0 = i0(e);  s1 = i1(e);
    n  = s1 - s0 + 1;

    Ae = double(Amp(:, s0:s1));          % nFast x n, once per epoch

    % shifts are drawn per epoch, shared across slow bands so that a given
    % surrogate index means the same displacement everywhere in the epoch
    if wantZ
        rng(P.seed + e, 'twister');
        shifts = randi([minShift, n - minShift], 1, nSurr);
        % 'cross' pairs this epoch's phase with another epoch's amplitude
        others = [1:e-1, e+1:nEp];
        if isempty(others), others = e; end
        pick   = others(randi(numel(others), 1, nSurr));
    end

    for j = 1:nSlow
        B     = PhaseBins(Phase(j, s0:s1), nbin);
        miObs = MIFromBins(Ae, B);
        MI(j, :, e) = single(miObs);

        if wantZ
            acc  = zeros(nFast, 1);
            acc2 = zeros(nFast, 1);
            ge   = zeros(nFast, 1);      % surrogates at least as extreme
            for k = 1:nSurr
                switch surrMode
                    case 'within'
                        m = MIFromBins(Ae, localShiftBins(B, shifts(k)));
                    case 'cross'
                        o = i0(pick(k));
                        m = MIFromBins(double(Amp(:, o:o+n-1)), B);
                    otherwise
                        error('CFC:surrogate', 'Unknown P.surrogate: %s', surrMode);
                end
                acc  = acc  + m;
                acc2 = acc2 + m.^2;
                ge   = ge   + (m >= miObs);
            end
            mu = acc / nSurr;
            sd = sqrt(max(acc2/nSurr - mu.^2, 0) * nSurr/(nSurr-1));
            surrMean(j, :, e) = single(mu);
            surrSD(j, :, e)   = single(sd);
            pVal(j, :, e)     = single((1 + ge) / (nSurr + 1));
        end
    end

    if mod(e, max(1, floor(nEp/10))) == 0 || e == nEp
        fprintf('   epoch %d/%d   %.1f s elapsed\n', e, nEp, toc(tStart));
    end
end

out = struct();
out.MI       = MI;
out.surrMean = surrMean;
out.surrSD   = surrSD;
out.p        = pVal;          % one-sided permutation p, (1+#{surr>=obs})/(nSurr+1)
out.elapsed  = toc(tStart);
out.nSurr    = wantZ * P.nSurr;
out.surrMode = surrMode;

if wantZ
    sd = surrSD;
    sd(sd == 0) = NaN;                 % a zero-variance null cannot make a z
    out.z = (MI - surrMean) ./ sd;
else
    out.z = [];
end

fprintf('CFC: done in %.1f s (%.2f ms per modulation index)\n', ...
        out.elapsed, 1000*out.elapsed/(nSlow*nFast*nEp*(1+out.nSurr)));
end


% =======================================================================
function Bs = localShiftBins(B, s)
%LOCALSHIFTBINS  Move every bin position back by s, wrapping in the epoch.
%   Equivalent to circularly shifting the amplitude series forward by s.
Bs      = B;
Bs.rows = mod(B.rows - s - 1, B.n) + 1;
Bs.S    = sparse(Bs.rows, B.cols, 1, B.n, B.nbin);
end
