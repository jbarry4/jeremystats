function out = CSDRaster_Avg_Pipeline(inputFolder, dataMatPath, varargin)
% CSDRaster_Avg_Pipeline
% Wrapper that builds ONE averaged CSD raster per group (SOLID/SPUTTER),
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

[paths, statsTable] = CSDRaster_Avg_core(inputFolder, dataMatPath, varargin{:});

% Write stats CSV (always alongside the PNGs)
outDir  = fileparts(paths.solidPng);
statsCSV = fullfile(outDir, 'CSDRaster_Avg_stats.csv');
try
    writetable(statsTable, statsCSV);
catch ME
    warning('CSDRaster_Avg_Pipeline: failed to write stats CSV: %s', ME.message);
    statsCSV = '';
end

% --- MODIFIED: Added PDF paths to output struct ---
out = struct( ...
    'pngSolid',   paths.solidPng, ...
    'pngSputter', paths.sputterPng, ...
    'pdfSolid',   paths.solidPdf, ...
    'pdfSputter', paths.sputterPdf, ...
    'statsCSV',   statsCSV);
% --- END MODIFIED ---
end

% ======================================================================
%                             CORE (adapted)
% ======================================================================
function [paths, statsT] = CSDRaster_Avg_core(inputFolder, dataMatPath, varargin)
% Adapted from your CSDRaster_Avg (same behavior), but returns:
%   - paths struct with PNG/PDF paths
%   - stats table for pipeline CSV merge

% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));
p.addParameter('winHalfWidthMs',   20e-3, @(x)isfinite(x)&&x>0);   % ±20 ms display
p.addParameter('metricHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms metrics on MEAN CSD
p.addParameter('anchorHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms anchor search
p.addParameter('climCSD',     [],            @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('yRobustPct',  99.5,          @(x) isfinite(x) && x>0 && x<100);
p.addParameter('climPadFrac', 0.12,          @(x) isfinite(x) && x>=0 && x<=0.5);
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
climCSDOpt     = p.Results.climCSD;
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

outRoot = fullfile(inputFolder, "CSD Raster Output");
if ~exist(outRoot,'dir'), mkdir(outRoot); end
% --- MODIFIED: Added PDF paths ---
outSOLpng = fullfile(outRoot, "CSD_Raster_Avg_SOLID.png");
outSPUpng = fullfile(outRoot, "CSD_Raster_Avg_SPUTTER.png");
outSOLpdf = fullfile(outRoot, "CSD_Raster_Avg_SOLID.pdf");
outSPUpdf = fullfile(outRoot, "CSD_Raster_Avg_SPUTTER.pdf");
% --- END MODIFIED ---

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

% Metrics-on-mean window indices
metStart = HWwin - HWmet + 1;
metEnd   = HWwin + HWmet + 1;
Lmet     = metEnd - metStart + 1;

% --- MODIFIED: More general logging ---
fprintf('CSD AvgGroups: sfx=%.1f Hz | window ±%.1f ms\n', ...
    sfx, 1e3*HWwin/sfx);

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

% ---------------- Build averaged CSD per group ----------------
[S_csd, S_stats] = buildAvgCSD(evtSOL, 'SOLID');
[P_csd, P_stats] = buildAvgCSD(evtSPU, 'SPUTTER');

% --- NEW: Export Raw CSD Values to CSV (Matches VoltageRaster style) ---
if ~isempty(S_csd), exportCSDValues(S_csd, 'SOLID'); end
if ~isempty(P_csd), exportCSDValues(P_csd, 'SPUTTER'); end
% --- END NEW ---

% ---------------- Global CLim across BOTH CSD averages ----------------
if isempty(S_csd) && isempty(P_csd)
    warning('CSDRaster_Avg_core: no average CSD rasters created.');
    statsT = table();
    % --- MODIFIED: Added PDF paths ---
    paths = struct('solidPng','', 'sputterPng','', 'solidPdf','', 'sputterPdf','');
    % --- END MODIFIED ---
    return;
end

if isempty(climCSDOpt)
    vals = [];
    if ~isempty(S_csd), vals = [vals; abs(S_csd(:))]; end %#ok<AGROW>
    if ~isempty(P_csd), vals = [vals; abs(P_csd(:))]; end %#ok<AGROW>
    vals = vals(isfinite(vals));
    if isempty(vals), pval = 1; else, pval = prctile(vals, yRobustPct); end
    climGlobal = (1 + climPadFrac) * max(1, pval);
else
    climGlobal = climCSDOpt;
end
fprintf('Global CSD CLim (averages): ±%.2f (CSD units).\n', climGlobal);

% ---------------- Render both with same CLim, 1 at TOP ----------------
% --- MODIFIED: Initialize PDF paths and update render call ---
pngSOL = ''; pngSPU = ''; pdfSOL = ''; pdfSPU = '';

if ~isempty(S_csd)
    [pngSOL, pdfSOL] = renderAvgRaster(S_csd, 'SOLID', outSOLpng, outSOLpdf, climGlobal, S_stats); 
end
if ~isempty(P_csd)
    [pngSPU, pdfSPU] = renderAvgRaster(P_csd, 'SPUTTER', outSPUpng, outSPUpdf, climGlobal, P_stats); 
end
% --- END MODIFIED ---

% ---------------- Stats table for pipeline ----------------
statsT = table();
if ~isempty(S_csd)
    % --- MODIFIED: Pass new anchor params ---
    statsT = [statsT; summarizeGroup('SOLID', S_stats, climGlobal, nCh, sfx, winHWms, anchorHWms, anchorMidpoint, anchorChannel, anchorPolarity)]; %#ok<AGROW>
end
if ~isempty(P_csd)
    % --- MODIFIED: Pass new anchor params ---
    statsT = [statsT; summarizeGroup('SPUTTER', P_stats, climGlobal, nCh, sfx, winHWms, anchorHWms, anchorMidpoint, anchorChannel, anchorPolarity)]; %#ok<AGROW>
end

% --- MODIFIED: Added PDF paths to output struct ---
paths = struct('solidPng', pngSOL, 'sputterPng', pngSPU, 'solidPdf', pdfSOL, 'sputterPdf', pdfSPU);
% --- END MODIFIED ---

% ============================= HELPERS =============================
    function [CSDMU, stats] = buildAvgCSD(evtList, tag)
        CSDMU = [];
        stats = struct('nEvents',0,'pkMean',NaN,'pkSD',NaN,'hwMean',NaN,'hwSD',NaN);
        if isempty(evtList), return; end
        
        % Accumulate mean VOLTAGE first; then CSD(mean)
        sumY  = zeros(nCh, winN);
        nUsed = 0;
        
        anchorDesc = ""; % For logging
        
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
                if ii == 1, anchorDesc = "Event Midpoint"; end
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
                    anchorDesc = sprintf("%s peak on row %d (±%.1f ms)", ...
                                         anchorPolarity, refCh, 1e3*anchorHWms/sfx);
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
            
            if ii == 1, fprintf('(%s) Align: %s\n', tag, anchorDesc); end
            % --- END MODIFIED ANCHOR LOGIC ---
            
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
        MU    = sumY / nUsed;   % mean VOLTAGE per channel
        CSDMU = computeCSD(MU); % CSD(mean)
        stats.nEvents = nUsed;
        
        % Metrics on the MEAN CSD (per-channel signed-peak & HW in ±metric window)
        perCh_pk = nan(nCh,1);
        perCh_hw = nan(nCh,1);
        
        for k = 1:nCh
            cs = CSDMU(k,:);
            csMet = cs(metStart:metEnd);
            if numel(csMet) >= 3 && all(isfinite(csMet))
                [mx, kMax] = max(csMet);
                [mn, kMin] = min(csMet);
                
                if abs(mn) > abs(mx)
                    sgn = -1; amp = abs(mn); pkRel = kMin;
                else
                    sgn = +1; amp = abs(mx); pkRel = kMax;
                end
                
                h  = 0.5 * amp; sig = sgn * csMet;
                
                % Left crossing
                kL = pkRel;
                while kL > 1 && sig(kL) >= h, kL = kL - 1; end
                if kL >= 1 && (kL+1) <= Lmet && sig(kL) < h && sig(kL+1) >= h
                    left_ip = kL + (h - sig(kL)) / (sig(kL+1) - sig(kL));
                else, left_ip = NaN; end
                
                % Right crossing
                kR = pkRel;
                while kR < Lmet && sig(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= Lmet && sig(kR-1) >= h && sig(kR) < h
                    right_ip = (kR-1) + (h - sig(kR-1)) / (sig(kR) - sig(kR-1));
                else, right_ip = NaN; end
                
                if isfinite(left_ip) && isfinite(right_ip) && right_ip > left_ip
                    hw_ms = (right_ip - left_ip) / sfx * 1e3;
                else
                    hw_ms = NaN;
                end
                perCh_pk(k) = amp;
                perCh_hw(k) = hw_ms;
            end
        end
        stats.pkMean = mean(perCh_pk, 'omitnan');
        stats.pkSD   = std( perCh_pk, 0, 'omitnan');
        stats.hwMean = mean(perCh_hw,  'omitnan');
        stats.hwSD   = std( perCh_hw,  0, 'omitnan');
    end

    % --- MODIFIED: Function signature and export block ---
    function [outPngPath, outPdfPath] = renderAvgRaster(CSDMU, tag, outPngPath, outPdfPath, clim, stats)
        % Slightly larger figure to avoid title cropping; smaller title font.
        perRowPx = 14; basePx = 290; maxPx = 2800;
        figH = min(maxPx, basePx + perRowPx * nCh);
        f = figure('Color','w','Position',[90 90 1100 figH],'Visible','off');
        
        % --- START: Full Manual PDF Layout Control (Lesson 4) ---
        set(f, 'Units', 'inches');
        figPos_inches = get(f, 'Position');
        set(f, 'PaperUnits', 'inches');
        set(f, 'PaperSize', [figPos_inches(3) figPos_inches(4)]);
        set(f, 'PaperPosition', [0 0 figPos_inches(3) figPos_inches(4)]);
        % --- END: Full Manual PDF Layout Control ---
        
        % --- FIX: AUTO-CROPPING PADDING ---
        % Identify rows that are NOT fully NaN (i.e., contain data)
        hasData = ~all(isnan(CSDMU), 2);
        validRows = find(hasData);
        
        % Fallback: if somehow empty, show everything
        if isempty(validRows), validRows = 1:nCh; end
        
        % Slice the data and labels to show ONLY valid rows
        CSDMU_cropped = CSDMU(validRows, :);
        
        % Plot using validRows as the Y-coordinates (so Y-axis numbers remain correct)
        imagesc(tRelMs, validRows, CSDMU_cropped);
        set(gca, 'YDir', 'reverse');          % 1 at top
        
        % Crop axes tightly to the valid rows (e.g., 1.5 to 63.5)
        ylim([min(validRows)-0.5, max(validRows)+0.5]);
        
        caxis([-clim, +clim]);
        colormap(jet); 
        
        % Colorbar setup
        cb = colorbar;
        cb.Label.String = 'CSD (a.u.)';
        cb.Label.Rotation = 90;
        
        xlabel('Time (ms)');
        
        % Label generation
        ylabel('Channel #');
        if isempty(kept_channels)
            % Default labels (integers)
            L_full = string(chList);
        else
            % CSC mapped labels
            L_full = arrayfun(@(kk) sprintf('%d', kept_channels(chList(kk))), 1:nCh, 'UniformOutput',false);
        end
        
        % Use only the labels for the valid rows
        L_cropped = L_full(validRows);
        
        set(gca,'YTick',validRows, 'YTickLabel',L_cropped, 'FontSize',9);
        title('Average CSD Raster', 'FontSize', 12, 'FontWeight', 'bold');
        
        % Save PNG
        exportgraphics(f, outPngPath, 'Resolution', 220);
        fprintf('Saved %s average CSD raster (PNG): %s\n', tag, outPngPath);
        
        % Save PDF (Lessons 1, 2, 3)
        try
            print(f, outPdfPath, '-dpdf', '-painters');
            fprintf('Saved %s average CSD raster (PDF): %s\n', tag, outPdfPath);
        catch ME
            warning('Failed to save PDF file %s: %s', outPdfPath, ME.message);
            outPdfPath = ''; % Return empty if failed
        end
        
        close(f);
    end
    % --- END MODIFIED ---

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
    % computeCSD: second spatial derivative across channels.
    % --- FIX: PADDING REMOVED ---
    % First and last rows are now returned as NaN (blank/lost).
        [nChLoc, nT] = size(Ych_t);
        if nChLoc < 2
            C = nan(nChLoc, nT); return;
        elseif nChLoc == 2
            C = nan(nChLoc, nT); return;
        end
        
        % Compute interior second derivative
        Cint = -( Ych_t(3:end,:) - 2*Ych_t(2:end-1,:) + Ych_t(1:end-2,:) );
        
        % Initialize with NaNs
        C = nan(nChLoc, nT);
        
        % Fill interior only. Rows 1 and nChLoc remain NaN.
        C(2:end-1,:) = Cint;
    end

    % --- MODIFIED: Added new anchor parameters to stats table ---
    function Trow = summarizeGroup(tag, stats, climG, nCh_, sfx_, winHWms_, anchorHWms_, anchorMidpoint_, anchorChannel_, anchorPolarity_)
        Trow = table( ...
            string(tag), stats.nEvents, nCh_, sfx_, ...
            1e3*winHWms_, 1e3*anchorHWms_, ...
            climG, stats.pkMean, stats.pkSD, stats.hwMean, stats.hwSD, ...
            anchorMidpoint_, anchorChannel_, string(anchorPolarity_), ...
            'VariableNames', {'Group','Events','Channels','SampRateHz', ...
                              'DisplayHalfWidth_ms','AnchorHalfWidth_ms', ...
                              'CLim_CSD','MeanCSDPeak','SD_CSDPeak','MeanHW_ms','SD_HW_ms', ...
                              'AnchorMidpoint','AnchorChannelRow','AnchorPolarity'});
    end

    % --- NEW: Export CSD Values Helper ---
    function exportCSDValues(MU, tag)
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
            
            outName = fullfile(outRoot, sprintf('CSD_Raster_Avg_Values_%s.csv', tag));
            writetable(T_out, outName);
            fprintf('Saved Raw CSD Values CSV: %s\n', outName);
        catch ME
            warning('Failed to save raw CSD values CSV for %s: %s', tag, ME.message);
        end
    end
end