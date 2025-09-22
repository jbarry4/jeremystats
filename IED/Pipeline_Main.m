function Pipeline_Main(inputFolder, dataMatPath, varargin)
% Pipeline_Main
% Builds ONE master figure (no separate module figures) + master CSV.

% ---------------- Parse shared options ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s) || isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s) || isstring(s));

p.addParameter('excelPath', "", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));

p.addParameter('halfWidthMs',         10e-3, @(x)isfinite(x)&&x>0);
p.addParameter('metricHalfWidthMs',    5e-3, @(x)isfinite(x)&&x>0);
p.addParameter('anchorHalfWidthMs',    5e-3, @(x)isfinite(x)&&x>0);

p.addParameter('yLimMicroV', [], @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('yRobustPct', 99.5, @(x) isfinite(x) && x>0 && x<100);
p.addParameter('yPadFrac',   0.12, @(x) isfinite(x) && x>=0 && x<=0.5);

p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('saveDir', "", @(s)ischar(s)||isstring(s));
p.addParameter('tag', 'ALL', @(s)ischar(s)||isstring(s));

% NEW: whether to include faint overlays in master (heavier memory)
p.addParameter('masterIncludeOverlays', false, @(x)islogical(x)||ismember(x,[0 1]));

p.parse(inputFolder, dataMatPath, varargin{:});
args = p.Results;

% ---------------- Output root ----------------
if args.saveDir == ""
    outRoot = fullfile(string(args.inputFolder), "Pipeline Output");
else
    outRoot = string(args.saveDir);
end
if ~exist(outRoot, 'dir'), mkdir(outRoot); end
fprintf('Pipeline_Main: output root = %s\n', outRoot);

% ================= 1) EventStacks_ampWidth_Avg (data-only) ================
evstacksOut = EventStacks_ampWidth_Avg_Pipeline( ...
    string(args.inputFolder), string(args.dataMatPath), ...
    'excelPath',        string(args.excelPath), ...
    'channelIndices',   args.channelIndices, ...
    'scaleToMicroV',    args.scaleToMicroV, ...
    'halfWidthMs',      args.halfWidthMs, ...
    'metricHalfWidthMs',args.metricHalfWidthMs, ...
    'anchorHalfWidthMs',args.anchorHalfWidthMs, ...
    'yLimMicroV',       args.yLimMicroV, ...
    'yRobustPct',       args.yRobustPct, ...
    'yPadFrac',         args.yPadFrac, ...
    'maxEventsPerGroup',args.maxEventsPerGroup, ...
    'saveDir',          outRoot, ...             % still where we save master outputs
    'tag',              string(args.tag), ...
    'makeIndividualPNGs', false, ...             % << don’t make separate figures
    'returnTraces',       args.masterIncludeOverlays ... % include heavy overlays?
);

% ================= Build the master figure =================
masterFig = figure('Color','w','Position',[60 60 1600 1000],'Visible','off');
tl = tiledlayout(masterFig, 2, 3, 'Padding','compact','TileSpacing','compact');
title(tl, 'Master Plot — Pipeline', 'FontSize', 14, 'FontWeight','bold');

% Row 1, Col 1-2: EventStacks SOLID / SPUTTER
% Global y-limit across both groups:
yL = [-evstacksOut.yMaxGlobal, +evstacksOut.yMaxGlobal];

% Left tile: SOLID
ax = nexttile(tl, 1); 
renderEventStacksPanel(ax, evstacksOut, 'SOLID', yL);

% Middle tile: SPUTTER
ax = nexttile(tl, 2);
renderEventStacksPanel(ax, evstacksOut, 'SPUTTER', yL);

% Right tile placeholder: Voltage Raster Avg (to be wired)
ax = nexttile(tl, 3);
text(ax, 0.5, 0.5, 'VoltageRaster_EventsAvg (placeholder)', 'HorizontalAlignment','center');
axis(ax,'off');

% Row 2 placeholders: CSD plots
ax = nexttile(tl, 4); text(ax, 0.5, 0.5, 'CSDRaster_Avg (placeholder)', 'HorizontalAlignment','center'); axis(ax,'off');
ax = nexttile(tl, 5); text(ax, 0.5, 0.5, 'CSD_CenterSlices_Waveform (placeholder)', 'HorizontalAlignment','center'); axis(ax,'off');
ax = nexttile(tl, 6); text(ax, 0.5, 0.5, 'CSD_TimeAvg_Waveform (placeholder)', 'HorizontalAlignment','center'); axis(ax,'off');

% Save master plot
masterPng = fullfile(outRoot, 'Pipeline_MasterPlot.png');
exportgraphics(masterFig, masterPng, 'Resolution', 220);
close(masterFig);
fprintf('Saved Master Plot: %s\n', masterPng);

% ================= Master CSV =================
allStats = table;

% Fold in EventStacks stats (per group)
if ~isempty(evstacksOut) && isfield(evstacksOut,'groups')
    for g = 1:numel(evstacksOut.groups)
        G = evstacksOut.groups(g);
        row = table;
        row.Module     = "EventStacks_ampWidth_Avg";
        row.Group      = string(G.tag);
        row.Nevents    = double(G.nEventsUsed);
        row.yLimUsed   = double(evstacksOut.yMaxGlobal);
        row.AmpMean_uV = double(mean(G.ampMean, 'omitnan'));
        row.AmpSD_uV   = double(mean(G.ampSD,  'omitnan'));
        row.HWMean_ms  = double(mean(G.hwMean, 'omitnan'));
        row.HWSD_ms    = double(mean(G.hwSD,  'omitnan'));
        allStats = [allStats; row]; %#ok<AGROW>
    end
end

csvPath = fullfile(outRoot, "Pipeline_Master_Stats.csv");
writetable(allStats, csvPath);
fprintf('Saved master CSV: %s\n', csvPath);

% ===================== local rendering helper =====================
function renderEventStacksPanel(ax, evOut, tag, yL)
    hold(ax,'on'); box(ax,'on'); grid(ax,'on');
    % Find group
    idx = find(strcmp({evOut.groups.tag}, tag), 1);
    if isempty(idx)
        text(ax, 0.5, 0.5, sprintf('%s (no data)', tag), 'HorizontalAlignment','center');
        axis(ax,'off'); return;
    end
    G = evOut.groups(idx);
    MU = G.MU; SE = G.SE;
    t  = evOut.tRelMs(:).';
    nCh = size(MU,1);

    % Compact stack: draw mean±SEM per channel as thin bands
    yOffset = 0; dy = 1.0; % one unit per channel “row”
    for k = 1:nCh
        mu = MU(k,:); se = SE(k,:);
        yu = mu + se; yl = mu - se;
        xpatch = [t, fliplr(t)];
        ypatch = [yl, fliplr(yu)]/max(abs(yL)) * 0.8 + (yOffset + (nCh-k)); % normalize for compactness
        patch('XData', xpatch, 'YData', ypatch, 'FaceColor',[0.6 0.7 0.95], 'EdgeColor','none','FaceAlpha',0.35, 'Parent', ax);
        plot(ax, t, (mu/max(abs(yL))*0.8) + (yOffset + (nCh-k)), 'k-', 'LineWidth', 0.8);
    end
    % y “channel ticks”
    yticks(ax, (0:nCh-1));
    yticklabels(ax, arrayfun(@(c) sprintf('row %d', evOut.channelList(c)), nCh:-1:1, 'UniformOutput', false));
    set(ax, 'YDir', 'normal', 'FontSize', 8);
    xlabel(ax, 'Time (ms)');
    ylabel(ax, sprintf('%s — Channels (top=1)', tag));
    title(ax, sprintf('EventStacks %s (mean±SEM) | yLim=±%.1f µV', tag, max(abs(yL))), 'FontSize', 10, 'FontWeight','bold');
end

end
