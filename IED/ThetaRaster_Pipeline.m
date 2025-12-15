function res = ThetaRaster_Pipeline(inputFolder, varargin) %#ok<INUSD>
% JB — ThetaRaster_Pipeline
% -------------------------------------------------------------------------
% - Finds and opens theta.fig (invisible), extracts x1,y1,c1
% - Computes MeanPositive / MeanNegative
% - Saves x1,y1,c1 + means into "<inputFolder>/Theta_Plots"
% - Renders a clean heatmap PNG + PDF (fixed caxis [-0.2 0.2])
% - Returns a struct compatible with Pipeline_Main
% -------------------------------------------------------------------------
    fprintf('\n===== JB: ThetaRaster_Pipeline =====\n');
    fprintf('Input folder: %s\n', inputFolder);
    
    % ---------- Output directory ----------
    outputDir = fullfile(inputFolder, 'Theta_Plots');
    if ~exist(outputDir, 'dir')
        mkdir(outputDir);
    end
    
    % ---------- Locate theta.fig ----------
    thetaFigPath = fullfile(inputFolder, 'theta.fig');
    if exist(thetaFigPath, 'file') ~= 2
        hits = dir(fullfile(inputFolder, '**', 'theta.fig'));
        assert(~isempty(hits), 'JB: No theta.fig found under: %s', inputFolder);
        thetaFigPath = fullfile(hits(1).folder, hits(1).name);
    end
    fprintf('Opening theta.fig (invisible): %s\n', thetaFigPath);
    
    % ---------- Open invisible + extract data ----------
    srcFig = openfig(thetaFigPath, 'invisible');
    figure(srcFig); 
    obj = findobj(srcFig, '-property', 'CData');
    c1  = obj(1).CData;
    obj = findobj(srcFig, '-property', 'XData');
    x1  = obj(1).XData;
    obj = findobj(srcFig, '-property', 'YData');
    y1  = obj(1).YData;
    
    % Ensure row vectors
    x1 = x1(:).';  
    y1 = y1(:).';
    
    close(srcFig);  
    fprintf('Closed source theta.fig.\n');
    
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
    pngPath = fullfile(outputDir, 'Theta_Raster.png');
    pdfPath = fullfile(outputDir, 'Theta_Raster.pdf');
    
    renderThetaRaster(outputDir, x1, y1, c1, MeanNegative, pngPath, pdfPath);
    
    % ---------- Return struct ----------
    res = struct();
    res.outputDir   = outputDir;
    res.pngSolid    = pngPath;
    res.pngSputter  = pngPath;
    res.pdfPath     = pdfPath;
    
    fprintf('ThetaRaster pipeline outputs:\n  %s\n  %s\n', pngPath, pdfPath);
    fprintf('===== JB: ThetaRaster_Pipeline done =====\n\n');
end

% --- MODIFIED: Render Function ---
function renderThetaRaster(~, xValues, yValues, cMatrix, MeanNegative, pngPath, pdfPath)
% JB — renderThetaRaster
% UI Fixes: 
% 1. "a.u." for units.
% 2. Double-newline padding in title to prevent overlap.
    
    fprintf('JB: Rendering Theta heatmap...\n');
    
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
    fprintf('JB: Saving PNG -> %s\n', pngPath);
    exportgraphics(f, pngPath, 'Resolution', 220);
    
    fprintf('JB: Saving PDF -> %s\n', pdfPath);
    try
        print(f, pdfPath, '-dpdf', '-painters');
    catch ME
        warning('Failed to save PDF: %s', ME.message);
    end
    
    close(f);
    fprintf('JB: Rendering complete.\n');
end