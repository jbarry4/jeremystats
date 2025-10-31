function Pipeline_Main(inputFolder, dataMatPath, varargin)
% Pipeline_Main — runs all sub-pipelines, builds TWO compact triptychs
% (SOLID & SPUTTER) at native resolution, plus a merged stats CSV.
%
% Triptych columns (left → center → right):
%   LEFT  : [VoltageRaster_EventsAvg, CSD_CenterSlices_Waveform_AvgGroups, Spectrogram_Waveform_Stacked_ThirdEvent]  (stacked vertically)
%   CENTER: [EventStacks_ampWidth_Avg]  (the long one)
%   RIGHT : [CSDRaster_Avg, CSD_TimeAvgSlices_Waveforms_AvgGroups]          (stacked vertically)
%
% Robust to missing images/CSVs (warns and continues).

% ---------- Output hub ----------
masterOutDir = fullfile(inputFolder, 'Pipeline Output');
if ~exist(masterOutDir, 'dir'), mkdir(masterOutDir); end
triptychSOLID   = fullfile(masterOutDir, 'Master_Compact_SOLID.png');
triptychSPUTTER = fullfile(masterOutDir, 'Master_Compact_SPUTTER.png');
masterCSV       = fullfile(masterOutDir, 'Master_Stats.csv');

% ---------- 1) EventStacks (CENTER) ----------
evtStacksRes = [];
try
    evtStacksRes = EventStacks_ampWidth_Avg_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'EventStacks_ampWidth_Avg_Pipeline failed: %s', ME.message);
end

% ---------- 2) Voltage Raster (LEFT) ----------
voltRasterRes = [];
try
    voltRasterRes = VoltageRaster_EventsAvg_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'VoltageRaster_EventsAvg_Pipeline failed: %s', ME.message);
end

% ---------- 3) CSD Raster (RIGHT) ----------
csdRasterRes = [];
try
    csdRasterRes = CSDRaster_Avg_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'CSDRaster_Avg_Pipeline failed: %s', ME.message);
end

% ---------- 4) CSD Center Slices + Vertical Waveforms (LEFT) ----------
csdSlicesRes = [];
try
    csdSlicesRes = CSD_CenterSlices_Waveform_AvgGroups_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'CSD_CenterSlices_Waveform_AvgGroups_Pipeline failed: %s', ME.message);
end

% ---------- 5) CSD Time-Avg Slices + Vertical Waveforms (RIGHT) ----------
csdTimeAvgRes = [];
try
    csdTimeAvgRes = CSD_TimeAvgSlices_Waveforms_AvgGroups_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'CSD_TimeAvgSlices_Waveforms_AvgGroups_Pipeline failed: %s', ME.message);
end

% ---------- 6) Spectrogram + Waveform (LEFT, bottom) ----------
spec3rdRes = [];
try
    spec3rdRes = Spectrogram_Waveform_Stacked_ThirdEvent_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'Spectrogram_Waveform_Stacked_ThirdEvent_Pipeline failed: %s', ME.message);
end

% ---------- 7) ThetaRaster (LEFT, bottom) ----------
thetaRes = [];
try
    thetaRes = ThetaRaster_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'ThetaRaster_Pipeline failed: %s', ME.message);
end

% ---------- Build SOLID triptych ----------
try
    colLeft_SOL = stackVerticalHiRes({ ...
        getFileIfExists(getFieldSafe(voltRasterRes,'pngSolid')), ...
        getFileIfExists(getFieldSafe(csdSlicesRes,'pngSolid')), ...
        getFileIfExists(getFieldSafe(thetaRes,    'pngSolid')), ...   
        getFileIfExists(getFieldSafe(spec3rdRes, 'pngSolid'))}, 6);   % spectrogram at bottom-left
    colCtr_SOL  = getFileIfExists(getFieldSafe(evtStacksRes,'pngSolid'));
    colRight_SOL= stackVerticalHiRes({ ...
        getFileIfExists(getFieldSafe(csdRasterRes,'pngSolid')), ...
        getFileIfExists(getFieldSafe(csdTimeAvgRes,'pngSolid'))}, 6);

    cols_SOL = filterNonEmpty({colLeft_SOL, colCtr_SOL, colRight_SOL});
    if isempty(cols_SOL)
        warning('Pipeline:NoSolidPNGs', 'No SOLID images found; SOLID compact montage not created.');
    else
        composeColumnsHiRes(cols_SOL, triptychSOLID, 10);
        fprintf('Master SOLID compact montage saved: %s\n', triptychSOLID);
    end
catch ME
    warning(ME.identifier, 'Failed to build SOLID compact montage: %s', ME.message);
end

% ---------- Build SPUTTER triptych ----------
try
    colLeft_SPU = stackVerticalHiRes({ ...
        getFileIfExists(getFieldSafe(voltRasterRes,'pngSputter')), ...
        getFileIfExists(getFieldSafe(csdSlicesRes,'pngSputter')), ...
        getFileIfExists(getFieldSafe(thetaRes,    'pngSputter')), ...
        getFileIfExists(getFieldSafe(spec3rdRes, 'pngSputter'))}, 6);
    colCtr_SPU  = getFileIfExists(getFieldSafe(evtStacksRes,'pngSputter'));
    colRight_SPU= stackVerticalHiRes({ ...
        getFileIfExists(getFieldSafe(csdRasterRes,'pngSputter')), ...
        getFileIfExists(getFieldSafe(csdTimeAvgRes,'pngSputter'))}, 6);

    cols_SPU = filterNonEmpty({colLeft_SPU, colCtr_SPU, colRight_SPU});
    if isempty(cols_SPU)
        warning('Pipeline:NoSputterPNGs', 'No SPUTTER images found; SPUTTER compact montage not created.');
    else
        composeColumnsHiRes(cols_SPU, triptychSPUTTER, 10);
        fprintf('Master SPUTTER compact montage saved: %s\n', triptychSPUTTER);
    end
catch ME
    warning(ME.identifier, 'Failed to build SPUTTER compact montage: %s', ME.message);
end

% ---------- Merge available stats into a single CSV ----------
T = table();
T = tryAddCSV(T, evtStacksRes,  'EventStacks');
T = tryAddCSV(T, voltRasterRes, 'VoltageRaster');
T = tryAddCSV(T, csdRasterRes,  'CSDRaster');
T = tryAddCSV(T, csdSlicesRes,  'CSDCenterSlices');
T = tryAddCSV(T, csdTimeAvgRes, 'CSDTimeAvg');
% (Spectrogram block has no CSV)

try
    if isempty(T)
        T = table(string(datetime('now')), "EMPTY", 'VariableNames', {'GeneratedAt','Note'});
    end
    writetable(T, masterCSV);
    fprintf('Master stats CSV: %s\n', masterCSV);
catch ME
    warning(ME.identifier, 'Failed writing master stats CSV: %s', ME.message);
end
end

% ================= helpers (I/O-safe, native-res composition) ================

function v = getFieldSafe(S, fieldName)
if ~(isstruct(S) && isfield(S, fieldName))
    v = "";
else
    v = string(S.(fieldName));
end
end

function p = getFileIfExists(s)
p = "";
if strlength(s) > 0
    c = char(s);
    if isfile(c), p = c; end
end
end

function C = filterNonEmpty(Cin)
C = {};
for i = 1:numel(Cin)
    if ~isempty(Cin{i})
        C{end+1} = Cin{i}; %#ok<AGROW>
    end
end
end

function outPath = stackVerticalHiRes(pngList, sep)
% Returns a path to a temp PNG that is a vertical stack of the inputs at native res.
% If zero or one valid png in list, returns [] or that single path as-is.
pngList = pngList(~cellfun(@isempty, pngList));
if isempty(pngList)
    outPath = [];
    return;
elseif numel(pngList) == 1
    outPath = pngList{1};
    return;
end

% read
imgs = cell(numel(pngList),1);
widths = zeros(numel(pngList),1);
heights= zeros(numel(pngList),1);
for i = 1:numel(pngList)
    imgs{i} = imread(pngList{i});
    [h,w,~] = size(imgs{i});
    widths(i)  = w;
    heights(i) = h;
end
Wmax = max(widths);

% prep white canvas
cls = class(imgs{1});
switch cls
    case {'uint8'},  whiteVal = uint8(255);
    case {'uint16'}, whiteVal = uint16(65535);
    case {'double'}, whiteVal = 1;
    case {'single'}, whiteVal = single(1);
    otherwise, error('Unsupported image class: %s', cls);
end
totalH = sum(heights) + sep*(numel(imgs)-1);
if size(imgs{1},3) == 1
    out = repmat(whiteVal, [totalH, Wmax, 1]);
else
    out = repmat(reshape(whiteVal,1,1,[]), [totalH, Wmax, size(imgs{1},3)]);
end

% paste
y = 1;
for i = 1:numel(imgs)
    I = imgs{i}; [h,w,c] = size(I);
    out(y:y+h-1, 1:w, 1:c) = I;
    y = y + h;
    if i < numel(imgs), out(y:y+sep-1, :, :) = whiteVal; y = y + sep; end
end

% save to a temp in master output dir sibling
tmpDir = tempname; mkdir(tmpDir);
outPath = fullfile(tmpDir, sprintf('colV_%s.png', char(java.util.UUID.randomUUID)));
imwrite(out, outPath);
end

function composeColumnsHiRes(columnImgs, outPath, colSep)
% Compose LEFT→RIGHT at native res, no resampling.
assert(~isempty(columnImgs), 'composeColumnsHiRes: no columns to compose.');

% read columns
cols = cell(numel(columnImgs),1);
cw   = zeros(numel(columnImgs),1);
ch   = zeros(numel(columnImgs),1);
for i = 1:numel(columnImgs)
    cols{i} = imread(columnImgs{i});
    [h,w,~] = size(cols{i});
    cw(i) = w; ch(i) = h;
end

Hmax = max(ch);
Wsum = sum(cw) + colSep*(numel(cols)-1);

% white canvas of proper class
cls = class(cols{1});
switch cls
    case {'uint8'},  whiteVal = uint8(255);
    case {'uint16'}, whiteVal = uint16(65535);
    case {'double'}, whiteVal = 1;
    case {'single'}, whiteVal = single(1);
    otherwise, error('Unsupported image class: %s', cls);
end
if size(cols{1},3) == 1
    out = repmat(whiteVal, [Hmax, Wsum, 1]);
else
    out = repmat(reshape(whiteVal,1,1,[]), [Hmax, Wsum, size(cols{1},3)]);
end

% paste columns top-aligned
x = 1;
for i = 1:numel(cols)
    I = cols{i}; [h,w,c] = size(I);
    out(1:h, x:x+w-1, 1:c) = I;
    x = x + w;
    if i < numel(cols), out(:, x:x+colSep-1, :) = whiteVal; x = x + colSep; end
end

imwrite(out, outPath);
end

function T = tryAddCSV(T, res, tag)
try
    if isstruct(res) && isfield(res,'statsCSV') && ~isempty(res.statsCSV) && isfile(res.statsCSV)
        C = readtable(res.statsCSV);
        if ~ismember('source', C.Properties.VariableNames)
            C.source = repmat(string(tag), height(C), 1);
        else
            C.source = string(C.source);
        end
        T = vertcatSafe(T, C);
    end
catch ME
    warning(ME.identifier, 'Failed to merge stats from %s: %s', tag, ME.message);
end
end

function T = vertcatSafe(A, B)
if isempty(A), T = B; return; end
if isempty(B), T = A; return; end
allVars = union(A.Properties.VariableNames, B.Properties.VariableNames, 'stable');
A = addMissingVars(A, allVars);
B = addMissingVars(B, allVars);
T = [A; B]; %#ok<AGROW>
end

function T = addMissingVars(T, allVars)
missing = setdiff(allVars, T.Properties.VariableNames, 'stable');
for k = 1:numel(missing)
    T.(missing{k}) = missingDefault();
end
T = T(:, allVars);
end

function x = missingDefault()
x = missing;
end
