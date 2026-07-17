function TheVision(dataMatPath, spikesMatPath, varargin)
% TheVision
% Select events that appear on 5–10 channels (inclusive). For each such event:
%   - Extract a window around the event (default anchor = event midpoint or per-channel peak).
%   - Plot ALL channels in a single COLUMN (rows-only), one subplot per channel.
%   - Channels where the event appeared (ech==true) are bold/dark; others thin/light.
%   - Save one PNG per event, include event index and active-channel count in filename.
%
% Units & scaling:
%   - All plotting and labeling are in microvolts (µV).
%   - Use 'scaleToMicroV' to convert raw data units to µV (default 1 = already µV).
%   - Legacy 'scaleToMV' is accepted but DEPRECATED; it is internally converted to µV as (mV * 1000).
%
% Fixed y-axis:
%   - Within each produced figure (event), all subplots share the same y-limits.
%   - Limits are symmetric around zero and based on the max |amplitude| across plotted channels for that event,
%     with a small padding.
%
% Inputs:
%   dataMatPath: MAT with fields d [nRows x nSamp], sfx (Hz), kept_channels (optional)
%   spikesMatPath: MAT with ets [N x 2], ech [N x nRows] (optional)
%
% Name-Value options:
%   'halfWidthMs'    (double) default 30e-3   % 30 ms half-window
%   'align'          ('midpoint'|'peak') default 'midpoint'
%   'peakPolarity'   ('abs'|'pos'|'neg') default 'abs'   % used if align='peak'
%   'scaleToMicroV'  (double) default 1       % multiply raw data to get µV
%   'scaleToMV'      (double) default []      % DEPRECATED; if provided, overrides scaleToMicroV = scaleToMV*1000
%   'saveDir'        (string/char) default: alongside dataMatPath
%   'minCh'          (int) default 6
%   'maxCh'          (int) default 8
%
% NOTE: Layout is forced to one column (rows only).

% ---------- Parse ----------
p = inputParser;
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addRequired('spikesMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('halfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);
p.addParameter('align','midpoint', @(s)any(strcmpi(s,{'midpoint','peak'})));
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'})));
p.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);
p.addParameter('scaleToMV', [], @(x)isempty(x)||(isfinite(x)&&x>0)); % DEPRECATED
p.addParameter('saveDir','', @(s)ischar(s)||isstring(s));
p.addParameter('minCh', 6, @(x)isfinite(x)&&x>=0);
p.addParameter('maxCh', 8, @(x)isfinite(x)&&x>=0);
p.parse(dataMatPath, spikesMatPath, varargin{:});

halfWidthMs   = p.Results.halfWidthMs;
alignMode     = lower(string(p.Results.align));
peakPolarity  = lower(string(p.Results.peakPolarity));
scaleToMicroV = p.Results.scaleToMicroV;
scaleToMV     = p.Results.scaleToMV; % deprecated
saveDir       = string(p.Results.saveDir);
minCh         = p.Results.minCh;
maxCh         = p.Results.maxCh;

% Backward compatibility: if scaleToMV provided, convert to µV and warn
if ~isempty(scaleToMV)
    scaleToMicroV = scaleToMV * 1000; % mV -> µV
    warning('TheVision:DeprecatedArg', ...
        ['''scaleToMV'' is deprecated. Use ''scaleToMicroV'' instead. ', ...
         'Proceeding with scaleToMicroV = scaleToMV*1000 = %g.'], scaleToMicroV);
end

% ---------- Load ----------
if ~isfile(dataMatPath), error('Data MAT not found: %s', dataMatPath); end
if ~isfile(spikesMatPath), error('Spikes MAT not found: %s', spikesMatPath); end

mf = matfile(dataMatPath);
try, sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRows = size(mf,'d',1);
nSamp = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end %#ok<NASGU>

S = load(spikesMatPath,'ets','ech');
if ~isfield(S,'ets'), error('Spikes MAT must contain ets [N x 2].'); end
ets = S.ets;
Nevents = size(ets,1);

if isfield(S,'ech')
    ech = S.ech;
    if size(ech,2) ~= nRows
        if size(ech,2) < nRows, ech(:,end+1:nRows) = false; else, ech = ech(:,1:nRows); end
    end
else
    ech = true(Nevents, nRows); % if missing, treat as present on all channels
end

% ---------- Select events with channel count in [minCh, maxCh] ----------
chCounts = sum(ech,2);
sel = (chCounts >= minCh) & (chCounts <= maxCh);
evtIdx = find(sel);
if isempty(evtIdx)
    fprintf('No events with %d–%d channels.\n', minCh, maxCh);
    return;
end

% ---------- Setup ----------
HW = max(1, round(halfWidthMs * sfx));  % half-width in samples
tRelSamples = -HW:HW; %#ok<NASGU>
tRelMs = (tRelSamples / sfx) * 1e3;

if saveDir==""
    [outDir,~,~] = fileparts(dataMatPath);
else
    outDir = char(saveDir);
end
if ~exist(outDir,'dir'), mkdir(outDir); end

fprintf('Found %d event(s) with %d–%d channels. Window ±%d samples (%.2f ms). ', ...
    numel(evtIdx), minCh, maxCh, HW, 1e3*HW/sfx);
fprintf('Scaling to µV with factor %g.\n', scaleToMicroV);

% ---------- Iterate selected events ----------
for ii = 1:numel(evtIdx)
    e = evtIdx(ii);
    activeMask = ech(e,:);                 % 1 x nRows
    nActive    = sum(activeMask);
    s0_ev = max(1, ets(e,1));
    s1_ev = min(nSamp, ets(e,2));

    % Determine anchor (shared midpoint OR per-channel peak)
    switch alignMode
        case "midpoint"
            anchor = round((s0_ev + s1_ev)/2);
            s0 = anchor - HW; s1 = anchor + HW;
            if s0 < 1 || s1 > nSamp
                fprintf('Evt %d skipped (window out of bounds).\n', e);
                continue;
            end
            % Pre-read all channels in a single call for speed; convert to µV
            Yfull = double(mf.d(:, s0:s1)) * scaleToMicroV;   % [nRows x winN] in µV
            validRow = all(isfinite(Yfull),2);
            usedRows = find(validRow).';
            Y = Yfull(validRow, :); % in µV
        otherwise % 'peak'
            % Per-channel anchor within the event window
            usedRows = [];
            Y = [];
            for ch = 1:nRows
                yseg = double(mf.d(ch, s0_ev:s1_ev));
                if any(~isfinite(yseg)), continue; end
                switch peakPolarity
                    case 'pos', [~,kpk] = max(yseg);
                    case 'neg', [~,kpk] = min(yseg);
                    otherwise,  [~,kpk] = max(abs(yseg));
                end
                a = s0_ev + kpk - 1;
                s0 = a - HW; s1 = a + HW;
                if s0 < 1 || s1 > nSamp, continue; end
                y = double(mf.d(ch, s0:s1)) * scaleToMicroV; % convert to µV
                if any(~isfinite(y)), continue; end
                Y(end+1,:) = y; %#ok<AGROW>  % in µV
                usedRows(end+1) = ch; %#ok<AGROW>
            end
    end

    if isempty(Y)
        fprintf('Evt %d: no valid channel windows, skipping.\n', e);
        continue;
    end

    % ---------- Compute FIXED y-limits for this figure (event), symmetric around 0 ----------
    % Compute FIXED y-limits (symmetric, increasing order)
    maxAbs = max(abs(Y(:)));
    if ~isfinite(maxAbs) || maxAbs==0, maxAbs = 1; end
    pad   = 0.05;                            % 5% padding
    span  = (1+pad) * maxAbs;
    yL    = span * [-1 1];                   % [-span, +span]  <-- increasing
    ylim(yL);


    % ---------- Figure: rows-only (one column) ----------
    nUsed = numel(usedRows);
    nCols = 1;                    % FORCE one column
    nRowsGrid = nUsed;            % one row per channel

    % Figure height scales with number of channels (cap to keep files manageable)
    perRowPx = 90; basePx = 200; maxPx = 5000;
    figH = min(maxPx, basePx + perRowPx * nRowsGrid);
    f = figure('Color','w','Position',[60 60 900 figH],'Visible','off');

    tl = tiledlayout(f, nRowsGrid, nCols, 'Padding','compact', 'TileSpacing','compact');

    for k = 1:nUsed
        ch = usedRows(k);
        nexttile(tl);
        hold on; box on; grid on;

        % Styling: bold/dark if active; thin/light otherwise
        isActive = activeMask(ch);
        if isActive
            lw = 1.4; col = [0 0 0];         % active: bold, dark
        else
            lw = 0.7; col = [0.5 0.5 0.5];   % inactive: thin, gray
        end

        plot(tRelMs, Y(k,:), 'LineWidth', lw, 'Color', col);
        xline(0,'--k','LineWidth',0.8); yline(0,':','Color',[0.7 0.7 0.7]);

        % FIXED y-axis across all subplots in this figure
        ylim(yL);

        titleStr = localTitle(ch, isActive, kept_channels);
        title(titleStr, 'FontSize',8);

        % Compact axes
        ax = gca; ax.FontSize = 8;
        if k < nUsed % hide xlabels except bottom row
            ax.XTickLabel = [];
        else
            xlabel('ms');
        end
        ylabel('\muV'); % microvolts
    end

    % ---------- Super title + save ----------
    titleStr = sprintf(['Event %03d  |  Active channels: %d  |  Align: %s  |  Win: \\pm%.1f ms  |  ', ...
                        'Units: \\muV  |  yLim=\\pm%.1f'], ...
                       e, nActive, alignMode, 1e3*HW/sfx, (1+pad)*maxAbs);
    sgtitle(tl, titleStr, 'FontSize',12, 'FontWeight','bold');

    outPng = fullfile(outDir, sprintf('Evt%03d_%dch_align-%s_HW%ds_%dms_rows-only_uV_fixedY.png', ...
                    e, nActive, alignMode, HW, round(1e3*HW/sfx)));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved: %s\n', outPng);
end

fprintf('Done. Output dir: %s\n', outDir);
end

% ======== Local helper functions ========

function s = tern(cond, a, b)
if cond, s = a; else, s = b; end
end

function ttl = localTitle(rowIdx, isActive, kept_channels)
aster = tern(isActive,' *','');
if ~isempty(kept_channels)
    ttl = sprintf('row %d (CSC%d)%s', rowIdx, kept_channels(rowIdx), aster);
else
    ttl = sprintf('row %d%s', rowIdx, aster);
end
end
