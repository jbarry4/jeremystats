function TheVision_fromCSV(recDir, csvPath, varargin)
% TheVision_fromCSV
% Plot per-event multi-channel stacks from Neuralynx CSC*.ncs using ONLY
% the windows listed in events_summary.csv (no full conversion).
%
% Inputs:
%   recDir   : folder containing CSC*.ncs (even channels as in your pipeline)
%   csvPath  : events_summary.csv (cols: sample_start,sample_end,time_start_s,time_end_s,channels)
%
% Name-Value options (defaults match your prior TheVision):
%   'halfWidthMs'    (double) default 30e-3   % 30 ms half-window
%   'align'          ('midpoint'|'peak') default 'midpoint'
%   'peakPolarity'   ('abs'|'pos'|'neg') default 'abs'
%   'scaleToMicroV'  (double) default 1       % multiply AD counts -> µV
%   'scaleToMV'      (double) default []      % DEPRECATED; overrides scaleToMicroV = *1000
%   'saveDir'        (string/char) default: recDir
%   'minCh'          (int) default 6          % filter by #active channels (inclusive)
%   'maxCh'          (int) default 8
%
% Notes:
% - Determines sample rate (sfx) from the first CSC via Nlx2MatCSC.
% - Uses record-index extraction (mode=2) and trims to exact sample range.
% - Active channels parsed from CSV "channels" column (list of CSC numbers).
% - Plots ALL available even CSCs in one column; active channels are bold.

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
scaleToMV     = p.Results.scaleToMV; % deprecated
saveDir       = string(p.Results.saveDir);
minCh         = p.Results.minCh;
maxCh         = p.Results.maxCh;

if ~isempty(scaleToMV)
    scaleToMicroV = scaleToMV * 1000; % mV -> µV
    warning('TheVision:DeprecatedArg', ...
        '''scaleToMV'' is deprecated. Using scaleToMicroV = %g (mV*1000).', scaleToMicroV);
end

if ~isfile(csvPath), error('CSV not found: %s', csvPath); end

% ---------- Discover CSC files (even channels, sorted) ----------
files = dir(fullfile(recDir, 'CSC*.ncs'));
if isempty(files), error('No CSC*.ncs in %s', recDir); end
nums  = cellfun(@(s) sscanf(s,'CSC%d.ncs'), {files.name});
keep  = mod(nums,2)==0 & ~isnan(nums);
files = files(keep); nums = nums(keep);
[nums,ix] = sort(nums,'ascend'); files=files(ix);

% Map: row index -> CSC number and filename
cscNums = nums(:)'; nChan = numel(cscNums);

% ---------- Determine sample rate from first file ----------
% Nlx2MatCSC(File,[TS,Ch,Fs,NValid,Samples],HdrFlag,ExtractMode,Vector)
[~, ~, FsVec] = Nlx2MatCSC(fullfile(files(1).folder, files(1).name), [0 0 1 0 0], 0, 1, []);
if isempty(FsVec), error('Could not read sampling frequency from first CSC.'); end
sfx = double(FsVec(1));
fprintf('[info] sfx = %g Hz (from %s)\n', sfx, files(1).name);

% ---------- Load CSV ----------
T = readtable(csvPath, 'TextType', 'string');
needCols = {'sample_start','sample_end','channels'};
for c = needCols
    if ~ismember(c{1}, T.Properties.VariableNames)
        error('CSV missing required column: %s', c{1});
    end
end
sample_start = double(T.sample_start);
sample_end   = double(T.sample_end);
chanStrs     = string(T.channels);

% filter by active channel count (minCh..maxCh)
actCounts = arrayfun(@(i) numel(str2num_safe(chanStrs(i))), (1:height(T))'); %#ok<ST2NM>
keepEvt   = (actCounts>=minCh) & (actCounts<=maxCh);
evtIdx    = find(keepEvt);

if isempty(evtIdx)
    fprintf('No events within %d–%d channels.\n', minCh, maxCh);
    return;
end

% ---------- Output dir ----------
outDir = saveDir;
if outDir=="" || ~isfolder(outDir), outDir = recDir; end
fprintf('[info] will save PNGs to: %s\n', outDir);

% ---------- Constants ----------
HW   = max(1, round(halfWidthMs * sfx));
REC  = 512; % Neuralynx CSC block size (samples per record)

% ---------- Iterate events ----------
for eii = 1:numel(evtIdx)
    e = evtIdx(eii);
    evS = max(1, sample_start(e));
    evE = sample_end(e);
    if evE <= evS, fprintf('Evt %d skipped (empty window)\n', e); continue; end

    % Active CSC numbers for this event (from CSV)
    activeList = str2num_safe(chanStrs(e));        % vector of CSC numbers (e.g., [2 6 8 ...])
    activeMaskCSC = ismember(cscNums, activeList);  % 1 x nChan

    % Choose anchor
    switch alignMode
        case "midpoint"
            anchor = round((evS + evE)/2);
            s0 = anchor - HW; s1 = anchor + HW;
            if s0 < 1, s0=1; end
        otherwise % 'peak' — per-channel peak within [evS..evE]
            s0 = evS; s1 = evE; % we’ll refine per channel below
    end

    % ---------- Read window data from each CSC (only necessary records) ----------
    % Prepare container
    if alignMode=="midpoint"
        winLen = s1 - s0 + 1;
        Y = nan(nChan, winLen, 'double');
        usedRows = false(1, nChan);
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

    else % align == 'peak' (per-channel)
        rows = {}; usedIdx = [];
        for k = 1:nChan
            yRaw = read_csc_samples(files(k), evS, evE, REC);
            if isempty(yRaw), continue; end
            % pick peak index in event window
            switch peakPolarity
                case 'pos', [~,kp] = max(yRaw);
                case 'neg', [~,kp] = min(yRaw);
                otherwise,  [~,kp] = max(abs(yRaw));
            end
            a = evS + kp - 1;
            s0k = a - HW; s1k = a + HW;
            if s0k < 1, s0k = 1; end
            yWin = read_csc_samples(files(k), s0k, s1k, REC);
            if numel(yWin) ~= (s1k - s0k + 1), continue; end
            rows{end+1} = double(yWin) * scaleToMicroV; %#ok<AGROW>
            usedIdx(end+1) = k; %#ok<AGROW>
        end
        if isempty(rows)
            fprintf('Evt %d: no valid channels (peak align), skip.\n', e); continue;
        end
        % unify (each row already centered on its own anchor)
        Y = cell2mat(rows(:));
        s0 = -HW; s1 = +HW; % for labeling only (relative time)
    end

    % ---------- Build styles and fixed y-limits ----------
    tRelSmps = -HW:HW;
    tRelMs   = (tRelSmps / sfx) * 1e3;
    maxAbs = max(abs(Y(:))); if ~isfinite(maxAbs)||maxAbs==0, maxAbs=1; end
    span = 1.05*maxAbs; yL = [-span, +span];

    % ---------- Figure: rows-only (one column) ----------
    nUsed = size(Y,1);
    perRowPx = 90; basePx = 200; maxPx = 5000;
    figH = min(maxPx, basePx + perRowPx*nUsed);
    f = figure('Color','w','Position',[60 60 900 figH],'Visible','off');
    tl = tiledlayout(f, nUsed, 1, 'Padding','compact', 'TileSpacing','compact');

    for r = 1:nUsed
        k = usedIdx(r);            % row index in cscNums/files
        nexttile(tl); hold on; box on; grid on;

        isActive = activeMaskCSC(k);
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

    % ---------- Save ----------
   nActive = sum(activeMaskCSC);
winMs = (numel(tRelMs)>1) * (tRelMs(end)-tRelMs(1)); %#ok<NASGU>
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
% Return exact sample slice [s0..s1] (1-based) from CSC file.
% Uses record-range extraction to avoid loading whole file.
if s1 < s0, y = []; return; end
rec0 = floor((s0-1)/REC) + 1;
rec1 = floor((s1-1)/REC) + 1;

% Read samples for record index RANGE
% Nlx2MatCSC(File,[TS,Ch,Fs,NValid,Samples],HdrFlag,ExtractMode,Vector)
S = Nlx2MatCSC(fullfile(fileRec.folder, fileRec.name), [0 0 0 0 1], 0, 2, [rec0 rec1]);
if isempty(S), y = []; return; end
v = S(:)';  % 512 x N -> vector

% Offset within block
off0 = s0 - ((rec0-1)*REC + 1);
off1 = s1 - ((rec0-1)*REC + 1);
i0 = max(0, off0); i1 = min(numel(v)-1, off1);
if i1 < i0, y = []; else, y = v(i0+1:i1+1); end
end

function v = tern(cond, a, b), if cond, v=a; else, v=b; end, end

function vec = str2num_safe(strCSV)
% parse "2,4,6" -> [2 4 6]; trims spaces; empty -> []
if strlength(strCSV)==0
    vec = [];
else
    parts = split(strCSV,','); parts = strtrim(parts);
    vec = str2double(parts); vec = vec(~isnan(vec));
end
end
