function SpikeAvgPerChannelCompare(dataMatPath, spikesMatPath, varargin)
% SpikeAvgPerChannelCompare
% For EACH channel, compute average event-aligned waveform across spikes
% twice: (1) align to event midpoint, (2) align to per-channel peak.
% Plot mean ± SEM for both in a 2x1 figure and save one PNG per channel.
%
% Window: half-width of 30 ms (configurable via 'halfWidthMs')
% Fixed y-axis: [-2, 2] mV (configurable via 'yLimMV')
% Peak polarity for 'peak' alignment: 'abs'|'pos'|'neg'
%
% Events included for a channel:
%   - If 'ech' exists: only events where ech(e, ch)==true
%   - Else: all events are included for every channel
%
% EXAMPLE
% SpikeAvgPerChannelCompare('...\LL_input_data.mat','...\LLspikes.mat',...
%     'halfWidthMs',0.030,'yLimMV',[-2 2],'peakPolarity','abs',...
%     'saveDir','C:\tmp\perChannelCompare');

% ---- Parse inputs ----
p = inputParser;
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addRequired('spikesMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('halfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);     % 30 ms default
p.addParameter('yLimMV', [0 3000], @(v)isnumeric(v)&&numel(v)==2&&v(1)<v(2));
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'})));
p.addParameter('scaleToMV', 1, @(x)isfinite(x)&&x>0);           % AD->mV multiplier
p.addParameter('saveDir','', @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.parse(dataMatPath, spikesMatPath, varargin{:});

halfWidthMs   = p.Results.halfWidthMs;
yLimMV        = p.Results.yLimMV;
peakPolarity  = lower(string(p.Results.peakPolarity));
scaleToMV     = p.Results.scaleToMV;
saveDir       = string(p.Results.saveDir);
channelIndices= p.Results.channelIndices;

% ---- Open data & spikes ----
if ~isfile(dataMatPath), error('Data MAT not found: %s', dataMatPath); end
if ~isfile(spikesMatPath), error('Spikes MAT not found: %s', spikesMatPath); end

mf = matfile(dataMatPath);
try
    sfx = mf.sfx;        % samples/sec
catch
    error('Sampling rate "sfx" is required to convert ms -> samples.');
end
HW = max(1, round(halfWidthMs * sfx));   % half-width in samples

% Optional channel labels
try kept_channels = mf.kept_channels; catch, kept_channels = []; end

nRows = size(mf,'d',1);
nSamp = size(mf,'d',2);

S = load(spikesMatPath,'ets','ech');
if ~isfield(S,'ets')
    error('Spikes file must contain ets (Nx2 on/off in samples).');
end
ets = S.ets;
Nevents = size(ets,1);

if isfield(S,'ech')
    ech = S.ech;
    if size(ech,2) ~= nRows
        if size(ech,2) < nRows, ech(:,end+1:nRows) = false; else, ech = ech(:,1:nRows); end
    end
else
    ech = true(Nevents, nRows); % include all events per channel
end

% Output directory
if saveDir == ""
    [outDir, ~, ~] = fileparts(dataMatPath);
else
    outDir = char(saveDir);
end
if ~exist(outDir,'dir'), mkdir(outDir); end

% Channels to process
if isempty(channelIndices)
    chList = 1:nRows;
else
    chList = channelIndices(:).';
    chList = chList(chList>=1 & chList<=nRows);
end

% Time axis in ms
tRelSamples = -HW:HW;
tRelMs = (tRelSamples / sfx) * 1e3;
winN = numel(tRelSamples);

fprintf('Comparing midpoint vs peak for %d channel(s) over up to %d events. HW=%d samples (%.2f ms)\n', ...
        numel(chList), Nevents, HW, 1e3*HW/sfx);

% ---- Main per-channel loop ----
for ch = chList
    % Build matrices for both alignment modes
    [X_mid, nUsed_mid] = collectWindows(mf, ets, ech(:,ch), ch, 'midpoint', peakPolarity, HW, nSamp, scaleToMV);
    [X_peak, nUsed_peak] = collectWindows(mf, ets, ech(:,ch), ch, 'peak',     peakPolarity, HW, nSamp, scaleToMV);

    if nUsed_mid == 0 && nUsed_peak == 0
        fprintf('Channel %d: no valid event windows, skipping.\n', ch);
        continue;
    end

    % Mean ± SEM
    mu_mid = mean(X_mid, 1, 'omitnan');  se_mid = std(X_mid, 0, 1, 'omitnan') ./ max(1,sqrt(nUsed_mid));
    mu_pk  = mean(X_peak,1, 'omitnan');  se_pk  = std(X_peak,0, 1, 'omitnan') ./ max(1,sqrt(nUsed_peak));

    % --- Figure: 2x1 (midpoint on top, peak on bottom) ---
    f = figure('Color','w','Position',[80 80 950 700],'Visible','off');

    % Top: midpoint
    ax1 = subplot(2,1,1,'Parent',f); hold(ax1,'on'); grid(ax1,'on'); box(ax1,'on');
    shadedMean(ax1, tRelMs, mu_mid, se_mid);
    commonAxes(ax1, yLimMV, tRelMs);
    if ~isempty(kept_channels), chLabel = sprintf('row %d (CSC%d)', ch, kept_channels(ch));
    else, chLabel = sprintf('row %d', ch); end
    title(ax1, sprintf('MIDPOINT alignment  |  %s  |  events used: %d', chLabel, nUsed_mid));

    % Bottom: peak
    ax2 = subplot(2,1,2,'Parent',f); hold(ax2,'on'); grid(ax2,'on'); box(ax2,'on');
    shadedMean(ax2, tRelMs, mu_pk, se_pk);
    commonAxes(ax2, yLimMV, tRelMs);
    xlabel(ax2, 'Time relative to anchor (ms)');
    title(ax2, sprintf('PEAK (%s) alignment  |  %s  |  events used: %d', peakPolarity, chLabel, nUsed_peak));

    % Save
    outPng = fullfile(outDir, sprintf('PerChannelAvgCompare_ch%03d_HW%ds_%dms_ylim[%g_%g].png', ...
                                      ch, HW, round(1e3*HW/sfx), yLimMV(1), yLimMV(2)));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);

    fprintf('Saved: %s\n', outPng);
end

fprintf('Done. Images saved to: %s\n', outDir);

% ====================== helpers ======================
function [X, nUsed] = collectWindows(mf, ets, ech_col, ch, alignMode, peakPolarity, HW, nSamp, scaleToMV)
    Ne = size(ets,1);
    winN = 2*HW + 1;
    X = nan(Ne, winN);

    for e = 1:Ne
        if ~ech_col(e), continue; end   % only events that involve this channel
        s0_ev = max(1, ets(e,1));
        s1_ev = min(nSamp, ets(e,2));

        switch lower(alignMode)
            case 'midpoint'
                anchor = round( (s0_ev + s1_ev)/2 );
            otherwise % 'peak'
                anchor = localPeakAnchor(mf, ch, s0_ev, s1_ev, peakPolarity);
        end

        s0 = anchor - HW;
        s1 = anchor + HW;
        if s0 < 1 || s1 > nSamp, continue; end

        y = double(mf.d(ch, s0:s1)) * scaleToMV;
        X(e,:) = y;
    end

    valid = all(isfinite(X),2);
    X = X(valid,:);
    nUsed = size(X,1);
end

function anchor = localPeakAnchor(mf, row, s0, s1, polarity)
    y = double(mf.d(row, s0:s1));
    switch lower(polarity)
        case 'pos', [~,k] = max(y);
        case 'neg', [~,k] = min(y);
        otherwise,  [~,k] = max(abs(y));
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
    yline(ax,0,':','Color',[0.6 0.6 0.6]);
    xline(ax,0,'--k','LineWidth',1.0);
    ylabel(ax, 'Amplitude (mV)');
end

function commonAxes(ax, yLimMV, tRelMs)
    ylim(ax, yLimMV);
    xlim(ax, [tRelMs(1), tRelMs(end)]);
end

end
