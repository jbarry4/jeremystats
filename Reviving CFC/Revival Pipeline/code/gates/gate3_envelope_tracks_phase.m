function [pass, info] = gate3_envelope_tracks_phase(sig, bank, ep, P, outDir)
%GATE3  The envelope tracks the phase.
%
%   Plots one fast envelope over one slow band for 2 s. It should visibly
%   rise and fall with the slow cycle.
%
%   If nothing tracks anything, check the fast bandwidth before blaming
%   biology: a 10 Hz-wide band centred at 80 Hz cannot carry 8 Hz amplitude
%   modulation, because the sidebands at 72 and 88 Hz fall outside it. This
%   gate reports that arithmetic explicitly rather than leaving you to
%   rediscover it.

if nargin < 5, outDir = ''; end
fprintf('\n--- GATE 3: the envelope tracks the phase ---\n');

% Pick the pair with the strongest coupling in the middle of the recording,
% so the picture shows the best case rather than an arbitrary one.
eMid = max(1, round(height(ep)/2));
s0 = ep.i0(eMid);  s1 = ep.i1(eMid);
Ae = double(bank.Amp(:, s0:s1));

MIe = zeros(P.nSlow, P.nFast);
for j = 1:P.nSlow
    B = PhaseBins(bank.Phase(j, s0:s1), P.nbin);
    MIe(j, :) = MIFromBins(Ae, B).';
end
[~, lin] = max(MIe(:));
[jP, iP] = ind2sub(size(MIe), lin);

fSlow = P.slowCenters(jP);
fFast = P.fastCenters(iP);

% --- the bandwidth arithmetic -------------------------------------------
% Amplitude modulation of a carrier at fFast by a rhythm at fSlow puts
% sidebands at fFast +/- fSlow. They must fit inside the fast band.
halfBW  = P.fastBW / 2;
canCarry = fSlow <= halfBW;
info = struct('fSlow', fSlow, 'fFast', fFast, 'fastBW', P.fastBW, ...
              'sidebandsFit', canCarry, 'MIpeak', MIe(jP, iP));

fprintf('    strongest pair in epoch %d: %.2f Hz phase / %.0f Hz amplitude, MI = %.5f\n', ...
        eMid, fSlow, fFast, MIe(jP, iP));
fprintf('    sidebands sit at %.0f and %.0f Hz; the fast band is %.0f Hz wide (+/- %.0f Hz).\n', ...
        fFast - fSlow, fFast + fSlow, P.fastBW, halfBW);

checks = {};
checks{end+1} = {'sidebands fit in the fast band', canCarry, ...
        sprintf('need bandwidth >= %.1f Hz, have %.1f Hz', 2*fSlow, P.fastBW)};
checks{end+1} = {'some pair shows modulation', MIe(jP,iP) > 0, ...
        sprintf('peak MI = %.5f', MIe(jP,iP))};

pass = true;
for k = 1:numel(checks)
    c = checks{k};
    if c{2}, mark = 'PASS'; else, mark = 'WARN'; end
    if ~c{2} && k == 2, pass = false; end
    fprintf('    [%s] %-34s %s\n', mark, c{1}, c{3});
end
if ~canCarry
    fprintf('    NOTE  The fast bandwidth is too narrow to carry this modulation.\n');
    fprintf('          That is an analysis limit, not a result. Widen P.fastBW to >= %.0f Hz\n', ceil(2*fSlow));
    fprintf('          if you want coupling at %.2f Hz to be detectable at all.\n', fSlow);
end
if pass, fprintf('    GATE 3 PASSES (look at the figure before believing it)\n');
else,    fprintf('    GATE 3 FAILS\n'); end
info.pass = pass;

% ---- 2 s of the two signals --------------------------------------------
nShow = min(round(2*sig.fs), s1-s0+1);
idx   = s0:(s0+nShow-1);
t     = (idx - s0) / sig.fs;

slowBand = double(bank.SlowEnv(jP, idx)) .* cos(double(bank.Phase(jP, idx)));
env      = double(bank.Amp(iP, idx));

fig = figure('Color','w','Position',[80 80 1150 430],'Visible','on');
ax = axes(fig);
yyaxis(ax,'left');
plot(ax, t, slowBand, '-', 'LineWidth', 1.3, 'Color', [0.09 0.33 0.61]);
ylabel(ax, sprintf('%.2f Hz band (\\muV)', fSlow));
yyaxis(ax,'right');
plot(ax, t, env, '-', 'LineWidth', 1.3, 'Color', [0.72 0.31 0.05]);
ylabel(ax, sprintf('%.0f Hz envelope (\\muV)', fFast));
xlabel(ax,'time (s)'); grid(ax,'on');
title(ax, sprintf(['GATE 3   the %.0f Hz envelope should rise and fall with the %.2f Hz cycle' ...
      '   (epoch %d, MI = %.5f)'], fFast, fSlow, eMid, MIe(jP,iP)), 'FontWeight','normal');

if ~isempty(outDir)
    if ~isfolder(outDir), mkdir(outDir); end
    exportgraphics(fig, fullfile(outDir,'gate3_envelope.png'), 'Resolution', 130);
end
end
