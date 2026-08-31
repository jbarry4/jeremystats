function Pipeline_main_loop(parentFolder)
% Pipeline_main_loop
% Takes a parent directory and runs Pipeline_Main for every subfolder.
% Collects the primary outputs from each run into a single
% 'Collected_results' folder.

% ---------- 1. Setup Collected Results Folder ----------
collectedDirName = 'Collected_results';
collectedDir = fullfile(parentFolder, collectedDirName);

if ~exist(collectedDir, 'dir')
    fprintf('Creating collection folder: %s\n', collectedDir);
    mkdir(collectedDir);
else
    fprintf('Collection folder already exists: %s\n', collectedDir);
end

% ---------- 2. Find All Subfolders ----------
d = dir(parentFolder);
subFolders = d([d.isdir]); % Get only directory items

fprintf('\nFound %d total directory items. Starting loop...\n', numel(subFolders));
fprintf('========================================================\n\n');

% ---------- 3. Loop Through Subfolders ----------
for i = 1:numel(subFolders)
    folderName = subFolders(i).name;
    
    % --- Logic to skip self, parent, and the collected folder ---
    if ismember(folderName, {'.', '..', collectedDirName})
        fprintf('Skipping directory: %s\n', folderName);
        fprintf('--------------------------------------------------------\n');
        continue;
    end
    
    currentFolder = fullfile(parentFolder, folderName);
    fprintf('===== PROCESSING: %s =====\n', folderName);
    
    % ---------- 4. Run Pipeline_Main on the Subfolder ----------
    try
        % Pass the subfolder path to the main pipeline
        Pipeline_Main(currentFolder);
        
        fprintf('  [SUCCESS] Pipeline_Main finished for %s.\n', folderName);
        
    catch ME
        fprintf('  [FAILED] Pipeline_Main crashed for %s.\n', folderName);
        fprintf('    Error: %s\n', ME.message);
        fprintf('    Skipping result collection for this folder.\n');
        fprintf('========================================================\n\n');
        continue; % Skip to the next folder
    end
    
    % ---------- 5. Collect and Rename Results ----------
    fprintf('  [INFO] Collecting results for %s...\n', folderName);
    outputDir = fullfile(currentFolder, 'Pipeline Output');
    
    if ~isfolder(outputDir)
        fprintf('    [WARN] No "Pipeline Output" folder found for %s.\n', folderName);
        fprintf('    Skipping result collection for this folder.\n');
        fprintf('========================================================\n\n');
        continue;
    end
    
    % Define files to copy and their new names
    filesToCopy = { ...
      'Master_Compact_SOLID.png',   [folderName '_Master_Compact_SOLID.png']; ...
      'Master_Compact_SPUTTER.png', [folderName '_Master_Compact_SPUTTER.png']; ...
      'Master_Stats.csv',         [folderName '_Master_Stats.csv'] ...
    };
    
    nCopied = 0;
    for j = 1:size(filesToCopy, 1)
        sourceFile = fullfile(outputDir, filesToCopy{j, 1});
        destFile   = fullfile(collectedDir, filesToCopy{j, 2});
        
        if isfile(sourceFile)
            try
                copyfile(sourceFile, destFile);
                fprintf('    -> Copied: %s\n', filesToCopy{j, 2});
                nCopied = nCopied + 1;
            catch copyME
                fprintf('    [WARN] Failed to copy %s: %s\n', filesToCopy{j, 1}, copyME.message);
            end
        else
            fprintf('    [INFO] Output file not found, skipping: %s\n', filesToCopy{j, 1});
        end
    end
    
    fprintf('  [INFO] Collected %d result files for %s.\n', nCopied, folderName);
    fprintf('========================================================\n\n');

end % End of for-loop

fprintf('===== Pipeline_main_loop COMPLETE =====\n');
fprintf('All results collected in: %s\n', collectedDir);

end