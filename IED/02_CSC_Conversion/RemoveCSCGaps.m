function RemoveCSCGaps()
% RemoveCSCGaps_Final
% Fixed based on Neuralynx v5.0.1 Documentation.
% REMOVED 'NumRecs' argument from Mat2NlxCSC call.

    % --- 0. Path Setup ---
    scriptDir = fileparts(mfilename('fullpath'));
    reqsPath = fullfile(scriptDir, 'reqsPath');
    if exist(reqsPath, 'dir'), addpath(reqsPath); end

    % --- 1. Select Data Folder ---
    folder_path = uigetdir(pwd, 'Select Folder containing CSC .ncs files');
    if folder_path == 0, return; end

    % Change Directory to handle paths safely
    original_dir = pwd;
    cd(folder_path);
    cleanupObj = onCleanup(@() cd(original_dir)); 

    fprintf('Working Directory: %s\n', pwd);

    file_list = dir('*.ncs');
    if isempty(file_list), disp('No .ncs files found.'); return; end

    fprintf('Found %d files. Processing...\n', length(file_list));
    
    % --- 2. Loop through files ---
    for i = 1:length(file_list)
        original_filename = file_list(i).name;
        
        % Skip output files
        if contains(original_filename, '_Clean')
            continue; 
        end
        
        [~, name, ext] = fileparts(original_filename);
        clean_filename = [name, '_Clean', ext];
        
        fprintf('\nPROCESSING: %s', original_filename);
        
        try
            % --- 3. Load Data ---
            % [TS, Ch, Freq, Val, Samp, Header]
            [Timestamps, ChannelNums, SampleFreqs, ValidSamples, Samples, Header] = ...
                Nlx2MatCSC(original_filename, [1 1 1 1 1], 1, 1, []);
            
            % --- 4. Identify & Remove Gaps ---
            bad_indices = find(ValidSamples < 512);
            if isempty(bad_indices)
                fprintf(' -> No gaps. Skipping.\n');
                continue;
            end
            
            fprintf(' -> Found %d gaps. Cleaning... ', length(bad_indices));
            
            Timestamps(bad_indices) = [];
            ChannelNums(bad_indices) = [];
            SampleFreqs(bad_indices) = [];
            ValidSamples(bad_indices) = [];
            Samples(:, bad_indices) = []; 
            
            % --- 5. DATA SANITIZATION (Strictly enforce Doc specs) ---
            % Doc: "1xN vector" for 1D arrays
            if size(Timestamps, 1) > 1, Timestamps = Timestamps'; end
            if size(ChannelNums, 1) > 1, ChannelNums = ChannelNums'; end
            if size(SampleFreqs, 1) > 1, SampleFreqs = SampleFreqs'; end
            if size(ValidSamples, 1) > 1, ValidSamples = ValidSamples'; end
            
            % Doc: "512xN matrix" for Samples
            if size(Samples, 1) ~= 512
                 Samples = Samples'; 
            end

            % Ensure Header is present
            if isempty(Header)
                Header = {'######## Neuralynx Data File Header ########'; ...
                          '## File: Matlab Converted'};
            end

            % --- 6. WRITE (Corrected Argument List) ---
            if exist(clean_filename, 'file'), delete(clean_filename); end
            
            % Argument Mapping based on v5.0.1 Doc:
            % 1. FileName
            % 2. AppendToFileFlag (0)
            % 3. ExportMode (1)
            % 4. ExportModeVector (1)
            % 5. FieldSelectionFlags ([1 1 1 1 1 1])
            % 6+. Data Variables...
            
            Mat2NlxCSC(clean_filename, 0, 1, 1, [1 1 1 1 1 1], ...
                       Timestamps, ChannelNums, SampleFreqs, ValidSamples, Samples, Header);
                       
            fprintf('Saved.\n');

        catch ME
            fprintf('\nERROR: %s\n', ME.message);
        end
    end
    fprintf('\nDone.\n');
end