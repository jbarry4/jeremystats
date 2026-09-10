function [pass, info] = gate1_looks_like_lfp(sig, P, outDir)
%GATE1  It looks like an LFP.
%
%   Passes if: fs is the decimated rate and not the raw one, the trace is
%   finite, the spectrum falls off like 1/f, and there is no mains peak left.
%
%   FAILS IF: wrong downsample, dead channel, notch off.

if nargin < 3, outDir = ''; end
fprintf('\n--- GATE 1: it looks like an LFP ---\n');

info = struct();
checks = {};

% fs should be the decimated rate. A raw Neuralynx CSC is ~32 kHz.
info.fs = sig.fs;
okFs = sig.fs > 500 && sig.fs < 8000;
checks{end+1} = {'fs is decimated, not raw', okFs, ...
                 sprintf('fs = %.2f Hz (raw would be ~%.0f)', sig.fs, sig.fs*P.downsample)};

% finite, and not flat
okFinite = all(isfinite(sig.lfp));
sdv = std(sig.lfp);
okAlive  = sdv > 1e-6;
checks{end+1} = {'all samples finite', okFinite, sprintf('%d non-finite', sum(~isfinite(sig.lfp)))};
checks{end+1} = {'channel is not dead',  okAlive,  sprintf('SD = %.2f uV', sdv)};

% spectrum: 1/f slope, and no mains peak
nfft = 2^nextpow2(min(sig.T, round(8*sig.fs)));
[pxx, f] = pwelch(sig.lfp, hann(nfft), nfft/2, nfft, sig.fs);
band = f > 2 & f < 200 & ~(f > 45 & f < 75);
pf = polyfit(log10(f(band)), log10(pxx(band)), 1);
info.spectralSlope = pf(1);
okSlope = pf(1) < -0.3;                 % real LFP is steeper than this
checks{end+1} = {'spectrum falls off like 1/f', okSlope, ...
                 sprintf('log-log slope = %.2f', pf(1))};

% mains: compare 59-61 Hz against 50-55 + 65-70 Hz shoulders
inN = f >= P.notch(1) & f <= P.notch(2);
inS = (f > 50 & f < 56) | (f > 64 & f < 70);
ratio = median(pxx(inN)) / median(pxx(inS));
info.mainsRatio = ratio;
okMains = ratio < 2;
checks{end+1} = {'no mains peak left', okMains, ...
                 sprintf('59-61 Hz / shoulders = %.2f x', ratio)};

% gaps and clipping are reported, not failed on
fprintf('    recording gaps: %d      flat runs: %d (%.4f%% of samples)\n', ...
        height(sig.gaps), sig.clipRuns, 100*sig.clipFrac);

pass = localReport(checks);
info.pass = pass;

% ---- the look-at-it half -----------------------------------------------
fig = figure('Color','w','Position',[80 80 1150 420],'Visible','on');
tiledlayout(fig,1,2,'TileSpacing','compact','Padding','compact');

ax1 = nexttile;
nShow = min(sig.T, round(10*sig.fs));
plot(ax1, (0:nShow-1)/sig.fs, sig.lfp(1:nShow), 'k-', 'LineWidth', 0.4);
xlabel(ax1,'time (s)'); ylabel(ax1,'\muV'); grid(ax1,'on');
title(ax1,'10 s of trace  -  theta should be visible by eye','FontWeight','normal');

ax2 = nexttile;
loglog(ax2, f, pxx, '-', 'LineWidth', 0.9, 'Color', [0.09 0.33 0.61]);
hold(ax2,'on');
xline(ax2, 60, 'r--', '60 Hz');
xlabel(ax2,'Hz'); ylabel(ax2,'\muV^2/Hz'); grid(ax2,'on');
xlim(ax2,[1 min(500, sig.fs/2)]);
title(ax2, sprintf('spectrum  -  slope %.2f, mains %.2fx', pf(1), ratio),'FontWeight','normal');

if ~isempty(outDir)
    if ~isfolder(outDir), mkdir(outDir); end
    exportgraphics(fig, fullfile(outDir,'gate1_lfp.png'), 'Resolution', 130);
end
end


function pass = localReport(checks)
pass = true;
for k = 1:numel(checks)
    c = checks{k};
    if c{2}, mark = 'PASS'; else, mark = 'FAIL'; pass = false; end
    fprintf('    [%s] %-32s %s\n', mark, c{1}, c{3});
end
if pass, fprintf('    GATE 1 PASSES\n'); else, fprintf('    GATE 1 FAILS\n'); end
end
