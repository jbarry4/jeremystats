function Theta_Overlay_On_Heatmap(rootInputFolder)
% JB — Theta_Overlay_On_Heatmap 
% (Even Channels Only + Vector PDF + Fixed Colorbar + Global Amplitude Scale)
% -------------------------------------------------------------------------
% 1. Loops through "Theta_Plots" processed folders.
% 2. Loads 'x1.mat' (Time), 'c1.mat' (CSD Heatmap), 'path.txt'.
% 3. Loads Raw LFP (Nlx2MatCSC), Filters Theta (4-12 Hz SOS).
% 4. Renders Heatmap (Full Res, Black BG) + Colorbar [-0.2 0.2].
% 5. Overlays Theta traces (Even Chs, Fixed Global Scale).
% 6. Exports PNG and VECTOR PDF.
% -------------------------------------------------------------------------

    fprintf('\n=================================================\n');
    fprintf('   JB: Theta Heatmap + Overlay (Even Chs, Vector PDF)\n');
    fprintf('   Root: %s\n', rootInputFolder);
    fprintf('=================================================\n');

    searchPattern = fullfile(rootInputFolder, '**', 'x1.mat');
    fileList = dir(searchPattern);

    if isempty(fileList)
        warning('No x1.mat files found in: %s', rootInputFolder);
        return;
    end

    fprintf('Found %d processed folders. Starting overlay...\n\n', length(fileList));

    for k = 1:length(fileList)
        x1Path    = fullfile(fileList(k).folder, fileList(k).name);
        parentDir = fileList(k).folder; 
        
        [~, folderName] = fileparts(parentDir);
        fprintf('--- Processing: %s ---\n', folderName);

        % 1. Locate path.txt
        pathTxtFile = fullfile(parentDir, 'path.txt');
        if ~exist(pathTxtFile, 'file')
            fprintf(2, '   [SKIP] "path.txt" missing.\n\n');
            continue;
        end
        
        try
            fid = fopen(pathTxtFile, 'rt');
            rawPathLine = fgetl(fid);
            fclose(fid);
            cscDir = strtrim(rawPathLine);
        catch
            continue;
        end

        % 2. Load Data
        try
            d_x1 = load(x1Path, 'x1'); x1 = d_x1.x1;
            d_c1 = load(fullfile(parentDir, 'c1.mat'), 'c1'); c1 = d_c1.c1;
        catch
            fprintf(2, '   [SKIP] Could not load x1.mat or c1.mat.\n');
            continue;
        end

        try
            render_single_overlay(parentDir, x1, c1, cscDir);
        catch ME
            fprintf(2, '   [ERROR] %s\n\n', ME.message);
        end
    end
    fprintf('===== Overlay Loop Complete =====\n');
end

function render_single_overlay(outputDir, x1, cMatrix, cscDir)
    % --- Configuration ---
    traceColor      = [0 0 0]; % Black lines
    traceAlpha      = 0.5;     % 50% Transparent
    gaussianSigma   = 0.75;    % For smoothing heatmap
    
    % GLOBAL AMPLITUDE SCALING
    % This ensures plots are relational. 
    % 300 uV signal will take up exactly the height of 1 channel row.
    global_uV_scale = 300;     
    traceGain       = 0.8;     % Visual scaling factor (keep < 1.0 to avoid overlap collision)
    
    % --- 1. Get Session Start Time ---
    ncsFiles = dir(fullfile(cscDir, '*.ncs'));
    if isempty(ncsFiles), error('No .ncs files in %s', cscDir); end
    
    % Sort strictly by number
    [~, idx] = sort_nat({ncsFiles.name}); 
    ncsFiles = ncsFiles(idx);
    
    % Read Session Start
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

    fprintf('   Extracting LFP (%.2fs - %.2fs)...\n', relStart, relEnd);

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
    
    % --- FIX 1: Explicit Colorbar with Fixed Limits ---
    caxis(ax, [-0.2 0.2]); 
    cb = colorbar(ax);
    cb.Label.String = 'CSD (a.u.)';
    
    hold(ax, 'on');

    % --- 4. Loop Channels (EVEN ONLY) ---
    maxCh = min(length(ncsFiles), 62);
    
    for ch = 2:2:maxCh
        fileToUse = ncsFiles(ch);
        
        % --- REPAIR LOGIC FOR CHANNEL 59 (If it happens to be even, though loop skips it) ---
        % Since we are looping evens (2, 4... 58, 60), 59 is skipped naturally.
        % However, if you ever change to ALL channels, we keep the logic here safely.
        fName = fileToUse.name;
        chNum = str2double(regexp(fName, '\d+', 'match', 'once'));
        if chNum == 59
             idx58 = find(arrayfun(@(x) str2double(regexp(x.name, '\d+', 'match', 'once')) == 58, ncsFiles));
             if ~isempty(idx58), fileToUse = ncsFiles(idx58); end
        end
        % -------------------------------------------------------------------------
        
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
        
        % --- FIX 2: GLOBAL SCALING ---
        % By dividing by a FIXED global_uV_scale (300) for every single plot,
        % the amplitudes are relational across all files.
        v_scaled = (v_plot / global_uV_scale) * traceGain; 
        v_shifted = v_scaled + ch;
        
        plot(ax, t_plot, v_shifted, 'Color', [traceColor, traceAlpha], 'LineWidth', 1.0);
    end
    
    % --- Final Polish ---
    xlabel(ax, 'Time (s)');
    ylabel(ax, 'Channel #');
    title(ax, 'Theta CSD with LFP Overlay', 'FontSize', 14);
    
    % Ticks for Even channels only to match data
    yticks(ax, 2:2:62);
    ylim(ax, [0.5, 63.5]); 
    xlim(ax, xExtent);
    set(ax, 'Layer', 'top'); 
    
    % --- EXPORT ---
    % 1. PNG (Raster)
    pngPath = fullfile(outputDir, 'Theta_Heatmap_Overlay.png');
    exportgraphics(f, pngPath, 'Resolution', 300);
    fprintf('   Saved PNG: %s\n', pngPath);
    
    % 2. PDF (Vector / "Unflattened")
    pdfPath = fullfile(outputDir, 'Theta_Heatmap_Overlay.pdf');
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