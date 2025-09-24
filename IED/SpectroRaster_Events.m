function SpectralRaster_Events(inputFolder, dataMatPath, varargin)
% SpectralRaster_Events
% Make a per-event stack of channel panels: waveform (top) + spectrogram (bottom).
% Time axis = ms (±10 ms around anchor). Y axis = frequency. Color = power (dB by default).
%
% Output:
%   <inputFolder>/Spectral Raster Output/Solid/SpecRaster_Evt%03d.png
%   <inputFolder>/Spectral Raster Output/Sputter/SpecRaster_Evt%03d.png

% ---------------- Args (mirrors VoltageRaster_Events with a few spec options) -----------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));

p.addParameter('anchorMode','firstChMax', @(s) any(strcmpi(s,{'firstChMax','midpoint'})));
p.addParameter('anchorHalfWidthMs', 5e-3,  @(x)isfinite(x)&&x>0);

% *** Spectral raster uses ±10 ms by default ***
p.addParameter('winHalfWidthMs', 10e-3,     @(x)isfinite(x)&&x>0);

% Spectrogram controls
p.addParameter('fmaxHz',        200,   @(x)isfinite(x)&&x>0);
p.addParameter('fStepHz',       2,     @(x)isfinite(x)&&x>0);
p.addParameter('specWinMs',     2e-3,  @(x)isfinite(x)&&x>0);   % STFT window length
p.addParameter('specOverlap',   0.75,  @(x)isfinite(x)&&x>=0&&x<1);
p.addParameter('powerScale',   'db',   @(s) any(strcmpi(s,{'db','linear'})));

% Color scaling (global across ALL events, both groups)
p.addParameter('climPower', [],         @(x) isempty(x) || isscalar(x)); % if 'db' -> ±dB around 0 not used; use [min max] via percentile
p.addParameter('robustPct',  99.5,      @(x) isfinite(x) && x>0 && x<100);
p.addParameter('climPadFrac', 0.12,     @(x) isfinite(x) && x>=0 && x<=0.5);

p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));

p.parse(inputFolder, dataMatPath, varargin{:});
S = p.Results;

% ---------------- Layout & IO ----------------
inputFolder = string(S.inputFolder);
dataMatPath = string(S.dataMatPath);

solidDir   = fullfile(inputFolder, "Solid");
sputterDir = fullfile(inputFolder, "Sputter");
assert(isfolder(solidDir),   'Missing folder: %s', solidDir);
assert(isfolder(sputterDir), 'Missing folder: %s', sputterDir);

excelPath = string(S.excelPath);
if excelPath == ""
    xl = dir(fullfile(inputFolder, "*.xlsx"));
    assert(~isempty(xl), 'No Excel file (*.xlsx) found in %s', inputFolder);
    excelPath = fullfile(xl(1).folder, xl(1).name);
end
assert(isfile(excelPath), 'Excel not found: %s', excelPath);

outRoot = fullfile(inputFolder, "Spectral Raster Output");
outSOL  = fullfile(outRoot, "Solid");
outSPU  = fullfile(outRoot, "Sputter");
if ~exist(outSOL,'dir'), mkdir(outSOL); end
if ~exist(outSPU,'dir'), mkdir(outSPU); end

% ---------------- Data ----------------
assert(isfile(dataMatPath), 'Data MAT not found: %s', dataMatPath);
mf = matfile(dataMatPath);
try sfx = mf.sfx; catch, error('Missing "sfx" (Hz) in data MAT.'); end
nRowsAll = size(mf,'d',1);
nSamp    = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end %#ok<NASGU>

if isempty(S.channelIndices)
    chList = 1:nRowsAll;
else
    chList = S.channelIndices(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);

% per-row scaling
if numel(S.scaleToMicroV) == 1
    scaleVec = repmat(S.scaleToMicroV, nRowsAll, 1);
else
    assert(numel(S.scaleToMicroV) >= nRowsAll, 'scaleToMicroV must be scalar or >= #rows.');
    scaleVec = S.scaleToMicroV(:);
end

% ---------------- Windows & timebase ----------------
HWwin    = max(1, round(S.winHalfWidthMs * sfx)); % ±10 ms -> window length ~20 ms
HWanchor = max(1, round(S.anchorHalfWidthMs * sfx));
tRelMs   = (-HWwin:HWwin) / sfx * 1e3;
winN     = numel(tRelMs);

fprintf('SpectralRaster_Events: sfx=%.1f Hz | window ±%.1f ms | anchor=%s (±%.1f ms)\n', ...
    sfx, 1e3*HWwin/sfx, string(S.anchorMode), 1e3*HWanchor/sfx);

% ---------------- Read Excel -> on/off samples ----------------
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

% ---------------- Event IDs from existing PNG names ----------------
evtSOL = parseEvtNumsFromPngs(solidDir);
evtSPU = parseEvtNumsFromPngs(sputterDir);
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));
if ~isempty(S.maxEventsPerGroup)
    evtSOL = evtSOL(1:min(end, S.maxEventsPerGroup));
    evtSPU = evtSPU(1:min(end, S.maxEventsPerGroup));
end

% ---------------- Global CLim for power (dB or linear) ----------------
% We compute a robust percentile across ALL events and channels.
if isempty(S.climPower)
    fprintf('Scanning events for global spectral scale (Pctl %.2f%%)...\n', S.robustPct);
    pwrVals = scanSpecPercentiles([evtSOL(:); evtSPU(:)]);
    if isempty(pwrVals) || all(~isfinite(pwrVals))
        climHi = 1; climLo = 0;
    else
        climHi = max(pwrVals(isfinite(pwrVals)));
        if strcmpi(S.powerScale,'db')
            % pwrVals already in dB
            pad  = S.climPadFrac * max(1, abs(climHi));
            climLo = min(-pad, prctile(pwrVals, 100 - S.robustPct)); % allow some negative
            climHi = climHi + pad;
        else
            % linear power
            climLo = 0;
            climHi = climHi * (1 + S.climPadFrac);
        end
    end
else
    if numel(S.climPower)==1
        if strcmpi(S.powerScale,'db')
            climLo = -S.climPower; climHi = +S.climPower;
        else
            climLo = 0;            climHi = S.climPower;
        end
    else
        climLo = S.climPower(1); climHi = S.climPower(2);
    end
end
fprintf('Global spectral CLim = [%.3g, %.3g] (%s).\n', climLo, climHi, upper(S.powerScale));

% ---------------- Render groups ----------------
renderGroup(evtSOL, outSOL, 'SOLID', climLo, climHi);
renderGroup(evtSPU, outSPU, 'SPUTTER', climLo, climHi);

fprintf('Done. Output in: %s\n', outRoot);

% ======================================================================
%                                HELPERS
% ======================================================================

function pvec = scanSpecPercentiles(evtList)
    % For speed, we sample power from a subset of channels (up to 8 evenly spaced)
    if isempty(evtList), pvec = []; return; end
    sampCh = chList(max(1, round(linspace(1, nCh, min(nCh,8)))));
    fVec = 0:S.fStepHz:S.fmaxHz;
    winSamp = max(4, round(S.specWinMs * sfx));
    nover   = min(winSamp-1, round(S.specOverlap * winSamp));
    pvec = nan(numel(evtList),1);
    for ii=1:numel(evtList)
        e = evtList(ii);
        if e<1 || e>NrowsXL, continue; end
        [s0, s1, ok] = getWindowForEvent(e);
        if ~ok, continue; end
        % collect a small random handful of power samples across chans
        P all = [];
        for k=1:numel(sampCh)
            ch = sampCh(k);
            y  = double(mf.d(ch, s0:s1)) * scaleVec(ch);
            if all(~isfinite(y)), continue; end
            [Sxx,~,~] = spectrogram(y, winSamp, nover, fVec, sfx);
            P_lin = abs(Sxx).^2;
            if strcmpi(S.powerScale,'db')
                Pall = [Pall; 10*log10(P_lin(:)+eps)]; %#ok<AGROW>
            else
                Pall = [Pall; P_lin(:)]; %#ok<AGROW>
            end
        end
        if ~isempty(Pall)
            pvec(ii) = prctile(Pall, S.robustPct);
        end
    end
end

function [s0, s1, ok] = getWindowForEvent(e)
    s0_ev = round(onSamp(e)); s1_ev = round(offSamp(e));
    ok = isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev;
    if ~ok, s0=1; s1=0; return; end
    switch lower(string(S.anchorMode))
        case "midpoint"
            anchor = round((s0_ev + s1_ev)/2);
        otherwise % firstChMax
            ancMid = round((s0_ev + s1_ev)/2);
            sa = max(1, ancMid - HWanchor);
            sb = min(nSamp, ancMid + HWanchor);
            refCh = chList(1);
            y0 = double(mf.d(refCh, sa:sb)) * scaleVec(refCh);
            if isempty(y0) || all(~isfinite(y0)), ok=false; s0=1; s1=0; return; end
            [~, krel] = max(y0); anchor = sa + krel - 1;
    end
    s0 = anchor - HWwin; s1 = anchor + HWwin;
    ok = s0>=1 && s1<=nSamp;
end

function renderGroup(evtList, outDir, tag, climLo, climHi)
    if isempty(evtList), warning('%s: no events to render.', tag); return; end
    fVec   = 0:S.fStepHz:S.fmaxHz;
    winSmp = max(4, round(S.specWinMs * sfx));
    nover  = min(winSmp-1, round(S.specOverlap * winSmp));

    for ii=1:numel(evtList)
        e = evtList(ii);
        if e<1 || e>NrowsXL, fprintf('%s evt %d: out of bounds.\n', tag, e); continue; end
        [s0, s1, ok] = getWindowForEvent(e);
        if ~ok, fprintf('%s evt %d: invalid window.\n', tag, e); continue; end

        % ------- Build figure (stack channels; for each: waveform + spectrogram) -------
        perChanPx = 140; % height per channel (2 tiles)
        basePx    = 140;
        figH      = basePx + perChanPx * nCh;
        f = figure('Color','w','Position',[80 80 1100 figH],'Visible','off');
        tl = tiledlayout(2*nCh, 1, 'Padding','compact','TileSpacing','compact');

        for k = 1:nCh
            ch = chList(k);
            sc = scaleVec(ch);
            y  = double(mf.d(ch, s0:s1)) * sc;

            % ---- Waveform (top tile) ----
            ax1 = nexttile(tl);
            plot(tRelMs, y, 'k', 'LineWidth', 1.0);
            grid(ax1,'on');
            ylabel(ax1, sprintf('Ch %d \\muV', ch));
            if ~isempty(kept_channels)
                title(ax1, sprintf('row %d (CSC%d)', ch, kept_channels(ch)), 'FontWeight','bold','FontSize',9);
            else
                title(ax1, sprintf('row %d', ch), 'FontWeight','bold','FontSize',9);
            end
            xlim(ax1, [tRelMs(1) tRelMs(end)]);
            set(ax1,'XTickLabel',[]); % hide x labels; shown on spec

            % ---- Spectrogram (bottom tile) ----
            ax2 = nexttile(tl);
            if any(isfinite(y))
                [Sxx, fHz, tIdx] = spectrogram(y, winSmp, nover, fVec, sfx);
                P_lin = abs(Sxx).^2;
                if strcmpi(S.powerScale,'db')
                    P_show = 10*log10(P_lin + eps);
                else
                    P_show = P_lin;
                end
                % Align spectrogram time to ms relative with same window
                % spectrogram returns times in seconds relative to start of y:
                tSpec_ms = (tIdx + (s0-1)/sfx - (s0-1)/sfx) * 1e3; %#ok<NASGU> % simplification -> starts at ~0 ms within window
                % We just map to local window axis:
                imagesc(tRelMs, fHz, P_show); axis xy
                caxis([climLo, climHi]);
                colormap(ax2, jet); colorbar(ax2);
                ylim(ax2, [0 S.fmaxHz]);
                ylabel(ax2,'Frequency (Hz)');
                xlabel(ax2,'Time (ms)');
            else
                imagesc(tRelMs, fVec, nan(numel(fVec), numel(tRelMs))); axis xy
                ylabel(ax2,'Frequency (Hz)'); xlabel(ax2,'Time (ms)');
            end
        end

        ttl = sprintf('%s | Evt %d | anchor=%s | window=\\pm%.1f ms | chans=%d | Scale [%g,%g] %s', ...
            tag, e, string(S.anchorMode), 1e3*HWwin/sfx, nCh, climLo, climHi, upper(S.powerScale));
        sgtitle(tl, ttl, 'FontSize', 12, 'FontWeight', 'bold');

        % ------- Save -------
        outPng = fullfile(outDir, sprintf('SpecRaster_Evt%03d.png', e));
        exportgraphics(f, outPng, 'Resolution', 220);
        close(f);
        fprintf('Saved %s spectral raster: %s\n', tag, outPng);
    end
end

function evts = parseEvtNumsFromPngs(dirpath)
    L = dir(fullfile(dirpath, '*.png'));
    evts = [];
    for kk = 1:numel(L)
        m = regexp(L(kk).name, 'Evt(\d+)', 'tokens', 'once');
        if ~isempty(m)
            ev = str2double(m{1});
            if isfinite(ev), evts(end+1) = ev; end %#ok<AGROW>
        end
    end
    evts = sort(unique(evts));
end

end
