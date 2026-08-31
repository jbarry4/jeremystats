function diagData = diagnose_VACC_CSC_timing(basePath, eightBad, varargin)
% diagnose_VACC_CSC_timing(basePath, eightBad, Name,Value,...)
%
%   Takes the *exact same* inputs as VACC_CSC2MAT_uV_disk to help diagnose
%   timing, gaps, or interpolation problems.
%
%   This function performs *ONLY THE FIRST PASS* logic to:
%     1. Select channels (honoring 'eightBad', 'evenOnly', 'keep')
%     2. Read the header, timestamps, and NValidSamples for each record
%     3. *** NEW: Performs a detailed analysis of timestamp deltas and
%           NValidSample counts for each channel. ***
%     4. *** NEW: Prints a detailed [DIAG] summary to the log. ***
%
%   It DOES NOT:
%     - Perform the second pass (reading full samples)
%     - Write any .mat file
%
%   It RETURNS:
%     A struct 'diagData' containing the collected data, including:
%       - diagData.timestamps_us_per_record {cell}
%       - diagData.nValidSamples_per_record {cell}
%       - diagData.timingAnalysis {cell} <-- NEW: detailed analysis results
%       - ... and other metadata.
%
% Example (How to use):
%{
    basePath = '/gpfs2/scratch/sakhava1/Rec';
    eightBad = true;
    
    % Run the diagnostic function
    diagData = diagnose_VACC_CSC_timing(basePath, eightBad, ...
        'nTotalCh', 64, 'evenOnly', true);
    
    % --- NEW: Inspect the detailed analysis for the first kept channel ---
    idx = 1;
    channelNum = diagData.kept_channels(idx);
    sourceNum = diagData.sourceChannelsUsed(idx);
    
    fprintf('Inspecting analysis for kept channel %d (read from CSC%d.ncs)\n', ...
        channelNum, sourceNum);
    
    % Get the analysis struct for this channel
    analysis = diagData.timingAnalysis{idx};
    
    % Print the pre-formatted summary
    disp(analysis.summary);
    
    % --- What to look for ---
    % 1. Partial records *before* the end (a major problem for flattening)
    if ~isempty(analysis.partialRecords_not_last_idx)
        fprintf('[PROBLEM] Found %d partial records before the last record!\n', ...
            numel(analysis.partialRecords_not_last_idx));
        disp('Record indices:');
        disp(analysis.partialRecords_not_last_idx);
    else
        fprintf('[INFO] No partial records found before the end.\n');
    end

    % 2. Timestamp Gaps (indicates missing data)
    if analysis.nGaps > 0
        fprintf('[PROBLEM] Found %d timestamp gaps.\n', analysis.nGaps);
        
        % Get the actual gap sizes
        gapSizes_us = analysis.delta_T_us(analysis.gapIndices);
        fprintf('  Min/Max gap size (us): %.2f / %.2f\n', ...
            min(gapSizes_us), max(gapSizes_us));
        fprintf('  (Expected step was: %.2f us)\n', analysis.expectedStep_us);
    else
        fprintf('[INFO] No significant timestamp gaps found.\n');
    end
    
    % 3. Plot the timestamp deltas
    figure;
    plot(analysis.delta_T_us, '.-');
    hold on;
    yline(analysis.expectedStep_us, 'r--', 'Expected Step');
    plot(analysis.gapIndices, analysis.delta_T_us(analysis.gapIndices), ...
        'ro', 'MarkerSize', 8, 'DisplayName', 'Gaps');
    plot(analysis.overlapIndices, analysis.delta_T_us(analysis.overlapIndices), ...
        'm>', 'MarkerSize', 8, 'DisplayName', 'Overlaps');
    title(sprintf('Timestamp Deltas for CSC%d (from CSC%d)', channelNum, sourceNum));
    xlabel('Record Index');
    ylabel('Delta Timestamp (us)');
    legend('show');
    set(gca, 'YScale', 'log'); % Use log scale to see large gaps
%}

%% ---------- Parse inputs (Identical to original) ----------
fprintf('\n[INFO] Starting DIAGNOSTIC pass (v3)...\n');

inputParserObject = inputParser;
inputParserObject.addRequired('basePath', @(s)ischar(s)||isstring(s));
inputParserObject.addRequired('eightBad', @(x)islogical(x)||ismember(x,[0,1]));
inputParserObject.addParameter('nTotalCh', 64, @(x)isnumeric(x)&&isscalar(x)&&x>=1);
inputParserObject.addParameter('evenOnly', true, @(x)islogical(x)||ismember(x,[0,1]));
inputParserObject.addParameter('keep', [], @(v)isnumeric(v)&&isvector(v)&&all(v>=1));
inputParserObject.addParameter('storeClass', 'single', @(s)ischar(s)||isstring(s)); % Ignored, but kept for compatibility
inputParserObject.addParameter('outName', '', @(s)ischar(s)||isstring(s)); % Ignored
inputParserObject.addParameter('fallbackADBV', 0.00000006103515625, @(x)isfinite(x)&&x>0);
inputParserObject.addParameter('reqsPath', fullfile(fileparts(mfilename('fullpath')), 'reqsPath'), @(s)ischar(s)||isstring(s));
inputParserObject.addParameter('invertPolarity', true, @(x)islogical(x)||ismember(x,[0,1])); % Ignored
inputParserObject.addParameter('reverseTime', false, @(x)islogical(x)||ismember(x,[0,1])); % Ignored
inputParserObject.parse(basePath, eightBad, varargin{:});

basePath            = char(inputParserObject.Results.basePath);
eightBad            = logical(inputParserObject.Results.eightBad);
nTotalCh            = inputParserObject.Results.nTotalCh;
evenOnly            = logical(inputParserObject.Results.evenOnly);
keep                = inputParserObject.Results.keep;
fallbackADBV        = inputParserObject.Results.fallbackADBV;
reqsPath            = char(inputParserObject.Results.reqsPath);
% storeClass, outName, invertPolarity, reverseTime are not needed for this diagnostic

fprintf('[INFO] Base path: %s\n', basePath);
fprintf('[INFO] eightBad flag: %d (1 means replace channel 8 with channel 9)\n', eightBad);
if ~isfolder(basePath)
    error('[ERROR] Base folder not found: %s', basePath);
end

%% ---------- PATH & MEX checks (Identical to original) ----------
if isfolder(reqsPath), addpath(reqsPath); end
rehash toolboxcache; clear mex;
nlxPaths = which('-all','Nlx2MatCSC');
if isempty(nlxPaths)
    error(['[ERROR] Nlx2MatCSC not found. Put Nlx2MatCSC.%s in reqsPath ' ...
           'or add its folder to path.'], mexext);
end
if ~any(endsWith(string(nlxPaths), ['.',mexext], 'IgnoreCase',true))
    error('[ERROR] Only Nlx2MatCSC.m is visible. Ensure Nlx2MatCSC.%s (MEX) is earlier on the path.', mexext);
end
fprintf('[INFO] Using Nlx2MatCSC found at:\n'); disp(nlxPaths(:));

%% ---------- Channel selection (Identical to original) ----------
allChannels = 1:nTotalCh;
if ~isempty(keep)
    kept_channels = intersect(allChannels, unique(keep(:)'));
elseif evenOnly
    kept_channels = allChannels(mod(allChannels,2)==0); % 2,4,6,...
else
    kept_channels = allChannels;                         % 1..nTotalCh
end
numberOfKeptChannels = numel(kept_channels);
if numberOfKeptChannels==0, error('[ERROR] No channels selected to keep.'); end

fprintf('[INFO] Channels to include: %d of %d\n', numberOfKeptChannels, nTotalCh);
fprintf('[INFO] First few kept channels: %s\n', mat2str(kept_channels(1:min(10,numberOfKeptChannels))));

% Helpful booleans for replacement logic
isChannel8Kept = ismember(8, kept_channels);
sourceChannelFor8 = 9; % fixed by requirement
fprintf('[INFO] isChannel8Kept: %d | sourceChannelFor8: %d\n', isChannel8Kept, sourceChannelFor8);

%% ---------- Diagnostic Pass: Collect Timestamps and NValid ----------
fieldSelectionAll  = [1 1 1 1 1];
extractHeader      = 1;
extractModeAll     = 1;

fileListKept        = strings(1, numberOfKeptChannels);
headersCell         = cell(1, numberOfKeptChannels);
samplingRateArray   = nan(1, numberOfKeptChannels);
effectiveLengthArr  = nan(1, numberOfKeptChannels);
badChannelMaskFull  = false(1, nTotalCh);
ADBitVoltsPerKeep   = nan(1, numberOfKeptChannels);
sourceChannelList   = nan(1, numberOfKeptChannels);

% *** DIAGNOSTIC DATA TO COLLECT ***
timestampsCell    = cell(1, numberOfKeptChannels);
nValidSamplesCell = cell(1, numberOfKeptChannels);
timingAnalysisCell = cell(1, numberOfKeptChannels); % NEW

% Track replacement provenance
replacementInfo.usedReplacementFor8 = false;
replacementInfo.sourceChannel       = NaN;
replacementInfo.sourceFile          = "";
replacementInfo.note                = "";

fprintf('\n[INFO] Diagnostic pass: scanning files for timing...\n');
for keptIndex = 1:numberOfKeptChannels
    channelNumber = kept_channels(keptIndex);

    % Decide which physical file to read
    sourceChannelThisRow = channelNumber;
    if eightBad && (channelNumber == 8)
        sourceChannelThisRow = sourceChannelFor8;  % 9
        fprintf('[INFO] Replacement engaged for channel 8: reading CSC%d.ncs instead of CSC8.ncs\n', sourceChannelThisRow);
        replacementInfo.usedReplacementFor8 = true;
        replacementInfo.sourceChannel       = sourceChannelThisRow;
    end
    sourceChannelList(keptIndex) = sourceChannelThisRow;

    cscFilePathToRead = fullfile(basePath, sprintf('CSC%d.ncs', sourceChannelThisRow));
    fileListKept(keptIndex) = string(fullfile(basePath, sprintf('CSC%d.ncs', channelNumber)));

    if ~isfile(cscFilePathToRead)
        warning('[WARN] Missing file: %s (row channel %d; source channel %d). Marking bad.', ...
            cscFilePathToRead, channelNumber, sourceChannelThisRow);
        badChannelMaskFull(channelNumber) = true;
        headersCell{keptIndex} = {};
        timestampsCell{keptIndex} = [];
        nValidSamplesCell{keptIndex} = [];
        timingAnalysisCell{keptIndex} = struct('error', 'File not found');
        continue;
    end

    % Define a default/empty analysis struct
    analysis = struct(...
        'summary', 'Analysis not run', ...
        'nRecords', 0, ...
        'recordBlockSize', 512, ...
        'nPartialRecords', 0, ...
        'partialRecords_not_last_idx', [], ...
        'expectedStep_us', NaN, ...
        'delta_T_us', [], ...
        'minDelta_us', NaN, ...
        'maxDelta_us', NaN, ...
        'gapIndices', [], ...
        'nGaps', 0, ...
        'overlapIndices', [], ...
        'nOverlaps', 0 ...
        );

    try
        [timestamps_us, ~, sampleFrequencies, numberValidSamples, samplesAD, headerLines] = ...
            Nlx2MatCSC(cscFilePathToRead, fieldSelectionAll, extractHeader, extractModeAll, []);

        % Store raw data for output struct
        timestampsCell{keptIndex} = timestamps_us;
        nValidSamplesCell{keptIndex} = numberValidSamples;
        headersCell{keptIndex} = headerLines;

        % --- Start Main Analysis Logic ---
        analysis.nRecords = numel(timestamps_us);
        analysis.recordBlockSize = size(samplesAD,1); % Should be 512
        
        % 1. Analyze NValidSamples
        % The original script's flattening logic fails if any record *except
        % the very last one* is not full.
        partial_idx = find(numberValidSamples(:)' < analysis.recordBlockSize);
        analysis.nPartialRecords = numel(partial_idx);
        
        if analysis.nRecords > 0
            % Find partial records that are NOT the last record
            not_last_mask = (1:analysis.nRecords) < analysis.nRecords;
            analysis.partialRecords_not_last_idx = find(...
                numberValidSamples(:)' < analysis.recordBlockSize & not_last_mask ...
            );
        end

        % Compute effective flattened length
        validPerRecord = min(analysis.recordBlockSize, max(0, numberValidSamples(:)'));
        effectiveLengthArr(keptIndex) = sum(validPerRecord);

        % Get Sampling frequency
        samplingRateThis = mode(double(sampleFrequencies(sampleFrequencies>0)));
        if ~(isfinite(samplingRateThis) && samplingRateThis>0)
            samplingFrequencyLine = headerLines(contains(headerLines,'SamplingFrequency','IgnoreCase',true));
            if ~isempty(samplingFrequencyLine)
                token = regexp(samplingFrequencyLine{1}, 'SamplingFrequency[^0-9eE.\-]*([\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?)', 'tokens', 'once');
                if ~isempty(token), samplingRateThis = str2double(token{1}); end
            end
        end
        samplingRateArray(keptIndex) = samplingRateThis;

        % Get ADBitVolts
        adbv = NaN;
        idx = find(contains(headerLines,'ADBitVolts','IgnoreCase',true),1,'first');
        if ~isempty(idx)
            token = regexp(headerLines{idx}, 'ADBitVolts[^0-9eE.\-]*([\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?)', 'tokens', 'once');
            if ~isempty(token), adbv = str2double(token{1}); end
        end
        if ~(isfinite(adbv) && adbv>0)
            adbv = fallbackADBV;
        end
        ADBitVoltsPerKeep(keptIndex) = adbv;

        % Print the standard row info
        fprintf('  Row CSC%-2d (from CSC%-2d): %10d samples eff @ %g Hz | %d records | ADBitVolts=%.12g V/AD\n', ...
            channelNumber, sourceChannelThisRow, effectiveLengthArr(keptIndex), samplingRateArray(keptIndex), analysis.nRecords, adbv);
        
        % 2. Analyze Timestamps
        summaryStrings = {};
        if ~isempty(timestamps_us) && isfinite(samplingRateThis) && samplingRateThis>0
            
            analysis.expectedStep_us = analysis.recordBlockSize * (1e6 / samplingRateThis);
            analysis.delta_T_us = diff(double(timestamps_us));
            
            % Define tolerance (50% of expected step, as in original)
            tolerance_us = 0.5 * analysis.expectedStep_us;
            
            % Find GAPS (deltas that are too large)
            analysis.gapIndices = find(analysis.delta_T_us > (analysis.expectedStep_us + tolerance_us));
            analysis.nGaps = numel(analysis.gapIndices);
            
            % Find OVERLAPS (deltas that are too small or negative)
            analysis.overlapIndices = find(analysis.delta_T_us < (analysis.expectedStep_us - tolerance_us));
            analysis.nOverlaps = numel(analysis.overlapIndices);

            analysis.minDelta_us = min(analysis.delta_T_us);
            analysis.maxDelta_us = max(analysis.delta_T_us);
            
            % --- Build Diagnostic Report ---
            s1 = sprintf('    [DIAG] NValid: Found %d partial records (NValid < %d).', ...
                analysis.nPartialRecords, analysis.recordBlockSize);
            if ~isempty(analysis.partialRecords_not_last_idx)
                s1 = [s1, sprintf(' *** PROBLEM: %d non-last partial records! ***', numel(analysis.partialRecords_not_last_idx))];
            end
            summaryStrings{end+1} = s1;

            s2 = sprintf('    [DIAG] Timestamps: Expected step: %.2f us. Found min=%.2f, max=%.2f.', ...
                analysis.expectedStep_us, analysis.minDelta_us, analysis.maxDelta_us);
            summaryStrings{end+1} = s2;
            
            s3 = sprintf('    [DIAG] -> Found %d GAPS (delta > %.2f us) and %d OVERLAPS (delta < %.2f us).', ...
                analysis.nGaps, analysis.expectedStep_us + tolerance_us, ...
                analysis.nOverlaps, analysis.expectedStep_us - tolerance_us);
            summaryStrings{end+1} = s3;
            
            if analysis.nGaps > 0
                % Report the single largest gap
                largestGap_us = max(analysis.delta_T_us(analysis.gapIndices));
                s4 = sprintf('    [DIAG] -> Largest gap: %.2f us (%.1f x expected).', ...
                    largestGap_us, largestGap_us / analysis.expectedStep_us);
                summaryStrings{end+1} = s4;
            end
            
            analysis.summary = strjoin(summaryStrings, '\n');

        else
            % Failed to get timing info
            s1 = '    [DIAG] Could not perform timing analysis (missing timestamps or Sfx).';
            summaryStrings{end+1} = s1;
            analysis.summary = s1;
        end
        
        % Print the multi-line diagnostic report
        fprintf('%s\n', strjoin(summaryStrings, '\n'));
        
        % --- End Main Analysis Logic ---
        
        if eightBad && (channelNumber == 8)
            replacementInfo.sourceFile = string(cscFilePathToRead);
            replacementInfo.note = "Row 8 populated from channel 9 for diagnostic pass.";
        end

    catch ME
        analysis.summary = sprintf('    [DIAG] Error during analysis: %s', ME.message);
        analysis.error = ME;
        fprintf('%s\n', analysis.summary);
        
        warning('[WARN] Read failure %s (row ch %d; source ch %d): %s. Marking bad.', ...
            cscFilePathToRead, channelNumber, sourceChannelThisRow, ME.message);
        
        badChannelMaskFull(channelNumber) = true;
        effectiveLengthArr(keptIndex)     = 0;
        headersCell{keptIndex}            = {};
        timestampsCell{keptIndex} = [];
        nValidSamplesCell{keptIndex} = [];
        samplingRateArray(keptIndex)      = NaN;
        ADBitVoltsPerKeep(keptIndex)      = NaN;
    end
    
    % Store the analysis struct for this channel
    timingAnalysisCell{keptIndex} = analysis;
end

%% ---------- Package Diagnostic Data ----------
fprintf('\n[INFO] Diagnostic pass complete. Returning collected data.\n');

diagData.notes = { ...
    'This struct contains data from the *first pass* of VACC_CSC2MAT_uV_disk.', ...
    'Inspect `diagData.timingAnalysis` for detailed reports on each channel.', ...
    'Check for timestamp gaps (nGaps > 0) and non-last partial records.', ...
    'See the example header in this function for how to use this struct.' ...
    };
diagData.basePath = basePath;
diagData.options = inputParserObject.Results;
diagData.kept_channels = kept_channels;
diagData.sourceChannelsUsed = sourceChannelList;
diagData.fileListKept_nominal = fileListKept;
diagData.timestamps_us_per_record = timestampsCell;
diagData.nValidSamples_per_record = nValidSamplesCell;
diagData.headers = headersCell;
diagData.samplingRates_Hz = samplingRateArray;
diagData.effectiveLengths = effectiveLengthArr;
diagData.ADBitVolts = ADBitVoltsPerKeep;
diagData.badChannelMask_original = badChannelMaskFull;
diagData.replacementInfo = replacementInfo;
diagData.timingAnalysis = timingAnalysisCell; % NEW

fprintf('[INFO] To start debugging, see the example in the header of this function.\img.\n');
fprintf('  e.g., `analysis = diagData.timingAnalysis{1}; disp(analysis.summary);`\n');

end