function fig = ChannelQC(sig, ep, cfc, Pw, P, tag, outDir)
%CHANNELQC  Seven panels: everything you need to believe or reject one channel.
%
%   fig = ChannelQC(sig, ep, cfc, Pw, P, tag, outDir)
%
%   Panel B is the one that matters most and is the reason IED detection was
%   dropped rather than replaced. The raw trace sits directly under the
%   MI-over-time trace, sharing an x axis, so a modulation index driven by a
%   single transient is visible as a transient rather than averaged into the
%   mean and never seen again. Nothing was removed from the data; the check
%   is that you can look.
%
%   A  MI over time at the peak cell        E  MI across the slow bands
%   B  raw LFP, same time axis as A         F  theta power vs MI  (Output C)
%   C  mean comodulogram                    G  epoch diagnostics: maxAbs, nSharp
%   D  mean z, or mean MI if no surrogates

if nargin < 7, outDir = pwd; end
if ~isfolder(outDir), mkdir(outDir); end

MI  = cfc.MI;                       % nSlow x nFast x nEp
tEp = ep.t0 + (ep.t1 - ep.t0)/2;
mMI = mean(MI, 3, 'omitnan');       % nSlow x nFast

% peak cell of the time-averaged comodulogram
[~, lin]      = max(mMI(:));
[jPeak, iPeak] = ind2sub(size(mMI), lin);
miPeak = squeeze(MI(jPeak, iPeak, :));

fig = figure('Color', 'w', 'Position', [60 60 1500 1000], 'Visible', 'on');
tl  = tiledlayout(fig, 4, 3, 'TileSpacing', 'compact', 'Padding', 'compact');
title(tl, sprintf('%s   -   %s', tag, strrep(sig.path, '\', '/')), ...
      'Interpreter', 'none', 'FontWeight', 'bold');

% ---- A: MI over time at the peak cell ----------------------------------
axA = nexttile(tl, [1 3]);
plot(axA, tEp, miPeak, '-', 'LineWidth', 1.1, 'Color', [0.09 0.33 0.61]);
ylabel(axA, 'MI');
title(axA, sprintf('A   MI over time at the peak cell:  %.2f Hz phase / %.0f Hz amplitude', ...
      P.slowCenters(jPeak), P.fastCenters(iPeak)), 'FontWeight', 'normal');
grid(axA, 'on');  axA.XTickLabel = [];

% ---- B: the raw trace, SAME time axis ----------------------------------
axB = nexttile(tl, [1 3]);
tRaw = (0:sig.T-1) / sig.fs;
step = max(1, floor(numel(tRaw)/200000));       % decimate for drawing only
plot(axB, tRaw(1:step:end), sig.lfp(1:step:end), '-', ...
     'LineWidth', 0.3, 'Color', [0.35 0.35 0.35]);
ylabel(axB, '\muV');  xlabel(axB, 'time (s)');
title(axB, 'B   raw LFP, same axis as A  -  a transient-driven MI spike is visible here', ...
      'FontWeight', 'normal');
grid(axB, 'on');
linkaxes([axA axB], 'x');
xlim(axA, [tEp(1)-P.epochSec, tEp(end)+P.epochSec]);

% ---- C: mean comodulogram ----------------------------------------------
axC = nexttile(tl);
imagesc(axC, P.slowCenters, P.fastCenters, mMI.');
set(axC, 'YDir', 'normal');  colormap(axC, parula);  colorbar(axC);
xlabel(axC, 'phase freq (Hz)');  ylabel(axC, 'amplitude freq (Hz)');
title(axC, 'C   mean MI over epochs', 'FontWeight', 'normal');
hold(axC, 'on');
plot(axC, P.slowCenters(jPeak), P.fastCenters(iPeak), 'w+', 'MarkerSize', 11, 'LineWidth', 1.4);

% ---- D: mean z, or a second view of MI if surrogates were skipped ------
axD = nexttile(tl);
if ~isempty(cfc.z)
    mz = mean(cfc.z, 3, 'omitnan');
    imagesc(axD, P.slowCenters, P.fastCenters, mz.');
    set(axD, 'YDir', 'normal');  colormap(axD, parula);  colorbar(axD);
    cl = max(3, min(10, max(abs(mz(:)))));
    clim(axD, [-cl cl]);
    title(axD, sprintf('D   mean z  (%d surrogates)', cfc.nSurr), 'FontWeight', 'normal');
else
    imagesc(axD, P.slowCenters, P.fastCenters, log10(mMI.'));
    set(axD, 'YDir', 'normal');  colormap(axD, parula);  colorbar(axD);
    title(axD, 'D   log_{10} mean MI  (no surrogates run)', 'FontWeight', 'normal');
end
xlabel(axD, 'phase freq (Hz)');  ylabel(axD, 'amplitude freq (Hz)');

% ---- E: MI across the slow bands ---------------------------------------
axE = nexttile(tl);
perSlow = squeeze(mean(MI, 2, 'omitnan'));        % nSlow x nEp
mu = mean(perSlow, 2);
sd = std(perSlow, 0, 2);
fill(axE, [P.slowCenters(:); flipud(P.slowCenters(:))], ...
          [mu-sd; flipud(mu+sd)], [0.09 0.33 0.61], ...
          'FaceAlpha', 0.15, 'EdgeColor', 'none');
hold(axE, 'on');
plot(axE, P.slowCenters, mu, '-o', 'LineWidth', 1.2, ...
     'Color', [0.09 0.33 0.61], 'MarkerSize', 3.5, 'MarkerFaceColor', [0.09 0.33 0.61]);
xlabel(axE, 'phase freq (Hz)');  ylabel(axE, 'MI, mean over fast bands');
title(axE, 'E   MI across the slow bands  (\pm1 SD over epochs)', 'FontWeight', 'normal');
grid(axE, 'on');  xlim(axE, [P.slowCenters(1) P.slowCenters(end)]);
axE.YAxis.Exponent = 0;  ytickformat(axE, '%.4f');   % keep the x10^-3 label
                                                    % off the title

% ---- F: theta power vs MI  (Output C, n = 1 channel) -------------------
axF = nexttile(tl, [1 2]);
pw  = Pw(jPeak, :).';
scatter(axF, pw, miPeak, 16, tEp, 'filled', 'MarkerFaceAlpha', 0.75);
cb = colorbar(axF);  cb.Label.String = 'time (s)';
xlabel(axF, sprintf('band power at %.2f Hz  (\\muV^2)', P.slowCenters(jPeak)));
ylabel(axF, 'MI at peak cell');
ttl = sprintf('F   power vs MI at the peak slow band');
if numel(pw) > 2
    r = corr(pw, miPeak, 'rows', 'complete', 'type', 'Spearman');
    ttl = sprintf('%s   -   Spearman r = %.2f', ttl, r);
end
title(axF, ttl, 'FontWeight', 'normal');  grid(axF, 'on');

% ---- G: what MakeEpochs recorded and never used ------------------------
axG = nexttile(tl);
yyaxis(axG, 'left');
plot(axG, tEp, ep.maxAbs, '-', 'LineWidth', 0.9);
ylabel(axG, 'max |LFP| (\muV)');
yyaxis(axG, 'right');
plot(axG, tEp, ep.nSharp, '-', 'LineWidth', 0.9);
ylabel(axG, sprintf('samples > %g SD', P.sharpSD));
xlabel(axG, 'time (s)');
title(axG, 'G   recorded, never used to drop', 'FontWeight', 'normal');
grid(axG, 'on');

% ---- save ---------------------------------------------------------------
outPng = fullfile(outDir, sprintf('%s_qc.png', tag));
exportgraphics(fig, outPng, 'Resolution', 150);
fprintf('ChannelQC: %s\n', outPng);
fprintf('   peak cell: %.2f Hz phase / %.0f Hz amplitude, mean MI = %.5f\n', ...
        P.slowCenters(jPeak), P.fastCenters(iPeak), mMI(jPeak, iPeak));
end
