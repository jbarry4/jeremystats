function plot_theta_ripple_simple(inputFolder, upscaleFactor)
% plot_theta_ripple_channels_inverted_upsample
% -----------------------------------------------------------------------------
% What this does (simple + robust):
%   1) Loads x1.mat (1xN), y1.mat (1xM), c1.mat (MxN)
%   2) PRESERVES your current, correct cMatrix orientation (no accidental flips)
%   3) Maps data rows to channels 2..63 (discrete channel rows)
%      - Adds a blank row for channel 1 (top) and channel 64 (bottom)
%   4) Puts larger channels at the bottom (channel 64 at bottom)
%   5) Upsamples the X-axis (columns) to reduce pixelation in the SVG
%      - We keep Y as discrete channels (no vertical upsampling) so ticks are exact
%   6) Plots with JET colormap and saves an SVG next to your data
%
% Usage:
%   plot_theta_ripple_channels_inverted_upsample('C:\path\folder');       % default 4x upsample (X only)
%   plot_theta_ripple_channels_inverted_upsample('C:\path\folder', 8);    % 8x upsample
%   plot_theta_ripple_channels_inverted_upsample('C:\path\folder', 1);    % no upsample
% -----------------------------------------------------------------------------

    if nargin < 2 || isempty(upscaleFactor)
        upscaleFactor = 4;   % default: 4x upsample along X to smooth blockiness
    end

    fprintf('\n--- Theta/Ripple Heatmap (JET) — Channels, 64 at Bottom, X Upsample ---\n');
    fprintf('Input folder: %s\n', inputFolder);
    fprintf('X upsample factor: %d\n', upscaleFactor);

    % ---------------- Load data ----------------
    xStruct = load(fullfile(inputFolder, 'x1.mat'));  xFields = fieldnames(xStruct);  xValues = xStruct.(xFields{1});
    yStruct = load(fullfile(inputFolder, 'y1.mat'));  yFields = fieldnames(yStruct);  yValues = yStruct.(yFields{1});
    cStruct = load(fullfile(inputFolder, 'c1.mat'));  cFields = fieldnames(cStruct);  cMatrix = cStruct.(cFields{1});

    % Force row vectors for axis labeling
    xValues = xValues(:).';
    yValues = yValues(:).';

    fprintf('Loaded sizes -> x: %d, y: %d, c: %d x %d\n', ...
        numel(xValues), numel(yValues), size(cMatrix,1), size(cMatrix,2));

    % ---------------- Make sure c is [numel(y) x numel(x)] ----------------
    if ~isequal(size(cMatrix), [numel(yValues), numel(xValues)])
        if isequal(size(cMatrix), [numel(xValues), numel(yValues)])
            fprintf('Transposing cMatrix to match [numel(y) x numel(x)]...\n');
            cMatrix = cMatrix.';
        else
            error('c1 size mismatch; expected [%d x %d] or [%d x %d], got [%d x %d].', ...
                numel(yValues), numel(xValues), numel(xValues), numel(yValues), size(cMatrix,1), size(cMatrix,2));
        end
    end

    % -------------------------------------------------------------------------
    % IMPORTANT: Preserve your current (correct) orientation of cMatrix.
    % We do NOT flip here; we only remap rows to the desired channel axis.
    % -------------------------------------------------------------------------

    % ---------------- Map rows to channels 2..63 (62 channels) --------------
    targetChannels = 2:63;                 % exact channels to show as data
    numTargetRows  = numel(targetChannels);% 62

    % If your data rows count != 62, adapt (trim or pad with NaN) to 62 rows
    currentRows = size(cMatrix, 1);
    if currentRows > numTargetRows
        fprintf('Data has %d rows; trimming to first %d rows to match channels 2..63.\n', currentRows, numTargetRows);
        cMatrix = cMatrix(1:numTargetRows, :);
    elseif currentRows < numTargetRows
        fprintf('Data has %d rows; padding with NaN rows to reach %d (channels 2..63).\n', currentRows, numTargetRows);
        cMatrix = [cMatrix; nan(numTargetRows - currentRows, size(cMatrix,2))];
    else
        fprintf('Data has exactly %d rows for channels 2..63.\n', currentRows);
    end

    % ---------------- Upsample along X only (reduce blockiness) -------------
    if upscaleFactor > 1
        fprintf('Upsampling X axis by factor %d using interp1 (linear)...\n', upscaleFactor);

        % Build fine X axis: preserve original span, more samples
        xValuesFine = linspace(xValues(1), xValues(end), numel(xValues) * upscaleFactor);

        % Interpolate each row independently along columns
        cUpsampled = nan(size(cMatrix,1), numel(xValuesFine));
        for r = 1:size(cMatrix,1)
            rowData = cMatrix(r, :);
            % Guard against NaNs across entire row
            if all(isnan(rowData))
                cUpsampled(r, :) = nan;
            else
                % Use linear interpolation; 'extrap' avoids edge NaNs if x not strictly monotonic
                cUpsampled(r, :) = interp1(xValues, rowData, xValuesFine, 'linear', 'extrap');
            end
        end

        cMatrix = cUpsampled;
        xValues = xValuesFine;

        fprintf('New sizes after X upsample -> x: %d, y: %d, c: %d x %d\n', ...
            numel(xValues), numel(targetChannels), size(cMatrix,1), size(cMatrix,2));
    else
        fprintf('No X upsampling (factor == 1).\n');
    end

    % ---------------- Add blank rows for channels 1 (top) and 64 (bottom) ---
    fprintf('Adding blank rows for channel 1 (top) and channel 64 (bottom)...\n');
    blankRow = nan(1, size(cMatrix, 2));
    cMatrixWithBlanks = [blankRow; cMatrix; blankRow];   % top blank (ch 1), bottom blank (ch 64)

    % ---------------- Put larger channels at the bottom ----------------------
    % Flip vertically so channel numbers increase downward visually (64 bottom).
    fprintf('Flipping vertically so channel 64 is at the bottom.\n');
    cMatrixWithBlanks = flipud(cMatrixWithBlanks);

    % Build channel axis 1..64 (discrete channel rows)
    channelNumbers = 1:64;

    % ---------------- Plot ----------------
    fprintf('Plotting imagesc with discrete channel Y axis...\n');
    figure('Color', 'w');
    imagesc(xValues, channelNumbers, cMatrixWithBlanks);

    % Keep Y increasing upward in axis coordinates; since we flipped the matrix,
    % high channel numbers now appear at the bottom as requested.
    set(gca, 'YDir', 'normal');

    xlabel('X');
    ylabel('Channel #');
    title('Theta–Ripple Heatmap (JET) — Channels (64 at Bottom)');
    colormap(jet);
    colorbar;
    grid on; box on;

    % Ticks every 4 channels to keep it clean
    yticks(1:4:64);

    % ---------------- Save SVG ----------------
    outputFilePath = fullfile(inputFolder, 'theta_ripple_channels.svg');
    fprintf('Saving SVG to: %s\n', outputFilePath);
    try
        exportgraphics(gcf, outputFilePath, 'ContentType', 'vector', 'BackgroundColor', 'white');
        fprintf('Saved SVG via exportgraphics.\n');
    catch ME
        fprintf('exportgraphics failed (%s). Using print fallback...\n', ME.message);
        print(gcf, outputFilePath, '-dsvg');
        fprintf('Saved SVG via print fallback.\n');
    end

    fprintf('--- Done ---\n\n');
end
