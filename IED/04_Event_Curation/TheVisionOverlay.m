function TheVisionOverlay(inputFolder, varargin)
% TheVisionOverlay_Pipeline
% Pipeline-enabled version of TheVisionOverlay.
%
% Takes a single inputFolder and auto-detects:
%   - Data *.mat file (e.g., data.mat)
%   - Spikes *.mat file (e.g., ets.mat or *spikes.mat, must contain 'ech')
%   - Events *.xlsx file (must contain 'onsamp'/'offsamp' or 'onsec'/'offsec')
%   - 'Solid' subfolder (for filtering event list)
%
% For each event that is BOTH in the 'Solid' folder AND meets the
% 'minCh'/'maxCh' criteria (from 'ech'), it produces a SINGLE
% overlay plot of channel waveforms.
%
% ---------- Parse ----------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addParameter('halfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'})));
p.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);
p.addParameter('saveDir','', @(s)ischar(s)||isstring(s));
p.addParameter('minCh', 5, @(x)isfinite(x)&&x>=0);
p.addParameter('maxCh', 8, @(x)isfinite(x)&&x>=0);
p.addParameter('channelStride', 1, @(x)isfinite(x)&&x>=1&&mod(x,1)==0);
p.addParameter('channelOffset', 0, @(x)isfinite(x)&&x>=0&&mod(x,1)==0);
% --- New parameters from pipeline examples ---
p.addParameter('indexBase','auto', @(s) any(strcmpi(s,{'auto','zero','one'})));
p.addParameter('evtOffset',0, @(x)isscalar(x)&&isfinite(x));
p.parse(inputFolder, varargin{:});

inputFolder = string(p.Results.inputFolder);
halfWidthMs    = p.Results.halfWidthMs;
peakPolarity   = lower(string(p.Results.peakPolarity));
scaleToMicroV  = p.Results.scaleToMicroV;
saveDir        = string(p.Results.saveDir);
minCh          = p.Results.minCh;
maxCh          = p.Results.maxCh;
channelStride  = p.Results.channelStride;
channelOffset  = p.Results.channelOffset;
indexBase      = p.Results.indexBase;
evtOffset      = p.Results.evtOffset;

% ---------- 1. Auto-detect paths ----------
fprintf('===== TheVisionOverlay_Pipeline =====\n');
assert(isfolder(inputFolder), 'Input folder not found: %s', inputFolder);

% Data MAT (find *.mat, ignore ets.mat or *spikes.mat)
matFiles = dir(fullfile(inputFolder, '*.mat'));
isEts = endsWith({matFiles.name}, 'spikes.mat', 'IgnoreCase', true) | ...
        strcmpi({matFiles.name}, 'ets.mat');
matFiles = matFiles(~isEts);
assert(~isempty(matFiles), 'No data .mat file found in %s', inputFolder);
dataMatPath = fullfile(matFiles(1).folder, matFiles(1).name);
fprintf('Data MAT: %s\n', dataMatPath);

% Spikes MAT (find *spikes.mat or ets.mat, must contain 'ech')
spikesMatFiles = dir(fullfile(inputFolder, '*spikes.mat'));
if isempty(spikesMatFiles)
    spikesMatFiles = dir(fullfile(inputFolder, 'ets.mat'));
end
assert(~isempty(spikesMatFiles), 'No spikes MAT (*spikes.mat or ets.mat) found in %s', inputFolder);
spikesMatPath = fullfile(spikesMatFiles(1).folder, spikesMatFiles(1).name);
fprintf('Spikes MAT: %s\n', spikesMatPath);

% Excel File
xl = dir(fullfile(inputFolder, "*.xlsx"));
assert(~isempty(xl), 'No Excel file (*.xlsx) found in %s', inputFolder);
excelPath = fullfile(xl(1).folder, xl(1).name);
fprintf('Excel File: %s\n', excelPath);

% Solid Folder
solidDir = fullfile(inputFolder, "Solid");
assert(isfolder(solidDir), 'Missing folder: %s', solidDir);
fprintf('Solid Dir: %s\n', solidDir);

% ---------- 2. Load Data & Events ----------
% Load data file
if ~isfile(dataMatPath), error('Data MAT not found: %s', dataMatPath); end
mf = matfile(dataMatPath);
try, sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRows = size(mf,'d',1);
nSamp = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end %#ok<NASGU>

% Load 'ech' (channel mask) from spikes MAT
if ~isfile(spikesMatPath), error('Spikes MAT not found: %s', spikesMatPath); end
S = load(spikesMatPath,'ech');
if isfield(S,'ech')
    ech = S.ech;
    if size(ech,2) ~= nRows
        if size(ech,2) < nRows, ech(:,end+1:nRows) = false; else, ech = ech(:,1:nRows); end
    end
else
    % If 'ech' is missing, default to all channels active for all events
    % Note: This will likely cause *all* events to be selected by min/max
    warning('Spikes MAT missing "ech". Defaulting to all channels active.');
    ech = true(1e6, nRows); % Set a placeholder size
end
Nevents = size(ech,1);

% Load 'ets' (timestamps) from Excel file
[onSamp, offSamp] = parseEventSamplesFromExcel(excelPath, sfx, nSamp, indexBase);
NrowsXL = numel(onSamp);

% Assert that ech and xlsx rows match
assert(Nevents == NrowsXL, ...
    'Event count mismatch: spikes MAT has %d events (ech rows), Excel has %d events (rows).', ...
    Nevents, NrowsXL);
ets = [onSamp(:), offSamp(:)]; % Create the ets matrix

% ---------- 3. Select events ----------
% Find events meeting channel criteria
chCounts = sum(ech,2);
selEch = (chCounts >= minCh) & (chCounts <= maxCh);

% Find events present in 'Solid' folder (using offset)
evtFromSolid = parseEvtNumsFromPngs(solidDir);
selSolid = false(size(selEch));
rowIndices = evtFromSolid + evtOffset; % Apply offset
rowIndices = rowIndices(rowIndices >= 1 & rowIndices <= numel(selEch)); % Filter valid rows
selSolid(rowIndices) = true;

% Final selection is the intersection
sel = selEch & selSolid;
evtIdx = find(sel);

if isempty(evtIdx)
    fprintf('No events found that are BOTH in /Solid AND have %d–%d channels.\n', minCh, maxCh);
    return;
end

% ---------- 4. Setup ----------
HW = max(1, round(halfWidthMs * sfx));  % half-width in samples
tRelSamples = -HW:HW; %#ok<NASGU>
tRelMs = (tRelSamples / sfx) * 1e3;

% --- Modified SaveDir logic ---
if saveDir==""
    outDir = fullfile(inputFolder, 'TheVisionOverlay Output');
else
    outDir = char(saveDir);
end
if ~exist(outDir,'dir'), mkdir(outDir); end

fprintf('Overlay: %d qualifying event(s) (%d–%d ch, from Solid folder). Window ±%d samples (%.2f ms). Using stride=%d offset=%d. Scale=%g µV.\n', ...
    numel(evtIdx), minCh, maxCh, HW, 1e3*HW/sfx, channelStride, channelOffset, scaleToMicroV);

% Row selection by stride/offset
offset = mod(channelOffset, channelStride);
rowKeepMask = arrayfun(@(r) mod(r-1, channelStride) == offset, 1:nRows);
rowKeepIdx  = find(rowKeepMask);

% Inactive color palette
colInactiveBelow   = [0.55 0.75 0.95];  % light blue
colInactiveBetween = [0.70 0.70 0.70];  % gray
colInactiveAbove   = [0.95 0.60 0.60];  % light red
colActive          = [0 0 0];

% ---------- 5. Iterate events ----------
for ii = 1:numel(evtIdx)
    e = evtIdx(ii); % 'e' is the correct row index for ets and ech
    maskActive = ech(e,:);                 % logical 1 x nRows
    
    % Get timestamps from Excel-derived 'ets'
    s0_ev = max(1, ets(e,1));
    s1_ev = min(nSamp, ets(e,2));
    
    % Global anchor from ACTIVE channels only
    activeRows = find(maskActive);
    if isempty(activeRows)
        fprintf('Evt %d: no active rows flagged; skipping.\n', e);
        continue;
    end
    
    peakIdx = nan(numel(activeRows),1);
    for k = 1:numel(activeRows)
        ch = activeRows(k);
        yseg = double(mf.d(ch, s0_ev:s1_ev));
        if any(~isfinite(yseg)), continue; end
        switch peakPolarity
            case "pos", [~,kpk] = max(yseg);
            case "neg", [~,kpk] = min(yseg);
            otherwise,  [~,kpk] = max(abs(yseg)); % 'abs'
        end
        peakIdx(k) = s0_ev + kpk - 1;
    end
    peakIdx = peakIdx(isfinite(peakIdx));
    if isempty(peakIdx)
        fprintf('Evt %d: could not compute peaks on active channels; skipping.\n', e, e);
        continue;
    end
    
    anchor = round(median(peakIdx));
    s0 = anchor - HW; s1 = anchor + HW;
    if s0 < 1 || s1 > nSamp
        fprintf('Evt %d: window out of bounds @ anchor %d; skipping.\n', e, anchor);
        continue;
    end
    
    % Extract windows for selected rows
    rowsToPlot = rowKeepIdx;
    nPlot = numel(rowsToPlot);
    Y = nan(nPlot, 2*HW+1);
    for k = 1:nPlot
        ch = rowsToPlot(k);
        y = double(mf.d(ch, s0:s1)) * scaleToMicroV; % µV
        if any(~isfinite(y)), continue; end
        Y(k,:) = y;
    end
    
    if all(~isfinite(Y(:)))
        fprintf('Evt %d: no valid windows for selected rows; skipping.\n', e);
        continue;
    end
    
    % Fixed symmetric y-limits
    maxAbs = max(abs(Y(:)), [], 'omitnan');
    if ~isfinite(maxAbs) || maxAbs<=0, maxAbs = 1; end
    pad  = 0.05; span = (1+pad)*maxAbs; yL = [-span, span];
    
    % Active range (by row index) for inactive color coding
    actMin = min(activeRows);
    actMax = max(activeRows);
    
    % Plot overlay
    f = figure('Color','w','Position',[80 80 1000 700],'Visible','off');
    ax = axes('Parent',f); hold(ax,'on'); box(ax,'on'); grid(ax,'on');
    for k = 1:nPlot
        ch = rowsToPlot(k);
        y  = Y(k,:);
        if all(~isfinite(y)), continue; end
        if maskActive(ch)
            lw = 1.6; col = colActive;       % active: bold black
        else
            % Inactive color by position relative to active range
            if ch < actMin
                col = colInactiveBelow;       % below smallest active -> light blue
            elseif ch > actMax
                col = colInactiveAbove;       % above largest active -> light red
            else
                col = colInactiveBetween;     % between -> gray
            end
            lw = 0.9;
        end
        plot(ax, tRelMs, y, 'LineWidth', lw, 'Color', col);
    end
    
    xline(ax,0,'--k','LineWidth',0.9);
    yline(ax,0,':','Color',[0.7 0.7 0.7]);
    ylim(ax, yL);
    xlabel(ax, 'ms'); ylabel(ax, '\muV');
    nActive = sum(maskActive);
    ttl = sprintf('Event %03d  |  Active channels: %d  |  Anchor: median peak @ [%d]  |  Win: \\pm%.1f ms  |  Plotted rows: %d (stride=%d, offset=%d)', ...
                   e, nActive, anchor, 1e3*HW/sfx, nPlot, channelStride, offset);
    title(ax, ttl, 'FontSize', 12, 'FontWeight', 'bold');
    
    % Legend note
    txt = sprintf(['\\fontsize{8}Active=bold black (%d)   Inactive: below=light blue, ', ...
                   'between=gray, above=light red (%d)   Units=\\muV   yLim=\\pm%.1f'], ...
                   nActive, nPlot - nActive, span);
    text(ax, 0.01, 0.98, txt, 'Units','normalized', 'VerticalAlignment','top', ...
         'BackgroundColor','w', 'Margin',3, 'EdgeColor',[0.85 0.85 0.85], 'Interpreter','tex');
         
    % Save
    msWin = round(1e3*HW/sfx);
    outPng = fullfile(outDir, sprintf('Overlay_Evt%03d_%drows_stride%d_off%d_HW%ds_%dms_uV.png', ...
                                      e, nPlot, channelStride, offset, HW, msWin));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved overlay: %s\n', outPng);
end
fprintf('Done. Output dir: %s\n', outDir);
end

% ======================================================================
%                          HELPER FUNCTIONS
% ======================================================================

function evts = parseEvtNumsFromPngs(dirpath)
% Parses Evt(\d+) from PNG filenames in a directory
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

function [onSamp, offSamp] = parseEventSamplesFromExcel(excelPath, sfx, nSamp, indexBase)
% Reads an Excel file and extracts event start/end samples.
% Handles 'onsamp'/'offsamp' or 'onsec'/'offsec' columns.
% Applies indexBase correction ('zero' or 'auto' for 0-based).
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
    case "zero"
        onSamp = onSamp+1; offSamp = offSamp+1;
    case "auto"
        if any(onSamp < 1 | offSamp < 1 | onSamp==0 | offSamp==0)
            fprintf('Detected 0-based indexing in Excel, adding 1.\n');
            onSamp = onSamp+1; offSamp = offSamp+1;
        end
    case "one"
        % no-op
end
% Clamp to valid sample range
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));
end