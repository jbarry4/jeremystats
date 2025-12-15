function VoltageRaster_GrandAverage_Spatial_Norm(rootFolder, varargin)
% VoltageRaster_GrandAverage_Spatial_Norm
% Performs SPATIAL NORMALIZATION based on a "Golden Template" before averaging.
%
% UPDATE: DYNAMIC GLOBAL QC SCALING + GROUP TITLES
% - Pass 1: Loads and warps all data into memory.
% - Calculation: Determines a single robust color limit across ALL sessions.
% - Pass 2: Renders QC plots with "Base" or "CNO" in the title.
%
% Usage:
%   VoltageRaster_GrandAverage_Spatial_Norm(rootFolder)
%   VoltageRaster_GrandAverage_Spatial_Norm(..., 'climMicroV', 150)

    p = inputParser;
    p.addRequired('rootFolder', @(s) ischar(s) || isstring(s));
    p.addParameter('climMicroV', [], @(x) isempty(x) || (isscalar(x) && x > 0));
    p.parse(rootFolder, varargin{:});
    
    rootFolder = char(p.Results.rootFolder);
    climOpt    = p.Results.climMicroV;
    
    % Output Directories
    outDir = fullfile(rootFolder, 'Voltage_GrandAverage_Spatial_Norm_Output');
    qcDir  = fullfile(outDir, 'Individual_Session_QC');
    
    if ~exist(outDir, 'dir'), mkdir(outDir); end
    if ~exist(qcDir, 'dir'),  mkdir(qcDir);  end
    
    fprintf('\n======================================================\n');
    fprintf('   SPATIAL NORMALIZATION & GRAND AVERAGE (DYNAMIC GLOBAL)\n');
    fprintf('======================================================\n');
    fprintf('Output: %s\n', outDir);
    
    % --- 1. Load Metadata ---
    
    % A. Group Info
    groupFile = fullfile(rootFolder, 'Mice_group.csv');
    if ~isfile(groupFile), error('Missing Mice_group.csv'); end
    fprintf('Loading group info from: %s\n', groupFile);
    T_grp = readtable(groupFile);
    
    grpCols = lower(T_grp.Properties.VariableNames);
    idxGrp = find(strcmp(grpCols, 'group'), 1);
    idxSession = find(strcmp(grpCols, 'session'), 1);
    idxLabeled = find(strcmp(grpCols, 'labeled'), 1);
    
    groups = T_grp{:, idxGrp};
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
    
    validBase = sessions(strcmpi(groups, 'base') & labeledMask);
    validCNO  = sessions(strcmpi(groups, 'cno')  & labeledMask);
    
    validBaseClean = cellfun(@(x) sanitizeSessionID(char(x)), validBase, 'UniformOutput', false);
    validCNOClean  = cellfun(@(x) sanitizeSessionID(char(x)), validCNO,  'UniformOutput', false);
    
    fprintf('  -> Targets: %d Base, %d CNO sessions defined.\n', numel(validBase), numel(validCNO));

    % B. Golden Template
    goldFile = fullfile(rootFolder, 'Golden_Template_Full_Probe.xlsx');
    if ~isfile(goldFile), error('Missing Golden_Template_Full_Probe.xlsx'); end
    try
        T_gold = readtable(goldFile, 'Sheet', 'Golden_Template');
    catch
        T_gold = readtable(goldFile, 'Sheet', 1);
    end
    fprintf('Loaded Golden Template (%d regions).\n', height(T_gold));
    
    % C. Detailed Channel Maps
    mapFile = fullfile(rootFolder, 'Final_Matched_and_Collapsed_Stats.xlsx');
    if ~isfile(mapFile), error('Missing Final_Matched_and_Collapsed_Stats.xlsx'); end
    try
        T_map_raw = readtable(mapFile, 'Sheet', 'Merged_Detailed_Data');
    catch
        T_map_raw = readtable(mapFile, 'Sheet', 1);
    end
    fprintf('Loaded Channel Maps (%d rows). Indexing...\n', height(T_map_raw));
    
    SessionMap = indexSessionMaps(T_map_raw);

    % --- 2. File Discovery & Classification ---
    fileName = 'VoltageRaster_Avg_Values_SOLID.csv';
    fprintf('\nSearching for "%s"...\n', fileName);
    allFiles = dir(fullfile(rootFolder, '**', fileName));
    allFiles = allFiles(~contains({allFiles.folder}, 'Voltage_GrandAverage_Spatial_Norm_Output'));
    
    if isempty(allFiles)
        fprintf('No data files found.\n'); return;
    end
    
    baseFiles = {}; baseIDs = {};
    cnoFiles  = {}; cnoIDs  = {};
    
    fprintf('\n--- CLASSIFYING FILES ---\n');
    for i = 1:numel(allFiles)
        fPathFull  = fullfile(allFiles(i).folder, allFiles(i).name);
        
        pat = 'm\d+s\d+'; 
        match = regexp(fPathFull, pat, 'match');
        if isempty(match), continue; end
        rawID = match{end};
        cleanID = sanitizeSessionID(rawID);
        
        isBase = ismember(cleanID, validBaseClean);
        isCNO  = ismember(cleanID, validCNOClean);
        
        if isBase
            baseFiles{end+1} = fPathFull; %#ok<AGROW>
            baseIDs{end+1}   = cleanID;   %#ok<AGROW>
            fprintf('  [BASE] %s (ID: %s)\n', allFiles(i).name, cleanID);
        elseif isCNO
            cnoFiles{end+1} = fPathFull; %#ok<AGROW>
            cnoIDs{end+1}   = cleanID;   %#ok<AGROW>
            fprintf('  [CNO ] %s (ID: %s)\n', allFiles(i).name, cleanID);
        end
    end

    % --- 3. Compute & Store (Pass 1) ---
    % Instead of plotting immediately, we store everything in struct arrays.
    
    fprintf('\n--- LOADING BASELINE DATA ---\n');
    [avgBase, tBase, DataBase] = processGroupData(baseFiles, baseIDs, T_gold, SessionMap);
    
    fprintf('\n--- LOADING CNO DATA ---\n');
    [avgCNO, tCNO, DataCNO] = processGroupData(cnoFiles, cnoIDs, T_gold, SessionMap);
    
    % --- 4. Determine Global Dynamic Scale ---
    if ~isempty(climOpt)
        globalClim = climOpt;
        fprintf('\n[SCALE] Using Manual CLim: %.2f uV\n', globalClim);
    else
        % Collect representative values from ALL sessions (Robust Percentile)
        vals = [];
        % Sample from Base
        for i=1:numel(DataBase)
            if ~isempty(DataBase(i).mat), vals = [vals; abs(DataBase(i).mat(:))]; end %#ok<AGROW>
        end
        % Sample from CNO
        for i=1:numel(DataCNO)
            if ~isempty(DataCNO(i).mat), vals = [vals; abs(DataCNO(i).mat(:))]; end %#ok<AGROW>
        end
        
        vals = vals(isfinite(vals));
        if isempty(vals)
            globalClim = 100; 
        else
            % 99.5th percentile of the entire dataset + 10% headroom
            globalClim = prctile(vals, 99.5) * 1.1; 
        end
        fprintf('\n[SCALE] Auto Dynamic Global CLim: %.2f uV (Calculated from %d data points)\n', globalClim, numel(vals));
    end
    
    % --- 5. Render QC Plots (Pass 2) ---
    fprintf('\n--- GENERATING QC PLOTS (Fixed Scale) ---\n');
    % --- UPDATE: Passing group label to renderQCSet ---
    renderQCSet(DataBase, T_gold, qcDir, globalClim, 'Base');
    renderQCSet(DataCNO,  T_gold, qcDir, globalClim, 'CNO');
    
    % --- 6. Render Grand Averages ---
    if ~isempty(avgBase)
        saveAndRender(avgBase, tBase, T_gold, 'SOLID_Base', outDir, globalClim, numel(DataBase));
    end
    if ~isempty(avgCNO)
        saveAndRender(avgCNO, tCNO, T_gold, 'SOLID_CNO', outDir, globalClim, numel(DataCNO));
    end
    
    fprintf('Done.\n');
end

% ======================================================================
%                        CORE LOGIC
% ======================================================================

function cleanID = sanitizeSessionID(rawID)
    if isempty(rawID), cleanID = ''; return; end
    str = lower(string(rawID));
    match = regexp(str, 'm\d+s\d+', 'match', 'once');
    if ~isempty(match), cleanID = char(match); else, cleanID = char(strtrim(str)); end
end

function [grandAvg, tRelMs, DataStruct] = processGroupData(fileList, idList, T_gold, SessionMap)
    grandAvg = [];
    tRelMs = [];
    
    % Initialize Data Struct Array
    DataStruct = struct('id', {}, 'mat', {}, 't', {});
    
    if isempty(fileList), return; end
    
    accumMatrix = []; 
    
    for i = 1:numel(fileList)
        fPath = fileList{i};
        sessionID = idList{i};
        
        fprintf('  Processing %s...', sessionID);
        
        try
            T_raw = readtable(fPath);
            if width(T_raw) < 2
                fprintf(' SKIPPED (Bad CSV width)\n');
                continue;
            end
            dataCols = T_raw{:, 2:end}; 
            
            if isempty(tRelMs)
                hdr = T_raw.Properties.VariableNames(2:end);
                tRelMs = parseTimeHeaders(hdr);
            end
            
            % --- SMART SCALING LOGIC ---
            nMatrixRows = size(dataCols, 1);
            ScaleFactor = nMatrixRows / 64.0; 
            
            if abs(ScaleFactor - 1.0) > 0.01
                fprintf(' [Scaled %.2fx] ', ScaleFactor);
            end
            
            % Normalize (Warp)
            warpedMat = warpMouseToTemplate(dataCols, sessionID, SessionMap, T_gold, ScaleFactor);
            
            if isempty(warpedMat) || all(isnan(warpedMat(:)))
                 fprintf(' WARN: Result is all NaN (Map Missing?)\n');
            else
                 fprintf(' OK\n');
            end
            
            % Store Individual Data
            DataStruct(end+1).id  = sessionID; %#ok<AGROW>
            DataStruct(end).mat   = warpedMat;
            DataStruct(end).t     = tRelMs;
            
            % Accumulate for Grand Avg
            if isempty(accumMatrix)
                accumMatrix = warpedMat;
            else
                accumMatrix = cat(3, accumMatrix, warpedMat);
            end
            
        catch ME
            fprintf(' FAIL: %s\n', ME.message);
        end
    end
    
    if ~isempty(accumMatrix)
        grandAvg = mean(accumMatrix, 3, 'omitnan');
    end
end

function warped = warpMouseToTemplate(rawMat, sessionID, SessionMap, T_gold, ScaleFactor)
    warped = [];
    
    if ~isKey(SessionMap, sessionID)
        totalH = sum(T_gold.Target_Thickness);
        warped = nan(totalH, size(rawMat,2));
        return;
    end
    
    myRegions = SessionMap(sessionID); 
    regions = T_gold.Region;
    targets = T_gold.Target_Thickness;
    maxRow  = size(rawMat, 1);
    
    for k = 1:length(regions)
        regName = char(regions{k});
        tH = targets(k);
        if tH <= 0, continue; end 
        
        chunk = [];
        
        % --- FETCH CHUNK (With Scaling) ---
        if strcmpi(regName, 'ABOVE CA1 SLM')
            if isKey(myRegions, 'CA1 SLM')
                ca1_range = myRegions('CA1 SLM');
                ana_end = ca1_range(1) - 1;
                mat_start = 1;
                mat_end   = floor(ana_end * ScaleFactor);
                if mat_end >= mat_start, chunk = rawMat(mat_start:mat_end, :); end
            end
            
        elseif strcmpi(regName, 'BELOW DG OML2')
            if isKey(myRegions, 'DG OML2')
                oml_range = myRegions('DG OML2');
                ana_start = oml_range(2) + 1;
                mat_start = ceil(ana_start * ScaleFactor);
                mat_end   = maxRow;
                if mat_start <= mat_end, chunk = rawMat(mat_start:mat_end, :); end
            end
            
        else
            if isKey(myRegions, regName)
                range = myRegions(regName);
                sAna = range(1); eAna = range(2);
                sR = ceil(sAna * ScaleFactor);
                eR = ceil(eAna * ScaleFactor);
                sR = max(1, sR); eR = min(maxRow, eR);
                if eR >= sR, chunk = rawMat(sR:eR, :); end
            end
        end
        
        % --- RESIZE ---
        if isempty(chunk)
            warpedChunk = nan(tH, size(rawMat,2));
        else
            [h, ~] = size(chunk);
            if h == tH
                warpedChunk = chunk;
            else
                x = 1:h;
                if h == 1
                    warpedChunk = repmat(chunk, tH, 1);
                else
                    xq = linspace(1, h, tH)';
                    warpedChunk = interp1(x, chunk, xq, 'linear');
                end
            end
        end
        warped = [warped; warpedChunk]; %#ok<AGROW>
    end
end

function renderQCSet(DataStruct, T_gold, qcDir, clim, groupName)
    for i = 1:numel(DataStruct)
        sessionID = DataStruct(i).id;
        mat = DataStruct(i).mat;
        t   = DataStruct(i).t;
        
        if isempty(mat), continue; end
        
        nCh = size(mat, 1);
        f = figure('Color','w','Visible','off','Position',[0 0 800 1200]);
        imagesc(t, 1:nCh, mat);
        set(gca, 'YDir', 'reverse');
        caxis([-clim, +clim]);
        colormap(jet); colorbar;
        
        % --- UPDATE: Title includes Group Name ---
        title(sprintf('QC [%s]: %s (Dynamic Global CLim=%.0f)', groupName, sessionID, clim), 'Interpreter', 'none');
        
        hold on; yCursor = 0.5;
        for k = 1:height(T_gold)
            th = T_gold.Target_Thickness(k);
            rName = char(T_gold.Region{k});
            yLine = yCursor + th;
            yline(yLine, 'k-', 'LineWidth', 0.5);
            text(min(t)+2, yCursor + th/2, rName, 'FontSize', 6, 'Interpreter','none', 'Color', 'k', 'BackgroundColor', 'w');
            yCursor = yCursor + th;
        end
        
        % Filename includes group so they don't overwrite if IDs duplicate (unlikely but safe)
        outName = fullfile(qcDir, sprintf('QC_%s_%s.png', groupName, sessionID));
        exportgraphics(f, outName, 'Resolution', 150);
        close(f);
    end
end

% ======================================================================
%                        HELPER UTILITIES
% ======================================================================

function SessionMap = indexSessionMaps(T_detailed)
    SessionMap = containers.Map;
    sessions = unique(T_detailed.Session_ID);
    for i = 1:length(sessions)
        rawID = char(sessions{i});
        cleanID = sanitizeSessionID(rawID);
        idx = strcmp(T_detailed.Session_ID, rawID);
        subT = T_detailed(idx, :);
        RegMap = containers.Map;
        regions = unique(subT.Region);
        for r = 1:length(regions)
            rName = char(regions{r});
            rIdx = strcmp(subT.Region, rName);
            chans = subT.Channel(rIdx);
            if ~isempty(chans), RegMap(rName) = [min(chans), max(chans)]; end
        end
        SessionMap(cleanID) = RegMap;
    end
end

function saveAndRender(grandAvg, tRelMs, T_gold, tag, outDir, clim, count)
    outCSV = fullfile(outDir, sprintf('GrandAvg_%s.csv', tag));
    outPng = fullfile(outDir, sprintf('GrandAvg_%s.png', tag));
    outPdf = fullfile(outDir, sprintf('GrandAvg_%s.pdf', tag));
    
    try
        T_out = array2table(grandAvg);
        writetable(T_out, outCSV);
        fprintf('Saved CSV: %s\n', outCSV);
    catch
    end
    
    nCh = size(grandAvg, 1);
    f = figure('Color','w','Visible','off','Position',[100 100 1200 800]);
    set(f, 'Units', 'inches');
    figPos = get(f, 'Position');
    set(f, 'PaperUnits', 'inches', 'PaperSize', [figPos(3) figPos(4)], 'PaperPosition', [0 0 figPos(3) figPos(4)]);

    imagesc(tRelMs, 1:nCh, grandAvg);
    set(gca, 'YDir', 'reverse');
    caxis([-clim, +clim]);
    colormap(jet);
    cb = colorbar;
    cb.Label.String = 'Voltage (uV)';
    
    xlabel('Time (ms)');
    title(sprintf('Spatially Normalized Grand Avg %s (N=%d)', tag, count), 'Interpreter', 'none');
    
    hold on; yCursor = 0.5; yticks = []; ylabels = {};
    for i = 1:height(T_gold)
        th = T_gold.Target_Thickness(i);
        rName = char(T_gold.Region{i});
        yticks(end+1) = yCursor + th/2; %#ok<AGROW>
        ylabels{end+1} = rName; %#ok<AGROW>
        yLine = yCursor + th;
        yline(yLine, 'k-', 'LineWidth', 1);
        yCursor = yCursor + th;
    end
    
    set(gca, 'YTick', yticks, 'YTickLabel', ylabels, 'FontSize', 8, 'TickLabelInterpreter', 'none');
    exportgraphics(f, outPng, 'Resolution', 220);
    try print(f, outPdf, '-dpdf', '-painters'); catch, end
    close(f);
    fprintf('Saved Plot: %s\n', outPng);
end

function tVals = parseTimeHeaders(headers)
    tVals = zeros(1, numel(headers));
    for i = 1:numel(headers)
        h = headers{i};
        h = strrep(h, 'T_', ''); h = strrep(h, 'ms', '');
        h = strrep(h, 'minus', '-'); h = strrep(h, 'm', '-');
        h = strrep(h, 'p', '.'); h = strrep(h, '_', '.');
        val = str2double(regexprep(h, '[^0-9\.\-]', ''));
        if isnan(val), val = 0; end
        tVals(i) = val;
    end
end