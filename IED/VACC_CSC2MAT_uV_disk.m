function VACC_CSC2MAT_uV_disk(basePath, eightBad, varargin)
% VACC_CSC2MAT_uV_disk(basePath, eightBad, Name,Value,...)
% Convert a folder of Neuralynx CSC#.ncs → disk-backed .mat in MICROVOLTS.
% No spike detection — conversion only — with options to invert polarity and/or reverse time.
% NEW: required logical "eightBad" — if true, channel 8 will be replaced with data from channel 7.
%
% REQUIRED:
%   basePath   : folder containing CSC#.ncs files (e.g., CSC1.ncs..CSC64.ncs)
%   eightBad   : logical true/false; if true -> replace channel 8 with channel 7
%
% OPTIONS (Name,Value):
%   'nTotalCh'       (default 64)       : total channels expected (1..nTotalCh)
%   'evenOnly'       (default true)     : keep only even channels (2,4,6,...) if true
%   'keep'           (default [])       : explicit list of channels to keep (overrides evenOnly)
%   'storeClass'     (default 'single') : 'single' or 'double' for saved data
%   'outName'        (default auto)     : output MAT filename (placed in basePath)
%   'fallbackADBV'   (default 0.00000006103515625) : V/AD used if header lacks ADBitVolts
%   'reqsPath'       (default ./reqsPath): folder containing Nlx2MatCSC MEX if not on path
%   'invertPolarity' (default true)     : multiply by -1 after scaling to µV
%   'reverseTime'    (default false)    : reverse each channel’s time series (flip L↔R)
%
% OUTPUT .mat (disk-backed; saved in basePath):
%   d              : [nKept x maxN] MICROVOLTS (µV), NaN-padded
%   sfx            : unified sampling rate (Hz), mode across good kept channels
%   badch          : logical(1,nTotalCh), marks missing/bad (original indexing)
%   chan_labels    : {'CSC1'..'CSCn'}
%   kept_channels  : channels written
%   headersCell    : header lines for each kept channel (note: for ch8, header from ch7 if replaced)
%   units          : 'microvolts'
%   meta           : provenance (fileListKept, ADBitVolts, options used, and replacement info)
%
% Example:
%   VACC_CSC2MAT_uV_disk('/gpfs2/scratch/sakhava1/Rec', true, ...
%       'nTotalCh',64, 'evenOnly',true, 'invertPolarity',true, 'reverseTime',false);

%% ---------- Parse inputs ----------
fprintf('\n[INFO] Starting VACC_CSC2MAT_uV_disk\n');

inputParserObject = inputParser;
inputParserObject.addRequired('basePath', @(s)ischar(s)||isstring(s));
inputParserObject.addRequired('eightBad', @(x)islogical(x)||ismember(x,[0,1]));
inputParserObject.addParameter('nTotalCh', 64, @(x)isnumeric(x)&&isscalar(x)&&x>=1);
inputParserObject.addParameter('evenOnly', true, @(x)islogical(x)||ismember(x,[0,1]));
inputParserObject.addParameter('keep', [], @(v)isnumeric(v)&&isvector(v)&&all(v>=1));
inputParserObject.addParameter('storeClass', 'single', @(s)ischar(s)||isstring(s));
inputParserObject.addParameter('outName', '', @(s)ischar(s)||isstring(s));
inputParserObject.addParameter('fallbackADBV', 0.00000006103515625, @(x)isfinite(x)&&x>0); % V/AD
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
fprintf('[INFO] eightBad flag: %d (1 means replace channel 8 with channel 7)\n', eightBad);
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
sourceChannelFor8 = 7; % fixed by requirement
fprintf('[INFO] isChannel8Kept: %d | sourceChannelFor8: %d\n', isChannel8Kept, sourceChannelFor8);

%% ---------- Auto output name if empty ----------
if isempty(strtrim(outName))
    [~, tailFolderName] = fileparts(basePath);
    outName = sprintf('LL_input_%s_mex_disk_uV.mat', tailFolderName);
end
outputFullPath = fullfile(basePath, outName);
fprintf('[INFO] Output MAT will be: %s\n', outputFullPath);

%% ---------- First pass: sizes, sampling rates, ADBitVolts ----------
% Neuralynx flags:
%   FieldSelection = [Timestamps, ChannelNumbers, SampleFrequencies, NumberValidSamples, Samples] -> [1 1 1 1 1]
%   ExtractHeader = 1 to get header, ExtractMode = 1 (extract all)
fieldSelectionAll  = [1 1 1 1 1];
extractHeader      = 1;
extractModeAll     = 1;

fileListKept       = strings(1, numberOfKeptChannels);  % nominal filenames for rows
headersCell        = cell(1, numberOfKeptChannels);     % header per kept index (for ch8, we may store ch7 header)
samplingRateArray  = nan(1, numberOfKeptChannels);
effectiveLengthArr = nan(1, numberOfKeptChannels);
badChannelMaskFull = false(1, nTotalCh);
ADBitVoltsPerKeep  = nan(1, numberOfKeptChannels);

% Track replacement provenance (so users can see exactly what we did)
replacementInfo.usedReplacementFor8 = false;
replacementInfo.sourceChannel       = NaN;
replacementInfo.sourceFile          = "";
replacementInfo.note                = "";

fprintf('\n[INFO] First pass: scan files, sizes, sampling rates, ADBitVolts\n');
for keptIndex = 1:numberOfKeptChannels
    channelNumber = kept_channels(keptIndex);

    % Decide which physical file to read:
    % If eightBad==true and this row corresponds to channel 8, we will read channel 7 instead.
    sourceChannelThisRow = channelNumber;
    if eightBad && (channelNumber == 8)
        sourceChannelThisRow = sourceChannelFor8;  % 7
        fprintf('[INFO] Replacement engaged for channel 8 in FIRST PASS: reading CSC%d.ncs instead of CSC8.ncs\n', sourceChannelThisRow);
        replacementInfo.usedReplacementFor8 = true;
        replacementInfo.sourceChannel       = sourceChannelThisRow;
    end

    cscFilePathToRead = fullfile(basePath, sprintf('CSC%d.ncs', sourceChannelThisRow));
    fileListKept(keptIndex) = string(fullfile(basePath, sprintf('CSC%d.ncs', channelNumber))); % nominal/row label stays as CSC8 if row=8

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

        % Compute effective flattened length honoring NumberValidSamples per record
        recordBlockLength = size(samplesAD,1);      % usually 512
        validPerRecord    = min(recordBlockLength, max(0, numberValidSamples(:)'));
        effectiveLengthArr(keptIndex) = sum(validPerRecord);

        % Sampling frequency: mode across records; fallback to header if needed
        samplingRateThis = mode(double(sampleFrequencies(sampleFrequencies>0)));
        if ~(isfinite(samplingRateThis) && samplingRateThis>0)
            samplingFrequencyLine = headerLines(contains(headerLines,'SamplingFrequency','IgnoreCase',true));
            if ~isempty(samplingFrequencyLine)
                token = regexp(samplingFrequencyLine{1}, 'SamplingFrequency[^0-9eE.\-]*([\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?)', 'tokens', 'once');
                if ~isempty(token), samplingRateThis = str2double(token{1}); end
            end
        end
        samplingRateArray(keptIndex) = samplingRateThis;

        % Read ADBitVolts (V/AD); use fallback if missing
        adbv = NaN;
        idx = find(contains(headerLines,'ADBitVolts','IgnoreCase',true),1,'first');
        if ~isempty(idx)
            token = regexp(headerLines{idx}, 'ADBitVolts[^0-9eE.\-]*([\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?)', 'tokens', 'once');
            if ~isempty(token), adbv = str2double(token{1}); end
        end
        if ~(isfinite(adbv) && adbv>0)
            adbv = fallbackADBV;
            warning('[WARN] ADBitVolts missing for CSC%d; using fallback %.12g V/AD', sourceChannelThisRow, adbv);
        end
        ADBitVoltsPerKeep(keptIndex) = adbv;

        % Store header for this row (note: if row=8 and eightBad==true, this will be header from channel 7)
        headersCell{keptIndex} = headerLines;

        fprintf('  Row CSC%-2d (from CSC%-2d): %10d samples eff @ %g Hz | ADBitVolts=%.12g V/AD\n', ...
            channelNumber, sourceChannelThisRow, effectiveLengthArr(keptIndex), samplingRateArray(keptIndex), adbv);

        % Optional continuity check
        if ~isempty(timestamps_us) && isfinite(samplingRateThis) && samplingRateThis>0
            expectedStep_us = 512 * (1e6 / samplingRateThis);
            deltaT = diff(double(timestamps_us));
            if any(abs(deltaT - expectedStep_us) > 0.5 * expectedStep_us)
                warning('[WARN] Timing irregularity in %s (source ch %d). Gaps not interpolated.', cscFilePathToRead, sourceChannelThisRow);
            end
        end

        % Remember exact file used for replacement provenance
        if eightBad && (channelNumber == 8)
            replacementInfo.sourceFile = string(cscFilePathToRead);
            replacementInfo.note = "Row 8 populated from channel 7 for both passes.";
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

%% ---------- Prepare disk-backed target ----------
maxSamplesAcrossKept = max(effectiveLengthArr(goodMask));
bytesPerElement = strcmpi(storeClass,'single')*4 + strcmpi(storeClass,'double')*8;
approximateGigabytesOnDisk = (numberOfKeptChannels*maxSamplesAcrossKept*bytesPerElement)/1e9;

fprintf('[INFO] Creating disk-backed array: %d x %d (%s) ~ %.2f GB on disk\n', ...
    numberOfKeptChannels, maxSamplesAcrossKept, storeClass, approximateGigabytesOnDisk);

if exist(outputFullPath, 'file')
    fprintf('[INFO] Output file already exists. Deleting to start fresh...\n');
    delete(outputFullPath);
end
matFileObject = matfile(outputFullPath, 'Writable', true);

switch lower(storeClass)
    case 'single', matFileObject.d = single(NaN(numberOfKeptChannels, maxSamplesAcrossKept));
    case 'double', matFileObject.d = NaN(numberOfKeptChannels, maxSamplesAcrossKept);
    otherwise, error('[ERROR] storeClass must be ''single'' or ''double''.');
end

% Save metadata up front so partial files are still informative
matFileObject.sfx           = unifiedSamplingRate_Hz;
matFileObject.badch         = badChannelMaskFull;
matFileObject.chan_labels   = arrayfun(@(k) sprintf('CSC%d', k), 1:nTotalCh, 'UniformOutput', false);
matFileObject.kept_channels = kept_channels;
matFileObject.headersCell   = headersCell;
matFileObject.units         = 'microvolts';

meta.basePath        = basePath;
meta.createdOn       = datestr(now);
meta.nTotalCh        = nTotalCh;
meta.nKept           = numberOfKeptChannels;
meta.reader          = ['Nlx2MatCSC (', mexext, ')'];
meta.storeClass      = storeClass;
meta.note            = 'Disk-backed; NaN-padded; per-channel AD→µV scaling during write.';
meta.fileListKept    = fileListKept;                   % nominal row filenames (row 8 shows CSC8.ncs)
meta.ADBitVolts      = ADBitVoltsPerKeep;              % V/AD used per row
meta.scaleFactor_uV  = ADBitVoltsPerKeep * 1e6;        % µV/AD per row
meta.invertPolarity  = invertPolarity;                 
meta.reverseTime     = reverseTime;                    
meta.eightBad        = eightBad;                       % NEW: record the flag
meta.replacementInfo = replacementInfo;                % NEW: detailed provenance for ch8 replacement
matFileObject.meta   = meta;

%% ---------- Second pass: read → flatten (NValid) → scale to µV → invert/flip → write ----------
fprintf('\n[INFO] Second pass: writing MICROVOLT data to disk (progress below)\n');
ticOverall = tic;

for keptIndex = 1:numberOfKeptChannels
    channelNumber = kept_channels(keptIndex);

    if badChannelMaskFull(channelNumber) || effectiveLengthArr(keptIndex)==0
        fprintf('  Row CSC%-2d: skipped (bad/missing)\n', channelNumber);
        continue;
    end

    % Again, if eightBad and the row is channel 8, we will read from channel 7
    sourceChannelThisRow = channelNumber;
    if eightBad && (channelNumber == 8)
        sourceChannelThisRow = sourceChannelFor8;  % 7
        fprintf('[INFO] Replacement engaged for channel 8 in SECOND PASS: reading CSC%d.ncs instead of CSC8.ncs\n', sourceChannelThisRow);
    end

    cscFilePathToRead = fullfile(basePath, sprintf('CSC%d.ncs', sourceChannelThisRow));
    if ~isfile(cscFilePathToRead)
        warning('[WARN] Source file missing for row CSC%d (wanted CSC%d): %s. Skipping row.', ...
            channelNumber, sourceChannelThisRow, cscFilePathToRead);
        continue;
    end

    % Read without header (faster): same FieldSelection; ExtractHeader=0; ExtractMode=1
    [~, ~, ~, numberValidSamples, samplesAD] = Nlx2MatCSC(cscFilePathToRead, [1 1 1 1 1], 0, 1, []); %#ok<ASGLU>

    recordBlockLength = size(samplesAD,1);
    numberOfRecords   = size(samplesAD,2);

    % Preallocate flat vector in AD units then fill honoring NValid per record
    flatSignalAD = nan(1, effectiveLengthArr(keptIndex)); % AD units
    writePosition = 1;

    for recordIndex = 1:numberOfRecords
        validCount = min(recordBlockLength, max(0, numberValidSamples(recordIndex)));
        if validCount > 0
            flatSignalAD(writePosition:writePosition+validCount-1) = double(samplesAD(1:validCount, recordIndex));
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

    % Time reverse (left↔right flip) if requested
    if reverseTime
        flatSignal_uV = fliplr(flatSignal_uV);
    end

    % Cast and write into the disk-backed matrix
    switch lower(storeClass)
        case 'single', flatSignal_uV = single(flatSignal_uV);
        case 'double', flatSignal_uV = double(flatSignal_uV);
    end
    matFileObject.d(keptIndex, 1:numel(flatSignal_uV)) = flatSignal_uV;

    % Progress prints
    if mod(keptIndex,2)==0 || keptIndex==numberOfKeptChannels
        elapsedSeconds = toc(ticOverall);
        fprintf('  [%3d/%3d] Row CSC%-2d (from CSC%-2d) written | %.1f%% | elapsed %s | invert=%d | reverse=%d\n', ...
            keptIndex, numberOfKeptChannels, channelNumber, sourceChannelThisRow, ...
            100*keptIndex/numberOfKeptChannels, duration(0,0,elapsedSeconds,"Format","mm:ss"), ...
            invertPolarity, reverseTime);
    end
end

%% ---------- Done ----------
fprintf('\n[INFO] Done.\n[INFO] Saved MICROVOLT conversion file:\n  %s\n', outputFullPath);
fprintf('[INFO] Quick check (in MATLAB):\n');
fprintf('  m = matfile(''%s''); size(m,''d''), m.units, m.sfx, m.meta.eightBad, m.meta.replacementInfo\n', outputFullPath);

end
