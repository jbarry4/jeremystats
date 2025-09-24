function SpectrogramRaster_Events(inputFolder, dataMatPath, varargin)
% SpectrogramRaster_Events
% Build a spectrogram raster per event (SOLID/SPUTTER), aligned by first
% channel positive peak near the event midpoint. Saves one PNG per event.
%
% AXES:
%   x: time (ms, relative to anchor)
%   y: frequency (Hz)
%   color: power (dB, 10*log10(|S|.^2))
%
% FOLDERS:
%   <inputFolder>/Spectral Raster Output/Solid/  EvtNNN_SPECT.png
%   <inputFolder>/Spectral Raster Output/Sputter/EvtNNN_SPECT.png
%
% REQUIRED DATA MAT FIELDS:
%   d   [nRows x nSamp]  (signal; assumed µV unless scaled)
%   sfx (scalar, Hz)
%   kept_channels (optional)
%
% REQUIRED LAYOUT IN inputFolder:
%   subfolders "Solid" and "Sputter" with PNGs named like "...Evt###....png"
%   and an Excel (*.xlsx) file with event on/off (samples or seconds)

% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

% Excel + channels + scaling
p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));

% Alignment and window
p.addParameter('winHalfWidthMs',    10e-3, @(x)isfinite(x)&&x>0);   % ±10 ms display
p.addParameter('anchorHalfWidthMs',  5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms anchor search

% Spectrogram params
p.addParameter('specWinMs',    1e-3,  @(x)isfinite(x)&&x>0);        % STFT window length (default 1 ms)
p.addParameter('specOverlap',  0.50,  @(x)isfinite(x)&&x>=0&&x<1);  % fraction overlap
p.addParameter('nfft',         [],    @(x) isempty(x) || (isscalar(x)&&x>0)); % default auto pow2
p.addParameter('fMaxHz',       3000,  @(x)isfinite(x)&&x>0);        % y-axis upper limit

% Color scaling (per-event)
p.addParameter('yRobustPct',   99.5,  @(x) isfinite(x) && x>0 && x<100);
p.addParameter('climPadFrac',  0.12,  @(x) isfinite(x) && x>=0 && x<=0.5); %#ok<NASGU> (kept for API parity)

% Caps
p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));

p.parse(inputFolder, dataMatPath, varargin{:});

inputFolder     = string(p.Results.inputFolder);
dataMatPath     = string(p.Results.dataMatPath);

excelPath       = string(p.Results.excelPath);
channelIdx      = p.Results.channelIndices;
scaleToMicroV   = p.Results.scaleToMicroV;

winHWms         = p.Results.winHalfWidthMs;
anchorHWms      = p.Results.anchorHalfWidthMs;

specWinMs       = p.Results.specWinMs;
specOverlap     = p.Results.specOverlap;
nfftOpt         = p.Results.nfft;
fMaxHz          = p.Results.fMaxHz;

yRobustPct      = p.Results.yRobustPct;
% climPadFrac   = p.Results.climPadFrac;

maxEventsPer    = p.Results.maxEventsPerGroup;

% ---------------- Layout ----------------
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
outSOL  = fullfile(outRoot, "Solid");
outSPU  = fullfile(outRoot, "Sputter");
if ~exist(outRoot,'dir'), mkdir(outRoot); end
if ~exist(outSOL,'dir'),  mkdir(outSOL);  end
if ~exist(outSPU,'dir'),  mkdir(outSPU);  end

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

% Scaling
if numel(scaleToMicroV)==1
    scaleVec = repmat(scaleToMicroV, nRowsAll, 1);
else
    assert(numel(scaleToMicroV) >= nRowsAll, 'scaleToMicroV must be scalar or length >= nRowsAll.');
    scaleVec = scaleToMicroV(:);
end

% ---------------- Windows ----------------
HWwin    = max(1, round(winHWms    * sfx));  % ±display half-width
HWanchor = max(1, round(anchorHWms * sfx));  % ±anchor search
tRelMs   = (-HWwin:HWwin) / sfx * 1e3; %#ok<NASGU> (labeling only)

% ---------------- Read Excel -> on/off (samples) ----------------
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

% ---------------- Events from PNG names ----------------
evtSOL = parseEvtNumsFromPngs(solidDir);
evtSPU = parseEvtNumsFromPngs(sputterDir);
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));
if ~isempty(maxEventsPer)
    evtSOL = evtSOL(1:min(end, maxEventsPer));
    evtSPU = evtSPU(1:min(end, maxEventsPer));
end

% ---------------- Spectrogram params (samples) ----------------
specWinSamp      = max(4, round(specWinMs * sfx));           % at least a few samples
specOverlapSamp  = max(0, min(specWinSamp-1, round(specOverlap * specWinSamp)));
if isempty(nfftOpt)
    nfft = 2^nextpow2(specWinSamp);
else
    nfft = nfftOpt;
end

fprintf(['Spectrogram params: win=%d samp (%.2f ms) | overlap=%d samp (%.0f%%) | nfft=%d | fMax=%.0f Hz | ' ...
         'display window ±%.1f ms | anchor search ±%.1f ms\n'], ...
        specWinSamp, 1e3*specWinSamp/sfx, specOverlapSamp, 100*specOverlapSamp/specWinSamp, ...
        nfft, fMaxHz, 1e3*HWwin/sfx, 1e3*HWanchor/sfx);

% ---------------- Build per group ----------------
renderGroup(evtSOL, outSOL, 'SOLID', mf, sfx, chList, nCh, kept_channels, ...
            onSamp, offSamp, NrowsXL, nSamp, scaleVec, HWanchor, HWwin, ...
            specWinSamp, specOverlapSamp, nfft, fMaxHz, yRobustPct);

renderGroup(evtSPU, outSPU, 'SPUTTER', mf, sfx, chList, nCh, kept_channels, ...
            onSamp, offSamp, NrowsXL, nSamp, scaleVec, HWanchor, HWwin, ...
            specWinSamp, specOverlapSamp, nfft, fMaxHz, yRobustPct);

fprintf('Done. Outputs in:\n  %s\n  %s\n', outSOL, outSPU);
end

% ======================================================================
%                                SUBFUNCTIONS
% ======================================================================

function renderGroup(evtList, outDir, tag, mf, sfx, chList, nCh, kept_channels, ...
                     onSamp, offSamp, NrowsXL, nSamp, scaleVec, HWanchor, HWwin, ...
                     specWinSamp, specOverlapSamp, nfft, fMaxHz, yRobustPct)

if isempty(evtList)
    fprintf('%s: no events to render.\n', tag);
    return;
end

for ii = 1:numel(evtList)
    e = evtList(ii);
    rowXL = e;
    if rowXL < 1 || rowXL > NrowsXL, continue; end

    s0_ev = round(onSamp(rowXL));
    s1_ev = round(offSamp(rowXL));
    if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev), continue; end

    % ---- Anchor: first channel positive peak near midpoint ----
    ancMid = round((s0_ev + s1_ev)/2);
    s0a = max(1, ancMid - HWanchor);
    s1a = min(nSamp, ancMid + HWanchor);
    refCh = chList(1);
    y0 = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
    if isempty(y0) || all(~isfinite(y0)), continue; end
    [~, k_rel] = max(y0);
    anchor = s0a + k_rel - 1;

    % ---- Display window ----
    s0 = anchor - HWwin;
    s1 = anchor + HWwin;
    if s0 < 1 || s1 > nSamp, continue; end

    % ---- Compute channel spectrograms ----
    allPow = [];
    S_store = cell(nCh,1);
    F_store = cell(nCh,1);
    T_store = cell(nCh,1);

    for k = 1:nCh
        ch = chList(k);
        sc = scaleVec(ch);
        y = double(mf.d(ch, s0:s1)) * sc;
        if any(~isfinite(y)), y(~isfinite(y)) = 0; end

        [S, F, T] = spectrogram(y, specWinSamp, specOverlapSamp, nfft, sfx);
        P = 10*log10(abs(S).^2 + eps);

        idxF = F <= fMaxHz;
        F = F(idxF); P = P(idxF, :);

        % Time axis in ms relative to anchor: T starts at 0 at segment start
        Tms = (T - (HWwin/sfx)) * 1e3;

        S_store{k} = P;
        F_store{k} = F;
        T_store{k} = Tms;

        allPow = [allPow; P(:)]; %#ok<AGROW>
    end

    % ---- Robust per-event CLim (dB) ----
    allPow = allPow(isfinite(allPow));
    if isempty(allPow)
        fprintf('Evt %d: no finite spectrogram power; skipping.\n', e);
        continue;
    end
    pUpper = prctile(allPow, yRobustPct);
    pLower = max(min(allPow), pUpper - 40);  % 40 dB dynamic below the robust top

    % ---- Figure: stacked rasters (channel 1 at top) ----
    perRowPx = 105; basePx = 230; maxPx = 5400;
    figH = min(maxPx, basePx + perRowPx * nCh);
    f = figure('Color','w','Position',[60 60 1100 figH],'Visible','off');
    tl = tiledlayout(f, nCh, 1, 'Padding','compact','TileSpacing','compact');

    for k = 1:nCh
        ax = nexttile(tl); hold(ax,'on'); box(ax,'on');

        P = S_store{k};
        F = F_store{k};
        Tms = T_store{k};

        if isempty(P)
            text(ax,0.5,0.5,'(no data)','Units','normalized','HorizontalAlignment','center');
            continue;
        end

        imagesc(ax, Tms, F, P);
        axis(ax,'xy');
        caxis(ax, [pLower pUpper]);
        colormap(ax, parula);

        % Axes formatting
        if k < nCh
            set(ax,'XTickLabel',[]);
        else
            xlabel(ax,'Time (ms)');
        end
        ylabel(ax,'Hz');
        if isempty(kept_channels)
            ttl = sprintf('row %d', chList(k));
        else
            ttl = sprintf('row %d (CSC%d)', chList(k), kept_channels(chList(k)));
        end
        title(ax, ttl, 'FontSize', 9, 'FontWeight','normal');
        ylim(ax, [0, fMaxHz]);
    end

    sg = sprintf(['%s  |  Evt %d  |  anchor: first-ch max (±%.1f ms)  |  window: \\pm%.1f ms  |  ' ...
                  'STFT win=%.2f ms, overlap=%.0f%%, nfft=%d, fMax=%.0f Hz  |  CLim=[%.1f, %.1f] dB'], ...
                  tag, e, 1e3*HWanchor/sfx, 1e3*HWwin/sfx, ...
                  1e3*specWinSamp/sfx, 100*specOverlapSamp/specWinSamp, nfft, fMaxHz, pLower, pUpper);
    sgtitle(tl, sg, 'FontSize', 10, 'FontWeight', 'bold');

    % Attach a single colorbar (to last axes is fine/portable)
    cb = colorbar('eastoutside');
    cb.Label.String = 'Power (dB)';

    if ~exist(outDir,'dir'), mkdir(outDir); end
    outPng = fullfile(outDir, sprintf('Evt%03d_SPECT.png', e));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved spectrogram: %s\n', outPng);
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
