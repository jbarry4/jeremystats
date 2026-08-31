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
% 1. "a.u." for units, Double-newline padding in title.
% 2. Reduced Y-ticks (1, 10, 20... 60) and increased font sizes.
% 3. Layering/Gap fix: Uses `axis tight` to perfectly bound upsampled image.
% 4. Top/Right ticks removed (box off + manual border trace).
% 5. Removed -0.1 from line plot X-axis and flattened text.
% 6. Locked Mean Sink X-axis exactly to [-0.2, 0].
    
    fprintf('JB: Rendering Theta heatmap...\n');
    
    % ---- Configuration ----
    gaussianSigma  = 0.75;
    upsampleFactor = 3;
    colormapName   = 'jet';
    colorScale     = [-0.2, 0.2];
    titleText      = 'Theta CSD Raster';
    
    % --- Font Size Controls ---
    titleSize      = 18; 
    axisFontSize   = 14; 
    
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
    tl = tiledlayout(f, 1, 5, 'TileSpacing', 'compact', 'Padding', 'loose');
    
    % =====================================================================
    % --- TILE 1 (Heatmap): Spans 4 columns ---
    % =====================================================================
    ax1 = nexttile(tl, 1, [1 4]);
    
    imagesc(ax1, 'XData', xExtent, 'YData', yExtent, 'CData', fullMatrix);
    set(ax1, 'YDir', 'reverse');
    colormap(ax1, colormapName);
    caxis(ax1, colorScale);
    
    % Colorbar
    cb = colorbar(ax1); 
    cb.Label.String = 'CSD (a.u.)'; 
    cb.Label.FontSize = axisFontSize;
    
    % Labels & Title
    xlabel(ax1, 'Time (s)', 'FontSize', axisFontSize, 'FontWeight', 'bold');
    ylabel(ax1, 'Channel #', 'FontSize', axisFontSize, 'FontWeight', 'bold');
    title(ax1, {titleText, ' '}, 'FontSize', titleSize, 'FontWeight', 'bold');
    
    % --- Y-Ticks (1, 10, 20, 30, 40, 50, 60) ---
    tickVals = [1, 10:10:60];
    yticks(ax1, tickVals);
    yticklabels(ax1, string(tickVals));
    
    % --- TIGHT BORDER & GAP FIX ---
    set(ax1, 'FontSize', axisFontSize, 'TickDir', 'out', 'Layer', 'top');
    box(ax1, 'off');   % Kills native box (removing top/right ticks)
    grid(ax1, 'off');  
    
    axis(ax1, 'tight'); % Perfectly snaps boundaries to the image!
    xl = xlim(ax1);
    yl = ylim(ax1);
    
    % Trace a clean black frame over the exact edges
    hold(ax1, 'on');
    plot(ax1, [xl(1) xl(2) xl(2) xl(1) xl(1)], [yl(1) yl(1) yl(2) yl(2) yl(1)], 'k-', 'LineWidth', 2, 'Clipping', 'off');
    
    % =====================================================================
    % --- TILE 2 (Line Plot): Spans 1 column ---
    % =====================================================================
    ax2 = nexttile(tl, 5, [1 1]);
    
    if numel(MeanNegative) == 63
        yAxis = 1:63;
        plot(ax2, MeanNegative, yAxis, 'b-', 'LineWidth', 2);
    else
        yAxis = 1:numel(MeanNegative);
        plot(ax2, MeanNegative, yAxis, 'b-', 'LineWidth', 2);
    end
    
    set(ax2, 'YDir', 'reverse');
    set(ax2, 'YTick', [], 'YTickLabel', []); 
    
    xlabel(ax2, 'CSD (a.u.)', 'FontSize', axisFontSize, 'FontWeight', 'bold');
    title(ax2, {'Mean Sink', ' '}, 'FontSize', titleSize, 'FontWeight', 'bold');
    
    % --- LINE PLOT BORDER/TICK FIXES ---
    set(ax2, 'FontSize', axisFontSize, 'TickDir', 'out', 'Color', 'w', 'Layer', 'top');
    ax2.XTickLabelRotation = 0; % Forces text to stay flat
    box(ax2, 'off'); 
    grid(ax2, 'on'); 
    
    % Sync Y-limits to match the exact mathematical bounds of ax1
    ylim(ax2, yl);
    
    % --- LOCK X-AXIS TO [-0.2, 0] ---
    xlim(ax2, [-0.2, 0]);
    
    drawnow; % Force MATLAB to calculate dynamic ticks
    
    % Dynamically remove -0.1 tick mark
    tks2 = xticks(ax2);
    tks2(abs(tks2 - (-0.1)) < 1e-4) = []; 
    xticks(ax2, tks2);
    
    % Trace a clean black frame over the line plot
    xl2 = xlim(ax2);
    hold(ax2, 'on');
    plot(ax2, [xl2(1) xl2(2) xl2(2) xl2(1) xl2(1)], [yl(1) yl(1) yl(2) yl(2) yl(1)], 'k-', 'LineWidth', 2, 'Clipping', 'off');
            
    % ---- Export ----
    fprintf('JB: Saving PNG -> %s\n', pngPath);
    exportgraphics(f, pngPath, 'Resolution', 300); 
    
    fprintf('JB: Saving PDF -> %s\n', pdfPath);
    try
        print(f, pdfPath, '-dpdf', '-painters');
    catch ME
        warning('Failed to save PDF: %s', ME.message);
    end
    
    close(f);
    fprintf('JB: Rendering complete.\n');
end