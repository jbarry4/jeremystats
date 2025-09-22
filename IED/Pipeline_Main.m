function Pipeline_Main(inputFolder, dataMatPath, varargin)
% Pipeline_Main — orchestrates sub-pipelines and builds TWO master montages
% and a merged CSV. Robust to missing pieces.

% ---------- Output hub ----------
masterOutDir = fullfile(inputFolder, 'Pipeline Output');
if ~exist(masterOutDir, 'dir'), mkdir(masterOutDir); end
masterPngSOLID   = fullfile(masterOutDir, 'Master_Montage_SOLID.png');
masterPngSPUTTER = fullfile(masterOutDir, 'Master_Montage_SPUTTER.png');
masterCSV        = fullfile(masterOutDir, 'Master_Stats.csv');

% ---------- 1) EventStacks ----------
evtStacksRes = [];
try
    evtStacksRes = EventStacks_ampWidth_Avg_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'EventStacks_ampWidth_Avg_Pipeline failed: %s', ME.message);
end

% ---------- 2) Voltage Raster (averages) ----------
voltRasterRes = [];
try
    voltRasterRes = VoltageRaster_EventsAvg_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'VoltageRaster_EventsAvg_Pipeline failed: %s', ME.message);
end

% ---------- 3) CSD Raster (averages) ----------
csdRasterRes = [];
try
    csdRasterRes = CSDRaster_Avg_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'CSDRaster_Avg_Pipeline failed: %s', ME.message);
end

% ---------- 4) CSD Center Slices + Vertical Waveforms (this request) ----------
csdSlicesRes = [];
try
    csdSlicesRes = CSD_CenterSlices_Waveform_AvgGroups_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'CSD_CenterSlices_Waveform_AvgGroups_Pipeline failed: %s', ME.message);
end

% ---------- 5) (placeholder) CSD Time-Avg ----------
% csdTimeAvgRes = [];
% try
%     csdTimeAvgRes = CSD_TimeAvg_Waveform_AvgGroups_Pipeline(inputFolder, dataMatPath, varargin{:});
% catch ME
%     warning(ME.identifier, 'CSD_TimeAvg_Waveform_AvgGroups_Pipeline failed: %s', ME.message);
% end

% ---------- Collect PNGs ----------
pngSOL = {};
pngSPU = {};

% EventStacks
if isstruct(evtStacksRes)
    if isfield(evtStacksRes, 'pngSolid')   && isfile(evtStacksRes.pngSolid),   pngSOL{end+1} = evtStacksRes.pngSolid; end
    if isfield(evtStacksRes, 'pngSputter') && isfile(evtStacksRes.pngSputter), pngSPU{end+1} = evtStacksRes.pngSputter; end
end

% Voltage Raster
if isstruct(voltRasterRes)
    if isfield(voltRasterRes, 'pngSolid')   && isfile(voltRasterRes.pngSolid),   pngSOL{end+1} = voltRasterRes.pngSolid; end
    if isfield(voltRasterRes, 'pngSputter') && isfile(voltRasterRes.pngSputter), pngSPU{end+1} = voltRasterRes.pngSputter; end
end

% CSD Raster
if isstruct(csdRasterRes)
    if isfield(csdRasterRes, 'pngSolid')   && isfile(csdRasterRes.pngSolid),   pngSOL{end+1} = csdRasterRes.pngSolid; end
    if isfield(csdRasterRes, 'pngSputter') && isfile(csdRasterRes.pngSputter), pngSPU{end+1} = csdRasterRes.pngSputter; end
end

% CSD Center Slices
if isstruct(csdSlicesRes)
    if isfield(csdSlicesRes, 'pngSolid')   && isfile(csdSlicesRes.pngSolid),   pngSOL{end+1} = csdSlicesRes.pngSolid; end
    if isfield(csdSlicesRes, 'pngSputter') && isfile(csdSlicesRes.pngSputter), pngSPU{end+1} = csdSlicesRes.pngSputter; end
end

% ---------- Build two hi-res montages ----------
if isempty(pngSOL)
    warning('Pipeline:NoSolidPNGs', 'No SOLID PNGs found; SOLID montage not created.');
else
    try
        makeMontageHiRes(pngSOL, masterPngSOLID);
        fprintf('Master SOLID montage saved: %s\n', masterPngSOLID);
    catch ME
        warning(ME.identifier, 'Failed to build SOLID montage: %s', ME.message);
    end
end

if isempty(pngSPU)
    warning('Pipeline:NoSputterPNGs', 'No SPUTTER PNGs found; SPUTTER montage not created.');
else
    try
        makeMontageHiRes(pngSPU, masterPngSPUTTER);
        fprintf('Master SPUTTER montage saved: %s\n', masterPngSPUTTER);
    catch ME
        warning(ME.identifier, 'Failed to build SPUTTER montage: %s', ME.message);
    end
end

% ---------- Merge available stats into a single CSV ----------
T = table();
T = tryAddCSV(T, evtStacksRes,  'EventStacks');
T = tryAddCSV(T, voltRasterRes, 'VoltageRaster');
T = tryAddCSV(T, csdRasterRes,  'CSDRaster');
T = tryAddCSV(T, csdSlicesRes,  'CSDCenterSlices');

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

% ----------------- helpers -----------------

function T = tryAddCSV(T, res, tag)
try
    if isstruct(res) && isfield(res,'statsCSV') && isfile(res.statsCSV)
        C = readtable(res.statsCSV);
        if ~ismember('source', C.Properties.VariableNames)
            C.source = repmat(string(tag), height(C), 1);
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
allVars = union(A.Properties.VariableNames, B.Properties.VariableNames);
A = addMissingVars(A, allVars);
B = addMissingVars(B, allVars);
T = [A; B]; %#ok<AGROW>
end

function T = addMissingVars(T, allVars)
missing = setdiff(allVars, T.Properties.VariableNames);
for k = 1:numel(missing)
    T.(missing{k}) = missingDefault();
end
T = T(:, allVars);
end

function x = missingDefault()
x = missing;
end

function makeMontageHiRes(pngList, outPath)
% Stack images vertically at NATIVE resolution (no resampling).
% Pads narrower images to the max width with white. Adds 6 px white spacer.

assert(~isempty(pngList), 'pngList is empty.');

imgs = cell(numel(pngList),1);
widths  = zeros(numel(pngList),1);
heights = zeros(numel(pngList),1);

for i = 1:numel(pngList)
    imgs{i} = imread(pngList{i});
    [h,w,~] = size(imgs{i});
    widths(i)  = w;
    heights(i) = h;
end

Wmax = max(widths);
sep  = 6; % white separator in pixels

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

y = 1;
for i = 1:numel(imgs)
    I = imgs{i};
    [h,w,c] = size(I);
    out(y:y+h-1, 1:w, 1:c) = I;
    y = y + h;
    if i < numel(imgs), y = y + sep; end
end

imwrite(out, outPath);
end
