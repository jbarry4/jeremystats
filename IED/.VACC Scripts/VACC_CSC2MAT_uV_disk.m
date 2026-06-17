function VACC_CSC2MAT_uV_disk(basePath, eightBad, varargin)
% VACC_CSC2MAT_uV_disk(basePath, eightBad, Name,Value,...)
% Convert a folder of Neuralynx CSC#.ncs -> disk-backed .mat in MICROVOLTS.
%
% --- VERSION 3: FUZZY FILE MATCHING ---
% - Supports 'CSC1_Clean.ncs' or 'CSC1.ncs' automatically.
% - Handles time gaps (NaN padding).
%
% REQUIRED:
%   basePath    : folder containing CSC files
%   eightBad    : logical; if true -> replace channel 8 with channel 9
%
% OPTIONS (Name,Value):
%   'nTotalCh'       (default 64)
%   'evenOnly'       (default true)
%   'keep'           (default [])
%   'storeClass'     (default 'single')
%   'outName'        (default auto)
%   'fallbackADBV'   (default 6e-8)
%   'reqsPath'       (default ./reqsPath)
%   'invertPolarity' (default true)
%   'reverseTime'    (default false)

%% ---------- Parse inputs ----------
fprintf('\n[INFO] Starting VACC_CSC2MAT_uV_disk (v3 Fuzzy-Match)\n');

inputParserObject = inputParser;
inputParserObject.addRequired('basePath', @(s)ischar(s)||isstring(s));
inputParserObject.addRequired('eightBad', @(x)islogical(x)||ismember(x,[0,1]));
inputParserObject.addParameter('nTotalCh', 64, @(x)isnumeric(x)&&isscalar(x)&&x>=1);
inputParserObject.addParameter('evenOnly', true, @(x)islogical(x)||ismember(x,[0,1]));
inputParserObject.addParameter('keep', [], @(v)isnumeric(v)&&isvector(v)&&all(v>=1));
inputParserObject.addParameter('storeClass', 'single', @(s)ischar(s)||isstring(s));
inputParserObject.addParameter('outName', '', @(s)ischar(s)||isstring(s));
inputParserObject.addParameter('fallbackADBV', 0.00000006103515625, @(x)isfinite(x)&&x>0); 
inputParserObject.addParameter('reqsPath', fullfile(fileparts(mfilename('fullpath')), 'reqsPath'), @(s)ischar(s)||isstring(s));
inputParserObject.addParameter('invertPolarity', true, @(x)islogical(x)||ismember(x,[0,1]));
inputParserObject.addParameter('reverseTime', false, @(x)islogical(x)||ismember(x,[0,1]));
inputParserObject.parse(basePath, eightBad, varargin{:});

basePath            = char(inputParserObject.Results.basePath);
eightBad            = logical(inputParserObject.Results.eightBad);
nTotalCh            = inputParserObject.Results.nTotalCh;
evenOnly            = logical(inputParserObject.Results.evenOnly);
keep                = inputParserObject.Results.keep;
storeClass          = char(inputParserObject.Results.storeClass);
outName             = char(inputParserObject.Results.outName);
fallbackADBV        = inputParserObject.Results.fallbackADBV;
reqsPath            = char(inputParserObject.Results.reqsPath);
invertPolarity      = logical(inputParserObject.Results.invertPolarity);
reverseTime         = logical(inputParserObject.Results.reverseTime);

fprintf('[INFO] Base path: %s\n', basePath);
if ~isfolder(basePath)
    error('[ERROR] Base folder not found: %s', basePath);
end

%% ---------- PATH & MEX checks ----------
if isfolder(reqsPath), addpath(reqsPath); end
rehash toolboxcache; clear mex;
nlxPaths = which('-all','Nlx2MatCSC');
if isempty(nlxPaths)
    error(['[ERROR] Nlx2MatCSC not found. Put Nlx2MatCSC.%s in reqsPath.'], mexext);
end

%% ---------- Channel selection ----------
allChannels = 1:nTotalCh;
if ~isempty(keep)
    kept_channels = intersect(allChannels, unique(keep(:)'));
elseif evenOnly
    kept_channels = allChannels(mod(allChannels,2)==0); 
else
    kept_channels = allChannels;
end
numberOfKeptChannels = numel(kept_channels);
if numberOfKeptChannels==0, error('[ERROR] No channels selected to keep.'); end

fprintf('[INFO] Channels to include: %d of %d\n', numberOfKeptChannels, nTotalCh);
fprintf('[INFO] First few kept channels: %s\n', mat2str(kept_channels(1:min(10,numberOfKeptChannels))));

% Helper to get files in directory once
dirStruct = dir(fullfile(basePath, '*.ncs'));
allNcsNames = {dirStruct.name};

% --- Helper Function for Fuzzy Matching ---
    function fPath = findCscFile(chNum)
        % Matches: CSC<num>.ncs OR CSC<num>_*.ncs (e.g. _Clean)
        % Pattern regex: ^CSC0*<num>(\D.*)?\.ncs$
        % This ensures CSC1 does not match CSC10.
        pat = ['^CSC0*', num2str(chNum), '(\D.*)?\.ncs$'];
        matchIdx = ~cellfun(@isempty, regexpi(allNcsNames, pat));
        
        matches = allNcsNames(matchIdx);
        if isempty(matches)
            fPath = '';
        else
            % If multiple, prefer exact match CSC#.ncs, otherwise take first
            exactName = sprintf('CSC%d.ncs', chNum);
            exactIdx = strcmpi(matches, exactName);
            if any(exactIdx)
                fPath = fullfile(basePath, matches{find(exactIdx,1)});
            else
                fPath = fullfile(basePath, matches{1});
            end
        end
    end

%% ---------- Auto output name ----------
if isempty(strtrim(outName))
    [~, tailFolderName] = fileparts(basePath);
    outName = sprintf('LL_input_%s_mex_disk_uV.mat', tailFolderName);
end
outputFullPath = fullfile(basePath, outName);
fprintf('[INFO] Output MAT will be: %s\n', outputFullPath);

%% ---------- First pass: Scan & Timing ----------
fieldSelectionAll  = [1 1 1 1 1];
extractHeader      = 1;
extractModeAll     = 1;

fileListKept       = strings(1, numberOfKeptChannels);
resolvedPaths      = strings(1, numberOfKeptChannels); % Store found paths
headersCell        = cell(1, numberOfKeptChannels);
samplingRateArray  = nan(1, numberOfKeptChannels);
effectiveLengthArr = nan(1, numberOfKeptChannels); 
badChannelMaskFull = false(1, nTotalCh);
ADBitVoltsPerKeep  = nan(1, numberOfKeptChannels);

all_timestamps_us_Cell = cell(1, numberOfKeptChannels);
all_nValidSamples_Cell = cell(1, numberOfKeptChannels);
all_first_T_us         = nan(1, numberOfKeptChannels);
all_last_T_us_plus_duration = nan(1, numberOfKeptChannels);

replacementInfo.usedReplacementFor8 = false;
replacementInfo.sourceChannel       = NaN;
replacementInfo.sourceFile          = "";
replacementInfo.note                = "";

fprintf('\n[INFO] First pass: scan files (Fuzzy Match), sizes, rates, TIMING\n');
for keptIndex = 1:numberOfKeptChannels
    channelNumber = kept_channels(keptIndex);

    % 1. Determine Source Channel
    sourceChannelThisRow = channelNumber;
    if eightBad && (channelNumber == 8)
        sourceChannelThisRow = 9; % Force 9
        replacementInfo.usedReplacementFor8 = true;
        replacementInfo.sourceChannel       = sourceChannelThisRow;
    end

    % 2. FIND FILE (Fuzzy Match)
    foundPath = findCscFile(sourceChannelThisRow);
    
    if isempty(foundPath)
        warning('[WARN] No matching file found for CSC%d (Row %d). Marking bad.', sourceChannelThisRow, channelNumber);
        badChannelMaskFull(channelNumber) = true;
        effectiveLengthArr(keptIndex) = 0;
        continue;
    end
    
    % Store resolved path for Pass 2
    resolvedPaths(keptIndex) = foundPath;
    fileListKept(keptIndex)  = foundPath;

    % 3. Read Data
    try
        [timestamps_us, ~, sampleFrequencies, numberValidSamples, samplesAD, headerLines] = ...
            Nlx2MatCSC(char(foundPath), fieldSelectionAll, extractHeader, extractModeAll, []);

        all_timestamps_us_Cell{keptIndex} = timestamps_us;
        all_nValidSamples_Cell{keptIndex} = numberValidSamples;

        recordBlockLength = size(samplesAD,1);
        validPerRecord    = min(recordBlockLength, max(0, numberValidSamples(:)'));
        effectiveLengthArr(keptIndex) = sum(validPerRecord);

        % Rate
        samplingRateThis = mode(double(sampleFrequencies(sampleFrequencies>0)));
        if ~(isfinite(samplingRateThis) && samplingRateThis>0)
             % Try header parse
             ln = headerLines(contains(headerLines,'SamplingFrequency','IgnoreCase',true));
             if ~isempty(ln), tok = regexp(ln{1}, '[\-+]?\d+(\.\d+)?', 'match'); 
                 if ~isempty(tok), samplingRateThis = str2double(tok{1}); end
             end
        end
        samplingRateArray(keptIndex) = samplingRateThis;

        % ADBitVolts
        adbv = NaN;
        idx = find(contains(headerLines,'ADBitVolts','IgnoreCase',true),1,'first');
        if ~isempty(idx)
            tok = regexp(headerLines{idx}, '[\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?', 'match');
            if ~isempty(tok), adbv = str2double(tok{1}); end
        end
        if ~(isfinite(adbv) && adbv>0), adbv = fallbackADBV; end
        ADBitVoltsPerKeep(keptIndex) = adbv;

        headersCell{keptIndex} = headerLines;

        [~, fNameOnly, fExt] = fileparts(foundPath);
        fprintf('  Row CSC%-2d (File: %s): %d samples | %g Hz\n', ...
            channelNumber, [fNameOnly fExt], effectiveLengthArr(keptIndex), samplingRateArray(keptIndex));

        % Timing Bounds
        if ~isempty(timestamps_us) && isfinite(samplingRateThis)
            all_first_T_us(keptIndex) = timestamps_us(1);
            samples_per_us = samplingRateThis / 1e6;
            dur_last_us = (double(numberValidSamples(end)) - 1) / samples_per_us;
            all_last_T_us_plus_duration(keptIndex) = double(timestamps_us(end)) + dur_last_us;
        end

        if eightBad && (channelNumber == 8)
            replacementInfo.sourceFile = string(foundPath);
            replacementInfo.note = "Row 8 populated from channel 9 file.";
            fprintf('   -> [REPLACEMENT] Channel 8 filled using file: %s\n', [fNameOnly fExt]);
        end

    catch ME
        warning('[WARN] Read failure %s: %s', foundPath, ME.message);
        badChannelMaskFull(channelNumber) = true;
    end
end

%% ---------- Unified Rate & Disk Prep ----------
goodMask = (effectiveLengthArr>0) & isfinite(samplingRateArray) & samplingRateArray>0;
if ~any(goodMask)
    error('[ERROR] No valid channels found. Check if files exist or are corrupted.');
end
unifiedSamplingRate_Hz = mode(round(samplingRateArray(goodMask)));
fprintf('\n[INFO] Unified sampling rate: %g Hz\n', unifiedSamplingRate_Hz);

global_min_T_us = min(all_first_T_us(goodMask));
global_max_T_us = max(all_last_T_us_plus_duration(goodMask));
total_duration_us = global_max_T_us - global_min_T_us;
samples_per_us = unifiedSamplingRate_Hz / 1e6;
maxSamplesAcrossKept = round(total_duration_us * samples_per_us) + 1;

bytesPerElement = strcmpi(storeClass,'single')*4 + strcmpi(storeClass,'double')*8;
approxGB = (numberOfKeptChannels*maxSamplesAcrossKept*bytesPerElement)/1e9;

fprintf('[INFO] Global Duration: %.2fs. Creating Array: %dx%d (~%.2f GB)\n', ...
    total_duration_us/1e6, numberOfKeptChannels, maxSamplesAcrossKept, approxGB);

if exist(outputFullPath, 'file'), delete(outputFullPath); end
matFileObject = matfile(outputFullPath, 'Writable', true);

switch lower(storeClass)
    case 'single', matFileObject.d = single(NaN(numberOfKeptChannels, maxSamplesAcrossKept));
    case 'double', matFileObject.d = NaN(numberOfKeptChannels, maxSamplesAcrossKept);
end

matFileObject.sfx           = unifiedSamplingRate_Hz;
matFileObject.badch         = badChannelMaskFull;
matFileObject.chan_labels   = arrayfun(@(k) sprintf('CSC%d', k), 1:nTotalCh, 'UniformOutput', false);
matFileObject.kept_channels = kept_channels;
matFileObject.headersCell   = headersCell;
matFileObject.units         = 'microvolts';
meta.basePath        = basePath;
meta.createdOn       = datestr(now);
meta.fileListKept    = fileListKept;
meta.ADBitVolts      = ADBitVoltsPerKeep;
meta.global_min_T_us = global_min_T_us;
meta.eightBad        = eightBad;
meta.replacementInfo = replacementInfo;
matFileObject.meta   = meta;

%% ---------- Second pass: Write Data ----------
fprintf('\n[INFO] Second pass: Writing to disk...\n');
ticOverall = tic;

for keptIndex = 1:numberOfKeptChannels
    channelNumber = kept_channels(keptIndex);
    
    % Use path resolved in Pass 1
    cscFilePathToRead = resolvedPaths(keptIndex); 

    if badChannelMaskFull(channelNumber) || effectiveLengthArr(keptIndex)==0 || cscFilePathToRead==""
        continue;
    end

    % Read Samples Only
    [~, ~, ~, ~, samplesAD] = Nlx2MatCSC(char(cscFilePathToRead), [1 1 1 1 1], 0, 1, []); 

    timestamps_us      = all_timestamps_us_Cell{keptIndex};
    numberValidSamples = all_nValidSamples_Cell{keptIndex};
    
    flatSignal_uV = nan(1, maxSamplesAcrossKept);
    scaleFactor   = ADBitVoltsPerKeep(keptIndex) * 1e6; 
    
    samples_per_us = unifiedSamplingRate_Hz / 1e6;
    recCount = size(samplesAD,2);
    
    for rIdx = 1:recCount
        valC = min(512, max(0, numberValidSamples(rIdx)));
        if valC == 0, continue; end

        chunk_uV = double(samplesAD(1:valC, rIdx)) * scaleFactor;
        if invertPolarity, chunk_uV = -chunk_uV; end

        tStart = double(timestamps_us(rIdx));
        startSample = round((tStart - global_min_T_us) * samples_per_us) + 1;
        endSample   = startSample + valC - 1;

        % Bounds Check
        wStart = max(1, startSample);
        wEnd   = min(maxSamplesAcrossKept, endSample);
        
        dStart = max(1, 1 - (startSample - 1));
        dEnd   = valC - (endSample - wEnd);
        
        if wStart <= wEnd && dStart <= dEnd
             flatSignal_uV(wStart:wEnd) = chunk_uV(dStart:dEnd);
        end
    end

    if reverseTime, flatSignal_uV = fliplr(flatSignal_uV); end
    
    switch lower(storeClass)
        case 'single', matFileObject.d(keptIndex, 1:maxSamplesAcrossKept) = single(flatSignal_uV);
        case 'double', matFileObject.d(keptIndex, 1:maxSamplesAcrossKept) = double(flatSignal_uV);
    end

    if mod(keptIndex,2)==0 || keptIndex==numberOfKeptChannels
        fprintf('  [%3d/%3d] Written Row CSC%-2d\n', keptIndex, numberOfKeptChannels, channelNumber);
    end
end

fprintf('[INFO] Done. Saved: %s\n', outputFullPath);
end