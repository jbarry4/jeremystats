function SpikeAvgByChannel(dataMatPath, spikesMatPath, varargin)
% SpikeAvgByEventParticipation
% Group events by how many channels they register on (using ech), from
% most channels -> least (1), and for EACH CHANNEL compute an average
% waveform per group using PEAK anchoring (per-channel, per-event peak).
% Plot mean ± STD in a single panel per figure and save a PNG for every
% (channel, group) pair.
%
% Window: half-width of 30 ms (configurable via 'halfWidthMs')
% Peak polarity: 'abs' | 'pos' | 'neg'
% y-axis: auto (best fit)
%
% Title annotations:
%   - Channel row and CSC label if available
%   - Group descriptor: "events with N participating channel(s)"
%   - #events used for this channel in this group
%   - Peak amplitude of the mean (mV) and STD@peak (mV)
%   - Channel number (CSC##) colored RED if 22 ≤ CSC ≤ 34
%
% Files saved as:
%   GroupAvg_ch###_CSC##_grpNofM_HW<samples>_<ms>.png
%
% EXAMPLE
% SpikeAvgByEventParticipation('.../LL_input_data.mat','.../LLspikes.mat', ...
%    'halfWidthMs',0.030,'peakPolarity','abs','saveDir','C:/tmp/grouped')

% ---- Parse inputs ----
p = inputParser;
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addRequired('spikesMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('halfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);     % 30 ms default
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'})));
p.addParameter('scaleToMV', 1, @(x)isfinite(x)&&x>0);           % AD->mV multiplier
p.addParameter('saveDir','', @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.parse(dataMatPath, spikesMatPath, varargin{:});

halfWidthMs    = p.Results.halfWidthMs;
peakPolarity   = lower(string(p.Results.peakPolarity));
scaleToMV      = p.Results.scaleToMV;
saveDir        = string(p.Results.saveDir);
channelIndices = p.Results.channelIndices;

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
    % If ech missing, assume every event registers on every channel
    ech = true(Nevents, nRows);
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

% --- Build participation counts per event ---
partCount = sum(ech, 2);                 % Nevents x 1
uniqueCounts = sort(unique(partCount), 'descend');

fprintf('Grouping %d events by participation counts: %s\n', Nevents, mat2str(uniqueCounts.'));

for ch = chList
    % Channel label and CSC index if available
    if ~isempty(kept_channels)
        chLabel = sprintf('row %d (CSC%d)', ch, kept_channels(ch));
        cscVal = kept_channels(ch);
    else
        chLabel = sprintf('row %d', ch);
        cscVal = NaN;
    end

    for gi = 1:numel(uniqueCounts)
        k = uniqueCounts(gi);                               % group by K participating channels
        idxGroup = find(partCount==k & ech(:,ch));          % events in this group that include this channel
        if isempty(idxGroup)
            fprintf('Channel %d: no events in group K=%d, skipping.\n', ch, k);
            continue;
        end

        % Collect windows with PEAK anchoring (per-event, per-channel)
        X = collectWindowsPeak(mf, ets(idxGroup,:), ch, peakPolarity, HW, nSamp, scaleToMV);
        if isempty(X)
            fprintf('Channel %d: windows out-of-bounds for group K=%d, skipping.\n', ch, k);
            continue;
        end

        % Mean ± STD
        mu = mean(X, 1, 'omitnan');
        sd = std(X, 0, 1, 'omitnan');

        % Peak metrics (of the mean)
        [peakAmp, sdAtPeak, tAtPeakMs] = peakMetrics(mu, sd, tRelMs);

        % --- Figure (single panel) ---
        f = figure('Color','w','Position',[80 80 980 560],'Visible','off');
        ax = axes('Parent',f); hold(ax,'on'); grid(ax,'on'); box(ax,'on');
        shadedMean(ax, tRelMs, mu, sd);
        xlabel(ax, 'Time relative to PEAK anchor (ms)');
        ylabel(ax, 'Amplitude (mV)');

        % Build title with conditional red CSC number (22..34)
        if ~isnan(cscVal)
            if cscVal>=22 && cscVal<=34
                cscStr = sprintf('\\color{red}CSC%d\\color{black}', cscVal);
            else
                cscStr = sprintf('CSC%d', cscVal);
            end
            chStr = sprintf('row %d (%s)', ch, cscStr);
        else
            chStr = sprintf('row %d', ch);
        end

        ttl = sprintf('PEAK (%s) alignment | %s | group: events with %d participating channel(s) | used: %d | peak=%.3f mV @ %.2f ms, STD@peak=%.3f mV', ...
                      peakPolarity, chStr, k, size(X,1), peakAmp, tAtPeakMs, sdAtPeak);
        title(ax, ttl, 'Interpreter','tex');

        % Save
        if isnan(cscVal)
            cscTag = 'CSCNA';
        else
            cscTag = sprintf('CSC%d', cscVal);
        end
        outPng = fullfile(outDir, sprintf('GroupAvg_ch%03d_%s_grp%dof%d_HW%ds_%dms.png', ...
                             ch, cscTag, gi, numel(uniqueCounts), HW, round(1e3*HW/sfx)));
        exportgraphics(f, outPng, 'Resolution', 220);
        close(f);
        fprintf('Saved: %s\n', outPng);
    end
end

fprintf('Done. Grouped images saved to: %s\n', outDir);

% ====================== helpers ======================
function X = collectWindowsPeak(mf, ets_sub, ch, peakPolarity, HW, nSamp, scaleToMV)
    Ne = size(ets_sub,1);
    winN = 2*HW + 1; %#ok<NASGU>
    X = nan(Ne, 2*HW+1);

    for i = 1:Ne
        s0_ev = max(1, ets_sub(i,1));
        s1_ev = min(nSamp, ets_sub(i,2));
        anchor = localPeakAnchor(mf, ch, s0_ev, s1_ev, peakPolarity);
        s0 = anchor - HW; s1 = anchor + HW;
        if s0 < 1 || s1 > nSamp, continue; end
        y = double(mf.d(ch, s0:s1)) * scaleToMV;
        X(i,:) = y;
    end

    valid = all(isfinite(X),2);
    X = X(valid,:);
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

function shadedMean(ax, x, mu, sd)
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

function [peakAmp, sdAtPeak, tAtPeakMs] = peakMetrics(mu, sd, tRelMs)
    if isempty(mu) || all(~isfinite(mu))
        peakAmp = NaN; sdAtPeak = NaN; tAtPeakMs = NaN; return;
    end
    [~, k] = max(abs(mu));
    peakAmp  = mu(k);
    sdAtPeak = sd(min(k, numel(sd)));
    tAtPeakMs = tRelMs(min(k, numel(tRelMs)));
end

end
