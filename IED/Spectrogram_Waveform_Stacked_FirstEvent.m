function Spectrogram_Waveform_Stacked_FirstEvent(inputFolder, dataMatPath, varargin)
% Spectrogram_Waveform_Stacked_FirstEvent (robust tall export, auto-chunk)
% For Solid and Sputter groups:
%   • Detect all events (by PNG "Evt###") but process ONLY THE FIRST of each group
%   • Align by first-channel positive peak within ±anchorHalfWidthMs of event midpoint
%   • Window ±100 ms
%   • Channels [2 12 24 34 44 54 64] by default (clipped to available rows)
%   • Row pair per channel:
%       - Waveform (red) with GLOBAL y-limits (µV)
%       - Spectrogram (power dB, 0..fMaxHz), shared CLim across rows
%   • Exports long PNG(s); auto-splits if too tall.
%
% REQUIRED dataMatPath fields:
%   d [nRows x nSamp], sfx (Hz), kept_channels (optional)

% ---------- Args ----------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

p.addParameter('excelPath', "", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [2 12 24 34 44 54 64], @(v) isnumeric(v) && all(v>=1));
p.addParameter('scaleToMicroV', 1, @(x) isnumeric(x) && all(isfinite(x)) && all(x>0));

p.addParameter('anchorHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);

p.addParameter('specWinMs',   20e-3, @(x)isfinite(x)&&x>0);
p.addParameter('specOverlap', 0.50,  @(x)isfinite(x)&&x>=0&&x<1);
p.addParameter('nfft',        [],    @(x) isempty(x) || (isscalar(x)&&x>0));
p.addParameter('fMaxHz',      2000,  @(x)isfinite(x)&&x>0);

p.addParameter('yLimMicroV', [],   @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('yRobustPct', 99.5, @(x) isfinite(x) && x>0 && x<100);
p.addParameter('yPadFrac',   0.12, @(x) isfinite(x) && x>=0 && x<=0.5);

p.addParameter('powerUpperPct', 99.5, @(x)isfinite(x)&&x>0&&x<100);
p.addParameter('powerDynRange', 40,   @(x)isfinite(x)&&x>0);

p.addParameter('maxFigHeightPx', 14000, @(x)isfinite(x)&&x>1000);
p.addParameter('dpi',            220,    @(x)isfinite(x)&&x>=72);

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

yLimMicroV      = p.Results.yLimMicroV;
yRobustPct      = p.Results.yRobustPct;
yPadFrac        = p.Results.yPadFrac;

powerUpperPct   = p.Results.powerUpperPct;
powerDynRange   = p.Results.powerDynRange;

maxFigH         = p.Results.maxFigHeightPx;
dpi             = p.Results.dpi;

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

outRoot = fullfile(inputFolder, "Spectrogram Waveform Stacked Output");
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

% Channels
chSel = chSel(chSel>=1 & chSel<=nRowsAll);
assert(~isempty(chSel), 'No valid channels in data after clipping.');
nCh = numel(chSel);

% Scaling
if numel(scaleToMicroV)==1
    scaleVec = repmat(scaleToMicroV, nRowsAll, 1);
else
    assert(numel(scaleToMicroV) >= nRowsAll, 'scaleToMicroV must be scalar or length >= nRowsAll.');
    scaleVec = scaleToMicroV(:);
end

% ---------- Excel on/off ----------
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

% ---------- Events ----------
evtSOL = parseEvtNumsFromPngs(solidDir);
evtSPU = parseEvtNumsFromPngs(sputterDir);
fprintf('Found %d SOLID, %d SPUTTER (by filenames). Using the FIRST of each if present.\n', numel(evtSOL), numel(evtSPU));

% ---------- Process first found in each group (if any) ----------
if ~isempty(evtSOL)
    renderOne(evtSOL(1), 'SOLID', outSOL);
end
if ~isempty(evtSPU)
    renderOne(evtSPU(1), 'SPUTTER', outSPU);
end

fprintf('Done.\n');

% ======================================================================
%                              NESTED: RENDER
% ======================================================================
    function renderOne(e, tag, outDir)
        % --- Window: ±100 ms ---
        HW = max(1, round(0.100 * sfx));
        tRelMs = (-HW:HW) / sfx * 1e3;   % waveform x-axis
        centerIdx = HW + 1; %#ok<NASU> (kept for clarity)

        % --- Anchor by first channel positive peak within ±anchor window ---
        if e < 1 || e > NrowsXL, warning('%s Evt %d: out of range.', tag, e); return; end
        s0_ev = round(onSamp(e)); s1_ev = round(offSamp(e));
        if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev)
            warning('%s Evt %d: bad on/off.', tag, e); return;
        end
        HWanchor = max(1, round(anchorHWms * sfx));
        ancMid = round((s0_ev + s1_ev)/2);
        s0a = max(1, ancMid - HWanchor);
        s1a = min(nSamp, ancMid + HWanchor);
        refCh = chSel(1);
        y0 = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
        if isempty(y0) || all(~isfinite(y0))
            warning('%s Evt %d: no finite data for anchor.', tag, e); return;
        end
        [~, k_rel] = max(y0);
        anchor = s0a + k_rel - 1;

        s0 = anchor - HW; s1 = anchor + HW;
        if s0 < 1 || s1 > nSamp
            warning('%s Evt %d: window out of bounds.', tag, e); return;
        end

        % --- Collect waveforms to compute GLOBAL y-limits ---
        rob = 0;
        for ci = 1:nCh
            ch = chSel(ci);
            sc = scaleVec(ch);
            y  = double(mf.d(ch, s0:s1)) * sc;
            yy = y(isfinite(y));
            if isempty(yy), continue; end
            pval = prctile(abs(yy), yRobustPct);
            if isfinite(pval) && pval > rob, rob = pval; end
        end
        if isempty(yLimMicroV)
            yMax = (1 + yPadFrac) * max(1, rob);
        else
            yMax = yLimMicroV;
        end
        yL_global = [-yMax, +yMax];

        % --- Spectrogram params ---
        specWinSamp     = max(8, round(specWinMs * sfx));
        specOverlapSamp = max(0, min(specWinSamp-1, round(specOverlap * specWinSamp)));
        if isempty(nfftOpt)
            nfft = max(32, 2^nextpow2(specWinSamp));
        else
            nfft = nfftOpt;
        end
        fMax = min(fMaxHz, sfx/2);

        % --- Precompute CLim for spectrograms across all channels ---
        allP = [];
        Pane = cell(nCh,1);
        for ci = 1:nCh                      % *** FIXED: colon, not semicolon ***
            ch = chSel(ci);
            sc = scaleVec(ch);
            y  = double(mf.d(ch, s0:s1)) * sc;
            y(~isfinite(y)) = 0;
            [S,F,T] = spectrogram(y, specWinSamp, specOverlapSamp, nfft, sfx);
            P = 10*log10(abs(S).^2 + eps);
            msk = (F>=0) & (F<=fMax);
            F2 = F(msk); P2 = P(msk,:);
            Tms = (T - (HW / sfx)) * 1e3;   % center at 0 ms
            Pane{ci} = struct('y',y, 'Tms',Tms, 'F',F2, 'P',P2);
            allP = [allP; P2(:)]; %#ok<AGROW>
        end
        allP = allP(isfinite(allP));
        if isempty(allP), pHi = 0; else, pHi = prctile(allP, powerUpperPct); end
        pLo = pHi - powerDynRange;

        % --- Layout size / chunking ---
        rowsPerChan = 2;   % (waveform + spectrogram)
        rowsTotal   = rowsPerChan * nCh;

        perRowPx   = 110;          % height per row (pixels)
        figW       = 980;          % fixed width (pixels)
        basePx     = 220;          % title/colorbar margin
        figH_full  = basePx + perRowPx*rowsTotal;

        % If too tall, chunk by channels
        if figH_full <= maxFigH
            chunks = {1:nCh};
        else
            chansPerChunk = max(1, floor( (maxFigH - basePx) / (perRowPx*rowsPerChan) ));
            idx = 1:nCh;
            chunks = {};
            while ~isempty(idx)
                take = min(chansPerChunk, numel(idx));
                chunks{end+1} = idx(1:take); %#ok<AGROW>
                idx = idx(take+1:end);
            end
        end

        if ~exist(outDir,'dir'), mkdir(outDir); end
        baseName = sprintf('Evt%03d_SpecWave_Stacked', e);

        for cidx = 1:numel(chunks)
            subCh = chunks{cidx};
            nSub  = numel(subCh);
            rows  = rowsPerChan * nSub;

            figH = basePx + perRowPx*rows;
            figH = min(figH, maxFigH);

            f = figure('Color','w','Visible','off','Units','pixels','Position',[60 60 figW figH], ...
                       'Renderer','opengl');  % bitmap-friendly

            tl = tiledlayout(f, rows, 1, 'Padding','compact','TileSpacing','compact');

            % Titles/labels
            if ~isempty(kept_channels)
                chanLabels = arrayfun(@(kk) sprintf('row %d (CSC%d)', chSel(kk), kept_channels(chSel(kk))), 1:nCh, 'UniformOutput', false);
            else
                chanLabels = arrayfun(@(kk) sprintf('row %d', chSel(kk)), 1:nCh, 'UniformOutput', false);
            end

            % Render rows for this chunk
            for jj = 1:nSub
                ci = subCh(jj);
                D  = Pane{ci};

                % Waveform (red)
                ax1 = nexttile(tl);
                hold(ax1,'on'); box(ax1,'on'); grid(ax1,'on');
                plot(ax1, tRelMs, D.y, 'Color',[0.85 0.10 0.10], 'LineWidth',1.5);
                xline(ax1,0,'--k','LineWidth',0.9);
                yline(ax1,0,':','Color',[0.7 0.7 0.7]);
                ylim(ax1, yL_global);
                ax1.TickDir = 'out'; ax1.FontSize = 8;
                if jj < nSub, ax1.XTickLabel = []; else, xlabel(ax1,'Time (ms)'); end
                ylabel(ax1, '\muV');
                title(ax1, sprintf('%s — waveform', chanLabels{ci}), 'FontSize',9, 'FontWeight','normal');

                % Spectrogram
                ax2 = nexttile(tl);
                imagesc(ax2, D.Tms, D.F, D.P);
                axis(ax2,'xy');
                colormap(ax2, parula);
                caxis(ax2, [pLo pHi]);
                xline(ax2,0,'--k','LineWidth',0.9,'Color',[0 0 0 0.6]);
                ax2.TickDir = 'out'; ax2.FontSize = 8;
                if jj < nSub, ax2.XTickLabel = []; else, xlabel(ax2,'Time (ms)'); end
                if jj==1
                    ylabel(ax2, 'Hz');
                else
                    ax2.YTickLabel = [];
                end
                ylim(ax2, [0 fMax]);
                title(ax2, sprintf('%s — spectrogram (0..%.0f Hz)', chanLabels{ci}, fMax), 'FontSize',9, 'FontWeight','normal');
            end

            % Single colorbar (attach to figure)
            cb = colorbar('eastoutside');
            cb.Label.String = sprintf('Power (dB) | CLim [%.1f, %.1f]', pLo, pHi);

            sg = sprintf('%s | %s | anchor: first-ch max (\\pm%.1f ms) | Window: \\pm100 ms | STFT win=%.1f ms ov=%.0f%% nfft=%d | chans=%s', ...
                         tag, baseName, 1e3*HWanchor/sfx, 1e3*specWinSamp/sfx, 100*specOverlapSamp/specWinSamp, nfft, mat2str(chSel(subCh)));
            sgtitle(tl, sg, 'FontSize',10, 'FontWeight','bold');

            % Export
            set(f,'PaperPositionMode','auto');
            if numel(chunks) == 1
                outPng = fullfile(outDir, baseName + ".png");
            else
                outPng = fullfile(outDir, sprintf('%s_part%02d.png', baseName, cidx));
            end
            exportgraphics(f, outPng, 'Resolution', dpi, 'BackgroundColor','white', 'ContentType','image');
            close(f);
            fprintf('Saved %s: %s\n', tag, outPng);
        end
    end

end

% ======================================================================
%                              HELPERS
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
%