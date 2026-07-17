%% 2_v2_visualize.m  Step 2 (v2 + spectrogram): voltage + CSD + time-freq + wide context
%
% Variant of 2_1_visualize.m. For each detected event it renders a 2x3 layout:
%   top-left     Voltage raster, +/-50 ms  (channels x time, colour = uV) with the
%                per-channel oscillation traces superimposed -- the event detail.
%   top-middle   CSD raster, +/-50 ms      current-source density = -d2V/dchannel^2,
%                blank (NaN) first/last rows, jet colormap, robust CLim.
%   top-right    Spectrogram, +/-50 ms     time-frequency map of the "driver" channel
%   (NEW)        (the active channel with the largest deflection). Continuous wavelet
%                transform (CWT), log frequency axis (low freq at bottom), jet colormap,
%                power in dB, with the driver waveform overlaid (white line, black
%                outline) -- same look/feel as
%                Scalogram_Waveform_Stacked_ThirdEvent_Pipeline.m.
%   bottom       Voltage raster, +/-5 s    full-width context window (loaded on
%   (spans       demand, block-mean decimated for display) WITH per-channel traces
%   all 3 cols)  overlaid, so each event can be seen in the surrounding recording.
%
% Called via eval(fileread(...)) from 2_v2_visualize.sbat.
% Required workspace variables (set by sbat before eval):
%   dataDir       - same animal folder used in Step 1 (contains ets/ech/detector_meta)
%   fiftyNineBad  - logical true/false
% Optional workspace variables:
%   trialMaxEvents - if set (>0), only the first N selected events are rendered
%                    (trial mode). Leave unset/0 to render everything.
%
% Reads the band-pass+notch detections from 1_1_ied_detect.m
% (ets/ech_hp_1_lp_300_nf.mat).
%
% One PNG per event is saved to:
%   <Take2>/Output2/Visualized_spikes_hp_1_lp_300_nf_CSD_zoomout_spectrogram/<animalName>/

if ~exist('fiftyNineBad','var') || isempty(fiftyNineBad)
    fiftyNineBad = false;
end
if ~exist('trialMaxEvents','var') || isempty(trialMaxEvents)
    trialMaxEvents = 0;     % 0 => render all selected events
end

% ############################################################################
% ##   >>>>>  SPECTROGRAM CHANNEL-SELECTION MODE  --  TRUE/FALSE FLAG  <<<<<  ##
% ############################################################################
% ##                                                                        ##
% ##   specFocusHighMag = TRUE   -> FOCUS ON HIGHEST AVERAGE MAGNITUDE       ##
% ##                                the specNumChans channels with the       ##
% ##                                largest MEAN |voltage| in the window     ##
% ##                                (the "hottest" channels of the event).   ##
% ##                                                                         ##
% ##   specFocusHighMag = FALSE  -> EVEN SPREAD TOP-TO-BOTTOM                 ##
% ##                                specNumChans channels spaced evenly       ##
% ##                                across the whole probe depth              ##
% ##                                (row 1 .. row nCh), regardless of power.  ##
% ##                                                                         ##
% ##   The .sbat launcher runs BOTH modes and overrides this flag; the       ##
% ##   default below is only used when the script is run by hand.            ##
% ##   Output goes to a mode-specific folder so the two never overwrite.     ##
% ############################################################################
if ~exist('specFocusHighMag','var') || isempty(specFocusHighMag)
    specFocusHighMag = true;   % <-- DEFAULT (used only if launcher does not set it)
end
specFocusHighMag = logical(specFocusHighMag);

%% ---- Parameters ----
halfWidthMs    = 50;     % ms either side of event centre (panels 1, 2 & 3)
wideHalfWidthS = 5;      % s  either side of event centre (panel 4, context)
minCh          = 1;      % include events with >= this many active channels
maxCh          = 64;     % include events with <= this many active channels
invertPolarity = true;   % match the polarity flip applied in Step 1
loadMaxCh      = 64;     % ignore CSC numbers above this
wideTargetCols = 3000;   % decimate the wide window down to ~this many columns

climPctile     = 99.5;   % robust percentile for the global colour limit
climPadFrac    = 0.12;   % fractional headroom added to the colour limit
traceAmpPct    = 99;     % robust percentile used to scale overlaid traces
traceHalfRows  = 0.45;   % a "traceAmpPct" deflection fills +/- this many rows

% --- Spectrogram (CWT) params (inspired by Scalogram_...ThirdEvent_Pipeline) ---
specFMinHz     = 20;     % lowest frequency shown
specFMaxHz     = 1000;   % highest frequency shown (capped to Nyquist at runtime)
specClimUpPct  = 99.5;   % upper percentile for log-power colour scaling
specClimDyn    = 4;      % dynamic range (decades of log10 magnitude) below upper
specWaveCapUV  = 3000;   % hard cap on the overlaid waveform amplitude axis (uV)
specWavePadFr  = 0.12;   % fractional headroom for the overlaid waveform axis
specNumChans   = 6;      % number of individual channel spectrograms stacked in box 3

%% ---- Output folder (mode-specific so the two runs never overwrite) ----
if specFocusHighMag
    modeTag = 'HighMag';        % highest average magnitude channels
else
    modeTag = 'EvenSpread';     % even spread top-to-bottom
end
scriptDir = fileparts(mfilename('fullpath'));
if isempty(scriptDir)
    scriptDir = '/users/s/a/sakhava1/scratch/KCNT1 Urethane/Take 2';
end
[~, animalName] = fileparts(char(dataDir));
outDir = fullfile(scriptDir, 'Output2', ...
    ['Visualized_spikes_hp_1_lp_300_nf_CSD_zoomout_spectrogram_' modeTag], animalName);
if ~exist(outDir,'dir'), mkdir(outDir); end

fprintf('\n[STEP 2-v2 SPEC | mode=%s] %s\n', modeTag, dataDir);
fprintf('[INFO] Output: %s\n', outDir);
fprintf('[INFO] Spectrogram channel mode: %s\n', modeTag);
if trialMaxEvents > 0
    fprintf('[INFO] TRIAL MODE: rendering at most %d events.\n', trialMaxEvents);
end

%% ---- Load detection results ----
load(fullfile(dataDir,'ets_hp_1_lp_300_nf.mat'), 'ets');
load(fullfile(dataDir,'ech_hp_1_lp_300_nf.mat'), 'ech');
load(fullfile(dataDir,'detector_meta.mat'), 'detector_meta');
global_min_T_us = detector_meta.global_min_T_us;
sfx             = detector_meta.sfx;
fprintf('[INFO] %d events  Fs=%g Hz\n', size(ets,1), sfx);

%% ---- Locate and filter CSC files ----
files = dir(fullfile(dataDir,'**','CSC*.n*'));
if isempty(files), error('No CSC files in: %s', dataDir); end

nums = nan(1, numel(files));
for i = 1:numel(files)
    tok = regexp(files(i).name, 'CSC(\d+)', 'tokens', 'once');
    if ~isempty(tok), nums(i) = str2double(tok{1}); end
end

keep = ~isnan(nums) & (nums <= loadMaxCh);
if fiftyNineBad, keep = keep & (nums ~= 59); end
[~, ia] = unique(nums(keep));
tmpIdx = find(keep);
keep(:) = false;
keep(tmpIdx(ia)) = true;

files = files(keep); nums = nums(keep);
[nums, ord] = sort(nums); files = files(ord);
nCh = numel(files);
fprintf('[INFO] %d channels.\n', nCh);

%% ---- Read header once for ADBitVolts ----
hdr        = Nlx2MatCSC(fullfile(files(1).folder,files(1).name),[0 0 0 0 0],1,1,[]);
ADBitVolts = parseNcsField(hdr,'ADBitVolts');
if isnan(ADBitVolts), error('ADBitVolts not found in header.'); end
fprintf('[INFO] ADBitVolts=%.6g\n', ADBitVolts);

%% ---- Spectrogram frequency band (cap to Nyquist) ----
specFMax = min(specFMaxHz, sfx/2 * 0.99);
specFMin = max(specFMinHz, 0.1);
if specFMin >= specFMax, specFMin = specFMax/100; end
fprintf('[INFO] Spectrogram band: %.1f - %.1f Hz (CWT).\n', specFMin, specFMax);

%% ---- Select events ----
chCount = sum(ech(:,1:nCh), 2);
evtIdx  = find(chCount >= minCh & chCount <= maxCh);
if trialMaxEvents > 0 && numel(evtIdx) > trialMaxEvents
    evtIdx = evtIdx(1:trialMaxEvents);
end
nEvt    = numel(evtIdx);
fprintf('[INFO] %d events selected.\n', nEvt);
if nEvt == 0, fprintf('[INFO] Nothing to plot.\n'); return; end

%% ---- Window geometry ----
HW_us  = halfWidthMs * 1000;
nSamp  = round(2 * HW_us * sfx / 1e6) + 1;
tRelMs = linspace(-halfWidthMs, halfWidthMs, nSamp);   % relative time (ms)

HWwide_us = wideHalfWidthS * 1e6;
nSampWide = round(2 * HWwide_us * sfx / 1e6) + 1;
% block-mean decimation factor for the wide window display
wideDec   = max(1, floor(nSampWide / wideTargetCols));
fprintf('[INFO] Wide window: %d samples -> decimate x%d for display.\n', nSampWide, wideDec);

%% ---- PASS A: load every +/-50 ms window once, cache, gather scale stats ----
fprintf('[INFO] Pass A: loading %d event windows (%d channels each = %d reads)...\n', ...
    nEvt, nCh, nEvt*nCh);
Ycache  = cell(nEvt,1);
centerS = nan(nEvt,1);     % event-centre time, seconds into recording
onS     = nan(nEvt,1);     % detected onset,  seconds into recording
offS    = nan(nEvt,1);     % detected offset, seconds into recording
perEvtClim  = nan(nEvt,1);
perEvtTrace = nan(nEvt,1);
perEvtCSD   = nan(nEvt,1);

logEveryA   = max(1, round(nEvt/100));   % ~100 progress lines over the pass
emptyTotalA = 0;                         % count of channel windows that came back empty
tA = tic;
for k = 1:nEvt
    e = evtIdx(k);
    anchor_samp  = round(mean(ets(e,:)));
    anchor_ts_us = global_min_T_us + (anchor_samp - 1) / (sfx/1e6);
    t0_us = anchor_ts_us - HW_us;
    t1_us = anchor_ts_us + HW_us;

    Y = zeros(nCh, nSamp, 'single');
    nEmptyCh = 0;
    for ch = 1:nCh
        fn = fullfile(files(ch).folder, files(ch).name);
        Y(ch,:) = loadWindow(fn, t0_us, t1_us, sfx, ADBitVolts, invertPolarity, nSamp);
        if ~any(Y(ch,:)), nEmptyCh = nEmptyCh + 1; end
    end
    emptyTotalA = emptyTotalA + nEmptyCh;
    Ycache{k}  = Y;

    centerS(k)   = (anchor_ts_us - global_min_T_us) / 1e6;
    onS(k)       = (ets(e,1) - 1) / sfx;
    offS(k)      = (ets(e,2) - 1) / sfx;

    v = abs(Y(isfinite(Y)));
    if ~isempty(v)
        perEvtClim(k)  = prctile(v, climPctile);
        perEvtTrace(k) = prctile(v, traceAmpPct);
    end

    % CSD = -2nd spatial derivative across channels; edge rows blank (NaN)
    C = nan(nCh, nSamp, 'single');
    if nCh >= 3
        C(2:end-1,:) = -( Y(3:end,:) - 2*Y(2:end-1,:) + Y(1:end-2,:) );
    end
    vc = abs(C(isfinite(C)));
    if ~isempty(vc), perEvtCSD(k) = prctile(vc, climPctile); end

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

% Global colour limits (shared across all events -> comparable)
climGlobal = max(perEvtClim(isfinite(perEvtClim)));
if isempty(climGlobal) || ~isfinite(climGlobal) || climGlobal<=0, climGlobal = 1; end
climGlobal = (1 + climPadFrac) * climGlobal;

csdClim = max(perEvtCSD(isfinite(perEvtCSD)));
if isempty(csdClim) || ~isfinite(csdClim) || csdClim<=0, csdClim = 1; end
csdClim = (1 + climPadFrac) * csdClim;

traceAmp = max(perEvtTrace(isfinite(perEvtTrace)));
if isempty(traceAmp) || ~isfinite(traceAmp) || traceAmp<=0, traceAmp = 1; end
traceGain = traceHalfRows / traceAmp;   % uV -> row units

fprintf('[INFO] Voltage CLim = +/-%.2f uV | CSD CLim = +/-%.2f a.u. | trace %.2f uV = %.2f rows\n', ...
    climGlobal, csdClim, traceAmp, traceHalfRows);

%% ---- PASS B: render 4-panel figures (V + CSD + spectrogram + wide) ----
fprintf('[INFO] Pass B: rendering %d figures (each loads a +/-%gs wide window)...\n', nEvt, wideHalfWidthS);
tB = tic;
for k = 1:nEvt
    e       = evtIdx(k);
    Y       = Ycache{k};
    active  = logical(ech(e,1:nCh));
    nActive = sum(active);

    anchor_ts_us = global_min_T_us + centerS(k)*1e6;

    % event extent relative to centre
    onRelMs  = (onS(k) - centerS(k)) * 1000;
    offRelMs = (offS(k) - centerS(k)) * 1000;
    onRelS   =  onS(k) - centerS(k);
    offRelS  = offS(k) - centerS(k);

    % CSD for this event (from cached Y)
    C = nan(nCh, nSamp, 'single');
    if nCh >= 3
        C(2:end-1,:) = -( Y(3:end,:) - 2*Y(2:end-1,:) + Y(1:end-2,:) );
    end

    % ---- pick specNumChans channels for the spectrogram stack (see flag at top) ----
    nTake = min(specNumChans, nCh);
    if specFocusHighMag
        % MODE TRUE: highest AVERAGE MAGNITUDE channels (largest mean |voltage|)
        magByCh = mean(abs(double(Y)), 2, 'omitnan');
        [~, ord] = sort(magByCh, 'descend');
        specChans = ord(1:nTake);
    else
        % MODE FALSE: EVEN SPREAD top-to-bottom across the full probe depth
        idx = unique(round(linspace(1, nCh, nTake)));
        if numel(idx) < nTake                 % rounding collisions -> pad with gaps
            missing = setdiff(1:nCh, idx);
            idx = [idx, missing(1:(nTake - numel(idx)))];
        end
        specChans = idx(:);
    end
    specChans = sort(specChans);              % display top->bottom by depth
    nSpec = numel(specChans);

    % ---- per-channel CWT (one small spectrogram per channel) ----
    Pg = cell(nSpec,1); Wv = cell(nSpec,1);
    fGrid = []; fLoData = []; fHiData = [];
    for jj = 1:nSpec
        yj = double(Y(specChans(jj),:));
        yj(~isfinite(yj)) = 0;
        [Cj, Fj] = cwt(yj, sfx, 'FrequencyLimits', [specFMin specFMax]);
        Pj = log10(abs(Cj) + eps);
        if numel(Fj) > 1 && Fj(1) > Fj(end)     % ascending (low freq at bottom)
            Fj = flipud(Fj); Pj = flipud(Pj);
        end
        if isempty(fGrid)                        % uniform log-freq grid (no banding/gap)
            fLoData = min(Fj); fHiData = max(Fj);
            fGrid   = logspace(log10(fLoData), log10(fHiData), 256);
        end
        Pg{jj} = interp1(Fj, Pj, fGrid, 'linear');
        Wv{jj} = yj;
    end

    % shared colour scaling across the grid (comparable rectangles)
    allP = cell2mat(cellfun(@(x) x(:), Pg, 'UniformOutput', false));
    allP = allP(isfinite(allP));
    if isempty(allP), pHi = 0; else, pHi = prctile(allP, specClimUpPct); end
    pLo = pHi - specClimDyn;

    % shared waveform amplitude scaling for the overlays (robust, capped)
    allW = abs(cell2mat(cellfun(@(x) x(:), Wv, 'UniformOutput', false)));
    wRob = prctile(allW(isfinite(allW)), traceAmpPct);
    if isempty(wRob) || ~isfinite(wRob) || wRob <= 0, wRob = 1; end
    wMax = (1 + specWavePadFr) * wRob;
    if wMax > specWaveCapUV, wMax = specWaveCapUV; end

    % ---- load + decimate the wide (+/- wideHalfWidthS s) voltage window ----
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
        Yw_disp = squeeze(mean(Ywd, 2, 'omitnan'));      % nCh x ncol
        tWideS  = linspace(-wideHalfWidthS, wideHalfWidthS, ncol);
    else
        Yw_disp = Yw;
        tWideS  = linspace(-wideHalfWidthS, wideHalfWidthS, nSampWide);
    end

    % Y labels
    L = cell(nCh,1);
    for ch = 1:nCh
        L{ch} = sprintf('CSC%d%s', nums(ch), lif(active(ch),' *',''));
    end

    % ---- figure layout: V (top-left) + CSD (top-mid) + spectrogram (top-right),
    %      wide voltage below spanning all 3 columns ----
    panelPx = max(340, 150 + 11*nCh);
    figH    = min(3600, 2*panelPx + 300);
    f = figure('Color','w','Position',[40 50 2400 figH],'Visible','off');
    tl = tiledlayout(f, 2, 3, 'TileSpacing','compact', 'Padding','compact');

    % ----- Panel 1 (top-left): voltage raster +/-50 ms (with trace overlay) -----
    ax1 = nexttile(tl);
    imagesc(ax1, tRelMs, 1:nCh, Y);
    set(ax1,'YDir','reverse'); colormap(ax1, jet); clim(ax1,[-climGlobal climGlobal]);
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

    % ----- Panel 2 (top-middle): CSD raster +/-50 ms -----
    ax2 = nexttile(tl);
    imagesc(ax2, tRelMs, 1:nCh, C, 'AlphaData', ~isnan(C));
    set(ax2,'YDir','reverse','Color','w'); colormap(ax2, jet); clim(ax2,[-csdClim csdClim]);
    hold(ax2,'on');
    xline(ax2, 0, '--k', 'LineWidth',1.0, 'Alpha',0.7);
    ylim(ax2,[0.5 nCh+0.5]); xlim(ax2,[-halfWidthMs halfWidthMs]);
    set(ax2,'YTick',1:nCh,'YTickLabel',L,'FontSize',7);
    xlabel(ax2,'Relative time (ms)'); ylabel(ax2,'Channel');
    title(ax2,'CSD raster (\pm50 ms)','FontSize',10,'FontWeight','bold');
    cb2 = colorbar(ax2); ylabel(cb2,'CSD (a.u.)');

    % ----- Panel 3 (top-right): grid of specNumChans individual spectrograms -----
    % A nested 3x2 tiledlayout inside the top-right tile: one small CWT rectangle
    % per channel (jet, log-freq, low freq at bottom, shared colour + amplitude
    % scaling), each with that channel's own waveform overlaid (white/black).
    % NOTE: single axis per rectangle (no yyaxis) -- on this headless node OpenGL
    % falls back to painters and an image on the inactive side of a yyaxis does not
    % rasterize through exportgraphics; the waveform is mapped into the freq space.
    t3 = tiledlayout(tl, nSpec, 1, 'TileSpacing','loose', 'Padding','compact');
    t3.Layout.Tile = 3; t3.Layout.TileSpan = [1 1];
    loF = log10(fLoData); hiF = log10(fHiData);
    axG = gobjects(nSpec,1);
    for jj = 1:nSpec
        axj = nexttile(t3); axG(jj) = axj;
        imagesc(axj, tRelMs, fGrid, Pg{jj});
        hold(axj, 'on');
        set(axj, 'YScale','log', 'YDir','normal');
        ylim(axj, [fLoData fHiData]);
        clim(axj, [pLo pHi]);
        colormap(axj, jet);
        % overlay this channel's waveform, clamped to +/-42% of the freq height
        yn   = max(-1, min(1, Wv{jj} / wMax));
        yWov = 10.^((loF+hiF)/2 + yn*0.42*(hiF-loF));
        plot(axj, tRelMs, yWov, 'k-', 'LineWidth', 1.6);
        plot(axj, tRelMs, yWov, 'w-', 'LineWidth', 0.9);
        xlim(axj, [-halfWidthMs halfWidthMs]);
        xline(axj, 0, '--w', 'LineWidth',0.8, 'Alpha',0.7);
        axj.Layer = 'top'; axj.FontSize = 7;
        ylabel(axj, 'Hz', 'FontSize',7);
        % channel label inset (top-left) so it does not eat vertical space
        text(axj, 0.015, 0.86, sprintf('CSC%d', nums(specChans(jj))), ...
             'Units','normalized', 'FontSize',8, 'FontWeight','bold', ...
             'Color','k', 'BackgroundColor','w', 'EdgeColor','k', 'Margin',1);
        if jj < nSpec, axj.XTickLabel = []; else, xlabel(axj,'Relative time (ms)','FontSize',8); end
    end
    cb3 = colorbar(axG(end)); cb3.Layout.Tile = 'east';
    cb3.Label.String = 'Power (dB)';
    title(t3, sprintf('Spectrogram (CWT) \\bullet %d ch [%s]', nSpec, modeTag), ...
        'FontSize',10, 'FontWeight','bold');

    % ----- Panel 4 (full-width, below): wide voltage raster +/- wideHalfWidthS s with traces -----
    ax4 = nexttile(tl, 4, [1 3]);
    imagesc(ax4, tWideS, 1:nCh, Yw_disp);
    set(ax4,'YDir','reverse'); colormap(ax4, jet); clim(ax4,[-climGlobal climGlobal]);
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

    % ----- overall metadata title (escape '_' so TeX renders it literally) -----
    hms = char(duration(0,0,centerS(k),'Format','hh:mm:ss.SSS'));
    animalNameDisp = strrep(animalName, '_', '\_');
    sgtitle(tl, { ...
        sprintf('%s   |   Event %03d   |   %d active channels   |   spectrogram [%s]: %d ch [%s]', ...
            animalNameDisp, e, nActive, modeTag, nSpec, ...
            strjoin(arrayfun(@(c) sprintf('CSC%d', nums(c)), specChans(:).', 'UniformOutput', false), ', ')), ...
        sprintf('t = %.3f s  (%s into recording)   |   Fs %g Hz   |   V CLim \\pm%.1f \\muV   |   CSD CLim \\pm%.1f a.u.', ...
            centerS(k), hms, sfx, climGlobal, csdClim) }, ...
        'FontSize',11,'FontWeight','bold');

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

fprintf('\n[STEP 2-v2 SPEC] Done in %.1f s. Output: %s\n', toc(tB), outDir);
