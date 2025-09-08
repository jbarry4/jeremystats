function LLSpikeViewer(dataMatPath, spikesMatPath)
% LLSpikeViewer – Scrollable viewer for CSC data with LLspikedetector overlays.
% - Streams from disk via matfile
% - Multi-select channels, time window slider, prev/next event
% - Highlights events (ets) and indicates which channels were involved (ech)
%
% Usage:
%   LLSpikeViewer('...\LL_input_..._mex_disk.mat');                % auto-find spikes file
%   LLSpikeViewer('...\LL_input_..._mex_disk.mat','...\_LLspikes_*.mat'); % explicit

%% ---------- Load metadata & find spikes file ----------
if nargin < 1 || ~isfile(dataMatPath)
    error('Provide the converted data .mat created by CSCconverter (disk-backed).');
end
mf = matfile(dataMatPath);

% Required fields from conversion:
try
    sfx          = mf.sfx;
    chan_labels  = mf.chan_labels;   % 1 x nTotalCh
    kept_channels= mf.kept_channels; % length = # rows in d
catch
    error('Input data file missing sfx/chan_labels/kept_channels. Use the provided converter.');
end
nRows = size(mf,'d',1);
nSamp = size(mf,'d',2);
durSec= nSamp / sfx;

% Load spikes (ets/ech)
if nargin < 2 || ~isfile(spikesMatPath)
    % Auto-pick first *_LLspikes_*.mat in same folder
    [p,f,~] = fileparts(dataMatPath);
    candidates = dir(fullfile(p, [f '_LLspikes_*.mat']));
    if isempty(candidates)
        error('Could not auto-locate a *_LLspikes_*.mat next to the data file. Provide spikesMatPath explicitly.');
    end
    spikesMatPath = fullfile(p, candidates(1).name);
end
S = load(spikesMatPath, 'ets', 'ech', 'params', 'T');
if ~isfield(S,'ets') || ~isfield(S,'ech')
    error('Spikes file must contain ets and ech.');
end
ets = S.ets;            % [N x 2] on/off (samples)
ech = S.ech;            % [N x nRows] channel involvement (rows of d)
Nevents = size(ets,1);
if size(ech,2) ~= nRows
    warning('ech column count (%d) != rows in d (%d). Attempting to continue.', size(ech,2), nRows);
end

% Build default channel names for plotted rows
rowLabels = arrayfun(@(k) sprintf('CSC%d', kept_channels(k)), 1:nRows, 'UniformOutput', false);

%% ---------- UI setup ----------
f = figure('Name','LLSpikeViewer','Color','w','NumberTitle','off',...
           'Units','normalized','Position',[0.05 0.07 0.9 0.86]);

% Axes for plot
ax = axes('Parent',f,'Position',[0.26 0.12 0.72 0.82]); grid(ax,'on'); box(ax,'on');

% Channel list (multi-select)
uicontrol(f,'Style','text','Units','normalized','Position',[0.02 0.92 0.22 0.04],...
             'String','Channels (rows of d):','HorizontalAlignment','left','BackgroundColor','w','FontWeight','bold');
lst = uicontrol(f,'Style','listbox','Units','normalized','Position',[0.02 0.58 0.22 0.34],...
                'String',rowLabels,'Max',10,'Min',0,'Value',1:min(4,numel(rowLabels)));

% Time window controls
uicontrol(f,'Style','text','Units','normalized','Position',[0.02 0.53 0.22 0.03],...
          'String','Window (sec):','BackgroundColor','w','HorizontalAlignment','left');
edtWin = uicontrol(f,'Style','edit','Units','normalized','Position',[0.02 0.50 0.10 0.035],'String','5');

uicontrol(f,'Style','text','Units','normalized','Position',[0.12 0.53 0.12 0.03],...
          'String','Decimate for view:','BackgroundColor','w','HorizontalAlignment','left');
edtDec = uicontrol(f,'Style','edit','Units','normalized','Position',[0.12 0.50 0.12 0.035],'String','1');

% Slider for position
sld = uicontrol(f,'Style','slider','Units','normalized','Position',[0.26 0.04 0.72 0.04],...
                'Min',0,'Max',max(0,durSec),'Value',0,'SliderStep',[0.001 0.02]);

% Event navigation & options
btnPrev = uicontrol(f,'Style','pushbutton','Units','normalized','Position',[0.02 0.43 0.10 0.05],...
                    'String','<< Prev Event','Callback',@(~,~)jumpEvent(-1));
btnNext = uicontrol(f,'Style','pushbutton','Units','normalized','Position',[0.14 0.43 0.10 0.05],...
                    'String','Next Event >>','Callback',@(~,~)jumpEvent(1));

chkOnlySel = uicontrol(f,'Style','checkbox','Units','normalized','Position',[0.02 0.39 0.22 0.035],...
                       'String','Show only events in selected channels','Value',1,'BackgroundColor','w');

% Event table (list)
evtList = uicontrol(f,'Style','listbox','Units','normalized','Position',[0.02 0.12 0.22 0.26],...
                    'String',eventListStrings(ets,ech,sfx,rowLabels),'Max',1,'Min',0,'Value',1);

% Status text
txt = uicontrol(f,'Style','text','Units','normalized','Position',[0.26 0.09 0.72 0.03],...
                'String','','BackgroundColor','w','HorizontalAlignment','left');

% Callbacks to refresh
lst.Callback     = @(~,~)refreshPlot();
edtWin.Callback  = @(~,~)refreshPlot();
edtDec.Callback  = @(~,~)refreshPlot();
sld.Callback     = @(~,~)refreshPlot();
evtList.Callback = @(~,~)jumpToSelectedEvent();

% Initial draw
refreshPlot();

%% ---------- Nested helper functions ----------
    function refreshPlot()
        % Read UI state
        sel = lst.Value;
        if isempty(sel), sel = 1; end
        winSec = str2double(edtWin.String);     if ~isfinite(winSec) || winSec<=0, winSec = 5; edtWin.String='5'; end
        dec    = round(str2double(edtDec.String)); if ~isfinite(dec) || dec<1, dec = 1; edtDec.String='1'; end
        t0     = sld.Value;
        t1     = min(t0 + winSec, durSec);
        s0     = max(1, floor(t0*sfx)+1);
        s1     = min(nSamp, ceil(t1*sfx));
        xxSec  = (s0:s1)/sfx;

        % Downsample stride for plotting (visual only)
        stride = max(1, dec);

        % Fetch selected rows from disk
        rows = sel(:)';   % rows of d to view
        Y = cell(numel(rows),1);
        for k = 1:numel(rows)
            y = mf.d(rows(k), s0:s1);
            if stride>1
                y = y(1:stride:end);
            end
            Y{k} = double(y);
        end
        if stride>1
            xxSec = xxSec(1:stride:end);
        end

        % Stack with vertical offsets for clarity
        clf(ax); hold(ax,'on');
        offset = 0;
        offsets = zeros(numel(rows),1);
        colors = lines(numel(rows));
        for k = 1:numel(rows)
            y = Y{k};
            yy = y + offset;
            plot(ax, xxSec, yy, 'Color', colors(k,:));
            % label
            text(ax, xxSec(1), offset, sprintf(' %s', rowLabels{rows(k)}), 'VerticalAlignment','bottom','Color',colors(k,:));
            offsets(k) = offset;
            % next baseline offset (use 95th percentile for spacing)
            if ~isempty(y) && all(~isnan(y))
                rng = prctile(abs(y),95);
                offset = offset + (rng*3 + 1);
            else
                offset = offset + 1;
            end
        end

        % Event shading
        onlySel = logical(chkOnlySel.Value);
        evIdx = findEventsOverlapping(t0,t1, rows, onlySel);
        for ei = evIdx(:)'
            tOn  = ets(ei,1)/sfx;
            tOff = ets(ei,2)/sfx;
            % shade full height band over the plot
            patch(ax, [max(tOn,t0) min(tOff,t1) min(tOff,t1) max(tOn,t0)], ...
                     [ax.YLim(1) ax.YLim(1) ax.YLim(2) ax.YLim(2)], ...
                     [0.93 0.96 1.00], 'EdgeColor',[0.6 0.7 1], 'FaceAlpha',0.25, 'LineWidth',0.5);
            % Draw small tick marks on each involved selected channel
            involved = find(ech(ei,:));
            [~, ia]  = intersect(rows, involved); % which of selected rows are involved
            for kk = ia(:)'
                y0 = offsets(kk);
                plot(ax, [tOn tOn], [y0-0.5 y0+0.5], 'Color',[0.2 0.4 1], 'LineWidth',1.2);
            end
        end

        % Cosmetics
        xlabel(ax, 'Time (s)');
        ylabel(ax, 'Amplitude (+offset per channel)');
        title(ax, sprintf('Channels: %s   |   t = %.3f–%.3f s of %.3f s    |   win = %.2f s, dec=%d', ...
            strjoin(rowLabels(rows), ', '), t0, t1, durSec, winSec, dec));
        xlim(ax, [t0 t1]);

        % Status
        set(txt,'String',sprintf('N events total: %d | showing %d overlappers%s', ...
            Nevents, numel(evIdx), ternary(onlySel,' (only selected channels)','')));
        drawnow;
    end

    function idx = findEventsOverlapping(t0,t1, rows, onlySel)
        % Return event indices that overlap [t0,t1] and (if onlySel) involve any of 'rows'
        if isempty(ets)
            idx = [];
            return;
        end
        ton  = ets(:,1)./sfx;
        toff = ets(:,2)./sfx;
        overlaps = (toff >= t0) & (ton <= t1);
        if onlySel
            mask = any(ech(:,rows), 2);
            idx = find(overlaps & mask);
        else
            idx = find(overlaps);
        end
    end

    function jumpEvent(direction)
        % direction = +1 or -1
        t0 = sld.Value;
        ton = ets(:,1)./sfx;
        if direction>0
            nxt = find(ton > t0 + 1e-9, 1, 'first');   % next after current t
            if ~isempty(nxt), sld.Value = max(0, ton(nxt)); end
        else
            prv = find(ton < t0 - 1e-9, 1, 'last');    % previous before current t
            if ~isempty(prv)
                % center just before that event
                winSec = str2double(edtWin.String); if ~isfinite(winSec) || winSec<=0, winSec = 5; end
                sld.Value = max(0, ton(prv) - 0.1*winSec);
            end
        end
        refreshPlot();
    end

    function jumpToSelectedEvent()
        i = evtList.Value;
        if isempty(i) || i<1 || i>size(ets,1), return; end
        tOn = ets(i,1)/sfx;
        sld.Value = max(0, tOn);
        refreshPlot();
    end
end

%% ---------- Utilities ----------
function L = eventListStrings(ets, ech, sfx, rowLabels)
% Build a readable list of events: [#] on_sec  off_sec  dur  | channels...
N = size(ets,1);
L = cell(N,1);
for i = 1:N
    tOn  = ets(i,1)/sfx;
    tOff = ets(i,2)/sfx;
    dur  = tOff - tOn;
    rows = find(ech(i,:));
    chs  = strjoin(rowLabels(rows), ',');
    if numel(chs) > 48
        chs = [chs(1:45) '...'];
    end
    L{i} = sprintf('[%04d]  %8.3f–%8.3f s  (%5.3f s)  |  %s', i, tOn, tOff, dur, chs);
end
if isempty(L)
    L = {'<no events>'};
end
end

function s = ternary(cond, a, b)
if cond, s=a; else, s=b; end
end
