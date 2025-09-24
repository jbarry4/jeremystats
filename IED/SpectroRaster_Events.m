function SpectralRaster_Events(inputFolder, dataMatPath, varargin)

% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));

p.addParameter('anchorMode','firstChMax', @(s) any(strcmpi(s,{'firstChMax','midpoint'})));
p.addParameter('anchorHalfWidthMs', 5e-3,  @(x)isfinite(x)&&x>0);

% Wider window for spectral analysis so 1 s STFT fits (±0.5 s default)
p.addParameter('specWinHalfWidthSec', 0.5, @(x)isfinite(x)&&x>0);

% Spectrogram params (mirroring your Jeremy code)
%  - windowLen = round(SF) samples (1 s), overlap = round(SF/2), freqs = 0.1:0.2:200 Hz
p.addParameter('specFreqs', 0.1:0.2:200, @(v)isnumeric(v) && isvector(v) && all(v>0));
p.addParameter('freqYMax', 200, @(x)isfinite(x)&&x>0);  % for plotting limit

% Global CLim in dB (robust). If empty, auto from data.
p.addParameter('climDB', [], @(x) isempty(x) || (isnumeric(x) && numel(x)==2 && x(1)<x(2)));
p.addParameter('yRobustPct', 99.5, @(x) isfinite(x) && x>0 && x<100);
p.addParameter('climPadFrac', 0.12, @(x) isfinite(x) && x>=0 && x<=0.5);

p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));

% Waveform atop spectrogram: show same time range as spectrogram (true)
p.addParameter('waveformSameWindow', true, @(x)islogical(x) || isnumeric(x));

p.parse(inputFolder, dataMatPath, varargin{:});

inputFolder   = string(p.Results.inputFolder);
dataMatPath   = string(p.Results.dataMatPath);
excelPath     = string(p.Results.excelPath);
channelIdx    = p.Results.channelIndices;
scaleToMicroV = p.Results.scaleToMicroV;

anchorMode    = lower(string(p.Results.anchorMode));
anchorHWms    = p.Results.anchorHalfWidthMs;
specHW        = p.Results.specWinHalfWidthSec;

specFreqs     = p.Results.specFreqs;
freqYMax      = p.Results.freqYMax;

climDBOpt     = p.Results.climDB;
yRobustPct    = p.Results.yRobustPct;
climPadFrac   = p.Results.climPadFrac;

maxEventsPer  = p.Results.maxEventsPerGroup;
waveSameWin   = logical(p.Results.waveformSameWindow);

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

% Output dirs (Spectral)
outRoot = fullfile(inputFolder, "Spectral Raster Output");
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
HWanchor = max(1, round(anchorHWms * sfx));   % ± anchor search
HWspec   = max(1, round(specHW    * sfx));    % ± analysis window
tRelSec  = (-HWspec:HWspec) / sfx;
tRelMs   = tRelSec * 1e3;                     % for plotting labels
winN     = numel(tRelSec);

fprintf('SpectralRaster_Events: sfx=%.1f Hz | spec window ±%.3f s | anchor=%s (±%.1f ms)\n', ...
    sfx, HWspec/sfx, anchorMode, 1e3*HWanchor/sfx);

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

% ---------------- Global dB CLim across ALL events & channels ----------------
if isempty(climDBOpt)
    fprintf('Scanning events/channels to compute global dB CLim (%.2f%% robust)...\n', yRobustPct);
    [pLow, pHigh] = scanSpectralPercentiles([evtSOL(:); evtSPU(:)]);
    if ~isfinite(pLow) || ~isfinite(pHigh) || pHigh<=pLow
        climDB = [-120, -20]; % fallback
    else
        span   = pHigh - pLow;
        pad    = climPadFrac * span;
        climDB = [pLow - pad, pHigh + pad];
    end
else
    climDB = climDBOpt(:).';
end
fprintf('Global dB CLim set to [%.1f, %.1f] dB.\n', climDB(1), climDB(2));

% ---------------- Render groups ----------------
renderGroup(evtSOL, outSOL, 'SOLID', climDB);
renderGroup(evtSPU, outSPU, 'SPUTTER', climDB);

fprintf('Done. Output in: %s\n', outRoot);

% ======================================================================
%                                HELPERS
% ======================================================================

function [pLow, pHigh] = scanSpectralPercentiles(evtList)
    % Robust percentiles across ALL channels & events over the analysis window.
    % We sample dB slices to avoid giant memory use.
    qlow  = 100 - yRobustPct;
    qhigh = yRobustPct;
    sampBucket = [];  % accumulate a manageable random subset of pixels

    rng(1);  % deterministic
    maxKeep = 2e6; % cap number of pixels we keep (adjust as needed)

    for ii = 1:numel(evtList)
        e = evtList(ii);
        rowXL = e;
        if rowXL < 1 || rowXL > NrowsXL, continue; end

        [s0, s1, ok] = getWindowBounds(rowXL);
        if ~ok, continue; end

        % Build quick spectral slices per channel
        for k = 1:nCh
            ch = chList(k);
            sc = scaleVec(ch);
            y  = double(mf.d(ch, s0:s1)) * sc;
            if ~any(isfinite(y)), continue; end

            % Spectrogram params per Jeremy code
            win  = round(sfx);          % 1 s
            ovlp = round(sfx/2);        % 50%
            [S, f, ~] = spectrogram(y, win, ovlp, specFreqs, sfx);
            SdB = 10*log10(abs(S).^2 + eps);

            % Keep only <= freqYMax
            maskF = f <= freqYMax;
            SdB = SdB(maskF, :);

            % Reservoir sample pixels
            v = SdB(:);
            v = v(isfinite(v));
            if isempty(v), continue; end
            if numel(sampBucket) < maxKeep
                need = maxKeep - numel(sampBucket);
                take = min(numel(v), need);
                idx  = randperm(numel(v), take);
                sampBucket = [sampBucket; v(idx)]; %#ok<AGROW>
            end
        end
    end

    if isempty(sampBucket)
        pLow = -120; pHigh = -20; return;
    end
    pLow  = prctile(sampBucket, qlow);
    pHigh = prctile(sampBucket, qhigh);
end

function [s0, s1, ok] = getWindowBounds(rowXL)
    ok = false;
    s0_ev = round(onSamp(rowXL));
    s1_ev = round(offSamp(rowXL));
    if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev), return; end

    switch anchorMode
        case "midpoint"
            anchor = round((s0_ev + s1_ev)/2);
        otherwise
            ancMid  = round((s0_ev + s1_ev)/2);
            a0     = max(1, ancMid - HWanchor);
            a1     = min(nSamp, ancMid + HWanchor);
            refCh   = chList(1);
            yseg0   = double(mf.d(refCh, a0:a1)) * scaleVec(refCh);
            if isempty(yseg0) || all(~isfinite(yseg0)), return; end
            [~, k_rel] = max(yseg0); % positive peak
            anchor = a0 + k_rel - 1;
    end

    s0 = anchor - HWspec;
    s1 = anchor + HWspec;
    if s0 < 1 || s1 > nSamp, return; end
    ok = true;
end

function renderGroup(evtList, outDir, tag, clim)
    if isempty(evtList)
        warning('%s: no events to render.', tag);
        return;
    end
    for ii = 1:numel(evtList)
        e = evtList(ii);
        rowXL = e;
        if rowXL < 1 || rowXL > NrowsXL
            fprintf('%s evt %d: out of Excel bounds. Skipping.\n', tag, e);
            continue;
        end

        [s0, s1, ok] = getWindowBounds(rowXL);
        if ~ok
            fprintf('%s evt %d: invalid/OO bounds window. Skipping.\n', tag, e);
            continue;
        end

        % For each channel, make one figure: waveform (top) + spectrogram (bottom)
        for k = 1:nCh
            ch = chList(k);
            sc = scaleVec(ch);
            y  = double(mf.d(ch, s0:s1)) * sc;

            if ~any(isfinite(y))
                fprintf('%s evt %d ch %d: no data. Skipping.\n', tag, e, ch);
                continue;
            end

            % --- Spectrogram (Jeremy params) ---
            win  = round(sfx);        % 1 s
            ovlp = round(sfx/2);      % 50%
            [S, f, t] = spectrogram(y, win, ovlp, specFreqs, sfx);
            SdB = 10*log10(abs(S).^2 + eps);
            maskF = f <= freqYMax;
            f2 = f(maskF);
            SdB = SdB(maskF,:);

            % Convert t to absolute relative ms (map STFT time centers into tRelMs)
            % t is in seconds relative to start of y; shift by centered window start
            tAbsMs = (t - t(1)) * 1e3 + tRelMs(1); % approximate alignment for display

            % --- Figure ---
            perPx = 300; % height per panel
            figH = 2*perPx + 120;
            figh = figure('Color','w','Position',[80 80 1000 figH],'Visible','off');

            % Waveform (top)
            ax1 = subplot(2,1,1);
            plot(tRelMs, y, 'k-', 'LineWidth', 1);
            grid on; xlim([tRelMs(1), tRelMs(end)]);
            ylabel('Voltage (\muV)');
            ttl = sprintf('%s  |  Evt %d  |  ch %d%s  |  anchor=%s  |  win=\\pm%.3f s', ...
                tag, e, ch, makeChTag(ch), char(anchorMode), HWspec/sfx);
            title(ttl, 'FontSize', 12, 'FontWeight', 'bold');

            % Spectrogram (bottom)
            ax2 = subplot(2,1,2);
            imagesc(tAbsMs, f2, SdB);
            set(gca,'YDir','normal');
            colormap(jet); colorbar;
            caxis(clim);
            xlabel('Time (ms)');
            ylabel('Frequency (Hz)');
            ylim([min(f2), freqYMax]);
            xlim([tRelMs(1), tRelMs(end)]);
            title('Spectrogram (dB)');

            % --- Save ---
            if isempty(kept_channels)
                chLabel = sprintf('row%03d', ch);
            else
                chLabel = sprintf('row%03d_CSC%d', ch, kept_channels(ch));
            end
            outPng = fullfile(outDir, sprintf('Spec_Evt%03d_%s.png', e, chLabel));
            exportgraphics(figh, outPng, 'Resolution', 220);
            close(figh);
            fprintf('Saved %s: %s\n', tag, outPng);
        end
    end
end

function s = makeChTag(ch)
    if isempty(kept_channels)
        s = '';
    else
        s = sprintf(' (CSC%d)', kept_channels(ch));
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
