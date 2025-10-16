function res = VACC_EventStacks_ampWidth_Avg(dataDir, V, varargin)
% VACC_EventStacks_ampWidth_Avg
% VACC version of EventStacks_ampWidth_Avg_Pipeline:
%   - Uses converted data struct V (µV) instead of dataMatPath
%   - Solid/Sputter folders are under dataDir/VACC_TheVision_out/
%   - Saves SOLID/SPUTTER PNGs + stats + per-channel CSV
%
% INPUTS
%   dataDir : folder that contains VACC_TheVision_out/{Solid,Sputter} and the Excel
%   V       : struct with fields
%             V.D  [nCh x nSamp]  (µV, single)
%             V.fs (Hz)
%             V.nums (CSC numbers per row)
%
% OUTPUT (for pipeline picker)
%   res.pngSolid, res.pngSputter, res.statsMatSolid, res.statsMatSputter, res.statsCSV

% ---------------- Args ----------------
p = inputParser;
p.addRequired('dataDir', @(s)ischar(s)||isstring(s));
p.addRequired('V',       @(x)isstruct(x) && isfield(x,'D') && isfield(x,'fs'));
% Selection / alignment / windows
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('halfWidthMs',         10e-3, @(x)isfinite(x)&&x>0); % ±10 ms display/averaging
p.addParameter('metricHalfWidthMs',    5e-3, @(x)isfinite(x)&&x>0); % ±5 ms metrics
p.addParameter('anchorHalfWidthMs',    5e-3, @(x)isfinite(x)&&x>0); % ±5 ms anchor search
% Spreadsheet + mapping
p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('indexBase','auto', @(s) any(strcmpi(s,{'auto','zero','one'})));
p.addParameter('evtOffset',0, @(x)isscalar(x)&&isfinite(x));
p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));
% Output + y-axis
p.addParameter('saveDir',"", @(s)ischar(s)||isstring(s));
p.addParameter('tag','ALL', @(s)ischar(s)||isstring(s));
p.addParameter('yLimMicroV', [], @(x) isempty(x) || (isscalar(x) && x>0)); % fixed ± limit
p.addParameter('yRobustPct', 99.5, @(x) isfinite(x) && x>0 && x<100);      % robust percentile if auto
p.addParameter('yPadFrac', 0.12, @(x) isfinite(x) && x>=0 && x<=0.5);      % headroom
p.parse(dataDir, V, varargin{:});

dataDir        = string(p.Results.dataDir);
D              = V.D;                        % µV (single)
sfx            = V.fs;
kept_channels  = []; if isfield(V,'nums'), kept_channels = V.nums(:)'; end
channelIndices = p.Results.channelIndices;

halfWidthMs    = p.Results.halfWidthMs;
metricHWms     = p.Results.metricHalfWidthMs;
anchorHWms     = p.Results.anchorHalfWidthMs;

excelPath      = string(p.Results.excelPath);
indexBase      = lower(string(p.Results.indexBase));
evtOffset      = p.Results.evtOffset;
maxEventsPerGp = p.Results.maxEventsPerGroup;

saveDir        = string(p.Results.saveDir);
tagStr         = string(p.Results.tag);
yLimMicroV     = p.Results.yLimMicroV;
yRobustPct     = p.Results.yRobustPct;
yPadFrac       = p.Results.yPadFrac;

% ---------------- Layout ----------------
rootVision = fullfile(dataDir, "VACC_TheVision_out");
solidDir   = fullfile(rootVision, "Solid");
sputterDir = fullfile(rootVision, "Sputter");
assert(isfolder(solidDir),   'Missing folder: %s', solidDir);
assert(isfolder(sputterDir), 'Missing folder: %s', sputterDir);

% Excel (find first .xlsx if not provided)
if excelPath == ""
    xl = dir(fullfile(dataDir, "*.xlsx"));
    assert(~isempty(xl), 'No Excel file (*.xlsx) found in %s', dataDir);
    excelPath = fullfile(xl(1).folder, xl(1).name);
end
assert(isfile(excelPath), 'Excel not found: %s', excelPath);

% ---------------- Data selection ----------------
[nRowsAll, nSamp] = size(D);
if isempty(channelIndices)
    chList = 1:nRowsAll;
else
    chList = channelIndices(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);

% ---------- Pipeline output directory ----------
if saveDir == ""
    outDir = fullfile(dataDir, 'EventStacks AmpWidth Output');
else
    outDir = char(saveDir);
end
if ~exist(outDir,'dir'), mkdir(outDir); end

% file paths for PNGs and stats
pngSOL = fullfile(outDir, sprintf('AvgStack_SOLID_anchor-max_disp%ds_met%ds.png', round(halfWidthMs*sfx), round(metricHWms*sfx)));
pngSPU = fullfile(outDir, sprintf('AvgStack_SPUTTER_anchor-max_disp%ds_met%ds.png', round(halfWidthMs*sfx), round(metricHWms*sfx)));
matSOL = fullfile(outDir, 'AvgStack_SOLID_stats.mat');
matSPU = fullfile(outDir, 'AvgStack_SPUTTER_stats.mat');
csvAll = fullfile(outDir, 'EventStacks_perChannel_Stats.csv');

% ---------------- Windows ----------------
HWdisp    = max(1, round(halfWidthMs * sfx));      % ± display/averaging
HWmet     = max(1, round(metricHWms  * sfx));      % ± metrics
HWanchor  = max(1, round(anchorHWms  * sfx));      % ± anchor search (first channel)
tRelSamp  = -HWdisp:HWdisp;
tRelMs    = (tRelSamp / sfx) * 1e3;
winN      = numel(tRelSamp);
centerIdx = HWdisp + 1;

fprintf(['VACC_EventStacks_ampWidth_Avg: sfx=%.1f Hz | display ±%.1f ms | ' ...
         'metrics ±%.1f ms | anchorSearch ±%.1f ms | channels=%d\n'], ...
         sfx, 1e3*HWdisp/sfx, 1e3*HWmet/sfx, 1e3*HWanchor/sfx, nCh);

% ---------------- Spreadsheet -> samples ----------------
T = readtable(excelPath, 'ReadVariableNames', true);
canon = lower(regexprep(T.Properties.VariableNames, '[^a-zA-Z0-9]', ''));
i_onSamp  = find(strcmp(canon,'onsamp')  | strcmp(canon,'startsample') | strcmp(canon,'startsamp') | strcmp(canon,'on'), 1);
i_offSamp = find(strcmp(canon,'offsamp') | strcmp(canon,'endsample')   | strcmp(canon,'endsamp')   | strcmp(canon,'off'), 1);
i_onSec   = find(strcmp(canon,'onsec')   | strcmp(canon,'startsec')    | strcmp(canon,'onsecs'), 1);
i_offSec  = find(strcmp(canon,'offsec')  | strcmp(canon,'endsec')      | strcmp(canon,'offsecs'), 1);

if ~isempty(i_onSamp) && ~isempty(i_offSamp)
    onSamp  = double(T{:, i_onSamp});
    offSamp = double(T{:, i_offSamp});
elseif ~isempty(i_onSec) && ~isempty(i_offSec)
    onSamp  = round(double(T{:, i_onSec})  * sfx);
    offSamp = round(double(T{:, i_offSec}) * sfx);
else
    assert(width(T) >= 2, 'Excel must have [on_samp, off_samp] or [on_sec, off_sec].');
    onSamp  = double(T{:,1});
    offSamp = double(T{:,2});
end

switch indexBase
    case "zero", onSamp = onSamp+1; offSamp = offSamp+1;
    case "auto"
        if any(onSamp < 1 | offSamp < 1 | onSamp==0 | offSamp==0)
            onSamp = onSamp+1; offSamp = offSamp+1;
        end
    case "one" % no-op
end

NrowsXL = numel(onSamp);
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));

% ---------------- Events from PNG names ----------------
evtSOL = unique(parseEvtNumsFromPngs(solidDir));
evtSPU = unique(parseEvtNumsFromPngs(sputterDir));
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));

if ~isempty(maxEventsPerGp)
    evtSOL = evtSOL(1:min(end, maxEventsPerGp));
    evtSPU = evtSPU(1:min(end, maxEventsPerGp));
end

% ---------------- Build group stats ----------------
[SOL, robSOL] = avgForGroup(evtSOL, 'SOLID');
[SPU, robSPU] = avgForGroup(evtSPU, 'SPUTTER');

% ---------------- Global y-limit across BOTH figures ----------------
if isempty(yLimMicroV)
    yMaxSOL = computeYMaxForGroup(SOL);
    yMaxSPU = computeYMaxForGroup(SPU);
    rob     = max([robSOL, robSPU, yMaxSOL, yMaxSPU, 10]);  % ensure >=10 µV headroom
    yMax    = (1 + yPadFrac) * rob;
else
    yMax = yLimMicroV;
end
yL_global = [-yMax, +yMax];
fprintf('Global y-limit (both figs): ±%.1f µV (%s)\n', yMax, tern(isempty(yLimMicroV),'auto','fixed'));

% ---------------- Plot & save (2 columns, with indicators) ----------------
plotStackWithIndicators(SOL, 'SOLID', yL_global, pngSOL);
plotStackWithIndicators(SPU, 'SPUTTER', yL_global, pngSPU);

% ---------------- Save lightweight stats & CSV ----------------
if ~isempty(SOL), save(matSOL, '-struct', 'SOL'); end
if ~isempty(SPU), save(matSPU, '-struct', 'SPU'); end

try
    Tcsv = makePerChannelTable(SOL, 'SOLID', chList, kept_channels);
    Tcsv = [Tcsv; makePerChannelTable(SPU, 'SPUTTER', chList, kept_channels)];
    writetable(Tcsv, csvAll);
catch ME
    wid = ME.identifier;
    if isempty(wid), wid = 'VACC:CSVWriteFailed'; end
    warning(wid, 'Failed writing EventStacks per-channel stats CSV to %s: %s', csvAll, ME.message);
end


% ---------------- Return paths ----------------
res = struct('outputDir', outDir, ...
             'pngSolid', pngSOL, 'pngSputter', pngSPU, ...
             'statsMatSolid', matSOL, 'statsMatSputter', matSPU, ...
             'statsCSV', csvAll);

fprintf('EventStacks outputs:\n  %s\n  %s\n  %s\n', pngSOL, pngSPU, csvAll);

% ======================================================================
%                                HELPERS
% ======================================================================

function evts = parseEvtNumsFromPngs(dirpath)
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

function yMax = computeYMaxForGroup(G)
    if isempty(G) || all(all(isnan(G.MU)))
        yMax = 0; return;
    end
    mm = max(abs([G.MU(:)+G.SE(:); G.MU(:)-G.SE(:)]), [], 'omitnan');
    as = max(G.ampMean + 3*G.ampSD, [], 'omitnan');
    yMax = max([mm, as, 0], [], 'omitnan');
    if ~isfinite(yMax) || yMax <= 0, yMax = 0; end
end

function [G, robAll] = avgForGroup(evtList, tag)
    G = struct('MU',nan(nCh,winN),'SE',nan(nCh,winN),'n',zeros(nCh,1), ...
               'ampMean',nan(nCh,1),'ampSD',nan(nCh,1),'hwMean',nan(nCh,1),'hwSD',nan(nCh,1), ...
               'usedEvents',[],'tRelMs',tRelMs,'traces',{cell(nCh,1)});
    robAll = 0;
    if isempty(evtList)
        warning('%s: no events.', tag); return;
    end

    stacks = cell(nCh,1);
    amps   = cell(nCh,1);
    hws    = cell(nCh,1);
    for i=1:nCh, stacks{i} = []; amps{i} = []; hws{i} = []; end

    refCh = chList(1);  % FIRST row drives the anchor
    nBad = 0;

    for ii = 1:numel(evtList)
        e = evtList(ii);
        rowXL = e + evtOffset;
        if rowXL < 1 || rowXL > NrowsXL
            alt = e;
            if alt >= 1 && alt <= NrowsXL, rowXL = alt; else, nBad=nBad+1; continue; end
        end

        s0_ev = max(1, round(onSamp(rowXL)));
        s1_ev = min(nSamp, round(offSamp(rowXL)));
        if ~isfinite(s0_ev) || ~isfinite(s1_ev) || s1_ev <= s0_ev
            nBad=nBad+1; continue;
        end

        ancMid = round((s0_ev + s1_ev)/2);

        % -------- COMMON ANCHOR from FIRST channel, POSITIVE PEAK ONLY --------
        s0srch = max(1, ancMid - HWanchor);
        s1srch = min(nSamp, ancMid + HWanchor);
        yseg0  = double(D(refCh, s0srch:s1srch));   % already µV

        if isempty(yseg0) || all(~isfinite(yseg0))
            nBad = nBad + 1; continue;
        end

        [~, k_rel] = max(yseg0);  % positive peak
        if isempty(k_rel) || ~isfinite(k_rel)
            nBad = nBad + 1; continue;
        end
        commonAnchor = s0srch + k_rel - 1;

        okAnyCh = false;
        for k = 1:nCh
            ch = chList(k);

            % Averaging window centered on COMMON anchor
            s0 = commonAnchor - HWdisp; s1 = commonAnchor + HWdisp;
            if s0 < 1 || s1 > nSamp, continue; end
            y = double(D(ch, s0:s1));             % µV
            if any(~isfinite(y)), continue; end
            stacks{k}(end+1,:) = y; %#ok<AGROW>
            okAnyCh = true;

            % robust y-limit helper on display window
            yy = y(isfinite(y));
            if ~isempty(yy)
                pval = prctile(abs(yy), yRobustPct);
                if isfinite(pval) && pval > robAll, robAll = pval; end
            end

            % Metrics (±metric) around COMMON anchor: POSITIVE PEAK ONLY
            s0m = max(1, commonAnchor - HWmet);
            s1m = min(nSamp, commonAnchor + HWmet);
            ym  = double(D(ch, s0m:s1m));
            if numel(ym) >= 3 && all(isfinite(ym))
                [amp, pkRel] = max(ym);
                h = 0.5 * amp;

                % left crossing
                kL = pkRel;
                while kL > 1 && ym(kL) >= h, kL = kL - 1; end
                if kL >= 1 && (kL+1) <= numel(ym) && ym(kL) < h && ym(kL+1) >= h
                    left_ip = kL + (h - ym(kL)) / (ym(kL+1) - ym(kL));
                else, left_ip = NaN; end

                % right crossing
                kR = pkRel; Lm = numel(ym);
                while kR < Lm && ym(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= Lm && ym(kR-1) >= h && ym(kR) < h
                    right_ip = (kR-1) + (h - ym(kR-1)) / (ym(kR) - ym(kR-1));
                else, right_ip = NaN; end

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

    if nBad>0, fprintf('%s: skipped %d event(s).\n', tag, nBad); end
    fprintf('%s: used %d/%d events.\n', tag, numel(G.usedEvents), numel(evtList));

    % Aggregate per channel
    for k = 1:nCh
        X = stacks{k}; 
        nUsed = size(X,1); 
        G.n(k) = nUsed;
        if nUsed > 0
            G.MU(k,:) = mean(X, 1, 'omitnan');
            G.SE(k,:) = std( X, 0, 1, 'omitnan') ./ max(1,sqrt(nUsed));
        end
        a = amps{k}; w = hws{k};
        if ~isempty(a), G.ampMean(k) = mean(a, 'omitnan'); G.ampSD(k) = std(a, 0, 'omitnan'); end
        if ~isempty(w), G.hwMean(k)  = mean(w, 'omitnan'); G.hwSD(k)  = std(w,  0, 'omitnan'); end

        G.traces{k} = X; % keep contributing traces for overlay
    end

    % Save lightweight stats for this group
    alignLabel = sprintf('first-channel max (±%.1f ms)', 1e3*HWanchor/sfx);
    statsPath = fullfile(outDir, sprintf('AvgStack_%s_stats.mat', tag));
    chList_local = chList; %#ok<NASGU>
    Gsave = G;
    save(statsPath, 'tRelMs','chList_local','kept_channels','halfWidthMs','metricHWms','sfx', ...
                    'alignLabel','Gsave');
    fprintf('Saved group stats: %s\n', statsPath);

    % attach for caller
    G.outStatsPath = statsPath;
end

function plotStackWithIndicators(G, tag, yL, outPng)
    if isempty(G) || all(all(isnan(G.MU)))
        warning('%s: no data to plot.', tag); 
        return; 
    end

    % ---- 2 columns layout ----
    nCols = 2;
    nRowsGrid = ceil(nCh / nCols);

    perRowPx = 120; basePx = 220; maxPx = 5200;
    figH = min(maxPx, basePx + perRowPx * nRowsGrid);
    f = figure('Color','w','Position',[60 60 1100 figH],'Visible','off');
    tl = tiledlayout(f, nRowsGrid, nCols, 'Padding','compact','TileSpacing','compact');

    % metric subrange indices within mean vector
    metStart = max(1, centerIdx - HWmet);
    metEnd   = min(winN, centerIdx + HWmet);
    Lmet     = metEnd - metStart + 1;

    for k = 1:nCh
        mu = G.MU(k,:); se = G.SE(k,:);
        ax = nexttile(tl); hold(ax,'on'); box(ax,'on'); grid(ax,'on');

        % faint overlay
        if isfield(G,'traces') && numel(G.traces) >= k && ~isempty(G.traces{k})
            Yk = G.traces{k};
            for r = 1:size(Yk,1)
                y = Yk(r,:);
                if any(isfinite(y))
                    plot(ax, tRelMs, y, 'LineWidth', 0.5, 'Color', [0.65 0.65 0.65]);
                end
            end
        end

        if any(isfinite(mu))
            yu = mu + se; yl = mu - se;
            xp = [tRelMs, fliplr(tRelMs)];
            yp = [yu,      fliplr(yl)];
            patch('XData',xp,'YData',yp,'FaceColor',[0.3 0.3 0.9],'FaceAlpha',0.25,'EdgeColor','none','HandleVisibility','off');
            plot(ax, tRelMs, mu, 'LineWidth', 1.8);

            % Indicators on mean (positive peak) within metric window
            muMet = mu(metStart:metEnd);
            if numel(muMet) >= 3 && all(isfinite(muMet))
                [amp, pkRel] = max(muMet);   
                h  = 0.5 * amp;
                % left crossing
                kL = pkRel;
                while kL > 1 && muMet(kL) >= h, kL = kL - 1; end
                if kL >= 1 && (kL+1) <= Lmet && muMet(kL) < h && muMet(kL+1) >= h
                    left_ip = kL + (h - muMet(kL)) / (muMet(kL+1) - muMet(kL));
                else, left_ip = NaN; end
                % right crossing
                kR = pkRel;
                while kR < Lmet && muMet(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= Lmet && muMet(kR-1) >= h && muMet(kR) < h
                    right_ip = (kR-1) + (h - muMet(kR-1)) / (muMet(kR) - muMet(kR-1));
                else, right_ip = NaN; end

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
                        plot(ax, tPk_ms, amp, 'o', 'MarkerSize',4.5, 'MarkerFaceColor',[0 0 0], 'MarkerEdgeColor','none','HandleVisibility','off');
                    end
                end
            end
        end

        xline(ax, 0,'--k','LineWidth',0.9); yline(ax, 0,':','Color',[0.7 0.7 0.7]);
        ylim(ax, yL);

        % Title (per-event stats mean±SD)
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

        ax.FontSize = 8;
        if k <= nCh - nCols, ax.XTickLabel = []; else, xlabel(ax, 'ms'); end
        ylabel(ax, '\muV');
    end

    sg = sprintf('%s  |  anchor: first-channel max (±%.1f ms)  |  display: \\pm%.1f ms  |  metrics: \\pm%.1f ms  |  channels=%d  |  %s', ...
                 tag, 1e3*HWanchor/sfx, 1e3*HWdisp/sfx, 1e3*HWmet/sfx, nCh, tagStr);
    sgtitle(tl, sg, 'FontSize',11,'FontWeight','bold');

    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved: %s\n', outPng);
end

function s = tern(cond, a, b)
    if cond, s = a; else, s = b; end
end

function T = makePerChannelTable(G, groupName, chList, kept_channels)
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
