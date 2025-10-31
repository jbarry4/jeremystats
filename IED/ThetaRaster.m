function ThetaRaster(inputFolder, varargin)
% plot_theta_ripple_channels_inverted
% -------------------------------------------------------------------------
% Purpose:
%   Load x1.mat (1xN), y1.mat (1xM), c1.mat (MxN), add blank rows for
%   channels 1 and 64, flip vertically so channel 64 is at the bottom,
%   smooth + upsample for nicer visuals, and save high-quality EPS + SVG.
%
% Update:
%   - Every channel number (1–64) now has a visible tick label.
%   - Slightly smaller font so all tick labels fit cleanly.
% -------------------------------------------------------------------------

    fprintf('\n--- Plot Theta/Ripple Heatmap (Smoothed + EPS) ---\n');
    fprintf('Input folder: %s\n', inputFolder);

    % ---------------- Parse options ----------------
    parser = inputParser;
    addParameter(parser, 'enableSmoothing', true);
    addParameter(parser, 'gaussianSigma', 0.75);
    addParameter(parser, 'upsampleFactor', 3);
    addParameter(parser, 'colormapName', 'jet');
    addParameter(parser, 'titleText', 'Theta–Ripple Heatmap — Channel 64 at Bottom');
    parse(parser, varargin{:});

    enableSmoothing  = logical(parser.Results.enableSmoothing);
    gaussianSigma    = parser.Results.gaussianSigma;
    upsampleFactor   = parser.Results.upsampleFactor;
    colormapName     = char(parser.Results.colormapName);
    titleText        = char(parser.Results.titleText);

    % ---------------- Load data ----------------
    xStruct = load(fullfile(inputFolder, 'x1.mat'));  
    xFields = fieldnames(xStruct);  
    xValues = xStruct.(xFields{1});

    yStruct = load(fullfile(inputFolder, 'y1.mat'));  
    yFields = fieldnames(yStruct);  
    yValues = yStruct.(yFields{1});

    cStruct = load(fullfile(inputFolder, 'c1.mat'));  
    cFields = fieldnames(cStruct);  
    cMatrix = cStruct.(cFields{1});

    % Force into row vectors
    xValues = xValues(:).';
    yValues = yValues(:).';

    fprintf('Loaded sizes -> x: %d | y: %d | c: %d x %d\n', ...
        numel(xValues), numel(yValues), size(cMatrix,1), size(cMatrix,2));

    % Match expected orientation
    if ~isequal(size(cMatrix), [numel(yValues), numel(xValues)])
        if isequal(size(cMatrix), [numel(xValues), numel(yValues)])
            fprintf('Transposing cMatrix...\n');
            cMatrix = cMatrix.';
        else
            error('Matrix size mismatch.');
        end
    end

    % ---------------- Add blanks + flip ----------------
    fprintf('Adding blank rows for channel 1 and 64...\n');
    numX = size(cMatrix, 2);
    blankRow = nan(1, numX);
    cMatrix = [blankRow; cMatrix; blankRow];
    fprintf('Flipping vertically (channel 64 → bottom)...\n');
    cMatrix = flipud(cMatrix);

    channelNumbers = 1:64;

    % ---------------- Smoothing ----------------
    if enableSmoothing
        fprintf('Applying Gaussian smoothing...\n');
        try
            cMatrix = imgaussfilt(cMatrix, gaussianSigma);
        catch
            fprintf('Falling back to manual Gaussian filter...\n');
            kernelSize = max(1, ceil(3 * gaussianSigma));
            [gx, gy] = meshgrid(-kernelSize:kernelSize);
            kernel = exp(-(gx.^2 + gy.^2) / (2 * gaussianSigma^2));
            kernel = kernel / sum(kernel(:));
            cMatrix = conv2(cMatrix, kernel, 'same');
        end
    end

    % ---------------- Upsample ----------------
    if upsampleFactor > 1
        fprintf('Upsampling (bicubic) x%.1f...\n', upsampleFactor);
        cMatrix = imresize(cMatrix, upsampleFactor, 'bicubic');
    end

    % ---------------- Plot ----------------
    fprintf('Plotting...\n');
    figure('Color','w','Position',[100 100 900 700]);
    imagesc(xValues, channelNumbers, cMatrix);
    set(gca,'YDir','normal');
    xlabel('X','FontSize',12);
    ylabel('Channel #','FontSize',11);
    title(titleText,'FontSize',14,'FontWeight','bold');
    colormap(colormapName);
    colorbar;
    grid on; box on;

    % ✅ Make every channel number visible
    yticks(channelNumbers);                % tick for every channel
    yticklabels(string(channelNumbers));   % label each tick
    set(gca,'FontSize',8);                 % smaller font so they fit
    set(gca,'TickDir','out','LineWidth',1);

    drawnow;

    % ---------------- Save EPS + SVG ----------------
    epsFilePath = fullfile(inputFolder, 'theta_ripple_channels_inverted.eps');
    svgFilePath = fullfile(inputFolder, 'theta_ripple_channels_inverted.svg');

    fprintf('Saving EPS: %s\n', epsFilePath);
    try
        exportgraphics(gcf, epsFilePath, 'ContentType', 'vector', 'BackgroundColor','white');
    catch
        print(gcf, '-depsc', '-tiff', '-r600', epsFilePath);
    end

    fprintf('Saving SVG: %s\n', svgFilePath);
    try
        exportgraphics(gcf, svgFilePath, 'ContentType', 'vector', 'BackgroundColor','white');
    catch
        print(gcf, svgFilePath, '-dsvg', '-r600');
    end

    fprintf('--- Done ---\n\n');
end
