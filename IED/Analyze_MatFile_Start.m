function Analyze_MatFile_Snippets(matFilePath, varargin)
% Analyze_MatFile_Snippets(matFilePath, 'nSamplesToInspect', 200)
%
% READ-ONLY diagnostic script to analyze the start of a disk-backed .mat file.
% This script finds the first data, total samples per channel, and prints a
% snippet of the initial data and its statistics.
%
% INPUT:
%   matFilePath : Full path to the .mat file to analyze.
%
% OPTIONS (Name,Value):
%   'nSamplesToInspect' (default 200): How many samples to read for the
%                                     statistics and snippet preview.

%% ---------- Parse Inputs ----------
p = inputParser;
p.addRequired('matFilePath', @(s) ischar(s) || isstring(s));
p.addParameter('nSamplesToInspect', 200, @(x) isnumeric(x) && isscalar(x) && x > 0);
p.parse(matFilePath, varargin{:});

matFilePath = p.Results.matFilePath;
nSamplesToInspect = p.Results.nSamplesToInspect;
nSnippetPreview = 20; % How many numbers to print in the preview

%% ---------- Setup and File Check ----------
fprintf('\n[DIAG] Starting Matfile Snippet Analyzer\n');

if ~isfile(matFilePath)
    error('[DIAG-ERROR] File not found: %s', matFilePath);
end

try
    fprintf('[DIAG] Loading matfile object: %s\n', matFilePath);
    m = matfile(matFilePath);
catch ME
    fprintf('\n[DIAG-ERROR] Could not open file. Is it a valid .mat file?\n');
    fprintf('Error details: %s\n', ME.message);
    return;
end

%% ---------- 1. Basic File Overview ----------
fprintf('\n[DIAG] --- 1. Basic File Overview ---\n');

try
    [nChannels, nSamples] = size(m, 'd');
    sfx = m.sfx;
    kept_channels = m.kept_channels;
    units = m.units;
    
    fprintf('  File Path: %s\n', m.Properties.Source);
    fprintf('  Data Variable (d): [%d x %d] (Total Matrix Size)\n', nChannels, nSamples);
    fprintf('  Data Class: %s\n', class(m.d(1,1)));
    fprintf('  Sampling Rate (sfx): %g Hz\n', sfx);
    fprintf('  Units (units): %s\n', units);
    fprintf('  Kept Channels: %d channels (IDs: %s...)\n', ...
        nChannels, mat2str(kept_channels(1:min(10,nChannels))));
    
catch ME
    fprintf('\n[DIAG-ERROR] Could not read expected variables (d, sfx, kept_channels, units).\n');
    fprintf('Error details: %s\n', ME.message);
    return;
end

%% ---------- 2. Per-Channel Data Start Analysis & Snippet ----------
fprintf('\n[DIAG] --- 2. Per-Channel Data Start Analysis ---\n');
fprintf('       (Scanning for data and printing snippets...)\n\n');

chunkSize = 5000000; % 5 million samples per chunk for scanning

% Store results
allFirstData = nan(nChannels, 1);
allFirstNonZero = nan(nChannels, 1);
allTotalSamples = nan(nChannels, 1); % <-- NEW: To store total sample count

tic; 
for i = 1:nChannels
    channelID = kept_channels(i);
    fprintf('  --- Analyzing Row %d (CSC%d) ---\n', i, channelID);
    
    % --- STEP 1: Find first non-NaN value ---
    firstNonNaNIndex = NaN;
    startSample = 1;
    while startSample <= nSamples
        endSample = min(startSample + chunkSize - 1, nSamples);
        dataChunk = m.d(i, startSample:endSample);
        firstInChunk = find(~isnan(dataChunk), 1, 'first');
        if ~isempty(firstInChunk)
            firstNonNaNIndex = startSample + firstInChunk - 1;
            break; 
        end
        startSample = endSample + 1;
    end
    
    if isnan(firstNonNaNIndex)
        fprintf('    [WARN] No data found. Channel is ALL NaN.\n');
        allTotalSamples(i) = 0; % Store 0 if all NaN
        fprintf('\n'); % Add space before next channel
        continue;
    else
        fprintf('    [INFO] First non-NaN data point found at sample: %d\n', firstNonNaNIndex);
        allFirstData(i) = firstNonNaNIndex;
    end

    % --- NEW: STEP 1b: Find last non-NaN value (total sample count) ---
    lastNonNaNIndex = NaN;
    currentEndSample = nSamples; % Start from the very end
    while currentEndSample >= 1
        currentStartSample = max(1, currentEndSample - chunkSize + 1);
        
        % Read one chunk from the end
        dataChunk = m.d(i, currentStartSample:currentEndSample);
        
        % Find the LAST non-NaN value in this chunk
        lastInChunk = find(~isnan(dataChunk), 1, 'last');
        
        if ~isempty(lastInChunk)
            % Found it! Calculate its absolute index.
            lastNonNaNIndex = currentStartSample + lastInChunk - 1;
            break; % Stop searching
        end
        
        % If not found, move to the next chunk (backwards)
        currentEndSample = currentStartSample - 1;
    end
    
    if isnan(lastNonNaNIndex)
        fprintf('    [INFO] Total valid samples found (last non-NaN): 0\n');
        allTotalSamples(i) = 0;
    else
        fprintf('    [INFO] Total valid samples found (last non-NaN): %d\n', lastNonNaNIndex);
        allTotalSamples(i) = lastNonNaNIndex;
    end

    
    % --- STEP 2: Find first non-zero value (start from where we found data) ---
    firstNonZeroIndex = NaN;
    startSample = firstNonNaNIndex; % Start from the first data point
    while startSample <= lastNonNaNIndex % Only search up to the last valid sample
        endSample = min(startSample + chunkSize - 1, lastNonNaNIndex);
        dataChunk = m.d(i, startSample:endSample);
        
        firstInChunk = find(dataChunk ~= 0, 1, 'first');
        if ~isempty(firstInChunk)
            firstNonZeroIndex = startSample + firstInChunk - 1;
            break;
        end
        
        % If this chunk was all zeros, move to the next one
        startSample = endSample + 1;
    end
    
    if isnan(firstNonZeroIndex)
        fprintf('    [WARN] Data found, but is ALL ZEROS from sample %d onward.\n', firstNonNaNIndex);
    else
        fprintf('    [INFO] First non-zero data point found at sample: %d\n', firstNonZeroIndex);
        allFirstNonZero(i) = firstNonZeroIndex;
    end

    % --- STEP 3: Print Data Snippet ---
    snippetStart = firstNonNaNIndex;
    snippetEnd = min(snippetStart + nSamplesToInspect - 1, lastNonNaNIndex);
    snippetLength = snippetEnd - snippetStart + 1;
    
    if snippetLength <= 0
        fprintf('    [SNIPPET] No data to display.\n');
    else
        dataSnippet = m.d(i, snippetStart:snippetEnd);
        
        % 1. Display the first few values
        nToDisplay = min(nSnippetPreview, snippetLength);
        fprintf('    [SNIPPET] First %d values (of %d inspected, starting at sample %d):\n', ...
            nToDisplay, snippetLength, snippetStart);
        fprintf('      %s\n', mat2str(dataSnippet(1:nToDisplay), 4));
        
        % 2. Display statistics for the whole snippet
        meanVal = mean(dataSnippet, 'omitnan');
        minVal = min(dataSnippet);
        maxVal = max(dataSnippet);
        fprintf('      Stats for %d samples: Min=%.4f, Max=%.4f, Mean=%.4f\n', ...
            snippetLength, minVal, maxVal, meanVal);
    end
    fprintf('\n'); % Add space before next channel
    
end
toc;

%% ---------- 3. Final Summary ----------
fprintf('\n[DIAG] --- 3. Analysis Summary ---\n');

% --- First Non-NaN Summary ---
minDataStart = min(allFirstData);
maxDataStart = max(allFirstData);
fprintf('  First Non-NaN Data (Actual Recording Start):\n');
if isnan(minDataStart)
    fprintf('    [!!] No data found in any channel (all NaN).\n');
else
    fprintf('    Earliest data point in any channel: sample %d\n', minDataStart);
    fprintf('    Latest data point in any channel:   sample %d\n', maxDataStart);
    if minDataStart == maxDataStart
        fprintf('    [OK] All channels are aligned (start at sample %d).\n', minDataStart);
    else
        fprintf('    [WARN] Channels are MISALIGNED. Start times range from %d to %d.\n', minDataStart, maxDataStart);
    end
end

% --- First Non-Zero Summary ---
minNonZeroStart = min(allFirstNonZero);
maxNonZeroStart = max(allFirstNonZero);
fprintf('\n  First Non-Zero Data (Ignoring leading zeros):\n');
if isnan(minNonZeroStart)
    fprintf('    [!!] No non-zero data found in any channel.\n');
else
    fprintf('    Earliest non-zero data point: sample %d\n', minNonZeroStart);
    fprintf('    Latest non-zero data point:   sample %d\n', maxNonZeroStart);
    if minNonZeroStart == maxNonZeroStart
        fprintf('    [OK] All channels have non-zero data by sample %d.\n', minNonZeroStart);
    else
        fprintf('    [WARN] Channels have different non-zero start times (from %d to %d).\n', minNonZeroStart, maxNonZeroStart);
    end
end

% --- NEW: Total Valid Samples Summary ---
fprintf('\n  Total Valid Samples (based on last non-NaN):\n');
minSamples = min(allTotalSamples);
maxSamples = max(allTotalSamples);

if isnan(minSamples) || maxSamples == 0
    fprintf('    [!!] No valid samples found in any channel.\n');
else
    fprintf('    Shortest channel: %d samples\n', minSamples);
    fprintf('    Longest channel:  %d samples\n', maxSamples);
    if minSamples == maxSamples
        fprintf('    [OK] All channels have an equal sample count (%d).\n', minSamples);
    else
        fprintf('    [WARN] Channels have MISMATCHED sample counts. Range from %d to %d.\F\n', minSamples, maxSamples);
        fprintf('    (This means some channels are padded with more NaNs at the end than others).\n');
    end
end


fprintf('\n[DIAG] Analysis complete.\n');

end