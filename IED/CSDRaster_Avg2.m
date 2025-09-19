function CSDRaster_Avg2(inputFolder, dataMatPath, varargin)
% CSDRaster_AvgGroups
% Build ONE CSD raster per group (SOLID, SPUTTER) by averaging aligned
% waveforms across all events in each group, then computing CSD on the mean.
%
% - Anchor: first channel's POSITIVE PEAK within ±anchorHalfWidthMs around
%   each event's midpoint (from Excel on/off). This ensures events are aligned.
% - Window: ±winHalfWidthMs (default ±20 ms) around the anchor, time centered at 0.
% - Averaging: per channel, average across events at each time sample (voltage),
%   then compute CSD(mean). (Second difference is linear ⇒ equivalent to mean(CSD).)
% - Output: 2 PNGs with a single GLOBAL color scale (CLim) across both groups.
%
% OUTPUT FILES:
%   <inputFolder>/CSD Raster Output/CSD_Raster_Avg_SOLID.png
%   <inputFolder>/CSD Raster Output/CSD_Raster_Avg_SPUTTER.png

% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));

p.addParameter('winHalfWidthMs',   20e-3, @(x)isfinite(x)&&x>0);   % ±20 ms display
p.addParameter('metricHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms metrics on MEAN CSD
p.addParameter('anchorHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms anchor search

p.addParameter('climCSD',     [],            @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('yRobustPct',  99.5,          @(x) isfinite(x) && x>0 && x<100);
p.addParameter('climPadFrac', 0.12,          @(x) isfinite(x) && x>=0 && x<=0.5);

p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));

p.parse(inputFolder, dataMatPath, varargin{:});

inputFolder    = string(p.Results.inputFolder);
dataMatPath    = string(p.Results.dataMatPath);
excelPath      = string(p.Results.excelPath);
channelIdx     = p.Results.channelIndices;
scaleToMicroV  = p.Results.scaleToMicroV;

winHWms        = p.Results.winHalfWidthMs;
metHWms        = p.Results.metricHalfWidthMs;
anchorHWms     = p.Results.anchorHalfWidthMs;

climCSDOpt     = p.Results.climCSD;
yRobustPct     = p.Results.yRobustPct;
climPadFrac    = p.Results.climPadFrac;

maxEventsPer   = p.Results.maxEventsPerGroup;

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

outRoot = fullfile(inputFolder, "CSD Raster Output");
if ~exist(outRoot,'dir'), mkdir(outRoot); end
outSOLpng = fullfile(outRoot, "CSD_Raster_Avg_SOLID.png");
outSPUpng = fullfile(outRoot, "CSD_Raster_Avg_SPUTTER.png");

% ---------------- Data ----------------
assert(isfile(dataMatPath), 'Data MAT not found: %s', dataMatPath);
mf = matfile(dataMatPath);
try sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRowsAll = size(mf,'d',1);
nSamp    = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end %#ok<NASGU>

% Channel selection
if isempty(channelIdx)
    chList = 1:nRowsAll;
else
    chList = channelIdx(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);

% scaling vector
if numel(scaleToMicroV)==1
    scaleVec = repmat(scaleToMicroV, nRowsAll, 1);
else
    assert(numel(scaleToMicroV) >= nRowsAll, 'scaleToMicroV must be scalar or length >= nRowsAll.');
    scaleVec = scaleToMicroV(:);
end

% ---------------- Windows ----------------
HWwin    = max(1, round(winHWms   * sfx));  % ±display half-width
HWmet    = max(1, round(metHWms   * sfx));  % ±metrics half-width
HWanchor = max(1, round(anchorHWms* sfx));  % ±anchor search
tRelMs   = (-HWwin:HWwin) / sfx * 1e3;
winN     = numel(tRelMs);

% Metrics-on-mean window indices
metStart = HWwin - HWmet + 1;
metEnd   = HWwin + HWmet + 1;
Lmet     = metEnd - metStart + 1;

fprintf('CSD AvgGroups: sfx=%.1f Hz | window ±%.1f ms | anchor: firstCh max (±%.1f ms)\n', ...
    sfx, 1e3*HWwin/sfx, 1e3*HWanchor/sfx);

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

% Bounds
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));
NrowsXL = numel(onSamp);

% ---------------- Event IDs by PNG names ----------------
evtSOL = parseEvtNumsFromPngs(solidDir);
evtSPU = parseEvtNumsFromPngs(sputterDir);
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));

if ~isempty(maxEventsPer)
    evtSOL = evtSOL(1:min(end, maxEventsPer));
    evtSPU = evtSPU(1:min(end, maxEventsPer));
end

% ---------------- Build averaged CSD per group ----------------
[S_csd, S_stats] = buildAvgCSD(evtSOL, 'SOLID');
[P_csd, P_stats] = buildAvgCSD(evtSPU, 'SPUTTER');

if isempty(S_csd) && isempty(P_csd)
    warning('No average CSD rasters created (no valid events in either group).');
    return;
end

% ---------------- Global CLim across BOTH CSD averages ----------------
if isempty(climCSDOpt)
    vals = [];
    if ~isempty(S_csd), vals = [vals; abs(S_csd(:))]; end %#ok<AGROW>
    if ~isempty(P_csd), vals = [vals; abs(P_csd(:))]; end %#ok<AGROW>
    vals = vals(isfinite(vals));
    if isempty(vals), pval = 1; else, pval = prctile(vals, yRobustPct); end
    climGlobal = (1 + climPadFrac) * max(1, pval);
else
    climGlobal = climCSDOpt;
end
fprintf('Global CSD CLim (averages): ±%.2f (CSD units).\n', climGlobal);

% ---------------- Render both with same CLim, 1 at TOP ----------------
if ~isempty(S_csd)
    renderAvgRaster(S_csd, 'SOLID', outSOLpng, climGlobal, S_stats);
end
if ~isempty(P_csd)
    renderAvgRaster(P_csd, 'SPUTTER', outSPUpng, climGlobal, P_stats);
end

fprintf('Saved:\n  %s\n  %s\n', outSOLpng, outSPUpng);

% ======================================================================
%                                HELPERS
% ======================================================================

function [CSDMU, stats] = buildAvgCSD(evtList, tag)
    CSDMU = [];
    stats = struct('nEvents',0,'pkMean',NaN,'pkSD',NaN,'hwMean',NaN,'hwSD',NaN);
    if isempty(evtList)
        fprintf('%s: no events.\n', tag); return;
    end

    % Accumulator for voltage mean (we will CSD the mean at the end)
    sumY  = zeros(nCh, winN);
    nUsed = 0;

    for ii = 1:numel(evtList)
        e = evtList(ii);
        rowXL = e;
        if rowXL < 1 || rowXL > NrowsXL, continue; end

        s0_ev = round(onSamp(rowXL));
        s1_ev = round(offSamp(rowXL));
        if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev), continue; end

        % ---- Anchor by first-channel positive peak (±anchor window) ----
        ancMid = round((s0_ev + s1_ev)/2);
        s0a = max(1, ancMid - HWanchor);
        s1a = min(nSamp, ancMid + HWanchor);
        refCh = chList(1);
        y0 = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
        if isempty(y0) || all(~isfinite(y0)), continue; end
        [~, k_rel] = max(y0);
        anchor = s0a + k_rel - 1;

        % ---- Window ----
        s0 = anchor - HWwin; s1 = anchor + HWwin;
        if s0 < 1 || s1 > nSamp, continue; end

        % ---- Add this event's segment to sums ----
        okAny = false;
        for k = 1:nCh
            ch = chList(k);
            sc = scaleVec(ch);
            y  = double(mf.d(ch, s0:s1)) * sc;
            if any(isfinite(y))
                sumY(k,:) = sumY(k,:) + y;
                okAny = true;
            end
        end
        if okAny
            nUsed = nUsed + 1;
        end
    end

    if nUsed == 0
        fprintf('%s: no usable events.\n', tag); return;
    end

    MU    = sumY / nUsed;     % mean VOLTAGE per channel
    CSDMU = computeCSD(MU);   % CSD of the mean (channels x time)
    stats.nEvents = nUsed;

    % ---- Metrics on the MEAN CSD (per-channel peak & HW) ----
    perCh_pk = nan(nCh,1);
    perCh_hw = nan(nCh,1);

    for k = 1:nCh
        cs = CSDMU(k,:);
        csMet = cs(metStart:metEnd);
        if numel(csMet) >= 3 && all(isfinite(csMet))
            [mx, kMax] = max(csMet);
            [mn, kMin] = min(csMet);
            if abs(mn) > abs(mx)
                sgn = -1; amp = abs(mn); pkRel = kMin;
            else
                sgn = +1; amp = abs(mx); pkRel = kMax;
            end
            h  = 0.5 * amp; sig = sgn * csMet;

            % Left crossing
            kL = pkRel;
            while kL > 1 && sig(kL) >= h, kL = kL - 1; end
            if kL >= 1 && (kL+1) <= Lmet
                left_ip = kL + (h - sig(kL)) / (sig(kL+1) - sig(kL));
            else, left_ip = NaN; end

            % Right crossing
            kR = pkRel;
            while kR < Lmet && sig(kR) >= h, kR = kR + 1; end
            if (kR-1) >= 1 && kR <= Lmet
                right_ip = (kR-1) + (h - sig(kR-1)) / (sig(kR) - sig(kR-1));
            else, right_ip = NaN; end

            if isfinite(left_ip) && isfinite(right_ip) && right_ip > left_ip
                hw_ms = (right_ip - left_ip) / sfx * 1e3;
            else
                hw_ms = NaN;
            end
            perCh_pk(k) = amp;
            perCh_hw(k) = hw_ms;
        end
    end

    stats.pkMean = mean(perCh_pk, 'omitnan');
    stats.pkSD   = std( perCh_pk, 0, 'omitnan');
    stats.hwMean = mean(perCh_hw,  'omitnan');
    stats.hwSD   = std( perCh_hw,  0, 'omitnan');
end

function renderAvgRaster(CSDMU, tag, outPath, clim, stats)
    % Slightly larger figure to avoid title cropping; smaller title font.
    perRowPx = 14; basePx = 290; maxPx = 2800;
    figH = min(maxPx, basePx + perRowPx * nCh);
    f = figure('Color','w','Position',[90 90 1100 figH],'Visible','off');

    imagesc(tRelMs, 1:nCh, CSDMU);
    set(gca, 'YDir', 'reverse');          % 1 at top
    caxis([-clim, +clim]);
    colormap(jet); colorbar;

    xlabel('Time (ms)');
    if isempty(kept_channels)
        L = arrayfun(@(kk) sprintf('row %d', chList(kk)), 1:nCh, 'UniformOutput',false);
    else
        L = arrayfun(@(kk) sprintf('row %d (CSC%d)', chList(kk), kept_channels(chList(kk))), 1:nCh, 'UniformOutput',false);
    end
    set(gca,'YTick',1:nCh,'YTickLabel',L,'FontSize',9);

    ttl = sprintf(['CSD Avg %s  |  events=%d  |  window=\\pm%.1f ms  |  anchor=firstCh max (\\pm%.1f ms)  |  ' ...
                   'channels=%d  |  CLim=\\pm%.2f  |  CSD peak=%.2f\\pm%.2f  |  HW=%.2f\\pm%.2f ms'], ...
                   tag, stats.nEvents, 1e3*HWwin/sfx, 1e3*HWanchor/sfx, nCh, ...
                   clim, stats.pkMean, stats.pkSD, stats.hwMean, stats.hwSD);
    title(ttl, 'FontSize', 10, 'FontWeight', 'bold');  % smaller font to avoid cropping

    exportgraphics(f, outPath, 'Resolution', 220);
    close(f);
    fprintf('Saved %s average CSD raster: %s\n', tag, outPath);
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

function C = computeCSD(Ych_t)
% computeCSD: second spatial derivative across channels.
% Input:  Ych_t is (channels x time) in µV
% Output: CSD (channels x time)
% Interior channels use standard 3-point stencil; EDGE CHANNELS are
% **replicated from the nearest interior** so the first/last rows are not blank.
    [nChLoc, nT] = size(Ych_t);
    if nChLoc < 2
        C = nan(nChLoc, nT);
        return;
    elseif nChLoc == 2
        % With 2 channels, define both as equal (degenerate); at least not blank.
        C = zeros(nChLoc, nT);
        return;
    end
    % interior second difference (negative sign for conventional CSD)
    Cint = -( Ych_t(3:end,:) - 2*Ych_t(2:end-1,:) + Ych_t(1:end-2,:) );
    C = zeros(nChLoc, nT);
    C(2:end-1,:) = Cint;
    % Edge handling: replicate nearest interior values so edges are visible
    C(1,:)      = C(2,:);
    C(end,:)    = C(end-1,:);
    % If you know electrode spacing h, divide by h^2 here.
end

end
