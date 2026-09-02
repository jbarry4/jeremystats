function LLSpikeViewer(dataMatPath, spikesMatPath)
% LLSpikeViewer – Scrollable viewer for CSC data with LLspikedetector overlays.
% Streams from disk (matfile), multi-select channels, time slider, prev/next event,
% event shading, start/end lines, and Y-axis controls (Auto / Lock / Manual).
%
% Usage:
%   LLSpikeViewer('...\LL_input_..._mex_disk.mat');
%   LLSpikeViewer('...\LL_input_..._mex_disk.mat','...\LL_input_..._LLspikes_*.mat');

%% ---------- Load metadata & spikes ----------
if nargin < 1 || ~isfile(dataMatPath)
    error('Provide the converted data .mat created by CSCconverter (disk-backed).');
end
mf = matfile(dataMatPath);

% Required fields from converter
try
    sfx = mf.sfx;
catch
    error('Input data file missing sfx. Use the provided converter.');
end

% Rows present in d (kept channels mapping)
if isprop(mf,'kept_channels')
    kept_channels = mf.kept_channels;      % original channel numbers for rows of d
else
    kept_channels = 1:size(mf,'d',1);
end

nRows  = size(mf,'d',1);
nSamp  = size(mf,'d',2);
durSec = nSamp / sfx;

% Load spikes (ets/ech)
if nargin < 2 || ~isfile(spikesMatPath)
    [p,f,~] = fileparts(dataMatPath);
    candidates = dir(fullfile(p, [f '_LLspikes_*.mat']));
    if isempty(candidates)
        error('Could not auto-locate a *_LLspikes_*.mat next to the data file. Provide spikesMatPath explicitly.');
    end
    % pick the newest by datenum
    [~,ix] = max([candidates.datenum]);
    spikesMatPath = fullfile(p, candidates(ix).name);
end
S = load(spikesMatPath, 'ets', 'ech', 'params', 'T');
if ~isfield(S,'ets') || ~isfield(S,'ech')
    error('Spikes file must contain ets and ech.');
end
ets = S.ets;                   % [N x 2] on/off (samples)
ech = S.ech;                   % [N x nRows] logical
Nevents = size(ets,1);
if size(ech,2) ~= nRows
    warning('ech has %d columns but d has %d rows. Continuing; overlay may be misaligned.', size(ech,2), nRows);
    % pad or trim for robustness
    if size(ech,2) < nRows, ech(:, end+1:nRows) = false; else, ech = ech(:,1:nRows); end
end

% Labels for rows of d (kept channels)
rowLabels = arrayfun(@(k) sprintf('CSC%d', kept_channels(k)), 1:nRows, 'UniformOutput', false);

%% ---------- Build UI ----------
f = figure('Name','LLSpikeViewer','Color','w','NumberTitle','off',...
           'Units','normalized','Position',[0.05 0.07 0.9 0.86]);

ax = axes('Parent',f,'Position',[0.26 0.12 0.72 0.82]); grid(ax,'on'); box(ax,'on');

uicontrol(f,'Style','text','Units','normalized','Position',[0.02 0.92 0.22 0.04],...
          'String','Channels (rows of d):','HorizontalAlignment','left','BackgroundColor','w','FontWeight','bold');

lst = uicontrol(f,'Style','listbox','Units','normalized','Position',[0.02 0.58 0.22 0.34],...
                'String',rowLabels,'Max',10,'Min',0,'Value',1:min(4,numel(rowLabels)));

uicontrol(f,'Style','text','Units','normalized','Position',[0.02 0.53 0.22 0.03],...
          'String','Window (sec):','BackgroundColor','w','HorizontalAlignment','left');
edtWin = uicontrol(f,'Style','edit','Units','normalized','Position',[0.02 0.50 0.10 0.035],'String','5');

uicontrol(f,'Style','text','Units','normalized','Position',[0.12 0.53 0.12 0.03],...
          'String','Decimate for view:','BackgroundColor','w','HorizontalAlignment','left');
edtDec = uicontrol(f,'Style','edit','Units','normalized','Position',[0.12 0.50 0.12 0.035],'String','1');

% Y-axis controls
uicontrol(f,'Style','text','Units','normalized','Position',[0.02 0.345 0.22 0.03],...
          'String','Y-axis mode:','BackgroundColor','w','HorizontalAlignment','left');
popYMode = uicontrol(f,'Style','popupmenu','Units','normalized','Position',[0.02 0.321 0.22 0.035],...
                     'String',{'Auto','Lock current','Manual (use Ymin/Ymax)'},'Value',1);

uicontrol(f,'Style','text','Units','normalized','Position',[0.02 0.285 0.09 0.03],...
          'String','Ymin:','BackgroundColor','w','HorizontalAlignment','left');
edtYmin = uicontrol(f,'Style','edit','Units','normalized','Position',[0.10 0.285 0.14 0.035],'String','');

uicontrol(f,'Style','text','Units','normalized','Position',[0.02 0.247 0.09 0.03],...
          'String','Ymax:','BackgroundColor','w','HorizontalAlignment','left');
edtYmax = uicontrol(f,'Style','edit','Units','normalized','Position',[0.10 0.247 0.14 0.035],'String','');

btnSetLock = uicontrol(f,'Style','pushbutton','Units','normalized','Position',[0.02 0.209 0.22 0.035],...
                       'String','Set Ymin/Ymax from current');

% Slider for position
sld = uicontrol(f,'Style','slider','Units','normalized','Position',[0.26 0.04 0.72 0.04],...
                'Min',0,'Max',max(0,durSec),'Value',0,'SliderStep',[0.001 0.02]);

% Event navigation & options
btnPrev = uicontrol(f,'Style','pushbutton','Units','normalized','Position',[0.02 0.43 0.10 0.05],...
                    'String','<< Prev Event');
btnNext = uicontrol(f,'Style','pushbutton','Units','normalized','Position',[0.14 0.43 0.10 0.05],...
                    'String','Next Event >>');

chkOnlySel = uicontrol(f,'Style','checkbox','Units','normalized','Position',[0.02 0.39 0.22 0.035],...
                       'String','Show only events in selected channels','Value',1,'BackgroundColor','w');

% Event list (click to center on event)
evtList = uicontrol(f,'Style','listbox','Units','normalized','Position',[0.02 0.12 0.22 0.08],...
                    'String',eventListStrings(ets,ech,sfx,rowLabels),'Max',1,'Min',0,'Value',1);

txt = uicontrol(f,'Style','text','Units','normalized','Position',[0.26 0.09 0.72 0.03],...
                'String','','BackgroundColor','w','HorizontalAlignment','left');

% Callbacks
lst.Callback      = @(~,~)refreshPlot();
edtWin.Callback   = @(~,~)refreshPlot();
edtDec.Callback   = @(~,~)refreshPlot();
popYMode.Callback = @(~,~)refreshPlot();
edtYmin.Callback  = @(~,~)refreshPlot();
edtYmax.Callback  = @(~,~)refreshPlot();
btnSetLock.Callback = @(~,~)setYFromCurrent();
sld.Callback      = @(~,~)refreshPlot();
evtList.Callback  = @(~,~)jumpToSelectedEvent();
btnPrev.Callback  = @(~,~)jumpEvent(-1);
btnNext.Callback  = @(~,~)jumpEvent(1);

% Ensure UI is realized, then first draw
drawnow;
refreshPlot();

%% ---------- Nested helpers ----------
    function refreshPlot()
        % selected channels
        sel = getSafeVal(lst, 1);
        if isempty(sel), sel = 1; end

        % window & decimation
        winSec = clampNum(str2double(getSafeStr(edtWin,'5')), 0.001, inf, 5);
        dec    = round(clampNum(str2double(getSafeStr(edtDec,'1')), 1, inf, 1));
        stride = max(1, dec);

        % slider position (start of window)
        t0 = clampNum(getSafeVal(sld, 0), 0, max(0,durSec), 0);
        t1 = min(t0 + winSec, durSec);
        s0 = max(1, floor(t0*sfx)+1);
        s1 = min(nSamp, ceil(t1*sfx));
        xxSec = (s0:s1)/sfx;

        % event filter: only events that include selected channels?
        onlySel = logical(getSafeVal(chkOnlySel, 1));

        % sanitize rows
        rows = sel(:)'; rows(rows<1 | rows>nRows) = [];
        if isempty(rows), rows = 1; end

        % fetch data window from disk
        Y = cell(numel(rows),1);
        for k = 1:numel(rows)
            y = mf.d(rows(k), s0:s1);
            if stride>1, y = y(1:stride:end); end
            Y{k} = double(y);
        end
        if stride>1, xxSec = xxSec(1:stride:end); end

        % ensure axis exists
        if ~isgraphics(ax) || ~strcmp(get(ax,'Type'),'axes')
            ax = axes('Parent',f,'Position',[0.26 0.12 0.72 0.82]); grid(ax,'on'); box(ax,'on');
        end

        % draw
        cla(ax); hold(ax,'on');
        offsets = zeros(numel(rows),1);
        colors = lines(numel(rows));
        offset = 0;

        for k = 1:numel(rows)
            y  = Y{k};
            yy = y + offset;
            plot(ax, xxSec, yy, 'Color', colors(k,:), 'LineWidth', 1.0);
            if ~isempty(xxSec)
                text(ax, xxSec(1), offset, sprintf(' %s', rowLabels{rows(k)}), ...
                    'VerticalAlignment','bottom','Color',colors(k,:));
            end
            offsets(k) = offset;
            if ~isempty(y) && all(~isnan(y))
                rng95 = prctile(abs(y),95);
                offset = offset + (rng95*3 + 1);
            else
                offset = offset + 1;
            end
        end

        % Y-axis mode handling
        yMode = getSafeVal(popYMode, 1); % 1=Auto, 2=Lock current, 3=Manual
        switch yMode
            case 1 % Auto
                % let MATLAB auto-scale, then keep that
                drawnow;
                yl = get(ax,'YLim');
            case 2 % Lock current
                yl = get(ax,'YLim'); % do nothing—keep current
            case 3 % Manual
                ymin = str2double(getSafeStr(edtYmin,''));
                ymax = str2double(getSafeStr(edtYmax,''));
                if isfinite(ymin) && isfinite(ymax) && ymax>ymin
                    yl = [ymin ymax];
                else
                    % fallback to auto if invalid
                    drawnow; yl = get(ax,'YLim');
                end
        end

        % event shading + start/end lines
        evIdx = findEventsOverlapping(t0,t1, rows, onlySel);
        for ei = evIdx(:)'
            tOn  = ets(ei,1)/sfx;  tOff = ets(ei,2)/sfx;
            x0   = max(tOn,t0);    x1   = min(tOff,t1);

            % shaded band
            patch(ax, [x0 x1 x1 x0], [yl(1) yl(1) yl(2) yl(2)], ...
                  [0.93 0.96 1.00], 'EdgeColor',[0.6 0.7 1], 'FaceAlpha',0.25, 'LineWidth',0.5);

            % start/end vertical lines (clear markers)
            line(ax, [tOn tOn], yl, 'Color',[0.15 0.45 0.95], 'LineStyle','-', 'LineWidth',1.6);
            line(ax, [tOff tOff], yl, 'Color',[0.95 0.3 0.3], 'LineStyle','--','LineWidth',1.6);

            % ticks on involved selected rows
            involved = find(ech(ei,:));
            [~, ia]  = intersect(rows, involved);
            for kk = ia(:)'
                y0 = offsets(kk);
                plot(ax, [tOn tOn], [y0-0.5 y0+0.5], 'Color',[0.2 0.4 1], 'LineWidth',1.2);
            end
        end

        xlabel(ax, 'Time (s)');
        ylabel(ax, 'Amplitude (+offset per channel)');
        title(ax, sprintf('Channels: %s   |   t = %.3f–%.3f s of %.3f s    |   win = %.2f s, dec=%d', ...
              strjoin(rowLabels(rows), ', '), t0, t1, durSec, winSec, dec));
        xlim(ax, [t0 t1]); ylim(ax, yl); grid(ax,'on'); box(ax,'on');

        setSafeStr(txt, sprintf('Events total: %d | in view: %d%s | Y-mode: %s', ...
            Nevents, numel(evIdx), iff(onlySel,' (selected ch)',''), yModeName(yMode)));
        drawnow;
    end

    function idx = findEventsOverlapping(t0,t1, rows, onlySel)
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
        % Center the found event in the window
        ton  = ets(:,1)./sfx;
        toff = ets(:,2)./sfx;
        if isempty(ton), return; end

        % current
        t0    = clampNum(getSafeVal(sld, 0), 0, max(0,durSec), 0);
        winSec= clampNum(str2double(getSafeStr(edtWin,'5')), 0.001, inf, 5);

        if direction > 0
            nxt = find(ton > t0 + 1e-9, 1, 'first');   % next after current window start
            if isempty(nxt), return; end
            tCenter = 0.5*(ton(nxt) + toff(nxt));
        else
            prv = find(ton < t0 - 1e-9, 1, 'last');    % previous before current window start
            if isempty(prv), return; end
            tCenter = 0.5*(ton(prv) + toff(prv));
        end

        newStart = clampNum(tCenter - winSec/2, 0, max(0, durSec - winSec), 0);
        setSafeVal(sld, newStart);
        refreshPlot();
    end

    function jumpToSelectedEvent()
        i = max(1, min(size(ets,1), round(getSafeVal(evtList,1))));
        if isempty(ets) || i<1 || i>size(ets,1), return; end
        ton  = ets(i,1)/sfx;
        toff = ets(i,2)/sfx;
        winSec= clampNum(str2double(getSafeStr(edtWin,'5')), 0.001, inf, 5);
        tCenter = 0.5*(ton + toff);
        newStart = clampNum(tCenter - winSec/2, 0, max(0, durSec - winSec), 0);
        setSafeVal(sld, newStart);
        refreshPlot();
    end

    function setYFromCurrent()
        % Snapshot current ylim into manual boxes and switch to Lock current
        yl = get(ax,'YLim');
        setSafeStr(edtYmin, num2str(yl(1)));
        setSafeStr(edtYmax, num2str(yl(2)));
        setSafeVal(popYMode, 2);  % Lock current
        refreshPlot();
    end
end

%% ---------- Utilities ----------
function v = getSafeVal(h, defaultVal)
if nargin<2, defaultVal = []; end
if ~isempty(h) && isgraphics(h)
    v = get(h,'Value');
else
    v = defaultVal;
end
end

function s = getSafeStr(h, defaultStr)
if nargin<2, defaultStr = ''; end
if ~isempty(h) && isgraphics(h)
    s = get(h,'String');
else
    s = defaultStr;
end
end

function setSafeVal(h, v)
if ~isempty(h) && isgraphics(h)
    try, set(h,'Value',v); end
end
end

function setSafeStr(h, s)
if ~isempty(h) && isgraphics(h)
    try, set(h,'String',s); end
end
end

function x = clampNum(x, lo, hi, fallback)
if ~isfinite(x), x = fallback; return; end
x = max(lo, min(hi, x));
end

function s = iff(c,a,b), if c, s=a; else, s=b; end, end

function L = eventListStrings(ets, ech, sfx, rowLabels)
N = size(ets,1);
if N==0, L = {'<no events>'}; return; end
L = cell(N,1);
for i = 1:N
    tOn  = ets(i,1)/sfx;
    tOff = ets(i,2)/sfx;
    dur  = tOff - tOn;
    rows = find(ech(i,:));
    chs  = strjoin(rowLabels(rows), ',');
    if numel(chs) > 64, chs = [chs(1:61) '...']; end
    L{i} = sprintf('[%04d]  %8.3f–%8.3f s  (%5.3f s)  |  %s', i, tOn, tOff, dur, chs);
end
end

function name = yModeName(v)
switch v
    case 1, name='Auto';
    case 2, name='Lock current';
    case 3, name='Manual';
    otherwise, name='?';
end
end
