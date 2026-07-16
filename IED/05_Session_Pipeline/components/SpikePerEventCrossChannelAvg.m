function SpikePerEventCrossChannelAvg(dataMatPath, spikesMatPath, varargin)
% SpikePerEventCrossChannelAvg
% For EACH detected event, compute cross-channel averages (not across events):
%   - ref-only        (reference channel waveform)
%   - ±8 channels     (avg across rows [ref-8 .. ref+8], clipped to valid)
%   - ±16 channels
%   - all channels    (avg across all rows of d)
%
% Alignment options per event:
%   - 'midpoint' : center = (on+off)/2
%   - 'peak'     : center at per-event, per-reference-channel peak
%                  (peakPolarity='abs' | 'pos' | 'neg')
%
% Reference channel selection per event:
%   - 'maxabs' (default): among involved rows, pick the one with largest |peak| within the event
%   - 'first'           : pick the first involved row
%
% NEW: semi-transparent ribbons for each curve (nice overlays).
%
% Usage:
%   SpikePerEventCrossChannelAvg( ...
%       'C:\...\LL_input_..._mex_disk.mat', ...
%       'C:\...\LL_input_..._LLspikes_YYYYMMDD_HHMMSS.mat', ...
%       'preSec',0.25,'postSec',0.25, ...
%       'align','peak','peakPolarity','abs', ...
%       'refChoice','maxabs', ...
%       'alphaFill',0.25,'bandFrac',0.06,'lineWidth',1.6, ...
%       'eventIndices',[], 'maxEvents',Inf, ...
%       'saveDir','' );

%% ---- Parse inputs ----
p = inputParser;
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addRequired('spikesMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('preSec', 0.25, @(x)isfinite(x)&&x>0);
p.addParameter('postSec', 0.25, @(x)isfinite(x)&&x>0);
p.addParameter('align','peak', @(s) any(strcmpi(s,{'peak','midpoint'})));
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'})));
p.addParameter('refChoice','maxabs', @(s) any(strcmpi(s,{'maxabs','first'})));
p.addParameter('eventIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('maxEvents', Inf, @(x) isfinite(x) || isinf(x));
p.addParameter('saveDir','', @(s)ischar(s)||isstring(s));
% new style params
p.addParameter('alphaFill', 0.25, @(x)isfinite(x)&&x>=0&&x<=1);
p.addParameter('bandFrac',  0.06, @(x)isfinite(x)&&x>0);
p.addParameter('lineWidth', 1.6,  @(x)isfinite(x)&&x>0);
p.parse(dataMatPath, spikesMatPath, varargin{:});

preSec       = p.Results.preSec;
postSec      = p.Results.postSec;
alignMode    = lower(string(p.Results.align));
peakPolarity = lower(string(p.Results.peakPolarity));
refChoice    = lower(string(p.Results.refChoice));
eventIndices = p.Results.eventIndices;
maxEvents    = p.Results.maxEvents;
saveDir      = string(p.Results.saveDir);
alphaFill    = p.Results.alphaFill;
bandFrac     = p.Results.bandFrac;
lineWidth    = p.Results.lineWidth;

if ~isfile(dataMatPath), error('Data MAT not found: %s', dataMatPath); end
if ~isfile(spikesMatPath), error('Spikes MAT not found: %s', spikesMatPath); end

%% ---- Open data & spikes ----
mf = matfile(dataMatPath);
try
    sfx           = mf.sfx;
    kept_channels = mf.kept_channels;      % original CSC numbers for each row of d
catch
    error('Missing sfx/kept_channels in data file. Use the provided converter.');
end
nRows  = size(mf,'d',1);
nSamp  = size(mf,'d',2);

S = load(spikesMatPath,'ets','ech');
if ~isfield(S,'ets') || ~isfield(S,'ech')
    error('Spikes file must contain ets and ech.');
end
ets = S.ets;             % [N x 2] event on/off (samples)
ech = S.ech;             % [N x nRows] logical: rows involved per event
Nevents = size(ets,1);
if size(ech,2) ~= nRows
    if size(ech,2) < nRows, ech(:,end+1:nRows) = false; else, ech = ech(:,1:nRows); end
end

% Choose output directory
if saveDir == ""
    [outDir, ~, ~] = fileparts(dataMatPath);
else
    outDir = char(saveDir);
end
if ~exist(outDir,'dir'), mkdir(outDir); end

% Time axis window
preN  = max(1, round(preSec  * sfx));
postN = max(1, round(postSec * sfx));
winN  = preN + postN + 1;
tRel  = (-preN:postN) / sfx;

% Which events to process
if isempty(eventIndices)
    evList = (1:Nevents).';
else
    evList = eventIndices(:);
    evList = evList(evList>=1 & evList<=Nevents);
end
if isfinite(maxEvents)
    evList = evList(1:min(numel(evList), maxEvents));
end
fprintf('Processing %d event(s) out of %d total.\n', numel(evList), Nevents);

%% ---- Main loop over events ----
for ii = 1:numel(evList)
    ei = evList(ii);
    rowsInvolved = find(ech(ei,:));
    if isempty(rowsInvolved), continue; end

    % ----- pick reference row for this event -----
    switch refChoice
        case "first"
            refRow = rowsInvolved(1);
        otherwise % "maxabs"
            [~, refRow] = pickMaxAbsRow(mf, rowsInvolved, ets(ei,:), peakPolarity);
    end
    refCSC = kept_channels(refRow);

    % ----- anchor selection -----
    switch alignMode
        case "midpoint"
            anchor = round( (ets(ei,1) + ets(ei,2))/2 );
        otherwise % 'peak' on reference row within event
            s0_ev = max(1,  ets(ei,1));
            s1_ev = min(nSamp, ets(ei,2));
            anchor = findPeakAnchor(mf, refRow, s0_ev, s1_ev, peakPolarity);
    end

    % window around anchor
    s0 = anchor - preN;  s1 = anchor + postN;
    if s0 < 1 || s1 > nSamp
        fprintf('Event %d skipped (window out of bounds)\n', ei);
        continue;
    end

    % ----- groups -----
    grp1 = refRow;
    grp2 = clampIdx((refRow-8):(refRow+8), nRows);
    grp3 = clampIdx((refRow-16):(refRow+16), nRows);
    grp4 = 1:nRows;

    % ----- averages -----
    A_ref  = meanRowsWindow(mf, grp1, s0, s1);
    A_pm8  = meanRowsWindow(mf, grp2, s0, s1);
    A_pm16 = meanRowsWindow(mf, grp3, s0, s1);
    A_all  = meanRowsWindow(mf, grp4, s0, s1);

    % ----- plot with transparency -----
    f = figure('Color','w','Position',[80 80 1100 520], 'Visible','off');
    ax = axes('Parent',f,'SortMethod','childorder'); hold(ax,'on'); grid(ax,'on'); box(ax,'on');

    cols = lines(4);
    % draw farthest group first (back), ref on top (front)
    plotTransLine(ax, tRel, A_all,  cols(4,:), alphaFill, lineWidth, bandFrac);
    plotTransLine(ax, tRel, A_pm16, cols(3,:), alphaFill, lineWidth, bandFrac);
    plotTransLine(ax, tRel, A_pm8,  cols(2,:), alphaFill, lineWidth, bandFrac);
    plotTransLine(ax, tRel, A_ref,  cols(1,:), alphaFill, lineWidth, bandFrac);

    xline(ax, 0, '--k','LineWidth',1.2);
    yline(ax, 0, ':','Color',[0.6 0.6 0.6]);

    xlabel(ax, 'Time relative to anchor (s)');
    ylabel(ax, 'Amplitude (AD counts)');
    ttl = sprintf('Event %d  |  ref: row %d (CSC%d)  |  align=%s', ei, refRow, refCSC, alignMode);
    title(ax, ttl);
    legend(ax, {'all','\pm16','\pm8','ref-only'}, 'Location','best');
    xlim(ax, [tRel(1) tRel(end)]);

    % name & save
    outPng = fullfile(outDir, sprintf('EventAvg_e%04d_refCSC%d_align-%s_pre%.3f_post%.3f_alpha%.2f.png', ...
                        ei, refCSC, alignMode, preSec, postSec, alphaFill));
    exportgraphics(ax, outPng, 'Resolution', 220);
    close(f);

    if mod(ii,25)==0 || ii==numel(evList)
        fprintf('Saved %d/%d (last: %s)\n', ii, numel(evList), outPng);
    end
end

fprintf('Done. Images saved to: %s\n', outDir);

%% ====================== helpers ======================
function idx = clampIdx(idx, nMax)
    idx = idx(idx>=1 & idx<=nMax);
end

function [maxAbsVal, bestRow] = pickMaxAbsRow(mf, rows, evWin, polarity)
    s0 = max(1, evWin(1)); s1 = min(size(mf,'d',2), evWin(2));
    maxAbsVal = -Inf; bestRow = rows(1);
    for r = rows(:)'
        y = double(mf.d(r, s0:s1));
        switch lower(polarity)
            case 'pos', v = max(y);
            case 'neg', v = -min(y);
            otherwise,   v = max(abs(y)); % 'abs'
        end
        if v > maxAbsVal
            maxAbsVal = v; bestRow = r;
        end
    end
end

function anchor = findPeakAnchor(mf, row, s0, s1, polarity)
    y = double(mf.d(row, s0:s1));
    switch lower(polarity)
        case 'pos', [~,k] = max(y);
        case 'neg', [~,k] = min(y);
        otherwise,  [~,k] = max(abs(y));
    end
    anchor = s0 + k - 1;
end

function wavg = meanRowsWindow(mf, rows, s0, s1)
    if numel(rows)==1
        Y = double(mf.d(rows, s0:s1));
        wavg = Y(:).';  return;
    end
    Y = double(mf.d(rows, s0:s1));   % nSel x winN
    M = isfinite(Y);
    if any(~M,'all')
        numer = sum(Y .* M, 1);
        denom = sum(M, 1);  denom(denom==0) = 1;
        wavg = numer ./ denom;
    else
        wavg = mean(Y, 1);
    end
end

function plotTransLine(ax, x, y, colorRGB, alphaFill, lineW, bandFrac)
    % Draw a semi-transparent ribbon around y, then a crisp line on top.
    y = y(:).';
    x = x(:).';
    if numel(x) ~= numel(y), error('x/y length mismatch'); end
    yr = max(y) - min(y);
    if ~isfinite(yr) || yr==0
        % fallback thickness from signal roughness
        dy = abs(diff(y)); dy(~isfinite(dy)) = 0;
        yr = max(1, median(dy)*10);
    end
    band = max( eps, bandFrac * yr );
    yu = y + band/2;
    yl = y - band/2;
    xp = [x; flipud(x)];
    yp = [yu; flipud(yl)];
    patch('Parent',ax, 'XData',xp, 'YData',yp, ...
          'FaceColor',colorRGB, 'FaceAlpha',alphaFill, ...
          'EdgeColor','none', 'HandleVisibility','off');
    plot(ax, x, y, 'Color', colorRGB, 'LineWidth', lineW);
end

end
