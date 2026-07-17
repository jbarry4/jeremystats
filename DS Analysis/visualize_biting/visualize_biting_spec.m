function visualize_biting_spec(dataDir, badChannels, halfWidthMs, varargin)
% visualize_biting_spec  Render 4-panel voltage/CSD/spectrogram figures for each detected
%                        dentate spike event.
%
% For each event in ets_hp_1_lp_300_nf.mat, a 4-panel PNG is saved:
%   Panel 1 (top-left)    - Voltage raster ± halfWidthMs ms, jet colormap, ± 1000 µV
%   Panel 2 (top-middle)  - CSD raster ± halfWidthMs ms, computed on a channel subset
%   Panel 3 (top-right)   - Stacked CWT spectrograms for specNumChans channels,
%                           jet colormap, log frequency axis, waveform overlay
%   Panel 4 (bottom, full-width) - Voltage raster ± wideHalfWidthS s (context window),
%                                  block-mean decimated for display
%
% Data flow overview:
%   1. All CSC*.ncs files in dataDir are discovered, sorted, and filtered.
%   2. sfx and global_min_T_us are read from the NCS header (reliable; Fs_vec can be 0).
%   3. Event timestamps are loaded from ets_hp_1_lp_300_nf.mat and converted to sample windows.
%   4. PASS A: every event × channel detail window is loaded once and cached in Ycache.
%              Global colour/amplitude limits are derived from all events so figures
%              are visually comparable.
%   5. PASS B: for each event, CSD and CWT are computed from the cached voltage, the wide
%              context window is loaded fresh (too large to cache), figures are composed
%              and saved as PNG, then immediately closed to bound memory usage.
%
% USAGE:
%   visualize_biting_spec(dataDir, badChannels, halfWidthMs)
%
% INPUTS:
%   dataDir      - (string) Full path to the recording session folder.
%                  Must contain CSC*.ncs files and ets_hp_1_lp_300_nf.mat.
%                  Example: 'D:/Data/m22s3jul15/2024-07-15_16-12-27/'
%   badChannels  - (numeric array) CSC channel numbers to exclude.
%                  Example: [8 41 59]. Default: 59.
%   halfWidthMs  - (numeric) Half-width in ms of the detail raster window (Panels 1–3).
%                  Also sets the ± offset applied to event timestamps when building ets.
%                  Default: 50 ms.
%
% OUTPUT:
%   One PNG per event saved to:
%   <scriptDir>/Output2/Visualized_spikes_hp_1_lp_300_nf_CSD_zoomout_<halfWidthMs>ms_spec_<modeTag>/<animalName>/
%
% DEPENDENCIES (must be on the MATLAB path or in the same folder):
%   Nlx2MatCSC.m    - Neuralynx binary NCS importer
%   loadWindow.m    - helper: load a timestamp-bounded voltage snippet from one NCS file
%   parseNcsField.m - helper: extract a numeric value from an NCS header cell array
%   lif.m           - helper: inline ternary (lif(cond, trueStr, falseStr))

% ---- Default argument handling ----
% nargin is the number of arguments actually passed by the caller.
% If fewer than 2 args were passed, or badChannels is empty, use the default.
if nargin < 2 || isempty(badChannels)
    badChannels = 59;
end

% Same default logic for halfWidthMs.
if nargin < 3 || isempty(halfWidthMs)
    halfWidthMs = 50;
end

%% ---- Parameters ----
% These control display and detection behaviour. Adjust as needed.

wideHalfWidthS = 5;      % Half-width in seconds for the wide context window (Panel 3).
minCh          = 1;      % Minimum number of active channels required to plot an event.
maxCh          = 64;     % Maximum number of active channels allowed (filters noisy events).
invertPolarity = true;   % Flip voltage sign — matches the polarity inversion applied in Step 1.
loadMaxCh      = 64;     % Ignore any CSC file with a channel number above this value.
wideTargetCols = 3000;   % Target number of display columns for the wide window (sets decimation).

climPctile     = 99.5;   % Percentile of |voltage| used to set the global colour limit.
climPadFrac    = 0.12;   % Fractional headroom added on top of the percentile limit (prevents clipping).
traceAmpPct    = 99;     % Percentile of |voltage| used to scale the overlaid per-channel traces.
traceHalfRows  = 0.45;   % A traceAmpPct deflection spans ± this many row-units in the raster.

% --- Spectrogram (CWT) parameters ---
% specFocusHighMag: true  = stack the specNumChans channels with the largest mean |voltage|
%                   false = evenly spaced channels across the full probe depth
specFocusHighMag = true;
specFMinHz     = 20;     % Lowest frequency shown on spectrogram (Hz).
specFMaxHz     = 1000;   % Highest frequency shown (capped to Nyquist at runtime).
specClimUpPct  = 99.5;   % Upper percentile used to set the log-power colour limit.
specClimDyn    = 4;      % Dynamic range (decades of log10 magnitude) shown below the upper limit.
specWaveCapUV  = 3000;   % Hard cap on the overlaid waveform amplitude axis (µV).
specWavePadFr  = 0.12;   % Fractional headroom for the waveform axis.
specNumChans   = 6;      % Number of individual channel spectrograms stacked in Panel 3.

%% ---- Output folder ----
% scriptDir is the folder containing this .m file. Output is written relative to it.
% The fallback path is used when mfilename returns empty (e.g. running via eval on a cluster).
scriptDir = fileparts(mfilename('fullpath'));
if isempty(scriptDir)
    scriptDir = '/gpfs2/scratch/syounger/DS_toothy';
end

% Strip trailing slash so fileparts works correctly, then walk up two levels:
%   dataDirStr  -> .../m22s3jul15/2024-07-15_16-12-27   (session folder)
%   parentDir   -> .../m22s3jul15                        (animal folder)
%   animalName  -> m22s3jul15                            (used in output path and figure title)
dataDirStr = char(dataDir);
if ~isempty(dataDirStr) && (dataDirStr(end)=='/' || dataDirStr(end)=='\')
    dataDirStr = dataDirStr(1:end-1);
end
[parentDir, ~] = fileparts(dataDirStr);
[~, animalName] = fileparts(parentDir);

% modeTag labels the output folder so HighMag and EvenSpread runs never overwrite each other.
if specFocusHighMag
    modeTag = 'HighMag';
else
    modeTag = 'EvenSpread';
end

% Build the output directory path, embedding halfWidthMs and modeTag in the folder name.
halfWidthMsChar = num2str(halfWidthMs);
outDirFolder = append('Visualized_spikes_hp_1_lp_300_nf_CSD_zoomout_', halfWidthMsChar, 'ms_spec_', modeTag);
outDir = fullfile(scriptDir, 'Output2', outDirFolder, '/', animalName);
if ~exist(outDir,'dir'), mkdir(outDir); end

fprintf('\n[STEP 2-CSD] %s\n', dataDir);
fprintf('[INFO] Output: %s\n', outDir);

%% ---- Locate and filter CSC files ----
% dir() with ** searches recursively for any file matching CSC*.n* (catches .ncs and .nsc).
files = dir(fullfile(dataDir,'**','CSC*.n*'));
if isempty(files), error('No CSC files in: %s', dataDir); end

% Add a channelNumber field to each struct entry by parsing the integer in the filename.
% E.g. 'CSC7.ncs' -> channelNumber = 7, 'CSC07_001.ncs' -> channelNumber = 7.
% Files that don't match the pattern get channelNumber = NaN and are dropped below.
for i = 1:numel(files)
    tok = regexp(files(i).name, 'CSC(\d+)', 'tokens', 'once');
    if ~isempty(tok)
        files(i).channelNumber = str2double(tok{1});
    else
        files(i).channelNumber = NaN;
    end
end

% Sort the struct array ascending by channelNumber so all downstream indexing is ordered.
[~, ord] = sort([files.channelNumber]);
files = files(ord);

% Build a logical keep mask:
%   - drop NaN entries (no CSC number found)
%   - drop channels above loadMaxCh
%   - drop channels listed in badChannels (e.g. broken electrodes)
keep = ~isnan([files.channelNumber]) & ([files.channelNumber] <= loadMaxCh);
for ch = badChannels
    keep = keep & ([files.channelNumber] ~= ch);
end

% If the same channel number appears more than once (e.g. duplicate files), keep only the first.
[~, ia] = unique([files(keep).channelNumber]);
tmpIdx = find(keep);
keep(:) = false;
keep(tmpIdx(ia)) = true;

% Apply the mask. nums is a convenience vector of channel numbers for label generation.
files = files(keep);
nums  = [files.channelNumber];   % 1 × nCh vector of CSC numbers in sorted order
nCh   = numel(files);
fprintf('[INFO] %d channels.\n', nCh);

%% ---- Read sfx and global_min_T_us from CSC headers ----
% sfx (sampling frequency in Hz) is read from the NCS file header field -SamplingFrequency.
% Reading from the header is more reliable than from per-record Fs_vec, which can be 0
% in some Neuralynx recordings.
hdr0 = Nlx2MatCSC(fullfile(files(1).folder, files(1).name), [0 0 0 0 0], 1, 1, []);
sfx  = parseNcsField(hdr0, 'SamplingFrequency');
if ~isfinite(sfx) || sfx <= 0
    sfx = 30000;   % fallback if header field is missing
    fprintf('[WARN] SamplingFrequency not in header, defaulting to %g Hz\n', sfx);
end
fprintf('[INFO] Fs=%g Hz\n', sfx);

% global_min_T_us is the earliest timestamp (µs) across all channels.
% It serves as the time origin: sample index s corresponds to time
%   t_us = global_min_T_us + (s - 1) / (sfx / 1e6)
% Reading all timestamps (mode 1, no sample data) is the safest approach
% because this Neuralynx importer version requires two parameters for range modes.
all_first_T_us = nan(1, nCh);
for k = 1:nCh
    fn = fullfile(files(k).folder, files(k).name);
    [ts_us] = Nlx2MatCSC(fn, [1 0 0 0 0], 0, 1, []);   % timestamps only, all records
    if ~isempty(ts_us), all_first_T_us(k) = ts_us(1); end
end
global_min_T_us = min(all_first_T_us);
fprintf('[INFO] global_min_T=%g us\n', global_min_T_us);

%% ---- Load detection results ----
% ets_hp_1_lp_300_nf.mat contains Combined_DS_timestamps_sec: an N×1 vector of
% event centre times in seconds, detected externally (e.g. by a dentate spike detector).
%
% Each centre time is expanded into an [onset, offset] pair by subtracting/adding
% halfWidthMs/1000 seconds, then converted to sample indices by multiplying by sfx.
% Result: ets is N×2, where ets(e,1) = onset sample, ets(e,2) = offset sample.
tmp = load(fullfile(dataDir,'ets_hp_1_lp_300_nf.mat'), 'Combined_DS_timestamps_sec');
ets = tmp.Combined_DS_timestamps_sec;

% ech (event-channel matrix) marks which channels were active for each event.
% The original detector used a single threshold channel, so rather than a real
% per-channel mask, the last column is set to true for every event (all events
% are treated as active on the reference channel).
%
% Combined_DS_timestamps_sec is stored as a row vector (1 × N), so size(ets,2)
% returns N. If the variable is ever saved as a column vector (N × 1), use
% numel(ets) instead to be safe.
ech = false(size(ets,2), nCh);
ech(:,end) = true;

% Convert timestamps from seconds to sample indices and build the N×2 onset/offset matrix.
ets = round(sfx * [ets(:) - (halfWidthMs/1000), ets(:) + (halfWidthMs/1000)]);
fprintf('[INFO] %d events  Fs=%g Hz\n', size(ets,1), sfx);

%% ---- Read header once for ADBitVolts ----
% ADBitVolts converts raw 16-bit ADC integers to volts (multiply raw by ADBitVolts * 1e6 for µV).
% loadWindow uses this internally when reading sample data.
hdr        = Nlx2MatCSC(fullfile(files(1).folder,files(1).name),[0 0 0 0 0],1,1,[]);
ADBitVolts = parseNcsField(hdr,'ADBitVolts');
if isnan(ADBitVolts), error('ADBitVolts not found in header.'); end
fprintf('[INFO] ADBitVolts=%.6g\n', ADBitVolts);

%% ---- Spectrogram frequency band (cap to Nyquist) ----
% cwt() requires FrequencyLimits strictly below Nyquist (sfx/2). The 0.99 factor
% leaves a 1% margin so the importer does not throw a boundary error.
% The lower floor of 0.1 Hz prevents specFMin from being set to 0 or negative
% by an unusual parameter combination. If the parameters cross each other after
% clamping (e.g. specFMinHz > sfx/2), the fallback pushes specFMin to 1/100 of specFMax.
specFMax = min(specFMaxHz, sfx/2 * 0.99);
specFMin = max(specFMinHz, 0.1);
if specFMin >= specFMax, specFMin = specFMax/100; end
fprintf('[INFO] Spectrogram band: %.1f - %.1f Hz (CWT) | mode: %s\n', specFMin, specFMax, modeTag);

%% ---- Select events ----
% chCount = number of active channels per event (row sum of ech).
% Only events within [minCh, maxCh] active channels are plotted.
% evtIdx maps from the plotting index k to the original event row index e in ets/ech.
chCount = sum(ech(:,1:nCh), 2);
evtIdx  = find(chCount >= minCh & chCount <= maxCh);
nEvt    = numel(evtIdx);
fprintf('[INFO] %d events selected.\n', nEvt);
if nEvt == 0, fprintf('[INFO] Nothing to plot.\n'); return; end

%% ---- Window geometry ----
% HW_us: half-width of the detail window in microseconds (used with Nlx2MatCSC timestamps).
% nSamp: total number of samples in the detail window (symmetric around event centre).
% tRelMs: relative time axis in ms for Panels 1 & 2 (zero = event centre).
HW_us  = halfWidthMs * 1000;
nSamp  = round(2 * HW_us * sfx / 1e6) + 1;
tRelMs = linspace(-halfWidthMs, halfWidthMs, nSamp);

% Wide window geometry for Panel 3.
% wideDec: decimation factor — nSampWide raw samples are averaged in blocks of wideDec
%          to produce ~wideTargetCols display columns (keeps the image manageable).
HWwide_us = wideHalfWidthS * 1e6;
nSampWide = round(2 * HWwide_us * sfx / 1e6) + 1;
wideDec   = max(1, floor(nSampWide / wideTargetCols));
fprintf('[INFO] Wide window: %d samples -> decimate x%d for display.\n', nSampWide, wideDec);

% csdChIdx: indices (1-based, into the nCh sorted channel array) selecting which channels
% are used for CSD. The CSD formula requires at least 3 channels; edge rows are NaN.
% Common alternatives:
%   [1:nCh]          - all channels (default)
%   [1:4, 5:2:nCh]  - first four dense, then every other (reduces redundancy on long probes)
% nCsdCh: number of channels in the CSD subset.
csdChIdx = [1:1:nCh];
nCsdCh   = numel(csdChIdx);

%% ---- PASS A: load every ± halfWidthMs window once, cache, gather scale stats ----
% Pass A reads every event × channel voltage window exactly once and caches the result.
% This avoids re-reading the same file data in Pass B and lets us compute global colour
% limits that are consistent across all events before any figure is drawn.
fprintf('[INFO] Pass A: loading %d event windows (%d channels each = %d reads)...\n', ...
    nEvt, nCh, nEvt*nCh);

% Per-event cache and scalar statistics arrays.
Ycache  = cell(nEvt,1);     % Ycache{k} = nCh × nSamp single matrix of µV values
centerS = nan(nEvt,1);      % Event centre time in seconds from recording start
onS     = nan(nEvt,1);      % Event onset  time in seconds from recording start
offS    = nan(nEvt,1);      % Event offset time in seconds from recording start
perEvtClim  = nan(nEvt,1);  % Per-event voltage colour limit (climPctile of |Y|)
perEvtTrace = nan(nEvt,1);  % Per-event trace amplitude estimate (traceAmpPct of |Y|)
perEvtCSD   = nan(nEvt,1);  % Per-event CSD colour limit (climPctile of |C|)

logEveryA   = max(1, round(nEvt/100));   % Print progress roughly every 1% of events
emptyTotalA = 0;                         % Running count of channel windows that returned all zeros
tA = tic;
for k = 1:nEvt
    e = evtIdx(k);   % original event index into ets/ech

    % Convert sample-index onset/offset to an absolute timestamp anchor (µs).
    % anchor_samp is the centre sample; anchor_ts_us is its absolute time in µs.
    anchor_samp  = round(mean(ets(e,:)));
    anchor_ts_us = global_min_T_us + (anchor_samp - 1) / (sfx/1e6);
    t0_us = anchor_ts_us - HW_us;   % window start (µs)
    t1_us = anchor_ts_us + HW_us;   % window end   (µs)

    % Load one nSamp-column voltage snippet per channel via loadWindow.
    % loadWindow calls Nlx2MatCSC internally with timestamp-range extraction
    % and applies ADBitVolts scaling and optional polarity inversion.
    Y = zeros(nCh, nSamp, 'single');
    nEmptyCh = 0;
    for ch = 1:nCh
        fn = fullfile(files(ch).folder, files(ch).name);
        Y(ch,:) = loadWindow(fn, t0_us, t1_us, sfx, ADBitVolts, invertPolarity, nSamp);
        if ~any(Y(ch,:)), nEmptyCh = nEmptyCh + 1; end
    end
    emptyTotalA = emptyTotalA + nEmptyCh;
    Ycache{k}  = Y;

    % Store timing info for use in Pass B figure labels and event-extent markers.
    centerS(k)   = (anchor_ts_us - global_min_T_us) / 1e6;
    onS(k)       = (ets(e,1) - 1) / sfx;
    offS(k)      = (ets(e,2) - 1) / sfx;

    % Collect voltage statistics for global colour scaling.
    v = abs(Y(isfinite(Y)));
    if ~isempty(v)
        perEvtClim(k)  = prctile(v, climPctile);
        perEvtTrace(k) = prctile(v, traceAmpPct);
    end

    % CSD (current source density) = negative second spatial derivative across channels.
    % Computed on the csdChIdx subset. Edge rows are left NaN (derivative undefined there).
    Ysub = Y(csdChIdx, :);
    C = nan(nCsdCh, nSamp, 'single');
    if nCsdCh >= 3
        C(2:end-1,:) = -( Ysub(3:end,:) - 2*Ysub(2:end-1,:) + Ysub(1:end-2,:) );
    end
    vc = abs(C(isfinite(C)));
    if ~isempty(vc), perEvtCSD(k) = prctile(vc, climPctile); end

    % Progress logging (~100 lines total across the pass).
    if k==1 || mod(k,logEveryA)==0 || k==nEvt
        el   = toc(tA);
        rate = k/max(el,eps);
        eta  = (nEvt-k)/max(rate,eps);
        fprintf('[A] %4d/%4d (%5.1f%%) | %.1f evt/s | elapsed %d:%02d | ETA %d:%02d | empty ch so far %d\n', ...
            k, nEvt, 100*k/nEvt, rate, ...
            floor(el/60), mod(round(el),60), floor(eta/60), mod(round(eta),60), emptyTotalA);
    end
end
fprintf('[INFO] Pass A done in %.1f s. Empty channel-windows: %d / %d (%.2f%%).\n', ...
    toc(tA), emptyTotalA, nEvt*nCh, 100*emptyTotalA/max(nEvt*nCh,1));
if emptyTotalA > 0.5*nEvt*nCh
    warning('Pass A: over half of channel windows loaded empty -- check ts alignment / Nlx2MatCSC.');
end

% ---- Global colour limits ----
% Taking the MAX across all events makes the colour scale identical on every figure,
% so events are visually comparable. climPadFrac adds a small buffer above the max.
climGlobal = max(perEvtClim(isfinite(perEvtClim)));
if isempty(climGlobal) || ~isfinite(climGlobal) || climGlobal<=0, climGlobal = 1; end
climGlobal = (1 + climPadFrac) * climGlobal;   % voltage colour limit (µV)

csdClim = max(perEvtCSD(isfinite(perEvtCSD)));
if isempty(csdClim) || ~isfinite(csdClim) || csdClim<=0, csdClim = 1; end
csdClim = (1 + climPadFrac) * csdClim;         % CSD colour limit (arbitrary units)

% traceGain converts µV to row-units for the overlaid per-channel traces.
% A deflection of traceAmp µV maps to ± traceHalfRows rows in the raster.
traceAmp = max(perEvtTrace(isfinite(perEvtTrace)));
if isempty(traceAmp) || ~isfinite(traceAmp) || traceAmp<=0, traceAmp = 1; end
traceGain = traceHalfRows / traceAmp;

fprintf('[INFO] Voltage CLim = +/-%.2f uV | CSD CLim = +/-%.2f a.u. | trace %.2f uV = %.2f rows\n', ...
    climGlobal, csdClim, traceAmp, traceHalfRows);

%% ---- PASS B: render 3-panel figures ----
% For each event, load the wide context window on demand, build the three axes,
% export as PNG, and close the figure immediately to keep memory usage low.
fprintf('[INFO] Pass B: rendering %d figures (each loads a +/-%gs wide window)...\n', nEvt, wideHalfWidthS);
tB = tic;
for k = 1:nEvt
    e       = evtIdx(k);
    Y       = Ycache{k};             % nCh × nSamp voltage matrix from Pass A
    active  = logical(ech(e,1:nCh)); % which channels fired for this event
    nActive = sum(active);

    anchor_ts_us = global_min_T_us + centerS(k)*1e6;

    % Event extent in relative time (used for shaded region markers on the plots).
    onRelMs  = (onS(k) - centerS(k)) * 1000;   % onset  offset from centre (ms)
    offRelMs = (offS(k) - centerS(k)) * 1000;   % offset offset from centre (ms)
    onRelS   =  onS(k) - centerS(k);            % onset  offset from centre (s)
    offRelS  = offS(k) - centerS(k);            % offset offset from centre (s)

    % Recompute CSD from the cached voltage using the channel subset.
    Ysub = Y(csdChIdx, :);
    C = nan(nCsdCh, nSamp, 'single');
    if nCsdCh >= 3
        C(2:end-1,:) = -( Ysub(3:end,:) - 2*Ysub(2:end-1,:) + Ysub(1:end-2,:) );
    end

    % ---- Pick specNumChans channels for the spectrogram stack ----
    nTake = min(specNumChans, nCh);
    if specFocusHighMag
        % Highest average magnitude: channels with the largest mean |voltage| in the window.
        magByCh = mean(abs(double(Y)), 2, 'omitnan');
        [~, specOrd] = sort(magByCh, 'descend');
        specChans = specOrd(1:nTake);
    else
        % Even spread: evenly spaced indices across the full probe depth.
        idx = unique(round(linspace(1, nCh, nTake)));
        if numel(idx) < nTake
            missing = setdiff(1:nCh, idx);
            idx = [idx, missing(1:(nTake - numel(idx)))];
        end
        specChans = idx(:);
    end
    specChans = sort(specChans);   % display top-to-bottom by depth
    nSpec = numel(specChans);

    % ---- Per-channel CWT (one small spectrogram per channel) ----
    % cwt() returns:
    %   Cj - complex wavelet coefficients, size [nFreq × nSamp]
    %   Fj - frequency axis (Hz), length nFreq
    % log10(|Cj| + eps) converts to log-power (dB-like). eps prevents log10(0).
    % MATLAB's cwt may return Fj in descending order; flipud ensures low freq is at bottom
    % so the imagesc Y axis reads correctly when YDir='normal'.
    %
    % All channels are interpolated onto a shared 256-point log-spaced frequency grid
    % (fGrid) so that imagesc tiles can be stacked without per-channel axis mismatches.
    % fGrid is built from the first channel's frequency range and reused for all others.
    Pg = cell(nSpec,1); Wv = cell(nSpec,1);
    fGrid = []; fLoData = []; fHiData = [];
    for jj = 1:nSpec
        yj = double(Y(specChans(jj),:));
        yj(~isfinite(yj)) = 0;                              % NaN gaps → 0 (no contribution to CWT)
        [Cj, Fj] = cwt(yj, sfx, 'FrequencyLimits', [specFMin specFMax]);
        Pj = log10(abs(Cj) + eps);                          % log-power: nFreq × nSamp
        if numel(Fj) > 1 && Fj(1) > Fj(end)               % normalise to ascending freq order
            Fj = flipud(Fj); Pj = flipud(Pj);
        end
        if isempty(fGrid)                                   % build shared grid from first channel
            fLoData = min(Fj); fHiData = max(Fj);
            fGrid   = logspace(log10(fLoData), log10(fHiData), 256);
        end
        Pg{jj} = interp1(Fj, Pj, fGrid, 'linear');         % resample onto common grid: 256 × nSamp
        Wv{jj} = yj;                                        % store raw waveform for overlay
    end

    % Shared colour scaling: pHi = specClimUpPct-ile of all log-power values across all channels.
    % pLo = pHi - specClimDyn clips specClimDyn decades of dynamic range below the peak.
    % Deriving limits from all channels together keeps rectangles on the same visual scale.
    allP = cell2mat(cellfun(@(x) x(:), Pg, 'UniformOutput', false));
    allP = allP(isfinite(allP));
    if isempty(allP), pHi = 0; else, pHi = prctile(allP, specClimUpPct); end
    pLo = pHi - specClimDyn;

    % Shared waveform amplitude axis: wMax is the traceAmpPct-ile of |voltage| across all
    % selected channels, with fractional headroom added. Hard cap at specWaveCapUV µV
    % prevents an unusually noisy channel from squashing all others to a flat line.
    allW = abs(cell2mat(cellfun(@(x) x(:), Wv, 'UniformOutput', false)));
    wRob = prctile(allW(isfinite(allW)), traceAmpPct);
    if isempty(wRob) || ~isfinite(wRob) || wRob <= 0, wRob = 1; end
    wMax = (1 + specWavePadFr) * wRob;
    if wMax > specWaveCapUV, wMax = specWaveCapUV; end

    % ---- Load wide context window (± wideHalfWidthS s) ----
    % This window is loaded fresh per event (not cached) to keep Pass A memory bounded.
    % wideDec block-mean decimation reduces nSampWide columns to ~wideTargetCols for display.
    t0w = anchor_ts_us - HWwide_us;
    t1w = anchor_ts_us + HWwide_us;
    Yw  = zeros(nCh, nSampWide, 'single');
    for ch = 1:nCh
        fn = fullfile(files(ch).folder, files(ch).name);
        Yw(ch,:) = loadWindow(fn, t0w, t1w, sfx, ADBitVolts, invertPolarity, nSampWide);
    end
    if wideDec > 1
        ncol = floor(nSampWide / wideDec);
        Ywd  = reshape(Yw(:,1:ncol*wideDec), nCh, wideDec, ncol);
        Yw_disp = squeeze(mean(Ywd, 2, 'omitnan'));      % nCh × ncol, block-averaged
        tWideS  = linspace(-wideHalfWidthS, wideHalfWidthS, ncol);
    else
        Yw_disp = Yw;
        tWideS  = linspace(-wideHalfWidthS, wideHalfWidthS, nSampWide);
    end

    % Y-axis tick labels: 'CSC<n>' for inactive channels, 'CSC<n> *' for active ones.
    L = cell(nCh,1);
    for ch = 1:nCh
        L{ch} = sprintf('CSC%d%s', nums(ch), lif(active(ch),' *',''));
    end

    % ---- Figure layout ----
    % Panel height scales with nCh so labels remain readable for both small and large arrays.
    % Figure is created off-screen (Visible off) and closed after saving.
    panelPx = max(340, 150 + 11*nCh);
    figH    = min(3600, 2*panelPx + 300);
    f = figure('Color','w','Position',[40 50 2400 figH],'Visible','off');
    tl = tiledlayout(f, 2, 3, 'TileSpacing','compact', 'Padding','compact');

    % ----- Panel 1 (top-left): voltage raster ± halfWidthMs ms -----
    % imagesc maps Y (nCh × nSamp) to colour using the jet colormap and ± 1000 µV limits.
    % Per-channel traces are overlaid: red for active channels, semi-transparent black for inactive.
    % xregion shades the detected event onset-to-offset interval.
    ax1 = nexttile(tl);
    imagesc(ax1, tRelMs, 1:nCh, Y);
    set(ax1,'YDir','reverse'); colormap(ax1, jet); clim(ax1,[-1000 1000]);
    hold(ax1,'on');
    xregion(ax1, onRelMs, offRelMs, 'FaceColor',[0 0 0], 'FaceAlpha',0.06);
    xline(ax1, 0, '--k', 'LineWidth',1.0, 'Alpha',0.7);
    for ch = 1:nCh
        yrow = double(ch) - traceGain * double(Y(ch,:));
        if active(ch)
            plot(ax1, tRelMs, yrow, 'Color',[0.85 0 0], 'LineWidth',0.9);
        else
            plot(ax1, tRelMs, yrow, 'Color',[0 0 0 0.45], 'LineWidth',0.4);
        end
    end
    ylim(ax1,[0.5 nCh+0.5]); xlim(ax1,[-halfWidthMs halfWidthMs]);
    set(ax1,'YTick',1:nCh,'YTickLabel',L,'FontSize',7);
    xlabel(ax1,'Relative time (ms)'); ylabel(ax1,'Channel');
    title(ax1,'Voltage raster (\pm50 ms)','FontSize',10,'FontWeight','bold');
    cb1 = colorbar(ax1); ylabel(cb1,'\muV');

    % ----- Panel 2 (top-right): CSD raster ± halfWidthMs ms -----
    % C is nCsdCh × nSamp. NaN edge rows are transparent (AlphaData).
    % Colour limits are set globally across all events for comparability.
    ax2 = nexttile(tl);
    imagesc(ax2, tRelMs, 1:nCsdCh, C, 'AlphaData', ~isnan(C));
    set(ax2,'YDir','reverse','Color','w'); colormap(ax2, jet); clim(ax2,[-200 200]);
    hold(ax2,'on');
    xline(ax2, 0, '--k', 'LineWidth',1.0, 'Alpha',0.7);
    ylim(ax2,[0.5 nCsdCh+0.5]); xlim(ax2,[-halfWidthMs halfWidthMs]);
    set(ax2,'YTick',1:nCsdCh,'YTickLabel',L(csdChIdx),'FontSize',7);
    xlabel(ax2,'Relative time (ms)'); ylabel(ax2,'Channel');
    title(ax2,'CSD raster (\pm50 ms)','FontSize',10,'FontWeight','bold');
    cb2 = colorbar(ax2); ylabel(cb2,'CSD (a.u.)');

    % ----- Panel 3 (top-right): stacked CWT spectrograms -----
    % A nested nSpec×1 tiledlayout (t3) is placed inside tile 3 of the outer layout (tl).
    % Setting t3.Layout.Tile = 3 and TileSpan = [1 1] anchors it to exactly that tile cell.
    % Each sub-tile shows one channel's log-power spectrogram (imagesc on fGrid × tRelMs).
    %
    % Waveform overlay:
    %   yn   = voltage normalised to ±1 (hard-clamped so it never leaves the axes).
    %   yWov = yn mapped into log-frequency space centred on the geometric mean of the axis:
    %          10^( mid + yn * 0.42 * range )   where mid = (loF+hiF)/2, range = hiF-loF.
    %   Plotted twice: thick black (k) underneath for outline, thin white (w) on top for fill.
    %
    % axj.Layer = 'top' forces the overlaid line graphics above the imagesc pixel layer.
    % X tick labels are suppressed on all but the last sub-tile to reduce clutter.
    t3 = tiledlayout(tl, nSpec, 1, 'TileSpacing','loose', 'Padding','compact');
    t3.Layout.Tile = 3; t3.Layout.TileSpan = [1 1];
    loF = log10(fLoData); hiF = log10(fHiData);   % log10 of frequency axis endpoints
    axG = gobjects(nSpec,1);
    for jj = 1:nSpec
        axj = nexttile(t3); axG(jj) = axj;
        imagesc(axj, tRelMs, fGrid, Pg{jj});       % colour = log10 power (fGrid × tRelMs)
        hold(axj, 'on');
        set(axj, 'YScale','log', 'YDir','normal'); % log frequency axis, low freq at bottom
        ylim(axj, [fLoData fHiData]);
        clim(axj, [pLo pHi]);
        colormap(axj, jet);
        % Map normalised waveform amplitude into log-frequency space for overlay.
        yn   = max(-1, min(1, Wv{jj} / wMax));                    % clamp to ±1
        yWov = 10.^((loF+hiF)/2 + yn*0.42*(hiF-loF));             % centre ± 42% of log range
        plot(axj, tRelMs, yWov, 'k-', 'LineWidth', 1.6);          % black outline
        plot(axj, tRelMs, yWov, 'w-', 'LineWidth', 0.9);          % white fill on top
        xlim(axj, [-halfWidthMs halfWidthMs]);
        xline(axj, 0, '--w', 'LineWidth',0.8, 'Alpha',0.7);       % event centre marker
        axj.Layer = 'top'; axj.FontSize = 7;
        ylabel(axj, 'Hz', 'FontSize',7);
        text(axj, 0.015, 0.86, sprintf('CSC%d', nums(specChans(jj))), ...
             'Units','normalized', 'FontSize',8, 'FontWeight','bold', ...
             'Color','k', 'BackgroundColor','w', 'EdgeColor','k', 'Margin',1);
        if jj < nSpec, axj.XTickLabel = []; else, xlabel(axj,'Relative time (ms)','FontSize',8); end
    end
    % Single shared colorbar attached to the last sub-axes. cbSpec.Layout.Tile = 'east'
    % places it to the right of the nested tiledlayout, not to the right of the full figure.
    cbSpec = colorbar(axG(end)); cbSpec.Layout.Tile = 'east';
    cbSpec.Label.String = 'Power (dB)';
    title(t3, sprintf('Spectrogram (CWT) \\bullet %d ch [%s]', nSpec, modeTag), ...
        'FontSize',10, 'FontWeight','bold');

    % ----- Panel 4 (bottom, full-width): wide voltage raster ± wideHalfWidthS s -----
    % Spans all 3 columns of the tiled layout.
    % Yw_disp is the block-mean decimated version of the full-width window.
    % Traces are overlaid at reduced line width (more data visible, less clutter).
    ax4 = nexttile(tl, 4, [1 3]);
    imagesc(ax4, tWideS, 1:nCh, Yw_disp);
    set(ax4,'YDir','reverse'); colormap(ax4, jet); clim(ax4,[-1000 1000]);
    hold(ax4,'on');
    xregion(ax4, onRelS, offRelS, 'FaceColor',[0 0 0], 'FaceAlpha',0.10);
    xline(ax4, 0, '--k', 'LineWidth',1.0, 'Alpha',0.7);
    for ch = 1:nCh
        yrow = double(ch) - traceGain * double(Yw_disp(ch,:));
        if active(ch)
            plot(ax4, tWideS, yrow, 'Color',[0.85 0 0], 'LineWidth',0.6);
        else
            plot(ax4, tWideS, yrow, 'Color',[0 0 0 0.40], 'LineWidth',0.3);
        end
    end
    ylim(ax4,[0.5 nCh+0.5]); xlim(ax4,[-wideHalfWidthS wideHalfWidthS]);
    set(ax4,'YTick',1:nCh,'YTickLabel',L,'FontSize',7);
    xlabel(ax4,'Relative time (s)'); ylabel(ax4,'Channel');
    title(ax4, sprintf('Voltage raster (\\pm%g s context, with traces)', wideHalfWidthS), ...
        'FontSize',10,'FontWeight','bold');
    cb4 = colorbar(ax4); ylabel(cb4,'\muV');

    % ----- Overall figure title -----
    % hms converts centerS (seconds from recording start) to HH:MM:SS.mmm for readability.
    % Underscores in animalName are escaped so MATLAB's TeX renderer doesn't treat them as subscript.
    hms = char(duration(0,0,centerS(k),'Format','hh:mm:ss.SSS'));
    animalNameDisp = strrep(animalName, '_', '\_');
    specChLabels = strjoin(arrayfun(@(c) sprintf('CSC%d', nums(c)), specChans(:).', 'UniformOutput', false), ', ');
    sgtitle(tl, { ...
        sprintf('%s   |   Event %03d   |   %d active channels', animalNameDisp, e, nActive), ...
        sprintf('t = %.3f s  (%s into recording)   |   Fs %g Hz   |   V CLim \\pm%.1f \\muV   |   CSD CLim \\pm%.1f a.u.', ...
            centerS(k), hms, sfx, climGlobal, csdClim), ...
        sprintf('Spec [%s] (%s)', specChLabels, modeTag) }, ...
        'FontSize',11,'FontWeight','bold');

    % Save as PNG and close immediately to free memory before the next event.
    outPng = fullfile(outDir, sprintf('Raster_Evt%03d_%dch.png', e, nActive));
    exportgraphics(f, outPng, 'Resolution',220);
    close(f);

    elB  = toc(tB);
    rate = k/max(elB,eps);
    eta  = (nEvt-k)/max(rate,eps);
    fprintf('[B] %4d/%4d (%5.1f%%) | %.2f fig/s | elapsed %d:%02d | ETA %d:%02d | Evt %03d (%d ch)\n', ...
        k, nEvt, 100*k/nEvt, rate, ...
        floor(elB/60), mod(round(elB),60), floor(eta/60), mod(round(eta),60), e, nActive);
end

fprintf('\n[STEP 2-CSD] Done in %.1f s. Output: %s\n', toc(tB), outDir);

end

function val = parseNcsField(hdr, fieldName)
% parseNcsField  Extract a numeric value from a Neuralynx NCS file header.
%
% NCS headers are cell arrays of strings. Each line looks like:
%   -FieldName  1.2207e-007
%
% INPUTS:
%   hdr       - cell array of header lines returned by Nlx2MatCSC with ExtractHeader=1
%   fieldName - (string) name of the field to find, e.g. 'ADBitVolts' or 'SamplingFrequency'
%
% OUTPUT:
%   val - numeric value parsed from the matching header line, or NaN if not found.
    val = NaN;
    pat = ['-', fieldName, '\s+([\d.eE+\-]+)'];
    for i = 1:numel(hdr)
        tok = regexp(char(hdr{i}), pat, 'tokens', 'once');
        if ~isempty(tok)
            val = str2double(tok{1});
            return;
        end
    end
end
