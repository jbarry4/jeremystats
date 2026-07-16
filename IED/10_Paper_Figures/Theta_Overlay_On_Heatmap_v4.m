function Theta_Overlay_On_Heatmap_v4()
% Theta_Overlay_On_Heatmap_v4 — hard-coded overlay re-run.
% -------------------------------------------------------------------------
% Differences vs Theta_Overlay_On_Heatmap.m:
%   - No path.txt needed. Raw CSC dir is hard-coded per session below.
%   - Reads the stem-prefixed mats written by ThetaRaster_v4
%     (<stem>_x1.mat / <stem>_c1.mat) rather than bare x1.mat / c1.mat.
%   - Writes <stem>_Overlay.png / .pdf into the SAME session folder.
% Everything else (filtering, scaling, rendering) is unchanged.
% -------------------------------------------------------------------------

    % ---------- Hard-coded inputs ----------
    rootDir = 'C:\Users\Z390\Desktop\IED DATA\Take 3';

    % session folder name  ->  raw Neuralynx recording dir (.ncs files)
    sessions = {
        'IED-_PTEN_M8s2', 'D:\PTEN\PTEN\M8_Pten\M8s2feb6\2024-02-06_17-52-07'
    };

    % Neuralynx reader (Nlx2MatCSC)
    addpath(fullfile(fileparts(mfilename('fullpath')), 'reqsPath'));

    fprintf('\n===== Theta_Overlay_On_Heatmap_v4: %d session(s) =====\n', size(sessions,1));

    for i = 1:size(sessions,1)
        folder = fullfile(rootDir, sessions{i,1});
        cscDir = sessions{i,2};
        fprintf('\n--- %s ---\n', sessions{i,1});

        if ~exist(cscDir, 'dir')
            fprintf(2, '  [SKIP] Raw CSC dir not found: %s\n', cscDir);
            continue;
        end

        matList = dir(fullfile(folder, '*_x1.mat'));
        if isempty(matList)
            fprintf(2, '  [SKIP] No *_x1.mat in %s (run ThetaRaster_v4 first).\n', folder);
            continue;
        end

        for k = 1:numel(matList)
            stem = erase(matList(k).name, '_x1.mat');
            try
                d_x1 = load(fullfile(folder, [stem '_x1.mat']), 'x1'); x1 = d_x1.x1;
                d_c1 = load(fullfile(folder, [stem '_c1.mat']), 'c1'); c1 = d_c1.c1;
            catch
                fprintf(2, '  [SKIP] Could not load mats for %s\n', stem);
                continue;
            end

            try
                render_single_overlay(folder, stem, x1, c1, cscDir);
            catch ME
                fprintf(2, '  [ERROR] %s: %s\n', stem, ME.message);
            end
        end
    end

    fprintf('\n===== Overlay v4 done =====\n\n');
end


function render_single_overlay(outputDir, stem, x1, cMatrix, cscDir)
    % --- Configuration ---
    traceColor      = [0 0 0]; % Black lines
    traceAlpha      = 0.5;     % 50% Transparent
    gaussianSigma   = 0.75;    % For smoothing heatmap

    % GLOBAL AMPLITUDE SCALING
    % 300 uV signal takes up exactly the height of 1 channel row.
    global_uV_scale = 300;
    traceGain       = 0.8;     % keep < 1.0 to avoid overlap collision

    % --- 1. Get Session Start Time ---
    ncsFiles = dir(fullfile(cscDir, '*.ncs'));
    if isempty(ncsFiles), error('No .ncs files in %s', cscDir); end

    [~, idx] = sort_nat({ncsFiles.name});
    ncsFiles = ncsFiles(idx);

    firstFile = fullfile(ncsFiles(1).folder, ncsFiles(1).name);
    try
        FirstTS = Nlx2MatCSC(firstFile, [1 0 0 0 0], 0, 3, 1);
        SessionStart_uS = FirstTS(1);
    catch
        error('Read failed for session start.');
    end

    % --- 2. Define Extraction Window ---
    relStart = min(x1);
    relEnd   = max(x1);
    buffer   = 0.2;

    absStart_uS = SessionStart_uS + ((relStart - buffer) * 1e6);
    absEnd_uS   = SessionStart_uS + ((relEnd + buffer) * 1e6);
    extractRange = [absStart_uS, absEnd_uS];

    fprintf('   %s: extracting LFP (%.2fs - %.2fs)...\n', stem, relStart, relEnd);

    % --- 3. Figure Setup ---
    f = figure('Visible', 'off', 'Color', 'w', 'Position', [100, 100, 1200, 800]);

    % --- Prepare Heatmap Data ---
    if size(cMatrix, 2) == 64 || size(cMatrix, 2) == 63
         cMatrix = cMatrix';
    end
    if size(cMatrix, 1) >= 64
        cMatrix = cMatrix(1:63, :); % Trim Ch 64
    end

    interior = imgaussfilt(cMatrix, gaussianSigma);
    interior = imresize(interior, 3, 'bicubic');

    xExtent = [relStart, relEnd];
    yExtent = [1, 63];

    ax = axes(f);
    set(ax, 'Color', 'k'); % Black background for gap

    imagesc(ax, 'XData', xExtent, 'YData', yExtent, 'CData', interior);
    set(ax, 'YDir', 'reverse');
    colormap(ax, 'jet');

    clim(ax, [-0.2 0.2]);
    cb = colorbar(ax);
    cb.Label.String = 'CSD (a.u.)';

    hold(ax, 'on');

    % --- 4. Loop Channels (EVEN ONLY) ---
    maxCh = min(length(ncsFiles), 62);

    for ch = 2:2:maxCh
        fileToUse = ncsFiles(ch);

        % Channel 59 repair logic (kept from original; evens skip 59 naturally)
        fName = fileToUse.name;
        chNum = str2double(regexp(fName, '\d+', 'match', 'once'));
        if chNum == 59
             idx58 = find(arrayfun(@(x) str2double(regexp(x.name, '\d+', 'match', 'once')) == 58, ncsFiles));
             if ~isempty(idx58), fileToUse = ncsFiles(idx58); end
        end

        fPath = fullfile(fileToUse.folder, fileToUse.name);

        try
            [Ts, Samples, Header] = Nlx2MatCSC(fPath, [1 0 0 0 1], 1, 4, extractRange);
        catch
            continue;
        end

        if isempty(Ts), continue; end

        [Fs, ADBitVolts] = parseHeader(Header);
        flatSamples = Samples(:)';

        blockStart_Rel = (double(Ts(1)) - double(SessionStart_uS)) / 1e6;
        t_vec = linspace(blockStart_Rel, blockStart_Rel + (length(flatSamples)/Fs), length(flatSamples));

        uV = flatSamples * ADBitVolts * 1e6 * -1;

        try
            lfp_filt = bandpass_filter_sos(uV, Fs, [4 12]);
        catch
            continue;
        end

        validIdx = t_vec >= relStart & t_vec <= relEnd;
        t_plot = t_vec(validIdx);
        v_plot = lfp_filt(validIdx);

        if isempty(t_plot), continue; end

        % --- GLOBAL SCALING (relational across all files) ---
        v_scaled  = (v_plot / global_uV_scale) * traceGain;
        v_shifted = v_scaled + ch;

        plot(ax, t_plot, v_shifted, 'Color', [traceColor, traceAlpha], 'LineWidth', 1.0);
    end

    % --- Final Polish ---
    xlabel(ax, 'Time (s)');
    ylabel(ax, 'Channel #');
    title(ax, 'Theta CSD with LFP Overlay', 'FontSize', 14);

    yticks(ax, 2:2:62);
    ylim(ax, [0.5, 63.5]);
    xlim(ax, xExtent);
    set(ax, 'Layer', 'top');

    % --- EXPORT ---
    pngPath = fullfile(outputDir, [stem '_Overlay.png']);
    exportgraphics(f, pngPath, 'Resolution', 300);
    fprintf('   Saved PNG: %s\n', pngPath);

    pdfPath = fullfile(outputDir, [stem '_Overlay.pdf']);
    exportgraphics(f, pdfPath, 'ContentType', 'vector');
    fprintf('   Saved Vector PDF: %s\n', pdfPath);

    close(f);
end

% --- Helpers ---

function [sorted, idx] = sort_nat(cellArray)
    [~, idx] = sort(cellfun(@(x) str2double(regexp(x, '\d+', 'match', 'once')), cellArray));
    sorted = cellArray(idx);
end

function [Fs, ADBitVolts] = parseHeader(headerCell)
    Fs = 30000; ADBitVolts = 6e-8;
    line = headerCell(contains(headerCell, 'SamplingFrequency', 'IgnoreCase', true));
    if ~isempty(line), tok = regexp(line{1}, '[\-+]?\d+(\.\d+)?', 'match'); Fs = str2double(tok{1}); end
    line = headerCell(contains(headerCell, 'ADBitVolts', 'IgnoreCase', true));
    if ~isempty(line), tok = regexp(line{1}, '[\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?', 'match'); ADBitVolts = str2double(tok{1}); end
end

function fd = bandpass_filter_sos(data, Fs, rng)
    if length(data) < 3*(Fs/rng(1)), fd = data; return; end
    order = 3;
    [z, p, k] = butter(order, rng/(Fs/2), 'bandpass');
    [sos, g] = zp2sos(z, p, k);
    fd = filtfilt(sos, g, data);
end
