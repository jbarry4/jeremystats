function [pass, info] = gate4_fast_matches_reference(bank, ep, P, nTrials)
%GATE4  ModIndexFast == ModIndex_v2, exactly.
%
%   The assertion that makes the surrogate step affordable. Without it you
%   are trusting a rewrite of the only line of arithmetic that matters.
%
%   This is the in-run version. The re-runnable version, which does not need
%   a loaded recording, is test/test_ModIndexFast.m.
%
%   FAILS IF: bin edges differ - check the half-open interval.

if nargin < 4, nTrials = 40; end
fprintf('\n--- GATE 4: fast == reference, exactly ---\n');

nbin = P.nbin;
position = zeros(1, nbin);
winsize  = 2*pi/nbin;
for j = 1:nbin, position(j) = -pi + (j-1)*winsize; end

rng(1234, 'twister');
nEp = height(ep);

worst = 0;  worstAmp = 0;  tFast = 0;  tRef = 0;
for k = 1:nTrials
    e = randi(nEp);
    j = randi(P.nSlow);
    i = randi(P.nFast);
    s0 = ep.i0(e);  s1 = ep.i1(e);

    ph = double(bank.Phase(j, s0:s1));
    am = double(bank.Amp(i,  s0:s1));

    t0 = tic;  [miRef, maRef] = ModIndex_v2(ph, am, position);  tRef  = tRef  + toc(t0);
    t0 = tic;  [miFast, maFast] = ModIndexFast(ph, am, nbin);   tFast = tFast + toc(t0);

    worst    = max(worst,    abs(miFast - miRef));
    worstAmp = max(worstAmp, max(abs(maFast(:) - maRef(:))));
end

tol = 1e-12;
info = struct('maxAbsDiffMI', worst, 'maxAbsDiffMeanAmp', worstAmp, ...
              'nTrials', nTrials, 'tol', tol, ...
              'msPerRef', 1000*tRef/nTrials, 'msPerFast', 1000*tFast/nTrials, ...
              'speedup', tRef/max(tFast, eps));

pass = worst < tol;
fprintf('    %d random (slow band, fast band, epoch) triples\n', nTrials);
fprintf('    max |MI_fast - MI_v2|       = %.3e   (tolerance %.0e)\n', worst, tol);
fprintf('    max |MeanAmp difference|    = %.3e\n', worstAmp);
fprintf('    ModIndex_v2  %.3f ms per MI\n', info.msPerRef);
fprintf('    ModIndexFast %.3f ms per MI   (%.1fx)\n', info.msPerFast, info.speedup);
if pass, fprintf('    GATE 4 PASSES\n'); else
    fprintf('    GATE 4 FAILS - the two do not agree. Check the half-open bin edge.\n');
end
info.pass = pass;
end
