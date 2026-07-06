%%2_1_visualize.m  Step 2 (v2): voltage raster + CSD raster + wide context
%
% Variant of 2_visualize.m. For each detected event it renders a 2x2 layout:
%   top-left   Voltage raster, +/-50 ms  (channels x time, colour = uV) with the
%              per-channel oscillation traces superimposed -- the event detail.
%   top-right  CSD raster, +/-50 ms      current-source density = -d2V/dchannel^2,
%              blank (NaN) first/last rows, jet colormap, robust CLim -- matches
%              the look/feel of CSDRaster_Avg_Pipeline.
%   bottom     Voltage raster, +/-5 s    full-width context window (loaded on
%   (spans     demand, block-mean decimated for display) WITH per-channel traces
%   both cols) overlaid, so each event can be seen in the surrounding recording.
%
% Putting voltage and CSD side-by-side (instead of stacked) gives every panel
% more room. All x-axes are RELATIVE time (ms for the two top panels, s for the
% wide bottom one). The old secondary top axis (which collided with the title)
% is gone; the metadata block lives in an sgtitle above the layout so nothing
% overlaps.
%
% Called via eval(fileread(...)) from 2_1_visualize.sbat.
% Required workspace variables (set by sbat before eval):
%   dataDir       - same animal folder used in Step 1 (contains ets/ech/detector_meta)
%   Old variable -> fiftyNineBad  - logical true/false
%   New variable to determine bad channels is badChannels
%   badChannels - array of channels to skip for analysis
%
% Reads the band-pass+notch detections from 1_1_ied_detect.m
% (ets/ech_hp_1_lp_300_nf.mat).
%
% One PNG per event is saved to:
%   <Take2>/Output2/Visualized_spikes_hp_1_lp_300_nf_CSD_zoomout/<animalName>/
% 
% Old code for fiftyNineBad
% if ~exist('fiftyNineBad','var') || isempty(fiftyNineBad)
%     fiftyNineBad = true;
% end

badChannels = [8,41,59];

if ~exist('badChannels','var') || isempty(badChannels)
    badChannels = 59;
end


%% ---- Parameters ----
halfWidthMs    = 50;     % ms either side of event centre (panels 1 & 2) & decides ets range
wideHalfWidthS = 5;      % s  either side of event centre (panel 3, context)
minCh          = 1;      % include events with >= this many active channels
maxCh          = 64;     % include events with <= this many active channels
invertPolarity = true;   % match the polarity flip applied in Step 1
loadMaxCh      = 64;     % ignore CSC numbers above this
wideTargetCols = 3000;   % decimate the wide window down to ~this many columns

climPctile     = 99.5;   % robust percentile for the global colour limit
climPadFrac    = 0.12;   % fractional headroom added to the colour limit
traceAmpPct    = 99;     % robust percentile used to scale overlaid traces
traceHalfRows  = 0.45;   % a "traceAmpPct" deflection fills +/- this many rows

%% ---- Output folder ----
dataDir = 'D:/Visualize_biting_testing/m22s3jul15/2024-07-15_16-12-27/';
scriptDir = fileparts(mfilename('fullpath'));
if isempty(scriptDir)
    scriptDir = '/users/s/a/sakhava1/scratch/KCNT1 Urethane/Take 2';
end
[~, animalName] = fileparts(char(dataDir));
halfWidthMsChar = num2str(halfWidthMs);
outDirFolder = append('Visualized_spikes_hp_1_lp_300_nf_CSD_zoomout_',halfWidthMsChar,'ms');
outDir = fullfile(scriptDir, 'Output2', outDirFolder, animalName);
if ~exist(outDir,'dir'), mkdir(outDir); end

fprintf('\n[STEP 2-CSD] %s\n', dataDir);
fprintf('[INFO] Output: %s\n', outDir);

%% ---- Locate and filter CSC files ----
files = dir(fullfile(dataDir,'**','CSC*.n*'));
if isempty(files), error('No CSC files in: %s', dataDir); end

% Add channelNumber field to each struct entry
for i = 1:numel(files)
    tok = regexp(files(i).name, 'CSC(\d+)', 'tokens', 'once');
    if ~isempty(tok)
        files(i).channelNumber = str2double(tok{1});
    else
        files(i).channelNumber = NaN;
    end
end

% Sort struct ascending by channelNumber
[~, ord] = sort([files.channelNumber]);
files = files(ord);

% Filter: valid channel numbers, within loadMaxCh, excluding bad channels
keep = ~isnan([files.channelNumber]) & ([files.channelNumber] <= loadMaxCh);
for ch = badChannels
    keep = keep & ([files.channelNumber] ~= ch);
end
% Remove duplicates, keeping first occurrence of each channel number
[~, ia] = unique([files(keep).channelNumber]);
tmpIdx = find(keep);
keep(:) = false;
keep(tmpIdx(ia)) = true;

files = files(keep);
nums  = [files.channelNumber];
nCh   = numel(files);
fprintf('[INFO] %d channels.\n', nCh);

%% ---- Read sfx and global_min_T_us from CSC headers ----
hdr0 = Nlx2MatCSC(fullfile(files(1).folder, files(1).name), [0 0 0 0 0], 1, 1, []);
sfx  = parseNcsField(hdr0, 'SamplingFrequency');
if ~isfinite(sfx) || sfx <= 0
    sfx = 30000;
    fprintf('[WARN] SamplingFrequency not in header, defaulting to %g Hz\n', sfx);
end
fprintf('[INFO] Fs=%g Hz\n', sfx);

all_first_T_us = nan(1, nCh);
for k = 1:nCh
    fn = fullfile(files(k).folder, files(k).name);
    [ts_us] = Nlx2MatCSC(fn, [1 0 0 0 0], 0, 1, []);
    if ~isempty(ts_us), all_first_T_us(k) = ts_us(1); end
end
global_min_T_us = min(all_first_T_us);
fprintf('[INFO] global_min_T=%g us\n', global_min_T_us);

%% ---- Load detection results ----
tmp = load(fullfile(dataDir,'ets_hp_1_lp_300_nf.mat'), 'Combined_DS_timestamps_sec');
ets = tmp.Combined_DS_timestamps_sec;
% ech adapted to fit Toothy script, which uses only one channel to detect
% every dentate spike. Rather than removing ech, it was deemed easier to
% just make the final row be true
ech = false(size(ets,2), nCh);
ech(:,end) = true;
ets = round(sfx * [ets(:) - (halfWidthMs/1000), ets(:) + (halfWidthMs/1000)]);
fprintf('[INFO] %d events  Fs=%g Hz\n', size(ets,1), sfx);

%% ---- Read header once for ADBitVolts ----
hdr        = Nlx2MatCSC(fullfile(files(1).folder,files(1).name),[0 0 0 0 0],1,1,[]);
ADBitVolts = parseNcsField(hdr,'ADBitVolts');
if isnan(ADBitVolts), error('ADBitVolts not found in header.'); end
fprintf('[INFO] ADBitVolts=%.6g\n', ADBitVolts);

%% ---- Select events ----
chCount = sum(ech(:,1:nCh), 2);
evtIdx  = find(chCount >= minCh & chCount <= maxCh);
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

% Channels used for CSD: first 4, then every other
csdChIdx = [1:4, 5:2:nCh];
nCsdCh   = numel(csdChIdx);

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
    Ysub = Y(csdChIdx, :);
    C = nan(nCsdCh, nSamp, 'single');
    if nCsdCh >= 3
        C(2:end-1,:) = -( Ysub(3:end,:) - 2*Ysub(2:end-1,:) + Ysub(1:end-2,:) );
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

%% ---- Shared Y-axis labels (CSC number, '*' = active in this event) ----
% built per event inside the loop because the '*' depends on the event

%% ---- PASS B: render 3-panel figures ----
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

    % CSD for this event (from cached Y), using first 4 channels then every other
    Ysub = Y(csdChIdx, :);
    C = nan(nCsdCh, nSamp, 'single');
    if nCsdCh >= 3
        C(2:end-1,:) = -( Ysub(3:end,:) - 2*Ysub(2:end-1,:) + Ysub(1:end-2,:) );
    end

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

    % ---- figure layout: voltage (top-left) + CSD (top-right), wide voltage below ----
    panelPx = max(340, 150 + 11*nCh);
    figH    = min(3200, 2*panelPx + 300);
    f = figure('Color','w','Position',[40 50 1800 figH],'Visible','off');
    tl = tiledlayout(f, 2, 2, 'TileSpacing','compact', 'Padding','compact');

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

    % ----- Panel 2 (top-right): CSD raster +/-50 ms -----
    ax2 = nexttile(tl);
    imagesc(ax2, tRelMs, 1:nCsdCh, C, 'AlphaData', ~isnan(C));
    set(ax2,'YDir','reverse','Color','w'); colormap(ax2, jet); clim(ax2,[-csdClim csdClim]);
    hold(ax2,'on');
    xline(ax2, 0, '--k', 'LineWidth',1.0, 'Alpha',0.7);
    ylim(ax2,[0.5 nCsdCh+0.5]); xlim(ax2,[-halfWidthMs halfWidthMs]);
    set(ax2,'YTick',1:nCsdCh,'YTickLabel',L(csdChIdx),'FontSize',7);
    xlabel(ax2,'Relative time (ms)'); ylabel(ax2,'Channel');
    title(ax2,'CSD raster (\pm50 ms)','FontSize',10,'FontWeight','bold');
    cb2 = colorbar(ax2); ylabel(cb2,'CSD (a.u.)');

    % ----- Panel 3 (full-width, below): wide voltage raster +/- wideHalfWidthS s with traces -----
    ax3 = nexttile(tl, [1 2]);
    imagesc(ax3, tWideS, 1:nCh, Yw_disp);
    set(ax3,'YDir','reverse'); colormap(ax3, jet); clim(ax3,[-climGlobal climGlobal]);
    hold(ax3,'on');
    xregion(ax3, onRelS, offRelS, 'FaceColor',[0 0 0], 'FaceAlpha',0.10);
    xline(ax3, 0, '--k', 'LineWidth',1.0, 'Alpha',0.7);
    for ch = 1:nCh
        yrow = double(ch) - traceGain * double(Yw_disp(ch,:));
        if active(ch)
            plot(ax3, tWideS, yrow, 'Color',[0.85 0 0], 'LineWidth',0.6);
        else
            plot(ax3, tWideS, yrow, 'Color',[0 0 0 0.40], 'LineWidth',0.3);
        end
    end
    ylim(ax3,[0.5 nCh+0.5]); xlim(ax3,[-wideHalfWidthS wideHalfWidthS]);
    set(ax3,'YTick',1:nCh,'YTickLabel',L,'FontSize',7);
    xlabel(ax3,'Relative time (s)'); ylabel(ax3,'Channel');
    title(ax3, sprintf('Voltage raster (\\pm%g s context, with traces)', wideHalfWidthS), ...
        'FontSize',10,'FontWeight','bold');
    cb3 = colorbar(ax3); ylabel(cb3,'\muV');

    % ----- overall metadata title (escape '_' so TeX renders it literally) -----
    hms = char(duration(0,0,centerS(k),'Format','hh:mm:ss.SSS'));
    animalNameDisp = strrep(animalName, '_', '\_');
    sgtitle(tl, { ...
        sprintf('%s   |   Event %03d   |   %d active channels', animalNameDisp, e, nActive), ...
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

fprintf('\n[STEP 2-CSD] Done in %.1f s. Output: %s\n', toc(tB), outDir);

function val = parseNcsField(hdr, fieldName)
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
