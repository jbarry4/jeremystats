function VACC_Pipeline_Main(eventsFolder, rawDataFolder, varargin)
% VACC_Pipeline_Main — master orchestrator (SOLID & SPUTTER compact montages + merged CSV)
% NOW accepts two separate folders:
%   eventsFolder : has Solid/ and Sputter/ (sorted event PNGs) and an .xlsx with on/off times
%   rawDataFolder: has raw .ncs/.nse files, headers, ech.mat, or a pre-converted .mat
%
% For now we ONLY develop the first subfunction:
%   - VACC_EventStacks_ampWidth_Avg_Pipeline (implemented below as a separate file)
% The rest are left as commented placeholders so wiring stays obvious.

fprintf('\n=============================================\n');
fprintf('VACC_Pipeline_Main — starting\n');
fprintf('eventsFolder   : %s\n', string(eventsFolder));
fprintf('rawDataFolder  : %s\n', string(rawDataFolder));
fprintf('=============================================\n\n');

% ---------- Output hub (same as before) ----------
masterOutputFolder = fullfile(eventsFolder, 'Pipeline Output');
if ~exist(masterOutputFolder, 'dir')
    mkdir(masterOutputFolder);
    fprintf('Created pipeline output folder: %s\n', masterOutputFolder);
end
triptychSolidPath   = fullfile(masterOutputFolder, 'Master_Compact_SOLID.png');
triptychSputterPath = fullfile(masterOutputFolder, 'Master_Compact_SPUTTER.png');
masterStatsCsvPath  = fullfile(masterOutputFolder, 'Master_Stats.csv');

% ---------- [1/6] EventStacks (CENTER column) ----------
eventStacksResult = struct();   % will hold pngSolid/pngSputter/statsCSV, etc.
try
    fprintf('[1/6] Running VACC_EventStacks_ampWidth_Avg_Pipeline ...\n');
    eventStacksResult = VACC_EventStacks_ampWidth_Avg_Pipeline(eventsFolder, rawDataFolder, varargin{:});
    fprintf('  ✓ EventStacks module done.\n\n');
catch ME
    warning(ME.identifier, 'EventStacks module failed: %s', ME.message);
end

% ---------- [2/6] Voltage Raster (LEFT, top) ----------
% fprintf('[2/6] VoltageRaster_EventsAvg_Pipeline (placeholder)\n');
% voltageRasterResult = VoltageRaster_EventsAvg_Pipeline(eventsFolder, rawDataFolder, varargin{:});

% ---------- [3/6] CSD Raster (RIGHT, top) ----------
% fprintf('[3/6] CSDRaster_Avg_Pipeline (placeholder)\n');
% csdRasterResult = CSDRaster_Avg_Pipeline(eventsFolder, rawDataFolder, varargin{:});

% ---------- [4/6] CSD Center Slices + Waveforms (LEFT, middle) ----------
% fprintf('[4/6] CSD_CenterSlices_Waveform_AvgGroups_Pipeline (placeholder)\n');
% csdSlicesResult = CSD_CenterSlices_Waveform_AvgGroups_Pipeline(eventsFolder, rawDataFolder, varargin{:});

% ---------- [5/6] CSD Time-Avg Slices + Waveforms (RIGHT, bottom) ----------
% fprintf('[5/6] CSD_TimeAvgSlices_Waveforms_AvgGroups_Pipeline (placeholder)\n');
% csdTimeAvgResult = CSD_TimeAvgSlices_Waveforms_AvgGroups_Pipeline(eventsFolder, rawDataFolder, varargin{:});

% ---------- [6/6] Spectrogram + Waveform (LEFT, bottom) ----------
% fprintf('[6/6] Spectrogram_Waveform_Stacked_ThirdEvent_Pipeline (placeholder)\n');
% spectroThirdResult = Spectrogram_Waveform_Stacked_ThirdEvent_Pipeline(eventsFolder, rawDataFolder, varargin{:});

% ============================================================
% Build SOLID compact montage (LEFT stack | CENTER | RIGHT stack)
% For now, only the CENTER column (EventStacks) exists. Others are empty.
% ============================================================
fprintf('Composing SOLID compact montage ...\n');
try
    columnLeft_SOL   = [];  % placeholder until left modules are implemented
    columnCenter_SOL = getFileIfExists(getFieldSafe(eventStacksResult, 'pngSolid'));
    columnRight_SOL  = [];  % placeholder until right modules are implemented

    solidColumns = filterNonEmpty({columnLeft_SOL, columnCenter_SOL, columnRight_SOL});
    if isempty(solidColumns)
        warning('VACC:NoSolidPNGs', 'No SOLID images found; SOLID compact montage not created.');
    else
        composeColumnsHiRes(solidColumns, triptychSolidPath, 10);
        fprintf('  ✓ SOLID montage saved: %s\n', triptychSolidPath);
    end
catch ME
    warning(ME.identifier, 'Failed to build SOLID montage: %s', ME.message);
end

% ============================================================
% Build SPUTTER compact montage (LEFT stack | CENTER | RIGHT stack)
% For now, only the CENTER column (EventStacks) exists. Others are empty.
% ============================================================
fprintf('Composing SPUTTER compact montage ...\n');
try
    columnLeft_SPU   = [];  % placeholder until left modules are implemented
    columnCenter_SPU = getFileIfExists(getFieldSafe(eventStacksResult, 'pngSputter'));
    columnRight_SPU  = [];  % placeholder until right modules are implemented

    sputterColumns = filterNonEmpty({columnLeft_SPU, columnCenter_SPU, columnRight_SPU});
    if isempty(sputterColumns)
        warning('VACC:NoSputterPNGs', 'No SPUTTER images found; SPUTTER compact montage not created.');
    else
        composeColumnsHiRes(sputterColumns, triptychSputterPath, 10);
        fprintf('  ✓ SPUTTER montage saved: %s\n', triptychSputterPath);
    end
catch ME
    warning(ME.identifier, 'Failed to build SPUTTER montage: %s', ME.message);
end

% ============================================================
% Merge available stats into a single CSV
% For now, only the EventStacks CSV may exist.
% ============================================================
fprintf('Merging module stats into one CSV ...\n');
mergedTable = table();

% Only EventStacks for now
mergedTable = tryAddCSV(mergedTable, eventStacksResult, 'EventStacks');

% Uncomment these as modules go live:
% mergedTable = tryAddCSV(mergedTable, voltageRasterResult, 'VoltageRaster');
% mergedTable = tryAddCSV(mergedTable, csdRasterResult,     'CSDRaster');
% mergedTable = tryAddCSV(mergedTable, csdSlicesResult,     'CSDCenterSlices');
% mergedTable = tryAddCSV(mergedTable, csdTimeAvgResult,    'CSDTimeAvg');
% (Spectrogram block has no CSV)

try
    if isempty(mergedTable)
        mergedTable = table(string(datetime('now')), "EMPTY", ...
            'VariableNames', {'GeneratedAt','Note'});
        fprintf('  (No module CSVs present; wrote a stub.)\n');
    end
    writetable(mergedTable, masterStatsCsvPath);
    fprintf('  ✓ Master stats CSV: %s\n', masterStatsCsvPath);
catch ME
    warning(ME.identifier, 'Failed to write master stats CSV: %s', ME.message);
end

fprintf('\nVACC_Pipeline_Main — done.\n\n');
end

% ================= helpers (I/O-safe, native-res composition) ================

function value = getFieldSafe(structInput, fieldName)
% Return "" if struct/field missing; otherwise string(value)
if ~(isstruct(structInput) && isfield(structInput, fieldName))
    value = "";
else
    value = string(structInput.(fieldName));
end
end

function pathOut = getFileIfExists(pathInString)
% Return char(path) if file exists; otherwise empty string
pathOut = "";
if strlength(pathInString) > 0
    c = char(pathInString);
    if isfile(c)
        pathOut = c;
    end
end
end

function nonEmpty = filterNonEmpty(candidates)
% Drop empty cells so montager only sees real paths
nonEmpty = {};
for i = 1:numel(candidates)
    if ~isempty(candidates{i})
        nonEmpty{end+1} = candidates{i}; %#ok<AGROW>
    end
end
end

function outPath = stackVerticalHiRes(pngList, separatorPixels)
% Vertical stack at native resolution. Returns a temp PNG path.
% If zero or one valid png in list, returns [] or that single path.
pngList = pngList(~cellfun(@isempty, pngList));
if isempty(pngList)
    outPath = [];
    return;
elseif numel(pngList) == 1
    outPath = pngList{1};
    return;
end

% Read images and compute canvas
imagesCell = cell(numel(pngList),1);
widths     = zeros(numel(pngList),1);
heights    = zeros(numel(pngList),1);
for i = 1:numel(pngList)
    imagesCell{i} = imread(pngList{i});
    [h, w, ~] = size(imagesCell{i});
    widths(i)  = w;
    heights(i) = h;
end
maxWidth = max(widths);

% Prepare white canvas (match class)
imgClass = class(imagesCell{1});
switch imgClass
    case {'uint8'},  whiteValue = uint8(255);
    case {'uint16'}, whiteValue = uint16(65535);
    case {'double'}, whiteValue = 1;
    case {'single'}, whiteValue = single(1);
    otherwise, error('Unsupported image class: %s', imgClass);
end
totalHeight = sum(heights) + separatorPixels * (numel(imagesCell)-1);
if size(imagesCell{1},3) == 1
    canvas = repmat(whiteValue, [totalHeight, maxWidth, 1]);
else
    canvas = repmat(reshape(whiteValue,1,1,[]), [totalHeight, maxWidth, size(imagesCell{1},3)]);
end

% Paste each image into the canvas
y = 1;
for i = 1:numel(imagesCell)
    I = imagesCell{i}; [h,w,c] = size(I);
    canvas(y:y+h-1, 1:w, 1:c) = I;
    y = y + h;
    if i < numel(imagesCell)
        canvas(y:y+separatorPixels-1, :, :) = whiteValue;
        y = y + separatorPixels;
    end
end

% Save to a temp file
tmpDir = tempname; mkdir(tmpDir);
outPath = fullfile(tmpDir, sprintf('colV_%s.png', char(java.util.UUID.randomUUID)));
imwrite(canvas, outPath);
end

function composeColumnsHiRes(columnImages, outputPath, columnSeparator)
% Compose columns LEFT→RIGHT at native resolution
assert(~isempty(columnImages), 'composeColumnsHiRes: no columns provided.');

% Read columns and compute canvas
cols = cell(numel(columnImages),1);
colW = zeros(numel(columnImages),1);
colH = zeros(numel(columnImages),1);
for i = 1:numel(columnImages)
    cols{i} = imread(columnImages{i});
    [h,w,~] = size(cols{i});
    colW(i) = w; colH(i) = h;
end
maxHeight = max(colH);
sumWidth  = sum(colW) + columnSeparator*(numel(cols)-1);

% Prepare white canvas
imgClass = class(cols{1});
switch imgClass
    case {'uint8'},  whiteValue = uint8(255);
    case {'uint16'}, whiteValue = uint16(65535);
    case {'double'}, whiteValue = 1;
    case {'single'}, whiteValue = single(1);
    otherwise, error('Unsupported image class: %s', imgClass);
end
if size(cols{1},3) == 1
    canvas = repmat(whiteValue, [maxHeight, sumWidth, 1]);
else
    canvas = repmat(reshape(whiteValue,1,1,[]), [maxHeight, sumWidth, size(cols{1},3)]);
end

% Paste columns top-aligned
x = 1;
for i = 1:numel(cols)
    I = cols{i}; [h,w,c] = size(I);
    canvas(1:h, x:x+w-1, 1:c) = I;
    x = x + w;
    if i < numel(cols)
        canvas(:, x:x+columnSeparator-1, :) = whiteValue;
        x = x + columnSeparator;
    end
end

imwrite(canvas, outputPath);
end

function T = tryAddCSV(T, moduleResult, tagString)
% Safe-append moduleResult.statsCSV to master table (adds "source" column)
try
    if isstruct(moduleResult) && isfield(moduleResult,'statsCSV') ...
            && ~isempty(moduleResult.statsCSV) && isfile(moduleResult.statsCSV)
        C = readtable(moduleResult.statsCSV);
        if ~ismember('source', C.Properties.VariableNames)
            C.source = repmat(string(tagString), height(C), 1);
        else
            C.source = string(C.source);
        end
        T = vertcatSafe(T, C);
    end
catch ME
    warning(ME.identifier, 'Failed to merge stats from %s: %s', tagString, ME.message);
end
end

function T = vertcatSafe(A, B)
% Vertically concatenate two tables with mismatched columns safely
if isempty(A), T = B; return; end
if isempty(B), T = A; return; end
allVars = union(A.Properties.VariableNames, B.Properties.VariableNames, 'stable');
A = addMissingVars(A, allVars);
B = addMissingVars(B, allVars);
T = [A; B]; %#ok<AGROW>
end

function T = addMissingVars(T, allVars)
missingVars = setdiff(allVars, T.Properties.VariableNames, 'stable');
for k = 1:numel(missingVars)
    T.(missingVars{k}) = missingDefault();
end
T = T(:, allVars);
end

function x = missingDefault()
x = missing;
end
