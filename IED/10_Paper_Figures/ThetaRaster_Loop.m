function ThetaRaster_Loop(rootInputFolder)
% JB — ThetaRaster_Loop
% -------------------------------------------------------------------------
% 1. Takes a root folder input.
% 2. Recursively searches for ALL instances of '*theta.fig' (Wildcard added).
% 3. Loops through each found file and runs the ThetaRaster pipeline logic.
%    - Creates a UNIQUE output subfolder for each file based on its name.
%    - Prevents overwriting of x1.mat, pngs, etc.
% -------------------------------------------------------------------------
    fprintf('\n========================================\n');
    fprintf('   JB: ThetaRaster LOOP STARTED\n');
    fprintf('   Root: %s\n', rootInputFolder);
    fprintf('========================================\n');

    % 1. Recursively find all *theta.fig files
    %    UPDATED: Added wildcard '*' before theta.fig to catch all variants
    searchPattern = fullfile(rootInputFolder, '**', '*theta.fig');
    fileList = dir(searchPattern);
    
    if isempty(fileList)
        warning('No files ending in "theta.fig" found in: %s', rootInputFolder);
        return;
    end
    
    nFiles = length(fileList);
    fprintf('Found %d theta figure file(s). Processing...\n\n', nFiles);
    
    % 2. Loop through each file
    for k = 1:nFiles
        thisFile   = fileList(k);
        % Get the full path to the figure
        fullFigPath = fullfile(thisFile.folder, thisFile.name);
        % Pass the parent folder and the specific filename
        parentDir   = thisFile.folder;
        fileName    = thisFile.name;
        
        fprintf('--- File %d of %d: %s ---\n', k, nFiles, fileName);
        
        try
            % Call the processing logic for this specific file
            process_single_theta(parentDir, fileName);
        catch ME
            fprintf(2, '!!! ERROR processing %s:\n%s\n', fullFigPath, ME.message);
        end
        fprintf('\n');
    end
    
    fprintf('===== JB: ThetaRaster_Loop Complete =====\n');
end

function process_single_theta(inputFolder, fileName)
% Adapted logic to handle unique filenames and create unique output folders

    fullFigPath = fullfile(inputFolder, fileName);

    % Extract filename without extension to use as a unique folder name
    [~, fNameNoExt, ~] = fileparts(fileName);

    % ---------- Output directory ----------
    % CRITICAL FIX: Creates a subfolder specific to THIS figure name
    % Structure: inputFolder / Theta_Plots / CTL_m02s01_012324_BASE_theta / ...
    outputDir = fullfile(inputFolder, 'Theta_Plots', fNameNoExt);
    
    if ~exist(outputDir, 'dir')
        mkdir(outputDir);
    end
    
    fprintf('   Output Dir: %s\n', outputDir);
    fprintf('   Opening invisible fig...\n');
    
    % ---------- Open invisible + extract data ----------
    srcFig = openfig(fullFigPath, 'invisible');
    
    % Extract Data
    obj = findobj(srcFig, '-property', 'CData');
    if isempty(obj)
        close(srcFig);
        error('Could not find CData object in figure.');
    end
    c1  = obj(1).CData;
    
    obj = findobj(srcFig, '-property', 'XData');
    x1  = obj(1).XData;
    
    obj = findobj(srcFig, '-property', 'YData');
    y1  = obj(1).YData;
    
    % Ensure row vectors
    x1 = x1(:).';  
    y1 = y1(:).';
    
    close(srcFig);
    
    % ---------- Compute Means ----------
    c2 = c1;          Positive = c2 > 0;  c2(~Positive) = 0;
    MeanPositive = sum(c2, 2) ./ sum(Positive, 2);
    
    c3 = c1;          Negative = c3 < 0;  c3(~Negative) = 0;
    MeanNegative = sum(c3, 2) ./ sum(Negative, 2);
    
    % ---------- Save mats ----------
    save(fullfile(outputDir, 'x1.mat'), 'x1');
    save(fullfile(outputDir, 'y1.mat'), 'y1');
    save(fullfile(outputDir, 'c1.mat'), 'c1');
    save(fullfile(outputDir, 'MeanPositive.mat'), 'MeanPositive');
    save(fullfile(outputDir, 'MeanNegative.mat'), 'MeanNegative');
    
    % ---------- Render ----------
    % We can keep standard names here (Theta_Raster.png) because they are 
    % now safely inside their own unique folder.
    pngPath = fullfile(outputDir, 'Theta_Raster.png');
    pdfPath = fullfile(outputDir, 'Theta_Raster.pdf');
    
    renderThetaRaster(outputDir, x1, y1, c1, MeanNegative, pngPath, pdfPath);
    
    fprintf('   Done.\n');
end

% --- MODIFIED: Render Function (Kept exactly as requested) ---
function renderThetaRaster(~, xValues, yValues, cMatrix, MeanNegative, pngPath, pdfPath)
% JB — renderThetaRaster
% UI Fixes: 
% 1. "a.u." for units.
% 2. Double-newline padding in title to prevent overlap.
    
    fprintf('   JB: Rendering Theta heatmap...\n');
    
    % ---- Configuration ----
    gaussianSigma  = 0.75;
    upsampleFactor = 3;
    colormapName   = 'jet';
    colorScale     = [-0.2, 0.2];
    titleText      = 'Theta CSD Raster';
    titleSize      = 16; 
    
    % ---- Orientation Check ----
    expectedRows = numel(yValues);
    expectedCols = numel(xValues);
    if ~isequal(size(cMatrix), [expectedRows, expectedCols])
        if isequal(size(cMatrix), [expectedCols, expectedRows])
            cMatrix = cMatrix.';
        else
            error('JB: cMatrix dim mismatch.');
        end
    end
    
    % ---- Processing ----
    interior = imgaussfilt(cMatrix, gaussianSigma);
    if upsampleFactor > 1
        interior = imresize(interior, upsampleFactor, 'bicubic');
    end
    fullMatrix = interior; 
    
    channels = 1:63; 
    xExtent  = [xValues(1), xValues(end)];
    yExtent  = [channels(1), channels(end)];
    
    % ---- Figure Setup ----
    f = figure('Color','w','Position',[100 100 1200 800], 'Visible','off');
    
    set(f, 'Units', 'inches');
    figPos_inches = get(f, 'Position');
    set(f, 'PaperUnits', 'inches');
    set(f, 'PaperSize', [figPos_inches(3) figPos_inches(4)]);
    set(f, 'PaperPosition', [0 0 figPos_inches(3) figPos_inches(4)]);
    % Use 'loose' padding
    tl = tiledlayout(f, 1, 5, 'TileSpacing', 'compact', 'Padding', 'loose');
    
    % --- TILE 1 (Heatmap): Spans 4 columns ---
    ax1 = nexttile(tl, 1, [1 4]);
    
    imagesc(ax1, 'XData', xExtent, 'YData', yExtent, 'CData', fullMatrix);
    set(ax1, 'YDir', 'reverse');
    colormap(ax1, colormapName);
    caxis(ax1, colorScale);
    
    % Colorbar (Updated label)
    cb = colorbar(ax1); 
    cb.Label.String = 'CSD (a.u.)'; % Changed from CSD (units)
    
    % Labels & Title
    xlabel(ax1, 'Time (s)');
    ylabel(ax1, 'Channel #');
    
    % FIX: Double-newline padding to ensure no overlap
    title(ax1, {titleText, ' '}, 'FontSize', titleSize, 'FontWeight', 'bold');
    
    % Y-Ticks: Every channel
    yticks(ax1, 1:63);
    yticklabels(ax1, string(1:63));
    
    % Black Background + Thick Line (Gap Filler)
    set(ax1, 'FontSize', 8, 'TickDir', 'out', 'LineWidth', 2, 'Color', 'k');
    
    grid(ax1, 'on'); 
    box(ax1, 'on');
    
    xlim(ax1, xExtent);
    ylim(ax1, [0.5 63.5]); 
    axis(ax1, 'normal'); 
    
    % --- TILE 2 (Line Plot): Spans 1 column ---
    ax2 = nexttile(tl, 5, [1 1]);
    
    if numel(MeanNegative) == 63
        yAxis = 1:63;
        plot(ax2, MeanNegative, yAxis, 'b-', 'LineWidth', 1.5);
    else
        yAxis = 1:numel(MeanNegative);
        plot(ax2, MeanNegative, yAxis, 'b-', 'LineWidth', 1.5);
    end
    
    set(ax2, 'YDir', 'reverse');
    set(ax2, 'YTick', [], 'YTickLabel', []); 
    
    xlabel(ax2, 'CSD (a.u.)');
    
    % Padding for Title
    title(ax2, {'Mean Sink', ' '}, 'FontSize', titleSize, 'FontWeight', 'bold');
    
    % Match border style
    set(ax2, 'FontSize', 8, 'TickDir', 'out', 'LineWidth', 2, 'Color', 'w');
    
    grid(ax2, 'on'); 
    box(ax2, 'on');
    
    ylim(ax2, [0.5 63.5]);
    axis(ax2, 'normal');
    
    linkaxes([ax1 ax2], 'y');
            
    drawnow;
    
    % ---- Export ----
    fprintf('   Saving PNG -> %s\n', pngPath);
    exportgraphics(f, pngPath, 'Resolution', 220);
    
    fprintf('   Saving PDF -> %s\n', pdfPath);
    try
        print(f, pdfPath, '-dpdf', '-painters');
    catch ME
        warning('Failed to save PDF: %s', ME.message);
    end
    
    close(f);
end