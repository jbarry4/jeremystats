function out = VoltageRaster_EventsAvg_Pipeline(inputFolder, dataMatPath, varargin)
% VoltageRaster_EventsAvg_Pipeline
% Wrapper that builds ONE averaged voltage raster per group (SOLID/SPUTTER),
% saves PNGs + vector PDFs + a stats CSV, and returns file paths.
%
% Returns struct:
%   out.pngSolid, out.pngSputter
%   out.pdfSolid, out.pdfSputter
%   out.statsCSV
%
% --- NEW ANCHOR PARAMETERS ---
%   'anchorMidpoint' (false): If true, skips peak search and uses the
%                             event's midpoint as the anchor.
%   'anchorChannel'  (0):     Matrix row to use for anchor search.
%                             If 0, defaults to last channel in chList.
%   'anchorPolarity' ('pos'): Type of peak to find: 'pos', 'neg', or 'abs'.
% -----------------------------

% ---------- Run the “core” and collect outputs ----------
[paths, statsTable] = VoltageRaster_AvgGroups_core(inputFolder, dataMatPath, varargin{:});

% Write stats CSV
outDir = fileparts(paths.solidPng);
statsCSV = fullfile(outDir, 'VoltageRaster_Avg_stats.csv');
try
    writetable(statsTable, statsCSV);
catch ME
    warning('VoltageRaster_EventsAvg_Pipeline:failedToWriteStats', 'Failed to write stats CSV: %s', ME.message);
    statsCSV = '';
end

% Return paths for Pipeline_Main
out = struct( ...
    'pngSolid',   paths.solidPng, ...
    'pngSputter', paths.sputterPng, ...
    'pdfSolid',   paths.solidPdf, ...
    'pdfSputter', paths.sputterPdf, ...
    'statsCSV',   statsCSV);
end

% ======================================================================
%                             CORE IMPLEMENTATION
% ======================================================================
function [paths, statsT] = VoltageRaster_AvgGroups_core(inputFolder, dataMatPath, varargin)
% This is adapted from your VoltageRaster_AvgGroups (no functional changes),
% but also returns a stats table for the pipeline.
% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));
p.addParameter('winHalfWidthMs',   20e-3, @(x)isfinite(x)&&x>0);   % ±20 ms display
p.addParameter('metricHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms metrics on MEAN waveform
p.addParameter('anchorHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms anchor search
p.addParameter('climMicroV', [],            @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('yRobustPct', 99.5,          @(x) isfinite(x) && x>0 && x<100);
p.addParameter('climPadFrac', 0.12,         @(x) isfinite(x) && x>=0 && x<=0.5);
p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));

% --- NEW ANCHOR PARAMETERS ---
p.addParameter('anchorMidpoint', false, @(x)islogical(x)||ismember(x,[0 1]));
p.addParameter('anchorChannel', 0, @(x)isscalar(x)&&isnumeric(x)&&x>=0);
p.addParameter('anchorPolarity', 'pos', @(s) any(validatestring(s, {'pos','neg','abs'})));
% --- END NEW PARAMETERS ---

p.parse(inputFolder, dataMatPath, varargin{:});
inputFolder    = string(p.Results.inputFolder);
dataMatPath    = string(p.Results.dataMatPath);
excelPath      = string(p.Results.excelPath);
channelIdx     = p.Results.channelIndices;
scaleToMicroV  = p.Results.scaleToMicroV;
winHWms        = p.Results.winHalfWidthMs;
metHWms        = p.Results.metricHalfWidthMs;
anchorHWms     = p.Results.anchorHalfWidthMs;
climMicroVOpt  = p.Results.climMicroV;
yRobustPct     = p.Results.yRobustPct;
climPadFrac    = p.Results.climPadFrac;
maxEventsPer   = p.Results.maxEventsPerGroup;

% --- NEW ANCHOR PARAMETERS ---
anchorMidpoint = p.Results.anchorMidpoint;
anchorChannel  = p.Results.anchorChannel;
anchorPolarity = p.Results.anchorPolarity;
% --- END NEW PARAMETERS ---

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

outRoot = fullfile(inputFolder, "Voltage Raster Output");
if ~exist(outRoot,'dir'), mkdir(outRoot); end
outSOLpng = fullfile(outRoot, "Raster_Avg_SOLID.png");
outSPUpng = fullfile(outRoot, "Raster_Avg_SPUTTER.png");
outSOLpdf = fullfile(outRoot, "Raster_Avg_SOLID.pdf");
outSPUpdf = fullfile(outRoot, "Raster_Avg_SPUTTER.pdf");

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
assert(nCh > 0, 'No valid channels selected.');

% scaling vector
if numel(scaleToMicroV)==1
    scaleVec = repmat(scaleToMicroV, nRowsAll, 1);
else
    assert(numel(scaleToMicroV) >= nRowsAll, 'scaleToMicroV must be scalar or length >= nRowsAll.');
    scaleVec = scaleToMicroV(:);
end

% ---------------- Windows ----------------
HWwin    = max(1, round(winHWms   * sfx));  % ±display half-width
HWmet    = max(1, round(metHWms   * sfx));  % ±metrics half-width
HWanchor = max(1, round(anchorHWms* sfx));  % ±anchor search
tRelMs   = (-HWwin:HWwin) / sfx * 1e3;
winN     = numel(tRelMs);

% For metric computations on MEAN waveform
metStart = HWwin - HWmet + 1;
metEnd   = HWwin + HWmet + 1;
Lmet     = metEnd - metStart + 1;
fprintf('VoltageRaster_AvgGroups: sfx=%.1f Hz | window ±%.1f ms\n', sfx, 1e3*HWwin/sfx);

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
% Bounds
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));
NrowsXL = numel(onSamp);

% ---------------- Event IDs by PNG names ----------------
evtSOL = parseEvtNumsFromPngs(solidDir);
evtSPU = parseEvtNumsFromPngs(sputterDir);
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));

if ~isempty(maxEventsPer)
    evtSOL = evtSOL(1:min(end, maxEventsPer));
    evtSPU = evtSPU(1:min(end, maxEventsPer));
end

% ---------------- Build averaged waveforms per group ----------------
[S_mu, S_stats] = buildAvg(evtSOL, 'SOLID');
[P_mu, P_stats] = buildAvg(evtSPU, 'SPUTTER');

% --- NEW: Export Raw Values to CSV (matches CSD pipeline style) ---
if ~isempty(S_mu), exportRasterValues(S_mu, 'SOLID'); end
if ~isempty(P_mu), exportRasterValues(P_mu, 'SPUTTER'); end
% --- END NEW ---

% ---------------- Global CLim across BOTH averages ----------------
if isempty(S_mu) && isempty(P_mu)
    warning('VoltageRaster_AvgGroups: no average rasters created.');
    statsT = table(); % nothing to report
    paths = struct('solidPng','', 'sputterPng','', 'solidPdf','', 'sputterPdf','');
    return;
end

if isempty(climMicroVOpt)
    vals = [];
    if ~isempty(S_mu), vals = [vals; abs(S_mu(:))]; end %#ok<AGROW>
    if ~isempty(P_mu), vals = [vals; abs(P_mu(:))]; end %#ok<AGROW>
    vals = vals(isfinite(vals));
    if isempty(vals), pval = 1; else, pval = prctile(vals, yRobustPct); end
    climGlobal = (1 + climPadFrac) * max(1, pval);
else
    climGlobal = climMicroVOpt;
end
fprintf('Global CLim (averages): ±%.2f µV.\n', climGlobal);

% ---------------- Render both with same CLim, 1 at TOP ----------------
pngSOL = ''; pngSPU = ''; pdfSOL = ''; pdfSPU = '';

if ~isempty(S_mu)
    [pngSOL, pdfSOL] = renderAvgRaster(S_mu, 'SOLID', outSOLpng, outSOLpdf, climGlobal, S_stats); 
end
if ~isempty(P_mu)
    [pngSPU, pdfSPU] = renderAvgRaster(P_mu, 'SPUTTER', outSPUpng, outSPUpdf, climGlobal, P_stats); 
end

% ---------------- Build stats table for pipeline ----------------
statsT = table();
if ~isempty(S_mu)
    statsT = [statsT; summarizeGroup('SOLID', S_stats, climGlobal, nCh, sfx, winHWms, anchorHWms, anchorMidpoint, anchorChannel, anchorPolarity)]; %#ok<AGROW>
end
if ~isempty(P_mu)
    statsT = [statsT; summarizeGroup('SPUTTER', P_stats, climGlobal, nCh, sfx, winHWms, anchorHWms, anchorMidpoint, anchorChannel, anchorPolarity)]; %#ok<AGROW>
end

paths = struct('solidPng', pngSOL, 'sputterPng', pngSPU, 'solidPdf', pdfSOL, 'sputterPdf', pdfSPU);

% ============================= HELPERS =============================
    function [MU, stats] = buildAvg(evtList, tag)
        MU = []; stats = struct('nEvents',0,'ampMean',NaN,'ampSD',NaN,'hwMean',NaN,'hwSD',NaN);
        if isempty(evtList), return; end
        
        sumY  = zeros(nCh, winN);
        nUsed = 0;
        perCh_amp = nan(nCh,1);
        perCh_hw  = nan(nCh,1);
        
        % --- Anchor setup message (print once) ---
        anchorDesc = ""; % Will be set on first event
        
        for ii = 1:numel(evtList)
            e = evtList(ii);
            rowXL = e;
            if rowXL < 1 || rowXL > NrowsXL, continue; end
            
            s0_ev = round(onSamp(rowXL));
            s1_ev = round(offSamp(rowXL));
            if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev), continue; end
            
            % --- MODIFIED ANCHOR LOGIC ---
            ancMid = round((s0_ev + s1_ev)/2);
            
            if anchorMidpoint == true
                % Option 1: Use midpoint, skip search
                anchor = ancMid;
                if ii == 1, anchorDesc = sprintf('Anchor: Event Midpoint (search disabled)'); end
            else
                % Option 2: Perform peak-finding search
                
                % Determine reference channel
                if anchorChannel == 0
                    refCh = chList(end); % Default: last channel
                else
                    % Use user-specified channel, with validation
                    if anchorChannel < 1 || anchorChannel > nRowsAll || ~any(chList == anchorChannel)
                        if ii == 1
                            warning('Invalid or unselected anchorChannel %d. Reverting to last channel (%d).', anchorChannel, chList(end));
                        end
                        refCh = chList(end);
                    else
                        refCh = anchorChannel; % Use specified, valid row
                    end
                end
                
                if ii == 1 % Print anchor method on first event
                    anchorDesc = sprintf('Anchor: %s peak on row %d (±%.1f ms search)', ...
                                         anchorPolarity, refCh, 1e3*anchorHWms);
                end
                
                % Define search window
                s0a = max(1, ancMid - HWanchor);
                s1a = min(nSamp, ancMid + HWanchor);
                
                y0 = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
                if isempty(y0) || all(~isfinite(y0)), continue; end
                
                % Find peak based on polarity
                switch anchorPolarity
                    case 'pos'
                        [~, k_rel] = max(y0);
                    case 'neg'
                        [~, k_rel] = min(y0);
                    case 'abs'
                        [~, k_rel] = max(abs(y0));
                    otherwise
                        [~, k_rel] = max(y0); % Default to pos
                end
                
                anchor = s0a + k_rel - 1;
            end
            % --- END MODIFIED ANCHOR LOGIC ---

            if ii == 1, fprintf('(%s) %s\n', tag, anchorDesc); end
            
            % Window
            s0 = anchor - HWwin; s1 = anchor + HWwin;
            if s0 < 1 || s1 > nSamp, continue; end
            
            okAny = false;
            for k = 1:nCh
                ch = chList(k);
                sc = scaleVec(ch);
                y  = double(mf.d(ch, s0:s1)) * sc;
                if any(isfinite(y))
                    sumY(k,:) = sumY(k,:) + y;
                    okAny = true;
                end
            end
            if okAny, nUsed = nUsed + 1; end
        end
        
        if nUsed == 0, return; end
        MU = sumY / nUsed;
        stats.nEvents = nUsed;
        
        % Per-channel metrics on MEAN waveform (±metric window)
        metStartL = HWwin - HWmet + 1;
        metEndL   = HWwin + HWmet + 1;
        LmetL     = metEndL - metStartL + 1;
        
        for k = 1:nCh
            mu = MU(k,:);
            muMet = mu(metStartL:metEndL);
            if numel(muMet) >= 3 && all(isfinite(muMet))
                [mx, kMax] = max(muMet);
                [mn, kMin] = min(muMet);
                
                if abs(mn) > abs(mx)
                    sgn = -1; amp = abs(mn); pkRel = kMin;
                else
                    sgn = +1; amp = abs(mx); pkRel = kMax;
                end
                
                h  = 0.5 * amp; sig = sgn * muMet;
                
                % Left crossing
                kL = pkRel; 
                while kL > 1 && sig(kL) >= h, kL = kL - 1; end
                
                % ***** THIS IS THE CORRECTED LINE *****
                if kL >= 1 && (kL+1) <= LmetL && sig(kL) < h && sig(kL+1) >= h
                    left_ip = kL + (h - sig(kL)) / (sig(kL+1) - sig(kL));
                else, left_ip = NaN; end
                
                % Right crossing
                kR = pkRel;
                while kR < LmetL && sig(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= LmetL && sig(kR-1) >= h && sig(kR) < h
                    right_ip = (kR-1) + (h - sig(kR-1)) / (sig(kR) - sig(kR-1));
                else, right_ip = NaN; end
                
                if isfinite(left_ip) && isfinite(right_ip) && right_ip > left_ip
                    hw_ms = (right_ip - left_ip) / sfx * 1e3;
                else
                    hw_ms = NaN;
                end
                perCh_amp(k) = amp;
                perCh_hw(k)  = hw_ms;
            end
        end
        stats.ampMean = mean(perCh_amp, 'omitnan');
        stats.ampSD   = std( perCh_amp, 0, 'omitnan');
        stats.hwMean  = mean(perCh_hw,  'omitnan');
        stats.hwSD    = std( perCh_hw,  0, 'omitnan');
    end

    function [outPngPath, outPdfPath] = renderAvgRaster(MU, tag, outPngPath, outPdfPath, clim, stats)
        perRowPx = 12; basePx = 260; maxPx = 2600;
        figH = min(maxPx, basePx + perRowPx * nCh);
        f = figure('Color','w','Position',[90 90 1100 figH],'Visible','off');
        
        % --- Font Size Controls ---
        titleSize    = 18; 
        axisFontSize = 14;
        
        % --- Full Manual PDF Layout Control ---
        set(f, 'Units', 'inches');
        figPos_inches = get(f, 'Position');
        set(f, 'PaperUnits', 'inches');
        set(f, 'PaperSize', [figPos_inches(3) figPos_inches(4)]);
        set(f, 'PaperPosition', [0 0 figPos_inches(3) figPos_inches(4)]);
        
        ax1 = axes('Parent', f);
        imagesc(ax1, 'XData', [tRelMs(1) tRelMs(end)], 'YData', [1 nCh], 'CData', MU);
        set(ax1, 'YDir', 'reverse');          % 1 at top
        caxis(ax1, [-clim, +clim]);
        colormap(ax1, jet); 
        
        % --- Colorbar ---
        cb = colorbar(ax1);
        cb.Label.String = 'Voltage (\muV)';
        cb.Label.Rotation = 90;
        cb.Label.FontSize = axisFontSize;
        cb.FontSize = axisFontSize;
        
        % --- Labels & Title ---
        xlabel(ax1, 'Time (ms)', 'FontSize', axisFontSize, 'FontWeight', 'bold');
        ylabel(ax1, 'Channel #', 'FontSize', axisFontSize, 'FontWeight', 'bold');
        title(ax1, {sprintf('%s Average Voltage Raster', tag), ' '}, 'FontSize', titleSize, 'FontWeight', 'bold');
        
        % --- Map row indices to actual hardware channels ---
        if isempty(kept_channels)
            actualChans = chList;
        else
            actualChans = kept_channels(chList);
        end
        
        % --- Y-Ticks (Even Channels Only) ---
        evenIdx = find(mod(actualChans, 2) == 0);
        yticks(ax1, evenIdx);
        yticklabels(ax1, string(actualChans(evenIdx)));
        
        % --- TIGHT BORDER & GAP FIX (Same as Theta) ---
        set(ax1, 'FontSize', axisFontSize, 'TickDir', 'out', 'Layer', 'top');
        box(ax1, 'off');   % Kills native box
        grid(ax1, 'off');  
        
        axis(ax1, 'tight');
        xl = xlim(ax1);
        yl = ylim(ax1);
        
        % Trace a clean black frame over the exact edges
        hold(ax1, 'on');
        plot(ax1, [xl(1) xl(2) xl(2) xl(1) xl(1)], [yl(1) yl(1) yl(2) yl(2) yl(1)], 'k-', 'LineWidth', 2, 'Clipping', 'off');
        
        % =================================================================
        % --- ADD SPECTROGRAM INDICATOR ICONS ---
        % =================================================================
        specChans = [8, 16, 24, 32, 40, 48, 56, 64];
        
        % Find which rows correspond to our target spectrogram channels
        [~, locs] = ismember(specChans, actualChans);
        validLocs = locs(locs > 0); % Only plot markers for channels actually present
        
        if ~isempty(validLocs)
            % Place marker slightly to the left of the Y-axis (-2% of width)
            markerX = xl(1) - (xl(2) - xl(1)) * 0.025; 
            plot(ax1, repmat(markerX, size(validLocs)), validLocs, 'r>', ...
                'MarkerFaceColor', 'r', 'MarkerEdgeColor', 'k', 'MarkerSize', 10, 'Clipping', 'off');
        end
        % =================================================================
        
        drawnow;
        
        % Save PNG
        exportgraphics(f, outPngPath, 'Resolution', 300); % Bumped to 300 DPI
        fprintf('Saved %s average raster (PNG): %s\n', tag, outPngPath);
        
        % Save PDF
        try
            print(f, outPdfPath, '-dpdf', '-painters');
            fprintf('Saved %s average raster (PDF): %s\n', tag, outPdfPath);
        catch ME
            warning('Failed to save PDF file %s: %s', outPdfPath, ME.message);
            outPdfPath = ''; % Return empty if failed
        end
        
        close(f);
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

    % --- MODIFIED: Added new anchor parameters to stats table ---
    function Trow = summarizeGroup(tag, stats, climG, nCh_, sfx_, winHWms_, anchorHWms_, anchorMidpoint_, anchorChannel_, anchorPolarity_)
        Trow = table( ...
            string(tag), stats.nEvents, nCh_, sfx_, ...
            1e3*winHWms_, 1e3*anchorHWms_, ...
            climG, stats.ampMean, stats.ampSD, stats.hwMean, stats.hwSD, ...
            anchorMidpoint_, anchorChannel_, string(anchorPolarity_), ...
            'VariableNames', {'Group','Events','Channels','SampRateHz', ...
                              'DisplayHalfWidth_ms','AnchorHalfWidth_ms', ...
                              'CLim_uV','MeanPeak_uV','SD_Peak_uV','MeanHW_ms','SD_HW_ms', ...
                              'AnchorMidpoint','AnchorChannelRow','AnchorPolarity'});
    end

    % --- NEW: Export Raster Values Helper ---
    function exportRasterValues(MU, tag)
        if isempty(MU), return; end
        try
            % 1. Create Column Headers (Time points)
            % e.g. "T_minus20p0ms", "T_0p0ms"
            tHeaders = arrayfun(@(t) sprintf('T_%.2fms', t), tRelMs, 'UniformOutput', false);
            % Sanitize for table variables (replace . with p, - with minus/m)
            tHeaders = strrep(tHeaders, '.', 'p');
            tHeaders = strrep(tHeaders, '-', 'm');
            
            % 2. Create Channel Label Column
            if isempty(kept_channels)
                cLab = arrayfun(@(k) sprintf('row %d', chList(k)), 1:nCh, 'UniformOutput',false);
            else
                cLab = arrayfun(@(k) sprintf('row %d (CSC%d)', chList(k), kept_channels(chList(k))), 1:nCh, 'UniformOutput',false);
            end

            % 3. Assemble and Write Table
            T_rows = table(cLab(:), 'VariableNames', {'Channel'});
            T_vals = array2table(MU, 'VariableNames', tHeaders);
            T_out  = [T_rows, T_vals];
            
            outName = fullfile(outRoot, sprintf('VoltageRaster_Avg_Values_%s.csv', tag));
            writetable(T_out, outName);
            fprintf('Saved Raw Voltage Values CSV: %s\n', outName);
        catch ME
            warning('Failed to save raw voltage values CSV for %s: %s', tag, ME.message);
        end
    end
end