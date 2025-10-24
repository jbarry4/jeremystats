function res = VACC_EventStacks_ampWidth_Avg_old(dataDir, V, varargin)
% VACC_EventStacks_ampWidth_Avg
% Build SOLID/SPUTTER average stacks (mean ± SEM) around each event window
% defined by ets.mat. This VACC version:
%   - Uses converted data V (already in microvolts, µV).
%   - NO Excel dependency; event windows come from ets(e,:) in samples.
%   - Anchors on the POSITIVE peak of the MEAN across rows [end-7 ... end-2]
%     (e.g., for 32 rows -> rows 26..30).
%   - Fixes plot y-limits to ±3000 µV for consistent scale.
%
% INPUTS
%   dataDir : folder that contains:
%                - VACC_TheVision_out/{Solid,Sputter}
%                - ets.mat  (N x 2 samples: [start end])
%              (ech.mat optional; not required)
%   V       : struct with fields:
%                V.D   [nRows x nSamp]  (µV, single)   -> data matrix
%                V.fs  (Hz)                               -> sampling rate
%                V.nums (optional) row->CSC label mapping (1xN)
%
% OPTIONAL NAME-VALUE ARGS (kept simple):
%   'channelIndices'   : subset of rows to process (default = all rows)
%   'halfWidthMs'      : ± display/averaging window (sec, default 10e-3)
%   'metricHalfWidthMs': ± metrics window (sec, default 5e-3)
%   'anchorHalfWidthMs': ± search window around event center (sec, default 5e-3)
%   'evtOffset'        : optional integer offset applied to evt index (default 0)
%   'saveDir'          : output dir (default: <dataDir>/EventStacks AmpWidth Output)
%   'tag'              : string to tag figure titles (default "ALL")
%   'yLimMicroV'       : fixed ± y-limit override (default [], we use ±3000)
%   'yRobustPct'       : kept for compatibility (unused here; fixed y-limit)
%   'yPadFrac'         : kept for compatibility (unused here; fixed y-limit)
%
% OUTPUT (for pipeline):
%   res.pngSolid, res.pngSputter, res.statsMatSolid, res.statsMatSputter, res.statsCSV

% ---------------- Args ----------------
p = inputParser;
p.addRequired('dataDir', @(s)ischar(s)||isstring(s));
p.addRequired('V',       @(x)isstruct(x) && isfield(x,'D') && isfield(x,'fs'));

% Selection / alignment / windows
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('halfWidthMs',         50e-3, @(x)isfinite(x)&&x>0); % ±10 ms display/averaging
p.addParameter('metricHalfWidthMs',    5e-3, @(x)isfinite(x)&&x>0); % ±5 ms metrics
p.addParameter('anchorHalfWidthMs',    10e-3, @(x)isfinite(x)&&x>0); % ±5 ms anchor search
p.addParameter('evtOffset', 0, @(x)isscalar(x)&&isfinite(x));       % optional offset (EvtNNN indexing)

% Output + labeling (y-limit is fixed to ±3000 unless user overrides)
p.addParameter('saveDir',"", @(s)ischar(s)||isstring(s));
p.addParameter('tag','ALL', @(s)ischar(s)||isstring(s));
p.addParameter('yLimMicroV', [], @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('yRobustPct', 99.5, @(x) isfinite(x) && x>0 && x<100);  % kept for compatibility
p.addParameter('yPadFrac', 0.12, @(x) isfinite(x) && x>=0 && x<=0.5);  % kept for compatibility
p.parse(dataDir, V, varargin{:});

dataDir        = string(p.Results.dataDir);
D              = V.D;                        % µV (single)
sfx            = V.fs;                       % Hz
kept_channels  = []; if isfield(V,'nums'), kept_channels = V.nums(:)'; end
channelIndices = p.Results.channelIndices;

halfWidthMs    = p.Results.halfWidthMs;
metricHWms     = p.Results.metricHalfWidthMs;
anchorHWms     = p.Results.anchorHalfWidthMs;

evtOffset      = p.Results.evtOffset;

saveDir        = string(p.Results.saveDir);
tagStr         = string(p.Results.tag);
yLimOverride   = p.Results.yLimMicroV;

% ---------------- Layout ----------------
rootVision = fullfile(dataDir, "VACC_TheVision_out");
solidDir   = fullfile(rootVision, "Solid");
sputterDir = fullfile(rootVision, "Garbage");
assert(isfolder(solidDir),   'Missing folder: %s', solidDir);
assert(isfolder(sputterDir), 'Missing folder: %s', sputterDir);

% ---------------- Load ets (event windows) ----------------
S = load(fullfile(dataDir,'ets.mat'),'ets');
assert(isfield(S,'ets') && ~isempty(S.ets), 'ets.mat missing or invalid in %s', dataDir);
ets = double(S.ets);                     % [Nevents x 2] samples: [start end]
NrowsETS = size(ets,1);

% ---------------- Data selection ----------------
[nRowsAll, nSamp] = size(D);
if isempty(channelIndices)
    chList = 1:nRowsAll;                 % default: all rows
else
    chList = channelIndices(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);

% --- Anchor rows: last 8 minus last 2 (generic across row counts)
% For 32 rows -> rows 26..30 (i.e., [end-7 : end-2])
anchorRowsAbs = max(1, nRowsAll-7) : max(1, nRowsAll-2);
fprintf('Anchoring on mean of rows %d..%d (absolute row indices)\n', anchorRowsAbs(1), anchorRowsAbs(end));

% ---------- Output directory ----------
if saveDir == ""
    outDir = fullfile(dataDir, 'EventStacks AmpWidth Output');
else
    outDir = char(saveDir);
end
if ~exist(outDir,'dir'), mkdir(outDir); end

% File paths for PNGs and stats
pngSOL = fullfile(outDir, sprintf('AvgStack_SOLID_anchor-meanRows%dto%d_disp%ds_met%ds.png', ...
    anchorRowsAbs(1), anchorRowsAbs(end), round(halfWidthMs*sfx), round(metricHWms*sfx)));
pngSPU = fullfile(outDir, sprintf('AvgStack_SPUTTER_anchor-meanRows%dto%d_disp%ds_met%ds.png', ...
    anchorRowsAbs(1), anchorRowsAbs(end), round(halfWidthMs*sfx), round(metricHWms*sfx)));
matSOL = fullfile(outDir, 'AvgStack_SOLID_stats.mat');
matSPU = fullfile(outDir, 'AvgStack_SPUTTER_stats.mat');
csvAll = fullfile(outDir, 'EventStacks_perChannel_Stats.csv');

% ---------------- Windows (in samples) ----------------
HWdisp    = max(1, round(halfWidthMs * sfx));      % ± display/averaging
HWmet     = max(1, round(metricHWms  * sfx));      % ± metrics
HWanchor  = max(1, round(anchorHWms  * sfx));      % ± anchor search around event center
tRelSamp  = -HWdisp:HWdisp;
tRelMs    = (tRelSamp / sfx) * 1e3;                % ms for plotting
winN      = numel(tRelSamp);
centerIdx = HWdisp + 1;

fprintf(['VACC_EventStacks_ampWidth_Avg: sfx=%.1f Hz | display ±%.1f ms | ', ...
         'metrics ±%.1f ms | anchorSearch ±%.1f ms | channels=%d\n'], ...
         sfx, 1e3*HWdisp/sfx, 1e3*HWmet/sfx, 1e3*HWanchor/sfx, nCh);

% ---------------- Events to use (from filenames EvtNNN_*.png under Solid/Sputter) ----------------
evtSOL = unique(parseEvtNumsFromPngs(solidDir));
evtSPU = unique(parseEvtNumsFromPngs(sputterDir));
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));

% ---------------- Build group stats (per-channel means/SEMs + metrics) ----------------
[SOL] = avgForGroup(evtSOL, 'SOLID');
[SPU] = avgForGroup(evtSPU, 'SPUTTER');

% ---------------- Fixed y-limit (±3000 µV) across BOTH figures ----------------
yMax = 3000;                            % µV (fixed), unless user provided override
if ~isempty(yLimOverride) && isfinite(yLimOverride) && yLimOverride>0
    yMax = yLimOverride;
end
yL_global = [-yMax, +yMax];
fprintf('Global y-limit (fixed): ±%.1f µV\n', yMax);

% ---------------- Plot & save (2 columns per figure) ----------------
plotStackWithIndicators(SOL, 'SOLID',   yL_global, pngSOL);
plotStackWithIndicators(SPU, 'SPUTTER', yL_global, pngSPU);

% ---------------- Save lightweight stats & CSV ----------------
if ~isempty(SOL), save(matSOL, '-struct', 'SOL'); end
if ~isempty(SPU), save(matSPU, '-struct', 'SPU'); end

try
    Tcsv = makePerChannelTable(SOL, 'SOLID', chList, kept_channels);
    Tcsv = [Tcsv; makePerChannelTable(SPU, 'SPUTTER', chList, kept_channels)];
    writetable(Tcsv, csvAll);
catch ME
    wid = ME.identifier; if isempty(wid), wid = 'VACC:CSVWriteFailed'; end
    warning(wid, 'Failed writing EventStacks per-channel stats CSV to %s: %s', csvAll, ME.message);
end

% ---------------- Return paths for pipeline picker ----------------
res = struct('outputDir', outDir, ...
             'pngSolid', pngSOL, 'pngSputter', pngSPU, ...
             'statsMatSolid', matSOL, 'statsMatSputter', matSPU, ...
             'statsCSV', csvAll);

fprintf('EventStacks outputs:\n  %s\n  %s\n  %s\n', pngSOL, pngSPU, csvAll);

% ======================================================================
%                                HELPERS
% ======================================================================

function evts = parseEvtNumsFromPngs(dirpath)
    % Parse EvtNNN from PNG filenames as integers
    L = dir(fullfile(dirpath, '*.png'));
    evts = [];
    for k = 1:numel(L)
        m = regexp(L(k).name, 'Evt(\d+)', 'tokens', 'once');
        if ~isempty(m)
            ev = str2double(m{1});
            if isfinite(ev), evts(end+1) = ev; end %#ok<AGROW>
        end
    end
    evts = sort(unique(evts));
end

function [G] = avgForGroup(evtList, tag)
    % Aggregate per-channel statistics around a COMMON anchor:
    %   - COMMON anchor: positive peak of the MEAN across the anchor rows
    %     (rows [end-7 .. end-2]) within ±HWanchor of the event midpoint.
    %
    % Outputs in G:
    %   MU, SE    : [nCh x winN] mean & SEM of aligned windows
    %   n         : [nCh x 1]    contributing counts
    %   ampMean/SD: [nCh x 1]    positive-peak amplitude (µV) stats
    %   hwMean/SD : [nCh x 1]    half-width (ms) stats
    %   traces    : cell{nCh}    contributing windows for faint overlays
    %   usedEvents: event IDs that contributed
    %   tRelMs    : time vector in ms (for plotting)

    G = struct('MU',nan(nCh,winN),'SE',nan(nCh,winN),'n',zeros(nCh,1), ...
               'ampMean',nan(nCh,1),'ampSD',nan(nCh,1), ...
               'hwMean',nan(nCh,1),'hwSD',nan(nCh,1), ...
               'usedEvents',[],'tRelMs',tRelMs,'traces',{cell(nCh,1)});

    if isempty(evtList)
        warning('%s: no events.', tag);
        return;
    end

    stacks = cell(nCh,1);   % per-channel windows (each row = one event)
    amps   = cell(nCh,1);   % per-event positive peak amplitudes (µV)
    hws    = cell(nCh,1);   % per-event half-widths (ms)
    for i=1:nCh, stacks{i} = []; amps{i} = []; hws{i} = []; end

    nBad = 0;

    for ii = 1:numel(evtList)
        e = evtList(ii);
        rowETS = e + evtOffset;            % allow optional offset
        if rowETS < 1 || rowETS > NrowsETS
            alt = e;                       % fallback to raw event number
            if alt >= 1 && alt <= NrowsETS, rowETS = alt; else, nBad=nBad+1; continue; end
        end

        % Event window (in samples), clipped to data bounds
        s0_ev = max(1, round(ets(rowETS,1)));
        s1_ev = min(nSamp, round(ets(rowETS,2)));
        if ~isfinite(s0_ev) || ~isfinite(s1_ev) || s1_ev <= s0_ev
            nBad = nBad + 1; continue;
        end

        % Midpoint of the event window (anchor search center)
        ancMid = round((s0_ev + s1_ev)/2);

        % -------- COMMON ANCHOR from MEAN across anchor rows (positive peak) --------
        s0srch = max(1, ancMid - HWanchor);
        s1srch = min(nSamp, ancMid + HWanchor);

        YsegA = double(D(anchorRowsAbs, s0srch:s1srch));   % [nAnchorRows x L] (µV)
        if isempty(YsegA) || all(~isfinite(YsegA(:))), nBad=nBad+1; continue; end

        yseg0 = mean(YsegA, 1, 'omitnan');                % 1 x L (µV)
        if all(~isfinite(yseg0)), nBad=nBad+1; continue; end

        [~, k_rel] = max(yseg0);                          % positive peak index
        if isempty(k_rel) || ~isfinite(k_rel), nBad=nBad+1; continue; end

        commonAnchor = s0srch + k_rel - 1;                % absolute sample index

        % -------- Collect aligned windows + metrics for each selected channel --------
        okAnyCh = false;
        for k = 1:nCh
            ch = chList(k);

            % Window centered at COMMON anchor (display/average)
            s0 = commonAnchor - HWdisp; s1 = commonAnchor + HWdisp;
            if s0 < 1 || s1 > nSamp, continue; end

            y = double(D(ch, s0:s1));                     % µV
            if any(~isfinite(y)), continue; end

            stacks{k}(end+1,:) = y; %#ok<AGROW>
            okAnyCh = true;

            % --- Metrics window (±metric) around COMMON anchor (POSITIVE peak only) ---
            s0m = max(1, commonAnchor - HWmet);
            s1m = min(nSamp, commonAnchor + HWmet);
            ym  = double(D(ch, s0m:s1m));
            if numel(ym) >= 3 && all(isfinite(ym))
                [amp, pkRel] = max(ym);       % positive peak amplitude (µV)
                h = 0.5 * amp;                % half-height

                % Left crossing (linear interpolation)
                kL = pkRel;
                while kL > 1 && ym(kL) >= h, kL = kL - 1; end
                if kL >= 1 && (kL+1) <= numel(ym) && ym(kL) < h && ym(kL+1) >= h
                    left_ip = kL + (h - ym(kL)) / (ym(kL+1) - ym(kL));
                else
                    left_ip = NaN;
                end

                % Right crossing (linear interpolation)
                kR = pkRel; Lm = numel(ym);
                while kR < Lm && ym(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= Lm && ym(kR-1) >= h && ym(kR) < h
                    right_ip = (kR-1) + (h - ym(kR-1)) / (ym(kR) - ym(kR-1));
                else
                    right_ip = NaN;
                end

                % Half-width in ms if both crossings exist
                if isfinite(left_ip) && isfinite(right_ip) && right_ip > left_ip
                    hw_ms = (right_ip - left_ip) / sfx * 1e3;
                else
                    hw_ms = NaN;
                end
                amps{k}(end+1,1) = amp; %#ok<AGROW>
                hws{k}(end+1,1)  = hw_ms; %#ok<AGROW>
            else
                amps{k}(end+1,1) = NaN; %#ok<AGROW>
                hws{k}(end+1,1)  = NaN; %#ok<AGROW>
            end
        end

        if okAnyCh
            G.usedEvents(end+1) = e; %#ok<AGROW>
        end
    end

    if nBad>0, fprintf('%s: skipped %d event(s) (bad/missing/out-of-bounds).\n', tag, nBad); end
    fprintf('%s: used %d/%d events (any channel contributed).\n', tag, numel(G.usedEvents), numel(evtList));

    % -------- Per-channel aggregates (mean, SEM, amp/HW stats) --------
    for k = 1:nCh
        X = stacks{k}; 
        nUsed = size(X,1); 
        G.n(k) = nUsed;

        if nUsed > 0
            G.MU(k,:) = mean(X, 1, 'omitnan');
            G.SE(k,:) = std( X, 0, 1, 'omitnan') ./ max(1,sqrt(nUsed)); % SEM
        end

        a = amps{k}; w = hws{k};
        if ~isempty(a), G.ampMean(k) = mean(a, 'omitnan'); G.ampSD(k) = std(a, 0, 'omitnan'); end
        if ~isempty(w), G.hwMean(k)  = mean(w, 'omitnan'); G.hwSD(k)  = std(w,  0, 'omitnan'); end

        % keep raw contributing traces for faint overlay
        G.traces{k} = X;
    end

    % -------- Save group stats (lightweight .mat) --------
    alignLabel = sprintf('mean(rows %d..%d) positive peak (±%.1f ms)', ...
                         anchorRowsAbs(1), anchorRowsAbs(end), 1e3*HWanchor/sfx);
    statsPath = fullfile(outDir, sprintf('AvgStack_%s_stats.mat', tag));
    chList_local = chList; %#ok<NASGU>
    Gsave = G;
    save(statsPath, 'tRelMs','chList_local','kept_channels','halfWidthMs','metricHWms','sfx', ...
                    'alignLabel','Gsave');
    fprintf('Saved group stats: %s\n', statsPath);

    % Attach path for caller
    G.outStatsPath = statsPath;
end

function plotStackWithIndicators(G, tag, yL, outPng)
    % Plot per-channel mean ± SEM with faint overlays of contributing traces.
    % Two-column grid; fixed global y-limits (passed in yL = [-yMax yMax]).

    if isempty(G) || all(all(isnan(G.MU)))
        warning('%s: no data to plot.', tag); 
        return; 
    end

    % --- Layout: 2 columns, rows as needed
    nCols = 2;
    nRowsGrid = ceil(nCh / nCols);

    perRowPx = 120; basePx = 220; maxPx = 5200;
    figH = min(maxPx, basePx + perRowPx * nRowsGrid);
    f = figure('Color','w','Position',[60 60 1100 figH],'Visible','off');
    tl = tiledlayout(f, nRowsGrid, nCols, 'Padding','compact','TileSpacing','compact');

    % Metric subrange indices within mean vector for indicators
    metStart = max(1, centerIdx - HWmet);
    metEnd   = min(winN, centerIdx + HWmet);
    Lmet     = metEnd - metStart + 1;

    for k = 1:nCh
        mu = G.MU(k,:); se = G.SE(k,:);
        ax = nexttile(tl); hold(ax,'on'); box(ax,'on'); grid(ax,'on');

        % Faint overlays of contributing event traces (if present)
        if isfield(G,'traces') && numel(G.traces) >= k && ~isempty(G.traces{k})
            Yk = G.traces{k};  % [nEventsUsed x winN]
            for r = 1:size(Yk,1)
                y = Yk(r,:);
                if any(isfinite(y))
                    plot(ax, tRelMs, y, 'LineWidth', 0.5, 'Color', [0.65 0.65 0.65]); % faint gray
                end
            end
        end

        % Mean ± SEM patch and mean line
        if any(isfinite(mu))
            yu = mu + se; yl = mu - se;
            xp = [tRelMs, fliplr(tRelMs)];
            yp = [yu,      fliplr(yl)];
            patch('XData',xp,'YData',yp,'FaceColor',[0.3 0.3 0.9],'FaceAlpha',0.25,'EdgeColor','none','HandleVisibility','off');
            plot(ax, tRelMs, mu, 'LineWidth', 1.8);

            % Indicators computed on MEAN waveform within ±metric window (POS PEAK)
            muMet = mu(metStart:metEnd);
            if numel(muMet) >= 3 && all(isfinite(muMet))
                [amp, pkRel] = max(muMet);   % positive peak amplitude
                h  = 0.5 * amp;              % half-height

                % Left crossing (linear interp)
                kL = pkRel;
                while kL > 1 && muMet(kL) >= h, kL = kL - 1; end
                if kL >= 1 && (kL+1) <= Lmet && muMet(kL) < h && muMet(kL+1) >= h
                    left_ip = kL + (h - muMet(kL)) / (muMet(kL+1) - muMet(kL));
                else, left_ip = NaN; end

                % Right crossing (linear interp)
                kR = pkRel;
                while kR < Lmet && muMet(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= Lmet && muMet(kR-1) >= h && muMet(kR) < h
                    right_ip = (kR-1) + (h - muMet(kR-1)) / (muMet(kR) - muMet(kR-1));
                else, right_ip = NaN; end

                % Convert to time (ms) relative to center and draw guides if in range
                if isfinite(left_ip) && isfinite(right_ip)
                    tPk_ms = ((metStart + pkRel  - 1) - centerIdx) / sfx * 1e3;
                    tL_ms  = ((metStart + left_ip - 1) - centerIdx) / sfx * 1e3;
                    tR_ms  = ((metStart + right_ip- 1) - centerIdx) / sfx * 1e3;

                    if tL_ms >= tRelMs(1) && tR_ms <= tRelMs(end)
                        xline(ax, tL_ms, '-', 'Color',[0.85 0.10 0.10], 'LineWidth',2.2, 'HandleVisibility','off');
                        xline(ax, tR_ms, '-', 'Color',[0.85 0.10 0.10], 'LineWidth',2.2, 'HandleVisibility','off');
                        plot(ax, [tL_ms tR_ms],[0 0], '-', 'Color',[0.85 0.10 0.10], 'LineWidth',1.4, 'HandleVisibility','off');
                    end
                    if tPk_ms >= tRelMs(1) && tPk_ms <= tRelMs(end)
                        plot(ax, tPk_ms, amp, 'o', 'MarkerSize',4.5, ...
                             'MarkerFaceColor',[0 0 0], 'MarkerEdgeColor','none', 'HandleVisibility','off');
                    end
                end
            end
        end

        % Axes cosmetics and fixed y-limit
        xline(ax, 0,'--k','LineWidth',0.9); 
        yline(ax, 0,':','Color',[0.7 0.7 0.7]);
        ylim(ax, yL);                         % <- fixed ±3000 µV (or override)
        ax.FontSize = 8;

        % Title shows per-channel amp/HW stats
        if ~isempty(kept_channels) && chList(k) <= numel(kept_channels)
            chName = sprintf('row %d (CSC%d)', chList(k), kept_channels(chList(k)));
        else
            chName = sprintf('row %d', chList(k));
        end
        if isfinite(G.ampMean(k)) && isfinite(G.hwMean(k))
            ttlTxt = sprintf('%s | amp=%.1f\\pm%.1f \\muV | HW=%.2f\\pm%.2f ms | n=%d', ...
                chName, G.ampMean(k), G.ampSD(k), G.hwMean(k), G.hwSD(k), G.n(k));
        else
            ttlTxt = sprintf('%s | amp=NA | HW=NA | n=%d', chName, G.n(k));
        end
        title(ax, ttlTxt, 'FontSize',9, 'FontWeight','normal');

        if k <= nCh - nCols, ax.XTickLabel = []; else, xlabel(ax, 'ms'); end
        ylabel(ax, '\muV');
    end

    % Figure title
    sg = sprintf(['%s  |  anchor: mean(rows %d..%d) pos-peak (±%.1f ms)  |  ', ...
                  'display: \\pm%.1f ms  |  metrics: \\pm%.1f ms  |  channels=%d  |  %s  |  yLim=\\pm%.0f \\muV'], ...
                 tag, anchorRowsAbs(1), anchorRowsAbs(end), 1e3*HWanchor/sfx, ...
                 1e3*HWdisp/sfx, 1e3*HWmet/sfx, nCh, tagStr, yL(2));
    sgtitle(tl, sg, 'FontSize',11,'FontWeight','bold');

    % Save figure
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved: %s\n', outPng);
end

function s = tern(cond, a, b)
    if cond, s = a; else, s = b; end
end

function T = makePerChannelTable(G, groupName, chList, kept_channels)
    % Lightweight per-channel summary table for CSV
    if isempty(G) || all(all(isnan(G.MU)))
        T = table(); return;
    end
    nCh = numel(chList);
    if isempty(kept_channels)
        chLab = arrayfun(@(r) sprintf('row %d', r), chList(:), 'UniformOutput', false);
    else
        chLab = arrayfun(@(r) sprintf('row %d (CSC%d)', r, kept_channels(r)), chList(:), 'UniformOutput', false);
    end
    T = table( repmat(string(groupName), nCh,1), ...
               chList(:), ...
               string(chLab(:)), ...
               G.n(:), ...
               G.ampMean(:), G.ampSD(:), ...
               G.hwMean(:),  G.hwSD(:), ...
               'VariableNames', {'Group','Row','ChannelLabel','Nused','AmpMean_uV','AmpSD_uV','HW_ms_Mean','HW_ms_SD'});
end
end
