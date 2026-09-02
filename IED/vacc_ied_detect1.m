function vacc_ied_detect1(basePath, eightBad, varargin)
% vacc_ied_detect(basePath, eightBad, Name,Value,...)
% Modeled after VACC_CSC2MAT_uV_disk, this function loads Neuralynx CSC
% data, converts it to microvolts in memory, runs LLSpikedetector,
% and saves the detection results (ets, ech) to a .mat file.
%
% This function calls LLspikedetector.m, which must be on the MATLAB path
% or in the same directory.
%
% REQUIRED:
%   basePath   : folder containing CSC#.ncs files (e.g., CSC1.ncs..CSC64.ncs)
%   eightBad   : logical true/false; if true -> replace channel 8 with channel 9
%
% OPTIONS (Name,Value):
%   'nTotalCh'       (default 64)       : total channels expected (1..nTotalCh)
%   'evenOnly'       (default true)     : keep only even channels (2,4,6,...) if true
%   'keep'           (default [])       : explicit list of channels to keep (overrides evenOnly)
%   'outName'        (default auto)     : output MAT filename for results (placed in basePath)
%   'fallbackADBV'   (default 0.00000006103515625) : V/AD used if header lacks ADBitVolts
%   'reqsPath'       (default ./reqsPath): folder containing Nlx2MatCSC MEX if not on path
%   'invertPolarity' (default true)     : multiply by -1 after scaling to µV (before detection)
%   'llw'            (default 0.04)     : line-length window (sec) for detector
%   'prc'            (default 99.9)     : percentile threshold for detector
%
% OUTPUT .mat (saved in basePath):
%   ets            : [nEvents x 2] matrix of event [on, off] times in samples
%   ech            : [nEvents x nKeptChannels] logical matrix of channel participation
%   meta           : Struct with provenance (sfx, llw, prc, kept_channels,
%                    badch_full, badch_kept_indexed, replacementInfo, etc.)
%
% Example:
%   vacc_ied_detect('/gpfs2/scratch/sakhava1/Rec', true, ...
%       'nTotalCh',64, 'evenOnly',true, 'llw',0.04, 'prc',99.9);

%% ---------- Parse inputs ----------
fprintf('\n[INFO] Starting vacc_ied_detect\n');

inputParserObject = inputParser;
inputParserObject.addRequired('basePath', @(s)ischar(s)||isstring(s));
inputParserObject.addRequired('eightBad', @(x)islogical(x)||ismember(x,[0,1]));
inputParserObject.addParameter('nTotalCh', 64, @(x)isnumeric(x)&&isscalar(x)&&x>=1);
inputParserObject.addParameter('evenOnly', true, @(x)islogical(x)||ismember(x,[0,1]));
inputParserObject.addParameter('keep', [], @(v)isnumeric(v)&&isvector(v)&&all(v>=1));
inputParserObject.addParameter('outName', '', @(s)ischar(s)||isstring(s));
inputParserObject.addParameter('fallbackADBV', 0.00000006103515625, @(x)isfinite(x)&&x>0); % V/AD
inputParserObject.addParameter('reqsPath', fullfile(fileparts(mfilename('fullpath')), 'reqsPath'), @(s)ischar(s)||isstring(s));
inputParserObject.addParameter('invertPolarity', true, @(x)islogical(x)||ismember(x,[0,1]));
inputParserObject.addParameter('llw', 0.04, @(x)isnumeric(x)&&isscalar(x)&&x>0);
inputParserObject.addParameter('prc', 99.9, @(x)isnumeric(x)&&isscalar(x)&&x>0&&x<=100);
inputParserObject.parse(basePath, eightBad, varargin{:});

basePath            = char(inputParserObject.Results.basePath);
eightBad            = logical(inputParserObject.Results.eightBad);
nTotalCh            = inputParserObject.Results.nTotalCh;
evenOnly            = logical(inputParserObject.Results.evenOnly);
keep                = inputParserObject.Results.keep;
outName             = char(inputParserObject.Results.outName);
fallbackADBV        = inputParserObject.Results.fallbackADBV;
reqsPath            = char(inputParserObject.Results.reqsPath);
invertPolarity      = logical(inputParserObject.Results.invertPolarity);
llw                 = inputParserObject.Results.llw;
prc                 = inputParserObject.Results.prc;

fprintf('[INFO] Base path: %s\n', basePath);
fprintf('[INFO] eightBad flag: %d (1 means replace channel 8 with channel 9)\n', eightBad);
fprintf('[INFO] Detection params: llw=%.3f sec, prc=%.3f\n', llw, prc);
if ~isfolder(basePath)
    error('[ERROR] Base folder not found: %s', basePath);
end

%% ---------- PATH & MEX checks ----------
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

% Check for LLspikedetector
if isempty(which('LLspikedetector'))
    warning('[WARN] LLspikedetector.m not found on path. Ensure it is in the same directory or on the MATLAB path.');
end

%% ---------- Channel selection ----------
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

%% ---------- Auto output name if empty ----------
if isempty(strtrim(outName))
    [~, tailFolderName] = fileparts(basePath);
    outName = sprintf('LL_detections_%s_prc%.1f.mat', tailFolderName, prc);
    outName = strrep(outName, '.', 'p'); % Replace decimal in prc
end
outputFullPath = fullfile(basePath, outName);
fprintf('[INFO] Output results MAT will be: %s\n', outputFullPath);

%% ---------- First pass: sizes, sampling rates, ADBitVolts ----------
% Neuralynx flags:
%   FieldSelection = [Timestamps, ChannelNumbers, SampleFrequencies, NumberValidSamples, Samples] -> [1 1 1 1 1]
%   ExtractHeader = 1 to get header, ExtractMode = 1 (extract all)
fieldSelectionAll  = [1 1 1 1 1];
extractHeader      = 1;
extractModeAll     = 1;

fileListKept       = strings(1, numberOfKeptChannels);  % nominal filenames for rows
headersCell        = cell(1, numberOfKeptChannels);     % header per kept index (for ch8, we may store ch9 header)
samplingRateArray  = nan(1, numberOfKeptChannels);
effectiveLengthArr = nan(1, numberOfKeptChannels);
badChannelMaskFull = false(1, nTotalCh);
ADBitVoltsPerKeep  = nan(1, numberOfKeptChannels);

% Track replacement provenance
replacementInfo.usedReplacementFor8 = false;
replacementInfo.sourceChannel       = NaN;
replacementInfo.sourceFile          = "";
replacementInfo.note                = "";

fprintf('\n[INFO] First pass: scan files, sizes, sampling rates, ADBitVolts\n');
for keptIndex = 1:numberOfKeptChannels
    channelNumber = kept_channels(keptIndex);

    % Decide which physical file to read:
    sourceChannelThisRow = channelNumber;
    if eightBad && (channelNumber == 8)
        sourceChannelThisRow = sourceChannelFor8;  % 9
        fprintf('[INFO] Replacement engaged for channel 8 in FIRST PASS: reading CSC%d.ncs instead of CSC8.ncs\n', sourceChannelThisRow);
        replacementInfo.usedReplacementFor8 = true;
        replacementInfo.sourceChannel       = sourceChannelThisRow;
    end

    cscFilePathToRead = fullfile(basePath, sprintf('CSC%d.ncs', sourceChannelThisRow));
    fileListKept(keptIndex) = string(fullfile(basePath, sprintf('CSC%d.ncs', channelNumber))); % nominal/row label

    if ~isfile(cscFilePathToRead)
        warning('[WARN] Missing file: %s (row channel %d; source channel %d). Marking bad.', ...
            cscFilePathToRead, channelNumber, sourceChannelThisRow);
        badChannelMaskFull(channelNumber) = true;
        effectiveLengthArr(keptIndex) = 0;
        headersCell{keptIndex} = {};
        continue;
    end

    try
        [timestamps_us, ~, sampleFrequencies, numberValidSamples, samplesAD, headerLines] = ...
            Nlx2MatCSC(cscFilePathToRead, fieldSelectionAll, extractHeader, extractModeAll, []);

        recordBlockLength = size(samplesAD,1);
        validPerRecord    = min(recordBlockLength, max(0, numberValidSamples(:)'));
        effectiveLengthArr(keptIndex) = sum(validPerRecord);

        samplingRateThis = mode(double(sampleFrequencies(sampleFrequencies>0)));
        if ~(isfinite(samplingRateThis) && samplingRateThis>0)
            samplingFrequencyLine = headerLines(contains(headerLines,'SamplingFrequency','IgnoreCase',true));
            if ~isempty(samplingFrequencyLine)
                token = regexp(samplingFrequencyLine{1}, 'SamplingFrequency[^0-9eE.\\-]*([\\-+]?\\d+(\\.\\d+)?([eE][\\-+]?\\d+)?)', 'tokens', 'once');
                if ~isempty(token), samplingRateThis = str2double(token{1}); end
            end
        end
        samplingRateArray(keptIndex) = samplingRateThis;

        adbv = NaN;
        idx = find(contains(headerLines,'ADBitVolts','IgnoreCase',true),1,'first');
        if ~isempty(idx)
            token = regexp(headerLines{idx}, 'ADBitVolts[^0-9eE.\\-]*([\\-+]?\\d+(\\.\\d+)?([eE][\\-+]?\\d+)?)', 'tokens', 'once');
            if ~isempty(token), adbv = str2double(token{1}); end
        end
        if ~(isfinite(adbv) && adbv>0)
            adbv = fallbackADBV;
            warning('[WARN] ADBitVolts missing for CSC%d; using fallback %.12g V/AD', sourceChannelThisRow, adbv);
        end
        ADBitVoltsPerKeep(keptIndex) = adbv;
        headersCell{keptIndex} = headerLines;

        fprintf('  Row CSC%-2d (from CSC%-2d): %10d samples eff @ %g Hz | ADBitVolts=%.12g V/AD\n', ...
            channelNumber, sourceChannelThisRow, effectiveLengthArr(keptIndex), samplingRateArray(keptIndex), adbv);

        if ~isempty(timestamps_us) && isfinite(samplingRateThis) && samplingRateThis>0
            expectedStep_us = 512 * (1e6 / samplingRateThis);
            deltaT = diff(double(timestamps_us));
            if any(abs(deltaT - expectedStep_us) > 0.5 * expectedStep_us)
                warning('[WARN] Timing irregularity in %s (source ch %d). Gaps not interpolated.', cscFilePathToRead, sourceChannelThisRow);
            end
        end

        if eightBad && (channelNumber == 8)
            replacementInfo.sourceFile = string(cscFilePathToRead);
            replacementInfo.note = "Row 8 populated from channel 9 for both passes.";
        end

    catch ME
        warning('[WARN] Read failure %s (row ch %d; source ch %d): %s. Marking bad.', ...
            cscFilePathToRead, channelNumber, sourceChannelThisRow, ME.message);
        badChannelMaskFull(channelNumber) = true;
        effectiveLengthArr(keptIndex)     = 0; 
        headersCell{keptIndex}            = {}; 
        samplingRateArray(keptIndex)      = NaN; 
        ADBitVoltsPerKeep(keptIndex)      = NaN;
    end
end

%% ---------- Unified sampling rate ----------
goodMask = (effectiveLengthArr>0) & isfinite(samplingRateArray) & samplingRateArray>0;
if ~any(goodMask)
    error('[ERROR] No valid channels found / no sampling frequency could be determined.');
end
unifiedSamplingRate_Hz = mode(round(samplingRateArray(goodMask)));
fprintf('\n[INFO] Unified sampling rate (mode across good channels): %g Hz\n', unifiedSamplingRate_Hz);

%% ---------- Prepare IN-MEMORY target ----------
maxSamplesAcrossKept = max(effectiveLengthArr(goodMask));
% Use 'single' for memory efficiency, was default storeClass in model script
storeClass = 'single'; 
bytesPerElement = 4;
approximateGigabytesInMemory = (numberOfKeptChannels*maxSamplesAcrossKept*bytesPerElement)/1e9;

fprintf('[INFO] Allocating in-memory array: %d x %d (%s) ~ %.2f GB\n', ...
    numberOfKeptChannels, maxSamplesAcrossKept, storeClass, approximateGigabytesInMemory);

d = nan(numberOfKeptChannels, maxSamplesAcrossKept, storeClass);


%% ---------- Second pass: read → flatten (NValid) → scale to µV → invert → write to RAM ----------
fprintf('\n[INFO] Second pass: loading MICROVOLT data into memory (progress below)\n');
ticOverall = tic;

for keptIndex = 1:numberOfKeptChannels
    channelNumber = kept_channels(keptIndex);

    if badChannelMaskFull(channelNumber) || effectiveLengthArr(keptIndex)==0
        fprintf('  Row CSC%-2d: skipped (bad/missing)\n', channelNumber);
        continue;
    end

    sourceChannelThisRow = channelNumber;
    if eightBad && (channelNumber == 8)
        sourceChannelThisRow = sourceChannelFor8;  % 9
        fprintf('[INFO] Replacement engaged for channel 8 in SECOND PASS: reading CSC%d.ncs instead of CSC8.ncs\n', sourceChannelThisRow);
    end

    cscFilePathToRead = fullfile(basePath, sprintf('CSC%d.ncs', sourceChannelThisRow));
    if ~isfile(cscFilePathToRead)
        warning('[WARN] Source file missing for row CSC%d (wanted CSC%d): %s. Skipping row.', ...
            channelNumber, sourceChannelThisRow, cscFilePathToRead);
        continue;
    end

    % Read without header (faster): FieldSelection=[1 1 1 1 1]; ExtractHeader=0; ExtractMode=1
    [~, ~, ~, numberValidSamples, samplesAD] = Nlx2MatCSC(cscFilePathToRead, [1 1 1 1 1], 0, 1, []); %#ok<ASGLU>

    recordBlockLength = size(samplesAD,1);
    numberOfRecords   = size(samplesAD,2);
    thisEffectiveLength = effectiveLengthArr(keptIndex);

    % Preallocate flat vector in AD units then fill honoring NValid per record
    flatSignalAD = nan(1, thisEffectiveLength); % AD units
    writePosition = 1;

    for recordIndex = 1:numberOfRecords
        validCount = min(recordBlockLength, max(0, numberValidSamples(recordIndex)));
        if validCount > 0
            endPos = writePosition+validCount-1;
            if endPos > thisEffectiveLength
                warning('[WARN] Overrun detected on row CSC%d. Truncating.', channelNumber);
                validCount = thisEffectiveLength - writePosition + 1;
                endPos = thisEffectiveLength;
            end
            if validCount <= 0; break; end
            
            flatSignalAD(writePosition:endPos) = double(samplesAD(1:validCount, recordIndex));
            writePosition = writePosition + validCount;
        end
    end

    % Convert to MICROVOLTS for this row
    scaleFactor_uV_per_AD = ADBitVoltsPerKeep(keptIndex) * 1e6; % µV/AD
    if ~(isfinite(scaleFactor_uV_per_AD) && scaleFactor_uV_per_AD>0)
        scaleFactor_uV_per_AD = fallbackADBV * 1e6;
        warning('[WARN] Using fallback scale for row CSC%d: %.12g µV/AD', channelNumber, scaleFactor_uV_per_AD);
    end
    flatSignal_uV = flatSignalAD * scaleFactor_uV_per_AD;

    % Polarity invert (vertical flip) if requested
    if invertPolarity
        flatSignal_uV = -flatSignal_uV;
    end

    % Write into the in-memory matrix
    d(keptIndex, 1:numel(flatSignal_uV)) = single(flatSignal_uV);
    
    % Clear large vars
    clear flatSignalAD flatSignal_uV samplesAD numberValidSamples;

    % Progress prints
    if mod(keptIndex,2)==0 || keptIndex==numberOfKeptChannels
        elapsedSeconds = toc(ticOverall);
        fprintf('  [%3d/%3d] Row CSC%-2d (from CSC%-2d) loaded | %.1f%% | elapsed %s | invert=%d\n', ...
            keptIndex, numberOfKeptChannels, channelNumber, sourceChannelThisRow, ...
            100*keptIndex/numberOfKeptChannels, duration(0,0,elapsedSeconds,"Format","mm:ss"), ...
            invertPolarity);
    end
end
fprintf('[INFO] Data loading complete. Total time: %s\n', duration(0,0,toc(ticOverall),"Format","mm:ss"));

%% ---------- Run Spike Detector ----------

% Create the badch mask for LLspikedetector (relative to kept channels)
% badChannelMaskFull is [1 x nTotalCh]
% kept_channels is [1 x nKept]
% We need badch_kept_indexed [1 x nKept]
badch_kept_indexed = badChannelMaskFull(kept_channels);
fprintf('\n[INFO] Bad channels (full mask): %s\n', mat2str(find(badChannelMaskFull)));
fprintf('[INFO] Bad channels (relative to kept): %s (indices) / %s (original CSC numbers)\n', ...
    mat2str(find(badch_kept_indexed)), mat2str(kept_channels(badch_kept_indexed)));

fprintf('[INFO] Running LLSpikedetector (llw=%.3f, prc=%.3f)...\n', llw, prc);
ticDetect = tic;

% Call LLspikedetector as an external function
[ets, ech] = LLspikedetector(d, unifiedSamplingRate_Hz, llw, prc, badch_kept_indexed);

fprintf('[INFO] Detection complete. Found %d events in %.1f sec.\n', size(ets,1), toc(ticDetect));

% Clear the large data matrix 'd' from memory
clear d;

%% ---------- Save Results ----------
fprintf('[INFO] Saving detection results to: %s\n', outputFullPath);

meta.basePath           = basePath;
meta.createdOn          = datestr(now);
meta.nTotalCh           = nTotalCh;
meta.nKept              = numberOfKeptChannels;
meta.reader             = ['Nlx2MatCSC (', mexext, ')'];
meta.detector           = 'LLspikedetector';
meta.detectionParams.llw = llw;
meta.detectionParams.prc = prc;
meta.note               = 'Detection run on in-memory microvolt data.';
meta.fileListKept       = fileListKept;
meta.ADBitVolts         = ADBitVoltsPerKeep;
meta.scaleFactor_uV     = ADBitVoltsPerKeep * 1e6;
meta.invertPolarity     = invertPolarity;
meta.eightBad           = eightBad;
meta.replacementInfo    = replacementInfo;
meta.sfx                = unifiedSamplingRate_Hz;
meta.kept_channels      = kept_channels;
meta.headersCell        = headersCell;
meta.badch_full         = badChannelMaskFull;     % [1 x nTotalCh] logical
meta.badch_kept_indexed = badch_kept_indexed; % [1 x nKept] logical

try
    save(outputFullPath, 'ets', 'ech', 'meta', '-v7.3');
catch ME_save
    warning('[WARN] Failed to save with -v7.3 (file may be >2GB). Retrying without -v7.3... Error: %s', ME_save.message);
    try
        save(outputFullPath, 'ets', 'ech', 'meta');
    catch ME_save2
        error('[ERROR] Failed to save results file: %s', ME_save2.message);
    end
end

fprintf('\n[INFO] Done.\n[INFO] Saved detection file:\n  %s\n', outputFullPath);

end