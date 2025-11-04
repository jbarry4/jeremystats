function res = CSD_TimeAvgSlices_Waveforms_AvgGroups_Pipeline(inputFolder, dataMatPath, varargin)
% CSD_TimeAvgSlices_Waveforms_AvgGroups_Pipeline
% Build per-group figures with:
%   LEFT  : per-event **time-averaged** CSD columns (channels × events, thickened)
%   RIGHT : vertical waveforms (each event in gray; group mean in black)
% Time-average window defaults to [0, +15] ms around the alignment anchor.
%
% RETURNS:
%   res.pngSolid, res.pngSputter  : output figure PNGs (or "" if not created)
%   res.pdfSolid, res.pdfSputter  : output figure PDFs (or "" if not created)
%   res.statsCSV                  : table written to CSV (or "" if failed)
%
% OUTPUT FILES:
%   <inputFolder>/CSD Center Slices Output/CSD_TimeAvg_SOLID.png
%   <inputFolder>/CSD Center Slices Output/CSD_TimeAvg_SOLID.pdf
%   <inputFolder>/CSD Center Slices Output/CSD_TimeAvg_SPUTTER.png
%   <inputFolder>/CSD Center Slices Output/CSD_TimeAvg_SPUTTER.pdf
%   <inputFolder>/CSD Center Slices Output/CSD_TimeAvg_stats.csv

% ---------- Args ----------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('excelPath', "", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));
p.addParameter('winHalfWidthMs',    20e-3, @(x)isfinite(x)&&x>0);   % ±20 ms around anchor
p.addParameter('anchorHalfWidthMs',  5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms anchor search
p.addParameter('avgStartMs',         0e-3, @(x)isfinite(x));        % time-avg start (rel to anchor)
p.addParameter('avgEndMs',          15e-3, @(x)isfinite(x));        % time-avg end   (rel to anchor)
p.addParameter('sliceThickness', 6, @(x)isfinite(x) && x>=1 && mod(x,1)==0);
p.addParameter('robustPct',    99.5, @(x) isfinite(x) && x>0 && x<100);
p.addParameter('padFrac',       0.12, @(x) isfinite(x) && x>=0 && x<=0.5);
p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));
p.parse(inputFolder, dataMatPath, varargin{:});
inputFolder   = string(p.Results.inputFolder);
dataMatPath   = string(p.Results.dataMatPath);
excelPath     = string(p.Results.excelPath);
channelIdx    = p.Results.channelIndices;
scaleToMicroV = p.Results.scaleToMicroV;
winHWms       = p.Results.winHalfWidthMs;
anchorHWms    = p.Results.anchorHalfWidthMs;
avgStartMs    = p.Results.avgStartMs;
avgEndMs      = p.Results.avgEndMs;
sliceThick    = p.Results.sliceThickness;
robPct        = p.Results.robustPct;
padFrac       = p.Results.padFrac;
maxEventsPer  = p.Results.maxEventsPerGroup;

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
outSOLpng = fullfile(outRoot, "CSD_TimeAvg_SOLID.png");
outSPUpng = fullfile(outRoot, "CSD_TimeAvg_SPUTTER.png");
outSOLpdf = fullfile(outRoot, "CSD_TimeAvg_SOLID.pdf");
outSPUpdf = fullfile(outRoot, "CSD_TimeAvg_SPUTTER.pdf");
statsCSV  = fullfile(outRoot, "CSD_TimeAvg_stats.csv");
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
tRelMs   = (-HWwin:HWwin) / sfx * 1e3;
centerIdx= HWwin + 1;
% Indices for time-average window relative to center
i0 = centerIdx + round(avgStartMs * sfx);
i1 = centerIdx + round(avgEndMs   * sfx);
i0 = max(1, min(i0, numel(tRelMs)));
i1 = max(1, min(i1, numel(tRelMs)));
if i1 < i0, [i0,i1] = deal(i1,i0); end
fprintf(['CSD Time-Average Slices: sfx=%.1f Hz | capture ±%.1f ms | avg window [%+.1f,%+.1f] ms ' ...
         '| anchor: lastCh max (±%.1f ms)\n'], ...
    sfx, 1e3*HWwin/sfx, 1e3*avgStartMs, 1e3*avgEndMs, 1e3*HWanchor/sfx);

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
[statsSOL, okSOL, pdfSOL] = buildAndRender(evtSOL, 'SOLID',   outSOLpng, outSOLpdf);
[statsSPU, okSPU, pdfSPU] = buildAndRender(evtSPU, 'SPUTTER', outSPUpng, outSPUpdf);
% --- END MODIFIED ---

% ---------- Save stats CSV ----------
% --- MODIFIED: Add PDF paths to output struct ---
res = struct('pngSolid',"", 'pngSputter',"", ...
             'pdfSolid',"", 'pdfSputter',"", ...
             'statsCSV',"");
try
    S = [statsSOL; statsSPU];
    if ~isempty(S)
        writetable(S, statsCSV);
        res.statsCSV = statsCSV;
    end
catch ME
    warning(ME.identifier, 'Failed to write CSD_TimeAvg stats CSV: %s', ME.message);
end
if okSOL
    res.pngSolid = outSOLpng;
    res.pdfSolid = pdfSOL; 
end
if okSPU
    res.pngSputter = outSPUpng;
    res.pdfSputter = pdfSPU;
end
% --- END MODIFIED ---
end

% ============================= HELPERS =============================
% --- MODIFIED: Function signature ---
function [Tstats, ok, outPdfPath] = buildAndRender(evtList, tag, outPngPath, outPdfPath)
    Tstats = table(); ok = false;
    if isempty(evtList)
        warning('CSD_TimeAvg:%s:NoEvents', '%s: no events to plot.', tag); 
        return;
    end
    
    % pull from outer scope
    mf = evalin('caller','mf'); sfx = evalin('caller','sfx'); 
    chList = evalin('caller','chList'); nCh = evalin('caller','nCh');
    kept_channels = evalin('caller','kept_channels'); %#ok<NASGU>
    scaleVec = evalin('caller','scaleVec');
    onSamp = evalin('caller','onSamp'); offSamp = evalin('caller','offSamp'); NrowsXL = evalin('caller','NrowsXL');
    HWanchor = evalin('caller','HWanchor'); HWwin = evalin('caller','HWwin');
    i0 = evalin('caller','i0'); i1 = evalin('caller','i1');
    sliceThick = evalin('caller','sliceThick'); robPct = evalin('caller','robPct'); padFrac = evalin('caller','padFrac');

    S = nan(nCh, numel(evtList));  % per-event TIME-AVERAGED CSD (channels x events)
    used = false(numel(evtList),1);
    
    for ii = 1:numel(evtList)
        e = evtList(ii);
        rowXL = e;
        if rowXL < 1 || rowXL > NrowsXL, continue; end
        
        s0_ev = round(onSamp(rowXL));
        s1_ev = round(offSamp(rowXL));
        if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev), continue; end
        
        % Anchor by last-channel positive peak (±anchor window)
        ancMid = round((s0_ev + s1_ev)/2);
        s0a = max(1, ancMid - HWanchor);
        s1a = min(evalin('caller','nSamp'), ancMid + HWanchor);
        refCh = chList(end);
        
        y0 = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
        if isempty(y0) || all(~isfinite(y0)), continue; end
        
        [~, k_rel] = max(y0);
        anchor = s0a + k_rel - 1;
        
        % Window around anchor
        s0 = anchor - HWwin;
        s1 = anchor + HWwin;
        if s0 < 1 || s1 > evalin('caller','nSamp'), continue; end
        
        % Extract block (channels x time) and CSD
        Y = nan(nCh, 2*HWwin+1);
        for k = 1:nCh
            ch = chList(k);
            sc = scaleVec(ch);
            y = double(mf.d(ch, s0:s1)) * sc;
            if any(isfinite(y)), Y(k,:) = y; end
        end
        if all(~isfinite(Y(:))), continue; end
        
        C = computeCSD(Y); % channels x time
        % TIME-AVERAGE over [i0..i1]
        S(:,ii) = mean(C(:, i0:i1), 2, 'omitnan');
        used(ii) = true;
    end
    
    if ~any(used)
        warning('CSD_TimeAvg:%s:NoUsable', '%s: no usable events after alignment and windowing.', tag);
        return;
    end
    
    S = S(:,used);              % keep only used events
    nEvt = size(S,2);
    MU  = mean(S,2, 'omitnan'); % mean vertical waveform (channels)
    
    % Robust symmetric scale
    vals = abs(S(:)); vals = vals(isfinite(vals));
    if isempty(vals), pval = 1; else, pval = prctile(vals, robPct); end
    clim = (1 + padFrac) * max(1, pval);
    
    % -------- Figure (tight alignment) --------
    figH = min(320 + 14*nCh, 3400);
    f = figure('Color','w','Position',[60 60 1200 figH],'Visible','off');
    
    % --- START: Full Manual PDF Layout Control (Lesson 4) ---
    set(f, 'Units', 'inches');
    figPos_inches = get(f, 'Position');
    set(f, 'PaperUnits', 'inches');
    set(f, 'PaperSize', [figPos_inches(3) figPos_inches(4)]);
    set(f, 'PaperPosition', [0 0 figPos_inches(3) figPos_inches(4)]);
    % --- END: Full Manual PDF Layout Control ---
    
    % One tiledlayout
    tl = tiledlayout(f, 1, 2, 'Padding','compact', 'TileSpacing','compact');
    
    % Channel labels once (left only)
    if isempty(kept_channels)
        chanLabels = arrayfun(@(kk) sprintf('row %d', chList(kk)), 1:nCh, 'UniformOutput',false);
    else
        chanLabels = arrayfun(@(kk) sprintf('row %d (CSC%d)', chList(kk), kept_channels(chList(kk))), 1:nCh, 'UniformOutput',false);
    end
    
    % LEFT: per-event time-avg image (repeat columns = thickness)
    ax1 = nexttile(tl); 
    hold(ax1, 'on');
    if sliceThick==1
        Img = S;
    else
        Img = repelem(S, 1, sliceThick);
    end
    imagesc(ax1, 1:size(Img,2), 1:nCh, Img);
    set(ax1,'YDir','reverse', 'YLim',[0.5 nCh+0.5], 'TickDir','out', ...
        'FontSize',9, 'YTick',1:nCh, 'YTickLabel',chanLabels, ...
        'Box','on', 'Layer','top', 'TickLength',[0 0]);
    caxis(ax1, [-clim, +clim]); colormap(ax1, jet);
    
    % Event tick marks
    if sliceThick >= 2
        centers = ((0:nEvt-1)*sliceThick) + ceil(sliceThick/2);
    else
        centers = 1:nEvt;
    end
    xticks(ax1, centers); xticklabels(ax1, string(1:nEvt));
    xlabel(ax1, 'Event #'); ylabel(ax1, 'Channel (1 at top)');
    
    % RIGHT: vertical waveform — all (gray) + average (black)
    ax2 = nexttile(tl); 
    hold(ax2, 'on'); grid(ax2,'on'); box(ax2,'on');
    set(ax2,'YDir','reverse', 'YLim',[0.5 nCh+0.5], 'TickDir','out', ...
        'FontSize',9, 'YTick',1:nCh, 'YTickLabel',[], ...
        'Layer','top', 'TickLength',[0 0]);
    y = 1:nCh;
    for i = 1:nEvt
        plot(ax2, S(:,i), y, '-', 'Color', [0.6 0.6 0.6 0.8], 'LineWidth', 0.9);
    end
    plot(ax2, MU, y, '-', 'Color', [0 0 0], 'LineWidth', 2.0);
    xline(ax2, 0, '--k', 'LineWidth', 0.8);
    xlim(ax2, [-clim, +clim]);
    xlabel(ax2, sprintf('CSD (avg %+.1f to %+.1f ms)\n(− sink   |   + source)', ...
        1e3*evalin('caller','avgStartMs'), 1e3*evalin('caller','avgEndMs')));
    
    % Link Y; shared colorbar
    set([ax1 ax2], 'LooseInset', max(get(ax1,'TightInset'), get(ax2,'TightInset')));
    linkaxes([ax1 ax2], 'y');
    axes(ax1); cb = colorbar; 
    try, cb.Layout.Tile = 'east'; catch, set(cb,'Location','eastoutside'); end
    cb.Label.String = sprintf('CSD units (CLim = \\pm%.2f)', clim);
    
    % Titles
    title(ax1, sprintf('%s — TIME-AVG CSD (n=%d)', tag, nEvt), 'FontSize',10, 'FontWeight','bold');
    title(ax2, sprintf('%s — Vertical waveform (mean in black)', tag), 'FontSize',10, 'FontWeight','bold');
    sg = sprintf('%s  |  align: last-channel max (\\pm%.1f ms)  |  capture: \\pm%.1f ms  |  avg window [%+.1f,%+.1f] ms  |  channels=%d', ...
        tag, 1e3*HWanchor/sfx, 1e3*HWwin/sfx, 1e3*evalin('caller','avgStartMs'), 1e3*evalin('caller','avgEndMs'), nCh);
    sgtitle(tl, sg, 'FontSize',10, 'FontWeight','bold');
    
    % --- MODIFIED: Export PNG and PDF ---
    % Save PNG
    exportgraphics(f, outPngPath, 'Resolution', 220);
    fprintf('Saved %s (PNG): %s\n', tag, outPngPath);
    
    % Save PDF (Lessons 1, 2, 3)
    try
        print(f, outPdfPath, '-dpdf', '-painters');
        fprintf('Saved %s (PDF): %s\n', tag, outPdfPath);
    catch ME
        warning('Failed to save PDF file %s: %s', outPdfPath, ME.message);
        outPdfPath = ''; % Return empty string if failed
    end
    
    close(f);
    % --- END MODIFIED ---
    
    ok = true;
    % Stats table (per group)
    Tstats = table(string(tag), nEvt, clim, 'VariableNames', {'group','n_events','clim_used'});
end

function evts = parseEvtNumsFromPngs(dirpath)
    L = dir(fullfile(dirpath, '*.png')); evts = [];
    for k = 1:numel(L)
        m = regexp(L(k).name, 'Evt(\d+)', 'tokens', 'once');
        if ~isempty(m)
            ev = str2double(m{1}); if isfinite(ev), evts(end+1) = ev; end %#ok<AGROW>
        end
    end
    evts = sort(unique(evts));
end

function C = computeCSD(Ych_t)
% standard 3-pt stencil; replicate edges so first/last row aren't blank
    [nCh, ~] = size(Ych_t);
    if nCh < 2, C = nan(size(Ych_t)); return;
    elseif nCh == 2, C = zeros(size(Ych_t)); return; end
    Cint = -( Ych_t(3:end,:) - 2*Ych_t(2:end-1,:) + Ych_t(1:end-2,:) );
    C = zeros(size(Ych_t));
    C(2:end-1,:) = Cint;
    C(1,:)   = C(2,:);
    C(end,:) = C(end-1,:);
end