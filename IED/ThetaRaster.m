function ThetaRaster(inputFolder, varargin)
% plot_theta_ripple_channels_inverted
% -------------------------------------------------------------------------
% Loads x1.mat (1xN), y1.mat (1xM), c1.mat (MxN)
% Blanks ONLY channel 1 and channel 64 (as NaN rows)
% Uses Gaussian smoothing + bicubic upsampling for cleaner visuals
% Shows every channel tick (1–64)
% Fixes color scale to [-0.2, 0.2]
% Saves EPS (no SVG)
%
% Note:
%   We smooth/upsample ONLY the interior (channels 2–63) to avoid NaN
%   bleeding. Then we add a single NaN row at the top/bottom. We use
%   YDir='reverse' so channel 64 is at the BOTTOM without any flips.
% -------------------------------------------------------------------------

    fprintf('\n--- Plot Theta/Ripple Heatmap (Smoothed, EPS, fixed scale) ---\n');
    fprintf('Input folder: %s\n', inputFolder);

    % ---------- Options (kept minimal and clear) ----------
    parser = inputParser;
    addParameter(parser, 'enableSmoothing', true);   % turn off if you want the raw pixels
    addParameter(parser, 'gaussianSigma', 0.75);     % smoothing strength (pixels)
    addParameter(parser, 'upsampleFactor', 3);       % 1 = no upsample; 2–4 looks nice
    addParameter(parser, 'colormapName', 'jet');     % try 'turbo' too
    addParameter(parser, 'titleText', 'Theta–Ripple Heatmap — Channel 64 at Bottom');
    parse(parser, varargin{:});

    enableSmoothing = logical(parser.Results.enableSmoothing);
    gaussianSigma   = parser.Results.gaussianSigma;
    upsampleFactor  = parser.Results.upsampleFactor;
    colormapName    = char(parser.Results.colormapName);
    titleText       = char(parser.Results.titleText);

    fprintf('Options -> smoothing: %d | sigma: %.3f | upsample: %.1fx | colormap: %s\n', ...
        enableSmoothing, gaussianSigma, upsampleFactor, colormapName);

    % ---------- Load data ----------
    xStruct = load(fullfile(inputFolder, 'x1.mat'));  xFields = fieldnames(xStruct);  xValues = xStruct.(xFields{1});
    yStruct = load(fullfile(inputFolder, 'y1.mat'));  yFields = fieldnames(yStruct);  yValues = yStruct.(yFields{1});
    cStruct = load(fullfile(inputFolder, 'c1.mat'));  cFields = fieldnames(cStruct);  cMatrix = cStruct.(cFields{1});

    % Force row vectors for axes
    xValues = xValues(:).';
    yValues = yValues(:).';

    fprintf('Loaded sizes -> x: %d | y: %d | c: %d x %d\n', ...
        numel(xValues), numel(yValues), size(cMatrix,1), size(cMatrix,2));

    % Ensure cMatrix is [numel(y) x numel(x)]
    if ~isequal(size(cMatrix), [numel(yValues), numel(xValues)])
        if isequal(size(cMatrix), [numel(xValues), numel(yValues)])
            fprintf('Transposing cMatrix to match [numel(y) x numel(x)]...\n');
            cMatrix = cMatrix.';
        else
            error('Matrix size mismatch: cMatrix must be [numel(y) x numel(x)].');
        end
    end

    % ---------- Prepare interior (channels 2–63) only ----------
    % Assumption: input cMatrix corresponds to channels 2..63 (62 rows).
    % We will process just this interior to avoid NaN contamination.
    interiorMatrix = cMatrix;  % treat the provided matrix as channels 2..63

    % ---------- Smoothing (interior only) ----------
    if enableSmoothing
        fprintf('Applying Gaussian smoothing to interior (sigma=%.3f)...\n', gaussianSigma);
        interiorMatrix = imgaussfilt(interiorMatrix, gaussianSigma);
    else
        fprintf('Smoothing disabled.\n');
    end

    % ---------- Upsampling (interior only) ----------
    if upsampleFactor > 1
        fprintf('Upsampling interior by factor %.1fx (bicubic)...\n', upsampleFactor);
        interiorMatrix = imresize(interiorMatrix, upsampleFactor, 'bicubic');
    end

    % ---------- Add single blank rows for channels 1 and 64 ----------
    fprintf('Inserting single NaN rows for channel 1 (top) and 64 (bottom)...\n');
    nanRow = nan(1, size(interiorMatrix, 2));
    fullMatrix = [nanRow; interiorMatrix; nanRow];  % ONLY channels 1 and 64 are blank

    % ---------- Axes setup ----------
    channelNumbers = 1:64;  % label every channel

    % Plot
    fprintf('Plotting with fixed color scale [-0.2, 0.2]...\n');
    figure('Color', 'w', 'Position', [100 100 900 700]);

    % Map x across original range, y across channel indices 1..64
    imagesc('XData', [xValues(1) xValues(end)], ...
            'YData', [channelNumbers(1) channelNumbers(end)], ...
            'CData', fullMatrix);

    % Make 64 at bottom without flipping data (simplest + robust):
    set(gca, 'YDir', 'reverse');

    % Labels, ticks, colormap
    xlabel('X', 'FontSize', 12);
    ylabel('Channel #', 'FontSize', 11);
    title(titleText, 'FontSize', 14, 'FontWeight', 'bold');
    colormap(colormapName);
    colorbar;
    caxis([-0.2, 0.2]);  % ✅ fixed scale, reflected in colorbar

    % Show every channel tick
    yticks(channelNumbers);
    yticklabels(string(channelNumbers));
    set(gca, 'FontSize', 8, 'TickDir', 'out', 'LineWidth', 1);
    grid on; box on;

    % ---------- Save EPS only ----------
    epsFilePath = fullfile(inputFolder, 'theta_ripple_channels_inverted.eps');
    fprintf('Saving EPS to: %s\n', epsFilePath);
    exportgraphics(gcf, epsFilePath, 'ContentType', 'vector', 'BackgroundColor', 'white');

    fprintf('--- Done ---\n\n');
end
