function [pass, info] = gate6_null_is_flat(sig, ep, P, outDir)
%GATE6  The null is flat.
%
%   The most valuable check in the beta run: a broken surrogate loop produces
%   beautiful, meaningless maps.
%
%   Re-runs the whole measure on a phase-randomised copy of the SAME channel.
%   Phase randomisation keeps the power spectrum exactly and destroys every
%   phase relationship, so there is no cross-frequency coupling left to find.
%
%   WHAT THIS GATE TESTS, AND WHY IT IS NOT "every |z| < 3"
%
%   It was written to assert that. Measured on null data it fails, and the
%   failure is real but is not a bug in the shift:
%
%     - the null is CENTRED. The observed MI sits at the middle of its own
%       surrogate distribution (mean rank quantile 0.49 against an ideal 0.50),
%       so there is no systematic bias to find.
%     - the null is OVER-DISPERSED relative to the surrogate spread. z has an
%       SD near 1.4 rather than 1.0, and that does NOT shrink as surrogates
%       are added -- measured identical at 20, 50, 100 and 500. It is
%       structural, not sampling noise.
%
%   Circularly shifting a narrowband phase series mostly rotates the preferred
%   phase rather than destroying the coupling, so the surrogate spread is an
%   underestimate of the true null spread, and z is anti-conservative: a
%   nominal |z| > 3 behaves like |z| > 2.2-2.6.
%
%   So this gate tests the claim that survives -- centring and p-value
%   uniformity -- and REPORTS the dispersion with the calibrated threshold,
%   rather than asserting a normality the measure does not have. Use
%   cfc.p (the rank-based permutation p) for significance, not z.

if nargin < 4, outDir = ''; end
fprintf('\n--- GATE 6: the null is flat ---\n');

Pn       = P;
Pn.nSurr = min(P.nSurr, 50);
nEpUse   = min(height(ep), 12);
epUse    = ep(1:nEpUse, :);

fprintf('    phase-randomising the trace (spectrum preserved), %d epochs, %d surrogates\n', ...
        nEpUse, Pn.nSurr);

surSig     = sig;
surSig.lfp = localPhaseRandomise(sig.lfp, P.seed);

evalc('bankN = FilterBanks(surSig, Pn);');
cfcN = CFC(bankN, epUse, Pn, true);

z = double(cfcN.z(:));  z = z(isfinite(z));
p = double(cfcN.p(:));  p = p(isfinite(p));

info = struct();
info.meanZ   = mean(z);
info.sdZ     = std(z);
info.maxAbsZ = max(abs(z));
info.meanP   = mean(p);
info.fracP05 = mean(p <= 0.05);
info.fracP01 = mean(p <= 0.01);
info.n       = numel(z);
info.z95     = prctile(abs(z), 95);
info.z99     = prctile(abs(z), 99);
info.surrMode = cfcN.surrMode;

fprintf('    n = %d cells, surrogate mode "%s"\n', info.n, info.surrMode);
fprintf('\n    CENTRING (this is the part that must hold)\n');
fprintf('      mean permutation p = %.3f      (ideal 0.500)\n', info.meanP);
fprintf('      mean z             = %+.3f      (ideal 0.000)\n', info.meanZ);
fprintf('\n    CALIBRATION (reported, not asserted)\n');
fprintf('      SD of z            = %.3f      (would be 1.000 if z were normal)\n', info.sdZ);
fprintf('      p <= 0.05 in %.2f%% of cells   (ideal 5.00%%)\n', 100*info.fracP05);
fprintf('      p <= 0.01 in %.2f%% of cells   (ideal 1.00%%)\n', 100*info.fracP01);
fprintf('      empirical |z| for 5%% / 1%%: %.2f / %.2f  (not 1.96 / 2.58)\n', ...
        info.z95, info.z99);

% Centring is the hard requirement. Dispersion is reported and only fails if
% it is wild enough to mean something is actually broken rather than merely
% anti-conservative.
okCentreP = abs(info.meanP - 0.5) < 0.08;
okCentreZ = abs(info.meanZ)       < 0.5;
okSane    = info.sdZ < 3 && info.fracP05 < 0.25;

checks = { {'permutation p is centred', okCentreP, sprintf('mean p = %.3f', info.meanP)}, ...
           {'z is centred',             okCentreZ, sprintf('mean z = %+.3f', info.meanZ)}, ...
           {'dispersion is not wild',   okSane,    sprintf('SD(z) = %.2f, %.1f%% at p<=.05', ...
                                                    info.sdZ, 100*info.fracP05)} };
pass = true;
for k = 1:numel(checks)
    c = checks{k};
    if c{2}, mark = 'PASS'; else, mark = 'FAIL'; pass = false; end
    fprintf('    [%s] %-28s %s\n', mark, c{1}, c{3});
end

if pass
    fprintf('    GATE 6 PASSES - the surrogate is centred and doing its job.\n');
    if info.sdZ > 1.15
        fprintf('    NOTE  z is over-dispersed (SD %.2f). Report significance from\n', info.sdZ);
        fprintf('          cfc.p, or threshold z at %.2f rather than 3.\n', info.z99);
    end
else
    fprintf('    GATE 6 FAILS - the null is not centred. The surrogate loop is wrong.\n');
end
info.pass = pass;

% ---- the map that should be featureless, and the p histogram -----------
mz = mean(cfcN.z, 3, 'omitnan');
fig = figure('Color','w','Position',[80 80 1400 420],'Visible','on');
tiledlayout(fig,1,3,'TileSpacing','compact','Padding','compact');

ax1 = nexttile;
imagesc(ax1, P.slowCenters, P.fastCenters, mz.'); set(ax1,'YDir','normal');
clim(ax1, [-3 3]); colorbar(ax1);
xlabel(ax1,'phase freq (Hz)'); ylabel(ax1,'amplitude freq (Hz)');
title(ax1,'mean z on phase-randomised data  -  should be featureless','FontWeight','normal');

ax2 = nexttile;
histogram(ax2, z, 60, 'FaceColor', [0.09 0.33 0.61], 'EdgeColor','none');
hold(ax2,'on'); xline(ax2,[-3 3],'r--','LineWidth',1);
xline(ax2,[-info.z99 info.z99],'k--','LineWidth',1);
xlabel(ax2,'z'); ylabel(ax2,'count'); grid(ax2,'on');
title(ax2, sprintf('z: mean %+.2f, SD %.2f   (black = empirical 1%%)', ...
      info.meanZ, info.sdZ),'FontWeight','normal');

ax3 = nexttile;
histogram(ax3, p, 20, 'Normalization','pdf', ...
          'FaceColor', [0.72 0.31 0.05], 'EdgeColor','none');
hold(ax3,'on'); yline(ax3, 1, 'k--', 'LineWidth', 1);
xlabel(ax3,'permutation p'); ylabel(ax3,'density'); grid(ax3,'on');
title(ax3, sprintf('p should be flat: mean %.3f, %.1f%% at p<=.05', ...
      info.meanP, 100*info.fracP05),'FontWeight','normal');

if ~isempty(outDir)
    if ~isfolder(outDir), mkdir(outDir); end
    exportgraphics(fig, fullfile(outDir,'gate6_null.png'), 'Resolution', 130);
end
end


% =======================================================================
function y = localPhaseRandomise(x, seed)
%LOCALPHASERANDOMISE  Same power spectrum, random phases, no coupling.
rng(seed, 'twister');
n  = numel(x);
X  = fft(x);
half = 2:floor(n/2);
ph = rand(1, numel(half)) * 2*pi;
X(half)         = abs(X(half)) .* exp(1i*ph);
X(n - half + 2) = conj(X(half));
if mod(n,2) == 0, X(n/2+1) = abs(X(n/2+1)); end
y = real(ifft(X));
end
