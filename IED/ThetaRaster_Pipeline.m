function res = ThetaRaster_Pipeline(inputFolder, varargin) %#ok<INUSD>
% JB — ThetaRaster_Pipeline
% -------------------------------------------------------------------------
% - Finds and opens theta.fig (invisible), extracts x1,y1,c1 (JB style)
% - Computes MeanPositive / MeanNegative (exact math from your snippet)
% - Saves x1,y1,c1 + means into "<inputFolder>/Theta_Plots"
% - Renders a clean heatmap PNG + EPS (fixed caxis [-0.2 0.2])
% - Returns a struct compatible with Pipeline_Main (pngSolid/pngSputter)
%   so it can slot right into the LEFT column (bottom tile).
% -------------------------------------------------------------------------

    fprintf('\n===== JB: ThetaRaster_Pipeline =====\n');
    fprintf('Input folder: %s\n', inputFolder);

    % ---------- Output directory ----------
    outputDir = fullfile(inputFolder, 'Theta_Plots');
    if ~exist(outputDir, 'dir')
        fprintf('Creating output folder: %s\n', outputDir);
        mkdir(outputDir);
    end

    % ---------- Locate theta.fig ----------
    thetaFigPath = fullfile(inputFolder, 'theta.fig');
    if exist(thetaFigPath, 'file') ~= 2
        fprintf('theta.fig not found in input folder. Searching subfolders...\n');
        hits = dir(fullfile(inputFolder, '**', 'theta.fig'));
        assert(~isempty(hits), 'JB: No theta.fig found under: %s', inputFolder);
        thetaFigPath = fullfile(hits(1).folder, hits(1).name);
    end
    fprintf('Opening theta.fig (invisible): %s\n', thetaFigPath);

    % ---------- Open invisible + extract data (JB snippet style) ----------
    srcFig = openfig(thetaFigPath, 'invisible');
    figure(srcFig); % make current (still invisible)

    obj = findobj(srcFig, '-property', 'CData');
    c1  = obj(1).CData;

    obj = findobj(srcFig, '-property', 'XData');
    x1  = obj(1).XData;

    obj = findobj(srcFig, '-property', 'YData');
    y1  = obj(1).YData;

    x1 = x1(:).';  % row vectors
    y1 = y1(:).';

    fprintf('JB: Extracted -> x1:%d | y1:%d | c1:%dx%d\n', numel(x1), numel(y1), size(c1,1), size(c1,2));

    close(srcFig);  % IMPORTANT: no stray windows
    fprintf('Closed source theta.fig.\n');

    % ---------- JB positive / negative means (unchanged math) ----------
    c2 = c1;          Positive = c2 > 0;  c2(~Positive) = 0;
    MeanPositive = sum(c2, 2) ./ sum(Positive, 2);

    c3 = c1;          Negative = c3 < 0;  c3(~Negative) = 0;
    MeanNegative = sum(c3, 2) ./ sum(Negative, 2);

    % ---------- Save mats ----------
    fprintf('Saving mats to: %s\n', outputDir);
    save(fullfile(outputDir, 'x1.mat'), 'x1');
    save(fullfile(outputDir, 'y1.mat'), 'y1');
    save(fullfile(outputDir, 'c1.mat'), 'c1');
    save(fullfile(outputDir, 'MeanPositive.mat'), 'MeanPositive');
    save(fullfile(outputDir, 'MeanNegative.mat'), 'MeanNegative');

    % ---------- Render tidy heatmap (PNG + EPS) ----------
    pngPath = fullfile(outputDir, 'Theta_Raster.png');
    epsPath = fullfile(outputDir, 'Theta_Raster.eps');
    renderThetaRaster(outputDir, x1, y1, c1, pngPath, epsPath);

    % ---------- Return (Pipeline_Main expects pngSolid/pngSputter) ----------
    res = struct();
    res.outputDir   = outputDir;
    res.pngSolid    = pngPath;   % same image for both columns; treated as “global”
    res.pngSputter  = pngPath;
    res.epsPath     = epsPath;

    fprintf('ThetaRaster pipeline outputs:\n  %s\n  %s\n', pngPath, epsPath);
    fprintf('===== JB: ThetaRaster_Pipeline done =====\n\n');
end


function renderThetaRaster(outputDir, xValues, yValues, cMatrix, pngPath, epsPath)
% JB — renderThetaRaster (invisible figure → PNG + EPS, then close)
% Clean + lean; fixed caxis; only ch 1 & 64 blank; tight X limits.

    fprintf('JB: Rendering Theta heatmap...\n');

    % ---- simple knobs (feel free to tweak) ----
    gaussianSigma  = 0.75;
    upsampleFactor = 3;
    colormapName   = 'jet';
    colorScale     = [-0.2, 0.2];
    titleText      = 'Theta–Ripple Heatmap — Channel 64 at Bottom';

    % ---- orientation check ----
    expectedRows = numel(yValues);
    expectedCols = numel(xValues);
    if ~isequal(size(cMatrix), [expectedRows, expectedCols])
        if isequal(size(cMatrix), [expectedCols, expectedRows])
            fprintf('JB: Transposing cMatrix to [%d x %d]...\n', expectedRows, expectedCols);
            cMatrix = cMatrix.';
        else
            error('JB: cMatrix must be [%d x %d]. Got %dx%d.', ...
                  expectedRows, expectedCols, size(cMatrix,1), size(cMatrix,2));
        end
    end

    % ---- smoothing + upsample on interior ----
    interior = imgaussfilt(cMatrix, gaussianSigma);
    if upsampleFactor > 1
        interior = imresize(interior, upsampleFactor, 'bicubic');
    end

    % ---- add NaN rows for channels 1 & 64 only ----
    nCols = size(interior, 2);
    nanRow = nan(1, nCols);
    fullMatrix = [nanRow; interior; nanRow];

    % ---- extents + ticks ----
    channels = 1:64;
    xExtent  = [xValues(1), xValues(end)];
    yExtent  = [channels(1), channels(end)];

    % ---- plot INVISIBLE, save, close ----
    f = figure('Color','w','Position',[100 100 900 700], 'Visible','off');
    imagesc('XData', xExtent, 'YData', yExtent, 'CData', fullMatrix);
    set(gca,'YDir','reverse');
    colormap(colormapName);
    caxis(colorScale);
    colorbar;

    xlabel('X'); ylabel('Channel #');
    title(titleText,'FontWeight','bold');

    yticks(channels);
    yticklabels(string(channels));
    set(gca,'FontSize',8,'TickDir','out','LineWidth',1);
    grid on; box on;
    xlim(xExtent); ylim([1 64]);
    drawnow;

    fprintf('JB: Saving PNG -> %s\n', pngPath);
    exportgraphics(f, pngPath, 'Resolution', 220);

    fprintf('JB: Saving EPS -> %s\n', epsPath);
    exportgraphics(f, epsPath, 'ContentType','vector', 'BackgroundColor','white');

    close(f);
    fprintf('JB: Closed rendering figure.\n');
end
