function SpectrogramRaster_Events_Stitched(inputFolder, dataMatPath, varargin)
% SpectrogramRaster_Events_Stitched
% For each event (SOLID/SPUTTER):
%   • Build a stitched spectrogram image: channels stacked vertically with NO gaps
%   • Overlay the channel waveform (µV) in RED on top of its own band
%   • Waveform overlay uses a single GLOBAL voltage scale per event (comparable across channels)
%
% x-axis: time (ms, relative to anchor)
% y-axis: “channel-frequency band index” (tick labels at channel centers)
% color : power (dB)
% red   : time-domain waveform scaled to the band height using a global µV range
%
% OUTPUT:
%   <inputFolder>/Spectral Raster Output (Stitched)/Solid/EvtNNN_STITCH.png
%   <inputFolder>/Spectral Raster Output (Stitched)/Sputter/EvtNNN_STITCH.png
%
% REQUIRED:
%   dataMatPath contains: d [nRows x nSamp], sfx (Hz), kept_channels (optional)
%   inputFolder contains: "Solid" and "Sputter" subfolders with "...Evt###..." PNG names
%                         and an Excel *.xlsx with event [on/off] in samples or seconds

% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

% Excel + channels + scaling
p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));

% Alignment & window
p.addParameter('winHalfWidthMs',    10e-3, @(x)isfinite(x)&&x>0);   % ±10 ms display
p.addParameter('anchorHalfWidthMs',  5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms anchor search

% Spectrogram params
p.addParameter('specWinMs',   0.1e-3, @(x)isfinite(x)&&x>0);        % default 0.1 ms (clamped to ≥8 samples)
p.addParameter('specOverlap', 0.50,   @(x)isfinite(x)&&x>=0&&x<1);
p.addParameter('nfft',        [],     @(x) isempty(x) || (isscalar(x)&&x>0));
p.addParameter('fMaxHz',      2000,   @(x)isfinite(x)&&x>0);        % y-axis cap (≤ Nyquist)

% Rendering / scaling
p.addParameter('nFreqRowsPerChan', 128, @(x)isfinite(x)&&x>=16&&mod(x,1)==0); % vertical pixels per channel
p.addParameter('powerUpperPct', 99.5,  @(x)isfinite(x)&&x>0&&x<100); % robust upper CLim (dB)
p.addParameter('powerDynRange', 40,    @(x)isfinite(x)&&x>0);        % lower CLim = upper - dynRange (dB)

% Waveform overlay scaling (µV)
p.addParameter('waveYLimMicroV', [],   @(x) isempty(x) || (numel(x)==2 && all(isfinite(x)))); % [min max] µV global
p.addParameter('waveRobustPct',  99.5, @(x)isfinite(x)&&x>0&&x<100); % robust |y| percentile → symmetric ±
p.addParameter('wavePadFrac',    0.12, @(x)isfinite(x)&&x>=0&&x<=0.5);

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
fMaxHzReq       = p.Results.fMaxHz;

nFperChan       = p.Results.nFreqRowsPerChan;
powerUpperPct   = p.Results.powerUpperPct;
powerDynRange   = p.Results.powerDynRange;

waveYLimOpt     = p.Results.waveYLimMicroV;
waveRobustPct   = p.Results.waveRobustPct;
wavePadFrac     = p.Results.wavePadFrac;

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

outRoot = fullfile(inputFolder, "Spectral Raster Output (Stitched)");
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
tMs_full = (-HWwin:HWwin) / sfx * 1e3;       % ms for time-domain overlay

% ---------------- Excel on/off (samples) ----------------
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
specWinSamp      = max(8, round(specWinMs * sfx));                      % enforce ≥8 samples
specOverlapSamp  = max(0, min(specWinSamp-1, round(specOverlap * specWinSamp)));
if isempty(nfftOpt)
    nfft = max(32, 2^nextpow2(specWinSamp));
else
    nfft = nfftOpt;
end

% Clamp fMax to Nyquist
fMaxHzReq = min(fMaxHzReq, sfx/2);

fprintf(['STITCH Spectrogram: win=%d samp (%.3f ms) | overlap=%d samp (%.0f%%) | nfft=%d | fMax=%.0f Hz | ' ...
         'display window ±%.1f ms | anchor search ±%.1f ms\n'], ...
        specWinSamp, 1e3*specWinSamp/sfx, specOverlapSamp, 100*specOverlapSamp/specWinSamp, ...
        nfft, fMaxHzReq, 1e3*HWwin/sfx, 1e3*HWanchor/sfx);

% ---------------- Render groups ----------------
renderGroup(evtSOL, outSOL, 'SOLID');
renderGroup(evtSPU, outSPU, 'SPUTTER');
fprintf('Done. Outputs in:\n  %s\n  %s\n', outSOL, outSPU);

% ======================================================================
%                              NESTED: render
% ======================================================================
function renderGroup(evtList, outDir, tag)
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

        % ---- Gather time-domain and spectrograms ----
        Yt_all = zeros(nCh, 2*HWwin+1);
        for k = 1:nCh
            ch = chList(k);
            sc = scaleVec(ch);
            y  = double(mf.d(ch, s0:s1)) * sc;
            y(~isfinite(y)) = 0;
            Yt_all(k,:) = y;
        end

        % Global waveform scaling (µV) for this event
        if isempty(waveYLimOpt)
            vals = abs(Yt_all(:));
            vals = vals(isfinite(vals));
            if isempty(vals), rob = 1; else, rob = prctile(vals, waveRobustPct); end
            vMax = (1 + wavePadFrac) * max(1, rob);
            vMin = -vMax;
        else
            vMin = waveYLimOpt(1); vMax = waveYLimOpt(2);
            if ~(isfinite(vMin) && isfinite(vMax) && vMax>vMin)
                error('waveYLimMicroV must be [min max] with min<max');
            end
        end

        % For spectrograms: compute once per channel, then resample to a common F-grid
        % Also collect power for robust CLim
        allPow = [];
        P_res_list = cell(nCh,1);

        Tms_common = [];           % we’ll enforce a common time vector using first channel’s spectrogram
        Fgrid       = linspace(0, fMaxHzReq, nFperChan);  % common freq grid (0..fMax), nFperChan rows

        for k = 1:nCh
            y = Yt_all(k,:);  % row vector
            [S, F, T] = spectrogram(y, specWinSamp, specOverlapSamp, nfft, sfx);
            P = 10*log10(abs(S).^2 + eps);
            idxF = (F >= 0) & (F <= fMaxHzReq);
            F = F(idxF); P = P(idxF, :);

            % Time axis (ms) centered on anchor: T is seconds from start of y (which is t=-HWwin..+HWwin)
            Tms = (T - (HWwin / sfx)) * 1e3;

            if isempty(Tms_common)
                % fix a common time grid: use this one
                Tms_common = Tms;
            else
                % if length differs slightly, resample spectrogram in time
                if numel(Tms) ~= numel(Tms_common) || any(abs(Tms - Tms_common) > (1e-6))
                    % linear time interpolation for each freq row
                    Ptemp = zeros(size(P,1), numel(Tms_common));
                    for rr = 1:size(P,1)
                        Ptemp(rr,:) = interp1(Tms, P(rr,:), Tms_common, 'linear', 'extrap');
                    end
                    P = Ptemp;
                    Tms = Tms_common; %#ok<NASGU>
                end
            end

            % Resample P(F,:) to common Fgrid
            Pres = zeros(nFperChan, size(P,2));
            for tt = 1:size(P,2)
                Pres(:,tt) = interp1(F, P(:,tt), Fgrid, 'linear', 'extrap');
            end

            P_res_list{k} = Pres;
            allPow = [allPow; Pres(:)]; %#ok<AGROW>
        end

        % Robust power CLim
        allPow = allPow(isfinite(allPow));
        if isempty(allPow), pHi = 0; else, pHi = prctile(allPow, powerUpperPct); end
        pLo = pHi - powerDynRange;

        % Build stitched image: (nCh*nFperChan) x nT
        nT = numel(Tms_common);
        Img = zeros(nCh*nFperChan, nT);
        for k = 1:nCh
            r0 = (k-1)*nFperChan + 1;
            r1 = k*nFperChan;
            Img(r0:r1, :) = P_res_list{k};
        end

        % Map waveform (µV) into each channel band’s vertical span
        % Normalize y using global [vMin vMax], clamp 0..1
        yNorm = (Yt_all - vMin) / max(1e-9, (vMax - vMin));
        yNorm = min(max(yNorm, 0), 1);

        % If time samples (tMs_full) don’t match spectrogram time (Tms_common), resample y to Tms_common
        if numel(tMs_full) ~= nT || any(abs(tMs_full - Tms_common) > 1e-6)
            yRes = zeros(nCh, nT);
            for k = 1:nCh
                yRes(k,:) = interp1(tMs_full, Yt_all(k,:), Tms_common, 'linear', 'extrap');
            end
            yNorm = (yRes - vMin) / max(1e-9, (vMax - vMin));
            yNorm = min(max(yNorm, 0), 1);
        end

        % Convert normalized 0..1 to row indices in each band
        yPlot = zeros(nCh, nT);
        for k = 1:nCh
            bandTop = (k-1)*nFperChan;              % 0-based
            yPlot(k,:) = bandTop + 1 + yNorm(k,:)*(nFperChan-1);
        end

        % -------- Figure: single imagesc + overlay (no gaps) --------
        perRowPx = 5; basePx = 240; maxPx = 5400;
        figH = min(maxPx, basePx + perRowPx * (nCh*nFperChan));
        f = figure('Color','w','Position',[60 60 1150 figH],'Visible','off');

        ax = axes('Parent', f); hold(ax, 'on'); box(ax, 'on');
        imagesc(ax, Tms_common, 1:(nCh*nFperChan), Img);
        axis(ax, 'xy');
        colormap(ax, parula);
        caxis(ax, [pLo pHi]);

        % Overlay waveforms in red
        for k = 1:nCh
            plot(ax, Tms_common, yPlot(k,:), 'r-', 'LineWidth', 1.0);
        end

        % y-ticks at channel centers, labels with channel names; channel 1 at TOP
        set(ax, 'YDir','reverse'); % channel 1 on top
        yCenters = ((0:nCh-1)*nFperChan) + (nFperChan+1)/2;
        if isempty(kept_channels)
            chanLabels = arrayfun(@(kk) sprintf('row %d', chList(kk)), 1:nCh, 'UniformOutput', false);
        else
            chanLabels = arrayfun(@(kk) sprintf('row %d (CSC%d)', chList(kk), kept_channels(chList(kk))), 1:nCh, 'UniformOutput', false);
        end
        set(ax, 'YTick', yCenters, 'YTickLabel', chanLabels, 'FontSize', 9, 'TickDir', 'out', 'TickLength', [0 0]);

        xlabel(ax, 'Time (ms)');
        ylabel(ax, 'Channel (stitched, no gaps)');
        cb = colorbar(ax, 'eastoutside'); cb.Label.String = 'Power (dB)';

        % Title (compact)
        sg = sprintf(['%s | Evt %d | anchor: first-ch max (\\pm%.1f ms) | window: \\pm%.1f ms | ' ...
                      'STFT win=%.3f ms, ov=%.0f%%, nfft=%d, fMax=%.0f Hz | ' ...
                      'wave \\muV global [%.1f, %.1f]'], ...
                      tag, e, 1e3*HWanchor/sfx, 1e3*HWwin/sfx, ...
                      1e3*specWinSamp/sfx, 100*specOverlapSamp/specWinSamp, nfft, fMaxHzReq, vMin, vMax);
        title(ax, sg, 'FontSize', 10, 'FontWeight', 'bold');

        % Save
        if ~exist(outDir,'dir'), mkdir(outDir); end
        outPng = fullfile(outDir, sprintf('Evt%03d_STITCH.png', e));
        exportgraphics(f, outPng, 'Resolution', 220);
        close(f);
        fprintf('Saved stitched spectrogram: %s\n', outPng);
    end
end

end

% ======================================================================
%                             HELPER: event IDs
% ======================================================================
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
