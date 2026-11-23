function plot_session_superimposed(sessionName, T, files, nums, ADBitVolts, ...
    sfx, global_min_T_us, invertPolarity, clusterIds, clusterSpikeSec, ...
    preWinS, postWinS, colors, outDir)
% plot_session_superimposed  One session, ALL IED events superimposed on
% the same axes (aligned to each event's own onset) -- the session-level
% companion to "4 Adding all waveforms", laid out the same way (waveform
% montage on top, cluster raster on the bottom of the SAME figure):
%   top    - stacked raw voltage montage (uV) for every CSC channel.
%            Every event's trace for a channel is drawn faint gray,
%            except when that channel was the driver (largest
%            |deflection| during onset->offset) for that specific event,
%            in which case it's drawn faint red -- same red-for-driver
%            convention as the per-event plots. The across-event average
%            trace for each channel is drawn on top in solid bold black.
%   bottom - tick raster of every cell cluster that fired at least once
%            inside any event's window. Every event's spike ticks
%            (relative to that event's own onset) are superimposed on the
%            same row as very faint marks; ticks that land at similar
%            latencies across events overlap and accumulate into a
%            bolder mark, while one-off spikes stay faint.

nCh = numel(files);
nEv = height(T);

%% ---- pass 1: load every event's channel window + find its driver ----
tRelAll   = cell(nEv, 1);
Yall      = cell(nEv, 1);
driverIdx = zeros(nEv, 1);
onOffDurAll = zeros(nEv, 1);
maxPostRel  = -Inf;
chMax = zeros(nCh, 1);

for j = 1:nEv
    onSamp  = T.onsamp(j);
    offSamp = T.offsamp(j);
    onS  = (double(onSamp) - 1) / sfx;
    offS = (double(offSamp) - 1) / sfx;
    onOffDur = offS - onS;

    t0S = onS - preWinS;
    t1S = offS + postWinS;
    t0_us = global_min_T_us + t0S * 1e6;
    t1_us = global_min_T_us + t1S * 1e6;
    nSampWin = round((t1S - t0S) * sfx) + 1;

    Y = zeros(nCh, nSampWin);
    for ch = 1:nCh
        fn = fullfile(files(ch).folder, files(ch).name);
        Y(ch, :) = double(loadWindow(fn, t0_us, t1_us, sfx, ADBitVolts, invertPolarity, nSampWin));
    end
    tRel = linspace(t0S, t1S, nSampWin) - onS;

    onOffMask = tRel >= 0 & tRel <= onOffDur;
    if ~any(onOffMask)
        [~, idxNearest] = min(abs(tRel));
        onOffMask = false(size(tRel)); onOffMask(idxNearest) = true;
    end
    magByCh = max(abs(Y(:, onOffMask)), [], 2);
    [~, dIdx] = max(magByCh);

    tRelAll{j} = tRel;
    Yall{j} = Y;
    driverIdx(j) = dIdx;
    onOffDurAll(j) = onOffDur;
    chMax = max(chMax, max(abs(Y), [], 2));

    postRel = t1S - onS;
    if postRel > maxPostRel, maxPostRel = postRel; end
end

%% ---- common onset-aligned grid + nan-safe per-channel average ----
dt = 1 / sfx;
trelCommon = (-preWinS):dt:maxPostRel;
nGrid = numel(trelCommon);

sumY = zeros(nCh, nGrid);
cntY = zeros(nCh, nGrid);
for j = 1:nEv
    yiT = interp1(tRelAll{j}(:), Yall{j}.', trelCommon(:), 'linear', NaN).'; % nCh x nGrid
    m = ~isnan(yiT);
    sumY(m) = sumY(m) + yiT(m);
    cntY(m) = cntY(m) + 1;
end
avgY = nan(nCh, nGrid);
have = cntY > 0;
avgY(have) = sumY(have) ./ cntY(have);

%% ---- decimate for PLOTTING only (averaging above stays full-resolution) ----
% With many events and 64 channels, plotting every raw 30 kHz sample of
% every event on every channel row can reach >1e8 line vertices with
% alpha blending, which overwhelms the renderer in headless batch mode
% and silently produces a solid black frame instead of an error. A 1500px
% wide figure cannot show more detail than a few thousand points per
% trace anyway, so each trace is stride-decimated to a fixed point
% budget before plotting.
targetPtsPerTrace = 4000;
tRelDecAll = cell(nEv, 1);
YDecAll = cell(nEv, 1);
for j = 1:nEv
    n = numel(tRelAll{j});
    stride = max(1, floor(n / targetPtsPerTrace));
    idxDec = 1:stride:n;
    tRelDecAll{j} = tRelAll{j}(idxDec);
    YDecAll{j} = Yall{j}(:, idxDec);
end
gridStride = max(1, floor(nGrid / targetPtsPerTrace));
idxGridDec = 1:gridStride:nGrid;
trelCommonDec = trelCommon(idxGridDec);
avgYDec = avgY(:, idxGridDec);

%% ---- cluster spikes: pool every event's ticks (relative to its onset) ----
nClusters = numel(clusterIds);
timesByCluster = cell(nClusters, 1);
activeMask = false(nClusters, 1);
for j = 1:nEv
    onS  = (double(T.onsamp(j)) - 1) / sfx;
    offS = (double(T.offsamp(j)) - 1) / sfx;
    t0S = onS - preWinS;
    t1S = offS + postWinS;
    for c = 1:nClusters
        spk = clusterSpikeSec{c};
        inWin = spk(spk >= t0S & spk <= t1S) - onS;
        if ~isempty(inWin)
            timesByCluster{c} = [timesByCluster{c}; inWin(:)];
            activeMask(c) = true;
        end
    end
end
activeIdx = find(activeMask);
activeIds = clusterIds(activeIdx);
nActive = numel(activeIdx);

%% ---- figure layout (same convention as "4 Adding all waveforms") ----
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

xr = [-preWinS, maxPostRel];

%% ---- top panel: superimposed all-channel voltage montage ----
ax1 = axes('Parent', fig, 'Units', 'normalized', ...
    'Position', [axLeft, ax1Bottom, axWidth, ax1Height]);
hold(ax1, 'on');

ampScale = median(chMax(chMax > 0), 'omitnan');
if ~isfinite(ampScale) || ampScale <= 0, ampScale = 50; end
spacing = ampScale * 2.4;
if ~isfinite(spacing) || spacing <= 0, spacing = 100; end
baseline = (nCh - (1:nCh)) * spacing;   % channel 1 at top, channel nCh at bottom

xlim(ax1, xr);
xregion(ax1, 0, median(onOffDurAll), 'FaceColor', [1 0 0], 'FaceAlpha', 0.06);

for ch = 1:nCh
    nonDriverT = []; nonDriverY = [];
    driverT = []; driverY = [];
    for j = 1:nEv
        seg = YDecAll{j}(ch, :) + baseline(ch);
        if driverIdx(j) == ch
            driverT = [driverT, tRelDecAll{j}, NaN]; %#ok<AGROW>
            driverY = [driverY, seg, NaN]; %#ok<AGROW>
        else
            nonDriverT = [nonDriverT, tRelDecAll{j}, NaN]; %#ok<AGROW>
            nonDriverY = [nonDriverY, seg, NaN]; %#ok<AGROW>
        end
    end
    if ~isempty(nonDriverT)
        plot(ax1, nonDriverT, nonDriverY, 'Color', [0.35 0.35 0.35 0.22], 'LineWidth', 0.5);
    end
    if ~isempty(driverT)
        plot(ax1, driverT, driverY, 'Color', [0.85 0 0 0.45], 'LineWidth', 0.8);
    end
    plot(ax1, trelCommonDec, avgYDec(ch, :) + baseline(ch), 'Color', [0 0 0], 'LineWidth', 1.8);
end

xline(ax1, 0, '--k', 'LineWidth', 0.8, 'Alpha', 0.6);

set(ax1, 'YTick', fliplr(baseline), 'YTickLabel', string(flipud(nums(:))), 'FontSize', 6);
ylim(ax1, [-spacing*0.75, (nCh-1)*spacing + spacing*0.75]);
ylabel(ax1, 'CSC channel');
title(ax1, sprintf('%s   Superimposed waveforms, %d IED events (per-event driver channel in red, channel average in bold black)', ...
    strrep(sessionName, '_', '\_'), nEv), 'FontWeight', 'bold');
box(ax1, 'on');

hNonProxy = plot(ax1, NaN, NaN, 'Color', [0.35 0.35 0.35], 'LineWidth', 1.2);
hDrvProxy = plot(ax1, NaN, NaN, 'Color', [0.85 0 0], 'LineWidth', 1.5);
hAvgProxy = plot(ax1, NaN, NaN, 'Color', [0 0 0], 'LineWidth', 2.2);
legend(ax1, [hNonProxy hDrvProxy hAvgProxy], ...
    {'Individual event (non-driver ch)', 'Individual event (driver ch that event)', 'Channel average'}, ...
    'Location', 'northwest', 'FontSize', 7, 'Box', 'on');

%% ---- bottom panel: superimposed active-cluster raster ----
ax2 = axes('Parent', fig, 'Units', 'normalized', ...
    'Position', [axLeft, ax2Bottom, axWidth, ax2Height]);
hold(ax2, 'on');

xlim(ax2, xr);
xregion(ax2, 0, median(onOffDurAll), 'FaceColor', [1 0 0], 'FaceAlpha', 0.06);
if nActive > 0
    for k = 1:nActive
        c = activeIdx(k);
        col = colors(mod(k-1, size(colors, 1)) + 1, :);
        times = timesByCluster{c};
        h = scatter(ax2, times, k * ones(size(times)), 60, col, '|', 'LineWidth', 1.6);
        h.MarkerEdgeAlpha = 0.12;
    end
    ylim(ax2, [0.5, nActive + 0.5]);
    set(ax2, 'YTick', 1:nActive, 'YTickLabel', string(activeIds));
else
    text(ax2, mean(xr), 0.5, 'No active clusters', 'HorizontalAlignment', 'center');
    ylim(ax2, [0 1]);
    set(ax2, 'YTick', []);
end
xline(ax2, 0, '--k', 'LineWidth', 0.8, 'Alpha', 0.6);
ylabel(ax2, 'Cell cluster');
xlabel(ax2, 'Time relative to IED onset (s)');
box(ax2, 'on');

linkaxes([ax1 ax2], 'x');

outPng = fullfile(outDir, sprintf('%s_Superimposed.png', sessionName));
exportgraphics(fig, outPng, 'Resolution', 200);
close(fig);
end
