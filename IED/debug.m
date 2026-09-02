%% Analyze NaN Statistics and Blocks from a Large .mat File
%
% This script analyzes a .mat file containing a large data matrix 'd'
% (channels x samples) and a sampling frequency 'sfx'.
%
% It is designed to be memory-efficient by loading one channel (row) at a
% time.
%
% For each channel, it calculates:
% 1. The total percentage of NaN values.
% 2. A list of all consecutive "blocks" of NaNs, with their start/end
%    times in seconds.
%
clc;
clear;
close all;

%% --- User Settings ---

% Set to true to use a pop-up dialog to find the file.
% Set to false to specify the path manually below.
USE_UI_FILE_PICKER = true;

% Manual path (only used if USE_UI_FILE_PICKER is false)
% Example: matFilePath = 'C:\my_data\my_file.mat';
matFilePath = 'C:\path\to\your\data.mat'; 

% Limit the number of blocks printed per channel to avoid flooding the console
maxBlocksToShow = 50; 

% --- End User Settings ---

%% 1. Get and Validate File
if USE_UI_FILE_PICKER
    [fileName, folderPath] = uigetfile('*.mat', 'Select your .mat data file');
    if isequal(fileName, 0)
        disp('User canceled file selection.');
        return;
    end
    matFilePath = fullfile(folderPath, fileName);
end

fprintf('Analyzing file: %s\n', matFilePath);

if ~isfile(matFilePath)
    error('File not found: %s', matFilePath);
end

%% 2. Load Metadata (Safely)
try
    % Use matfile to access the file properties without loading it all
    mf = matfile(matFilePath);
catch ME
    error('Could not open .mat file. Error: %s', ME.message);
end

% Check for required variables 'd' and 'sfx'
if ~isprop(mf, 'd')
    error('File does not contain a variable named "d".');
end
if ~isprop(mf, 'sfx')
    warning('File does not contain a variable named "sfx". Timestamps will be in SAMPLES, not seconds.');
    sfx = 1; % Use 1 to report in samples
else
    sfx = mf.sfx; % Load *just* the sfx variable
end

% Get dimensions from the matfile object
[nChannels, nTotalSamples] = size(mf, 'd');

fprintf('File contains %d channels and %d total samples.\n', nChannels, nTotalSamples);
fprintf('Using sampling frequency (sfx): %.1f Hz\n', sfx);

%% 3. Process Each Channel
for i = 1:nChannels
    fprintf('\n%s\n--- Analyzing Channel %d ---\n%s\n', repmat('=', 1, 30), i, repmat('=', 1, 30));
    
    % --- Load Data for THIS Channel ---
    fprintf('  Loading data for channel %d...\n', i);
    try
        % This loads ONLY row 'i' into memory
        channelData = mf.d(i, :); 
        fprintf('  Loading complete.\n');
    catch ME
        fprintf('  ERROR: Could not load data for channel %d. Skipping. Error: %s\n', i, ME.message);
        continue;
    end

    % --- Task 1: Calculate NaN Percentage ---
    isNanVec = isnan(channelData);
    nNaN = sum(isNanVec);
    pctNaN = (nNaN / nTotalSamples) * 100;
    
    fprintf('  NaN Stats: %d / %d samples are NaN (%.4f %%)\n', nNaN, nTotalSamples, pctNaN);

    % --- Task 2: Find NaN Blocks ---
    if nNaN == 0
        fprintf('  No NaN blocks found.\n');
        continue; % Go to the next channel
    end
    
    if nNaN == nTotalSamples
        fprintf('  *** This entire channel is NaN. ***\n');
        continue; % Go to the next channel
    end

    fprintf('  Finding NaN blocks...\n');
    
    % Find starts and ends of blocks
    % We pad with 0 to catch blocks at the very start or end
    d = diff([0, isNanVec, 0]);
    
    % A '1' in d means a block started
    blockStarts_idx = find(d == 1);
    
    % A '-1' in d means a block ended (at the *previous* index)
    blockEnds_idx = find(d == -1) - 1;
    
    nBlocks = numel(blockStarts_idx);
    fprintf('  Found %d distinct NaN block(s).\n\n', nBlocks);

    % --- Report Blocks ---
    for b = 1:nBlocks
        if b > maxBlocksToShow
            fprintf('  ...and %d more blocks (not shown).\n', nBlocks - maxBlocksToShow);
            break;
        end
        
        startIdx = blockStarts_idx(b);
        endIdx = blockEnds_idx(b);
        
        % Calculate times
        durationSamples = endIdx - startIdx + 1;
        startTime_s = (startIdx - 1) / sfx; % -1 because 1st sample is at time 0
        endTime_s = endIdx / sfx; % End time of the last bad sample
        duration_s = durationSamples / sfx;
        
        fprintf('  Block %d:\n', b);
        fprintf('    Samples: %d to %d\n', startIdx, endIdx);
        fprintf('    Time:    %.3f s to %.3f s\n', startTime_s, endTime_s);
        fprintf('    Duration: %d samples (%.3f s)\n\n', durationSamples, duration_s);
    end
    
end % End of channel loop

fprintf('\n%s\nAnalysis complete.\n%s\n', repmat('=', 1, 30), repmat('=', 1, 30));