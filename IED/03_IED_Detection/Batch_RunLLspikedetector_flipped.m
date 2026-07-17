function Batch_RunLLspikedetector_flipped()
% Batch processes all .mat files in a user-selected folder using LLspikedetector.
% For each file, it flips the signal polarity before running the detector.
% All outputs are saved to a new, timestamped subfolder.

%% -------------------- USER SETTINGS --------------------
% LLspikedetector parameters (applied to all files):
llw_sec = 0.040;     % line-length window in seconds (e.g., 40 ms)
prc_thr = 99.9;      % percentile threshold (e.g., 99.9)
% --------------------------------------------------------

% --- Step 1: Get Input Directory from User ---
inputFolder = uigetdir('', 'Select the folder containing your .mat files');
if inputFolder == 0
    disp('No folder selected. Aborting script.');
    return;
end
fprintf('Input folder selected:\n  %s\n', inputFolder);

% --- Step 2: Create a Unique Output Subfolder ---
timestamp = datestr(now, 'yyyymmdd_HHMMSS');
outputFolder = fullfile(inputFolder, sprintf('LLSpike_Output_%s', timestamp));
if ~isfolder(outputFolder)
    mkdir(outputFolder);
    fprintf('Created output folder:\n  %s\n', outputFolder);
else
    fprintf('Output folder already exists:\n  %s\n', outputFolder);
end

% --- Step 3: Find all .mat files to process ---
matFiles = dir(fullfile(inputFolder, '*.mat'));
if isempty(matFiles)
    fprintf('\nNo .mat files found in the selected directory. Nothing to do.\n');
    return;
end

numFiles = length(matFiles);
fprintf('\nFound %d .mat file(s) to process.\n', numFiles);

% --- Step 4: Loop Through and Process Each File ---
tBatch = tic;
for i = 1:numFiles
    inputFile = fullfile(inputFolder, matFiles(i).name);
    
    fprintf('\n------------------------------------------------------------\n');
    fprintf('Processing file %d of %d: %s\n', i, numFiles, matFiles(i).name);
    fprintf('------------------------------------------------------------\n');
    
    try
        % Pass the file and settings to the processing function
        processSingleFile(inputFile, outputFolder, llw_sec, prc_thr);
    catch ME
        % If one file fails, report the error and continue with the next
        fprintf('!!! ERROR processing file: %s\n', matFiles(i).name);
        fprintf('!!! Error Message: %s\n', ME.message);
        % For debugging, you can show the full stack trace
        % disp(ME.getReport());
    end
end

fprintf('\n============================================================\n');
fprintf('Batch processing complete.\n');
fprintf('Total time taken: %s\n', duration(0, 0, toc(tBatch), "Format", "hh:mm:ss"));
fprintf('All results saved in: %s\n', outputFolder);
fprintf('============================================================\n');

end

%% -------------------- PROCESSING FUNCTION --------------------
function processSingleFile(inMat, outDir, llw_sec, prc_thr)
% This function contains the core logic from the original single-file script.
% It loads, flips, processes, and saves the results for one .mat file.

tFile = tic;

% Open disk-backed file (fast metadata peek)
mf = matfile(inMat);

% Pull metadata
sfx = mf.sfx;
badch_full = mf.badch;
if isprop(mf, 'kept_channels')
    kept_channels = mf.kept_channels;
else
    kept_channels = 1:size(mf, 'd', 1);
end

nRows = size(mf, 'd', 1);
fprintf('  Loading data (%d channels)...\n', nRows);

% Load data rows into RAM as double
d = double(mf.d(:,:));

% --- FLIP THE SIGNAL POLARITY ---
d = -d;
fprintf('  Signal polarity flipped.\n');

% Build badch aligned to the rows we will load into memory
badch_rows = ismember(kept_channels, find(badch_full));

% Run the detector
fprintf('  Running LLspikedetector (llw=%.3f s, prc=%.3f)...\n', llw_sec, prc_thr);
[ets, ech] = LLspikedetector(d, sfx, llw_sec, prc_thr, badch_rows);

% Convert event sample indices to seconds
t_on = ets(:, 1) ./ sfx;
t_off = ets(:, 2) ./ sfx;
dur_s = t_off - t_on;

% Create a human-readable channel list for each event
chan_list = cell(size(ech, 1), 1);
for k = 1:size(ech, 1)
    active_rows = find(ech(k, :));
    chan_list{k} = strjoin(arrayfun(@(r) sprintf('CSC%d', kept_channels(r)), active_rows, 'UniformOutput', false), ',');
end

% Assemble a summary table
T = table(ets(:, 1), ets(:, 2), t_on, t_off, dur_s, chan_list, ...
    'VariableNames', {'on_samp', 'off_samp', 'on_sec', 'off_sec', 'duration_sec', 'channels'});

% Save outputs
[~, baseName, ~] = fileparts(inMat);
outMat = fullfile(outDir, sprintf('%s_LLspikes.mat', baseName));
outCsv = fullfile(outDir, sprintf('%s_LLspikes.csv', baseName));

params.llw_sec = llw_sec;
params.prc_thr = prc_thr;
params.sourceFile = inMat;

save(outMat, 'ets', 'ech', 'T', 'params', '-v7.3');
writetable(T, outCsv);

fprintf('  Detected %d spike event(s).\n', size(ets, 1));
fprintf('  Saved results to:\n    MAT: %s\n    CSV: %s\n', outMat, outCsv);

% Clean up temporary files that LLspikedetector may create
cleanup_LLtemps(pwd); % LLSpikedetector often saves to the current working directory

fprintf('  Finished in %s.\n', duration(0, 0, toc(tFile), "Format", "mm:ss.SS"));
end

%% -------------------- HELPER FUNCTION --------------------
function cleanup_LLtemps(dirPath)
% Deletes temporary files saved by LLspikedetector to avoid disk clutter.
cand = {'d.mat', 'L.mat', 'Lvec.mat', 'eON.mat', 'eOFF.mat'};
for i = 1:numel(cand)
    f = fullfile(dirPath, cand{i});
    if exist(f, 'file')
        try
            delete(f);
        catch
            % Suppress delete errors if file is locked
        end
    end
end
end