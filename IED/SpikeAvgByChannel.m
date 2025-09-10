function SpikeAvgByChannel(dataMatPath, spikesMatPath, varargin)
% SpikeAvgByParticipation
% For EACH event, average its participating channels (per 'ech') after
% per-channel PEAK alignment within the event window. Sort events by how
% many channels participated (most -> least) and save one PNG per event.
%
% Plots: mean ± STD (not SEM). Title lists CSC#s for included channels;
% CSC22..CSC34 are highlighted red in the title (using TeX color markup).
%
% Inputs (same style as prior utilities):
%   dataMatPath  : MAT with d (rows=channels, cols=samples), sfx, optional kept_channels
%   spikesMatPath: MAT with ets (Nx2 on/off in samples), ech (NxC logical) [optional; else all true]
%
% Name-Value:
%   'halfWidthMs'   (default 30e-3)
%   'peakPolarity'  'abs' | 'pos' | 'neg'   (default 'abs')
%   'scaleToMV'     multiplier to convert AD->mV (default 1)
%   'saveDir'       output directory (default: alongside dataMatPath)
%   'maxEvents'     limit how many events to render (default Inf)
%
% Example:
% SpikeAvgByParticipation('...\LL_input_data.mat','...\LLspikes.mat',...
%   'halfWidthMs',0.030,'peakPolarity','abs','saveDir','C:\tmp\byEvent','scaleToMV',1);

% ---- Parse inputs ----
p = inputParser;
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addRequired('spikesMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('halfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);     % 30 ms default
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'})));
p.addParameter('scaleToMV', 1, @(x)isfinite(x)&&x>0);
p.addParameter('saveDir','', @(s)ischar(s)||isstring(s));
p.addParameter('maxEvents', inf, @(x)isfinite(x)&&x>0);
p.parse(dataMatPath, spikesMatPath, varargin{:});

halfWidthMs  = p.Results.halfWidthMs;
peakPolarity = lower(string(p.Results.peakPolarity));
scaleToMV    = p.Results.scaleToMV;
saveDir      = string(p.Results.saveDir);
maxEvents    = p.Results.maxEvents;

% ---- Load data & spikes ----
if ~isfile(dataMatPath), error('Data MAT not found: %s', dataMatPath); end
if ~isfile(spikesMatPath), error('Spikes MAT not found: %s', spikesMatPath); end

mf = matfile(dataMatPath);
try
    sfx = mf.sfx;             % samples/sec
catch
    error('Sampling rate "sfx" is required.');
end

% Optional channel labels
try kept_channels = mf.kept_channels; catch, kept_channels = []; end

nRows = size(mf,'d',1);
nSamp = size(mf,'d',2);

S = load(spikesMatPath,'ets','ech');
if ~isfield(S,'ets')
    error('Spikes file must contain ets (Nx2 on/off in samples).');
end
ets = S.ets;                % Nx2 [on off]
Nevents = size(ets,1);

if isfield(S,'ech')
    ech = S.ech;
    % pad/clip columns to match nRows
    if size(ech,2) ~= nRows
        if size(ech,2) < nRows, ech(:,end+1:nRows) = false; else, ech = ech(:,1:nRows); end
    end
else
    ech = true(Nevents, nRows);
end

% ---- Set up window/time ----
HW     = max(1, round(halfWidthMs * sfx));     % half-width in samples
tRel   = (-HW:HW) / sfx * 1e3;                 % ms
winN   = numel(tRel);

% ---- Sort events by participation count ----
chCount = sum(ech,2);                 % channels per event
[~, order] = sort(chCount, 'descend');
order = order(:);
if isfinite(maxEvents)
    order = order(1:min(numel(order), maxEvents));
end

% ---- Output directory ----
if saveDir == ""
    [outDir, ~, ~] = fileparts(dataMatPath);
else
    outDir = char(saveDir);
end
if ~exist(outDir,'dir'), mkdir(outDir); end

fprintf('Rendering %d/%d event(s), HW=%d samples (%.2f ms), peakPolarity=%s\n',...
    numel(order), Nevents, HW, 1e3*HW/sfx, peakPolarity);

% ---- Per-event processing ----
for ii = 1:numel(order)
    e = order(ii);
    rows = find(ech(e,:));            % participating channel rows
    K = numel(rows);
    if K==0, continue; end

    % Collect aligned windows for the event across its channels
    X = nan(K, winN);
    s0_ev = max(1, ets(e,1));
    s1_ev = min(nSamp, ets(e,2));

    for k = 1:K
        r = rows(k);
        anchor = localPeakAnchor(mf, r, s0_ev, s1_ev, peakPolarity);
        s0 = anchor - HW; s1 = anchor + HW;
        if s0 < 1 || s1 > nSamp, continue; end
        y = double(mf.d(r, s0:s1)) * scaleToMV;
        X(k,:) = y;
    end

    valid = all(isfinite(X),2);
    X = X(valid,:);
    Kvalid = size(X,1);
    if Kvalid==0
        fprintf('Event %d: no valid channel windows after bounds, skipping.\n', e);
        continue;
    end

    mu  = mean(X,1,'omitnan');
    sd  = std(X,0,1,'omitnan');

    % Peak metrics (of mean)
    [pkAmp, sdAtPk, tPkMs] = peakMetrics(mu, sd, tRel);

    % ---- Figure ----
    f = figure('Color','w','Position',[100 100 950 500],'Visible','off');
    ax = axes('Parent',f); hold(ax,'on'); grid(ax,'on'); box(ax,'on');

    shadedMeanStd(ax, tRel, mu, sd);
    plot(ax, tRel, mu, 'LineWidth', 1.8); %#ok<UNRCH> (line sits on top)

    xlabel(ax, 'Time relative to per-channel peak (ms)');
    ylabel(ax, 'Amplitude (mV)');

    % Build CSC label list with selective red coloring for CSC22..CSC34
    chStr = channelsTitleString(rows, kept_channels);

    title(ax, sprintf('Event %d  |  #ch=%d  |  %s', e, Kvalid, chStr), ...
        'Interpreter','tex');

    % Annotation
    txt = sprintf('Peak = %.3f mV @ %.2f ms\nSTD@peak = %.3f mV', pkAmp, tPkMs, sdAtPk);
    text(ax, 0.02, 0.95, txt, 'Units','normalized', 'VerticalAlignment','top', ...
        'FontSize',10,'BackgroundColor','w','Margin',4,'EdgeColor',[0.85 0.85 0.85]);

    % Save
    outPng = fullfile(outDir, sprintf('EventAvg_e%04d_K%02d_HW%ds_%dms.png', ...
        e, Kvalid, HW, round(1e3*HW/sfx)));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);

    fprintf('Saved: %s\n', outPng);
end

fprintf('Done. Images saved to: %s\n', outDir);

% ====================== helpers ======================
function anchor = localPeakAnchor(mf, row, s0, s1, polarity)
    y = double(mf.d(row, s0:s1));
    switch lower(polarity)
        case 'pos', [~,k] = max(y);
        case 'neg', [~,k] = min(y);
        otherwise,  [~,k] = max(abs(y));
    end
    anchor = s0 + k - 1;
end

function shadedMeanStd(ax, x, mu, sd)
    if isempty(mu) || all(~isfinite(mu)), return; end
    yu = mu + sd; yl = mu - sd;
    xp = [x, fliplr(x)];
    yp = [yu, fliplr(yl)];
    patch('Parent',ax,'XData',xp,'YData',yp, ...
          'FaceColor',[0.3 0.3 0.9],'FaceAlpha',0.25, ...
          'EdgeColor','none','HandleVisibility','off');
    plot(ax, x, mu, 'LineWidth', 1.8);
    yline(ax,0,':','Color',[0.6 0.6 0.6]);
    xline(ax,0,'--k','LineWidth',1.0);
end

function [peakAmp, sdAtPeak, tMs] = peakMetrics(mu, sd, tRel)
    if isempty(mu) || all(~isfinite(mu))
        peakAmp = NaN; sdAtPeak = NaN; tMs = NaN; return;
    end
    [~, k] = max(abs(mu));
    peakAmp = mu(k);
    sdAtPeak = sd(min(k, numel(sd)));
    tMs = tRel(k);
end

function s = channelsTitleString(rows, kept_channels)
    % Build a TeX string like: Channels: [CSC1, CSC2, \color{red}CSC22\color{black}, ...]
    if isempty(rows)
        s = 'Channels: []'; return;
    end
    if ~isempty(kept_channels)
        cscs = kept_channels(rows);   % numeric CSC identifiers
    else
        cscs = rows;                  % fallback: use row index as CSC#
    end
    parts = strings(1,numel(cscs));
    for i = 1:numel(cscs)
        tag = sprintf('CSC%d', cscs(i));
        if cscs(i) >= 22 && cscs(i) <= 34
            parts(i) = sprintf('\\color{red}%s\\color{black}', tag);
        else
            parts(i) = tag;
        end
    end
    s = "Channels: [" + strjoin(parts, ', ') + "]";
    s = char(s);
end

end
