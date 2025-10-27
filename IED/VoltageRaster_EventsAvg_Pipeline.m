function out = VoltageRaster_EventsAvg_Pipeline(inputFolder, dataMatPath, varargin)
% VoltageRaster_EventsAvg_Pipeline
% Wrapper that builds ONE averaged voltage raster per group (SOLID/SPUTTER),
% saves PNGs + a stats CSV, and returns file paths so Pipeline_Main can
% ingest them later.
%
% Returns struct:
%   out.pngSolid   -> "<inputFolder>/Voltage Raster Output/Raster_Avg_SOLID.png"
%   out.pngSputter -> "<inputFolder>/Voltage Raster Output/Raster_Avg_SPUTTER.png"
%   out.statsCSV   -> "<inputFolder>/Voltage Raster Output/VoltageRaster_Avg_stats.csv"

% ---------- Run the “core” and collect outputs ----------
[paths, statsTable] = VoltageRaster_AvgGroups_core(inputFolder, dataMatPath, varargin{:});

% Write stats CSV
outDir = fileparts(paths.solidPng);
statsCSV = fullfile(outDir, 'VoltageRaster_Avg_stats.csv');
try
    writetable(statsTable, statsCSV);
catch ME
    warning('VoltageRaster_EventsAvg_Pipeline:failedToWriteStats', 'Failed to write stats CSV: %s', ME.message);
    statsCSV = '';
end

% Return paths for Pipeline_Main
out = struct( ...
    'pngSolid',   paths.solidPng, ...
    'pngSputter', paths.sputterPng, ...
    'statsCSV',   statsCSV);
end


% ======================================================================
%                             CORE IMPLEMENTATION
% ======================================================================
function [paths, statsT] = VoltageRaster_AvgGroups_core(inputFolder, dataMatPath, varargin)
% This is adapted from your VoltageRaster_AvgGroups (no functional changes),
% but also returns a stats table for the pipeline.

% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));

p.addParameter('winHalfWidthMs',   20e-3, @(x)isfinite(x)&&x>0);   % ±20 ms display
p.addParameter('metricHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms metrics on MEAN waveform
p.addParameter('anchorHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms anchor search

p.addParameter('climMicroV', [],            @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('yRobustPct', 99.5,          @(x) isfinite(x) && x>0 && x<100);
p.addParameter('climPadFrac', 0.12,         @(x) isfinite(x) && x>=0 && x<=0.5);

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

climMicroVOpt  = p.Results.climMicroV;
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

outRoot = fullfile(inputFolder, "Voltage Raster Output");
if ~exist(outRoot,'dir'), mkdir(outRoot); end
outSOLpng = fullfile(outRoot, "Raster_Avg_SOLID.png");
outSPUpng = fullfile(outRoot, "Raster_Avg_SPUTTER.png");

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

% For metric computations on MEAN waveform
metStart = HWwin - HWmet + 1;
metEnd   = HWwin + HWmet + 1;
Lmet     = metEnd - metStart + 1;

fprintf('VoltageRaster_AvgGroups: sfx=%.1f Hz | window ±%.1f ms | anchor: lastCh max (±%.1f ms)\n', ...
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

% ---------------- Build averaged waveforms per group ----------------
[S_mu, S_stats] = buildAvg(evtSOL, 'SOLID');
[P_mu, P_stats] = buildAvg(evtSPU, 'SPUTTER');

% ---------------- Global CLim across BOTH averages ----------------
if isempty(S_mu) && isempty(P_mu)
    warning('VoltageRaster_AvgGroups: no average rasters created.');
    statsT = table(); % nothing to report
    paths = struct('solidPng','', 'sputterPng','');
    return;
end

if isempty(climMicroVOpt)
    vals = [];
    if ~isempty(S_mu), vals = [vals; abs(S_mu(:))]; end %#ok<AGROW>
    if ~isempty(P_mu), vals = [vals; abs(P_mu(:))]; end %#ok<AGROW>
    vals = vals(isfinite(vals));
    if isempty(vals), pval = 1; else, pval = prctile(vals, yRobustPct); end
    climGlobal = (1 + climPadFrac) * max(1, pval);
else
    climGlobal = climMicroVOpt;
end
fprintf('Global CLim (averages): ±%.2f µV.\n', climGlobal);

% ---------------- Render both with same CLim, 1 at TOP ----------------
pngSOL = ''; pngSPU = '';
if ~isempty(S_mu), pngSOL = renderAvgRaster(S_mu, 'SOLID', outSOLpng, climGlobal, S_stats); end
if ~isempty(P_mu), pngSPU = renderAvgRaster(P_mu, 'SPUTTER', outSPUpng, climGlobal, P_stats); end

% ---------------- Build stats table for pipeline ----------------
statsT = table();
if ~isempty(S_mu)
    statsT = [statsT; summarizeGroup('SOLID', S_stats, climGlobal, nCh, sfx, winHWms, anchorHWms)]; %#ok<AGROW>
end
if ~isempty(P_mu)
    statsT = [statsT; summarizeGroup('SPUTTER', P_stats, climGlobal, nCh, sfx, winHWms, anchorHWms)]; %#ok<AGROW>
end

paths = struct('solidPng', pngSOL, 'sputterPng', pngSPU);

% ============================= HELPERS =============================
    function [MU, stats] = buildAvg(evtList, tag)
        MU = []; stats = struct('nEvents',0,'ampMean',NaN,'ampSD',NaN,'hwMean',NaN,'hwSD',NaN);
        if isempty(evtList), return; end

        sumY  = zeros(nCh, winN);
        nUsed = 0;

        perCh_amp = nan(nCh,1);
        perCh_hw  = nan(nCh,1);

        for ii = 1:numel(evtList)
            e = evtList(ii);
            rowXL = e;
            if rowXL < 1 || rowXL > NrowsXL, continue; end

            s0_ev = round(onSamp(rowXL));
            s1_ev = round(offSamp(rowXL));
            if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev), continue; end

            % Anchor by first-channel positive peak (±anchor window)
            ancMid = round((s0_ev + s1_ev)/2);
            s0a = max(1, ancMid - HWanchor);
            s1a = min(nSamp, ancMid + HWanchor);
            refCh = chList(end);
            y0 = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
            if isempty(y0) || all(~isfinite(y0)), continue; end
            [~, k_rel] = max(y0);
            anchor = s0a + k_rel - 1;

            % Window
            s0 = anchor - HWwin; s1 = anchor + HWwin;
            if s0 < 1 || s1 > nSamp, continue; end

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
            if okAny, nUsed = nUsed + 1; end
        end

        if nUsed == 0, return; end
        MU = sumY / nUsed;
        stats.nEvents = nUsed;

        % Per-channel metrics on MEAN waveform (±metric window)
        metStartL = HWwin - HWmet + 1;
        metEndL   = HWwin + HWmet + 1;
        LmetL     = metEndL - metStartL + 1;

        for k = 1:nCh
            mu = MU(k,:);
            muMet = mu(metStartL:metEndL);
            if numel(muMet) >= 3 && all(isfinite(muMet))
                [mx, kMax] = max(muMet);
                [mn, kMin] = min(muMet);
                if abs(mn) > abs(mx)
                    sgn = -1; amp = abs(mn); pkRel = kMin;
                else
                    sgn = +1; amp = abs(mx); pkRel = kMax;
                end
                h  = 0.5 * amp; sig = sgn * muMet;

                % Left crossing
                kL = pkRel; 
                while kL > 1 && sig(kL) >= h, kL = kL - 1; end
                if kL >= 1 && (kL+1) <= LmetL
                    left_ip = kL + (h - sig(kL)) / (sig(kL+1) - sig(kL));
                else, left_ip = NaN; end

                % Right crossing
                kR = pkRel;
                while kR < LmetL && sig(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= LmetL
                    right_ip = (kR-1) + (h - sig(kR-1)) / (sig(kR) - sig(kR-1));
                else, right_ip = NaN; end

                if isfinite(left_ip) && isfinite(right_ip) && right_ip > left_ip
                    hw_ms = (right_ip - left_ip) / sfx * 1e3;
                else
                    hw_ms = NaN;
                end
                perCh_amp(k) = amp;
                perCh_hw(k)  = hw_ms;
            end
        end

        stats.ampMean = mean(perCh_amp, 'omitnan');
        stats.ampSD   = std( perCh_amp, 0, 'omitnan');
        stats.hwMean  = mean(perCh_hw,  'omitnan');
        stats.hwSD    = std( perCh_hw,  0, 'omitnan');
    end

    function outPath = renderAvgRaster(MU, tag, outPath, clim, stats)
        perRowPx = 12; basePx = 260; maxPx = 2600;
        figH = min(maxPx, basePx + perRowPx * nCh);
        f = figure('Color','w','Position',[90 90 1100 figH],'Visible','off');

        imagesc(tRelMs, 1:nCh, MU);
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

        ttl = sprintf(['Avg %s  |  events=%d  |  window=\\pm%.1f ms  |  anchor=lastCh max (\\pm%.1f ms)  |  ' ...
                       'channels=%d  |  CLim=\\pm%.1f \\muV  |  mean peak=%.1f\\pm%.1f \\muV  |  HW=%.2f\\pm%.2f ms'], ...
                       tag, stats.nEvents, 1e3*HWwin/sfx, 1e3*HWanchor/sfx, nCh, ...
                       clim, stats.ampMean, stats.ampSD, stats.hwMean, stats.hwSD);
        title(ttl, 'FontSize', 12, 'FontWeight', 'bold');

        exportgraphics(f, outPath, 'Resolution', 220);
        close(f);
        fprintf('Saved %s average raster: %s\n', tag, outPath);
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

    function Trow = summarizeGroup(tag, stats, climG, nCh_, sfx_, winHWms_, anchorHWms_)
        Trow = table( ...
            string(tag), stats.nEvents, nCh_, sfx_, ...
            1e3*winHWms_, 1e3*anchorHWms_, ...
            climG, stats.ampMean, stats.ampSD, stats.hwMean, stats.hwSD, ...
            'VariableNames', {'Group','Events','Channels','SampRateHz', ...
                              'DisplayHalfWidth_ms','AnchorHalfWidth_ms', ...
                              'CLim_uV','MeanPeak_uV','SD_Peak_uV','MeanHW_ms','SD_HW_ms'});
    end
end
