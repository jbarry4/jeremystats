function EventStacks_AmpWidth(inputFolder, dataMatPath, varargin)

p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

% Data / channels / scaling (assumes µV in mf.d unless you pass a scale)
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);

% Alignment & windows
p.addParameter('align','peak', @(s) any(strcmpi(s,{'midpoint','peak'})));
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'})));
p.addParameter('halfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);      % default plotting window (overridden to 10 ms if align='peak')
p.addParameter('metricHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0); % ± window for amp/HW metrics

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
p.addParameter('yPadFrac', 0.10, @(x) isfinite(x) && x>=0 && x<=0.5);      % headroom

p.parse(inputFolder, dataMatPath, varargin{:});
inputFolder     = string(p.Results.inputFolder);
dataMatPath     = string(p.Results.dataMatPath);
channelIndices  = p.Results.channelIndices;
scaleToMicroV   = p.Results.scaleToMicroV;

alignMode       = lower(string(p.Results.align));
peakPolarity    = lower(string(p.Results.peakPolarity));
halfWidthMs     = p.Results.halfWidthMs;
metricHWms      = p.Results.metricHalfWidthMs;

excelPath       = string(p.Results.excelPath);
indexBase       = lower(string(p.Results.indexBase));
evtOffset       = p.Results.evtOffset;
maxEventsPerGrp = p.Results.maxEventsPerGroup;

saveDir         = string(p.Results.saveDir);
tagStr          = string(p.Results.tag);
yLimMicroV      = p.Results.yLimMicroV;
yRobustPct      = p.Results.yRobustPct;
yPadFrac        = p.Results.yPadFrac;

% --- Layout ---
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

% --- Data ---
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

if saveDir == "", outDir = inputFolder; else, outDir = char(saveDir); end
if ~exist(outDir,'dir'), mkdir(outDir); end

% --- Windows ---
% If aligning by peak, force display ±10 ms as requested.
if alignMode == "peak"
    halfWidthMs = 10e-3;      % force ±10 ms display/averaging
end
HWdisp   = max(1, round(halfWidthMs * sfx));   % averaging/plot window half-width (samples)
HWmet    = max(1, round(metricHWms  * sfx));   % metric window half-width (samples) (±5 ms default)
HWsearch = max(1, round(10e-3 * sfx));         % ±10 ms search for local peak around midpoint
tRelSamp = -HWdisp:HWdisp;
tRelMs   = (tRelSamp / sfx) * 1e3;
winN     = numel(tRelSamp);
centerIdx= HWdisp + 1;

fprintf('Avg SOLID/SPUTTER: sfx=%.1f Hz | display ±%.1f ms | metrics ±%.1f ms | align=%s\n', ...
        sfx, 1e3*HWdisp/sfx, 1e3*HWmet/sfx, alignMode);

% --- Spreadsheet -> samples ---
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

% --- Events from PNG names ---
evtSOL = unique(parseEvtNumsFromPngs(solidDir));
evtSPU = unique(parseEvtNumsFromPngs(sputterDir));
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));

if ~isempty(maxEventsPerGrp)
    evtSOL = evtSOL(1:min(end, maxEventsPerGrp));
    evtSPU = evtSPU(1:min(end, maxEventsPerGrp));
end

% --- Build group stats ---
[SOL, robSOL] = avgForGroup(evtSOL, 'SOLID');
[SPU, robSPU] = avgForGroup(evtSPU, 'SPUTTER');

% --- Global y-limit across BOTH figures ---
if isempty(yLimMicroV)
    rob = max([robSOL, robSPU, 1]);
    yMax = (1 + yPadFrac) * rob;
else
    yMax = yLimMicroV;
end
yL_global = [-yMax, +yMax];
fprintf('Global y-limit (both figs): ±%.1f µV (%s)\n', yMax, tern(isempty(yLimMicroV),'robust','fixed'));

% --- Plot & save (2 columns, with indicators on MEAN waveform) ---
plotStackWithIndicators(SOL, 'SOLID', yL_global);
plotStackWithIndicators(SPU, 'SPUTTER', yL_global);

fprintf('Done. Outputs in: %s\n', outDir);

% ===================== helpers =====================

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

function [G, robAll] = avgForGroup(evtList, tag)
% Per-channel aggregates:
%   MU (1×winN), SE (1×winN), nUsed, ampMean/SD, hwMean/SD (from per-event metrics)
% Also returns robAll = robust |signal| percentile for y-limit suggestion.
    G.MU  = nan(nCh, winN);
    G.SE  = nan(nCh, winN);
    G.n   = zeros(nCh,1);
    G.ampMean = nan(nCh,1); G.ampSD = nan(nCh,1);
    G.hwMean  = nan(nCh,1); G.hwSD  = nan(nCh,1);
    G.usedEvents = [];
    G.tRelMs = tRelMs; %#ok<STRNU>
    robAll = 0;

    if isempty(evtList)
        warning('%s: no events.', tag); return;
    end

    stacks = cell(nCh,1);   % per-event windows for averaging
    amps   = cell(nCh,1);   % per-event amplitudes (µV)
    hws    = cell(nCh,1);   % per-event half-widths (ms)
    for i=1:nCh, stacks{i} = []; amps{i} = []; hws{i} = []; end

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
        if ~isfinite(s0_ev) || ~isfinite(s1_ev) || s1_ev <= s0_ev, nBad=nBad+1; continue; end

        ancMid = round((s0_ev + s1_ev)/2);  % event midpoint

        okAnyCh = false;
        for k = 1:nCh
            ch = chList(k);
            sc = scaleToMicroV; if numel(sc)>1, sc = sc(ch); end

            % ---- Anchor selection ----
            if alignMode == "midpoint"
                anchor = ancMid;
            else
                % Search for local peak ONLY within ±10 ms around midpoint
                s0srch = max(1, ancMid - HWsearch);
                s1srch = min(nSamp, ancMid + HWsearch);
                yseg = double(mf.d(ch, s0srch:s1srch));
                if any(~isfinite(yseg)), continue; end
                switch peakPolarity
                    case "pos", [~, kp] = max(yseg);
                    case "neg", [~, kp] = min(yseg);
                    otherwise
                        [mx, iMax] = max(yseg);
                        [mn, iMin] = min(yseg);
                        if abs(mn) > abs(mx), kp = iMin; else, kp = iMax; end
                end
                anchor = s0srch + kp - 1;
            end

            % ---- Averaging/plot window (±10 ms when align='peak') ----
            s0 = anchor - HWdisp; s1 = anchor + HWdisp;
            if s0 < 1 || s1 > nSamp, continue; end
            y = double(mf.d(ch, s0:s1)) * sc;
            if any(~isfinite(y)), continue; end
            stacks{k}(end+1,:) = y; %#ok<AGROW>
            okAnyCh = true;

            % robust y-limit helper on display window
            p = prctile(abs(y), yRobustPct);
            if isfinite(p) && p > robAll, robAll = p; end

            % ---- Metrics window (±5 ms around anchor) ----
            s0m = max(1, anchor - HWmet);
            s1m = min(nSamp, anchor + HWmet);
            ym  = double(mf.d(ch, s0m:s1m)) * sc;
            if numel(ym) >= 3 && all(isfinite(ym))
                [mx, kMax] = max(ym);
                [mn, kMin] = min(ym);
                if abs(mn) > abs(mx)
                    sgn = -1; amp = abs(mn); pkRel = kMin;
                else
                    sgn = +1; amp = abs(mx); pkRel = kMax;
                end
                h = 0.5*amp; sig = sgn*ym;

                % left crossing
                kL = pkRel; while kL > 1 && sig(kL) >= h, kL = kL - 1; end
                if kL >= 1 && (kL+1) <= numel(sig)
                    left_ip = kL + (h - sig(kL)) / (sig(kL+1) - sig(kL));
                else, left_ip = NaN; end
                % right crossing
                kR = pkRel; L = numel(sig);
                while kR < L && sig(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= L
                    right_ip = (kR-1) + (h - sig(kR-1)) / (sig(kR) - sig(kR-1));
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
            if numel(G.usedEvents) <= 5
                fprintf('%s evt %d -> row %d | on=%d off=%d (%.2f ms)\n', ...
                    tag, e, rowXL, s0_ev, s1_ev, 1e3*(s1_ev - s0_ev + 1)/sfx);
            end
        end
    end

    if nBad>0, fprintf('%s: skipped %d event(s) (bad/missing/out-of-bounds).\n', tag, nBad); end
    fprintf('%s: used %d/%d events.\n', tag, numel(G.usedEvents), numel(evtList));

    % Aggregate per channel
    for k = 1:nCh
        X = stacks{k}; nUsed = size(X,1); G.n(k) = nUsed;
        if nUsed > 0
            G.MU(k,:) = mean(X, 1, 'omitnan');
            G.SE(k,:) = std( X, 0, 1, 'omitnan') ./ sqrt(nUsed); % SEM
        end
        a = amps{k}; w = hws{k};
        if ~isempty(a), G.ampMean(k) = mean(a, 'omitnan'); G.ampSD(k) = std(a, 0, 'omitnan'); end
        if ~isempty(w), G.hwMean(k)  = mean(w, 'omitnan'); G.hwSD(k)  = std(w,  0, 'omitnan'); end
    end

    % Save stats
    alignLabel = tern(alignMode=="midpoint","midpoint",sprintf('peak(local ±10ms, %s)',peakPolarity));
    statsPath = fullfile(outDir, sprintf('AvgStack_%s_stats.mat', tag));
    chList_local = chList; scale_local = scaleToMicroV; %#ok<NASGU>
    save(statsPath, 'tRelMs','chList_local','kept_channels','scale_local','halfWidthMs','metricHWms','sfx', ...
                    'alignLabel','G');
    fprintf('Saved: %s\n', statsPath);
end

function plotStackWithIndicators(G, tag, yL)
    if isempty(G) || all(all(isnan(G.MU))), warning('%s: no data to plot.', tag); return; end

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
        nexttile(tl); hold on; box on; grid on;

        if any(isfinite(mu))
            yu = mu + se; yl = mu - se;
            xp = [tRelMs, fliplr(tRelMs)];
            yp = [yu,      fliplr(yl)];
            patch('XData',xp,'YData',yp,'FaceColor',[0.3 0.3 0.9],'FaceAlpha',0.25,'EdgeColor','none','HandleVisibility','off');
            plot(tRelMs, mu, 'LineWidth', 1.8);

            % ---- Indicators computed on MEAN waveform within ±metric window ----
            muMet = mu(metStart:metEnd);
            if numel(muMet) >= 3 && all(isfinite(muMet))
                [mx, kMax] = max(muMet);
                [mn, kMin] = min(muMet);
                if abs(mn) > abs(mx)
                    sgn = -1; amp = abs(mn); pkRel = kMin;
                else
                    sgn = +1; amp = abs(mx); pkRel = kMax;
                end
                h = 0.5 * amp; sig = sgn * muMet;

                % left crossing
                kL = pkRel;
                while kL > 1 && sig(kL) >= h, kL = kL - 1; end
                if kL >= 1 && (kL+1) <= Lmet
                    left_ip = kL + (h - sig(kL)) / (sig(kL+1) - sig(kL));
                else
                    left_ip = NaN;
                end
                % right crossing
                kR = pkRel;
                while kR < Lmet && sig(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= Lmet
                    right_ip = (kR-1) + (h - sig(kR-1)) / (sig(kR) - sig(kR-1));
                else
                    right_ip = NaN;
                end

                if isfinite(left_ip) && isfinite(right_ip)
                    % convert fractional sample indices -> time (ms)
                    tPk_ms = ((metStart + pkRel - 1) - centerIdx) / sfx * 1e3;
                    tL_ms  = ((metStart + left_ip  - 1) - centerIdx) / sfx * 1e3;
                    tR_ms  = ((metStart + right_ip - 1) - centerIdx) / sfx * 1e3;

                    % vertical red half-width lines + red baseline segment
                    xline(tL_ms, '-', 'Color',[0.85 0.10 0.10], 'LineWidth',2.2, 'HandleVisibility','off');
                    xline(tR_ms, '-', 'Color',[0.85 0.10 0.10], 'LineWidth',2.2, 'HandleVisibility','off');
                    plot([tL_ms tR_ms],[0 0], '-', 'Color',[0.85 0.10 0.10], 'LineWidth',1.4, 'HandleVisibility','off');

                    % peak dot on mean curve
                    plot(tPk_ms, sgn*amp, 'o', 'MarkerSize', 4.5, ...
                         'MarkerFaceColor',[0 0 0], 'MarkerEdgeColor','none', 'HandleVisibility','off');
                end
            end
        end

        xline(0,'--k','LineWidth',0.9); yline(0,':','Color',[0.7 0.7 0.7]);
        ylim(yL);

        % Title (per-event stats mean±SD)
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
        title(ttlTxt, 'FontSize',9, 'FontWeight','normal');

        ax = gca; ax.FontSize = 8;
        if k <= nCh - nCols, ax.XTickLabel = []; else, xlabel('ms'); end
        ylabel('\muV');
    end

    alignLabel = tern(alignMode=="midpoint","midpoint",sprintf('peak(local ±10ms, %s)',peakPolarity));
    sg = sprintf('%s  |  align: %s  |  display: \\pm%.1f ms  |  metrics: \\pm%.1f ms  |  channels=%d  |  %s', ...
                 tag, alignLabel, 1e3*HWdisp/sfx, 1e3*HWmet/sfx, nCh, tagStr);
    sgtitle(tl, sg, 'FontSize',12,'FontWeight','bold');

    outPng = fullfile(outDir, sprintf('AvgStack_%s_align-%s_disp%ds_met%ds_globalY_2col.png', ...
        tag, regexprep(alignLabel,'[^a-zA-Z0-9]+','_'), HWdisp, HWmet));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved: %s\n', outPng);
end

function s = tern(cond, a, b)
    if cond, s = a; else, s = b; end
end

end
