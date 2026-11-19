function plot_ied_cluster_waveform(sessionName, eventNumber, onSamp, offSamp, ...
    files, nums, ADBitVolts, sfx, global_min_T_us, invertPolarity, ...
    clusterIds, clusterSpikeSec, preWinS, postWinS, colors, outDir)
% plot_ied_cluster_waveform  One IED event: driver-channel voltage waveform
% (top) + colour-coded cluster spike-tick raster (bottom), sharing a time
% axis of [onset - preWinS, offset + postWinS] seconds, zeroed on IED onset.
%
% Only clusters with at least one spike inside that window are drawn (each
% gets a distinct ROYGBIV row/colour, cycling if there are more clusters
% than colours). The driver channel is whichever CSC has the largest peak
% |voltage| during the onset->offset span itself (not the flanking windows).

onS  = (double(onSamp) - 1) / sfx;
offS = (double(offSamp) - 1) / sfx;
onOffDur = offS - onS;

t0S = onS - preWinS;
t1S = offS + postWinS;
t0_us = global_min_T_us + t0S * 1e6;
t1_us = global_min_T_us + t1S * 1e6;
nSampWin = round((t1S - t0S) * sfx) + 1;

%% ---- pick the driver channel from the onset->offset span only ----
onOff_t0_us = global_min_T_us + onS * 1e6;
onOff_t1_us = global_min_T_us + offS * 1e6;
nSampOnOff = max(2, round(onOffDur * sfx) + 1);

nCh = numel(files);
magByCh = zeros(nCh, 1);
for ch = 1:nCh
    fn = fullfile(files(ch).folder, files(ch).name);
    seg = loadWindow(fn, onOff_t0_us, onOff_t1_us, sfx, ADBitVolts, invertPolarity, nSampOnOff);
    magByCh(ch) = max(abs(double(seg)));
end
[~, driverIdx] = max(magByCh);
driverFile = fullfile(files(driverIdx).folder, files(driverIdx).name);
driverNum  = nums(driverIdx);

%% ---- load the full pre/during/post window for the driver channel ----
Y = double(loadWindow(driverFile, t0_us, t1_us, sfx, ADBitVolts, invertPolarity, nSampWin));
tRel = linspace(t0S, t1S, nSampWin) - onS;   % seconds relative to IED onset

%% ---- gather clusters with >=1 spike inside the window ----
activeIds = [];
activeTimes = {};
for c = 1:numel(clusterIds)
    spk = clusterSpikeSec{c};
    inWin = spk(spk >= t0S & spk <= t1S) - onS;
    if ~isempty(inWin)
        activeIds(end+1) = clusterIds(c); %#ok<AGROW>
        activeTimes{end+1} = inWin(:); %#ok<AGROW>
    end
end
nActive = numel(activeIds);

%% ---- figure: waveform (top) + cluster raster (bottom) ----
figH = max(360, 160 + 22 * max(nActive, 1));
fig = figure('Color', 'w', 'Position', [80 80 1100 figH], 'Visible', 'off');
tl = tiledlayout(fig, 2, 1, 'TileSpacing', 'compact', 'Padding', 'compact');

ax1 = nexttile(tl, 1);
hold(ax1, 'on');
xregion(ax1, 0, onOffDur, 'FaceColor', [1 0 0], 'FaceAlpha', 0.08);
plot(ax1, tRel, Y, 'k-', 'LineWidth', 1.0);
xline(ax1, 0, '--k', 'LineWidth', 0.8, 'Alpha', 0.6);
xline(ax1, onOffDur, '--k', 'LineWidth', 0.8, 'Alpha', 0.6);
yl = max(abs(Y)) * 1.1;
if ~isfinite(yl) || yl <= 0, yl = 1; end
ylim(ax1, [-yl yl]);
ylabel(ax1, '\muV');
title(ax1, sprintf('%s   Event %d   (driver CSC%d)', strrep(sessionName, '_', '\_'), eventNumber, driverNum), ...
    'FontWeight', 'bold');
box(ax1, 'on');

ax2 = nexttile(tl, 2);
hold(ax2, 'on');
xregion(ax2, 0, onOffDur, 'FaceColor', [1 0 0], 'FaceAlpha', 0.08);
if nActive > 0
    for k = 1:nActive
        col = colors(mod(k-1, size(colors, 1)) + 1, :);
        plot(ax2, activeTimes{k}, k * ones(size(activeTimes{k})), ...
            'Marker', '|', 'LineStyle', 'none', 'Color', col, 'MarkerSize', 8, 'LineWidth', 1.3);
    end
    ylim(ax2, [0.5, nActive + 0.5]);
    set(ax2, 'YTick', 1:nActive, 'YTickLabel', string(activeIds));
else
    text(ax2, mean([t0S t1S]) - onS, 0.5, 'No active clusters', 'HorizontalAlignment', 'center');
    ylim(ax2, [0 1]);
    set(ax2, 'YTick', []);
end
xline(ax2, 0, '--k', 'LineWidth', 0.8, 'Alpha', 0.6);
xline(ax2, onOffDur, '--k', 'LineWidth', 0.8, 'Alpha', 0.6);
ylabel(ax2, 'Cell cluster');
xlabel(ax2, 'Time relative to IED onset (s)');
box(ax2, 'on');

linkaxes([ax1 ax2], 'x');
xlim(ax1, [t0S - onS, t1S - onS]);

outPng = fullfile(outDir, sprintf('Evt%04d_ClusterWaveform.png', eventNumber));
exportgraphics(fig, outPng, 'Resolution', 200);
close(fig);
end
