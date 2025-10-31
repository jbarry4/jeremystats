function ThetaRaster_Pipeline(inputFolder)
% JB code — ThetaRaster_Pipeline
% -------------------------------------------------------------------------
% 1) Find and open theta.fig (INVISIBLE)
% 2) Pull out x1, y1, c1 from the figure's image object (like your snippet)
% 3) Compute MeanPositive / MeanNegative exactly like snippet
% 4) Save x1, y1, c1, MeanPositive, MeanNegative into "Theta_Plots"
% 5) Generate clean EPS heatmap (no GUI popups) and CLOSE all figures
% -------------------------------------------------------------------------

    fprintf('\n===== JB: ThetaRaster_Pipeline =====\n');
    fprintf('Input folder: %s\n', inputFolder);

    % ---------------- Make output folder ----------------
    outputFolder = fullfile(inputFolder, 'Theta_Plots');
    if ~exist(outputFolder, 'dir')
        fprintf('Creating output folder: %s\n', outputFolder);
        mkdir(outputFolder);
    end

    % ---------------- Locate theta.fig ----------------
    candidatePath = fullfile(inputFolder, 'theta.fig');
    if exist(candidatePath, 'file') ~= 2
        fprintf('theta.fig not found in input folder. Searching subfolders...\n');
        searchHits = dir(fullfile(inputFolder, '**', 'theta.fig'));
        if isempty(searchHits)
            error('JB: No theta.fig found under: %s', inputFolder);
        end
        candidatePath = fullfile(searchHits(1).folder, searchHits(1).name);
    end
    fprintf('Opening theta.fig (invisible): %s\n', candidatePath);

    % ---------------- Open fig INVISIBLE and grab data ----------------
    figHandle = openfig(candidatePath, 'invisible');  % no popup
    % Make it current just like your snippet pattern (still invisible)
    figure(figHandle);  % gcf points to this, but it's not shown

    dataObjects = findobj(figHandle, '-property', 'XData');
    x1 = dataObjects(1).XData;
    dataObjects = findobj(figHandle, '-property', 'YData');
    y1 = dataObjects(1).YData;
    dataObjects = findobj(figHandle, '-property', 'CData');
    c1 = dataObjects(1).CData;

    x1 = x1(:).';
    y1 = y1(:).';

    fprintf('JB: Extracted sizes -> x1:%d | y1:%d | c1:%dx%d\n', ...
        numel(x1), numel(y1), size(c1,1), size(c1,2));

    % Immediately CLOSE the source figure to avoid stray windows
    close(figHandle);
    fprintf('Closed source theta.fig handle.\n');

    % ---------------- JB positive/negative masks (unchanged math) ----------------
    c2 = c1;
    Positive = c2 > 0;
    c2(~Positive) = 0;
    MeanPositive = sum(c2, 2) ./ sum(Positive, 2);

    c3 = c1;
    Negative = c3 < 0;
    c3(~Negative) = 0;
    MeanNegative = sum(c3, 2) ./ sum(Negative, 2);

    % ---------------- Save outputs ----------------
    fprintf('Saving x1/y1/c1 and MeanPositive/MeanNegative to: %s\n', outputFolder);
    save(fullfile(outputFolder, 'x1.mat'), 'x1');
    save(fullfile(outputFolder, 'y1.mat'), 'y1');
    save(fullfile(outputFolder, 'c1.mat'), 'c1');
    save(fullfile(outputFolder, 'MeanPositive.mat'), 'MeanPositive');
    save(fullfile(outputFolder, 'MeanNegative.mat'), 'MeanNegative');

    % ---------------- Make the pretty EPS heatmap (no GUI) ----------------
    ThetaRaster(outputFolder, x1, y1, c1);

    fprintf('===== JB: Done =====\n\n');
end


function ThetaRaster(outputFolder, xValues, yValues, cMatrix)
% JB code — ThetaRaster (plot & save EPS without leaving any figures open)
% -------------------------------------------------------------------------
% - Fixed color scale [-0.2, 0.2]
% - Every channel tick (1–64) visible
% - Only channels 1 and 64 are blank (NaN rows added after smoothing)
% - No empty margins: X axis fits data exactly
% - Figure is created INVISIBLE, saved, then CLOSED
% -------------------------------------------------------------------------

    fprintf('\n--- JB: ThetaRaster (plot & save EPS) ---\n');

    % -------- Simple settings --------
    gaussianSigma  = 0.75;
    upsampleFactor = 3;
    colormapName   = 'jet';
    colorScale     = [-0.2, 0.2];
    titleText      = 'Theta–Ripple Heatmap — Channel 64 at Bottom';

    % -------- Ensure orientation --------
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

    % -------- Smooth + upsample INTERIOR --------
    fprintf('JB: Smoothing (sigma=%.3f) and upsampling (x%.1f)...\n', gaussianSigma, upsampleFactor);
    interiorMatrix = imgaussfilt(cMatrix, gaussianSigma);
    if upsampleFactor > 1
        interiorMatrix = imresize(interiorMatrix, upsampleFactor, 'bicubic');
    end

    % -------- Add exactly one NaN row on top/bottom for ch 1 and ch 64 --------
    numberOfColumns = size(interiorMatrix, 2);
    nanRow = nan(1, numberOfColumns);
    fullMatrix = [nanRow; interiorMatrix; nanRow];  % ONLY 1 and 64 blanked

    % -------- Axes + extents --------
    channelNumbers = 1:64;
    xExtent = [xValues(1), xValues(end)];
    yExtent = [channelNumbers(1), channelNumbers(end)];

    % -------- Create figure INVISIBLE, plot, save, CLOSE --------
    figureHandle = figure('Color','w','Position',[100 100 900 700], 'Visible', 'off');

    imagesc('XData', xExtent, 'YData', yExtent, 'CData', fullMatrix);
    set(gca, 'YDir', 'reverse');
    colormap(colormapName);
    caxis(colorScale);
    colorbar;

    xlabel('X');
    ylabel('Channel #');
    title(titleText, 'FontWeight', 'bold');

    yticks(channelNumbers);
    yticklabels(string(channelNumbers));
    set(gca, 'FontSize', 8, 'TickDir', 'out', 'LineWidth', 1);
    grid on; box on;

    xlim(xExtent);
    ylim([1 64]);
    drawnow;

    epsFilePath = fullfile(outputFolder, 'Theta_Raster.eps');
    fprintf('JB: Saving EPS -> %s\n', epsFilePath);
    exportgraphics(figureHandle, epsFilePath, 'ContentType', 'vector', 'BackgroundColor', 'white');

    % IMPORTANT: close the plotting figure so nothing lingers
    close(figureHandle);
    fprintf('JB: Closed plotting figure.\n');

    fprintf('--- JB: ThetaRaster done ---\n\n');
end
