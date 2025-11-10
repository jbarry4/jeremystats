function spreadsheet_to_gui(excelPath, dataMatPath, varargin)
% spreadsheet_to_gui (v4)
% Creates a robust, lightweight GUI to manually click and save anchor points
% for events defined in a spreadsheet.
%
% - v4: Optimized for visualization. Removed labels/ticks, increased
%       line width, and set tile spacing to 'none' for a clean look.
% - Uses matfile for fast, on-demand data loading.
% - Robustly handles events near the start/end of the file (NaN padding).
% - Includes GUI controls to change X-Window (ms) and Y-Limit (µV).
%
% USAGE:
%   spreadsheet_to_gui("events.xlsx", "data.mat")
%   spreadsheet_to_gui("events.xlsx", "data.mat", 'yLimMicroV', 500) % Start with fixed Y
%   spreadsheet_to_gui("events.xlsx", "data.mat", 'channelIndices', 1:32)

% ---------- 1. Input Parsing ----------
p = inputParser;
p.addRequired('excelPath', @(s) isstring(s) || ischar(s));
p.addRequired('dataMatPath', @(s) isstring(s) || ischar(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));
p.addParameter('winHalfWidthMs', 20, @(x)isfinite(x)&&x>0);   % Default: ±20 ms
p.addParameter('yLimMicroV', [], @(x) isempty(x) || (isscalar(x) && x>0)); % Default: auto
p.addParameter('yRobustPct', 99.5, @(x) isfinite(x) && x>0 && x<100);

p.parse(excelPath, dataMatPath, varargin{:});
excelPath    = string(p.Results.excelPath);
dataMatPath  = string(p.Results.dataMatPath);
channelIdx   = p.Results.channelIndices;
scaleToMicroV= p.Results.scaleToMicroV;
winHWms      = p.Results.winHalfWidthMs;
yLimInitial  = p.Results.yLimMicroV;
yRobustPct   = p.Results.yRobustPct;

fprintf('===== spreadsheet_to_gui (v4) =====\n');

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

% ---------- 4. Windowing Setup ----------
HWwin    = max(1, round(winHWms / 1000 * sfx));  % ±plot half-width (in samples)
tRelMs   = (-HWwin:HWwin) / sfx * 1e3;

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
fig = uifigure('Name', 'Spreadsheet-to-GUI Anchor Tool', ...
               'Position', [100 100 1200 800], ...
               'UserData', [], ...
               'CloseRequestFcn', @(src,evt) closeGUI(src));

% Main grid layout
gl = uigridlayout(fig, [11, 4]);
gl.RowHeight = {'1x', '1x', '1x', '1x', '1x', '1x', '1x', '2x', 'fit', 'fit', 30};
gl.ColumnWidth = {'1x', '1x', '1x', '1x'};

% *** BUG FIX: Create a UIPANEL as the container, not UIAXES ***
plotPanel = uipanel(gl);
plotPanel.Layout.Row = [1 8];
plotPanel.Layout.Column = [1 4];
plotPanel.BorderType = 'none'; % Make it invisible
% *** END BUG FIX ***

% --- GUI Controls Row ---
xWinLabel = uilabel(gl, 'Text', 'Window (ms):', 'HorizontalAlignment', 'right');
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
ud.winHalfWidthMs = winHWms; % Store in ms
ud.HWwin = HWwin;             % Store in samples
ud.tRelMs = tRelMs;
ud.yRobustPct = yRobustPct;
ud.plotPanel = plotPanel; % *** BUG FIX: Store panel handle ***
ud.tiledLayout = [];      % Handle to the tiled layout
ud.statusLabel = statusLabel;
ud.yLimEdit = yLimEdit;
ud.PlotHandles = {};      % Cell array for line handles
ud.MidpointLine = [];   % Handle for the midpoint xline
ud.AnchorLine = [];     % Handle for the selected anchor xline
ud.AxesTiles = {};        % Handles to the individual axes tiles
ud.yLimCurrent = yLimInitial; % Will be set on first plot if empty

fig.UserData = ud;

% ---------- 9. Initial Plot ----------
updatePlot(fig);
fprintf('GUI is ready. Please select anchor points.\n');

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
    
    % --- Define plot window (IDEAL) ---
    s0_ideal = mid - ud.HWwin;
    s1_ideal = mid + ud.HWwin;
    
    % --- *** ROBUSTNESS FIX *** ---
    % --- Clamp window to valid data range ---
    s0_plot = max(1, s0_ideal);
    s1_plot = min(ud.nSamp, s1_ideal);
    
    % --- Check for completely invalid window ---
    if s1_plot <= s0_plot
        cla(ud.plotPanel); % Clear the panel
        % Create a temporary axes in the panel to show the error
        ax_err = uiaxes(ud.plotPanel);
        ax_err.Visible = 'off';
        text(ax_err, 0.5, 0.5, sprintf('Event %d: Plot window is invalid.\n(s0=%d, s1=%d)', idx, s0_plot, s1_plot), ...
            'HorizontalAlignment', 'center', 'Color', 'r', 'FontSize', 14);
        ud.statusLabel.Text = sprintf('Event %d of %d (INVALID WINDOW)', idx, height(ud.T_events));
        return;
    end
    
    tRelMs_Mid = (mid - mid) / ud.sfx * 1e3; % This is 0
    
    % --- Plotting ---
    if isempty(ud.PlotHandles)
        % --- First time: Create all axes and plot objects ---
        cla(ud.plotPanel); % Clear the 'loading' text
        
        % *** v4: Set TileSpacing to 'none' for max vertical space ***
        tl = tiledlayout(ud.plotPanel, ud.nCh, 1, 'Padding', 'compact', 'TileSpacing', 'none');
        ud.tiledLayout = tl; % Store handle
        
        ud.AxesTiles = cell(ud.nCh, 1);
        ud.PlotHandles = cell(ud.nCh, 1);
        
        yLimAutoSet = false;
        if isempty(ud.yLimCurrent)
            % Auto-detect Y-Lim from first event's data
            yLimAutoSet = true;
            yLimMax = 0;
        end
        
        for k = 1:ud.nCh
            ax_k = nexttile(tl);
            ch = ud.chList(k);
            sc = ud.scaleVec(ch);
            
            % --- ROBUST DATA EXTRACTION ---
            y_data = double(ud.mf.d(ch, s0_plot:s1_plot)) * sc;
            y_full = nan(1, numel(ud.tRelMs));
            
            % Calculate where this data fits in the full NaN vector
            idx_start_in_y_full = s0_plot - s0_ideal + 1;
            idx_end_in_y_full   = idx_start_in_y_full + (s1_plot - s0_plot);
            
            if idx_start_in_y_full >= 1 && idx_end_in_y_full <= numel(y_full)
                y_full(idx_start_in_y_full:idx_end_in_y_full) = y_data;
            else
                if ~isempty(y_data)
                    y_full(1:numel(y_data)) = y_data(1:numel(y_full));
                end
            end
            % --- END ROBUST EXTRACTION ---

            % *** v4: Increased LineWidth ***
            h = plot(ax_k, ud.tRelMs, y_full, 'Color', [0.1 0.1 0.8], 'LineWidth', 1.5);
            
            if yLimAutoSet
                yy = y_data(isfinite(y_data));
                if ~isempty(yy)
                    p = prctile(abs(yy), ud.yRobustPct);
                    if isfinite(p) && p > yLimMax, yLimMax = p; end
                end
            end
            
            hold(ax_k, 'on');
            grid(ax_k, 'on');
            box(ax_k, 'on');
            xlim(ax_k, [ud.tRelMs(1), ud.tRelMs(end)]);
            
            % *** v4: Remove labels for space ***
            % ylabel(ax_k, '\muV');
            % title(ax_k, ud.chanLabels{k}, 'FontSize', 9, 'FontWeight', 'normal');
            set(ax_k, 'FontSize', 8);
            set(ax_k, 'YTick', []); % Remove Y-ticks
            
            if k < ud.nCh
                set(ax_k, 'XTickLabel', []); % Remove x-labels for all but last
            end
            
            % Set the click callback for this specific tile
            ax_k.ButtonDownFcn = @(src,evt) recordClick(fig, evt);
            
            ud.PlotHandles{k} = h;
            ud.AxesTiles{k} = ax_k;
        end
        xlabel(ax_k, 'Time relative to Midpoint (ms)'); % Keep on last plot
        
        % Set initial Y-Lim
        if yLimAutoSet
            yLimMax = max(10, yLimMax); % v4: Use robust max, no extra padding
            ud.yLimCurrent = [-yLimMax, yLimMax];
            ud.yLimEdit.Value = round(yLimMax); % v4: Set box to actual value
        end
        for k = 1:ud.nCh
            set(ud.AxesTiles{k}, 'YLim', ud.yLimCurrent);
        end
        
        % *** v4: Bug Fix - Create line array ***
        ud.MidpointLine = gobjects(ud.nCh, 1);
        ud.AnchorLine   = gobjects(ud.nCh, 1);
        for k = 1:ud.nCh
            ud.MidpointLine(k) = xline(ud.AxesTiles{k}, tRelMs_Mid, '--k', 'Midpoint', 'LineWidth', 1.5, 'HandleVisibility', 'off');
            ud.AnchorLine(k)   = xline(ud.AxesTiles{k}, NaN, '-r', 'Anchor', 'LineWidth', 2.0, 'HandleVisibility', 'off');
        end
        linkaxes([ud.AxesTiles{:}], 'x');
        
    else
        % --- Subsequent times: Just update XData and YData (FAST) ---
        for k = 1:ud.nCh
            ch = ud.chList(k);
            sc = ud.scaleVec(ch);

            % --- ROBUST DATA EXTRACTION ---
            y_data = double(ud.mf.d(ch, s0_plot:s1_plot)) * sc;
            y_full = nan(1, numel(ud.tRelMs));
            
            idx_start_in_y_full = s0_plot - s0_ideal + 1;
            idx_end_in_y_full   = idx_start_in_y_full + (s1_plot - s0_plot);
            
            if idx_start_in_y_full >= 1 && idx_end_in_y_full <= numel(y_full)
                y_full(idx_start_in_y_full:idx_end_in_y_full) = y_data;
            end
            % --- END ROBUST EXTRACTION ---

            set(ud.PlotHandles{k}, 'XData', ud.tRelMs, 'YData', y_full);
        end
        
        % Reset x-axis limits (in case of zoom/pan or window change)
        xlim(ud.AxesTiles{1}, [ud.tRelMs(1), ud.tRelMs(end)]);
    end
    
    % --- Update Visual Guides (v4: works on array) ---
    set(ud.MidpointLine, 'Value', tRelMs_Mid);
    
    selected_anchor_samp = ud.Results.manual_anchor_samp(idx);
    if isfinite(selected_anchor_samp)
        tRelMs_Anchor = (selected_anchor_samp - mid) / ud.sfx * 1e3;
        set(ud.AnchorLine, 'Value', tRelMs_Anchor, 'Visible', 'on');
    else
        set(ud.AnchorLine, 'Visible', 'off');
    end
    
    % --- Update Status ---
    ud.statusLabel.Text = sprintf('Event %d of %d (Excel Row: %d)', idx, height(ud.T_events), idx);
    
    % Save state
    fig.UserData = ud;
    drawnow('limitrate');
end

% ======================================================================
%                        GUI CALLBACK FUNCTIONS
% ======================================================================

function recordClick(fig, evt)
    ud = fig.UserData;
    idx = ud.CurrentIndex;

    % --- 1. Get click info ---
    clicked_time_ms = evt.IntersectionPoint(1); % Time (ms) relative to midpoint
    
    % --- 2. Get event midpoint sample ---
    onsamp = ud.T_events.onsamp(idx);
    offsamp = ud.T_events.offsamp(idx);
    mid = round((onsamp + offsamp) / 2);
    
    % --- 3. Calculate absolute anchor sample ---
    clicked_samp_rel = round(clicked_time_ms / 1000 * ud.sfx);
    manual_anchor_samp = mid + clicked_samp_rel;
    
    % --- 4. Store the result ---
    ud.Results.manual_anchor_samp(idx) = manual_anchor_samp;
    fprintf('Event %d: Anchor set to sample %d (%.2f ms rel. to mid)\n', idx, manual_anchor_samp, clicked_time_ms);
    
    % --- 5. Save state and advance ---
    fig.UserData = ud;
    goToEvent(fig, idx + 1); % Auto-advance
end

function goToEvent(fig, newIndex)
    ud = fig.UserData;
    numEvents = height(ud.T_events);
    
    if newIndex < 1
        fprintf('Already at first event.\n');
        return;
    end
    
    if newIndex > numEvents
        fprintf('Reached last event. Click "Finish & Save".\n');
        ud.statusLabel.Text = sprintf('Last event! Click "Finish & Save"');
        return;
    end
    
    ud.CurrentIndex = newIndex;
    fig.UserData = ud;
    
    % Update the plot to show the new event
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
    
    % Record NaN for this event
    ud.Results.manual_anchor_samp(idx) = NaN;
    fprintf('Event %d: Skipped (NaN).\n', idx);
    
    % Save state and advance
    fig.UserData = ud;
    goToEvent(fig, idx + 1);
end

function saveClicked(fig)
    ud = fig.UserData;
    
    % Get save path
    [file, path] = uiputfile('*.csv', 'Save Manual Anchors', 'manual_anchors.csv');
    
    if isequal(file, 0) || isequal(path, 0)
        fprintf('Save cancelled.\n');
        return;
    end
    
    fullPath = fullfile(path, file);
    
    try
        writetable(ud.Results, fullPath);
        fprintf('SUCCESS: Manual anchors saved to %s\n', fullPath);
        
        % Ask to close
        selection = uiconfirm(fig, 'Results saved. Close the GUI?', 'Save Complete', ...
                               'Options',{'Close GUI', 'Keep Working'}, ...
                               'DefaultOption', 1, 'Icon', 'success');
        if strcmp(selection, 'Close GUI')
            delete(fig);
        end
        
    catch ME
        uialert(fig, sprintf('Failed to save CSV:\n%s', ME.message), 'Save Error', 'Icon', 'error');
    end
end

function closeGUI(fig)
    % Ask for confirmation before closing
    selection = uiconfirm(fig, 'Are you sure you want to close? Unsaved anchors will be lost.', 'Confirm Close', ...
                       'Options',{'Yes, Close', 'No, Cancel'}, ...
                       'DefaultOption', 2, 'Icon', 'warning');
                   
    if strcmp(selection, 'Yes, Close')
        % Clean up matfile object if it exists
        try
            ud = fig.UserData;
            clear ud.mf;
        catch
            % No UserData yet, or no mf. Fine to close.
        end
        delete(fig);
    end
end

function changeXWindow(fig, src)
    ud = fig.UserData;
    newWinMs = src.Value;
    
    if newWinMs <= 0
        fprintf('Invalid X window. Must be > 0.\n');
        return;
    end
    
    % Update state
    ud.winHalfWidthMs = newWinMs;
    ud.HWwin = max(1, round(newWinMs / 1000 * ud.sfx));
    ud.tRelMs = (-ud.HWwin:ud.HWwin) / ud.sfx * 1e3;
    
    fprintf('X-Window changed to ±%.2f ms\n', newWinMs);
    
    % --- Force a full replot ---
    % We must delete the old layout and all its children
    if ~isempty(ud.tiledLayout) && isvalid(ud.tiledLayout)
        delete(ud.tiledLayout);
    end
    ud.tiledLayout = [];
    ud.PlotHandles = {};
    ud.AxesTiles = {};
    ud.MidpointLine = [];
    ud.AnchorLine = [];
    fig.UserData = ud;
    
    updatePlot(fig); % This will now run the "first time" logic
end

function changeYLim(fig, src)
    % *** v4: Bug Fix - use UserData ***
    ud = fig.UserData;
    newYLim = src.Value;
    
    if newYLim <= 0
        fprintf('Invalid Y-Lim. Must be > 0.\n');
        return;
    end
    
    ud.yLimCurrent = [-newYLim, newYLim];
    fig.UserData = ud;
    
    % Apply to all existing axes
    for k = 1:ud.nCh
        if ~isempty(ud.AxesTiles) && numel(ud.AxesTiles) >= k && isgraphics(ud.AxesTiles{k})
            set(ud.AxesTiles{k}, 'YLim', ud.yLimCurrent);
        end
    end
    fprintf('Y-Lim changed to ±%.2f µV\n', newYLim);
end


% ======================================================================
%                  COPIED FROM YOUR OTHER SCRIPTS
% ======================================================================

function [onSamp, offSamp] = find_event_stamps(T, sfx)
% Robustly finds event sample columns, converting from seconds if needed.
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