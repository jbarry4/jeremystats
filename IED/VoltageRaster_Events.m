function VoltageRaster_Events(inputFolder, dataMatPath, varargin)
% VoltageRaster_Events
% Make a voltage raster (channels x time) for EACH event in a 20 ms window,
% saving per-event PNGs into:
%   <inputFolder> / "Voltage Raster Output" / Solid
%   <inputFolder> / "Voltage Raster Output" / Sputter
%
% Event membership (Solid vs Sputter) is inferred by scanning the PNG names
% already present in <inputFolder>/Solid and <inputFolder>/Sputter, using
% the pattern 'Evt(\d+)' to extract event numbers.
%
% The time window is anchored by default to the FIRST channel's POSITIVE PEAK
% within ±5 ms around the event midpoint (computed from Excel on/off columns).
% Optionally set anchorMode='midpoint' to center exactly on the midpoint.
%
% INPUTS
%   inputFolder   : folder containing "Solid" and "Sputter" subfolders and the Excel file
%   dataMatPath   : MAT with fields d [nRows x nSamp], sfx (Hz), kept_channels (optional)
%
% NAME-VALUE OPTIONS
%   'excelPath'         : path to Excel (auto-detected as *.xlsx in inputFolder if omitted)
%   'channelIndices'    : rows (channels) to include; default = all rows of d
%   'scaleToMicroV'     : scalar or per-row vector to scale raw units -> µV (default 1)
%   'anchorMode'        : 'firstChMax' (default) or 'midpoint'
%   'anchorHalfWidthMs' : ±ms to search the anchor around midpoint (default 5e-3)
%   'winHalfWidthMs'    : half window for raster in seconds (default 10e-3 → 20 ms total)
%   'climMicroV'        : fixed symmetric color limit (±value). If empty, auto-robust.
%   'yRobustPct'        : robust |signal| percentile for auto CLim (default 99.5)
%   'climPadFrac'       : fractional headroom added to CLim (default 0.12)
%   'maxEventsPerGroup' : optional cap on # of events per group for output
%
% OUTPUT
%   Saves PNG rasters: "Raster_Evt%03d.png" under the Solid/Sputter output dirs.
%
% EXAMPLE
%   VoltageRaster_Events('C:\Exp1', 'C:\Exp1\data.mat', 'anchorMode','midpoint');

% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));

p.addParameter('anchorMode','firstChMax', @(s) any(strcmpi(s,{'firstChMax','midpoint'})));
p.addParameter('anchorHalfWidthMs', 5e-3,  @(x)isfinite(x)&&x>0);

p.addParameter('winHalfWidthMs', 10e-3,     @(x)isfinite(x)&&x>0); % ±10 ms -> 20 ms total
p.addParameter('climMicroV', [],            @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('yRobustPct', 99.5,          @(x) isfinite(x) && x>0 && x<100);
p.addParameter('climPadFrac', 0.12,         @(x) isfinite(x) && x>=0 && x<=0.5);

p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));

p.parse(inputFolder, dataMatPath, varargin{:});

inputFolder   = string(p.Results.inputFolder);
dataMatPath   = string(p.Results.dataMatPath);
excelPath     = string(p.Results.excelPath);
channelIdx    = p.Results.channelIndices;
scaleToMicroV = p.Results.scaleToMicroV;

anchorMode    = lower(string(p.Results.anchorMode));
anchorHWms    = p.Results.anchorHalfWidthMs;

winHalfMs     = p.Results.winHalfWidthMs;
climMicroV    = p.Results.climMicroV;
yRobustPct    = p.Results.yRobustPct;
climPadFrac   = p.Results.climPadFrac;

maxEventsPer  = p.Results.maxEventsPerGroup;

% ---------------- Layout & IO ----------------
solidDir   = fullfile(inputFolder, "Solid");
sputterDir = fullfile(inputFolder, "Sputter");
assert(isfolder(solidDir),   'Missing folder: %s', solidDir);
assert(isfolder(sputterDir), 'Missing folder: %s', sputterDir);

if excelPath == ""
    xl = dir(fullfile(inputFolder, "*.xlsx"));
    assert(~isempty(xl), 'No Excel file (*.xlsx) found in %s', inputFolder);
    excelPath = fullfile(xl(1).folder, xl(1).name);
end
assert(isfile(excelPath), 'Excel not found: %s', excelPath);

% Output dirs
outRoot = fullfile(inputFolder, "Voltage Raster Output");
outSOL  = fullfile(outRoot, "Solid");
outSPU  = fullfile(outRoot, "Sputter");
if ~exist(outSOL,'dir'), mkdir(outSOL); end
if ~exist(outSPU,'dir'), mkdir(outSPU); end

% ---------------- Data ----------------
assert(isfile(dataMatPath), 'Data MAT not found: %s', dataMatPath);
mf = matfile(dataMatPath);
try sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRowsAll = size(mf,'d',1);
nSamp    = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end %#ok<NASGU>

if isempty(channelIdx)
    chList = 1:nRowsAll;
else
    chList = channelIdx(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);

% allow per-row scaling
if numel(scaleToMicroV) == 1
    scaleVec = repmat(scaleToMicroV, nRowsAll, 1);
else
    assert(numel(scaleToMicroV) >= nRowsAll, 'scaleToMicroV must be scalar or >= nRowsAll length.');
    scaleVec = scaleToMicroV(:);
end

% ---------------- Windows ----------------
HWwin    = max(1, round(winHalfMs   * sfx)); % ± display window (±10 ms by default)
HWanchor = max(1, round(anchorHWms  * sfx)); % ± anchor search (5 ms default)
tRelMs   = (-HWwin:HWwin) / sfx * 1e3;
winN     = numel(tRelMs);

fprintf('VoltageRaster_Events: sfx=%.1f Hz | raster window ±%.1f ms | anchor=%s (±%.1f ms)\n', ...
    sfx, 1e3*HWwin/sfx, anchorMode, 1e3*HWanchor/sfx);

% ---------------- Read Excel -> samples per row ----------------
T = readtable(excelPath, 'ReadVariableNames', true);
canon = lower(regexprep(T.Properties.VariableNames, '[^a-zA-Z0-9]', ''));
i_onSamp  = find(strcmp(canon,'onsamp')  | strcmp(canon,'startsample') | strcmp(canon,'startsamp') | strcmp(canon,'on'), 1);
i_offSamp = find(strcmp(canon,'offsamp') | strcmp(canon,'endsample')   | strcmp(canon,'endsamp')   | strcmp(canon,'off'), 1);
i_onSec   = find(strcmp(canon,'onsec')   | strcmp(canon,'startsec')    | strcmp(canon,'onsecs'), 1);
i_offSec  = find(strcmp(canon,'offsec')  | strcmp(canon,'endsec')      | strcmp(canon,'offsecs'), 1);

if ~isempty(i_onSamp) && ~isempty(i_offSamp)
    onSamp  = double(T{:, i_onSamp});
    offSamp = double(T{:, i_offSamp});
elseif ~isempty(i_onSec) && ~isempty(i_offSec)
    onSamp  = round(double(T{:, i_onSec})  * sfx);
    offSamp = round(double(T{:, i_offSec}) * sfx);
else
    assert(width(T) >= 2, 'Excel must have [on_samp, off_samp] or [on_sec, off_sec].');
    onSamp  = double(T{:,1});
    offSamp = double(T{:,2});
end

% make sure in range
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));
NrowsXL = numel(onSamp);

% ---------------- Event IDs from PNG names ----------------
evtSOL = parseEvtNumsFromPngs(solidDir);
evtSPU = parseEvtNumsFromPngs(sputterDir);
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));

if ~isempty(maxEventsPer)
    evtSOL = evtSOL(1:min(end, maxEventsPer));
    evtSPU = evtSPU(1:min(end, maxEventsPer));
end

% ---------------- Render groups ----------------
renderGroup(evtSOL, outSOL, 'SOLID');
renderGroup(evtSPU, outSPU, 'SPUTTER');

fprintf('Done. Output in: %s\n', outRoot);

% ======================================================================
%                                HELPERS
% ======================================================================

function renderGroup(evtList, outDir, tag)
    if isempty(evtList)
        warning('%s: no events to render.', tag);
        return;
    end
    for ii = 1:numel(evtList)
        e = evtList(ii);
        % Excel row (events are 1-indexed)
        rowXL = e;
        if rowXL < 1 || rowXL > NrowsXL
            fprintf('%s evt %d: out of Excel bounds. Skipping.\n', tag, e);
            continue;
        end

        % ---- Anchor selection ----
        s0_ev = round(onSamp(rowXL));
        s1_ev = round(offSamp(rowXL));
        if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev)
            fprintf('%s evt %d: invalid on/off samples. Skipping.\n', tag, e);
            continue;
        end

        switch anchorMode
            case "midpoint"
                anchor = round((s0_ev + s1_ev)/2);
            otherwise % "firstChMax"
                ancMid  = round((s0_ev + s1_ev)/2);
                s0a     = max(1, ancMid - HWanchor);
                s1a     = min(nSamp, ancMid + HWanchor);
                refCh   = chList(1);
                yseg0   = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
                if isempty(yseg0) || all(~isfinite(yseg0))
                    fprintf('%s evt %d: no finite data in anchor window. Skipping.\n', tag, e);
                    continue;
                end
                [~, k_rel] = max(yseg0); % positive peak only
                anchor = s0a + k_rel - 1;
        end

        % ---- Raster window ----
        s0 = anchor - HWwin;
        s1 = anchor + HWwin;
        if s0 < 1 || s1 > nSamp
            fprintf('%s evt %d: raster window out of bounds. Skipping.\n', tag, e);
            continue;
        end

        % ---- Assemble channel x time matrix (µV) ----
        Y = nan(nCh, winN);
        for k = 1:nCh
            ch = chList(k);
            sc = scaleVec(ch);
            y  = double(mf.d(ch, s0:s1)) * sc;
            if any(isfinite(y)), Y(k,:) = y; end
        end

        if all(~isfinite(Y(:)))
            fprintf('%s evt %d: no valid data in raster window. Skipping.\n', tag, e);
            continue;
        end

        % ---- Color limits (symmetric) ----
        if isempty(climMicroV)
            v = abs(Y(:));
            v = v(isfinite(v));                 % omit NaNs/Infs manually
            if isempty(v)
                pval = 1;
            else
                pval = prctile(v, yRobustPct);  % legacy-compatible syntax
                if ~isfinite(pval) || pval <= 0
                    pval = 1;
                end
            end
            clim = (1 + climPadFrac) * pval;
        else
            clim = climMicroV;
        end

        % ---- Plot raster ----
        perRowPx = 10; basePx = 200; maxPx = 2400;
        figH = min(maxPx, basePx + perRowPx * nCh);
        f = figure('Color','w','Position',[80 80 1000 figH],'Visible','off');

        imagesc(tRelMs, 1:nCh, Y);
        set(gca, 'YDir', 'normal'); % channels from bottom to top
        caxis([-clim, +clim]);
        colormap(jet); colorbar;

        xlabel('Time (ms)');
        if isempty(kept_channels)
            L = arrayfun(@(kk) sprintf('row %d', chList(kk)), 1:nCh, 'UniformOutput',false);
        else
            L = arrayfun(@(kk) sprintf('row %d (CSC%d)', chList(kk), kept_channels(chList(kk))), 1:nCh, 'UniformOutput',false);
        end
        set(gca,'YTick',1:nCh,'YTickLabel',L,'FontSize',9);

        ttl = sprintf('%s  |  Evt %d  |  anchor=%s  |  window=\\pm%.1f ms  |  channels=%d', ...
            tag, e, char(anchorMode), 1e3*HWwin/sfx, nCh);
        title(ttl, 'FontSize', 12, 'FontWeight', 'bold');

        % ---- Save ----
        outPng = fullfile(outDir, sprintf('Raster_Evt%03d.png', e));
        exportgraphics(f, outPng, 'Resolution', 220);
        close(f);
        fprintf('Saved %s raster: %s\n', tag, outPng);
    end
end

function evts = parseEvtNumsFromPngs(dirpath)
    L = dir(fullfile(dirpath, '*.png'));
    evts = [];
    for k = 1:numel(L)
        m = regexp(L(k).name, 'Evt(\d+)', 'tokens', 'once');
        if ~isempty(m)
            ev = str2double(m{1});
            if isfinite(ev), evts(end+1) = ev; end %#ok<AGROW>
        end
    end
    evts = sort(unique(evts));
end

end
