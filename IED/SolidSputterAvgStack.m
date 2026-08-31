function SolidSputterAvgStack(inputFolder, dataMatPath, varargin)

p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('halfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);
p.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'})));
p.addParameter('align','midpoint', @(s) any(strcmpi(s,{'peak','midpoint'})));  % default: preserve temporality
p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('saveDir',"", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('evtOffset', 0, @(x)isscalar(x)&&isfinite(x));      % set to +1 only if your sheet is shifted
p.addParameter('indexBase', 'auto', @(s) any(strcmpi(s,{'auto','zero','one'}))); % spreadsheet sample indices base
p.parse(inputFolder, dataMatPath, varargin{:});

inputFolder     = string(p.Results.inputFolder);
dataMatPath     = string(p.Results.dataMatPath);
halfWidthMs     = p.Results.halfWidthMs;
scaleToMicroV   = p.Results.scaleToMicroV;
peakPolarity    = lower(string(p.Results.peakPolarity));
alignMode       = lower(string(p.Results.align));
excelPath       = string(p.Results.excelPath);
saveDir         = string(p.Results.saveDir);
channelIndices  = p.Results.channelIndices;
maxEventsPerGrp = p.Results.maxEventsPerGroup;
evtOffset       = p.Results.evtOffset;
indexBase       = lower(string(p.Results.indexBase));

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

assert(isfile(dataMatPath), 'Data MAT not found: %s', dataMatPath);
mf = matfile(dataMatPath);
try sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRowsAll = size(mf,'d',1);
nSamp    = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end

if isempty(channelIndices)
    chList = 1:nRowsAll;
else
    chList = channelIndices(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);

if saveDir == "", outDir = inputFolder; else, outDir = char(saveDir); end
if ~exist(outDir,'dir'), mkdir(outDir); end

HW = max(1, round(halfWidthMs * sfx));
tRelSamples = -HW:HW;
tRelMs = (tRelSamples / sfx) * 1e3;
winN = numel(tRelSamples);

% ----- Read & normalize spreadsheet to sample indices -----
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
    if width(T) < 2, error('Excel must have [on_samp, off_samp] or [on_sec, off_sec].'); end
    onSamp  = double(T{:,1});
    offSamp = double(T{:,2});
end

switch indexBase
    case "zero"
        onSamp  = onSamp + 1; offSamp = offSamp + 1;
    case "auto"
        if any(onSamp < 1 | offSamp < 1 | onSamp==0 | offSamp==0)
            onSamp  = onSamp + 1; offSamp = offSamp + 1;
        end
    case "one"
        % no-op
end

NrowsXL = numel(onSamp);
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));

% ----- Event lists from PNG names -----
evtSOL = unique(parseEvtNumsFromPngs(solidDir));
evtSPU = unique(parseEvtNumsFromPngs(sputterDir));
fprintf('Found %d SOLID events, %d SPUTTER events from filenames.\n', numel(evtSOL), numel(evtSPU));
if ~isempty(maxEventsPerGrp)
    evtSOL = evtSOL(1:min(end, maxEventsPerGrp));
    evtSPU = evtSPU(1:min(end, maxEventsPerGrp));
end

[muSOL, seSOL, usedSOL] = avgForGroup(evtSOL, 'SOLID');
[muSPU, seSPU, usedSPU] = avgForGroup(evtSPU, 'SPUTTER');

alignLabel = tern(alignMode=="midpoint","midpoint",sprintf('peak(%s)',peakPolarity));
plotStack(muSOL, seSOL, 'SOLID', usedSOL, alignLabel);
plotStack(muSPU, seSPU, 'SPUTTER', usedSPU, alignLabel);

fprintf('Done. Outputs in: %s\n', outDir);

% ---------- helpers ----------
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
    end

    function [MU, SE, usedEvents] = avgForGroup(evtList, tag)
        if isempty(evtList)
            MU = []; SE = []; usedEvents = [];
            warning('%s: no events.', tag);
            return;
        end

        MU = nan(nCh, winN);
        SE = nan(nCh, winN);
        usedEvents = [];
        stacks = cell(nCh,1);
        for i=1:nCh, stacks{i} = []; end

        nBad = 0;
        for ii = 1:numel(evtList)
            e = evtList(ii);

            % map event -> spreadsheet row
            rowXL = e + evtOffset;
            if rowXL < 1 || rowXL > NrowsXL
                alt = e;
                if alt >= 1 && alt <= NrowsXL
                    rowXL = alt;
                else
                    nBad = nBad + 1; 
                    continue;
                end
            end

            s0_ev = max(1, round(onSamp(rowXL)));
            s1_ev = min(nSamp, round(offSamp(rowXL)));
            if ~isfinite(s0_ev) || ~isfinite(s1_ev) || s1_ev <= s0_ev
                nBad = nBad + 1; 
                continue;
            end

            if alignMode == "midpoint"
                anchorMid = round((s0_ev + s1_ev)/2);
            end

            okAnyCh = false;
            for k = 1:nCh
                ch = chList(k);

                if alignMode == "midpoint"
                    anchor = anchorMid;   % same anchor for all channels (preserve temporality)
                else
                    yseg = double(mf.d(ch, s0_ev:s1_ev));
                    if any(~isfinite(yseg)), continue; end
                    switch peakPolarity
                        case "pos", [~, kp] = max(yseg);
                        case "neg", [~, kp] = min(yseg);
                        otherwise,  [~, kp] = max(abs(yseg));
                    end
                    anchor = s0_ev + kp - 1;
                end

                s0 = anchor - HW; s1 = anchor + HW;
                if s0 < 1 || s1 > nSamp, continue; end

                y = double(mf.d(ch, s0:s1)) * scaleToMicroV; % µV
                if any(~isfinite(y)), continue; end

                stacks{k}(end+1, :) = y; %#ok<AGROW>
                okAnyCh = true;
            end

            if okAnyCh
                usedEvents(end+1) = e; %#ok<AGROW>
                if numel(usedEvents) <= 5
                    fprintf('%s evt %d -> row %d | on=%d off=%d (len=%d samp, %.2f ms)%s\n', ...
                        tag, e, rowXL, s0_ev, s1_ev, s1_ev - s0_ev + 1, 1e3*(s1_ev - s0_ev + 1)/sfx, ...
                        tern(alignMode=="midpoint", sprintf(' | anchorMid=%d', anchorMid), ''));
                end
            end
        end

        if nBad>0
            fprintf('%s: skipped %d event(s) due to bad/missing indices/out-of-bounds.\n', tag, nBad);
        end
        fprintf('%s: used %d/%d events.\n', tag, numel(usedEvents), numel(evtList));

        for k = 1:nCh
            nUsedCh = size(stacks{k},1);
            if nUsedCh > 0
                MU(k,:) = mean(stacks{k}, 1, 'omitnan');
                SE(k,:) = std(stacks{k}, 0, 1, 'omitnan') ./ sqrt(nUsedCh);
            end
        end
    end

    function plotStack(MU, SE, tag, usedEvents, alignLabel)
        if isempty(MU)
            warning('%s: no data to plot.', tag);
            return;
        end
        maxAbs = max(abs([MU(:); (MU(:)+SE(:)); (MU(:)-SE(:))]), [], 'omitnan');
        if ~isfinite(maxAbs) || maxAbs==0, maxAbs = 1; end
        pad = 0.05;
        span = (1+pad) * maxAbs;
        yL = span * [-1 1];

        nRowsGrid = nCh;
        perRowPx = 90; basePx = 200; maxPx = 5000;
        figH = min(maxPx, basePx + perRowPx * nRowsGrid);
        f = figure('Color','w','Position',[60 60 900 figH],'Visible','off');
        tl = tiledlayout(f, nRowsGrid, 1, 'Padding','compact','TileSpacing','compact');

        for k = 1:nCh
            nexttile(tl); hold on; box on; grid on;
            mu = MU(k,:); se = SE(k,:);
            if any(isfinite(mu))
                shadedMean(tRelMs, mu, se);
                xline(0,'--k','LineWidth',0.8); yline(0,':','Color',[0.7 0.7 0.7]);
            end
            ylim(yL);
            ch = chList(k);
            title(localTitle(ch, kept_channels),'FontSize',8);
            ax = gca; ax.FontSize = 8;
            if k < nCh, ax.XTickLabel = []; else, xlabel('ms'); end
            ylabel('\muV');
        end

        sg = sprintf('%s | align: %s | Win: \\pm%.1f ms | nEvents=%d | yLim=\\pm%.1f \\muV', ...
            tag, alignLabel, 1e3*HW/sfx, numel(usedEvents), (1+pad)*maxAbs);
        sgtitle(tl, sg, 'FontSize',12,'FontWeight','bold');

        alignTag = regexprep(alignLabel, '[^a-zA-Z0-9]+','_');
        outPng = fullfile(outDir, sprintf('AvgStack_%s_align-%s_HW%ds_%dms_rows-only_uV_fixedY.png', ...
            tag, alignTag, HW, round(1e3*HW/sfx)));
        exportgraphics(f, outPng, 'Resolution', 220);
        close(f);

        statsPath = fullfile(outDir, sprintf('AvgStack_%s_stats.mat', tag));
        save(statsPath, 'MU','SE','tRelMs','chList','kept_channels','scaleToMicroV','halfWidthMs','sfx','alignLabel','usedEvents');
        fprintf('Saved: %s\n', outPng);
        fprintf('Saved: %s\n', statsPath);
    end

    function shadedMean(x, mu, se)
        if isempty(mu) || all(~isfinite(mu)), return; end
        yu = mu + se; yl = mu - se;
        xp = [x, fliplr(x)];
        yp = [yu, fliplr(yl)];
        patch('XData',xp,'YData',yp,'FaceColor',[0.3 0.3 0.9],'FaceAlpha',0.25,'EdgeColor','none','HandleVisibility','off');
        plot(x, mu, 'LineWidth', 1.8);
    end

    function s = tern(cond, a, b)
        if cond, s = a; else, s = b; end
    end

    function ttl = localTitle(rowIdx, kept)
        if ~isempty(kept)
            ttl = sprintf('row %d (CSC%d)', rowIdx, kept(rowIdx));
        else
            ttl = sprintf('row %d', rowIdx);
        end
    end

end
