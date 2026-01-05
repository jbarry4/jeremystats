function CSDRaster_GrandAverage_Spatial_Norm(rootFolder, varargin)
% CSDRaster_GrandAverage_Spatial_Norm
% Performs SPATIAL NORMALIZATION on CSD data based on a "Golden Template".
% 
% PUBLICATION READY VERSION:
%   - Grand Avg Probe Limit requires 100% consensus across subjects.
%   - Grand Avg plots cropped to CA1 SLM -> DG OML2.
%   - QC Plots default to cropped (controlled by includeQCFigurePadding).
%   - QC Plots now output PDF versions in addition to PNG.
%   - Status 1: "Probe Depth Limit" (Red).
%   - Status 2: "CSD Padding" (Purple).
%   - Outputs: CSV, PNG, and PDF.
%
% Usage:
%   CSDRaster_GrandAverage_Spatial_Norm(rootFolder)
%   CSDRaster_GrandAverage_Spatial_Norm(..., 'climCSD', 500, 'includeQCFigurePadding', true)

    p = inputParser;
    p.addRequired('rootFolder', @(s) ischar(s) || isstring(s));
    p.addParameter('climCSD', [], @(x) isempty(x) || (isscalar(x) && x > 0));
    p.addParameter('includeQCFigurePadding', false, @islogical); % Default false
    p.parse(rootFolder, varargin{:});
    
    rootFolder     = char(p.Results.rootFolder);
    climOpt        = p.Results.climCSD;
    includePadding = p.Results.includeQCFigurePadding;
    
    % Output Directories
    outDir = fullfile(rootFolder, 'CSD_GrandAverage_Spatial_Norm_Output');
    qcDir  = fullfile(outDir, 'Individual_Session_QC');
    
    if ~exist(outDir, 'dir'), mkdir(outDir); end
    if ~exist(qcDir, 'dir'),  mkdir(qcDir);  end
    
    fprintf('\n======================================================\n');
    fprintf('   CSD SPATIAL NORMALIZATION & GRAND AVERAGE\n');
    fprintf('   (Publication Ready: 100%% Limit Rule, PDF Output)\n');
    fprintf('======================================================\n');
    fprintf('QC Padding Included: %s\n', string(includePadding));
    
    % --- 1. Load Metadata ---
    groupFile = fullfile(rootFolder, 'Mice_group.csv');
    if ~isfile(groupFile), error('Missing Mice_group.csv'); end
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
    
    % B. Golden Template
    goldFile = fullfile(rootFolder, 'Golden_Template_Full_Probe.xlsx');
    if ~isfile(goldFile), error('Missing Golden_Template_Full_Probe.xlsx'); end
    try
        T_gold = readtable(goldFile, 'Sheet', 'Golden_Template');
    catch
        T_gold = readtable(goldFile, 'Sheet', 1);
    end
    
    % C. Detailed Channel Maps
    mapFile = fullfile(rootFolder, 'Final_Matched_and_Collapsed_Stats.xlsx');
    if ~isfile(mapFile), error('Missing Final_Matched_and_Collapsed_Stats.xlsx'); end
    try
        T_map_raw = readtable(mapFile, 'Sheet', 'Merged_Detailed_Data');
    catch
        T_map_raw = readtable(mapFile, 'Sheet', 1);
    end
    
    SessionMap = indexSessionMaps(T_map_raw);
    
    % --- 2. File Discovery ---
    fileName = 'CSD_Raster_Avg_Values_SOLID.csv';
    allFiles = dir(fullfile(rootFolder, '**', fileName));
    allFiles = allFiles(~contains({allFiles.folder}, 'CSD_GrandAverage_Spatial_Norm_Output'));
    
    if isempty(allFiles), fprintf('No data files found.\n'); return; end
    
    baseFiles = {}; baseIDs = {};
    cnoFiles  = {}; cnoIDs  = {};
    
    for i = 1:numel(allFiles)
        fPathFull  = fullfile(allFiles(i).folder, allFiles(i).name);
        match = regexp(fPathFull, 'm\d+s\d+', 'match');
        if isempty(match), continue; end
        cleanID = sanitizeSessionID(match{end}); 
        
        if ismember(cleanID, validBaseClean)
            baseFiles{end+1} = fPathFull; baseIDs{end+1} = cleanID; %#ok<AGROW>
        elseif ismember(cleanID, validCNOClean)
            cnoFiles{end+1} = fPathFull; cnoIDs{end+1} = cleanID; %#ok<AGROW>
        end
    end
    
    % --- 3. Compute (Pass 1) ---
    fprintf('Loading Base...\n');
    [avgBase, tBase, DataBase, statusBase] = processGroupData(baseFiles, baseIDs, T_gold, SessionMap);
    
    fprintf('Loading CNO...\n');
    [avgCNO, tCNO, DataCNO, statusCNO] = processGroupData(cnoFiles, cnoIDs, T_gold, SessionMap);
    
    % --- 4. Scale ---
    if ~isempty(climOpt)
        globalClim = climOpt;
    else
        vals = [];
        for i=1:numel(DataBase), if ~isempty(DataBase(i).mat), vals = [vals; abs(DataBase(i).mat(:))]; end, end
        for i=1:numel(DataCNO), if ~isempty(DataCNO(i).mat), vals = [vals; abs(DataCNO(i).mat(:))]; end, end
        vals = vals(isfinite(vals));
        if isempty(vals), globalClim = 200; else, globalClim = prctile(vals, 99.5) * 1.1; end
    end
    fprintf('Global Scale: %.2f\n', globalClim);
    
    % --- 5. Render QC (Controlled by Padding Flag) ---
    renderQCSet(DataBase, T_gold, qcDir, globalClim, 'Base', includePadding);
    renderQCSet(DataCNO,  T_gold, qcDir, globalClim, 'CNO', includePadding);
    
    % --- 6. Render Grand Averages (Cropped) ---
    if ~isempty(avgBase)
        saveAndRenderGrandAvg(avgBase, tBase, T_gold, 'SOLID_Base', outDir, globalClim, numel(DataBase), statusBase);
    end
    if ~isempty(avgCNO)
        saveAndRenderGrandAvg(avgCNO, tCNO, T_gold, 'SOLID_CNO', outDir, globalClim, numel(DataCNO), statusCNO);
    end
    fprintf('Done.\n');
end
% ======================================================================
%                        CORE LOGIC
% ======================================================================
function [grandAvg, tRelMs, DataStruct, grandStatus] = processGroupData(fileList, idList, T_gold, SessionMap)
    grandAvg = []; tRelMs = []; grandStatus = [];
    DataStruct = struct('id', {}, 'mat', {}, 't', {}, 'status', {});
    
    if isempty(fileList), return; end
    
    accumMatrix = []; accumStatus = [];
    InputChannels = 2:2:64; 
    
    for i = 1:numel(fileList)
        fPath = fileList{i};
        sessionID = idList{i};
        try
            T_raw = readtable(fPath);
            if width(T_raw) < 2, continue; end
            dataCols = T_raw{:, 2:end}; 
            
            if size(dataCols, 1) ~= length(InputChannels), continue; end
            if isempty(tRelMs)
                hdr = T_raw.Properties.VariableNames(2:end);
                tRelMs = parseTimeHeaders(hdr);
            end
            
            % Warp to template
            [warpedMat, statusMat] = warpMouseToTemplate(dataCols, sessionID, SessionMap, T_gold, InputChannels);
            
            % Interpolate over CSD artifacts
            warpedMat = fillCSDGaps(warpedMat, statusMat);
            
            DataStruct(end+1).id     = sessionID; %#ok<AGROW>
            DataStruct(end).mat      = warpedMat;
            DataStruct(end).t        = tRelMs;
            DataStruct(end).status   = statusMat;
            
            if isempty(accumMatrix)
                accumMatrix = warpedMat;
                accumStatus = statusMat;
            else
                accumMatrix = cat(3, accumMatrix, warpedMat);
                accumStatus = cat(3, accumStatus, statusMat);
            end
        catch, end
    end
    
    if ~isempty(accumMatrix)
        grandAvg = mean(accumMatrix, 3, 'omitnan');
        
        % --- PUBLICATION VOTING: 100% Rule for Probe Limit ---
        [rows, cols, nMice] = size(accumStatus);
        grandStatus = zeros(rows, cols);
        
        for r = 1:rows
            for c = 1:cols
                votes = squeeze(accumStatus(r,c,:));
                
                % Count Probe Limit (1)
                countLimit = sum(votes == 1);
                
                % RULE: Strict 100% for Probe Depth Limit
                if countLimit == nMice
                    grandStatus(r,c) = 1; % Probe Depth Limit wins (Red)
                else
                    % If even one mouse has data (0 or 2), we use data.
                    % If any vote is 0 (valid data), the pixel is 0.
                    % If no votes are 0, but some are 2 (padded), pixel is 2.
                    if any(votes == 0)
                        grandStatus(r,c) = 0; % Valid Data
                    else
                        grandStatus(r,c) = 2; % CSD Padding (Purple)
                    end
                end
            end
        end
        
        % Apply final fill based on the new consensus
        grandAvg = fillCSDGaps(grandAvg, grandStatus);
    end
end
function filledMat = fillCSDGaps(mat, status)
    % Stretches data over regions marked as Status 2
    filledMat = mat;
    
    % 1. Fill all NaNs vertically
    matFilled = fillmissing(mat, 'linear', 1, 'EndValues', 'none'); 
    if any(isnan(matFilled(:)))
         matFilled = fillmissing(matFilled, 'nearest', 1);
    end
    % 2. Fill where Status is 2 (CSD Padding)
    maskCSD = (status == 2);
    
    % 3. Enforce NaNs where Status is 1 (Probe Depth Limit)
    maskLimit = (status == 1);
    
    filledMat(maskCSD) = matFilled(maskCSD);
    filledMat(maskLimit) = NaN; 
end
function [warped, statusMat] = warpMouseToTemplate(rawMat, sessionID, SessionMap, T_gold, InputChannels)
    warped = []; statusMat = [];
    totalH = sum(T_gold.Target_Thickness);
    
    if ~isKey(SessionMap, sessionID)
        warped = nan(totalH, size(rawMat,2));
        statusMat = ones(size(warped)); 
        return;
    end
    
    myRegions = SessionMap(sessionID); 
    regions = T_gold.Region;
    targets = T_gold.Target_Thickness;
    
    for k = 1:length(regions)
        regName = char(regions{k});
        tH = targets(k);
        if tH <= 0, continue; end 
        
        chunk = []; physStart = nan; physEnd = nan;
        isMissingRegion = false;
        
        if strcmpi(regName, 'ABOVE CA1 SLM')
            if isKey(myRegions, 'CA1 SLM')
                ca1_range = myRegions('CA1 SLM');
                physEnd = ca1_range(1) - 1; physStart = -inf; 
            end
        elseif strcmpi(regName, 'BELOW DG OML2')
            if isKey(myRegions, 'DG OML2')
                oml_range = myRegions('DG OML2');
                physStart = oml_range(2) + 1; physEnd = inf;
            end
        else
            if isKey(myRegions, regName)
                range = myRegions(regName);
                physStart = range(1); physEnd = range(2);
            else
                isMissingRegion = true;
            end
        end
        
        if ~isnan(physStart)
            validRowIndices = find(InputChannels >= physStart & InputChannels <= physEnd);
            if ~isempty(validRowIndices), chunk = rawMat(validRowIndices, :); end
        end
        
        warpedChunk = nan(tH, size(rawMat,2));
        statusChunk = zeros(tH, size(rawMat,2));
        
        if isMissingRegion || (isempty(chunk) && ~isnan(physStart) && isempty(validRowIndices))
            statusChunk(:) = 1; 
        else
            [h, ~] = size(chunk);
            if h == 0
                 statusChunk(:) = 1;
            else
                if h == tH, warpedChunk = chunk;
                else
                    x = 1:h;
                    if h == 1, warpedChunk = repmat(chunk, tH, 1);
                    else, xq = linspace(1, h, tH)'; warpedChunk = interp1(x, chunk, xq, 'linear'); end
                end
                
                maskNaN = isnan(warpedChunk);
                statusChunk(maskNaN) = 2; 
            end
        end
        
        warped = [warped; warpedChunk]; %#ok<AGROW>
        statusMat = [statusMat; statusChunk]; %#ok<AGROW>
    end
end
function cleanID = sanitizeSessionID(rawID)
    if isempty(rawID), cleanID = ''; return; end
    str = lower(string(rawID));
    match = regexp(str, 'm\d+s\d+', 'match', 'once');
    if ~isempty(match), cleanID = char(match); else, cleanID = char(strtrim(str)); end
end
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
% ======================================================================
%                        RENDERING
% ======================================================================
function renderQCSet(DataStruct, T_gold, qcDir, clim, groupName, includePadding)
    % Prepare cropping indices
    rowsToKeep = [];
    subsetRegions = {};
    subsetThickness = [];
    
    currentStart = 1;
    for k = 1:height(T_gold)
        th = T_gold.Target_Thickness(k);
        rName = char(T_gold.Region{k});
        
        isBuffer = contains(upper(rName), 'ABOVE') || contains(upper(rName), 'BELOW');
        
        % If padding is included OR it's not a buffer, we keep it
        if includePadding || ~isBuffer
            rowsToKeep = [rowsToKeep, currentStart:(currentStart+th-1)]; %#ok<AGROW>
            subsetRegions{end+1} = rName; %#ok<AGROW>
            subsetThickness(end+1) = th; %#ok<AGROW>
        end
        currentStart = currentStart + th;
    end
    
    if isempty(rowsToKeep)
        rowsToKeep = 1:sum(T_gold.Target_Thickness);
        subsetRegions = T_gold.Region;
        subsetThickness = T_gold.Target_Thickness;
    end

    for i = 1:numel(DataStruct)
        sessionID = DataStruct(i).id;
        mat = DataStruct(i).mat;
        t   = DataStruct(i).t;
        status = DataStruct(i).status;
        
        if isempty(mat), continue; end
        
        % CROP DATA & STATUS
        try
            matCropped = mat(rowsToKeep, :);
            statusCropped = status(rowsToKeep, :);
        catch
            matCropped = mat;
            statusCropped = status;
        end
        
        nCh = size(matCropped, 1);
        f = figure('Color','w','Visible','off','Position',[0 0 900 1200]);
        imagesc(t, 1:nCh, matCropped);
        set(gca, 'YDir', 'reverse');
        caxis([-clim, +clim]);
        colormap(jet); 
        
        % Colorbar setup
        cb = colorbar; 
        cb.Label.String = 'CSD (a.u.)';
        cb.Label.Rotation = 270;
        cb.Label.VerticalAlignment = 'bottom';
        
        title(sprintf('QC: %s', sessionID), 'Interpreter', 'none');
        xlabel('Time (ms)');
        
        hold on;
        yCursor = 0.5;
        
        % Draw lines using subset
        for k = 1:length(subsetRegions)
            th = subsetThickness(k);
            rName = subsetRegions{k};
            yLine = yCursor + th;
            yline(yLine, 'k-', 'LineWidth', 0.5);
            text(min(t)+2, yCursor + th/2, rName, 'FontSize', 6, 'Interpreter','none', 'Color', 'k', 'BackgroundColor', 'w');
            yCursor = yCursor + th;
        end
        
        % Overlay using cropped status
        drawRepeatingOverlay(matCropped, statusCropped, t);
        
        % Export PNG and PDF
        outPng = fullfile(qcDir, sprintf('QC_CSD_%s_%s.png', groupName, sessionID));
        outPdf = fullfile(qcDir, sprintf('QC_CSD_%s_%s.pdf', groupName, sessionID));
        
        exportgraphics(f, outPng, 'Resolution', 300);
        exportgraphics(f, outPdf, 'ContentType', 'vector');
        
        close(f);
    end
end
function saveAndRenderGrandAvg(grandAvg, tRelMs, T_gold, tag, outDir, clim, count, grandStatus)
    % CROPPING: Exclude 'ABOVE CA1 SLM' and 'BELOW DG OML2'
    
    % 1. Identify rows to keep
    rowsToKeep = [];
    regionsToKeep = {};
    thicknessToKeep = [];
    
    yCursor = 0.5;
    currentStartRow = 1;
    
    for i = 1:height(T_gold)
        rName = char(T_gold.Region{i});
        th = T_gold.Target_Thickness(i);
        
        % Check if this region is one of the buffers
        isBuffer = contains(upper(rName), 'ABOVE') || contains(upper(rName), 'BELOW');
        
        if ~isBuffer
            % Add indices to filter
            endRow = currentStartRow + th - 1;
            rowsToKeep = [rowsToKeep, currentStartRow:endRow]; %#ok<AGROW>
            regionsToKeep{end+1} = rName; %#ok<AGROW>
            thicknessToKeep(end+1) = th; %#ok<AGROW>
        end
        currentStartRow = currentStartRow + th;
    end
    
    if isempty(rowsToKeep)
        % Fallback if something matched wrong
        rowsToKeep = 1:size(grandAvg,1);
        regionsToKeep = T_gold.Region;
        thicknessToKeep = T_gold.Target_Thickness;
    end
    
    % 2. Crop Data and Status
    grandAvgCropped = grandAvg(rowsToKeep, :);
    grandStatusCropped = grandStatus(rowsToKeep, :);
    
    outCSV = fullfile(outDir, sprintf('CSD_GrandAvg_%s.csv', tag));
    outPng = fullfile(outDir, sprintf('CSD_GrandAvg_%s.png', tag));
    outPdf = fullfile(outDir, sprintf('CSD_GrandAvg_%s.pdf', tag));
    
    try writetable(array2table(grandAvgCropped), outCSV); catch, end
    
    nCh = size(grandAvgCropped, 1);
    f = figure('Color','w','Visible','off','Position',[100 100 1300 800]);
    
    imagesc(tRelMs, 1:nCh, grandAvgCropped);
    set(gca, 'YDir', 'reverse');
    caxis([-clim, +clim]);
    colormap(jet); 
    
    % Colorbar setup
    cb = colorbar; 
    cb.Label.String = 'CSD (a.u.)';
    cb.Label.Rotation = 270;
    cb.Label.VerticalAlignment = 'bottom';
    
    title(sprintf('Grand Avg %s (N=%d)', tag, count), 'Interpreter', 'none');
    xlabel('Time (ms)');
    
    hold on; 
    yCursor = 0.5; 
    yticks = []; 
    ylabels = {};
    
    % 3. Draw lines for kept regions
    for i = 1:length(regionsToKeep)
        th = thicknessToKeep(i);
        rName = regionsToKeep{i};
        yticks(end+1) = yCursor + th/2; %#ok<AGROW>
        ylabels{end+1} = rName; %#ok<AGROW>
        yline(yCursor + th, 'k-', 'LineWidth', 1);
        yCursor = yCursor + th;
    end
    
    set(gca, 'YTick', yticks, 'YTickLabel', ylabels, 'FontSize', 8, 'TickLabelInterpreter', 'none');
    
    drawRepeatingOverlay(grandAvgCropped, grandStatusCropped, tRelMs);
    
    exportgraphics(f, outPng, 'Resolution', 300);
    exportgraphics(f, outPdf, 'ContentType', 'vector');
    
    close(f);
end
function drawRepeatingOverlay(mat, statusMat, tVector)
% overlays colored boxes and repeating text based on status
% Status: 1 = PROBE LIMIT (RED), 2 = CSD PADDING (PURPLE)
    xMin = min(tVector);
    xMax = max(tVector);
    xWidth = xMax - xMin;
    
    if isempty(mat) || isempty(statusMat), return; end
    
    % Collapse statusMat to get dominant status per row
    % Use Mode, but filter for valid error codes
    rowModes = mode(statusMat, 2);
    rowModes(rowModes ~= 1 & rowModes ~= 2) = 0; 
    
    rowModes(end+1) = -1; % Sentinel
    
    startIdx = -1;
    currentType = -1;
    
    for r = 1:length(rowModes)
        thisType = rowModes(r);
        
        if startIdx == -1
            if thisType > 0
                startIdx = r;
                currentType = thisType;
            end
        else
            if thisType ~= currentType
                renderBox(startIdx, r-1, currentType, xMin, xMax, xWidth);
                if thisType > 0
                    startIdx = r;
                    currentType = thisType;
                else
                    startIdx = -1;
                    currentType = -1;
                end
            end
        end
    end
end
function renderBox(rStart, rEnd, typeCode, xMin, xMax, xWidth)
    if typeCode == 1
        % Probe Limit -> RED, Opaque-ish
        col = [1 0 0]; 
        txt = 'Probe Depth Limit';
        boxAlpha = 0.4;
        textColor = 'w';
    elseif typeCode == 2
        % CSD Padding -> PURPLE, VERY TRANSPARENT
        col = [0.5 0 0.5];
        txt = 'CSD Padding';
        boxAlpha = 0.15; 
        textColor = [1 1 1]; 
    else
        return; 
    end
    
    yTop = rStart - 0.5;
    yBot = rEnd + 0.5;
    
    patch([xMin, xMax, xMax, xMin], [yTop, yTop, yBot, yBot], ...
          col, 'FaceAlpha', boxAlpha, 'EdgeColor', 'none');
          
    xStep = xWidth / 4; % Fewer repetitions for longer text
    xGrid = xMin + xStep/2 : xStep : xMax;
    yGrid = rStart:2:rEnd;
    if isempty(yGrid), yGrid = (rStart+rEnd)/2; end 
    
    for xx = xGrid
        for yy = yGrid
            text(xx, yy, txt, ...
                'Color', textColor, ...
                'FontSize', 7, ...
                'FontWeight', 'bold', ...
                'HorizontalAlignment', 'center', ...
                'VerticalAlignment', 'middle');
        end
    end
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