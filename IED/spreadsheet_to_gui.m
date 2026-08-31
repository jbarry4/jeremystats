function spreadsheet_to_gui(excelPath, dataMatPath, varargin)
% spreadsheet_to_gui (v5)
% - v5: REMOVED LIMITS. Decoupled data loading from viewing window.
%       - Loads a +/- 2000ms buffer by default so you can pan/zoom.
%       - Added Axis Toolbar (Pan/Zoom) for navigation.
%       - Click logic now handles off-screen/panned anchors correctly.
%
% USAGE:
%   spreadsheet_to_gui("events.xlsx", "data.mat")

% ---------- 1. Input Parsing ----------
p = inputParser;
p.addRequired('excelPath', @(s) isstring(s) || ischar(s));
p.addRequired('dataMatPath', @(s) isstring(s) || ischar(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));
p.addParameter('winHalfWidthMs', 20, @(x)isfinite(x)&&x>0);   % Initial View Width
p.addParameter('yLimMicroV', [], @(x) isempty(x) || (isscalar(x) && x>0)); 
p.addParameter('yRobustPct', 99.5, @(x) isfinite(x) && x>0 && x<100);
p.parse(excelPath, dataMatPath, varargin{:});

excelPath    = string(p.Results.excelPath);
dataMatPath  = string(p.Results.dataMatPath);
channelIdx   = p.Results.channelIndices;
scaleToMicroV= p.Results.scaleToMicroV;
winHWms      = p.Results.winHalfWidthMs;
yLimInitial  = p.Results.yLimMicroV;
yRobustPct   = p.Results.yRobustPct;

fprintf('===== spreadsheet_to_gui (v5 - Infinite Pan) =====\n');

% ---------- 2. Setup IO & Data ----------
assert(isfile(excelPath), 'Excel file not found: %s', excelPath);
assert(isfile(dataMatPath), 'Data MAT file not found: %s', dataMatPath);

fprintf('Loading matfile (fast)... ');
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
fprintf('Done.\n');

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

if numel(scaleToMicroV) == 1
    scaleVec = repmat(scaleToMicroV, nRowsAll, 1);
else
    assert(numel(scaleToMicroV) >= nRowsAll, 'scaleToMicroV must be scalar or length >= nRowsAll.');
    scaleVec = scaleToMicroV(:);
end

% ---------- 4. Windowing Setup (View vs Load) ----------
% We define a "Buffer" that is larger than the view. 
% E.g., Always load at least 2 seconds (2000ms) or 5x the view window.
minBufferMs = 2000; 
bufferMs = max(minBufferMs, winHWms * 5);

HWwin_View = max(1, round(winHWms / 1000 * sfx));   % What we set xlim to
HWwin_Load = max(1, round(bufferMs / 1000 * sfx));  % What we actually load

% Time vector for the LOADED data
tRelMs_Load = (-HWwin_Load:HWwin_Load) / sfx * 1e3;

% ---------- 5. Read Excel File ----------
fprintf('Reading event stamps... ');
T_events = readtable(excelPath, 'ReadVariableNames', true);
[onSamp, offSamp] = find_event_stamps(T_events, sfx);
T_events.onsamp = onSamp;
T_events.offsamp = offSamp;
numEvents = height(T_events);
assert(numEvents > 0, 'No event data found in Excel file.');
fprintf('Found %d events.\n', numEvents);

% ---------- 6. Prepare Results Table ----------
Results = T_events;
Results.manual_anchor_samp = nan(numEvents, 1);

% ---------- 7. Create GUI ----------
fprintf('Building GUI... ');
fig = uifigure('Name', 'Anchor Tool v5 (Pan Enabled)', ...
               'Position', [100 100 1200 800], ...
               'UserData', [], ...
               'CloseRequestFcn', @(src,evt) closeGUI(src));

% Main grid layout
gl = uigridlayout(fig, [11, 4]);
gl.RowHeight = {'1x', '1x', '1x', '1x', '1x', '1x', '1x', '2x', 'fit', 'fit', 30};
gl.ColumnWidth = {'1x', '1x', '1x', '1x'};

% Plot container
plotPanel = uipanel(gl);
plotPanel.Layout.Row = [1 8];
plotPanel.Layout.Column = [1 4];
plotPanel.BorderType = 'none'; 

% --- GUI Controls Row ---
xWinLabel = uilabel(gl, 'Text', 'View Width (ms):', 'HorizontalAlignment', 'right');
xWinLabel.Layout.Row = 9; xWinLabel.Layout.Column = 1;

xWinEdit = uieditfield(gl, 'numeric', 'Value', winHWms, ...
                       'ValueChangedFcn', @(src,evt) changeXWindow(fig, src));
xWinEdit.Layout.Row = 9; xWinEdit.Layout.Column = 2;

yLimLabel = uilabel(gl, 'Text', 'Y-Lim (µV):', 'HorizontalAlignment', 'right');
yLimLabel.Layout.Row = 9; yLimLabel.Layout.Column = 3;

yLimEdit = uieditfield(gl, 'numeric', 'Value', 0, ...
                       'ValueChangedFcn', @(src,evt) changeYLim(fig, src));
yLimEdit.Layout.Row = 9; yLimEdit.Layout.Column = 4;

% --- Status Label Row ---
statusLabel = uilabel(gl, 'Text', 'Loading...', ...
                      'FontSize', 14, 'FontWeight', 'bold', ...
                      'HorizontalAlignment', 'center');
statusLabel.Layout.Row = 10;
statusLabel.Layout.Column = [1 4];

% --- Button Row ---
prevButton = uibutton(gl, 'Text', '<< Prev Event', ...
                    'ButtonPushedFcn', @(src,evt) prevClicked(fig));
prevButton.Layout.Row = 11;
prevButton.Layout.Column = 1;

skipButton = uibutton(gl, 'Text', 'Skip Event >>', ...
                    'ButtonPushedFcn', @(src,evt) skipClicked(fig), ...
                    'FontColor', [0.8 0 0]);
skipButton.Layout.Row = 11;
skipButton.Layout.Column = 2;

nextButton = uibutton(gl, 'Text', 'Next Event >>', ...
                    'ButtonPushedFcn', @(src,evt) nextClicked(fig));
nextButton.Layout.Row = 11;
nextButton.Layout.Column = 3;

saveButton = uibutton(gl, 'Text', 'Finish & Save CSV', ...
                    'ButtonPushedFcn', @(src,evt) saveClicked(fig), ...
                    'BackgroundColor', [0.1 0.7 0.1], 'FontColor', 'w');
saveButton.Layout.Row = 11;
saveButton.Layout.Column = 4;

% ---------- 8. Store State in UserData ----------
ud = struct();
ud.mf = mf;
ud.sfx = sfx;
ud.nSamp = nSamp;
ud.T_events = T_events;
ud.Results = Results;
ud.CurrentIndex = 1;
ud.chList = chList;
ud.nCh = nCh;
ud.chanLabels = chanLabels;
ud.scaleVec = scaleVec;

% Windowing State
ud.winHalfWidthMs = winHWms;  % View Width
ud.HWwin_View = HWwin_View;   % View Samples
ud.HWwin_Load = HWwin_Load;   % Load Samples (The buffer)
ud.tRelMs_Load = tRelMs_Load; % X-Axis for the loaded buffer

ud.yRobustPct = yRobustPct;
ud.plotPanel = plotPanel;
ud.tiledLayout = []; 
ud.statusLabel = statusLabel;
ud.yLimEdit = yLimEdit;
ud.PlotHandles = {};    
ud.MidpointLine = [];   
ud.AnchorLine = [];     
ud.AxesTiles = {};      
ud.yLimCurrent = yLimInitial; 

fig.UserData = ud;

% ---------- 9. Initial Plot ----------
updatePlot(fig);
fprintf('GUI is ready.\n');
fprintf('TIP: Use the toolbar (top right of plot) to Pan/Zoom if the anchor is off-screen.\n');
end

% ======================================================================
%                          GUI HELPER FUNCTIONS
% ======================================================================

function updatePlot(fig)
    ud = fig.UserData;
    idx = ud.CurrentIndex;
    
    % --- Get event info ---
    onsamp = ud.T_events.onsamp(idx);
    offsamp = ud.T_events.offsamp(idx);
    mid = round((onsamp + offsamp) / 2);
    
    % --- Define LOAD window (Buffer) ---
    s0_load = mid - ud.HWwin_Load;
    s1_load = mid + ud.HWwin_Load;
    
    % --- Clamp to file limits ---
    s0_plot = max(1, s0_load);
    s1_plot = min(ud.nSamp, s1_load);
    
    % Check invalid
    if s1_plot <= s0_plot
        cla(ud.plotPanel);
        ud.statusLabel.Text = sprintf('Event %d: Invalid Window', idx);
        return;
    end
    
    tRelMs_Mid = 0; 
    
    % --- Plotting ---
    if isempty(ud.PlotHandles)
        % --- First time Setup ---
        cla(ud.plotPanel);
        tl = tiledlayout(ud.plotPanel, ud.nCh, 1, 'Padding', 'compact', 'TileSpacing', 'none');
        ud.tiledLayout = tl;
        
        ud.AxesTiles = cell(ud.nCh, 1);
        ud.PlotHandles = cell(ud.nCh, 1);
        
        yLimAutoSet = false;
        if isempty(ud.yLimCurrent)
            yLimAutoSet = true;
            yLimMax = 0;
        end
        
        for k = 1:ud.nCh
            ax_k = nexttile(tl);
            ch = ud.chList(k);
            sc = ud.scaleVec(ch);
            
            % --- LOAD BUFFER DATA ---
            y_data = double(ud.mf.d(ch, s0_plot:s1_plot)) * sc;
            
            % Map to full buffer size (handle NaNs if near edge)
            y_full = nan(1, numel(ud.tRelMs_Load));
            idx_start_in_full = s0_plot - s0_load + 1;
            idx_end_in_full   = idx_start_in_full + (s1_plot - s0_plot);
            
            if idx_start_in_full >= 1 && idx_end_in_full <= numel(y_full)
                y_full(idx_start_in_full:idx_end_in_full) = y_data;
            end
            
            h = plot(ax_k, ud.tRelMs_Load, y_full, 'Color', [0.1 0.1 0.8], 'LineWidth', 1.5);
            
            if yLimAutoSet
                yy = y_data(isfinite(y_data));
                if ~isempty(yy)
                    p = prctile(abs(yy), ud.yRobustPct);
                    if isfinite(p) && p > yLimMax, yLimMax = p; end
                end
            end
            
            hold(ax_k, 'on'); grid(ax_k, 'on'); box(ax_k, 'on');
            
            % --- VIEW LIMITS (Zoomed in initially) ---
            xlim(ax_k, [-ud.winHalfWidthMs, ud.winHalfWidthMs]);
            
            set(ax_k, 'FontSize', 8, 'YTick', []);
            if k < ud.nCh, set(ax_k, 'XTickLabel', []); end
            
            % Click Callback
            ax_k.ButtonDownFcn = @(src,evt) recordClick(fig, evt);
            
            % *** v5: Enable Toolbar for Panning ***
            % This adds the Pan/Zoom buttons to the top right of the axes
            axtoolbar(ax_k, {'pan', 'zoomin', 'zoomout', 'restoreview'});
            
            ud.PlotHandles{k} = h;
            ud.AxesTiles{k} = ax_k;
        end
        xlabel(ud.AxesTiles{end}, 'Time relative to Midpoint (ms)');
        
        if yLimAutoSet
            yLimMax = max(10, yLimMax);
            ud.yLimCurrent = [-yLimMax, yLimMax];
            ud.yLimEdit.Value = round(yLimMax);
        end
        for k = 1:ud.nCh
            set(ud.AxesTiles{k}, 'YLim', ud.yLimCurrent);
        end
        
        ud.MidpointLine = gobjects(ud.nCh, 1);
        ud.AnchorLine   = gobjects(ud.nCh, 1);
        for k = 1:ud.nCh
            ud.MidpointLine(k) = xline(ud.AxesTiles{k}, 0, '--k', 'Midpoint', 'LineWidth', 1.5, 'HandleVisibility', 'off');
            ud.AnchorLine(k)   = xline(ud.AxesTiles{k}, NaN, '-r', 'Anchor', 'LineWidth', 2.0, 'HandleVisibility', 'off');
        end
        linkaxes([ud.AxesTiles{:}], 'x');
        
    else
        % --- Subsequent Updates ---
        for k = 1:ud.nCh
            ch = ud.chList(k);
            sc = ud.scaleVec(ch);
            
            y_data = double(ud.mf.d(ch, s0_plot:s1_plot)) * sc;
            y_full = nan(1, numel(ud.tRelMs_Load));
            idx_start_in_full = s0_plot - s0_load + 1;
            idx_end_in_full   = idx_start_in_full + (s1_plot - s0_plot);
            
            if idx_start_in_full >= 1 && idx_end_in_full <= numel(y_full)
                y_full(idx_start_in_full:idx_end_in_full) = y_data;
            end
            
            set(ud.PlotHandles{k}, 'XData', ud.tRelMs_Load, 'YData', y_full);
        end
        
        % Reset View to default window (center on event)
        xlim(ud.AxesTiles{1}, [-ud.winHalfWidthMs, ud.winHalfWidthMs]);
    end
    
    % --- Visual Guides ---
    selected_anchor_samp = ud.Results.manual_anchor_samp(idx);
    if isfinite(selected_anchor_samp)
        tRelMs_Anchor = (selected_anchor_samp - mid) / ud.sfx * 1e3;
        set(ud.AnchorLine, 'Value', tRelMs_Anchor, 'Visible', 'on');
    else
        set(ud.AnchorLine, 'Visible', 'off');
    end
    
    ud.statusLabel.Text = sprintf('Event %d of %d', idx, height(ud.T_events));
    fig.UserData = ud;
    drawnow('limitrate');
end

function recordClick(fig, evt)
    ud = fig.UserData;
    idx = ud.CurrentIndex;
    
    % 1. Get click info (works even if panned)
    clicked_time_ms = evt.IntersectionPoint(1); 
    
    % 2. Calculate absolute sample
    onsamp = ud.T_events.onsamp(idx);
    offsamp = ud.T_events.offsamp(idx);
    mid = round((onsamp + offsamp) / 2);
    
    clicked_samp_rel = round(clicked_time_ms / 1000 * ud.sfx);
    manual_anchor_samp = mid + clicked_samp_rel;
    
    % 3. Store
    ud.Results.manual_anchor_samp(idx) = manual_anchor_samp;
    fprintf('Event %d: Anchor set @ %.2f ms\n', idx, clicked_time_ms);
    
    fig.UserData = ud;
    goToEvent(fig, idx + 1);
end

function goToEvent(fig, newIndex)
    ud = fig.UserData;
    numEvents = height(ud.T_events);
    if newIndex < 1, return; end
    if newIndex > numEvents
        ud.statusLabel.Text = 'Last event! Click "Finish & Save"';
        return;
    end
    ud.CurrentIndex = newIndex;
    fig.UserData = ud;
    updatePlot(fig);
end

function prevClicked(fig)
    ud = fig.UserData;
    goToEvent(fig, ud.CurrentIndex - 1);
end
function nextClicked(fig)
    ud = fig.UserData;
    goToEvent(fig, ud.CurrentIndex + 1);
end
function skipClicked(fig)
    ud = fig.UserData;
    idx = ud.CurrentIndex;
    ud.Results.manual_anchor_samp(idx) = NaN;
    fig.UserData = ud;
    goToEvent(fig, idx + 1);
end

function saveClicked(fig)
    ud = fig.UserData;
    [file, path] = uiputfile('*.csv', 'Save Manual Anchors', 'manual_anchors.csv');
    if isequal(file, 0), return; end
    
    try
        writetable(ud.Results, fullfile(path, file));
        selection = uiconfirm(fig, 'Saved. Close GUI?', 'Success', ...
                               'Options',{'Close', 'Keep Working'}, 'DefaultOption', 1);
        if strcmp(selection, 'Close'), delete(fig); end
    catch ME
        uialert(fig, ME.message, 'Error');
    end
end

function closeGUI(fig)
    delete(fig);
end

function changeXWindow(fig, src)
    ud = fig.UserData;
    newWinMs = src.Value;
    if newWinMs <= 0, return; end
    
    % Update View Window
    ud.winHalfWidthMs = newWinMs;
    ud.HWwin_View = max(1, round(newWinMs / 1000 * ud.sfx));
    
    % If requested view is larger than current buffer, expand buffer
    minBuffer = max(2000, newWinMs * 5);
    if minBuffer > (numel(ud.tRelMs_Load)/ud.sfx*1000)/2
        ud.HWwin_Load = max(1, round(minBuffer / 1000 * ud.sfx));
        ud.tRelMs_Load = (-ud.HWwin_Load:ud.HWwin_Load) / ud.sfx * 1e3;
        
        % Force full rebuild
        if ~isempty(ud.tiledLayout), delete(ud.tiledLayout); end
        ud.tiledLayout = [];
        ud.PlotHandles = {};
        fig.UserData = ud;
        updatePlot(fig);
    else
        % Just update View Limit
        fig.UserData = ud;
        for k = 1:ud.nCh
            xlim(ud.AxesTiles{k}, [-newWinMs, newWinMs]);
        end
    end
end

function changeYLim(fig, src)
    ud = fig.UserData;
    val = src.Value;
    if val <= 0, return; end
    ud.yLimCurrent = [-val, val];
    fig.UserData = ud;
    for k=1:ud.nCh, set(ud.AxesTiles{k}, 'YLim', ud.yLimCurrent); end
end

% ======================================================================
%                  HELPER FUNCTIONS
% ======================================================================
function [onSamp, offSamp] = find_event_stamps(T, sfx)
    canon = lower(regexprep(T.Properties.VariableNames, '[^a-zA-Z0-9]', ''));
    i_onSamp  = find(strcmp(canon,'onsamp')|strcmp(canon,'startsample')|strcmp(canon,'on'), 1);
    i_offSamp = find(strcmp(canon,'offsamp')|strcmp(canon,'endsample')|strcmp(canon,'off'), 1);
    i_onSec   = find(strcmp(canon,'onsec')|strcmp(canon,'startsec'), 1);
    i_offSec  = find(strcmp(canon,'offsec')|strcmp(canon,'endsec'), 1);
    
    if ~isempty(i_onSamp) && ~isempty(i_offSamp)
        onSamp = round(double(T{:, i_onSamp})); offSamp = round(double(T{:, i_offSamp}));
    elseif ~isempty(i_onSec) && ~isempty(i_offSec)
        onSamp = round(double(T{:, i_onSec})*sfx); offSamp = round(double(T{:, i_offSec})*sfx);
    else
        onSamp = round(double(T{:,1})); offSamp = round(double(T{:,2}));
    end
end
function chanLabels = get_channel_labels(chList, kept_channels)
    nCh = numel(chList); chanLabels = cell(nCh, 1);
    for k = 1:nCh
        if ~isempty(kept_channels) && chList(k) <= numel(kept_channels)
            chanLabels{k} = sprintf('Row %d (CSC%d)', chList(k), kept_channels(chList(k)));
        else
            chanLabels{k} = sprintf('Row %d', chList(k));
        end
    end
end