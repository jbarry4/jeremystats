function SpikeAvgByChannel(dataMatPath, spikesMatPath, varargin)
% SpikeAvgAcrossChannelsPerEvent
% Rank events by how many channels they appear on, then for each event:
%   • Collect waveforms ONLY from channels where the event appears (ech==true)
%   • Align each channel’s window to its per-channel peak within the event
%   • Plot (1) mean ± SEM (shaded) and (2) overlap of all channel waveforms
%       - In the overlap panel, the mean is bold; individual traces are thin,
%         pastel (simulated ~50% opacity). Channels 22–34 are colored RED.
%   • Annotate the figure with the channel list and the number of channels.
%
% Inputs (like your previous function):
%   dataMatPath: MAT file with fields:
%       - d  [nRows x nSamp] numeric
%       - sfx (scalar, samples/second)
%       - kept_channels (optional) mapping row->CSC#
%   spikesMatPath: MAT with fields:
%       - ets [N x 2] event on/off sample indices (inclusive start, inclusive end ok)
%       - ech [N x nRows] logical event-by-channel mask (optional -> defaults to all true)
%
% Name-Value options:
%   'halfWidthMs' (double) default 30e-3   % 30 ms half-window
%   'peakPolarity' ('abs'|'pos'|'neg') default 'abs'
%   'scaleToMV' (double) default 1         % multiply AD units -> mV
%   'saveDir' (char/string) default: alongside dataMatPath
%
% Saves one PNG per event in rank order:  Rank###_EvtNNN_HW<samples>_<ms>.png

% ---------------- Parse inputs ----------------
p = inputParser;
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addRequired('spikesMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('halfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'})));
p.addParameter('scaleToMV', 1, @(x)isfinite(x)&&x>0);
p.addParameter('saveDir','', @(s)ischar(s)||isstring(s));
p.parse(dataMatPath, spikesMatPath, varargin{:});

halfWidthMs  = p.Results.halfWidthMs;
peakPolarity = lower(string(p.Results.peakPolarity));
scaleToMV    = p.Results.scaleToMV;
saveDir      = string(p.Results.saveDir);

% ---------------- Load data ----------------
if ~isfile(dataMatPath), error('Data MAT not found: %s', dataMatPath); end
if ~isfile(spikesMatPath), error('Spikes MAT not found: %s', spikesMatPath); end

mf = matfile(dataMatPath);
try
    sfx = mf.sfx;    % samples/sec
catch
    error('Sampling rate "sfx" missing in data MAT.');
end
nRows = size(mf,'d',1);
nSamp = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end

S = load(spikesMatPath,'ets','ech');
if ~isfield(S,'ets'), error('Spikes MAT must contain ets [N x 2].'); end
ets = S.ets;
Nevents = size(ets,1);

if isfield(S,'ech')
    ech = S.ech;
    % Pad/clip if mismatch:
    if size(ech,2) ~= nRows
        if size(ech,2) < nRows, ech(:,end+1:nRows) = false; else, ech = ech(:,1:nRows); end
    end
else
    ech = true(Nevents, nRows); % If missing, treat as present on all channels
end

% ---------------- Rank events by channel count ----------------
chCounts = sum(ech, 2);
[~, sortIdx] = sortrows([-chCounts, (1:Nevents)']); % desc by count, tie by original order
HW = max(1, round(halfWidthMs * sfx));              % half-width in samples
tRelSamples = -HW:HW;
tRelMs = (tRelSamples / sfx) * 1e3;

% ---------------- Output dir ----------------
if saveDir == ""
    [outDir,~,~] = fileparts(dataMatPath);
else
    outDir = char(saveDir);
end
if ~exist(outDir,'dir'), mkdir(outDir); end

fprintf('Ranking %d events by channel count (half-width=%d samples, %.2f ms)\n', ...
         Nevents, HW, 1e3*HW/sfx);

% ---------------- Iterate events in rank order ----------------
for r = 1:Nevents
    e = sortIdx(r);
    chMask = ech(e,:);                 % logical [1 x nRows]
    chList = find(chMask);             % numeric list of channels for this event
    nCh    = numel(chList);

    if nCh == 0
        fprintf('Rank %03d (Evt %03d): no channels marked, skipping.\n', r, e);
        continue;
    end

    % Collect aligned windows (per-channel peak within the event window)
    [X, usedCh] = collectEventChannelWindows(mf, ets(e,:), chList, peakPolarity, HW, nSamp, scaleToMV);

    if isempty(X)
        fprintf('Rank %03d (Evt %03d): no valid windows inside data bounds, skipping.\n', r, e);
        continue;
    end

    mu = mean(X, 1, 'omitnan');
    se = std(X, 0, 1, 'omitnan') ./ max(1, sqrt(size(X,1)));

    % Peak metrics (of the mean)
    [peakAmp, semAtPeak, kpk] = peakMetrics(mu, se);
    anchorms = tRelMs(kpk);

    % --------- Build figure: 2x1 ---------
    f = figure('Color','w','Position',[80 80 1100 820],'Visible','off');

    % (1) Mean ± SEM shaded
    ax1 = subplot(2,1,1,'Parent',f); hold(ax1,'on'); grid(ax1,'on'); box(ax1,'on');
    shadedMean(ax1, tRelMs, mu, se);
    title(ax1, sprintf('Rank %03d (Evt %03d)  |  Channels used: %d', r, e, size(X,1)));
    ylabel(ax1,'Amplitude (mV)');
    xlabel(ax1,'Time relative to per-channel peak (ms)');
    annotatePeak(ax1, peakAmp, semAtPeak, anchorms);

    % (2) Overlap of individual channel waveforms (thin), mean bold
    ax2 = subplot(2,1,2,'Parent',f); hold(ax2,'on'); grid(ax2,'on'); box(ax2,'on');
    % Color map for individuals
    baseColors = lines(max(size(X,1), 8));
    % Draw each channel trace; channels 22–34 are RED
    for i = 1:numel(usedCh)
        ch = usedCh(i);
        y  = X(i,:);
        if ~isempty(kept_channels) && kept_channels(ch) >= 22 && kept_channels(ch) <= 34
            c = [0.85 0.10 0.10]; % strong red for these channels
        else
            c = pastelize(baseColors(1+mod(i-1,size(baseColors,1)),:), 0.5); % ~50% opacity look
        end
        plot(ax2, tRelMs, y, 'Color', c, 'LineWidth', 0.8);
    end
    % Mean in bold
    plot(ax2, tRelMs, mu, 'k', 'LineWidth', 2.0);
    yline(ax2,0,':','Color',[0.6 0.6 0.6]); xline(ax2,0,'--k','LineWidth',1.0);
    xlabel(ax2,'Time relative to per-channel peak (ms)');
    ylabel(ax2,'Amplitude (mV)');
    title(ax2, 'Overlap: individual channel waveforms (thin) + mean (bold)');

    % Channel list annotation (tiny font); channels 22–34 shown in red
    chanLabel = channelLabelString(usedCh, kept_channels);
    text(ax2, 0.01, 0.98, sprintf('\\fontsize{7}Channels (%d): %s', numel(usedCh), chanLabel), ...
        'Units','normalized','Interpreter','tex', 'VerticalAlignment','top', ...
        'BackgroundColor','w', 'Margin',3, 'EdgeColor',[0.85 0.85 0.85]);

    % Save
    outPng = fullfile(outDir, sprintf('Rank%03d_Evt%03d_HW%ds_%dms.png', ...
                                      r, e, HW, round(1e3*HW/sfx)));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved: %s  (channels: %d)\n', outPng, numel(usedCh));
end

fprintf('Done. Output directory: %s\n', outDir);

% ====================== Helpers ======================

function [X, usedCh] = collectEventChannelWindows(mf, ets_row, chList, peakPolarity, HW, nSamp, scaleToMV)
% Returns [nChUsed x (2*HW+1)] matrix X and the channel numbers used
    winN = 2*HW + 1;
    s0_ev = max(1, ets_row(1));
    s1_ev = min(nSamp, ets_row(2));
    X = [];
    usedCh = [];

    for ch = chList(:).'
        anchor = localPeakAnchor(mf, ch, s0_ev, s1_ev, peakPolarity);
        s0 = anchor - HW; s1 = anchor + HW;
        if s0 < 1 || s1 > nSamp, continue; end
        y = double(mf.d(ch, s0:s1)) * scaleToMV;
        if any(~isfinite(y)), continue; end
        X(end+1, :) = y; %#ok<AGROW>
        usedCh(end+1,1) = ch; %#ok<AGROW>
    end
end

function anchor = localPeakAnchor(mf, row, s0, s1, polarity)
    y = double(mf.d(row, s0:s1));
    switch lower(polarity)
        case 'pos', [~,k] = max(y);
        case 'neg', [~,k] = min(y);
        otherwise,  [~,k] = max(abs(y)); % 'abs'
    end
    anchor = s0 + k - 1;
end

function shadedMean(ax, x, mu, se)
    if isempty(mu) || all(~isfinite(mu)), return; end
    yu = mu + se; yl = mu - se;
    xp = [x, fliplr(x)];
    yp = [yu, fliplr(yl)];
    patch('Parent',ax,'XData',xp,'YData',yp, ...
          'FaceColor',[0.3 0.3 0.9],'FaceAlpha',0.25, ...
          'EdgeColor','none','HandleVisibility','off');
    plot(ax, x, mu, 'LineWidth', 1.8);
    yline(ax,0,':','Color',[0.6 0.6 0.6]); xline(ax,0,'--k','LineWidth',1.0);
end

function [peakAmp, semAtPeak, k] = peakMetrics(mu, se)
    if isempty(mu) || all(~isfinite(mu))
        peakAmp = NaN; semAtPeak = NaN; k = 1; return;
    end
    [~, k] = max(abs(mu));
    peakAmp  = mu(k);
    if isempty(se) || all(~isfinite(se)), semAtPeak = NaN; else, semAtPeak = se(k); end
end

function c2 = pastelize(c, alphaFrac)
% Simulate ~alpha by blending with white: c2 = (1-alpha)*c + alpha*1
    a = min(max(alphaFrac,0),1);
    c2 = (1-a)*c + a*[1 1 1];
end

function s = channelLabelString(chs, kept_channels)
% Build tiny TeX string; channels 22–34 in red. Include CSC labels if present.
    parts = cell(1, numel(chs));
    for i = 1:numel(chs)
        ch = chs(i);
        if ~isempty(kept_channels)
            lab = sprintf('row %d (CSC%d)', ch, kept_channels(ch));
        else
            lab = sprintf('row %d', ch);
        end
        if ~isempty(kept_channels) && kept_channels(ch) >= 22 && kept_channels(ch) <= 34
            parts{i} = sprintf('\\color{red}%s\\color{black}', lab);
        else
            parts{i} = lab;
        end
    end
    % Join with commas, insert newlines every ~10 items for readability
    maxPerLine = 10;
    lines = {};
    for i = 1:max(1,ceil(numel(parts)/maxPerLine))
        idx = ( (i-1)*maxPerLine + 1 ) : min(i*maxPerLine, numel(parts));
        lines{end+1} = strjoin(parts(idx), ', '); %#ok<AGROW>
    end
    s = strjoin(lines, '\newline ');
end

function annotatePeak(ax, peakAmp, semAtPeak, t_ms)
    txt = sprintf('Mean peak = %.3f mV @ %.2f ms\\newlineSEM@peak = %.3f mV', ...
                  peakAmp, t_ms, semAtPeak);
    text(ax, 0.02, 0.95, txt, 'Units','normalized', ...
         'VerticalAlignment','top', 'FontSize',9, ...
         'BackgroundColor','w', 'Margin',3, 'EdgeColor',[0.85 0.85 0.85], ...
         'Interpreter','tex');
end

end
