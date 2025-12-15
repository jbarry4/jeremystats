function out = Scalogram_Waveform_Stacked_ThirdEvent_Pipeline(inputFolder, dataMatPath, varargin)
% Scalogram_Waveform_Stacked_ThirdEvent_Pipeline
% --- CWT (WAVELET) VERSION ---
% - Uses the 3rd event from SOLID and SPUTTER (if present)
% - Defaults to 1st event if 3rd not present.
% - Selects every 4th ROW (spatial density).
% - Maps Row Index -> Real Channel # (CSC) for labels.
% - Overlays Waveform (White with Black Outline) on top of Scalogram.
% - Scalogram: Low Freq (Bottom) -> High Freq (Top).
% - Waveform Axis: Capped at +2000 uV max.
%
% OUTPUT: PNG(s)/PDF(s) under "<inputFolder>/Spectrogram Waveform Stacked Output/{Solid,Sputter}"
%
% Returns struct OUT with fields:
%   pngSolid, pngSputter, pdfSolid, pdfSputter, statsCSV (unused -> "")
% -----------------------------
% ---------- Args ----------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('excelPath', "", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('preferEvenRows', true, @(x)islogical(x)||ismember(x,[0 1]));
% Scaling
p.addParameter('scaleToMicroV', 1, @(x) isnumeric(x) && all(isfinite(x)) && all(x>0));
% Alignment
p.addParameter('anchorHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);
% --- NEW ANCHOR PARAMETERS ---
p.addParameter('anchorMidpoint', false, @(x)islogical(x)||ismember(x,[0 1]));
p.addParameter('anchorChannel', 0, @(x)isscalar(x)&&isnumeric(x)&&x>=0);
p.addParameter('anchorPolarity', 'pos', @(s) any(validatestring(s, {'pos','neg','abs'})));
% --- END NEW PARAMETERS ---
% --- CWT PARAMETERS ---
p.addParameter('fMinHz',      20,   @(x)isfinite(x)&&x>0);   
p.addParameter('fMaxHz',      1000, @(x)isfinite(x)&&x>0);
% --- END CWT PARAMETERS ---
% Global waveform y-scale
p.addParameter('yLimMicroV', [],   @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('yRobustPct', 99.5, @(x) isfinite(x) && x>0 && x<100);
p.addParameter('yPadFrac',   0.12, @(x) isfinite(x) && x>=0 && x<=0.5);
% Scalogram color scaling (log10(magnitude))
p.addParameter('climUpperPct',  99.5, @(x)isfinite(x)&&x>0&&x<100);
p.addParameter('climDynRange',  4,    @(x)isfinite(x)&&x>0); 
% Export controls
p.addParameter('maxFigHeightPx', 16000, @(x)isfinite(x)&&x>1000);
p.addParameter('dpi',            220,   @(x)isfinite(x)&&x>=72);
p.parse(inputFolder, dataMatPath, varargin{:});

inputFolder     = string(p.Results.inputFolder);
dataMatPath     = string(p.Results.dataMatPath);
excelPath       = string(p.Results.excelPath);
chUser          = p.Results.channelIndices;
preferEven      = p.Results.preferEvenRows;
scaleToMicroV   = p.Results.scaleToMicroV;
anchorHWms      = p.Results.anchorHalfWidthMs;
anchorMidpoint  = p.Results.anchorMidpoint;
anchorChannel   = p.Results.anchorChannel;
anchorPolarity  = p.Results.anchorPolarity;
fMinHz          = p.Results.fMinHz;
fMaxHz          = p.Results.fMaxHz;
yLimMicroV      = p.Results.yLimMicroV;
yRobustPct      = p.Results.yRobustPct;
yPadFrac        = p.Results.yPadFrac;
climUpperPct    = p.Results.climUpperPct;
climDynRange    = p.Results.climDynRange;
maxFigH         = p.Results.maxFigHeightPx;
dpi             = p.Results.dpi;

out = struct('pngSolid',"", 'pngSputter',"", 'pdfSolid',"", 'pdfSputter',"", 'statsCSV',"");

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
% --- Load Channel Mapping ---
try kept_channels = mf.kept_channels; catch, kept_channels = []; end 

% Scaling vector
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

% ---------- Events from PNG names ----------
evtSOL = parseEvtNumsFromPngs(solidDir);
evtSPU = parseEvtNumsFromPngs(sputterDir);
fprintf('Found %d SOLID, %d SPUTTER (by filenames). Using the 3rd of each if present.\n', numel(evtSOL), numel(evtSPU));

% ---------- Channel selection (Every 4th Row) ----------
if ~isempty(chUser)
    % If user specified channels manually, use them directly
    chSel = unique(chUser, 'stable');
    chSel = chSel(chSel>=1 & chSel<=nRowsAll);
else
    % Default: Select every 4th ROW from the matrix
    % (e.g. Rows 4, 8, 12, 16...)
    chSel = 4:4:nRowsAll;
end

if isempty(chSel)
    error('No valid channels to select from (check nRowsAll vs 4:4:end).');
end

nCh = numel(chSel);
fprintf('Selected %d matrix rows for Scalogram (Every 4th): %s\n', nCh, mat2str(chSel));

% ---------- Render 3rd event (or 1st) of each group ----------
if numel(evtSOL) >= 3
    fprintf('SOLID: Found %d events, using 3rd event (Evt %d).\n', numel(evtSOL), evtSOL(3));
    [out.pngSolid, out.pdfSolid] = renderOne(evtSOL(3), 'SOLID', outSOL, chSel);
elseif numel(evtSOL) >= 1
    warning('SOLID: Found only %d events (fewer than 3). Defaulting to 1st event (Evt %d).', numel(evtSOL), evtSOL(1));
    [out.pngSolid, out.pdfSolid] = renderOne(evtSOL(1), 'SOLID', outSOL, chSel);
else
    warning('SOLID: No events found — skipping scalogram.');
end

if numel(evtSPU) >= 3
    fprintf('SPUTTER: Found %d events, using 3rd event (Evt %d).\n', numel(evtSPU), evtSPU(3));
    [out.pngSputter, out.pdfSputter] = renderOne(evtSPU(3), 'SPUTTER', outSPU, chSel);
elseif numel(evtSPU) >= 1
    warning('SPUTTER: Found only %d events (fewer than 3). Defaulting to 1st event (Evt %d).', numel(evtSPU), evtSPU(1));
    [out.pngSputter, out.pdfSputter] = renderOne(evtSPU(1), 'SPUTTER', outSPU, chSel);
else
    warning('SPUTTER: No events found — skipping scalogram.');
end

fprintf('Scalogram_Waveform_Stacked_ThirdEvent pipeline done.\n');

% ======================================================================
%                              NESTED: RENDER
% ======================================================================
    function [outPng, outPdf] = renderOne(e, tag, outDir, chSel)
        outPng = "";
        outPdf = "";
        HW = max(1, round(0.100 * sfx));
        tRelMs = (-HW:HW) / sfx * 1e3;
        
        if e < 1 || e > NrowsXL, warning('%s Evt %d: out of range.', tag, e); return; end
        s0_ev = round(onSamp(e)); s1_ev = round(offSamp(e));
        if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev)
            warning('%s Evt %d: bad on/off.', tag, e); return;
        end
        
        HWanchor = max(1, round(anchorHWms * sfx));
        ancMid = round((s0_ev + s1_ev)/2);
        anchorDesc = ""; 
        
        % --- ANCHOR LOGIC ---
        if anchorMidpoint == true
            anchor = ancMid;
            anchorDesc = "Event Midpoint";
        else
            if anchorChannel == 0
                refCh = chSel(end); 
            else
                if anchorChannel < 1 || anchorChannel > nRowsAll || ~any(chSel == anchorChannel)
                    warning('Invalid/unselected anchorChannel %d. Reverting to last selected.', anchorChannel);
                    refCh = chSel(end);
                else
                    refCh = anchorChannel; 
                end
            end
            
            anchorDesc = sprintf("%s peak on row %d (±%.1f ms)", ...
                                 anchorPolarity, refCh, 1e3*anchorHWms);
            
            s0a = max(1, ancMid - HWanchor);
            s1a = min(nSamp, ancMid + HWanchor);
            scRef = scaleVec(refCh);
            y0 = double(mf.d(refCh, s0a:s1a)) * scRef;
            
            if isempty(y0) || all(~isfinite(y0))
                warning('%s Evt %d: no finite data for anchor.', tag, e); return;
            end
            
            switch anchorPolarity
                case 'pos', [~, k_rel] = max(y0);
                case 'neg', [~, k_rel] = min(y0);
                case 'abs', [~, k_rel] = max(abs(y0));
                otherwise,  [~, k_rel] = max(y0);
            end
            anchor = s0a + k_rel - 1;
        end
        fprintf('%s Evt %d: Align: %s\n', tag, e, anchorDesc);
        
        s0 = anchor - HW; s1 = anchor + HW;
        if s0 < 1 || s1 > nSamp
            warning('%s Evt %d: window out of bounds.', tag, e); return;
        end
        
        % --- Collect waveforms for GLOBAL y-limits ---
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
        
        % --- FIX: HARD CAP Y-MAX at 2000 uV ---
        if yMax > 2000
            yMax = 2000;
        end
        yL_global = [-yMax, +yMax];
        
        % --- CWT params ---
        fMax = min(fMaxHz, sfx/2);
        fMin = max(fMinHz, 0.1); 
        if fMin >= fMax, fMin = fMax/100; end
        
        % --- Precompute CWT & CLim across selected channels ---
        allP = [];
        Pane = cell(nCh,1);
        for ci = 1:nCh
            ch = chSel(ci);
            sc = scaleVec(ch);
            y  = double(mf.d(ch, s0:s1)) * sc;
            y(~isfinite(y)) = 0;
            
            % Compute CWT
            [C, F] = cwt(y, sfx, 'FrequencyLimits', [fMin fMax]);
            P = log10(abs(C) + eps);
            
            % --- STRICTLY SORT F ASCENDING ---
            if length(F) > 1 && F(1) > F(end)
                F = flipud(F);
                P = flipud(P);
            end
            
            Tms = tRelMs; 
            Pane{ci} = struct('y',y, 'Tms',Tms, 'F',F, 'P',P);
            allP = [allP; P(:)]; %#ok<AGROW>
        end
        allP = allP(isfinite(allP));
        if isempty(allP), pHi = 0; else, pHi = prctile(allP, climUpperPct); end
        pLo = pHi - climDynRange;
        
        % ---------- Figure ----------
        rowsPerChan = 1;                 
        rowsTotal   = rowsPerChan * nCh;
        
        perRowPx   = 200; 
        figW       = 1000;
        topBotPad  = 320;
        figH_full  = topBotPad + perRowPx*rowsTotal;
        figH       = min(figH_full, maxFigH);
        
        if ~exist(outDir,'dir'), mkdir(outDir); end
        baseName = sprintf('Evt%03d_SpecWave_Stacked', e); 
        
        f = figure('Color','w','Visible','off','Units','pixels', ...
                   'Position',[60 60 figW figH], 'Renderer','opengl', ...
                   'InvertHardcopy','off');
        
        set(f, 'Units', 'inches');
        figPos_inches = get(f, 'Position');
        set(f, 'PaperUnits', 'inches');
        set(f, 'PaperSize', [figPos_inches(3) figPos_inches(4)]);
        set(f, 'PaperPosition', [0 0 figPos_inches(3) figPos_inches(4)]);
        
        tl = tiledlayout(f, rowsTotal, 1, 'Padding','loose','TileSpacing','compact');
        for ci = 1:nCh
            D  = Pane{ci};
            ax = nexttile(tl);
            
            % --- 1. LEFT AXIS: SCALOGRAM (Frequency) ---
            yyaxis(ax, 'left');
            imagesc(ax, D.Tms, D.F, D.P);
            hold(ax, 'on'); 
            
            set(ax, 'YScale', 'log'); 
            
            % --- FIX: Force Normal Direction (Low Freq at Bottom) ---
            set(ax, 'YDir', 'normal'); 
            
            ylim(ax, [fMin fMax]);
            caxis(ax, [pLo pHi]);
            colormap(ax, jet);
            
            ax.YColor = 'k';
            ylabel(ax, 'Frequency (Hz)', 'Color', 'k');
            
            % --- 2. RIGHT AXIS: WAVEFORM (Voltage) ---
            yyaxis(ax, 'right');
            
            % --- Thick Outline + White Fill ---
            plot(ax, tRelMs, D.y, 'k-', 'LineWidth', 2.5);
            hold(ax, 'on');
            plot(ax, tRelMs, D.y, 'w-', 'LineWidth', 1.5);
            
            ylim(ax, yL_global);
            
            ax.YColor = 'k';
            ylabel(ax, 'Amplitude (\muV)', 'Color', 'k');
            
            % --- 3. SHARED AXIS STYLING ---
            xlim(ax, [-100 100]); 
            xticks(ax, [-100 0 100]);
            xline(ax, 0, '--w', 'LineWidth', 0.8, 'Alpha', 0.7); 
            
            ax.TickDir = 'out'; 
            ax.FontSize = 9;
            ax.Layer = 'top'; 
            
            if ci == nCh
                xlabel(ax, 'Time (ms)');
            else
                ax.XTickLabel = []; 
            end
            
            % --- UI FIX: INSET LABELS WITH MAPPING ---
            rowIdx = chSel(ci);
            
            if ~isempty(kept_channels)
                % Map Matrix Row -> Real Channel #
                dispLabel = sprintf('Channel %d', kept_channels(rowIdx));
            else
                % Fallback
                dispLabel = sprintf('Row %d', rowIdx);
            end
            
            text(ax, 0.015, 0.9, dispLabel, ...
                 'Units', 'normalized', 'FontSize', 9, 'FontWeight', 'bold', ...
                 'Color', 'k', ...
                 'BackgroundColor', 'w', ...
                 'EdgeColor', 'k');
        end
        
        cb = colorbar('eastoutside');
        cb.Label.String = 'Power (dB)';
        
        sgtitle(tl, 'Waveform Frequency', 'FontSize',12, 'FontWeight','bold');
        
        drawnow;
        
        outPng = fullfile(outDir, baseName + ".png");
        outPdf = fullfile(outDir, baseName + ".pdf");
        
        exportgraphics(f, outPng, 'Resolution', dpi, 'BackgroundColor','white', 'ContentType','image');
        fprintf('Saved %s (PNG): %s\n', tag, outPng);
        
        try
            print(f, outPdf, '-dpdf', '-painters');
            fprintf('Saved %s (PDF): %s\n', tag, outPdf);
        catch ME
            warning('Failed to save PDF file %s: %s', outPdf, ME.message);
            outPdf = ''; 
        end
        close(f);
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