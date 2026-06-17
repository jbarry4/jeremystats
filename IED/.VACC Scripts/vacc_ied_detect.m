function vacc_ied_detect(basePath, eightBad)
% vacc_ied_detect.m — minimal, folder-based IED batch detector (single-precision)
% Runs on 'basePath' and writes ets.mat / ech.mat back there.
%
% --- VERSION 2: MODIFIED TO HANDLE TIME GAPS ---
% This version correctly pads the data matrix 'd' with NaNs to account for
% timestamp irregularities (gaps/overlaps) found in fragmented Ncs files.
% It determines a global time-span and "places" data records onto this
% timeline, rather than simply concatenating them, before running the
% spike detector.
%
% INPUTS:
%   basePath: (string) Full path to the directory containing CSC*.ncs files.
%   eightBad: (logical) If true, replace CSC8.ncs with CSC9.ncs in the analysis.

% basePath is now the data directory
dataDir = basePath; 

% Setup paths relative to this script's location
baseScriptDir = fileparts(mfilename('fullpath'));
 
% Add required deps (LLspikedetector.m, Nlx2MatCSC.m/.mexa64)
addpath(baseScriptDir);
% --- MODIFIED: Made reqsPath relative to this script ---
addpath(fullfile(baseScriptDir, "reqsPath")); % contains Nlx2MatCSC.*
fprintf('[INFO] Added script directory to path: %s\n', baseScriptDir);

% Find all CSC files in the specified basePath
files = dir(fullfile(dataDir, 'CSC*.ncs'));
if isempty(files)
    error('No .ncs files found in: %s', dataDir);
end

% --- Channel selection logic (Unchanged) ---
names = {files.name};
nums  = cellfun(@(s) sscanf(s,'CSC%d.ncs'), names);
 
isValidNum = ~isnan(nums);
isEven = mod(nums, 2) == 0;
isCSC8 = (nums == 8);
isCSC9 = (nums == 9);

keep_mask = isEven & isValidNum;
 
nTotalCh = numel(files);
 
fprintf('[INFO] Total .ncs files found: %d\n', nTotalCh);

if eightBad
    fprintf('[INFO] eightBad flag is TRUE.\n');
    isChannel8Kept = any(keep_mask & isCSC8);
    fprintf('[INFO] isChannel8Kept (based on even filter): %d\n', isChannel8Kept);
    
    if isChannel8Kept
        fprintf('[INFO] Replacing CSC8.ncs with CSC9.ncs.\n');
        keep_mask = keep_mask & ~isCSC8;
        
        if any(isCSC9 & isValidNum)
            keep_mask = keep_mask | (isCSC9 & isValidNum);
        else
            fprintf('[WARN] eightBad is true and CSC8 was kept, but CSC9.ncs does not exist in the folder. CSC8 will be excluded and not replaced.\n');
        end
    end
else
    fprintf('[INFO] eightBad flag is FALSE. Standard even channel selection.\n');
end

files_to_process = files(keep_mask);
 
kept_channels_info = nums(keep_mask);

[sorted_channel_nums, sort_indices] = sort(kept_channels_info);
 
files_to_process = files_to_process(sort_indices);
kept_channels_info = sorted_channel_nums; 
fprintf('[INFO] Files sorted by channel number.\n');

numberOfKeptChannels = numel(files_to_process);

if numberOfKeptChannels == 0
    error('[ERROR] No channels selected to keep after filtering. Check data and flags.'); 
end
 
fprintf('[INFO] Channels to include: %d\n', numberOfKeptChannels);
fprintf('[INFO] Kept channels (file numbers): %s\n', mat2str(kept_channels_info(1:min(10,numberOfKeptChannels))));
% --- End channel selection ---


% -------------------------------------------------------------------------
% --- NEW PASS 1: Read ALL data and metadata to find global time range ---
% This replaces the old, broken loading loop
% -------------------------------------------------------------------------
fprintf('[INFO] Pass 1: Scanning metadata for %d files...\n', numberOfKeptChannels);

% --- NEW: Storage for timing info ---
S_meta = cell(1, numberOfKeptChannels); % Will store metadata for each file
all_first_T_us = nan(1, numberOfKeptChannels);
all_last_T_us_plus_duration = nan(1, numberOfKeptChannels);
all_samplingRates = nan(1, numberOfKeptChannels);

for k = 1:numberOfKeptChannels
    fn = fullfile(files_to_process(k).folder, files_to_process(k).name);
    fprintf('       Scanning %s\n', files_to_process(k).name);

    % Read ALL fields: [Timestamps, Chan#, Fs, NValid, Samples]
    % No header (0), Extract All (1)
    [timestamps_us, ~, sampleFrequencies, numberValidSamples, samplesAD] = ...
        Nlx2MatCSC(fn, [1 1 1 1 1], 0, 1, []);
    
    % Store the data we need for Pass 2
    S_meta{k}.timestamps_us = timestamps_us;
    S_meta{k}.numberValidSamples = numberValidSamples;
    S_meta{k}.samplesAD = samplesAD; % Store raw AD data

    % --- Get Sampling Rate ---
    samplingRateThis = mode(double(sampleFrequencies(sampleFrequencies>0)));
    if ~(isfinite(samplingRateThis) && samplingRateThis>0)
        % Fallback: Try to get from Nlx header (if we had read it)
        % For this script, we'll just assume 30k if missing
        samplingRateThis = 30000; 
        fprintf('[WARN] Could not read Fs for %s, assuming %.0f Hz\n', files_to_process(k).name, samplingRateThis);
    end
    all_samplingRates(k) = samplingRateThis;
    
    % --- Calculate start and end time for this channel ---
    if ~isempty(timestamps_us)
        all_first_T_us(k) = timestamps_us(1);
        samples_per_us = samplingRateThis / 1e6;
        
        duration_of_last_record_us = (double(numberValidSamples(end)) - 1) / samples_per_us;
        all_last_T_us_plus_duration(k) = double(timestamps_us(end)) + duration_of_last_record_us;
    
        % Optional continuity check
        expectedStep_us = 512 * (1e6 / samplingRateThis);
        deltaT = diff(double(timestamps_us));
        if any(abs(deltaT - expectedStep_us) > 0.5 * expectedStep_us)
            fprintf('[WARN] Timing irregularity in %s. Gaps will be NaN-padded.\n', files_to_process(k).name);
        end
    else
        fprintf('[WARN] No timestamps found for %s.\n', files_to_process(k).name);
    end
end
fprintf('[INFO] Pass 1 scan complete.\n');

% -------------------------------------------------------------------------
% --- NEW: Global Time Calculation & Array Prep ---
% -------------------------------------------------------------------------

% --- MODIFIED: Use *actual* sfx, not hardcoded one ---
goodMask = isfinite(all_samplingRates);
if ~any(goodMask)
    error('[ERROR] No valid sampling frequency could be determined from any file.');
end
sfx = mode(round(all_samplingRates(goodMask)));
fprintf('[INFO] Unified sampling rate (mode across good channels): %g Hz\n', sfx);

% Calculate global time-span and total samples
global_min_T_us = min(all_first_T_us(goodMask));
global_max_T_us = max(all_last_T_us_plus_duration(goodMask));
total_duration_us = global_max_T_us - global_min_T_us;
samples_per_us = sfx / 1e6;

% This is the NEW total number of samples for the *entire* duration
maxSamples = round(total_duration_us * samples_per_us) + 1;

fprintf('[INFO] Global time-span: %.2f s (from %.2f s to %.2f s)\n', ...
    total_duration_us/1e6, global_min_T_us/1e6, global_max_T_us/1e6);

% --- MODIFIED: Pre-allocate with single NaNs ---
% This replaces the old "Pad to rectangle" section
fprintf('[INFO] Allocating [ %d x %d ] matrix with NaN padding...\n', ...
    numberOfKeptChannels, maxSamples);
d = single(NaN(numberOfKeptChannels, maxSamples));


% -------------------------------------------------------------------------
% --- NEW PASS 2: Place data onto time-aligned NaN grid ---
% -------------------------------------------------------------------------
fprintf('[INFO] Pass 2: Reconstructing data with NaN-padding...\n');

for k = 1:numberOfKeptChannels
    % Get the data we stored from Pass 1
    meta = S_meta{k};
    if isempty(meta) || isempty(meta.timestamps_us)
        fprintf('       Skipping row %d (no data from Pass 1)\n', k);
        continue;
    end
    
    timestamps_us = meta.timestamps_us;
    numberValidSamples = meta.numberValidSamples;
    samplesAD = meta.samplesAD;
    
    recordBlockLength = size(samplesAD,1);
    numberOfRecords   = size(samplesAD,2);
    
    % --- NEW: Gap-filling loop ---
    for recordIndex = 1:numberOfRecords
        validCount = min(recordBlockLength, max(0, numberValidSamples(recordIndex)));
        if validCount == 0, continue; end

        % Get data for this record
        recordDataAD = double(samplesAD(1:validCount, recordIndex));

        % --- Apply original script's logic: INVERT and cast to SINGLE ---
        recordData_inverted = single(-recordDataAD);
        
        % Calculate precise start/end sample indices for this chunk
        record_start_T_us = double(timestamps_us(recordIndex));
        time_from_global_start_us = record_start_T_us - global_min_T_us;
        
        start_sample_index = round(time_from_global_start_us * samples_per_us) + 1;
        end_sample_index = start_sample_index + validCount - 1;

        % --- Boundary check ---
        write_start_idx = max(1, start_sample_index);
        write_end_idx   = min(maxSamples, end_sample_index);
        
        data_start_idx = max(1, 1 - (start_sample_index - 1));
        data_end_idx   = validCount - (end_sample_index - write_end_idx);
        
        if write_start_idx > write_end_idx || data_start_idx > data_end_idx
           continue; 
        end
        
        % Place the chunk into the full NaN matrix
        % Note: d is (channel, time)
        d(k, write_start_idx:write_end_idx) = recordData_inverted(data_start_idx:data_end_idx);
    end
end
fprintf('[INFO] Pass 2 complete. Final matrix ''d'' is built.\n');

% --- Clear the large temporary metadata cell ---
clear S_meta;

% -------------------------------------------------------------------------
% --- Run Spike Detector (Logic is now safe to run) ---
% -------------------------------------------------------------------------

% Fixed params per request (sfx is now read from files)
llw = 0.04;          % 40 ms window
prc = 99.9;          % percentile threshold

fprintf('[INFO] Detecting spikes with sfx=%.1f, llw=%.3f, prc=%.1f...\n', sfx, llw, prc);
% Detect spikes (rows of ets are [on off] in samples; ech marks channels per event)
% LLspikedetector is already designed to handle NaNs perfectly.
[ets, ech] = LLspikedetector(d, sfx, llw, prc);
fprintf('[INFO] Spike detection complete. Found %d events.\n', size(ets, 1));

% Save outputs right next to data (in basePath)
output_ets_file = fullfile(dataDir, 'ets.mat');
output_ech_file = fullfile(dataDir, 'ech.mat');
 
fprintf('[INFO] Saving outputs to: %s\n', dataDir);
save(output_ets_file, 'ets');
save(output_ech_file, 'ech');
fprintf('[INFO] Save complete.\n');
end