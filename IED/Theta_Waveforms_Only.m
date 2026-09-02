function Theta_Waveforms_Only(rootInputFolder)
% JB — Theta_Waveforms_Only
% -------------------------------------------------------------------------
% 1. Loops through "Theta_Plots" folders.
% 2. Reads 'path.txt' to find raw Neuralynx data.
% 3. Loads raw LFP (Nlx2MatCSC) for the time window defined in x1.mat.
% 4. Filters for Theta (4-12 Hz) using stable SOS filtering.
% 5. Generates a clean plot of just the channel waveforms (Stacked).
% -------------------------------------------------------------------------

    fprintf('\n=================================================\n');
    fprintf('   JB: Theta Waveforms Only (No Heatmap)\n');
    fprintf('   Root: %s\n', rootInputFolder);
    fprintf('=================================================\n');

    % Search for x1.mat to find processed folders
    searchPattern = fullfile(rootInputFolder, '**', 'x1.mat');
    fileList = dir(searchPattern);

    if isempty(fileList)
        warning('No x1.mat files found in: %s', rootInputFolder);
        return;
    end

    fprintf('Found %d processed folders.\n\n', length(fileList));

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
        
        % Read Raw Path
        try
            fid = fopen(pathTxtFile, 'rt');
            rawPathLine = fgetl(fid);
            fclose(fid);
            cscDir = strtrim(rawPathLine);
        catch
            continue;
        end

        % 2. Load Time Vector (x1)
        try
            d_x1 = load(x1Path, 'x1'); x1 = d_x1.x1;
        catch
            fprintf(2, '   [SKIP] Could not load x1.mat.\n');
            continue;
        end

        try
            render_waveforms(parentDir, x1, cscDir);
        catch ME
            fprintf(2, '   [ERROR] %s\n\n', ME.message);
        end
    end
    fprintf('===== Loop Complete =====\n');
end

function render_waveforms(outputDir, x1, cscDir)
    % --- Configuration ---
    traceColor     = [0 0 0]; % Black lines
    traceAlpha     = 0.7;     
    traceGain      = 0.8;     % Amplitude scaling
    
    % --- 1. Get Session Start Time ---
    ncsFiles = dir(fullfile(cscDir, '*.ncs'));
    if isempty(ncsFiles), error('No .ncs files in %s', cscDir); end
    
    % Sort strictly (CSC1, CSC2... CSC10)
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
    f = figure('Visible', 'off', 'Color', 'w', 'Position', [100, 100, 1000, 1200]);
    ax = axes(f);
    hold(ax, 'on');

    % --- 4. Loop Channels & Plot ---
    % Limit to 64 channels max to prevent clutter
    numChannels = min(length(ncsFiles), 64);
    
    for ch = 1:numChannels
        fPath = fullfile(ncsFiles(ch).folder, ncsFiles(ch).name);
        
        % Read Data
        try
            [Ts, Samples, Header] = Nlx2MatCSC(fPath, [1 0 0 0 1], 1, 4, extractRange);
        catch
            continue; 
        end
        
        if isempty(Ts), continue; end
        
        % Parse Header
        [Fs, ADBitVolts] = parseHeader(Header);
        
        % Flatten
        flatSamples = Samples(:)';
        
        % Time Vector
        blockStart_Rel = (double(Ts(1)) - double(SessionStart_uS)) / 1e6;
        t_vec = linspace(blockStart_Rel, blockStart_Rel + (length(flatSamples)/Fs), length(flatSamples));
        
        % Convert uV
        uV = flatSamples * ADBitVolts * 1e6 * -1; 
        
        % Filter (SOS method to fix Singular Matrix error)
        try
            lfp_filt = bandpass_filter_sos(uV, Fs, [4 12]);
        catch
            continue;
        end
        
        % Trim to Plot Window
        validIdx = t_vec >= relStart & t_vec <= relEnd;
        t_plot = t_vec(validIdx);
        v_plot = lfp_filt(validIdx);
        
        if isempty(t_plot), continue; end
        
        % Scale & Shift (Stacking traces)
        % 200 uV arbitrary height per "row"
        v_scaled = (v_plot / 200) * traceGain; 
        
        % Channel 1 at top (standard EEG/Laminar convention)
        % Shift down as channel number increases
        % OR Channel 1 at top: y = -ch
        % Let's keep your previous convention: Y-axis = Channel #
        v_shifted = v_scaled + ch;
        
        plot(ax, t_plot, v_shifted, 'Color', [traceColor, traceAlpha], 'LineWidth', 0.8);
    end
    
    % --- Final Polish ---
    xlabel(ax, 'Time (s)');
    ylabel(ax, 'Channel #');
    title(ax, 'Theta Waveforms (4-12 Hz)', 'FontSize', 14);
    
    set(ax, 'YDir', 'reverse'); % Channel 1 at top
    yticks(ax, 1:numChannels);
    ylim(ax, [0.5, numChannels + 0.5]);
    xlim(ax, [relStart, relEnd]);
    grid(ax, 'on');
    
    % Save
    savePath = fullfile(outputDir, 'Theta_Waveforms.png');
    exportgraphics(f, savePath, 'Resolution', 300);
    close(f);
    fprintf('   Saved: %s\n', savePath);
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
    % Replaces [b,a] butter logic with [z,p,k] -> zp2sos
    % This fixes the "Matrix close to singular" error for narrow bands at high Fs
    
    if length(data) < 3*(Fs/rng(1))
        fd = data; 
        return; 
    end
    
    order = 3;
    [z, p, k] = butter(order, rng/(Fs/2), 'bandpass');
    [sos, g] = zp2sos(z, p, k);
    fd = filtfilt(sos, g, data);
end