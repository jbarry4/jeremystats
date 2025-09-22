function out = EventStacks_ampWidth_Avg_Pipeline(inputFolder, dataMatPath, varargin)
% EventStacks_ampWidth_Avg_Pipeline
% Pipeline-friendly version:
% - Can skip making its own PNGs (makeIndividualPNGs=false)
% - Can return traces for faint overlays (returnTraces=true)
% - Always returns structs you can render inside a master plot

% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

% Data / channels / scaling (assumes µV in mf.d unless you pass a scale)
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);

% Alignment & windows
p.addParameter('halfWidthMs',         10e-3, @(x)isfinite(x)&&x>0); % ±10 ms
p.addParameter('metricHalfWidthMs',    5e-3, @(x)isfinite(x)&&x>0); % ±5 ms
p.addParameter('anchorHalfWidthMs',    5e-3, @(x)isfinite(x)&&x>0); % ±5 ms

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

% NEW: master-plot options
p.addParameter('makeIndividualPNGs', true, @(x)islogical(x)||ismember(x,[0 1]));
p.addParameter('returnTraces',       false, @(x)islogical(x)||ismember(x,[0 1]));

p.parse(inputFolder, dataMatPath, varargin{:});
inputFolder       = string(p.Results.inputFolder);
dataMatPath       = string(p.Results.dataMatPath);
channelIndices    = p.Results.channelIndices;
scaleToMicroV     = p.Results.scaleToMicroV;

halfWidthMs       = p.Results.halfWidthMs;
metricHWms        = p.Results.metricHalfWidthMs;
anchorHWms        = p.Results.anchorHalfWidthMs;

excelPath         = string(p.Results.excelPath);
indexBase         = lower(string(p.Results.indexBase));
evtOffset         = p.Results.evtOffset;
maxEventsPerGrp   = p.Results.maxEventsPerGroup;

saveDirOpt        = string(p.Results.saveDir);
tagStr            = string(p.Results.tag);
yLimMicroV        = p.Results.yLimMicroV;
yRobustPct        = p.Results.yRobustPct;
yPadFrac          = p.Results.yPadFrac;

makePNGs          = logical(p.Results.makeIndividualPNGs);
returnTraces      = logical(p.Results.returnTraces);

% ---------------- Layout ----------------
solidDir   = fullfile(inputFolder, "Solid");
sputterDir = fullfile(inputFolder, "Sputter");
assert(isfolder(solidDir),   'Missing folder: %s', solidDir);
assert(isfolder(sputterDir), 'Missing folder: %s', sputterDir);

if excelPath == ""
    xl = dir(fullfile(inputFolder, "*.xlsx"));
    assert(~isempty(xl), 'No Excel file (*.xlsx) found in %s', inputFolder);
    excelPath = fullfile(xl(1).folder, xl(1).name);
end
assert(isfile(excelPath), 'Excel not found: %s', excelPath);

% ---------------- Data ----------------
assert(isfile(dataMatPath), 'Data MAT not found: %s', dataMatPath);
mf = matfile(dataMatPath);
try sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRowsAll = size(mf,'d',1);
nSamp    = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end %#ok<NASGU>

if isempty(channelIndices)
    chList = 1:nRowsAll;
else
    chList = channelIndices(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);

% Output dir (if we do save)
if saveDirOpt == ""
    outDir = fullfile(inputFolder, "EventStacks Output");
else
    outDir = fullfile(saveDirOpt, "EventStacks Output");
end
if makePNGs && ~exist(outDir,'dir'), mkdir(outDir); end

% ---------------- Windows ----------------
HWdisp    = max(1, round(halfWidthMs * sfx));      % ± display/averaging
HWmet     = max(1, round(metricHWms  * sfx));      % ± metrics
HWanchor  = max(1, round(anchorHWms  * sfx));      % ± anchor search (first channel)
tRelSamp  = -HWdisp:HWdisp;
tRelMs    = (tRelSamp / sfx) * 1e3;
winN      = numel(tRelSamp);
centerIdx = HWdisp + 1;

fprintf(['EventStacks_ampWidth_Avg_Pipeline: sfx=%.1f Hz | display ±%.1f ms | ' ...
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
    case "one"
        % no-op
end

NrowsXL = numel(onSamp);
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));

% ---------------- Events from PNG names ----------------
evtSOL = unique(parseEvtNumsFromPngs(solidDir));
evtSPU = unique(parseEvtNumsFromPngs(sputterDir));
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));

if ~isempty(maxEventsPerGrp)
    evtSOL = evtSOL(1:min(end, maxEventsPerGrp));
    evtSPU = evtSPU(1:min(end, maxEventsPerGrp));
end

% ---------------- Build group stats ----------------
[SOL, robSOL] = avgForGroup(evtSOL, 'SOLID');
[SPU, robSPU] = avgForGroup(evtSPU, 'SPUTTER');

% ---------------- Global y-limit across BOTH groups ----------------
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

% ---------------- Optionally save standalone PNGs ----------------
pngSOL = ""; pngSPU = "";
if makePNGs
    if ~isempty(SOL), pngSOL = plotStackWithIndicators(SOL, 'SOLID', yL_global, outDir); end
    if ~isempty(SPU), pngSPU = plotStackWithIndicators(SPU, 'SPUTTER', yL_global, outDir); end
    fprintf('Standalone EventStacks PNGs saved in: %s\n', outDir);
end

% ---------------- Package for pipeline return ----------------
out = struct;
out.module     = 'EventStacks_ampWidth_Avg';
out.inputDir   = inputFolder;
out.dataMat    = dataMatPath;
out.yMaxGlobal = yMax;
out.tRelMs     = tRelMs;
out.channelList = chList;
out.kept_channels = kept_channels;
out.groups  = [];

if ~isempty(SOL)
    out.groups(end+1) = packGroup('SOLID', SOL, pngSOL); %#ok<AGROW>
end
if ~isempty(SPU)
    out.groups(end+1) = packGroup('SPUTTER', SPU, pngSPU); %#ok<AGROW>
end

% If the main wants faint overlays, include traces (heavy) now
if returnTraces
    if ~isempty(SOL), out.groups(strcmp({out.groups.tag},'SOLID')).traces = SOL.traces; end
    if ~isempty(SPU), out.groups(strcmp({out.groups.tag},'SPUTTER')).traces = SPU.traces; end
end

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
    G.MU  = nan(nCh, winN);
    G.SE  = nan(nCh, winN);
    G.n   = zeros(nCh,1);
    G.ampMean = nan(nCh,1); G.ampSD = nan(nCh,1);
    G.hwMean  = nan(nCh,1); G.hwSD  = nan(nCh,1);
    G.usedEvents = [];
    G.tRelMs = tRelMs; %#ok<STRNU>
    G.traces = cell(nCh,1);  % keep contributing traces (used only if returnTraces=true)
    robAll = 0;

    if isempty(evtList)
        warning('%s: no events.', tag); return;
    end

    refCh = chList(1);
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

        ancMid = round((s0_ev + s1_ev)/2);  % event midpoint

        % Anchor: FIRST channel positive peak
        s0srch = max(1, ancMid - HWanchor);
        s1srch = min(nSamp, ancMid + HWanchor);
        yseg0  = double(mf.d(refCh, s0srch:s1srch)) * scaleToMicroV;
        if isempty(yseg0) || all(~isfinite(yseg0)), nBad=nBad+1; continue; end
        [~, k_rel] = max(yseg0);
        commonAnchor = s0srch + k_rel - 1;

        okAnyCh = false;
        for k = 1:nCh
            ch = chList(k);
            sc = scaleToMicroV; if numel(sc)>1, sc = sc(ch); end

            s0 = commonAnchor - HWdisp; s1 = commonAnchor + HWdisp;
            if s0 < 1 || s1 > nSamp, continue; end
            y = double(mf.d(ch, s0:s1)) * sc;
            if any(~isfinite(y)), continue; end

            % collect trace (for mean/SEM; and optionally for overlays)
            G.traces{k}(end+1,:) = y; %#ok<AGROW>
            okAnyCh = true;

            % robust helper for global y-limit
            yy = y(isfinite(y));
            if ~isempty(yy)
                p = prctile(abs(yy), yRobustPct);
                if isfinite(p) && p > robAll, robAll = p; end
            end

            % Metrics in ±metric window (positive peak)
            s0m = max(1, commonAnchor - HWmet);
            s1m = min(nSamp, commonAnchor + HWmet);
            ym  = double(mf.d(ch, s0m:s1m)) * sc;
            if numel(ym) >= 3 && all(isfinite(ym))
                [amp, pkRel] = max(ym);
                h = 0.5 * amp;

                % Left crossing
                kL = pkRel;
                while kL > 1 && ym(kL) >= h, kL = kL - 1; end
                if kL >= 1 && (kL+1) <= numel(ym) && ym(kL) < h && ym(kL+1) >= h
                    left_ip = kL + (h - ym(kL)) / (ym(kL+1) - ym(kL)); else, left_ip = NaN; end

                % Right crossing
                kR = pkRel; Lm = numel(ym);
                while kR < Lm && ym(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= Lm && ym(kR-1) >= h && ym(kR) < h
                    right_ip = (kR-1) + (h - ym(kR-1)) / (ym(kR) - ym(kR-1)); else, right_ip = NaN; end

                if isfinite(left_ip) && isfinite(right_ip) && right_ip > left_ip
                    hw_ms = (right_ip - left_ip) / sfx * 1e3;
                else, hw_ms = NaN; end
                G.ampMean(k, end+1) = amp; %#ok<AGROW>
                G.hwMean(k,  end+1) = hw_ms; %#ok<AGROW>
            else
                G.ampMean(k, end+1) = NaN; %#ok<AGROW>
                G.hwMean(k,  end+1) = NaN; %#ok<AGROW>
            end
        end

        if okAnyCh, G.usedEvents(end+1) = e; end %#ok<AGROW>
    end

    % Collapse metrics & compute MU/SE
    if isfield(G,'ampMean')
        G.ampSD = nan(nCh,1); G.hwSD = nan(nCh,1);
        for k=1:nCh
            a = G.ampMean(k,:); w = G.hwMean(k,:);
            G.ampSD(k) = std(a, 0, 'omitnan');
            G.hwSD(k)  = std(w, 0, 'omitnan');
            G.ampMean(k) = mean(a, 'omitnan');
            G.hwMean(k)  = mean(w, 'omitnan');
        end
    else
        G.ampMean = nan(nCh,1); G.ampSD = nan(nCh,1);
        G.hwMean  = nan(nCh,1); G.hwSD  = nan(nCh,1);
    end

    for k = 1:nCh
        X = G.traces{k};
        nUsed = size(X,1);
        G.n(k) = nUsed;
        if nUsed > 0
            G.MU(k,:) = mean(X, 1, 'omitnan');
            G.SE(k,:) = std( X, 0, 1, 'omitnan') ./ max(1,sqrt(nUsed));
        end
    end

    fprintf('%s: used %d/%d events. Skipped=%d.\n', tag, numel(G.usedEvents), numel(evtList), nBad);
    G.nEventsUsed = numel(G.usedEvents);

    % If traces are *not* requested by the main, drop them to save memory
    if ~returnTraces
        G = rmfield(G, 'traces');
    end
end

function pngPath = plotStackWithIndicators(G, tag, yL, outRoot)
    if isempty(G) || all(all(isnan(G.MU))), warning('%s: no data to plot.', tag); pngPath=""; return; end

    % ---- compact rendering omitted here for brevity ----
    % (unchanged from your previous version; keeps faint overlays, etc.)

    % For pipeline: still save if requested
    perRowPx = 120; basePx = 220; maxPx = 5200;
    figH = min(maxPx, basePx + perRowPx * size(G.MU,1));
    f = figure('Color','w','Position',[60 60 1100 figH],'Visible','off');
    tl = tiledlayout(f, ceil(size(G.MU,1)/2), 2, 'Padding','compact','TileSpacing','compact');

    % (Plotting body omitted… use your existing block.)

    pngPath = fullfile(outRoot, sprintf('AvgStack_%s.png', tag));
    exportgraphics(f, pngPath, 'Resolution', 220);
    close(f);
end

function S = tern(cond, a, b), if cond, S = a; else, S = b; end, end

function Gout = packGroup(tag, G, pngPath)
    Gout = struct;
    Gout.tag         = tag;
    Gout.pngPath     = string(pngPath);
    Gout.nEventsUsed = G.nEventsUsed;
    Gout.tRelMs      = G.tRelMs;
    Gout.ampMean     = G.ampMean;
    Gout.ampSD       = G.ampSD;
    Gout.hwMean      = G.hwMean;
    Gout.hwSD        = G.hwSD;
    Gout.MU          = G.MU;
    Gout.SE          = G.SE;
    Gout.n           = G.n;
end

end
