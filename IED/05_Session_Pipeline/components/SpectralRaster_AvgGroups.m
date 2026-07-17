function SpectralRaster_AvgGroups(inputFolder, dataMatPath, varargin)
% SpectralRaster_AvgGroups
% Build ONE spectral raster per group (SOLID, SPUTTER) by averaging
% event-locked PSDs per channel, then plotting channels x frequency (Hz).
%
% Anchor/Window/Excel parsing & outputs mirror VoltageRaster_AvgGroups:
% - Anchor: first channel's POSITIVE PEAK within ±anchorHalfWidthMs.
% - Window: ±winHalfWidthMs (default ±20 ms) around the anchor.
% - PSD: per event & channel, Hann-taper periodogram, averaged in LINEAR power,
%        then converted to dB/Hz; one heatmap per group.
% - Output: 2 PNGs with a single GLOBAL color scale (CLim) across both groups.
%
% OUTPUT FILES:
%   <inputFolder>/Spectral Raster Output/Spectral_Avg_SOLID.png
%   <inputFolder>/Spectral Raster Output/Spectral_Avg_SPUTTER.png
%
% REQUIRED DATA MAT FIELDS:
%   d   [nRows x nSamp]  (raw samples; assumed µV unless scaled)
%   sfx (scalar, Hz)
%   kept_channels (optional; for labels)
%
% ARGUMENTS
%   inputFolder   : folder containing "Solid" and "Sputter" subfolders and the Excel file
%   dataMatPath   : MAT file path (with fields above)
%
% NAME-VALUE OPTIONS (kept parallel to VoltageRaster_AvgGroups)
%   'excelPath'         : explicit Excel path (auto-detected *.xlsx in inputFolder if omitted)
%   'channelIndices'    : which rows to include; default=all
%   'scaleToMicroV'     : scalar or per-row vector (default 1)
%   'winHalfWidthMs'    : display half-width (default 20e-3 → 40 ms total)
%   'anchorHalfWidthMs' : anchor search half-width (default 5e-3)
%   'maxEventsPerGroup' : cap # events per group (optional)
%   ----- spectral-specific -----
%   'fMaxHz'            : max frequency shown (default 120)
%   'nfftMin'           : minimum NFFT (default 256). Actual NFFT = max(nfftMin, 2^nextpow2(winN))
%   'robustLowPct'      : lower percentile for global CLim (default 2)
%   'robustHighPct'     : upper percentile for global CLim (default 98)
%   'climPadFrac'       : expands the [low,high] range by this fraction (default 0.10)
%
% EXAMPLE
%   SpectralRaster_AvgGroups('C:\Exp', 'C:\Exp\data.mat');

% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));

p.addParameter('winHalfWidthMs',   20e-3, @(x)isfinite(x)&&x>0);   % ±20 ms display
p.addParameter('anchorHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms anchor search

p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));

% spectral
p.addParameter('fMaxHz', 120, @(x)isfinite(x)&&x>0);
p.addParameter('nfftMin', 256, @(x)isfinite(x)&&x>=64);
p.addParameter('robustLowPct',  2,  @(x)isfinite(x)&&x>=0&&x<50);
p.addParameter('robustHighPct', 98, @(x)isfinite(x)&&x>50&&x<=100);
p.addParameter('climPadFrac', 0.10, @(x)isfinite(x)&&x>=0&&x<=0.5);

p.parse(inputFolder, dataMatPath, varargin{:});

inputFolder    = string(p.Results.inputFolder);
dataMatPath    = string(p.Results.dataMatPath);
excelPath      = string(p.Results.excelPath);
channelIdx     = p.Results.channelIndices;
scaleToMicroV  = p.Results.scaleToMicroV;

winHWms        = p.Results.winHalfWidthMs;
anchorHWms     = p.Results.anchorHalfWidthMs;

maxEventsPer   = p.Results.maxEventsPerGroup;

fMaxHz         = p.Results.fMaxHz;
nfftMin        = p.Results.nfftMin;
robLo          = p.Results.robustLowPct;
robHi          = p.Results.robustHighPct;
climPadFrac    = p.Results.climPadFrac;

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

outRoot = fullfile(inputFolder, "Spectral Raster Output");
if ~exist(outRoot,'dir'), mkdir(outRoot); end
outSOLpng = fullfile(outRoot, "Spectral_Avg_SOLID.png");
outSPUpng = fullfile(outRoot, "Spectral_Avg_SPUTTER.png");

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
HWanchor = max(1, round(anchorHWms* sfx));  % ±anchor search
winN     = 2*HWwin + 1;

fprintf('Spectral AvgGroups: sfx=%.1f Hz | window ±%.1f ms | anchor: firstCh max (±%.1f ms)\n', ...
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

% ---------------- Build averaged PSD per group ----------------
[S_psdDB, S_freq, S_stats] = buildAvgPSD(evtSOL, 'SOLID');
[P_psdDB, P_freq, P_stats] = buildAvgPSD(evtSPU, 'SPUTTER');

if isempty(S_psdDB) && isempty(P_psdDB)
    warning('No spectral rasters created (no valid events in either group).');
    return;
end

% ---------------- Global CLim across BOTH (robust percentiles) ---------
allVals = [];
if ~isempty(S_psdDB), allVals = [allVals; S_psdDB(:)]; end %#ok<AGROW>
if ~isempty(P_psdDB), allVals = [allVals; P_psdDB(:)]; end %#ok<AGROW>
allVals = allVals(isfinite(allVals));
if isempty(allVals)
    clim = [-120 -20]; % fallback
else
    lo = prctile(allVals, robLo);
    hi = prctile(allVals, robHi);
    ctr = (lo+hi)/2; span = (hi-lo)/2;
    clim = [ctr - (1+climPadFrac)*span, ctr + (1+climPadFrac)*span];
end
fprintf('Global Spectral CLim (dB/Hz): [%.1f, %.1f]\n', clim(1), clim(2));

% ---------------- Render both with same CLim, 1 at TOP ----------------
if ~isempty(S_psdDB)
    renderSpectralRaster(S_psdDB, S_freq, 'SOLID', outSOLpng, clim, S_stats);
end
if ~isempty(P_psdDB)
    renderSpectralRaster(P_psdDB, P_freq, 'SPUTTER', outSPUpng, clim, P_stats);
end

fprintf('Saved:\n  %s\n  %s\n', outSOLpng, outSPUpng);

% ======================================================================
%                                HELPERS
% ======================================================================

function [PSDdb, f, stats] = buildAvgPSD(evtList, tag)
    PSDdb = []; f = []; 
    stats = struct('nEvents',0,'thetaFrac',NaN,'sgFrac',NaN,'hgFrac',NaN, ...
                   'thetaPkHz',NaN,'sgPkHz',NaN,'hgPkHz',NaN);

    if isempty(evtList)
        fprintf('%s: no events.\n', tag); return;
    end

    % PSD accumulators (linear) will be allocated after we know NFFT
    nUsed = 0;
    PSDsum = []; f = [];

    % band masks will be set once f is known
    thetaMask = []; sgMask = []; hgMask = [];

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

        % Prepare window/taper and FFT params (once)
        if isempty(PSDsum)
            Nseg  = s1 - s0 + 1;
            NFFT  = max(nfftMin, 2^nextpow2(Nseg));
            w     = hann(Nseg).';
            U     = sum(w.^2);                 % window power (for proper scaling)
            df    = sfx / NFFT;
            f     = (0:floor(NFFT/2)) * df;    % one-sided
            fMask = f <= fMaxHz;
            f     = f(fMask);
            PSDsum = zeros(nCh, numel(f));
            % bands
            thetaMask = f >= 4 & f <= 12;
            sgMask    = f >= 30 & f <= 50;
            hgMask    = f >= 70 & f <= 90;
        end

        okAny = false;
        for k = 1:nCh
            ch = chList(k);
            sc = scaleVec(ch);
            x  = double(mf.d(ch, s0:s1)) * sc;
            if ~any(isfinite(x)), continue; end
            x(~isfinite(x)) = 0;

            % Detrend (remove DC) and taper
            x = x - mean(x);
            xw = x(:).' .* hann(length(x)).';

            % FFT
            X = fft(xw, NFFT);
            P2 = (abs(X).^2) / (sfx * U);   % periodogram, two-sided
            P1 = P2(1:floor(NFFT/2)+1);
            P1(2:end-1) = 2*P1(2:end-1);    % single-sided
            PSDsum(k,:) = PSDsum(k,:) + P1(fMask);
            okAny = true;
        end
        if okAny
            nUsed = nUsed + 1;
        end
    end

    if nUsed == 0
        fprintf('%s: no usable events.\n', tag); return;
    end

    PSDlin = PSDsum / nUsed;             % mean linear PSD (µV^2/Hz)
    PSDdb  = 10*log10(PSDlin + eps);     % convert to dB/Hz for display

    % ---- Simple group stats across channels (fractions & peaks) ----
    fracTheta = nan(nCh,1); fracSG = nan(nCh,1); fracHG = nan(nCh,1);
    pkT = nan(nCh,1); pkSG = nan(nCh,1); pkHG = nan(nCh,1);
    for k = 1:nCh
        p = PSDlin(k,:);
        if ~any(isfinite(p)), continue; end
        p(~isfinite(p)) = 0;
        S = sum(p);
        if S > 0
            fracTheta(k) = sum(p(thetaMask)) / S;
            fracSG(k)    = sum(p(sgMask))    / S;
            fracHG(k)    = sum(p(hgMask))    / S;
        end
        [~,it]  = max(p(thetaMask)); ft = f(thetaMask); if ~isempty(it), pkT(k)  = ft(it(1));  end
        [~,ig]  = max(p(sgMask));    fg = f(sgMask);    if ~isempty(ig), pkSG(k) = fg(ig(1)); end
        [~,ihg] = max(p(hgMask));    fh = f(hgMask);    if ~isempty(ihg), pkHG(k)= fh(ihg(1)); end
    end
    stats.nEvents  = nUsed;
    stats.thetaFrac = mean(fracTheta,'omitnan');
    stats.sgFrac    = mean(fracSG,'omitnan');
    stats.hgFrac    = mean(fracHG,'omitnan');
    stats.thetaPkHz = mean(pkT,'omitnan');
    stats.sgPkHz    = mean(pkSG,'omitnan');
    stats.hgPkHz    = mean(pkHG,'omitnan');
end

function renderSpectralRaster(PSDdb, freqHz, tag, outPath, clim, stats)
    perRowPx = 12; basePx = 260; maxPx = 2600;
    figH = min(maxPx, basePx + perRowPx * nCh);
    f = figure('Color','w','Position',[90 90 1100 figH],'Visible','off');

    imagesc(freqHz, 1:nCh, PSDdb);
    set(gca, 'YDir', 'reverse');          % 1 at top
    caxis(clim);
    colormap(jet); cb = colorbar;
    ylabel(cb, 'PSD (dB/Hz)');

    xlabel('Frequency (Hz)');
    if isempty(kept_channels)
        L = arrayfun(@(kk) sprintf('row %d', chList(kk)), 1:nCh, 'UniformOutput',false);
    else
        L = arrayfun(@(kk) sprintf('row %d (CSC%d)', chList(kk), kept_channels(chList(kk))), 1:nCh, 'UniformOutput',false);
    end
    set(gca,'YTick',1:nCh,'YTickLabel',L,'FontSize',9);

    ttl = sprintf(['Avg %s PSD  |  events=%d  |  window=\\pm%.1f ms  |  anchor=firstCh max (\\pm%.1f ms)  |  ' ...
                   'channels=%d  |  CLim=[%.1f %.1f] dB/Hz  |  thetaFrac=%.3f  SG=%.3f  HG=%.3f  |  ' ...
                   'pkHz: T=%.1f  SG=%.1f  HG=%.1f'], ...
                   tag, stats.nEvents, 1e3*HWwin/sfx, 1e3*HWanchor/sfx, nCh, ...
                   clim(1),clim(2), stats.thetaFrac, stats.sgFrac, stats.hgFrac, ...
                   stats.thetaPkHz, stats.sgPkHz, stats.hgPkHz);
    title(ttl, 'FontSize', 12, 'FontWeight', 'bold');

    exportgraphics(f, outPath, 'Resolution', 220);
    close(f);
    fprintf('Saved %s spectral raster: %s\n', tag, outPath);
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
