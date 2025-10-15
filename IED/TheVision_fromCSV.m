function TheVision_fromCSV(recDir, csvPath, varargin)
% Plot per-event stacks from CSC*.ncs using ONLY windows in CSV.
% Supports:
%   A) channels column is "2,4,8"
%   B) channels column is numeric; extra numeric columns hold CSC IDs.

% ---------- Parse ----------
p = inputParser;
p.addRequired('recDir', @(s)ischar(s)||isstring(s));
p.addRequired('csvPath', @(s)ischar(s)||isstring(s));
p.addParameter('halfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);
p.addParameter('align','midpoint', @(s)any(strcmpi(s,{'midpoint','peak'})));
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'})));
p.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);
p.addParameter('scaleToMV', [], @(x)isempty(x)||(isfinite(x)&&x>0));
p.addParameter('saveDir','', @(s)ischar(s)||isstring(s));
p.addParameter('minCh', 6, @(x)isfinite(x)&&x>=0);
p.addParameter('maxCh', 8, @(x)isfinite(x)&&x>=0);
p.parse(recDir, csvPath, varargin{:});

recDir        = string(p.Results.recDir);
csvPath       = string(p.Results.csvPath);
halfWidthMs   = p.Results.halfWidthMs;
alignMode     = lower(string(p.Results.align));
peakPolarity  = lower(string(p.Results.peakPolarity));
scaleToMicroV = p.Results.scaleToMicroV;
scaleToMV     = p.Results.scaleToMV;
saveDir       = string(p.Results.saveDir);
minCh         = p.Results.minCh;
maxCh         = p.Results.maxCh;

if ~isempty(scaleToMV)
    scaleToMicroV = scaleToMV * 1000;
    warning('TheVision:DeprecatedArg','''scaleToMV'' deprecated. Using scaleToMicroV=%g.',scaleToMicroV);
end
if ~isfile(csvPath), error('CSV not found: %s', csvPath); end

% ---------- CSC discovery (even channels, sorted) ----------
files = dir(fullfile(recDir, 'CSC*.ncs'));
if isempty(files), error('No CSC*.ncs in %s', recDir); end
nums  = cellfun(@(s) sscanf(s,'CSC%d.ncs'), {files.name});
keep  = mod(nums,2)==0 & ~isnan(nums);
files = files(keep); nums = nums(keep);
[nums,ix] = sort(nums,'ascend'); files=files(ix);
cscNums = nums(:)'; nChan = numel(cscNums);

% ---------- sample rate ----------
FsVec = Nlx2MatCSC(fullfile(files(1).folder, files(1).name), [0 0 1 0 0], 0, 1, []);
if isempty(FsVec), error('Could not read sampling frequency from %s', files(1).name); end
sfx = double(FsVec(1));
fprintf('[info] sfx = %g Hz (from %s)\n', sfx, files(1).name);

% ---------- load CSV ----------
T = readtable(csvPath, 'TextType', 'string');

needCols = {'sample_start','sample_end'};
for k=1:numel(needCols)
    if ~ismember(needCols{k}, T.Properties.VariableNames)
        error('CSV missing required column: %s', needCols{k});
    end
end
sample_start = double(T.sample_start);
sample_end   = double(T.sample_end);

% Determine channel list format
hasChanCol = ismember('channels', T.Properties.VariableNames);
chanIsStringList = false;
if hasChanCol
    chVar = T.channels;
    if isstring(chVar) || ischar(chVar)
        % if any row has separators, treat as list
        idx = find(chVar~="",1,'first');
        if ~isempty(idx)
            ex = chVar(idx);
            chanIsStringList = contains(ex,["," " " ";"]);
        end
    elseif iscell(chVar)
        % cellstr or mixed — treat as string list if any entry has a separator
        idx = find(~cellfun(@(x) isempty(x) || (isstring(x)&&x==""), chVar),1,'first');
        if ~isempty(idx)
            val = chVar{idx};
            if isstring(val) || ischar(val)
                chanIsStringList = contains(string(val),["," " " ";"]);
            end
        end
    else
        % numeric => not a string list
        chanIsStringList = false;
    end
end

% Collect extra numeric columns that may hold CSC IDs per row
cand = setdiff(T.Properties.VariableNames, {'sample_start','sample_end','time_start_s','time_end_s','channels'});
extraCols = {};
for i=1:numel(cand)
    v = T.(cand{i});
    if isnumeric(v)
        extraCols{end+1} = cand{i}; %#ok<AGROW>
    end
end
chanIsNumericWithExtras = (~chanIsStringList) && ~isempty(extraCols);

% function to get active CSC list for row r
    function v = get_active_list(r)
        if chanIsStringList
            v = parse_chan_list(T.channels(r)); % vector of CSC IDs
        elseif chanIsNumericWithExtras
            tmp = [];
            for c = 1:numel(extraCols)
                val = T.(extraCols{c})(r);
                if ~isnan(val), tmp(end+1) = double(val); end %#ok<AGROW>
            end
            v = unique(tmp);
        else
            % fallback: if channels is numeric and no extras, treat as single CSC id
            if hasChanCol && isnumeric(T.channels) && ~isnan(T.channels(r))
                v = double(T.channels(r));
            else
                v = [];
            end
        end
        % keep only CSCs we actually have (even channels)
        if ~isempty(v)
            v = v(ismember(v, cscNums));
        end
    end

% filter events by #active channels
actCounts = zeros(height(T),1);
for i=1:height(T), actCounts(i) = numel(get_active_list(i)); end
keepEvt = (actCounts>=minCh) & (actCounts<=maxCh);
evtIdx  = find(keepEvt);

if isempty(evtIdx)
    fprintf('No events within %d–%d channels.\n', minCh, maxCh);
    return;
end

% ---------- output dir ----------
outDir = saveDir;
if outDir=="" || ~isfolder(outDir), outDir = recDir; end
fprintf('[info] will save PNGs to: %s\n', outDir);

% ---------- constants ----------
HW   = max(1, round(halfWidthMs * sfx));
REC  = 512; % samples per CSC record

% ---------- iterate events ----------
for eii = 1:numel(evtIdx)
    e = evtIdx(eii);
    evS = max(1, sample_start(e));
    evE = sample_end(e);
    if evE <= evS, fprintf('Evt %d skipped (empty window)\n', e); continue; end

    activeList   = get_active_list(e);                  % CSC numbers
    activeMaskCS = ismember(cscNums, activeList);       % 1 x nChan

    % anchor selection
    switch alignMode
        case "midpoint"
            anchor = round((evS + evE)/2);
            s0 = max(1, anchor - HW); s1 = anchor + HW;

            winLen = s1 - s0 + 1;
            Y = nan(nChan, winLen, 'double'); usedRows = false(1,nChan);
            for k = 1:nChan
                y = read_csc_samples(files(k), s0, s1, REC);
                if isempty(y), continue; end
                Y(k,:) = double(y) * scaleToMicroV;
                usedRows(k) = all(isfinite(Y(k,:)));
            end
            usedIdx = find(usedRows);
            if isempty(usedIdx)
                fprintf('Evt %d: no valid channels, skip.\n', e); continue;
            end

        otherwise % 'peak' (per-channel)
            rows = {}; usedIdx = [];
            for k = 1:nChan
                yRaw = read_csc_samples(files(k), evS, evE, REC);
                if isempty(yRaw), continue; end
                switch peakPolarity
                    case 'pos', [~,kp] = max(yRaw);
                    case 'neg', [~,kp] = min(yRaw);
                    otherwise,  [~,kp] = max(abs(yRaw));
                end
                a = evS + kp - 1;
                s0k = max(1, a - HW); s1k = a + HW;
                yWin = read_csc_samples(files(k), s0k, s1k, REC);
                if numel(yWin) ~= (s1k - s0k + 1), continue; end
                rows{end+1} = double(yWin) * scaleToMicroV; %#ok<AGROW>
                usedIdx(end+1) = k; %#ok<AGROW>
            end
            if isempty(rows)
                fprintf('Evt %d: no valid channels (peak align), skip.\n', e); continue;
            end
            Y = cell2mat(rows(:));
            s0 = -HW; s1 = +HW; % relative for labels
    end

    % time & y-lims
    tRelSmps = -HW:HW; tRelMs = (tRelSmps / sfx) * 1e3;
    maxAbs = max(abs(Y(:))); if ~isfinite(maxAbs)||maxAbs==0, maxAbs=1; end
    span = 1.05*maxAbs; yL = [-span, +span];

    % figure
    nUsed = size(Y,1);
    perRowPx = 90; basePx = 200; maxPx = 5000;
    figH = min(maxPx, basePx + perRowPx*nUsed);
    f = figure('Color','w','Position',[60 60 900 figH],'Visible','off');
    tl = tiledlayout(f, nUsed, 1, 'Padding','compact', 'TileSpacing','compact');

    for r = 1:nUsed
        k = usedIdx(r);
        nexttile(tl); hold on; box on; grid on;

        isActive = activeMaskCS(k);
        if isActive, lw=1.4; col=[0 0 0]; else, lw=0.7; col=[0.5 0.5 0.5]; end

        plot(tRelMs, Y(r,:), 'LineWidth', lw, 'Color', col);
        xline(0,'--k','LineWidth',0.8); yline(0,':','Color',[0.7 0.7 0.7]);
        ylim(yL);

        ttl = sprintf('row %d (CSC%d)%s', k, cscNums(k), tern(isActive,' *',''));
        title(ttl,'FontSize',8);

        ax=gca; ax.FontSize=8;
        if r<nUsed, ax.XTickLabel=[]; else, xlabel('ms'); end
        ylabel('\muV');
    end

    nActive = sum(activeMaskCS);
    sgtitle(tl, sprintf('Evt %d  |  Active %d  |  Align: %s  |  Win ±%.1f ms  |  sfx=%g Hz', ...
        e, nActive, alignMode, 1e3*HW/sfx, sfx), ...
        'FontSize', 12, 'FontWeight', 'bold');

    outPng = fullfile(outDir, sprintf('Evt%03d_%dch_align-%s_HW%ds_rows-only_uV_fixedY.png', ...
                    e, nActive, alignMode, HW));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved: %s\n', outPng);
end

fprintf('Done. Output dir: %s\n', outDir);
end

% ================= helpers =================

function y = read_csc_samples(fileRec, s0, s1, REC)
if s1 < s0, y = []; return; end
rec0 = floor((s0-1)/REC) + 1;
rec1 = floor((s1-1)/REC) + 1;
S = Nlx2MatCSC(fullfile(fileRec.folder, fileRec.name), [0 0 0 0 1], 0, 2, [rec0 rec1]);
if isempty(S), y = []; return; end
v = S(:)';  % flatten
off0 = s0 - ((rec0-1)*REC + 1);
off1 = s1 - ((rec0-1)*REC + 1);
i0 = max(0, off0); i1 = min(numel(v)-1, off1);
if i1 < i0, y = []; else, y = v(i0+1:i1+1); end
end

function out = tern(cond, a, b)
if cond, out=a; else, out=b; end
end

function v = parse_chan_list(s)
% Parse "2,4,6" or "2 4 6" -> [2 4 6]
s = string(s);
if strlength(s)==0, v=[]; return; end
s = regexprep(s,'[\[\]\(\)]','');
s = strrep(s,';',',');
parts = split(strtrim(s), {',',' '});
parts = parts(parts~="");
v = str2double(parts); v = v(~isnan(v));
end
