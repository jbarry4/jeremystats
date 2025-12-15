function out = CSD_CenterSlices_Waveform_AvgGroups_Pipeline(inputFolder, dataMatPath, varargin)
% CSD_CenterSlices_Waveform_AvgGroups_Pipeline
% Left: Vertical Waveform @ 0 ms (Mean in black, individual events in gray).
% Right: Per-event CSD slices at 0 ms (Heatmap).
%
% OUTPUT struct:
%   out.pngSolid, out.pngSputter, out.pdfSolid, out.pdfSputter, out.statsCSV
%
% --- NEW ANCHOR PARAMETERS ---
%   'anchorMidpoint' (false): If true, skips peak search and uses the
%                             event's midpoint as the anchor.
%   'anchorChannel'  (0):     Matrix row to use for anchor search.
%                             If 0, defaults to last channel in chList.
%   'anchorPolarity' ('pos'): Type of peak to find: 'pos', 'neg', or 'abs'.
% -----------------------------
% ---------- Args ----------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('excelPath', "", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));
p.addParameter('winHalfWidthMs',    20e-3, @(x)isfinite(x)&&x>0);   % ±20 ms around anchor
p.addParameter('anchorHalfWidthMs',  5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms anchor search
p.addParameter('sliceThickness', 6, @(x)isfinite(x) && x>=1 && mod(x,1)==0); % columns per event tile
p.addParameter('robustPct',    99.5, @(x) isfinite(x) && x>0 && x<100);
p.addParameter('padFrac',       0.12, @(x) isfinite(x) && x>=0 && x<=0.5);
p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('absoluteClim', 1000, @(x) isempty(x) || (isscalar(x) && x>0)); 
% --- NEW ANCHOR PARAMETERS ---
p.addParameter('anchorMidpoint', false, @(x)islogical(x)||ismember(x,[0 1]));
p.addParameter('anchorChannel', 0, @(x)isscalar(x)&&isnumeric(x)&&x>=0);
p.addParameter('anchorPolarity', 'pos', @(s) any(validatestring(s, {'pos','neg','abs'})));
% --- END NEW PARAMETERS ---
p.parse(inputFolder, dataMatPath, varargin{:});
inputFolder   = string(p.Results.inputFolder);
dataMatPath   = string(p.Results.dataMatPath);
excelPath     = string(p.Results.excelPath);
channelIdx    = p.Results.channelIndices;
scaleToMicroV = p.Results.scaleToMicroV;
winHWms       = p.Results.winHalfWidthMs;
anchorHWms    = p.Results.anchorHalfWidthMs;
sliceThick    = p.Results.sliceThickness;
robPct        = p.Results.robustPct;
padFrac       = p.Results.padFrac;
maxEventsPer  = p.Results.maxEventsPerGroup;
absoluteClim  = p.Results.absoluteClim; 
% --- NEW ANCHOR PARAMETERS ---
anchorMidpoint = p.Results.anchorMidpoint;
anchorChannel  = p.Results.anchorChannel;
anchorPolarity = p.Results.anchorPolarity;
% --- END NEW PARAMETERS ---
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
outRoot = fullfile(inputFolder, "CSD Center Slices Output");
if ~exist(outRoot,'dir'), mkdir(outRoot); end
% --- MODIFIED: Added PDF paths ---
outSOLpng = fullfile(outRoot, "CSD_CenterSlices_SOLID.png");
outSPUpng = fullfile(outRoot, "CSD_CenterSlices_SPUTTER.png");
outSOLpdf = fullfile(outRoot, "CSD_CenterSlices_SOLID.pdf");
outSPUpdf = fullfile(outRoot, "CSD_CenterSlices_SPUTTER.pdf");
outCSV    = fullfile(outRoot, "CSD_CenterSlices_stats.csv");
% --- END MODIFIED ---
% ---------- Data ----------
assert(isfile(dataMatPath), 'Data MAT not found: %s', dataMatPath);
mf = matfile(dataMatPath);
try sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRowsAll = size(mf,'d',1);
nSamp    = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end %#ok<NASGU>
% Channels
if isempty(channelIdx)
    chList = 1:nRowsAll;
else
    chList = channelIdx(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);
assert(nCh > 0, 'No valid channels selected.');
% Scaling
if numel(scaleToMicroV)==1
    scaleVec = repmat(scaleToMicroV, nRowsAll, 1);
else
    assert(numel(scaleToMicroV) >= nRowsAll, 'scaleToMicroV must be scalar or length >= nRowsAll.');
    scaleVec = scaleToMicroV(:);
end
% ---------- Windows ----------
HWwin    = max(1, round(winHWms    * sfx));  % ±display half-width
HWanchor = max(1, round(anchorHWms * sfx));  % ±anchor search
tRelMs   = (-HWwin:HWwin) / sfx * 1e3; %#ok<NASGU>
centerIdx= HWwin + 1;
% Indices to average the "center slice" over [-1, 0] ms
i0_slice = centerIdx + round(-1e-3 * sfx);  % -1 ms
i1_slice = centerIdx;                       %  0 ms
i0_slice = max(1, min(2*HWwin+1, i0_slice));
i1_slice = max(1, min(2*HWwin+1, i1_slice));
fprintf('CSD Center Slices PIPELINE: sfx=%.1f Hz | window ±%.1f ms\n', ...
    sfx, 1e3*HWwin/sfx);
% ---------- Excel -> sample indices ----------
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
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));
if ~isempty(maxEventsPer)
    evtSOL = evtSOL(1:min(end, maxEventsPer));
    evtSPU = evtSPU(1:min(end, maxEventsPer));
end
% ---------- Build & render ----------
% --- MODIFIED: Pass PDF paths to render function ---
S1 = buildAndRender(evtSOL, 'SOLID',   outSOLpng, outSOLpdf);
S2 = buildAndRender(evtSPU, 'SPUTTER', outSPUpng, outSPUpdf);
% --- END MODIFIED ---
% ---------- Stats CSV ----------
try
    G = {};
    if ~isempty(S1), G{end+1} = S1; end %#ok<AGROW>
    if ~isempty(S2), G{end+1} = S2; end %#ok<AGROW>
    if ~isempty(G)
        Tcsv = vertcat(G{:});
        writetable(Tcsv, outCSV);
    else
        % create a stub so main can find something
        writetable(cell2table(cell(0,10), 'VariableNames', ...
            {'group','nEvents','clim','sliceThickness','anchorHW_ms','winHW_ms','note', ...
             'AnchorMidpoint','AnchorChannelRow','AnchorPolarity'}), outCSV);
    end
catch ME
    warning(ME.identifier, 'CSD_CenterSlices_Waveform_AvgGroups_Pipeline: failed to write stats CSV: %s', ME.message);
end
% ---------- Return ----------
% --- MODIFIED: Add PDF paths to output struct ---
out = struct('pngSolid', outSOLpng, 'pngSputter', outSPUpng, ...
             'pdfSolid', outSOLpdf, 'pdfSputter', outSPUpdf, ...
             'statsCSV', outCSV);
% --- END MODIFIED ---
% ============================= HELPERS =============================
    % --- MODIFIED: Function signature ---
    function Tgroup = buildAndRender(evtList, tag, outPngPath, outPdfPath)
        Tgroup = table(); 
        
        % Pull variables from caller scope
        outRoot = evalin('caller','outRoot'); 
        mf = evalin('caller','mf'); sfx = evalin('caller','sfx'); 
        chList = evalin('caller','chList'); nCh = evalin('caller','nCh');
        kept_channels = evalin('caller','kept_channels'); 
        scaleVec = evalin('caller','scaleVec');
        onSamp = evalin('caller','onSamp'); offSamp = evalin('caller','offSamp'); NrowsXL = evalin('caller','NrowsXL');
        HWanchor = evalin('caller','HWanchor'); HWwin = evalin('caller','HWwin');
        sliceThick = evalin('caller','sliceThick'); robPct = evalin('caller','robPct'); padFrac = evalin('caller','padFrac');
        absoluteClim = evalin('caller','absoluteClim'); 
        
        i0_slice = evalin('caller','i0_slice');
        i1_slice = evalin('caller','i1_slice');
        
        anchorMidpoint = evalin('caller', 'anchorMidpoint');
        anchorChannel  = evalin('caller', 'anchorChannel');
        anchorPolarity = evalin('caller', 'anchorPolarity');
        nRowsAll       = evalin('caller', 'nRowsAll');
        nSamp          = evalin('caller', 'nSamp');
    
        if isempty(evtList)
            warning('CSDCenterSlices:%s', '%s: no events to plot.', tag);
            return;
        end
        
        % ================= CALCULATION LOOP =================
        S = nan(nCh, numel(evtList));  % per-event 0 ms CSD slice (channels x events)
        used = false(numel(evtList),1);
        anchorDesc = ""; 
        
        for ii = 1:numel(evtList)
            e = evtList(ii);
            rowXL = e;
            if rowXL < 1 || rowXL > NrowsXL, continue; end
            
            s0_ev = round(onSamp(rowXL));
            s1_ev = round(offSamp(rowXL));
            if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev), continue; end
            
            % Anchor Logic
            ancMid = round((s0_ev + s1_ev)/2);
            
            if anchorMidpoint == true
                anchor = ancMid;
                if ii == 1, anchorDesc = "Event Midpoint"; end
            else
                if anchorChannel == 0, refCh = chList(end); else, refCh = anchorChannel; end
                if anchorChannel < 1 || anchorChannel > nRowsAll, refCh = chList(end); end
                
                if ii == 1, anchorDesc = sprintf("%s peak on row %d", anchorPolarity, refCh); end
                
                s0a = max(1, ancMid - HWanchor);
                s1a = min(nSamp, ancMid + HWanchor);
                y0 = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
                if isempty(y0) || all(~isfinite(y0)), continue; end
                
                switch anchorPolarity
                    case 'pos', [~, k_rel] = max(y0);
                    case 'neg', [~, k_rel] = min(y0);
                    case 'abs', [~, k_rel] = max(abs(y0));
                    otherwise,  [~, k_rel] = max(y0);
                end
                anchor = s0a + k_rel - 1;
            end
            
            if ii == 1, fprintf('(%s) Align: %s\n', tag, anchorDesc); end
            
            % Data Extraction
            s0 = anchor - HWwin; s1 = anchor + HWwin;
            if s0 < 1 || s1 > nSamp, continue; end
            
            Y = nan(nCh, 2*HWwin+1);
            for k = 1:nCh
                ch = chList(k);
                Y(k,:) = double(mf.d(ch, s0:s1)) * scaleVec(ch);
            end
            if all(~isfinite(Y(:))), continue; end
            
            C = computeCSD(Y); 
            % Slice at t = 0 ms
            S(:,ii) = mean(C(:, i0_slice:i1_slice), 2, 'omitnan');
            used(ii) = true;
        end
        
        if ~any(used)
            warning('CSDCenterSlices:%s', '%s: no usable events.', tag);
            return;
        end
        
        S = S(:,used);
        evtList = evtList(used);
        nEvt = size(S,2);
        MU  = mean(S,2, 'omitnan');
    
        % Generate Channel Labels (Simplified to number strings)
        if isempty(kept_channels)
            chanLabels = arrayfun(@(kk) sprintf('%d', chList(kk)), 1:nCh, 'UniformOutput',false);
        else
            chanLabels = arrayfun(@(kk) sprintf('%d', kept_channels(chList(kk))), 1:nCh, 'UniformOutput',false);
        end
    
        % ================= EXPORT RAW VALUES TO CSV =================
        try
            colHeaders = arrayfun(@(x) sprintf('Evt_%d', x), evtList, 'UniformOutput', false);
            T_export = table(chanLabels(:), 'VariableNames', {'Channel'});
            T_data = array2table(S, 'VariableNames', colHeaders);
            T_export = [T_export, T_data];
            csvValPath = fullfile(outRoot, sprintf('CSD_CenterSlices_Values_%s.csv', tag));
            writetable(T_export, csvValPath);
            fprintf('Saved Raw Values: %s\n', csvValPath);
        catch ME
            warning('Failed to save raw values CSV: %s', ME.message);
        end
        
        % Scaling logic
        if ~isempty(absoluteClim)
            clim = absoluteClim;
        else
            vals = abs(S(:)); vals = vals(isfinite(vals));
            if isempty(vals), pval = 1; else, pval = prctile(vals, robPct); end
            clim = (1 + padFrac) * max(1, pval);
        end
        
        % ================= PLOTTING =================
        figH = min(320 + 14*nCh, 3400);
        f = figure('Color','w','Position',[60 60 1200 figH],'Visible','off');
        
        set(f, 'Units', 'inches'); figPos = get(f, 'Position');
        set(f, 'PaperUnits', 'inches', 'PaperSize', figPos(3:4), 'PaperPosition', [0 0 figPos(3:4)]);
        
        colormap(f, jet);
        
        % 1. Use 50 columns to create a tiny "1-column gap" at column 25
        tl = tiledlayout(f, 1, 50, 'Padding','compact', 'TileSpacing','none');
        
        % Determine Crop Range: Rows 1 and nCh are blank/NaN, so we crop them.
        if nCh >= 3
            yL_crop = [1.5, nCh-0.5];
        else
            yL_crop = [0.5, nCh+0.5];
        end
        
        % --- LEFT PANEL: Vertical Waveform (Spans 1-24) ---
        ax1 = nexttile(tl, 1, [1 24]); 
        hold(ax1, 'on'); grid(ax1,'on'); box(ax1,'on');
        
        y = 1:nCh;
        for i = 1:nEvt
            plot(ax1, S(:,i), y, '-', 'Color', [0.6 0.6 0.6 0.8], 'LineWidth', 0.9);
        end
        plot(ax1, MU, y, '-', 'Color', [0 0 0], 'LineWidth', 2.0);
        xline(ax1, 0, '--k'); xlim(ax1, [-clim, +clim]);
        
        % FIX: Apply Crop to Y-Limits
        set(ax1,'YDir','reverse', 'YLim', yL_crop, 'TickDir','out', ...
            'FontSize',9, 'YTick',1:nCh, 'YTickLabel',chanLabels, 'Layer','top');
        
        ylabel(ax1, 'Channel #');
        xlabel(ax1, 'CSD (a.u.)');
        
        % --- RIGHT PANEL: Event Heatmap (Spans 26-50) ---
        ax2 = nexttile(tl, 26, [1 25]); 
        hold(ax2, 'on');
        
        if sliceThick==1
            Img = S;
        else
            Img = repelem(S, 1, sliceThick);
        end
        imagesc(ax2, 1:size(Img,2), 1:nCh, Img);
        
        % FIX: Apply Crop to Y-Limits here too
        set(ax2,'YDir','reverse', 'YLim', yL_crop, 'TickDir','out', ...
            'FontSize',9, 'YTick', [], 'YTickLabel', [], ...
            'Box','on', 'Layer','top', 'TickLength',[0 0]);
            
        % FIX: Explicitly set X-Limits to remove side whitespace
        xlim(ax2, [0.5, size(Img,2)+0.5]);
        
        caxis(ax2, [-clim, +clim]);
        
        % Colorbar
        axes(ax2); cb = colorbar; 
        try cb.Layout.Tile = 'east'; catch, set(cb,'Location','eastoutside'); end
        cb.Label.String = 'CSD (a.u.)'; % 5. Updated label
        
        % X-Axis Ticks
        if sliceThick >= 2
            % FIX: Use floating point math to center ticks exactly
            centers = ( (0:nEvt-1)*sliceThick ) + (sliceThick/2) + 0.5;
        else
            centers = 1:nEvt;
        end
        xticks(ax2, centers); 
        xticklabels(ax2, string(1:nEvt));
        ax2.XTickLabelRotation = 0;
        
        xlabel(ax2, 'Event #'); 
        
        linkaxes([ax1 ax2], 'y');
        
        % 2. Title: Simplified
        sgtitle(tl, 'Ground-zero: CSD [-1, 0]ms', 'FontSize',10, 'FontWeight','bold');
        
        exportgraphics(f, outPngPath, 'Resolution', 220);
        try print(f, outPdfPath, '-dpdf', '-painters'); catch, end
        close(f);
        
        Tgroup = table(string(tag), size(S,2), clim, sliceThick, ...
                       1e3*HWanchor/sfx, 1e3*HWwin/sfx, string('OK'), ...
                       anchorMidpoint, anchorChannel, string(anchorPolarity), ...
            'VariableNames', {'group','nEvents','clim','sliceThickness','anchorHW_ms','winHW_ms','note', ...
                              'AnchorMidpoint','AnchorChannelRow','AnchorPolarity'});
    end
end
% --------- utilities ---------
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
function C = computeCSD(Ych_t)
% (channels x time) voltage (µV) → CSD (channels x time)
% Interior: standard 3-point stencil.
% Edges: NaN (lost, no padding).
    [nCh, nT] = size(Ych_t);
    if nCh < 3
        C = nan(nCh, nT); return;
    end
    
    Cint = -( Ych_t(3:end,:) - 2*Ych_t(2:end-1,:) + Ych_t(1:end-2,:) );
    
    C = nan(nCh, nT);
    C(2:end-1,:) = Cint;
end