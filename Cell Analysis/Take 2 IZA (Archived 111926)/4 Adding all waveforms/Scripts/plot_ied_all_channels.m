function plot_ied_all_channels(sessionName, eventNumber, onSamp, offSamp, ...
    files, nums, ADBitVolts, sfx, global_min_T_us, invertPolarity, ...
    clusterIds, clusterSpikeSec, preWinS, postWinS, colors, outDir)
% plot_ied_all_channels  One IED event, ALL recorded CSC channels:
%   top    - stacked raw voltage montage (uV) for every channel (1..64),
%            spanning 1 s before onset -> the IED itself -> 1 s after
%            offset, with the driver channel (largest |deflection| during
%            the IED itself) highlighted in red.
%   bottom - colour-coded tick raster of every cell cluster that fired at
%            least once inside that same window (same convention as the
%            original "2 Cluster Waveform Visualization" plot -- clusters
%            are not tied to a specific CSC channel, so only active
%            clusters get a row, one row per cluster).

onS  = (double(onSamp) - 1) / sfx;
offS = (double(offSamp) - 1) / sfx;
onOffDur = offS - onS;

t0S = onS - preWinS;
t1S = offS + postWinS;
t0_us = global_min_T_us + t0S * 1e6;
t1_us = global_min_T_us + t1S * 1e6;
nSampWin = round((t1S - t0S) * sfx) + 1;

nCh = numel(files);

%% ---- load the pre/during/post window for every channel ----
Y = zeros(nCh, nSampWin);
for ch = 1:nCh
    fn = fullfile(files(ch).folder, files(ch).name);
    Y(ch, :) = double(loadWindow(fn, t0_us, t1_us, sfx, ADBitVolts, invertPolarity, nSampWin));
end
tRel = linspace(t0S, t1S, nSampWin) - onS;   % seconds relative to IED onset

%% ---- driver channel = largest |deflection| during onset->offset only ----
onOffMask = tRel >= 0 & tRel <= onOffDur;
if ~any(onOffMask)
    [~, idxNearest] = min(abs(tRel));
    onOffMask = false(size(tRel)); onOffMask(idxNearest) = true;
end
magByCh = max(abs(Y(:, onOffMask)), [], 2);
[~, driverIdx] = max(magByCh);
driverNum = nums(driverIdx);

%% ---- clusters with >=1 spike inside the window ----
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

%% ---- figure layout (manually positioned axes so row-pixel-height stays
%       constant regardless of how many channels there are) ----
rowH = 14;                          % px per channel row
waveH   = max(220, nCh * rowH);
rasterH = max(160, 22 * max(nActive, 1));
marginBottom = 60; marginGap = 45; marginTop = 55;

figW = 1500;
figH = marginBottom + rasterH + marginGap + waveH + marginTop;
fig = figure('Color', 'w', 'Position', [40 30 figW figH], 'Visible', 'off');

axLeft = 0.08; axWidth = 0.90;
ax2Bottom = marginBottom / figH;
ax2Height = rasterH / figH;
ax1Bottom = (marginBottom + rasterH + marginGap) / figH;
ax1Height = waveH / figH;

%% ---- top panel: all-channel voltage montage ----
ax1 = axes('Parent', fig, 'Units', 'normalized', ...
    'Position', [axLeft, ax1Bottom, axWidth, ax1Height]);
hold(ax1, 'on');

ampScale = median(max(abs(Y), [], 2), 'omitnan');
if ~isfinite(ampScale) || ampScale <= 0, ampScale = 50; end
spacing = ampScale * 2.4;
if ~isfinite(spacing) || spacing <= 0, spacing = 100; end

baseline = (nCh - (1:nCh)) * spacing;   % channel 1 at top, channel nCh at bottom

xlim(ax1, [t0S - onS, t1S - onS]);
xr = xlim(ax1);
patch(ax1, [xr(1) xr(2) xr(2) xr(1)], ...
    [baseline(driverIdx)-spacing/2, baseline(driverIdx)-spacing/2, ...
     baseline(driverIdx)+spacing/2, baseline(driverIdx)+spacing/2], ...
    [1 0.85 0.85], 'EdgeColor', 'none', 'FaceAlpha', 0.6);
xregion(ax1, 0, onOffDur, 'FaceColor', [1 0 0], 'FaceAlpha', 0.08);

for ch = 1:nCh
    if ch == driverIdx, continue; end
    plot(ax1, tRel, Y(ch, :) + baseline(ch), 'Color', [0.25 0.25 0.25], 'LineWidth', 0.5);
end
plot(ax1, tRel, Y(driverIdx, :) + baseline(driverIdx), 'Color', [0.85 0 0], 'LineWidth', 1.2);

xline(ax1, 0, '--k', 'LineWidth', 0.8, 'Alpha', 0.6);
xline(ax1, onOffDur, '--k', 'LineWidth', 0.8, 'Alpha', 0.6);

tickLabels1 = strings(nCh, 1);
for ch = 1:nCh
    if ch == driverIdx
        tickLabels1(ch) = sprintf('\\color{red}%d', nums(ch));
    else
        tickLabels1(ch) = sprintf('%d', nums(ch));
    end
end
set(ax1, 'YTick', fliplr(baseline), 'YTickLabel', flipud(tickLabels1), ...
    'TickLabelInterpreter', 'tex', 'FontSize', 6);
ylim(ax1, [-spacing*0.75, (nCh-1)*spacing + spacing*0.75]);
ylabel(ax1, 'CSC channel');
title(ax1, sprintf('%s   Event %d   All %d channels (driver CSC%d highlighted)', ...
    strrep(sessionName, '_', '\_'), eventNumber, nCh, driverNum), 'FontWeight', 'bold');
box(ax1, 'on');

%% ---- bottom panel: active-cluster raster (flat list, like the original) ----
ax2 = axes('Parent', fig, 'Units', 'normalized', ...
    'Position', [axLeft, ax2Bottom, axWidth, ax2Height]);
hold(ax2, 'on');

xlim(ax2, [t0S - onS, t1S - onS]);
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
    text(ax2, 0, 0.5, 'No active clusters', 'HorizontalAlignment', 'center');
    ylim(ax2, [0 1]);
    set(ax2, 'YTick', []);
end
xline(ax2, 0, '--k', 'LineWidth', 0.8, 'Alpha', 0.6);
xline(ax2, onOffDur, '--k', 'LineWidth', 0.8, 'Alpha', 0.6);
ylabel(ax2, 'Cell cluster');
xlabel(ax2, 'Time relative to IED onset (s)');
box(ax2, 'on');

linkaxes([ax1 ax2], 'x');

outPng = fullfile(outDir, sprintf('Evt%04d_AllChannels.png', eventNumber));
exportgraphics(fig, outPng, 'Resolution', 200);
close(fig);
end
