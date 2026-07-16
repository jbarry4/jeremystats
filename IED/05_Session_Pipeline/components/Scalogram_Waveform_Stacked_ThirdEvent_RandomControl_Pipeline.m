function out = Scalogram_Waveform_Stacked_ThirdEvent_RandomControl_Pipeline(inputFolder, dataMatPath, varargin)
% Scalogram_Waveform_Stacked_ThirdEvent_Pipeline
% --- CWT (WAVELET) VERSION -- TARGET vs CONTROL ---
% - Uses the 3rd event from SOLID and SPUTTER (if present).
% - Defaults to 1st event if 3rd not present.
% - Selects every 4th ROW (spatial density).
% - Maps Row Index -> Real Channel # (CSC) for labels.
% - Overlays Waveform (White with Black Outline) on top of Scalogram.
% - LEFT COLUMN: Target Event.
% - RIGHT COLUMN: Random Control (5-10s offset).
%
% OUTPUT: PNG(s)/PDF(s) under "<inputFolder>/Spectrogram Waveform Stacked Output/{Solid,Sputter}"
% -----------------------------

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
p.addParameter('anchorMidpoint', false, @(x)islogical(x)||ismember(x,[0 1]));
p.addParameter('anchorChannel', 0, @(x)isscalar(x)&&isnumeric(x)&&x>=0);
p.addParameter('anchorPolarity', 'pos', @(s) any(validatestring(s, {'pos','neg','abs'})));
% CWT Parameters
p.addParameter('fMinHz',      20,   @(x)isfinite(x)&&x>0);   
p.addParameter('fMaxHz',      1000, @(x)isfinite(x)&&x>0);
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
    chSel = unique(chUser, 'stable');
    chSel = chSel(chSel>=1 & chSel<=nRowsAll);
else
    chSel = 4:4:nRowsAll;
end
if isempty(chSel), error('No valid channels to select from.'); end

nCh = numel(chSel);
fprintf('Selected %d matrix rows for Scalogram (Every 4th): %s\n', nCh, mat2str(chSel));

% ---------- Render 3rd event (or 1st) ----------
if numel(evtSOL) >= 3
    fprintf('SOLID: Found %d events, using 3rd event (Evt %d).\n', numel(evtSOL), evtSOL(3));
    [out.pngSolid, out.pdfSolid] = renderOne(evtSOL(3), 'SOLID', outSOL, chSel);
elseif numel(evtSOL) >= 1
    warning('SOLID: Found fewer than 3 events. Defaulting to 1st (Evt %d).', evtSOL(1));
    [out.pngSolid, out.pdfSolid] = renderOne(evtSOL(1), 'SOLID', outSOL, chSel);
end

if numel(evtSPU) >= 3
    fprintf('SPUTTER: Found %d events, using 3rd event (Evt %d).\n', numel(evtSPU), evtSPU(3));
    [out.pngSputter, out.pdfSputter] = renderOne(evtSPU(3), 'SPUTTER', outSPU, chSel);
elseif numel(evtSPU) >= 1
    warning('SPUTTER: Found fewer than 3 events. Defaulting to 1st (Evt %d).', evtSPU(1));
    [out.pngSputter, out.pdfSputter] = renderOne(evtSPU(1), 'SPUTTER', outSPU, chSel);
end

fprintf('Scalogram_Waveform_Stacked_ThirdEvent pipeline done.\n');

% ======================================================================
%                              NESTED: RENDER
% ======================================================================
    function [outPng, outPdf] = renderOne(e, tag, outDir, chSel)
        outPng = ""; outPdf = "";
        HW = max(1, round(0.100 * sfx));
        tRelMs = (-HW:HW) / sfx * 1e3;
        
        if e < 1 || e > NrowsXL, warning('%s Evt %d: out of range.', tag, e); return; end
        s0_ev = round(onSamp(e)); s1_ev = round(offSamp(e));
        
        % --- 1. DETERMINE TARGET ANCHOR ---
        HWanchor = max(1, round(anchorHWms * sfx));
        ancMid = round((s0_ev + s1_ev)/2);
        anchorDesc = ""; 
        
        if anchorMidpoint == true
            anchor = ancMid;
            anchorDesc = "Event Midpoint";
        else
            if anchorChannel == 0, refCh = chSel(end); else, refCh = anchorChannel; end
            anchorDesc = sprintf("%s peak on row %d", anchorPolarity, refCh);
            s0a = max(1, ancMid - HWanchor);
            s1a = min(nSamp, ancMid + HWanchor);
            scRef = scaleVec(refCh);
            y0 = double(mf.d(refCh, s0a:s1a)) * scRef;
            
            switch anchorPolarity
                case 'pos', [~, k_rel] = max(y0);
                case 'neg', [~, k_rel] = min(y0);
                case 'abs', [~, k_rel] = max(abs(y0));
                otherwise,  [~, k_rel] = max(y0);
            end
            anchor = s0a + k_rel - 1;
        end
        
        s0t = anchor - HW; s1t = anchor + HW;
        if s0t < 1 || s1t > nSamp, warning('%s Evt %d: target out of bounds.', tag, e); return; end

        % --- 2. DETERMINE RANDOM CONTROL ANCHOR (5-10s away) ---
        % Try to find a valid window 5-10s before or after
        validControl = false;
        attempts = 0;
        offsetDesc = "";
        
        while ~validControl && attempts < 20
            offsetSec = 5 + (10-5)*rand(); % Random 5.0 to 10.0 seconds
            if rand() > 0.5, dir = 1; else, dir = -1; end
            
            offsetSamp = round(offsetSec * sfx * dir);
            anchorC    = anchor + offsetSamp;
            s0c = anchorC - HW; 
            s1c = anchorC + HW;
            
            if s0c >= 1 && s1c <= nSamp
                validControl = true;
                offsetDesc = sprintf("%+.1fs", offsetSec * dir);
            end
            attempts = attempts + 1;
        end
        
        if ~validControl
            warning('Could not find valid control window for Evt %d. Using target as placeholder.', e);
            s0c = s0t; s1c = s1t; offsetDesc = "Duplicate";
        end

        fprintf('%s Evt %d: Align: %s | Control: %s\n', tag, e, anchorDesc, offsetDesc);
        
        % --- 3. PRE-SCAN TARGET TO SET LIMITS ---
        % We base y-limits and CWT color limits on the TARGET to show true contrast.
        rob = 0;
        allP_Target = [];
        
        % Pre-calculation loop (Target only)
        for ci = 1:nCh
            ch = chSel(ci);
            sc = scaleVec(ch);
            y  = double(mf.d(ch, s0t:s1t)) * sc;
            yy = y(isfinite(y));
            if isempty(yy), continue; end
            
            % Amplitude Limit
            pval = prctile(abs(yy), yRobustPct);
            if pval > rob, rob = pval; end
            
            % CWT Color Limit
            fMax = min(fMaxHz, sfx/2);
            fMin = max(fMinHz, 0.1); 
            [C, ~] = cwt(y, sfx, 'FrequencyLimits', [fMin fMax]);
            P = log10(abs(C) + eps);
            allP_Target = [allP_Target; P(:)]; %#ok<AGROW>
        end
        
        % Compute Global Limits
        if isempty(yLimMicroV)
            yMax = (1 + yPadFrac) * max(1, rob);
        else
            yMax = yLimMicroV;
        end
        if yMax > 3000, yMax = 3000; end % Cap
        yL_global = [-yMax, +yMax];
        
        allP_Target = allP_Target(isfinite(allP_Target));
        if isempty(allP_Target), pHi = 0; else, pHi = prctile(allP_Target, climUpperPct); end
        pLo = pHi - climDynRange;
        
        % --- 4. EXTRACT & CWT FOR BOTH ---
        PaneTarget  = cell(nCh,1);
        PaneControl = cell(nCh,1);
        
        for ci = 1:nCh
            ch = chSel(ci);
            sc = scaleVec(ch);
            
            % Function to process one window
            processWin = @(sStart, sEnd) processWindow(mf, ch, sc, sStart, sEnd, sfx, fMin, fMax, tRelMs);
            
            PaneTarget{ci}  = processWin(s0t, s1t);
            PaneControl{ci} = processWin(s0c, s1c);
        end
        
        % ---------- Figure ----------
        rowsPerChan = 1;                 
        rowsTotal   = rowsPerChan * nCh;
        perRowPx    = 200; 
        figW        = 1800; % Wider for side-by-side
        topBotPad   = 320;
        figH_full   = topBotPad + perRowPx*rowsTotal;
        figH        = min(figH_full, maxFigH);
        
        if ~exist(outDir,'dir'), mkdir(outDir); end
        baseName = sprintf('Evt%03d_SpecWave_Stacked_Control', e); 
        
        f = figure('Color','w','Visible','off','Units','pixels', ...
                   'Position',[60 60 figW figH], 'Renderer','opengl', ...
                   'InvertHardcopy','off');
        
        set(f, 'Units', 'inches');
        figPos_inches = get(f, 'Position');
        set(f, 'PaperUnits', 'inches');
        set(f, 'PaperSize', [figPos_inches(3) figPos_inches(4)]);
        set(f, 'PaperPosition', [0 0 figPos_inches(3) figPos_inches(4)]);
        
        % 2 Columns: Left = Target, Right = Control
        tl = tiledlayout(f, rowsTotal, 2, 'Padding','loose','TileSpacing','compact');
        
        for ci = 1:nCh
            % --- LEFT: TARGET ---
            axT = nexttile(tl);
            plotPanel(axT, PaneTarget{ci}, fMin, fMax, pLo, pHi, yL_global, kept_channels, chSel(ci), ci==nCh, 'Target');
            
            if ci == 1, title(axT, "TARGET EVENT", 'FontSize', 14, 'FontWeight', 'bold'); end
            
            % --- RIGHT: CONTROL ---
            axC = nexttile(tl);
            plotPanel(axC, PaneControl{ci}, fMin, fMax, pLo, pHi, yL_global, kept_channels, chSel(ci), ci==nCh, 'Control');
            
            if ci == 1, title(axC, sprintf("CONTROL (%s)", offsetDesc), 'FontSize', 14, 'FontWeight', 'bold', 'Color', [0.4 0.4 0.4]); end
        end
        
        cb = colorbar('eastoutside');
        cb.Layout.Tile = 'east';
        cb.Label.String = 'Power (dB)';
        
        sgtitle(tl, sprintf('%s Event %d vs Random Reference', tag, e), 'FontSize',16, 'FontWeight','bold');
        
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
function S = processWindow(mf, ch, sc, s0, s1, sfx, fMin, fMax, tRelMs)
    y  = double(mf.d(ch, s0:s1)) * sc;
    y(~isfinite(y)) = 0;
    
    [C, F] = cwt(y, sfx, 'FrequencyLimits', [fMin fMax]);
    P = log10(abs(C) + eps);
    
    if length(F) > 1 && F(1) > F(end)
        F = flipud(F);
        P = flipud(P);
    end
    S = struct('y',y, 'Tms',tRelMs, 'F',F, 'P',P);
end

function plotPanel(ax, D, fMin, fMax, pLo, pHi, yL, kept_channels, rowIdx, showX, ~)
    % 1. SCALOGRAM
    yyaxis(ax, 'left');
    imagesc(ax, D.Tms, D.F, D.P);
    hold(ax, 'on'); 
    set(ax, 'YScale', 'log'); 
    set(ax, 'YDir', 'normal'); 
    ylim(ax, [fMin fMax]);
    caxis(ax, [pLo pHi]);
    colormap(ax, jet);
    ax.YColor = 'k';
    
    % 2. WAVEFORM
    yyaxis(ax, 'right');
    plot(ax, D.Tms, D.y, 'k-', 'LineWidth', 2.5);
    hold(ax, 'on');
    plot(ax, D.Tms, D.y, 'w-', 'LineWidth', 1.5);
    ylim(ax, yL);
    ax.YColor = 'k';
    
    % 3. STYLING
    xlim(ax, [-100 100]); 
    xticks(ax, [-100 0 100]);
    xline(ax, 0, '--w', 'LineWidth', 0.8, 'Alpha', 0.7); 
    ax.TickDir = 'out'; 
    ax.FontSize = 9;
    ax.Layer = 'top'; 
    
    if showX
        xlabel(ax, 'Time (ms)');
    else
        ax.XTickLabel = []; 
    end
    
    % Channel Label
    if ~isempty(kept_channels)
        dispLabel = sprintf('Ch %d', kept_channels(rowIdx));
    else
        dispLabel = sprintf('Row %d', rowIdx);
    end
    text(ax, 0.02, 0.9, dispLabel, ...
         'Units', 'normalized', 'FontSize', 8, 'FontWeight', 'bold', ...
         'Color', 'k', 'BackgroundColor', 'w', 'EdgeColor', 'none', 'Margin', 1);
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