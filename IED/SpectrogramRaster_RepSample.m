function SpectrogramRaster_RepSample(inputFolder, dataMatPath, varargin)
% SpectrogramRaster_RepSample
% For each event (found via Evt### in Solid/Sputter folders), compute spectrograms
% on selected channels [2 12 22 32 42 52 64] for two windows (±20 ms and ±100 ms),
% and output BOTH sets in a single PNG per event.
%
% REQUIRED dataMatPath fields:
%   d [nRows x nSamp], sfx (Hz), kept_channels (optional)
%
% INPUTS
%   inputFolder   : folder with subfolders Solid, Sputter and an Excel (*.xlsx) holding [on/off]
%   dataMatPath   : MAT file path containing the data
%
% NAME-VALUE OPTIONS
%   'excelPath'      : explicit Excel path (auto-detect in inputFolder if empty)
%   'channelIndices' : override channel list (default fixed: [2 12 22 32 42 52 64])
%   'scaleToMicroV'  : scalar or per-row vector (default 1)
%   'anchorHalfWidthMs' : ±ms for anchor search around event midpoint (default 5e-3)
%   'specWinMs'      : STFT window length in ms (default 0.1e-3 → 0.1 ms; clamped to ≥8 samples)
%   'specOverlap'    : fraction overlap for STFT window (default 0.5)
%   'nfft'           : NFFT for spectrogram (default auto = nextpow2(window))
%   'fMaxHz'         : y-axis (frequency) upper limit (default 2000)
%   'powerUpperPct'  : robust percentile for CLim high (dB) across all panes (default 99.5)
%   'powerDynRange'  : dynamic range below the high CLim (dB) (default 40)
%   'maxEventsPerGroup' : cap number of events per group (optional)
%
% OUTPUTS (one PNG per event):
%   <inputFolder>/Spectral RepSample Output/Solid/EvtNNN_RepSample.png
%   <inputFolder>/Spectral RepSample Output/Sputter/EvtNNN_RepSample.png

% ---------- Args ----------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

p.addParameter('excelPath', "", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [2 12 22 32 42 52 64], @(v) isnumeric(v) && all(v>=1));
p.addParameter('scaleToMicroV', 1, @(x) isnumeric(x) && all(isfinite(x)) && all(x>0));

p.addParameter('anchorHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);

p.addParameter('specWinMs',   0.1e-2, @(x)isfinite(x)&&x>0);  % 0.4 ms
p.addParameter('specOverlap', 0.50,   @(x)isfinite(x)&&x>=0&&x<1);
p.addParameter('nfft',        [],     @(x) isempty(x) || (isscalar(x)&&x>0));
p.addParameter('fMaxHz',      2000,   @(x)isfinite(x)&&x>0);

p.addParameter('powerUpperPct', 99.5, @(x)isfinite(x)&&x>0&&x<100);
p.addParameter('powerDynRange', 40,   @(x)isfinite(x)&&x>0);

p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));

p.parse(inputFolder, dataMatPath, varargin{:});
inputFolder     = string(p.Results.inputFolder);
dataMatPath     = string(p.Results.dataMatPath);

excelPath       = string(p.Results.excelPath);
chSel           = unique(p.Results.channelIndices(:).');
scaleToMicroV   = p.Results.scaleToMicroV;

anchorHWms      = p.Results.anchorHalfWidthMs;

specWinMs       = p.Results.specWinMs;
specOverlap     = p.Results.specOverlap;
nfftOpt         = p.Results.nfft;
fMaxHz          = p.Results.fMaxHz;

powerUpperPct   = p.Results.powerUpperPct;
powerDynRange   = p.Results.powerDynRange;

maxEventsPer    = p.Results.maxEventsPerGroup;

% ---------- Layout ----------
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

outRoot = fullfile(inputFolder, "Spectral RepSample Output");
outSOL  = fullfile(outRoot, "Solid");
outSPU  = fullfile(outRoot, "Sputter");
if ~exist(outRoot,'dir'), mkdir(outRoot); end
if ~exist(outSOL,'dir'),  mkdir(outSOL);  end
if ~exist(outSPU,'dir'),  mkdir(outSPU);  end

% ---------- Data ----------
assert(isfile(dataMatPath), 'Data MAT not found: %s', dataMatPath);
mf = matfile(dataMatPath);
try sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRowsAll = size(mf,'d',1);
nSamp    = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end %#ok<NASGU>

% Clip channels to data range
chSel = chSel(chSel>=1 & chSel<=nRowsAll);
assert(~isempty(chSel), 'No valid channels in data after clipping.');
nCh = numel(chSel);

% Scaling (vectorized)
if numel(scaleToMicroV)==1
    scaleVec = repmat(scaleToMicroV, nRowsAll, 1);
else
    assert(numel(scaleToMicroV) >= nRowsAll, 'scaleToMicroV must be scalar or length >= nRowsAll.');
    scaleVec = scaleToMicroV(:);
end

% ---------- Excel on/off (samples or seconds) ----------
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
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));
NrowsXL = numel(onSamp);

% ---------- Events from PNG names ----------
evtSOL = parseEvtNumsFromPngs(solidDir);
evtSPU = parseEvtNumsFromPngs(sputterDir);
fprintf('RepSample: found %d SOLID, %d SPUTTER (by filenames).\n', numel(evtSOL), numel(evtSPU));
if ~isempty(maxEventsPer)
    evtSOL = evtSOL(1:min(end, maxEventsPer));
    evtSPU = evtSPU(1:min(end, maxEventsPer));
end

% ---------- Spectrogram params ----------
specWinSamp     = max(8, round(specWinMs * sfx)); % ≥8 samples
specOverlapSamp = max(0, min(specWinSamp-1, round(specOverlap * specWinSamp)));
if isempty(nfftOpt)
    nfft = max(32, 2^nextpow2(specWinSamp));
else
    nfft = nfftOpt;
end
fMaxHz = min(fMaxHz, sfx/2);

fprintf(['Spectrogram params: win=%d samp (%.3f ms) | overlap=%d samp (%.0f%%) | nfft=%d | fMax=%.0f Hz | ' ...
         'anchor search ±%.1f ms\n'], specWinSamp, 1e3*specWinSamp/sfx, specOverlapSamp, ...
         100*specOverlapSamp/specWinSamp, nfft, fMaxHz, 1e3*(round(anchorHWms*sfx))/sfx);

% ---------- Pack context for helpers ----------
ctx = struct();
ctx.mf = mf;
ctx.sfx = sfx;
ctx.nSamp = nSamp;
ctx.onSamp = onSamp;
ctx.offSamp = offSamp;
ctx.NrowsXL = NrowsXL;
ctx.chSel = chSel;
ctx.scaleVec = scaleVec;
ctx.kept_channels = kept_channels;

ctx.specWinSamp = specWinSamp;
ctx.specOverlapSamp = specOverlapSamp;
ctx.nfft = nfft;
ctx.fMaxHz = fMaxHz;
ctx.powerUpperPct = powerUpperPct;
ctx.powerDynRange = powerDynRange;

ctx.anchorHWms = anchorHWms;  % seconds

% ---------- Render ----------
renderGroup(evtSOL, outSOL, 'SOLID', ctx);
renderGroup(evtSPU, outSPU, 'SPUTTER', ctx);

fprintf('Done.\n');

end % === main ===

% ----------------------------------------------------------------------
% Render a group (Solid/Sputter)
% ----------------------------------------------------------------------
function renderGroup(evtList, outDir, tag, ctx)
if isempty(evtList), fprintf('%s: no events.\n', tag); return; end
for ii = 1:numel(evtList)
    e = evtList(ii);
    try
        renderOneEvent(e, outDir, tag, ctx);
    catch ME
        warning('%s Evt %d: %s', tag, e, ME.message);
    end
end
end

% ----------------------------------------------------------------------
% Render a single event: two windows (±20 ms top row, ±100 ms bottom row)
% ----------------------------------------------------------------------
function renderOneEvent(e, outDir, tag, ctx)

mf            = ctx.mf;
sfx           = ctx.sfx;
nSamp         = ctx.nSamp;
onSamp        = ctx.onSamp;
offSamp       = ctx.offSamp;
NrowsXL       = ctx.NrowsXL;
chSel         = ctx.chSel;
scaleVec      = ctx.scaleVec;
kept_channels = ctx.kept_channels;

specWinSamp     = ctx.specWinSamp;
specOverlapSamp = ctx.specOverlapSamp;
nfft            = ctx.nfft;
fMaxHz          = ctx.fMaxHz;
powerUpperPct   = ctx.powerUpperPct;
powerDynRange   = ctx.powerDynRange;

anchorHWms      = ctx.anchorHWms;  % seconds
HWanchor        = max(1, round(anchorHWms * sfx));

% Event bounds
if e < 1 || e > NrowsXL, return; end
s0_ev = round(onSamp(e));
s1_ev = round(offSamp(e));
if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev), return; end

% --- Anchor by first channel (positive peak) within ±HWanchor around midpoint
ancMid = round((s0_ev + s1_ev)/2);
s0a = max(1, ancMid - HWanchor);
s1a = min(nSamp, ancMid + HWanchor);
refCh = chSel(1);
y0 = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
if isempty(y0) || all(~isfinite(y0)), return; end
[~, k_rel] = max(y0);
anchor = s0a + k_rel - 1;

% Two windows: ±20 ms and ±100 ms
HW20   = max(1, round(0.020 * sfx));
HW100  = max(1, round(0.100 * sfx));

windows = [HW20, HW100];        % samples
labels  = { '±20 ms', '±100 ms' };

% Precompute CLim across all panes (both windows × channels)
allP = [];
paneData = cell(2, numel(chSel)); % store P (dB), Tms, F for rendering

for wi = 1:2
    HW = windows(wi);
    s0 = anchor - HW; s1 = anchor + HW;
    if s0 < 1 || s1 > nSamp, error('Event %d window out of bounds.', e); end

    for ci = 1:numel(chSel)
        ch = chSel(ci);
        y  = double(mf.d(ch, s0:s1)) * scaleVec(ch);
        y(~isfinite(y)) = 0;

        [S, F, T] = spectrogram(y, specWinSamp, specOverlapSamp, nfft, sfx);
        P = 10*log10(abs(S).^2 + eps);

        % limit to [0, fMaxHz]
        msk = (F >= 0) & (F <= fMaxHz);
        F2  = F(msk);
        P2  = P(msk, :);

        % Time axis in ms, centered: T starts at 0 sec at start of segment
        Tms = (T - (HW / sfx)) * 1e3;

        paneData{wi,ci} = struct('P',P2, 'F',F2, 'Tms',Tms);
        allP = [allP; P2(:)]; %#ok<AGROW>
    end
end

% Robust CLim across all panes
allP = allP(isfinite(allP));
if isempty(allP), pHi = 0; else, pHi = prctile(allP, powerUpperPct); end
pLo = pHi - powerDynRange;

% --- Render figure: 2 rows (windows), nCh columns (channels)
nRows = 2; nCols = numel(chSel);
tileH = 170; titleH = 70; maxH = 2800;
figH  = min(maxH, titleH + nRows*tileH);
figW  = 150 + nCols*210;

f = figure('Color','w','Position',[80 80 figW figH],'Visible','off');
tl = tiledlayout(f, nRows, nCols, 'Padding','compact', 'TileSpacing','compact');

for wi = 1:2
    for ci = 1:nCols
        D = paneData{wi,ci};
        ax = nexttile(tl);
        imagesc(ax, D.Tms, D.F, D.P);
        axis(ax, 'xy');
        colormap(ax, parula);
        caxis(ax, [pLo pHi]);
        if wi==nRows, xlabel(ax,'Time (ms)'); else, ax.XTickLabel=[]; end
        if ci==1, ylabel(ax,'Hz'); else, ax.YTickLabel=[]; end

        if ~isempty(kept_channels)
            chLbl = sprintf('row %d (CSC%d)', chSel(ci), kept_channels(chSel(ci)));
        else
            chLbl = sprintf('row %d', chSel(ci));
        end
        ttl = sprintf('%s | %s', chLbl, labels{wi});
        title(ax, ttl, 'FontSize',9, 'FontWeight','bold');
        grid(ax,'on'); ax.GridColor=[0 0 0]; ax.GridAlpha=0.08;
    end
end

% ---- Colorbar (compat-friendly) ----
cb = colorbar;                  % attach to current figure/axes context
set(cb, 'Location', 'eastoutside');
cb.Label.String = sprintf('Power (dB)  |  CLim: [%.1f, %.1f]', pLo, pHi);

sg = sprintf('%s  |  Evt %d  |  anchor: first-ch max (±%.1f ms)  |  STFT: win=%.3f ms, ov=%.0f%%, nfft=%d, fMax=%.0f Hz', ...
             tag, e, 1e3*HWanchor/sfx, 1e3*specWinSamp/sfx, 100*specOverlapSamp/specWinSamp, nfft, fMaxHz);
sgtitle(tl, sg, 'FontSize', 10, 'FontWeight', 'bold');

if ~exist(outDir,'dir'), mkdir(outDir); end
outPng = fullfile(outDir, sprintf('Evt%03d_RepSample.png', e));
exportgraphics(f, outPng, 'Resolution', 220);
close(f);
fprintf('Saved: %s\n', outPng);
end

% ----------------------------------------------------------------------
% Helper: find event numbers from PNG names containing "Evt###"
% ----------------------------------------------------------------------
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
