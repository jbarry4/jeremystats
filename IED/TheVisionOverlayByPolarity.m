function TheVisionOverlayByPolarity(dataMatPath, spikesMatPath, varargin)
% ---------- Parse ----------
p = inputParser;
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addRequired('spikesMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('halfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);
p.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);
p.addParameter('saveDir','', @(s)ischar(s)||isstring(s));
p.addParameter('minCh', 5, @(x)isfinite(x)&&x>=0);
p.addParameter('maxCh', 8, @(x)isfinite(x)&&x>=0);
p.addParameter('channelStride', 1, @(x)isfinite(x)&&x>=1&&mod(x,1)==0);
p.addParameter('channelOffset', 0, @(x)isfinite(x)&&x>=0&&mod(x,1)==0);
p.parse(dataMatPath, spikesMatPath, varargin{:});

halfWidthMs    = p.Results.halfWidthMs;
scaleToMicroV  = p.Results.scaleToMicroV;
saveDir        = string(p.Results.saveDir);
minCh          = p.Results.minCh;
maxCh          = p.Results.maxCh;
channelStride  = p.Results.channelStride;
channelOffset  = p.Results.channelOffset;

% ---------- Load ----------
if ~isfile(dataMatPath), error('Data MAT not found: %s', dataMatPath); end
if ~isfile(spikesMatPath), error('Spikes MAT not found: %s', spikesMatPath); end

mf = matfile(dataMatPath);
try, sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRows = size(mf,'d',1);
nSamp = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end %#ok<NASGU>

S = load(spikesMatPath,'ets','ech');
if ~isfield(S,'ets'), error('Spikes MAT must contain ets [N x 2].'); end
ets = S.ets;
Nevents = size(ets,1);

if isfield(S,'ech')
    ech = S.ech;
    if size(ech,2) ~= nRows
        if size(ech,2) < nRows, ech(:,end+1:nRows) = false; else, ech = ech(:,1:nRows); end
    end
else
    ech = true(Nevents, nRows);
end

% ---------- Select events ----------
chCounts = sum(ech,2);
sel = (chCounts >= minCh) & (chCounts <= maxCh);
evtIdx = find(sel);
if isempty(evtIdx)
    fprintf('No events with %d–%d channels.\n', minCh, maxCh);
    return;
end

% ---------- Setup ----------
HW = max(1, round(halfWidthMs * sfx));
tRelSamples = -HW:HW; %#ok<NASGU>
tRelMs = (tRelSamples / sfx) * 1e3;

if saveDir==""
    [outDir,~,~] = fileparts(dataMatPath);
else
    outDir = char(saveDir);
end
if ~exist(outDir,'dir'), mkdir(outDir); end

fprintf('Polarity overlays: %d qualifying event(s) (%d–%d ch). Window ±%d samples (%.2f ms). Stride=%d, Offset=%d. Scale=%g µV.\n', ...
    numel(evtIdx), minCh, maxCh, HW, 1e3*HW/sfx, channelStride, channelOffset, scaleToMicroV);

% ---------- Row selection (stride/offset) ----------
offset = mod(channelOffset, channelStride);
rowKeepMask = arrayfun(@(r) mod(r-1, channelStride) == offset, 1:nRows);
rowsToPlot  = find(rowKeepMask);
nPlot       = numel(rowsToPlot);

% Predefine inactive colors
colInactiveBelow = [0.55 0.75 0.95];  % light blue
colInactiveBetween = [0.70 0.70 0.70];% gray
colInactiveAbove = [0.95 0.60 0.60];  % light red
colActive = [0 0 0];

for ii = 1:numel(evtIdx)
    e = evtIdx(ii);
    maskActive = ech(e,:);                 % logical 1 x nRows
    s0_ev = max(1, ets(e,1));
    s1_ev = min(nSamp, ets(e,2));

    % Global anchor from ACTIVE channels
    activeRows = find(maskActive);
    if isempty(activeRows)
        fprintf('Evt %d: no active rows; skipping.\n', e);
        continue;
    end
    peakIdx = nan(numel(activeRows),1);
    for k = 1:numel(activeRows)
        ch = activeRows(k);
        yseg = double(mf.d(ch, s0_ev:s1_ev));
        if any(~isfinite(yseg)), continue; end
        [~,kpk] = max(abs(yseg));
        peakIdx(k) = s0_ev + kpk - 1;
    end
    peakIdx = peakIdx(isfinite(peakIdx));
    if isempty(peakIdx)
        fprintf('Evt %d: could not compute active peaks; skipping.\n', e);
        continue;
    end
    anchor = round(median(peakIdx));
    s0 = anchor - HW; s1 = anchor + HW;
    if s0 < 1 || s1 > nSamp
        fprintf('Evt %d: window out of bounds @ anchor %d; skipping.\n', e, anchor);
        continue;
    end

    % Extract windows for selected rows; classify polarity by sign of abs-peak
    Y = nan(nPlot, 2*HW+1);
    pkSign = nan(nPlot,1);  % +1/-1
    for k = 1:nPlot
        ch = rowsToPlot(k);
        y = double(mf.d(ch, s0:s1)) * scaleToMicroV; % µV
        if any(~isfinite(y)), continue; end
        Y(k,:) = y;
        [~,kpk] = max(abs(y));
        sgn = sign(y(kpk)); if sgn==0, sgn=1; end
        pkSign(k) = sgn;
    end
    if all(~isfinite(Y(:)))
        fprintf('Evt %d: no valid windows; skipping.\n', e);
        continue;
    end

    posIdx = find(pkSign > 0);
    negIdx = find(pkSign < 0);

    % Active range (by row index) for color-coding inactive traces
    actMin = min(activeRows);  % smallest active channel index
    actMax = max(activeRows);  % largest  active channel index

    % Shared y-limits
    maxAbs = max(abs(Y(:)), [], 'omitnan'); if ~isfinite(maxAbs) || maxAbs<=0, maxAbs = 1; end
    span = 1.05 * maxAbs; yL = [-span, span];

    % Figure with two stacked panels
    f = figure('Color','w','Position',[80 80 1050 900],'Visible','off');
    tl = tiledlayout(f, 2, 1, 'Padding','compact', 'TileSpacing','compact');

    % Top: positive peaks
    ax1 = nexttile(tl,1); hold(ax1,'on'); box(ax1,'on'); grid(ax1,'on');
    plotGroupPolarity(ax1, tRelMs, Y, rowsToPlot, maskActive, posIdx, yL, ...
        actMin, actMax, colActive, colInactiveBelow, colInactiveBetween, colInactiveAbove);
    title(ax1, sprintf('Event %03d — Positive-peak channels: %d  |  Anchor @ %d  |  Win \\pm%.1f ms', ...
        e, numel(posIdx), anchor, 1e3*HW/sfx), 'FontWeight','bold');
    ylabel(ax1,'\muV');

    % Bottom: negative peaks
    ax2 = nexttile(tl,2); hold(ax2,'on'); box(ax2,'on'); grid(ax2,'on');
    plotGroupPolarity(ax2, tRelMs, Y, rowsToPlot, maskActive, negIdx, yL, ...
        actMin, actMax, colActive, colInactiveBelow, colInactiveBetween, colInactiveAbove);
    title(ax2, sprintf('Event %03d — Negative-peak channels: %d', e, numel(negIdx)), 'FontWeight','bold');
    ylabel(ax2,'\muV'); xlabel(ax2,'ms');

    % Tiny note
    text(ax1, 0.01, 0.98, sprintf('\\fontsize{8}Active=bold black   Inactive: below=light blue, between=gray, above=light red   yLim=\\pm%.1f   Plotted rows=%d (stride=%d, offset=%d)', ...
         span, nPlot, channelStride, offset), ...
         'Units','normalized','VerticalAlignment','top','BackgroundColor','w','Margin',3, ...
         'EdgeColor',[0.85 0.85 0.85],'Interpreter','tex');

    % Save
    msWin = round(1e3*HW/sfx);
    outPng = fullfile(outDir, sprintf('OverlayPolarityColor_Evt%03d_%drows_stride%d_off%d_HW%ds_%dms_uV.png', ...
                                      e, nPlot, channelStride, offset, HW, msWin));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved polarity+range-colored overlay: %s (pos=%d, neg=%d)\n', outPng, numel(posIdx), numel(negIdx));
end

fprintf('Done. Output dir: %s\n', outDir);
end

% ======== Helpers ========

function plotGroupPolarity(ax, tMs, Y, rowsToPlot, maskActive, keepIdx, yL, ...
                           actMin, actMax, colActive, colBelow, colBetween, colAbove)
    xline(ax,0,'--k','LineWidth',0.9); yline(ax,0,':','Color',[0.7 0.7 0.7]);
    ylim(ax, yL);
    if isempty(keepIdx), return; end
    for ii = 1:numel(keepIdx)
        k  = keepIdx(ii);
        ch = rowsToPlot(k);
        y  = Y(k,:);
        if all(~isfinite(y)), continue; end

        if maskActive(ch)
            lw = 1.6; col = colActive;      % active: bold black
        else
            % Inactive color by channel index relative to active range:
            if ch < actMin
                col = colBelow;              % below smallest active -> light blue
            elseif ch > actMax
                col = colAbove;              % above largest active -> light red
            else
                col = colBetween;            % between -> gray
            end
            lw = 0.9;
        end

        plot(ax, tMs, y, 'LineWidth', lw, 'Color', col);
    end
end