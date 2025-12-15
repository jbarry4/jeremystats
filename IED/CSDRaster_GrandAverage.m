function CSDRaster_GrandAverage(rootFolder, varargin)
% CSDRaster_GrandAverage
% Recursively finds 'CSD_Raster_Avg_Values_SOLID.csv' (and ...SPUTTER.csv if needed)
% in the given rootFolder, calculates the Grand Average (mean across animals),
% and saves the results (CSV, PNG, PDF) in a 'CSD_GrandAverage_Output' folder.
%
% Usage:
%   CSDRaster_GrandAverage(rootFolder)
%   CSDRaster_GrandAverage(..., 'climCSD', 500)
%
% Parameters:
%   rootFolder : String/char path to the top-level directory containing animal subfolders.
%   'climCSD'  : (Optional) Manual color limit (±CSD units). If empty, calculated automatically
%                across BOTH groups (Base & CNO) so they share the same scale.

    p = inputParser;
    p.addRequired('rootFolder', @(s) ischar(s) || isstring(s));
    p.addParameter('climCSD', [], @(x) isempty(x) || (isscalar(x) && x > 0));
    p.parse(rootFolder, varargin{:});
    
    rootFolder = char(p.Results.rootFolder);
    climOpt    = p.Results.climCSD;
    
    % Output Directory
    outDir = fullfile(rootFolder, 'CSD_GrandAverage_Output');
    if ~exist(outDir, 'dir'), mkdir(outDir); end
    
    fprintf('======================================================\n');
    fprintf('   STARTING CSD GRAND AVERAGE PROCESSING\n');
    fprintf('======================================================\n');
    fprintf('Root Folder: %s\n', rootFolder);
    fprintf('Output Dir:  %s\n', outDir);

    % --- Load Group Info ---
    groupFile = fullfile(rootFolder, 'Mice_group.csv');
    if ~isfile(groupFile)
        error('Mice_group.csv not found in: %s', rootFolder);
    end
    
    fprintf('Loading group info from: %s\n', groupFile);
    T_grp = readtable(groupFile);
    
    % Normalize variable names
    grpCols = lower(T_grp.Properties.VariableNames);
    idxGrp     = find(strcmp(grpCols, 'group'), 1);
    idxSession = find(strcmp(grpCols, 'session'), 1);
    idxLabeled = find(strcmp(grpCols, 'labeled'), 1);
    
    if isempty(idxGrp) || isempty(idxSession)
        error('Mice_group.csv must contain "Group" and "Session" columns.');
    end
    
    groups   = T_grp{:, idxGrp};
    sessions = T_grp{:, idxSession};
    
    if ~isempty(idxLabeled)
        labeled = T_grp{:, idxLabeled};
        if iscell(labeled) || isstring(labeled)
            labeledMask = strcmpi(string(labeled), 'TRUE');
        else
            labeledMask = logical(labeled);
        end
    else
        labeledMask = true(size(groups));
    end
    
    % --- DIAGNOSTIC: Print Loaded Criteria ---
    baseMask = strcmpi(groups, 'base');
    cnoMask = strcmpi(groups, 'cno');
    
    validBase = sessions(baseMask & labeledMask);
    validCNO  = sessions(cnoMask & labeledMask);
    
    skippedBase = sessions(baseMask & ~labeledMask);
    skippedCNO  = sessions(cnoMask & ~labeledMask);
    
    fprintf('\n--- SEARCH CRITERIA (Loaded from CSV) ---\n');
    fprintf('BASE SESSIONS to find (%d):\n', numel(validBase));
    if ~isempty(validBase), fprintf('  %s\n', strjoin(string(validBase), ', ')); end
    
    fprintf('CNO SESSIONS to find  (%d):\n', numel(validCNO));
    if ~isempty(validCNO), fprintf('  %s\n', strjoin(string(validCNO), ', ')); end
    
    if ~isempty(skippedBase) || ~isempty(skippedCNO)
        fprintf('SKIPPED (Labeled=FALSE) (%d):\n', numel(skippedBase) + numel(skippedCNO));
        if ~isempty(skippedBase), fprintf('  Base: %s\n', strjoin(string(skippedBase), ', ')); end
        if ~isempty(skippedCNO),  fprintf('  CNO:  %s\n', strjoin(string(skippedCNO), ', ')); end
    end
    fprintf('-----------------------------------------\n');
    
    % --- File Discovery & Classification ---
    % LOOKING FOR CSD FILES NOW
    fileName = 'CSD_Raster_Avg_Values_SOLID.csv';
    fprintf('\nSearching file system for "%s"...\n', fileName);
    
    filePattern = fullfile(rootFolder, '**', fileName);
    allFiles = dir(filePattern);
    
    % Filter out files in output folder to avoid self-inclusion
    keepMask = true(size(allFiles));
    for i = 1:numel(allFiles)
        if contains(allFiles(i).folder, 'CSD_GrandAverage_Output')
            keepMask(i) = false;
        end
    end
    allFiles = allFiles(keepMask);
    
    if isempty(allFiles)
        fprintf('No CSD SOLID CSV files found.\n');
        return;
    end
    
    % Classify Files
    baseFiles = [];
    cnoFiles = [];
    
    fprintf('\n--- DETECTED FOLDERS & MATCHING LOG ---\n');
    for i = 1:numel(allFiles)
        folderPath = string(allFiles(i).folder);
        
        isBase = false;
        isCNO = false;
        matchedSession = "";
        
        % Check Base
        for s = 1:numel(validBase)
            searchStr = string(validBase(s)); 
            if contains(folderPath, searchStr, 'IgnoreCase', true)
                isBase = true;
                matchedSession = searchStr;
                break;
            end
        end
        
        % Check CNO (only if not already Base)
        if ~isBase
            for s = 1:numel(validCNO)
                searchStr = string(validCNO(s));
                if contains(folderPath, searchStr, 'IgnoreCase', true)
                    isCNO = true;
                    matchedSession = searchStr;
                    break;
                end
            end
        end
        
        % Shorten path for display
        shortPath = folderPath; 
        if strlength(shortPath) > 60
            shortPath = "..." + extractAfter(shortPath, strlength(shortPath)-60);
        end
        
        if isBase
            fprintf('  [BASE] %s (Matches: "%s")\n', char(shortPath), char(matchedSession));
            baseFiles = [baseFiles; allFiles(i)]; %#ok<AGROW>
        elseif isCNO
            fprintf('  [CNO ] %s (Matches: "%s")\n', char(shortPath), char(matchedSession));
            cnoFiles = [cnoFiles; allFiles(i)]; %#ok<AGROW>
        else
            % DIAGNOSTIC: Why did it fail?
            reason = "No matching string in path";
            
            % Check if it matches a SKIPPED session (Labeled=FALSE)
            for s = 1:numel(skippedBase)
                checkStr = string(skippedBase(s));
                if contains(folderPath, checkStr, 'IgnoreCase', true)
                    reason = sprintf("MATCHES SKIPPED BASE ITEM '%s'", checkStr);
                    break;
                end
            end
            for s = 1:numel(skippedCNO)
                checkStr = string(skippedCNO(s));
                if contains(folderPath, checkStr, 'IgnoreCase', true)
                    reason = sprintf("MATCHES SKIPPED CNO ITEM '%s'", checkStr);
                    break;
                end
            end
            
            fprintf('  [----] %s -> IGNORED. Reason: %s\n', char(shortPath), reason);
        end
    end
    fprintf('-----------------------------------------\n');

    % --- 1. COMPUTE AVERAGES (DO NOT PLOT YET) ---
    [avgBase, tBase, lblBase, countBase] = computeGroupAverage(baseFiles, 'SOLID_Base');
    [avgCNO,  tCNO,  lblCNO,  countCNO]  = computeGroupAverage(cnoFiles,  'SOLID_CNO');

    % --- 2. DETERMINE GLOBAL COLOR SCALE ---
    if ~isempty(climOpt)
        globalClim = climOpt;
        fprintf('\nUsing Manual CSD CLim: ±%.2f\n', globalClim);
    else
        % Collect all values to find robust percentile across both groups
        vals = [];
        if ~isempty(avgBase), vals = [vals; abs(avgBase(:))]; end
        if ~isempty(avgCNO),  vals = [vals; abs(avgCNO(:))]; end
        
        vals = vals(isfinite(vals));
        if isempty(vals)
            globalClim = 1; 
        else
            globalClim = prctile(vals, 99.5) * 1.12; 
        end
        fprintf('\nAuto-calculated Global CSD CLim (shared): ±%.2f\n', globalClim);
    end

    % --- 3. SAVE & RENDER ---
    if ~isempty(avgBase)
        saveAndRender(avgBase, tBase, lblBase, 'SOLID_Base', outDir, globalClim, countBase);
    else
        fprintf('No valid Base files found to process.\n');
    end
    
    if ~isempty(avgCNO)
        saveAndRender(avgCNO, tCNO, lblCNO, 'SOLID_CNO', outDir, globalClim, countCNO);
    else
        fprintf('No valid CNO files found to process.\n');
    end
    
    fprintf('Done.\n');
end

function [grandAvg, tRelMs, chLabels, count] = computeGroupAverage(files, tag)
    grandAvg = [];
    tRelMs = [];
    chLabels = {};
    count = 0;
    
    if isempty(files)
        return;
    end
    
    fprintf('\nComputing Average for: %s\n', tag);
    sumMat = [];
    
    for i = 1:numel(files)
        fPath = fullfile(files(i).folder, files(i).name);
        
        % Short path for logging
        shortPath = string(fPath);
        if strlength(shortPath) > 60, shortPath = "..." + extractAfter(shortPath, strlength(shortPath)-60); end
        
        try
            T = readtable(fPath);
            if width(T) < 2
                fprintf('  [SKIP] %s (Insufficient columns)\n', shortPath);
                continue; 
            end
            
            dataCols = T{:, 2:end};
            currLabels = T.Channel;
            
            if isempty(sumMat)
                sumMat = zeros(size(dataCols));
                chLabels = currLabels;
                hdr = T.Properties.VariableNames(2:end);
                tRelMs = parseTimeHeaders(hdr);
                
                if isempty(tRelMs) || any(isnan(tRelMs))
                     warning('Time header parsing failed for %s', fPath);
                end
            else
                if ~isequal(size(sumMat), size(dataCols))
                    warning('Dimension mismatch: %s. Expected %dx%d, got %dx%d.', ...
                        shortPath, size(sumMat,1), size(sumMat,2), size(dataCols,1), size(dataCols,2));
                    continue;
                end
            end
            
            if any(isnan(dataCols(:))), dataCols(isnan(dataCols)) = 0; end
            
            sumMat = sumMat + dataCols;
            count = count + 1;
            fprintf('  [ OK ] Included: %s\n', shortPath);
            
        catch ME
            warning('Error reading %s: %s', shortPath, ME.message);
        end
    end
    
    if count > 0
        grandAvg = sumMat / count;
        fprintf('  -> Computed average from %d animals.\n', count);
    end
end

function saveAndRender(grandAvg, tRelMs, chLabels, tag, outDir, clim, count)
    fprintf('\nSaving & Rendering: %s\n', tag);

    % Save Results (Filenames prefixed with CSD_)
    outCSV = fullfile(outDir, sprintf('CSD_GrandAvg_%s.csv', tag));
    outPng = fullfile(outDir, sprintf('CSD_GrandAvg_%s.png', tag));
    outPdf = fullfile(outDir, sprintf('CSD_GrandAvg_%s.pdf', tag));
    
    % Write CSV
    try
        T_rows = table(chLabels, 'VariableNames', {'Channel'});
        tHeaders = arrayfun(@(t) sprintf('T_%.2fms', t), tRelMs, 'UniformOutput', false);
        tHeaders = strrep(tHeaders, '.', 'p');
        tHeaders = strrep(tHeaders, '-', 'm');
        T_vals = array2table(grandAvg, 'VariableNames', tHeaders);
        writetable([T_rows, T_vals], outCSV);
        fprintf('  Saved CSV: %s\n', outCSV);
    catch ME
        warning('Failed to write CSV: %s', ME.message);
    end
    
    % Render
    renderGrandAvg(grandAvg, tRelMs, chLabels, tag, outPng, outPdf, clim, count);
end

% ======================================================================
%                             HELPERS
% ======================================================================
function tVals = parseTimeHeaders(headers)
    tVals = zeros(1, numel(headers));
    for i = 1:numel(headers)
        h = headers{i};
        h = strrep(h, 'T_', '');
        h = strrep(h, 'ms', '');
        h = strrep(h, 'minus', '-');
        if startsWith(h, 'm'), h(1) = '-'; end
        h = strrep(h, 'p', '.');
        h = strrep(h, '_', '.');
        
        val = str2double(h);
        if isnan(val)
             h_clean = regexprep(h, '[^0-9\.\-]', '');
             val = str2double(h_clean);
        end
        if isnan(val), val = 0; end
        tVals(i) = val;
    end
end

function renderGrandAvg(MU, tRelMs, chLabels, tag, outPng, outPdf, clim, nCount)
    nCh = size(MU, 1);
    perRowPx = 12; basePx = 260; maxPx = 2600;
    figH = min(maxPx, basePx + perRowPx * nCh);
    
    f = figure('Color','w','Position',[100 100 1100 figH], 'Visible', 'off');
    
    % PDF Layout Control
    set(f, 'Units', 'inches');
    figPos = get(f, 'Position');
    set(f, 'PaperUnits', 'inches', 'PaperSize', [figPos(3) figPos(4)], 'PaperPosition', [0 0 figPos(3) figPos(4)]);
    
    imagesc(tRelMs, 1:nCh, MU);
    set(gca, 'YDir', 'reverse'); 
    caxis([-clim, +clim]);
    colormap(jet); 
    cb = colorbar;
    cb.Label.String = 'CSD (a.u.)'; % Label changed for CSD
    
    xlabel('Time (ms)');
    set(gca, 'YTick', 1:nCh, 'YTickLabel', chLabels, 'FontSize', 9, 'TickLabelInterpreter', 'none');
    title(sprintf('CSD Grand Avg %s (N=%d)', tag, nCount), 'FontSize', 12, 'FontWeight', 'bold', 'Interpreter', 'none');
    
    exportgraphics(f, outPng, 'Resolution', 220);
    try
        print(f, outPdf, '-dpdf', '-painters');
    catch
        % simple fallback
    end
    fprintf('  Saved Plot: %s\n', outPng);
    close(f);
end