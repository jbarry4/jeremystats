function SpectroRaster_Events(inputFolder, dataMatPath, varargin)
% SpectroRaster_Events
% For each EVENT, produce a figure with one ROW PER CHANNEL:
%   - Left tile: waveform (µV) in a ±10 ms display window around the anchor
%   - Right tile: spectrogram (dB): x=time (ms), y=frequency (Hz), color=power
%
% Output PNGs:
%   <inputFolder> / "Spectral Raster Output" / Solid   / Spectro_Evt%03d.png
%   <inputFolder> / "Spectral Raster Output" / Sputter / Spectro_Evt%03d.png
%
% Event membership (Solid/Sputter) is inferred by scanning PNGs already
% present in <inputFolder>/Solid and /Sputter with pattern 'Evt(\d+)'.
%
% Spectrogram params are the SAME as in JeremyEEG4:
%   window = round(SF), overlap = round(SF/2), freqs = 0.1:0.2:200 Hz
% We compute the spectrogram on a larger CONTEXT (±1 s by default) so the
% 1 s window is valid, then DISPLAY only ±10 ms on the time axis.
%
% INPUTS
%   inputFolder, dataMatPath : like VoltageRaster_Events
%
% NAME-VALUE OPTIONS
%   'excelPath'              : path to Excel (auto-detected if omitted)
%   'channelIndices'         : rows (channels) to include; default = all
%   'scaleToMicroV'          : scalar or per-row vector to scale raw -> µV (default 1)
%   'anchorMode'             : 'firstChMax' (default) or 'midpoint'
%   'anchorHalfWidthMs'      : ±5 ms (for anchor search when firstChMax)
%   'winHalfWidthMs'         : DISPLAY half window (default 10e-3 → ±10 ms)
%   'specContextHalfWidthSec': ±1.0 s CONTEXT (for spectrogram computation)
%   'fmaxHz'                 : show up to this Hz in the spectrogram (default 100)
%   'climDb'                 : fixed dB color range [lo hi]; else auto robust
%   'dbLowPct'               : low percentile for auto CLim (default 5)
%   'dbHighPct'              : high percentile for auto CLim (default 99.5)
%   'climPadFrac'            : fractional headroom (default 0.12)
%   'maxEventsPerGroup'      : cap #events per group for output (optional)
%
% OUTPUT
%   One PNG per event per group with consistent global dB CLim.

% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));

p.addParameter('anchorMode','firstChMax', @(s) any(strcmpi(s,{'firstChMax','midpoint'})));
p.addParameter('anchorHalfWidthMs', 5e-3,  @(x)isfinite(x)&&x>0);

p.addParameter('winHalfWidthMs', 10e-3,     @(x)isfinite(x)&&x>0);   % DISPLAY ±10 ms
p.addParameter('specContextHalfWidthSec', 1.0, @(x)isfinite(x)&&x>0);% CONTEXT ±1 s

p.addParameter('fmaxHz', 100, @(x)isfinite(x)&&x>0);                 % show to 100 Hz

p.addParameter('climDb', [], @(v) isempty(v) || (isnumeric(v) && numel(v)==2 && v(1)<v(2)));
p.addParameter('dbLowPct', 5, @(x)isfinite(x) && x>=0 && x<100);
p.addParameter('dbHighPct', 99.5, @(x)isfinite(x) && x>0 && x<=100);
p.addParameter('climPadFrac', 0.12, @(x) isfinite(x) && x>=0 && x<=0.5);

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
ctxHalfSec    = p.Results.specContextHalfWidthSec;
fmaxHz        = p.Results.fmaxHz;

climDbOpt     = p.Results.climDb;
pctLow        = p.Results.dbLowPct;
pctHigh       = p.Results.dbHighPct;
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
HWdisp    = max(1, round(winHalfMs   * sfx));    % ± display window (±10 ms)
HWanchor  = max(1, round(anchorHWms  * sfx));    % ± anchor search (5 ms)
HWctx     = max(1, round(ctxHalfSec  * sfx));    % ± spectro context (±1 s)
tRelMs    = (-HWdisp:HWdisp) / sfx * 1e3;        % display x-axis (ms)
winN      = numel(tRelMs);

fprintf('SpectroRaster_Events: sfx=%.1f Hz | display ±%.1f ms | spectro context ±%.1f s | anchor=%s (±%.1f ms)\n', ...
    sfx, 1e3*HWdisp/sfx, HWctx/sfx, anchorMode, 1e3*HWanchor/sfx);

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

% clamp
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

% ---------------- Global dB CLim across ALL events (Solid + Sputter) ----
if isempty(climDbOpt)
    fprintf('Scanning events to compute global dB CLim (percentiles %.2f–%.2f%%)...\n', pctLow, pctHigh);
    [loSOL, hiSOL] = scanDbPercentiles(evtSOL);
    [loSPU, hiSPU] = scanDbPercentiles(evtSPU);
    loVals = [loSOL; loSPU]; loVals = loVals(isfinite(loVals));
    hiVals = [hiSOL; hiSPU]; hiVals = hiVals(isfinite(hiVals));
    if isempty(loVals) || isempty(hiVals)
        climDb = [-120, -20]; % fallback
    else
        lo = min(loVals); hi = max(hiVals);
        mid = (lo+hi)/2; half = (hi-lo)/2;
        lo = mid - (1+climPadFrac)*half;
        hi = mid + (1+climPadFrac)*half;
        climDb = [lo, hi];
    end
else
    climDb = climDbOpt(:).';
end
fprintf('Global dB CLim: [%.1f, %.1f] dB\n', climDb(1), climDb(2));

% ---------------- Render groups with GLOBAL CLim ----------------
renderGroup(evtSOL, outSOL, 'SOLID', climDb);
renderGroup(evtSPU, outSPU, 'SPUTTER', climDb);

fprintf('Done. Output in: %s\n', outRoot);

% ======================================================================
%                                HELPERS
% ======================================================================

function [pLowVec, pHighVec] = scanDbPercentiles(evtList)
    % For each event, build dB values across channels (within f<=fmaxHz) over ±1 s context,
    % then take percentiles; return vectors of low/high percentiles (one per event).
    pLowVec  = nan(numel(evtList),1);
    pHighVec = nan(numel(evtList),1);
    for ii = 1:numel(evtList)
        e = evtList(ii);
        rowXL = e;
        if rowXL < 1 || rowXL > NrowsXL, continue; end

        s0_ev = round(onSamp(rowXL));
        s1_ev = round(offSamp(rowXL));
        if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev), continue; end

        % ---- Anchor ----
        switch anchorMode
            case "midpoint"
                anchor = round((s0_ev + s1_ev)/2);
            otherwise
                ancMid  = round((s0_ev + s1_ev)/2);
                s0a     = max(1, ancMid - HWanchor);
                s1a     = min(nSamp, ancMid + HWanchor);
                refCh   = chList(1);
                yseg0   = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
                if isempty(yseg0) || all(~isfinite(yseg0)), continue; end
                [~, k_rel] = max(yseg0);
                anchor = s0a + k_rel - 1;
        end

        % ---- Spectrogram context window (±1 s by default) ----
        s0_ctx = max(1, anchor - HWctx);
        s1_ctx = min(nSamp, anchor + HWctx);
        if s1_ctx - s0_ctx + 1 < round(sfx)  % need >= 1 s window
            continue;
        end

        % Accumulate dB values across channels for this event (up to fmaxHz)
        dBall = [];
        for k = 1:nCh
            ch = chList(k);
            sc = scaleVec(ch);
            y  = double(mf.d(ch, s0_ctx:s1_ctx)) * sc;
            if isempty(y) || all(~isfinite(y)), continue; end
            win = round(sfx);
            ov  = round(sfx/2);
            fvec = 0.1:0.2:200;
            [S, f, ~] = spectrogram(y, win, ov, fvec, sfx);
            dB = 10*log10(abs(S).^2);
            maskF = (f <= fmaxHz);
            dBall = [dBall; dB(maskF,:)']; %#ok<AGROW>
        end
        if ~isempty(dBall)
            v = dBall(isfinite(dBall));
            if ~isempty(v)
                pLowVec(ii)  = prctile(v, pctLow);
                pHighVec(ii) = prctile(v, pctHigh);
            end
        end
    end
end

function renderGroup(evtList, outDir, tag, climDb_)
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
                [~, k_rel] = max(yseg0); % positive peak
                anchor = s0a + k_rel - 1;
        end

        % ---- Windows ----
        s0_disp = anchor - HWdisp;
        s1_disp = anchor + HWdisp;
        if s0_disp < 1 || s1_disp > nSamp
            fprintf('%s evt %d: display window out of bounds. Skipping.\n', tag, e);
            continue;
        end
        s0_ctx = max(1, anchor - HWctx);
        s1_ctx = min(nSamp, anchor + HWctx);
        if s1_ctx - s0_ctx + 1 < round(sfx)
            fprintf('%s evt %d: context < 1 s; skipping.\n', tag, e);
            continue;
        end

        % ---- Figure ----
        % Two tiles per channel (waveform + spectrogram), generously tall
        perPairPx = 220; basePx = 260; maxPx = 9000;
        figH = min(maxPx, basePx + perPairPx * nCh);
        f = figure('Color','w','Position',[60 60 1200 figH],'Visible','off');
        tl = tiledlayout(f, nCh, 2, 'Padding','compact','TileSpacing','compact');

        for k = 1:nCh
            ch = chList(k);
            sc = scaleVec(ch);

            % Waveform segment for display
            yplot = double(mf.d(ch, s0_disp:s1_disp)) * sc;

            % Spectrogram on context (Jeremy params)
            yctx  = double(mf.d(ch, s0_ctx:s1_ctx)) * sc;
            win  = round(sfx);
            ov   = round(sfx/2);
            fvec = 0.1:0.2:200;
            [S, fHz, tSecCtx] = spectrogram(yctx, win, ov, fvec, sfx);  % tSecCtx in seconds from start of yctx
            dBfull = 10*log10(abs(S).^2);

            % Convert spectrogram times to ms relative to the anchor (no rounding to samples)
            % Absolute time (sec) of each spectrogram column in original recording:
            tAbs_sec = (s0_ctx - 1)/sfx + tSecCtx;
            % Relative to anchor (sec):
            tRel_sec = tAbs_sec - (anchor - 1)/sfx;
            tCtx_ms  = 1e3 * tRel_sec;  % ms rel anchor

            % Restrict to DISPLAY time window ±10 ms and fmax
            maskT = (tCtx_ms >= -10) & (tCtx_ms <= +10);
            maskF = fHz <= fmaxHz;
            dBcut = dBfull(maskF, maskT);
            tcut  = tCtx_ms(maskT);
            fcut  = fHz(maskF);

            % --- Waveform tile ---
            ax1 = nexttile(tl, (k-1)*2 + 1); hold(ax1,'on'); box(ax1,'on'); grid(ax1,'on');
            if ~isempty(yplot), plot(ax1, tRelMs, yplot, 'LineWidth', 1.6); end
            xline(ax1, 0,'--k','LineWidth',0.9); yline(ax1, 0,':','Color',[0.7 0.7 0.7]);
            xlim(ax1, [-10 10]); xticks(ax1, -10:5:10);
            ax1.FontSize = 10;
            if k < nCh, ax1.XTickLabel = []; else, xlabel(ax1,'Time (ms)'); end
            ylabel(ax1,'\muV');

            % Title
            if ~isempty(kept_channels)
                chName = sprintf('row %d (CSC%d)', ch, kept_channels(ch));
            else
                chName = sprintf('row %d', ch);
            end
            title(ax1, sprintf('%s  |  Waveform', chName), 'FontSize',10, 'FontWeight','normal');

            % --- Spectrogram tile ---
            ax2 = nexttile(tl, (k-1)*2 + 2);
            if isempty(dBcut) || isempty(tcut) || isempty(fcut)
                imagesc(ax2, [-10 10], [0 fmaxHz], nan(2));
            else
                imagesc(ax2, tcut, fcut, dBcut);
            end
            set(ax2,'YDir','normal'); colormap(ax2, jet); colorbar(ax2);
            caxis(ax2, climDb_); xlim(ax2, [-10 10]); xticks(ax2, -10:5:10);
            xlabel(ax2,'Time (ms)'); ylabel(ax2,'Frequency (Hz)');
            title(ax2, 'Spectrogram (dB)', 'FontSize',10, 'FontWeight','normal');
            ax2.FontSize = 10;
            xline(ax2, 0,'--k','LineWidth',0.9,'Color',[0 0 0 0.65]);
        end

        sg = sprintf('%s  |  Evt %d  |  anchor=%s  |  display=\\pm10 ms  |  spectro ctx=\\pm%.1f s  |  channels=%d  |  dB CLim=[%.1f, %.1f]  |  f_{max}=%d Hz', ...
            tag, e, char(anchorMode), HWctx/sfx, nCh, climDb_(1), climDb_(2), fmaxHz);
        sgtitle(tl, sg, 'FontSize',12,'FontWeight','bold');

        % ---- Save ----
        outPng = fullfile(outDir, sprintf('Spectro_Evt%03d.png', e));
        exportgraphics(f, outPng, 'Resolution', 220);
        close(f);
        fprintf('Saved %s spectrogram: %s\n', tag, outPng);
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
