function ThetaRaster_Pipeline(inputFolder)
% JB code — ThetaRaster_Pipeline
% -------------------------------------------------------------------------
% 1) Find and open theta.fig (invisible)
% 2) Pull out x1, y1, c1 from the figure's image object (like your snippet)
% 3) Build c2/c3 masks; compute MeanPositive/MeanNegative (exact math)
% 4) Save x1, y1, c1, MeanPositive, MeanNegative into "Theta_Plots" folder
% 5) Make the pretty EPS heatmap via ThetaRaster (JB plotting style)
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
        % simple recursive search; use the first match if multiple
        searchHits = dir(fullfile(inputFolder, '**', 'theta.fig'));
        if isempty(searchHits)
            error('JB: No theta.fig found under: %s', inputFolder);
        end
        candidatePath = fullfile(searchHits(1).folder, searchHits(1).name);
    end
    fprintf('Opening theta.fig: %s\n', candidatePath);

    % ---------------- Open fig invisibly and grab data (like your snippet) ----------------
    figHandle = openfig(candidatePath, 'invisible');
    figure(figHandle); % make current so gcf matches your original snippet
    fig = gcf;         %#ok<NASGU>  % JB: keep variable name as in snippet

    % JB snippet style: pull XData, YData, CData from the first object found
    dataObjects = findobj(figHandle, '-property', 'XData');
    x1 = dataObjects(1).XData;
    dataObjects = findobj(figHandle, '-property', 'YData');
    y1 = dataObjects(1).YData;
    dataObjects = findobj(figHandle, '-property', 'CData');
    c1 = dataObjects(1).CData;

    % Force row vectors for x1/y1 to be consistent downstream
    x1 = x1(:).';
    y1 = y1(:).';

    fprintf('JB: Extracted sizes -> x1:%d | y1:%d | c1:%dx%d\n', ...
        numel(x1), numel(y1), size(c1,1), size(c1,2));

    % ---------------- JB positive mask block (unchanged math) ----------------
    c2 = c1;
    Positive = c2 > 0;
    c2(~Positive) = 0;
    MeanPositive = sum(c2, 2) ./ sum(Positive, 2);

    % ---------------- JB negative mask block (unchanged math) ----------------
    c3 = c1;
    Negative = c3 < 0;
    c3(~Negative) = 0;
    MeanNegative = sum(c3, 2) ./ sum(Negative, 2);

    % ---------------- Save exactly what we computed ----------------
    fprintf('Saving x1/y1/c1 and MeanPositive/MeanNegative to: %s\n', outputFolder);
    save(fullfile(outputFolder, 'x1.mat'), 'x1');
    save(fullfile(outputFolder, 'y1.mat'), 'y1');
    save(fullfile(outputFolder, 'c1.mat'), 'c1');
    save(fullfile(outputFolder, 'MeanPositive.mat'), 'MeanPositive');
    save(fullfile(outputFolder, 'MeanNegative.mat'), 'MeanNegative');

    % ---------------- Make the pretty EPS heatmap in Theta_Plots ----------------
    ThetaRaster(outputFolder, x1, y1, c1);

    fprintf('===== JB: Done =====\n\n');
end


function ThetaRaster(outputFolder, xValues, yValues, cMatrix)
% JB code — ThetaRaster (pretty, lean EPS)
% -------------------------------------------------------------------------
% - Fixed color scale [-0.2, 0.2]
% - Every channel tick (1–64) visible
% - Only channels 1 and 64 are blank (NaN rows added after smoothing)
% - No empty margins: X axis fits data exactly
% - Saves EPS into outputFolder
% -------------------------------------------------------------------------

    fprintf('\n--- JB: ThetaRaster (plot & save EPS) ---\n');

    % -------- Settings (simple knobs) --------
    gaussianSigma  = 0.75;          % smoothing strength in pixels
    upsampleFactor = 3;             % 1=no upsample; 2–4 looks nice
    colormapName   = 'jet';         % classic JB palette
    colorScale     = [-0.2, 0.2];   % requested fixed scale
    titleText      = 'Theta–Ripple Heatmap — Channel 64 at Bottom';

    % -------- Orient cMatrix to [numel(y) x numel(x)] if needed --------
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

    % -------- Smooth + upsample INTERIOR (treat cMatrix as channels 2–63) --------
    fprintf('JB: Smoothing (sigma=%.3f) and upsampling (x%.1f)...\n', gaussianSigma, upsampleFactor);
    interiorMatrix = imgaussfilt(cMatrix, gaussianSigma);
    if upsampleFactor > 1
        interiorMatrix = imresize(interiorMatrix, upsampleFactor, 'bicubic');
    end

    % -------- Add exactly one NaN row on top/bottom for ch 1 and ch 64 --------
    numberOfColumns = size(interiorMatrix, 2);
    nanRow = nan(1, numberOfColumns);
    fullMatrix = [nanRow; interiorMatrix; nanRow];  % ONLY 1 and 64 blanked

    % -------- Axes + mapping --------
    channelNumbers = 1:64;
    xExtent = [xValues(1), xValues(end)];
    yExtent = [channelNumbers(1), channelNumbers(end)];

    % -------- Plot --------
    fprintf('JB: Plotting heatmap...\n');
    figureHandle = figure('Color','w','Position',[100 100 900 700]);
    imagesc('XData', xExtent, 'YData', yExtent, 'CData', fullMatrix);
    set(gca, 'YDir', 'reverse');       % channel 64 at bottom
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

    % Tight to data (no empty left/right)
    xlim(xExtent);
    ylim([1 64]);
    drawnow;

    % -------- Save EPS --------
    epsFilePath = fullfile(outputFolder, 'Theta_Raster.eps');
    fprintf('JB: Saving EPS -> %s\n', epsFilePath);
    exportgraphics(figureHandle, epsFilePath, 'ContentType', 'vector', 'BackgroundColor', 'white');

    fprintf('--- JB: ThetaRaster done ---\n\n');
end
