function vacc_ied_highpass_detect(basePath, fiftyNineBad)
% vacc_ied_highpass_detect.m — IED batch detector with high-pass pre-filter
%
% --- VERSION 4: NESTED FOLDERS, FUZZY MATCHING & STRICT CH59 EXCLUSION ---
% Identical to vacc_ied_detect.m with the addition of a 1 Hz Butterworth
% high-pass filter applied to all channels before the line-length transform,
% to suppress slow oscillations that can inflate the LL threshold / cause
% false detections.

% Default fiftyNineBad to false if not provided
if nargin < 2
    fiftyNineBad = false;
end

%% ---------- Setup Paths & Toolboxes ----------
baseScriptDir = fileparts(mfilename('fullpath'));
addpath(baseScriptDir);
addpath(fullfile(baseScriptDir, "reqsPath"));
fprintf('\n[INFO] Starting vacc_ied_highpass_detect (v4 Nested Fuzzy-Match + HP filter)\n');
fprintf('[INFO] Base path: %s\n', basePath);

if ~isfolder(basePath)
    error('[ERROR] Base folder not found: %s', basePath);
end

%% ---------- Step into Subfolder ----------
subDirs = dir(basePath);
subDirs = subDirs([subDirs.isdir] & ~ismember({subDirs.name}, {'.', '..'}));

if isempty(subDirs)
    error('[ERROR] No data subfolders found inside base path: %s', basePath);
end

targetPath = fullfile(basePath, subDirs(1).name);
fprintf('[INFO] Target directory updated to subfolder: %s\n', targetPath);

%% ---------- File Matching & Channel Selection ----------
dirStruct = dir(fullfile(targetPath, 'CSC*.*'));
allNcsNames = {dirStruct.name};

    function fPath = findCscFile(chNum)
        % Matches: CSC<num>.ncs OR CSC<num>_001.ncs OR CSC<num>.nsc
        pat = ['^CSC0*', num2str(chNum), '([^0-9].*)?\.(ncs|nsc)$'];
        matchIdx = ~cellfun(@isempty, regexpi(allNcsNames, pat));
        matches = allNcsNames(matchIdx);
        if isempty(matches)
            fPath = '';
        else
            exactName = sprintf('CSC%d.ncs', chNum);
            exactIdx = strcmpi(matches, exactName);
            if any(exactIdx)
                fPath = fullfile(targetPath, matches{find(exactIdx,1)});
            else
                fPath = fullfile(targetPath, matches{1});
            end
        end
    end

% Scan standard channel range
allChannels = 1:64;
foundChannels = [];
foundPaths = strings(0);

for c = allChannels
    fp = findCscFile(c);
    if ~isempty(fp)
        foundChannels(end+1) = c;
        foundPaths(end+1) = string(fp);
    end
end

if isempty(foundChannels)
    error('[ERROR] No CSC files found in: %s', targetPath);
end

isCSC59 = (foundChannels == 59);

% Force all found channels to be kept initially
keep_mask = true(size(foundChannels));

% Process fiftyNineBad flag
if fiftyNineBad
    fprintf('[INFO] fiftyNineBad flag is TRUE. Strictly removing CSC59.\n');
    keep_mask = keep_mask & ~isCSC59;
else
    fprintf('[INFO] fiftyNineBad flag is FALSE. Keeping CSC59 (if found).\n');
end

kept_channels_info = foundChannels(keep_mask);
files_to_process = foundPaths(keep_mask);
numberOfKeptChannels = numel(kept_channels_info);

if numberOfKeptChannels == 0
    error('[ERROR] No channels selected to keep after filtering.');
end

fprintf('[INFO] Channels to include: %d\n', numberOfKeptChannels);
fprintf('[INFO] Kept channels: %s\n', mat2str(kept_channels_info(1:min(10,numberOfKeptChannels))));

%% ---------- PASS 1: Read metadata & global time range ----------
fprintf('\n[INFO] Pass 1: Scanning metadata for %d files...\n', numberOfKeptChannels);

S_meta = cell(1, numberOfKeptChannels);
all_first_T_us = nan(1, numberOfKeptChannels);
all_last_T_us_plus_duration = nan(1, numberOfKeptChannels);
all_samplingRates = nan(1, numberOfKeptChannels);

for k = 1:numberOfKeptChannels
    fn = char(files_to_process(k));
    [~, fNameOnly, fExt] = fileparts(fn);
    fprintf('        Scanning %s\n', [fNameOnly fExt]);

    [timestamps_us, ~, sampleFrequencies, numberValidSamples, samplesAD] = ...
        Nlx2MatCSC(fn, [1 1 1 1 1], 0, 1, []);

    S_meta{k}.timestamps_us = timestamps_us;
    S_meta{k}.numberValidSamples = numberValidSamples;
    S_meta{k}.samplesAD = samplesAD;

    samplingRateThis = mode(double(sampleFrequencies(sampleFrequencies>0)));
    if ~(isfinite(samplingRateThis) && samplingRateThis>0)
        samplingRateThis = 30000;
        fprintf('[WARN] Could not read Fs for %s, assuming %.0f Hz\n', [fNameOnly fExt], samplingRateThis);
    end
    all_samplingRates(k) = samplingRateThis;

    if ~isempty(timestamps_us)
        all_first_T_us(k) = timestamps_us(1);
        samples_per_us = samplingRateThis / 1e6;

        duration_of_last_record_us = (double(numberValidSamples(end)) - 1) / samples_per_us;
        all_last_T_us_plus_duration(k) = double(timestamps_us(end)) + duration_of_last_record_us;

        expectedStep_us = 512 * (1e6 / samplingRateThis);
        deltaT = diff(double(timestamps_us));
        if any(abs(deltaT - expectedStep_us) > 0.5 * expectedStep_us)
            fprintf('[WARN] Timing irregularity in %s. Gaps will be NaN-padded.\n', [fNameOnly fExt]);
        end
    else
        fprintf('[WARN] No timestamps found for %s.\n', [fNameOnly fExt]);
    end
end
fprintf('[INFO] Pass 1 scan complete.\n');

%% ---------- Global Time Calculation & Array Prep ----------
goodMask = isfinite(all_samplingRates);
if ~any(goodMask)
    error('[ERROR] No valid sampling frequency could be determined.');
end
sfx = mode(round(all_samplingRates(goodMask)));
fprintf('\n[INFO] Unified sampling rate: %g Hz\n', sfx);

global_min_T_us = min(all_first_T_us(goodMask));
global_max_T_us = max(all_last_T_us_plus_duration(goodMask));
total_duration_us = global_max_T_us - global_min_T_us;
samples_per_us = sfx / 1e6;

maxSamples = round(total_duration_us * samples_per_us) + 1;

fprintf('[INFO] Global time-span: %.2f s. Allocating [ %d x %d ] matrix...\n', ...
    total_duration_us/1e6, numberOfKeptChannels, maxSamples);

d = single(NaN(numberOfKeptChannels, maxSamples));

%% ---------- PASS 2: Place data onto time-aligned NaN grid ----------
fprintf('\n[INFO] Pass 2: Reconstructing data with NaN-padding...\n');

for k = 1:numberOfKeptChannels
    meta = S_meta{k};
    if isempty(meta) || isempty(meta.timestamps_us)
        continue;
    end

    timestamps_us = meta.timestamps_us;
    numberValidSamples = meta.numberValidSamples;
    samplesAD = meta.samplesAD;

    recordBlockLength = size(samplesAD,1);
    numberOfRecords   = size(samplesAD,2);

    for recordIndex = 1:numberOfRecords
        validCount = min(recordBlockLength, max(0, numberValidSamples(recordIndex)));
        if validCount == 0, continue; end

        recordDataAD = double(samplesAD(1:validCount, recordIndex));
        recordData_inverted = single(-recordDataAD);

        record_start_T_us = double(timestamps_us(recordIndex));
        time_from_global_start_us = record_start_T_us - global_min_T_us;

        start_sample_index = round(time_from_global_start_us * samples_per_us) + 1;
        end_sample_index = start_sample_index + validCount - 1;

        write_start_idx = max(1, start_sample_index);
        write_end_idx   = min(maxSamples, end_sample_index);

        data_start_idx = max(1, 1 - (start_sample_index - 1));
        data_end_idx   = validCount - (end_sample_index - write_end_idx);

        if write_start_idx > write_end_idx || data_start_idx > data_end_idx
           continue;
        end

        d(k, write_start_idx:write_end_idx) = recordData_inverted(data_start_idx:data_end_idx);
    end
end
fprintf('[INFO] Pass 2 complete.\n');

clear S_meta;

%% ---------- High-pass filter to remove slow oscillations ----------
% Zero-phase 4th-order Butterworth HPF at 1 Hz.
% NaN gaps are zero-filled before filtering and restored after, so gaps
% do not propagate through filtfilt.
hp_cutoff = 1.0;  % Hz
[b_hp, a_hp] = butter(4, hp_cutoff / (sfx/2), 'high');
fprintf('\n[INFO] Applying %.1f Hz high-pass filter to %d channels...\n', hp_cutoff, numberOfKeptChannels);

d_filt = d;
for k = 1:numberOfKeptChannels
    ch = double(d(k,:));
    nan_mask = isnan(ch);
    ch(nan_mask) = 0;
    ch = filtfilt(b_hp, a_hp, ch);
    ch(nan_mask) = NaN;
    d_filt(k,:) = single(ch);
end
fprintf('[INFO] High-pass filtering complete.\n');

clear d;

%% ---------- Spike Detection ----------
llw = 0.04;
prc = 99.9;

fprintf('\n[INFO] Detecting spikes with sfx=%.1f, llw=%.3f, prc=%.1f...\n', sfx, llw, prc);
[ets, ech] = LLspikedetector(d_filt, sfx, llw, prc);
fprintf('[INFO] Spike detection complete. Found %d events.\n', size(ets, 1));

output_ets_file = fullfile(basePath, 'ets_hippocampus_59rm_hp.mat');
output_ech_file = fullfile(basePath, 'ech_hippocampus_59rm_hp.mat');

fprintf('[INFO] Saving outputs to: %s\n', basePath);
save(output_ets_file, 'ets');
save(output_ech_file, 'ech');
fprintf('[INFO] Done.\n');
end
