% --- BATCH SCRIPT START ---

% 1. Define the base input folder.
%    - If your files are in the current working directory, use 'pwd'.
%    - If they are in a specific folder, replace 'pwd' with the folder path
%      (e.g., 'C:\MyData\2024\Exp1\').
inputFolder = pwd;

% 2. Loop through files CS1.ncs to CS64.ncs
for i = 1:64
    % Construct the current file name (e.g., 'CS1.ncs', 'CS2.ncs', etc.)
    currentFileName = sprintf('CS%d.ncs', i);
    
    % Define the full path to the input and output files.
    ncsFilePath = fullfile(inputFolder, currentFileName);
    
    % Use fileparts to get the name without extension for the output .mat file
    [folder, name, ~] = fileparts(ncsFilePath);
    matFilePath = fullfile(folder, [name '.mat']);

    % 3. Check if the input file exists.
    if ~exist(ncsFilePath, 'file')
        fprintf('⚠️ Skipping: File not found: %s\n', ncsFilePath);
        continue; % Skip to the next iteration of the loop
    end

    % 4. Call the Nlx2MatCSC() function.
    fprintf('\n--- Processing file %d of 64: %s ---\n', i, currentFileName);
    fprintf('Reading data from %s...\n', ncsFilePath);
    
    try
        [Timestamps, ScNumbers, SampleFrequencies, NumberOfValidSamples, Samples, Header] = ...
            Nlx2MatCSC(ncsFilePath, [1 1 1 1 1], 1, 1, []);
        
        % 5. Save the retrieved data to the specified .mat file path.
        fprintf('Saving data to %s...\n', matFilePath);
        save(matFilePath, 'Timestamps', 'ScNumbers', 'SampleFrequencies', ...
            'NumberOfValidSamples', 'Samples', 'Header');
        
        % 6. Display a success message.
        fprintf('✅ Conversion complete for %s! Data saved successfully.\n', currentFileName);
        
    catch ME
        % Error handling for Nlx2MatCSC or save function
        fprintf('❌ An error occurred while processing %s: %s\n', currentFileName, ME.message);
        continue; % Move to the next file
    end
end

fprintf('\n--- BATCH PROCESSING COMPLETE ---\n');

% --- BATCH SCRIPT END ---