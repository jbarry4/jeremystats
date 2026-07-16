function spreadsheet_to_graph(excelPath, dataMatPath, varargin)
% spreadsheet_to_graph
% Reads event stamps from an Excel file and plots a stacked-channel
% voltage trace for each event, saving each as a separate PNG.
%
% This function mimics the alignment logic from your other pipelines:
% 1. Reads on/off stamps from Excel.
% 2. Finds the midpoint of the stamps.
% 3. Anchors to the positive peak on the LAST channel within a small
%    window around that midpoint.
% 4. Plots all channels in a window around that anchor.
%
% USAGE:
%   spreadsheet_to_graph("events.xlsx", "data.mat")
%   spreadsheet_to_graph("events.xlsx", "data.mat", 'channelIndices', 1:32, 'winHalfWidthMs', 100)

% ---------- 1. Input Parsing ----------
p = inputParser;
p.addRequired('excelPath', @(s) isstring(s) || ischar(s));
p.addRequired('dataMatPath', @(s) isstring(s) || ischar(s));

% Parameters modeled after your pipelines
p.addParameter('outputDir', "", @(s) isstring(s) || ischar(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));
p.addParameter('winHalfWidthMs',    50e-3, @(x)isfinite(x)&&x>0); % ±50 ms plot window
p.addParameter('anchorHalfWidthMs',  5e-3, @(x)isfinite(x)&&x>0); % ±5 ms anchor search

p.parse(excelPath, dataMatPath, varargin{:});
excelPath    = string(p.Results.excelPath);
dataMatPath  = string(p.Results.dataMatPath);
channelIdx   = p.Results.channelIndices;
scaleToMicroV= p.Results.scaleToMicroV;
winHWms      = p.Results.winHalfWidthMs;
anchorHWms   = p.Results.anchorHalfWidthMs;
outputDir    = string(p.Results.outputDir);

fprintf('===== spreadsheet_to_graph =====\n');

% ---------- 2. Setup IO & Data ----------
if outputDir == ""
    outputDir = fullfile(fileparts(excelPath), "Spreadsheet_Graphs");
end
if ~exist(outputDir, 'dir'), mkdir(outputDir); end
fprintf('Output PNGs will be saved to: %s\n', outputDir);

assert(isfile(excelPath), 'Excel file not found: %s', excelPath);
assert(isfile(dataMatPath), 'Data MAT file not found: %s', dataMatPath);

mf = matfile(dataMatPath);
try
    sfx = mf.sfx;
catch
    error('Missing "sfx" (sampling frequency) in data MAT file.');
end
nRowsAll = size(mf, 'd', 1);
nSamp    = size(mf, 'd', 2);
try
    kept_channels = mf.kept_channels;
catch
    kept_channels = [];
end

% ---------- 3. Channel & Scaling Setup ----------
if isempty(channelIdx)
    chList = 1:nRowsAll;
else
    chList = channelIdx(:).';
    chList = chList(chList >= 1 & chList <= nRowsAll);
end
nCh = numel(chList);
assert(nCh > 0, 'No valid channels selected.');

chanLabels = get_channel_labels(chList, kept_channels);
refCh = chList(end); % Use last channel for alignment anchor
fprintf('Plotting %d channels. Anchoring to last channel (Row %d).\n', nCh, refCh);

if numel(scaleToMicroV) == 1
    scaleVec = repmat(scaleToMicroV, nRowsAll, 1);
else
    assert(numel(scaleToMicroV) >= nRowsAll, 'scaleToMicroV must be scalar or length >= nRowsAll.');
    scaleVec = scaleToMicroV(:);
end

% ---------- 4. Windowing Setup ----------
HWwin    = max(1, round(winHWms    * sfx));  % ±plot half-width
HWanchor = max(1, round(anchorHWms * sfx));  % ±anchor search
tRelMs   = (-HWwin:HWwin) / sfx * 1e3;
winN     = numel(tRelMs);

% ---------- 5. Read Excel File ----------
T = readtable(excelPath, 'ReadVariableNames', true);
[onSamp, offSamp] = find_event_stamps(T, sfx);
NrowsXL = numel(onSamp);
assert(NrowsXL > 0, 'No event data found in Excel file.');
fprintf('Found %d events in spreadsheet.\n', NrowsXL);

% ---------- 6. Main Loop: Plot One PNG Per Row ----------
nPlotted = 0;
nSkipped = 0;
for row = 1:NrowsXL
    s0_evt = onSamp(row);
    s1_evt = offSamp(row);

    % --- A. Validate Stamps ---
    if ~(isfinite(s0_evt) && isfinite(s1_evt) && s1_evt > s0_evt && s0_evt > 0 && s1_evt <= nSamp)
        fprintf('  Skipping row %d: Invalid or out-of-bounds stamps (%d, %d).\n', row, s0_evt, s1_evt);
        nSkipped = nSkipped + 1;
        continue;
    end

    % --- B. Find Anchor (like your pipelines) ---
    ancMid = round((s0_evt + s1_evt) / 2);
    s0a = max(1, ancMid - HWanchor);
    s1a = min(nSamp, ancMid + HWanchor);
    
    y0 = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
    if isempty(y0) || all(~isfinite(y0))
        fprintf('  Skipping row %d: No anchor data on ref channel.\n', row);
        nSkipped = nSkipped + 1;
        continue;
    end
    
    [~, k_rel] = max(y0); % Anchor on positive peak
    anchor = s0a + k_rel - 1;

    % --- C. Define Plot Window ---
    s0_plot = anchor - HWwin;
    s1_plot = anchor + HWwin;
    
    if s0_plot < 1 || s1_plot > nSamp
        fprintf('  Skipping row %d: Plot window (around anchor %d) is out-of-bounds.\n', row, anchor);
        nSkipped = nSkipped + 1;
        continue;
    end
    
    % --- D. Extract Data ---
    Y_data = nan(nCh, winN);
    for k = 1:nCh
        ch = chList(k);
        sc = scaleVec(ch);
        y_raw = double(mf.d(ch, s0_plot:s1_plot));
        if any(isfinite(y_raw))
            Y_data(k, :) = y_raw * sc;
        end
    end
    
    if all(~isfinite(Y_data(:)))
        fprintf('  Skipping row %d: No finite data in plot window.\n', row);
        nSkipped = nSkipped + 1;
        continue;
    end

    % --- E. Plot Figure ---
    figH = min(16000, 150 + nCh * 120); % Dynamic height
    figW = 1000;
    f = figure('Color', 'w', 'Position', [100 100 figW figH], 'Visible', 'off');
    tl = tiledlayout(f, nCh, 1, 'Padding', 'compact', 'TileSpacing', 'compact');
    
    % Calculate original stamp times relative to new anchor
    tRelMs_On = (s0_evt - anchor) / sfx * 1e3;
    tRelMs_Off = (s1_evt - anchor) / sfx * 1e3;
    
    for k = 1:nCh
        ax = nexttile(tl);
        plot(ax, tRelMs, Y_data(k, :), 'Color', [0.1 0.1 0.8]); % Blue trace
        hold(ax, 'on');
        box(ax, 'on');
        grid(ax, 'on');
        
        % Mark anchor (t=0)
        xline(ax, 0, '--k', 'LineWidth', 1.5, 'Label', 'Anchor (t=0)');
        % Mark original Excel stamps
        xline(ax, tRelMs_On, ':r', 'LineWidth', 1, 'Label', 'onstamp');
        xline(ax, tRelMs_Off, ':r', 'LineWidth', 1, 'Label', 'offstamp');
        
        xlim(ax, [tRelMs(1), tRelMs(end)]);
        ylabel(ax, '\muV');
        title(ax, chanLabels{k}, 'FontSize', 9, 'FontWeight', 'normal');
        set(ax, 'FontSize', 8);
        
        if k < nCh
            set(ax, 'XTickLabel', []); % Remove x-labels for all but last plot
        end
    end
    xlabel(ax, 'Time relative to Anchor (ms)');
    
    sgtitle(tl, sprintf('Event Row %d | Anchor: %d | Original Stamps: %d - %d', ...
        row, anchor, s0_evt, s1_evt), 'FontSize', 12, 'FontWeight', 'bold');

    % --- F. Save PNG ---
    outPngPath = fullfile(outputDir, sprintf('Event_Row_%04d_Aligned.png', row));
    try
        exportgraphics(f, outPngPath, 'Resolution', 200);
        nPlotted = nPlotted + 1;
    catch ME
        warning('Failed to save PNG for row %d: %s', row, ME.message);
        nSkipped = nSkipped + 1;
    end
    close(f);
end

fprintf('===== Done. =====\n');
fprintf('Successfully plotted and saved %d events.\n', nPlotted);
fprintf('Skipped %d events due to errors or invalid data.\n', nSkipped);
end


% =============================
%           HELPERS
% =============================

function [onSamp, offSamp] = find_event_stamps(T, sfx)
% Robustly finds event sample columns, converting from seconds if needed.
% Copied from your pipelines

canon = lower(regexprep(T.Properties.VariableNames, '[^a-zA-Z0-9]', ''));
i_onSamp  = find(strcmp(canon,'onsamp')  | strcmp(canon,'startsample') | strcmp(canon,'startsamp') | strcmp(canon,'on'), 1);
i_offSamp = find(strcmp(canon,'offsamp') | strcmp(canon,'endsample')   | strcmp(canon,'endsamp')   | strcmp(canon,'off'), 1);
i_onSec   = find(strcmp(canon,'onsec')   | strcmp(canon,'startsec')    | strcmp(canon,'onsecs'), 1);
i_offSec  = find(strcmp(canon,'offsec')  | strcmp(canon,'endsec')      | strcmp(canon,'offsecs'), 1);

if ~isempty(i_onSamp) && ~isempty(i_offSamp)
    fprintf('Reading event stamps from sample columns: %s, %s\n', ...
        T.Properties.VariableNames{i_onSamp}, T.Properties.VariableNames{i_offSamp});
    onSamp  = round(double(T{:, i_onSamp}));
    offSamp = round(double(T{:, i_offSamp}));
elseif ~isempty(i_onSec) && ~isempty(i_offSec)
    fprintf('Reading event stamps from second columns: %s, %s (sfx=%.1f)\n', ...
        T.Properties.VariableNames{i_onSec}, T.Properties.VariableNames{i_offSec}, sfx);
    onSamp  = round(double(T{:, i_onSec})  * sfx);
    offSamp = round(double(T{:, i_offSec}) * sfx);
else
    if width(T) >= 2
        fprintf('No standard columns found. Using first 2 columns as on/off samples.\n');
        onSamp  = round(double(T{:,1}));
        offSamp = round(double(T{:,2}));
    else
        error('Cannot find on/off stamp columns. Please name them "onsamp"/"offsamp" or "onsec"/"offsec".');
    end
end
end


function chanLabels = get_channel_labels(chList, kept_channels)
% Creates string labels for channels, using CSC info if available.
% Copied from your pipelines
nCh = numel(chList);
chanLabels = cell(nCh, 1);
if isempty(kept_channels)
    for k = 1:nCh
        chanLabels{k} = sprintf('Row %d', chList(k));
    end
else
    for k = 1:nCh
        ch = chList(k);
        if ch <= numel(kept_channels)
            chanLabels{k} = sprintf('Row %d (CSC%d)', ch, kept_channels(ch));
        else
            chanLabels{k} = sprintf('Row %d (CSC_OOB)', ch); % Out of bounds
        end
    end
end
end