function res = VACC_EventStacks_ampWidth_Avg_Pipeline(eventsFolder, dataDir, varargin)
% VACC_EventStacks_ampWidth_Avg_Pipeline
% VACC version of EventStacks_ampWidth_Avg_Pipeline:
%   - Uses ets/ech in dataDir for on/off (samples) and channel map
%   - Loads CSC*.ncs with Nlx2MatCSC, converts to µV using ADBitVolts
%   - Finds events from Evt###_##Ch.png under Solid/ and Sputter/
%   - Positive-peak anchor on FIRST channel near midpoint of each event
%   - Plots mean±SEM per channel + half-width/amp indicators
%
% INPUTS
%   eventsFolder : folder with Solid/ and Sputter/ images (Evt###_##Ch.png)
%   dataDir      : folder with ets.mat, ech.mat, and CSC*.ncs
%
% OUTPUT
%   res.pngSolid, res.pngSputter, res.statsMatSolid, res.statsMatSputter, res.statsCSV

% ---------------- Args ----------------
p = inputParser;
p.addRequired('eventsFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataDir',      @(s)ischar(s)||isstring(s));

% channel / polarity / file selection
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('evenOnly', false, @(x)islogical(x)||ismember(x,[0 1]));
p.addParameter('invertPolarity', false, @(x)islogical(x)||ismember(x,[0 1]));

% windows (seconds)
p.addParameter('displayHalfWidthSec',  10e-3, @(x)isfinite(x)&&x>0); % ±10 ms
p.addParameter('metricHalfWidthSec',    5e-3, @(x)isfinite(x)&&x>0); % ±5 ms
p.addParameter('anchorHalfWidthSec',    5e-3, @(x)isfinite(x)&&x>0); % ±5 ms

% event index offset (if Evt001 corresponds to ets row 0 or 2, etc.)
p.addParameter('eventRowOffset', 0, @(x)isscalar(x)&&isfinite(x));
p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));

% output + y-axis
p.addParameter('saveDir',"", @(s)ischar(s)||isstring(s));
p.addParameter('tag','ALL', @(s)ischar(s)||isstring(s));
p.addParameter('yLimitMicroV', [], @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('yRobustPercentile', 99.5, @(x) isfinite(x) && x>0 && x<100);
p.addParameter('yPadFraction', 0.12, @(x) isfinite(x) && x>=0 && x<=0.5);

p.parse(eventsFolder, dataDir, varargin{:});
eventsFolder          = string(p.Results.eventsFolder);
dataDir               = string(p.Results.dataDir);

channelIndicesUser    = p.Results.channelIndices;
evenOnly              = logical(p.Results.evenOnly);
invertPolarity        = logical(p.Results.invertPolarity);

displayHalfWidthSec   = p.Results.displayHalfWidthSec;
metricHalfWidthSec    = p.Results.metricHalfWidthSec;
anchorHalfWidthSec    = p.Results.anchorHalfWidthSec;

eventRowOffset        = p.Results.eventRowOffset;
maxEventsPerGroup     = p.Results.maxEventsPerGroup;

saveDir               = string(p.Results.saveDir);
tagString             = string(p.Results.tag);
yLimitMicroV          = p.Results.yLimitMicroV;
yRobustPercentile     = p.Results.yRobustPercentile;
yPadFraction          = p.Results.yPadFraction;

% ---------------- Layout ----------------
solidFolder   = fullfile(eventsFolder, "Solid");
sputterFolder = fullfile(eventsFolder, "Sputter");
assert(isfolder(solidFolder),   'Missing folder: %s', solidFolder);
assert(isfolder(sputterFolder), 'Missing folder: %s', sputterFolder);

% ---------------- Load ets / ech ----------------
load(fullfile(dataDir,'ets.mat'),'ets');     % [nEvents x 2] samples: [on off]
load(fullfile(dataDir,'ech.mat'),'ech');     % channel map/meta (size used for count; labels from CSC# below)
fprintf('Loaded %d events × %d channels from ets/ech\n', size(ets,1), size(ech,2));

% ---------------- Find CSC files ----------------
files = dir(fullfile(dataDir,'CSC*.ncs'));
if isempty(files), error('No CSC*.ncs files in: %s', dataDir); end
nums = cellfun(@(n) sscanf(n,'CSC%d.ncs'), {files.name});
keep = ~isnan(nums);
if evenOnly, keep = keep & mod(nums,2)==0; end
files = files(keep); nums = nums(keep);
[nums, ord] = sort(nums); files = files(ord);
nChAll = numel(files);

% ---------------- Read header ONCE ----------------
hdr = Nlx2MatCSC(fullfile(files(1).folder, files(1).name), [0 0 0 0 0], 1, 1, []);
ADBitVolts = parse_adbitvolts(hdr);              % volts/bit
fsHdr      = parse_samplingfreq(hdr);            % Hz
if isnan(ADBitVolts), error('ADBitVolts not found in header.'); end
fs = fsHdr; if isnan(fs), fs = 30000; end
fprintf('Header: ADBitVolts=%.12g V/bit | fs=%.0f Hz\n', ADBitVolts, fs);

% ---------------- Load raw samples per channel ----------------
fprintf('Loading raw samples...\n');
raw = cell(1,nChAll);
maxLen = 0;
for i = 1:nChAll
    fn = fullfile(files(i).folder, files(i).name);
    try
        S = Nlx2MatCSC(fn, [0 0 0 0 1], 0, 1, []);     % samples only
        s = reshape(S,1,[]);                           % [1 x N]
        s = single(s);
        if invertPolarity, s = -s; end
        raw{i} = s;
        if numel(s) > maxLen, maxLen = numel(s); end
    catch ME
        fprintf('  !! %s failed: %s\n', files(i).name, ME.message);
        raw{i} = [];
    end
end
fprintf('Longest channel: %.2f sec\n', maxLen/fs);

% Stack to rectangular matrix (A/D counts)
D = zeros(nChAll, maxLen, 'single');
for i = 1:nChAll
    v = raw{i}; if isempty(v), continue; end
    D(i,1:numel(v)) = v;
end
clear raw

% Convert ONCE to microvolts
D = D .* single(ADBitVolts * 1e6);               % µV

% ---------------- Channel list ----------------
if isempty(channelIndicesUser)
    chList = 1:nChAll;
else
    chList = channelIndicesUser(:).';
    chList = chList(chList>=1 & chList<=nChAll);
end
nCh = numel(chList);
fprintf('Using %d %s-numbered channels (CSC labels kept for titles)\n', nCh, tern(evenOnly,'even','all'));

% For titles: map each row to CSC#
kept_channels = zeros(1, nChAll); kept_channels(:) = nums(:);
kept_channels = kept_channels(:)'; % index by row

% ---------------- Output directory ----------------
if saveDir == ""
    outDir = fullfile(eventsFolder, 'EventStacks AmpWidth Output');
else
    outDir = char(saveDir);
end
if ~exist(outDir,'dir'), mkdir(outDir); end

pngSOL = fullfile(outDir, 'AvgStack_SOLID.png');
pngSPU = fullfile(outDir, 'AvgStack_SPUTTER.png');
matSOL = fullfile(outDir, 'AvgStack_SOLID_stats.mat');
matSPU = fullfile(outDir, 'AvgStack_SPUTTER_stats.mat');
csvAll = fullfile(outDir, 'EventStacks_perChannel_Stats.csv');

% ---------------- Windows (in samples) ----------------
HWdisp    = max(1, round(displayHalfWidthSec * fs));
HWmet     = max(1, round(metricHalfWidthSec  * fs));
HWanchor  = max(1, round(anchorHalfWidthSec  * fs));

tRelSamp  = -HWdisp:HWdisp;
tRelMs    = (tRelSamp / fs) * 1e3;
winN      = numel(tRelSamp);
centerIdx = HWdisp + 1;

fprintf(['VACC EventStacks: fs=%.1f Hz | display ±%.1f ms | metrics ±%.1f ms | ' ...
         'anchor ±%.1f ms | channels=%d\n'], ...
         fs, 1e3*HWdisp/fs, 1e3*HWmet/fs, 1e3*HWanchor/fs, nCh);

nSamp = size(D,2);
NeventsETS = size(ets,1);

% ---------------- Events from PNG names ----------------
evtSOL = unique(parseEvtNumsFromPngs(solidFolder));
evtSPU = unique(parseEvtNumsFromPngs(sputterFolder));
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));
if ~isempty(maxEventsPerGroup)
    evtSOL = evtSOL(1:min(end, maxEventsPerGroup));
    evtSPU = evtSPU(1:min(end, maxEventsPerGroup));
end

% ---------------- Build group stats ----------------
[SOL, robSOL] = avgForGroup(evtSOL, 'SOLID');
[SPU, robSPU] = avgForGroup(evtSPU, 'SPUTTER');

% ---------------- Global y-limit across BOTH figures ----------------
if isempty(yLimitMicroV)
    yMaxSOL = computeYMaxForGroup(SOL);
    yMaxSPU = computeYMaxForGroup(SPU);
    rob     = max([robSOL, robSPU, yMaxSOL, yMaxSPU, 10]);  % ≥10 µV headroom
    yMax    = (1 + yPadFraction) * rob;
else
    yMax = yLimitMicroV;
end
yL_global = [-yMax, +yMax];
fprintf('Global y-limit (both figs): ±%.1f µV (%s)\n', yMax, tern(isempty(yLimitMicroV),'auto','fixed'));

% ---------------- Plot & save ----------------
plotStackWithIndicators(SOL, 'SOLID', yL_global, pngSOL);
plotStackWithIndicators(SPU, 'SPUTTER', yL_global, pngSPU);

% ---------------- Save stats & CSV ----------------
if ~isempty(SOL), save(matSOL, '-struct', 'SOL'); end
if ~isempty(SPU), save(matSPU, '-struct', 'SPU'); end

try
    Tcsv = makePerChannelTable(SOL, 'SOLID', chList, kept_channels);
    Tcsv = [Tcsv; makePerChannelTable(SPU, 'SPUTTER', chList, kept_channels)];
    writetable(Tcsv, csvAll);
    fprintf('Per-channel stats CSV: %s\n', csvAll);
catch ME
    warning('Failed writing EventStacks per-channel stats CSV: %s', ME.message);
end

% ---------------- Return paths ----------------
res = struct('outputDir', outDir, ...
             'pngSolid', pngSOL, 'pngSputter', pngSPU, ...
             'statsMatSolid', matSOL, 'statsMatSputter', matSPU, ...
             'statsCSV', csvAll);

fprintf('VACC EventStacks pipeline outputs:\n  %s\n  %s\n  %s\n', pngSOL, pngSPU, csvAll);

% ======================================================================
%                                HELPERS
% ======================================================================

function evts = parseEvtNumsFromPngs(dirpath)
    L = dir(fullfile(dirpath, '*.png'));
    evts = [];
    for k = 1:numel(L)
        % Accept Evt### or Evt###_##Ch
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

    refCh = chList(1);  % FIRST channel drives the anchor
    nBad = 0;

    for ii = 1:numel(evtList)
        e = evtList(ii);
        rowETS = e + eventRowOffset;
        if rowETS < 1 || rowETS > NeventsETS
            nBad = nBad + 1; continue;
        end

        s0_ev = max(1, round(ets(rowETS,1)));
        s1_ev = min(nSamp, round(ets(rowETS,2)));
        if ~isfinite(s0_ev) || ~isfinite(s1_ev) || s1_ev <= s0_ev
            nBad = nBad + 1; continue;
        end

        ancMid  = round((s0_ev + s1_ev)/2);
        s0srch  = max(1, ancMid - HWanchor);
        s1srch  = min(nSamp, ancMid + HWanchor);

        yseg0 = double(D(refCh, s0srch:s1srch));   % already µV
        if isempty(yseg0) || all(~isfinite(yseg0))
            nBad = nBad + 1; continue;
        end
        [~, k_rel] = max(yseg0);  % positive peak only
        if isempty(k_rel) || ~isfinite(k_rel)
            nBad = nBad + 1; continue;
        end
        commonAnchor = s0srch + k_rel - 1;

        okAnyCh = false;
        for k = 1:nCh
            ch = chList(k);

            s0 = commonAnchor - HWdisp; 
            s1 = commonAnchor + HWdisp;
            if s0 < 1 || s1 > nSamp, continue; end

            y = double(D(ch, s0:s1));  % µV
            if any(~isfinite(y)), continue; end
            stacks{k}(end+1,:) = y; %#ok<AGROW>
            okAnyCh = true;

            % robust y-limit helper
            yy = y(isfinite(y));
            if ~isempty(yy)
                pctl = prctile(abs(yy), yRobustPercentile);
                if isfinite(pctl) && pctl > robAll, robAll = pctl; end
            end

            % metrics window
            s0m = max(1, commonAnchor - HWmet);
            s1m = min(nSamp, commonAnchor + HWmet);
            ym  = double(D(ch, s0m:s1m));
            if numel(ym) >= 3 && all(isfinite(ym))
                [amp, pkRel] = max(ym);
                h  = 0.5 * amp;

                % left crossing
                kL = pkRel;
                while kL > 1 && ym(kL) >= h, kL = kL - 1; end
                if kL >= 1 && (kL+1) <= numel(ym) && ym(kL) < h && ym(kL+1) >= h
                    left_ip = kL + (h - ym(kL)) / (ym(kL+1) - ym(kL));
                else
                    left_ip = NaN;
                end

                % right crossing
                kR = pkRel; Lm = numel(ym);
                while kR < Lm && ym(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= Lm && ym(kR-1) >= h && ym(kR) < h
                    right_ip = (kR-1) + (h - ym(kR-1)) / (ym(kR) - ym(kR-1));
                else
                    right_ip = NaN;
                end

                if isfinite(left_ip) && isfinite(right_ip) && right_ip > left_ip
                    hw_ms = (right_ip - left_ip) / fs * 1e3;
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
        G.traces{k} = X;
    end

    % Save lightweight stats for this group
    alignLabel = sprintf('first-channel max (±%.1f ms)', 1e3*HWanchor/fs); %#ok<NASGU>
    statsPath  = fullfile(outDir, sprintf('AvgStack_%s_stats.mat', tag));
    chList_local = chList; %#ok<NASGU>
    save(statsPath, 'tRelMs','chList_local','kept_channels','displayHalfWidthSec','metricHalfWidthSec','fs', ...
                    'alignLabel','-struct','G');
    fprintf('Saved group stats: %s\n', statsPath);

    % attach for caller
    G.outStatsPath = statsPath;
end

function plotStackWithIndicators(G, tag, yL, outPng)
    if isempty(G) || all(all(isnan(G.MU)))
        warning('%s: no data to plot.', tag); 
        return; 
    end

    nCols = 2;
    nRowsGrid = ceil(nCh / nCols);
    perRowPx = 120; basePx = 220; maxPx = 5200;
    f = figure('Color','w','Position',[60 60 1100 min(maxPx, basePx + perRowPx * nRowsGrid)],'Visible','off');
    tl = tiledlayout(f, nRowsGrid, nCols, 'Padding','compact','TileSpacing','compact');

    metStart = max(1, centerIdx - HWmet);
    metEnd   = min(winN, centerIdx + HWmet);
    Lmet     = metEnd - metStart + 1;

    for k = 1:nCh
        mu = G.MU(k,:); se = G.SE(k,:);
        ax = nexttile(tl); hold(ax,'on'); box(ax,'on'); grid(ax,'on');

        if isfield(G, 'traces') && numel(G.traces) >= k && ~isempty(G.traces{k})
            Yk = G.traces{k};
            for r = 1:size(Yk,1)
                y = Yk(r,:); if any(isfinite(y))
                    plot(ax, tRelMs, y, 'LineWidth', 0.5, 'Color', [0.65 0.65 0.65]);
                end
            end
        end

        if any(isfinite(mu))
            yu = mu + se; yl = mu - se;
            xp = [tRelMs, fliplr(tRelMs)];
            yp = [yu,     fliplr(yl)];
            patch('XData',xp,'YData',yp,'FaceColor',[0.3 0.3 0.9],'FaceAlpha',0.25,'EdgeColor','none','HandleVisibility','off');
            plot(ax, tRelMs, mu, 'LineWidth', 1.8);

            muMet = mu(metStart:metEnd);
            if numel(muMet) >= 3 && all(isfinite(muMet))
                [amp, pkRel] = max(muMet);
                h  = 0.5 * amp;

                kL = pkRel;
                while kL > 1 && muMet(kL) >= h, kL = kL - 1; end
                if kL >= 1 && (kL+1) <= Lmet && muMet(kL) < h && muMet(kL+1) >= h
                    left_ip = kL + (h - muMet(kL)) / (muMet(kL+1) - muMet(kL));
                else, left_ip = NaN; end

                kR = pkRel;
                while kR < Lmet && muMet(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= Lmet && muMet(kR-1) >= h && muMet(kR) < h
                    right_ip = (kR-1) + (h - muMet(kR-1)) / (muMet(kR) - muMet(kR-1));
                else, right_ip = NaN; end

                if isfinite(left_ip) && isfinite(right_ip)
                    tPk_ms = ((metStart + pkRel  - 1) - centerIdx) / fs * 1e3;
                    tL_ms  = ((metStart + left_ip - 1) - centerIdx) / fs * 1e3;
                    tR_ms  = ((metStart + right_ip- 1) - centerIdx) / fs * 1e3;

                    if tL_ms >= tRelMs(1) && tR_ms <= tRelMs(end)
                        xline(ax, tL_ms, '-', 'Color',[0.85 0.10 0.10], 'LineWidth',2.2, 'HandleVisibility','off');
                        xline(ax, tR_ms, '-', 'Color',[0.85 0.10 0.10], 'LineWidth',2.2, 'HandleVisibility','off');
                        plot(ax, [tL_ms tR_ms],[0 0], '-', 'Color',[0.85 0.10 0.10], 'LineWidth',1.4, 'HandleVisibility','off');
                    end

                    if tPk_ms >= tRelMs(1) && tPk_ms <= tRelMs(end)
                        plot(ax, tPk_ms, amp, 'o', 'MarkerSize', 4.5, ...
                             'MarkerFaceColor',[0 0 0], 'MarkerEdgeColor','none', 'HandleVisibility','off');
                    end
                end
            end
        end

        xline(ax, 0,'--k','LineWidth',0.9);
        yline(ax, 0,':','Color',[0.7 0.7 0.7]);
        ylim(ax, yL);

        if ~isempty(kept_channels)
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
                 tag, 1e3*HWanchor/fs, 1e3*HWdisp/fs, 1e3*HWmet/fs, nCh, tagString);
    sgtitle(tl, sg, 'FontSize',11,'FontWeight','bold');

    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved: %s\n', outPng);
end

function s = tern(cond, a, b); if cond, s = a; else, s = b; end; end

function T = makePerChannelTable(G, groupName, chListLoc, keptCh)
    if isempty(G) || all(all(isnan(G.MU)))
        T = table(); return;
    end
    nChLoc = numel(chListLoc);
    if isempty(keptCh)
        chLab = arrayfun(@(r) sprintf('row %d', r), chListLoc(:), 'UniformOutput', false);
    else
        chLab = arrayfun(@(r) sprintf('row %d (CSC%d)', r, keptCh(r)), chListLoc(:), 'UniformOutput', false);
    end
    T = table( repmat(string(groupName), nChLoc,1), ...
               chListLoc(:), ...
               string(chLab(:)), ...
               G.n(:), ...
               G.ampMean(:), G.ampSD(:), ...
               G.hwMean(:),  G.hwSD(:), ...
               'VariableNames', {'Group','Row','ChannelLabel','Nused','AmpMean_uV','AmpSD_uV','HW_ms_Mean','HW_ms_SD'});
end

% ------- header parsers -------
function v = parse_adbitvolts(hdr)
    v = NaN;
    for i = 1:numel(hdr)
        line = string(hdr{i});
        if contains(line, 'ADBitVolts','IgnoreCase',true)
            m = regexp(line, 'ADBitVolts[^0-9eE\.\-\+]*([\-+]?\d*\.?\d+(?:[eE][\-+]?\d+)?)', 'tokens', 'once');
            if ~isempty(m), v = str2double(m{1}); return; end
        end
    end
end
function f = parse_samplingfreq(hdr)
    f = NaN;
    for i = 1:numel(hdr)
        line = string(hdr{i});
        if contains(line, 'SamplingFrequency','IgnoreCase',true) || contains(line,'SamplingFrequencyHz','IgnoreCase',true)
            m = regexp(line, '([\-+]?\d*\.?\d+(?:[eE][\-+]?\d+)?)', 'tokens', 'once');
            if ~isempty(m), f = str2double(m{1}); return; end
        end
    end
end
end
