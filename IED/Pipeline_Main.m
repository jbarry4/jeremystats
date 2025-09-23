function Pipeline_Main(inputFolder, dataMatPath, varargin)
% Pipeline_Main — orchestrates sub-pipelines and builds TWO compact masters
% (SOLID, SPUTTER) + merged stats CSV. Lots of verbose logging.
%
% Column layout per group:
%   LEFT  : VoltageRaster_EventsAvg + CSD_CenterSlices_Waveform_AvgGroups
%   MIDDLE: EventStacks_ampWidth_Avg (tall)
%   RIGHT : CSDRaster_Avg + CSD_TimeAvgSlices_Waveforms_AvgGroups
%
% All images are composed at native resolution. No resampling.

fprintf('\n=== Pipeline_Main starting ===\n');

% ---------- Output hub ----------
masterOutDir = fullfile(inputFolder, 'Pipeline Output');
if ~exist(masterOutDir, 'dir'), mkdir(masterOutDir); end
masterPngSOLID   = fullfile(masterOutDir, 'Master_Compact_SOLID.png');
masterPngSPUTTER = fullfile(masterOutDir, 'Master_Compact_SPUTTER.png');
masterCSV        = fullfile(masterOutDir, 'Master_Stats.csv');

% ---------- 0) (optional) spike detection placeholder ----------
% try
%     SpikeDetect_Pipeline(inputFolder, dataMatPath, varargin{:});
% catch ME
%     warning(ME.identifier, 'SpikeDetect_Pipeline failed: %s', ME.message);
% end

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

% ---------- 4) CSD Center Slices + Vertical Waveforms ----------
csdSlicesRes = [];
try
    csdSlicesRes = CSD_CenterSlices_Waveform_AvgGroups_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'CSD_CenterSlices_Waveform_AvgGroups_Pipeline failed: %s', ME.message);
end

% ---------- 5) CSD Time-Avg Slices + Vertical Waveforms ----------
csdTimeAvgRes = [];
try
    csdTimeAvgRes = CSD_TimeAvgSlices_Waveforms_AvgGroups_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning(ME.identifier, 'CSD_TimeAvgSlices_Waveforms_AvgGroups_Pipeline failed: %s', ME.message);
end

% ---------- Collect PNGs by role (per group) ----------
SOL_left  = filterExisting({getFieldSafe(voltRasterRes,'pngSolid'),   getFieldSafe(csdSlicesRes,'pngSolid')});
SOL_mid   = filterExisting({getFieldSafe(evtStacksRes,'pngSolid')});
SOL_right = filterExisting({getFieldSafe(csdRasterRes,'pngSolid'),    getFieldSafe(csdTimeAvgRes,'pngSolid')});

SPU_left  = filterExisting({getFieldSafe(voltRasterRes,'pngSputter'), getFieldSafe(csdSlicesRes,'pngSputter')});
SPU_mid   = filterExisting({getFieldSafe(evtStacksRes,'pngSputter')});
SPU_right = filterExisting({getFieldSafe(csdRasterRes,'pngSputter'),  getFieldSafe(csdTimeAvgRes,'pngSputter')});

% Verbose logging of what we found
logColumn('SOLID / LEFT',  SOL_left);
logColumn('SOLID / MID',   SOL_mid);
logColumn('SOLID / RIGHT', SOL_right);
logColumn('SPUTTER / LEFT',  SPU_left);
logColumn('SPUTTER / MID',   SPU_mid);
logColumn('SPUTTER / RIGHT', SPU_right);

% ---------- Build compact masters (3 columns) ----------
builtSOL = false; builtSPU = false;
try
    if ~isempty(SOL_left) || ~isempty(SOL_mid) || ~isempty(SOL_right)
        makeThreeColPanelHiRes(SOL_left, SOL_mid, SOL_right, masterPngSOLID);
        fprintf('[OK] Master SOLID compact saved: %s\n', masterPngSOLID);
        builtSOL = true;
    else
        warning('Pipeline:NoSolidPNGs', 'No SOLID PNGs found; SOLID master not created.');
    end
catch ME
    warning(ME.identifier, 'Failed to build SOLID compact: %s', ME.message);
end

try
    if ~isempty(SPU_left) || ~isempty(SPU_mid) || ~isempty(SPU_right)
        makeThreeColPanelHiRes(SPU_left, SPU_mid, SPU_right, masterPngSPUTTER);
        fprintf('[OK] Master SPUTTER compact saved: %s\n', masterPngSPUTTER);
        builtSPU = true;
    else
        warning('Pipeline:NoSputterPNGs', 'No SPUTTER PNGs found; SPUTTER master not created.');
    end
catch ME
    warning(ME.identifier, 'Failed to build SPUTTER compact: %s', ME.message);
end

% ---------- Merge available stats into a single CSV ----------
T = table();
T = tryAddCSV(T, evtStacksRes,  'EventStacks');
T = tryAddCSV(T, voltRasterRes, 'VoltageRaster');
T = tryAddCSV(T, csdRasterRes,  'CSDRaster');
T = tryAddCSV(T, csdSlicesRes,  'CSDCenterSlices');
T = tryAddCSV(T, csdTimeAvgRes, 'CSDTimeAvg');

try
    if isempty(T)
        T = table(string(datetime('now')), "EMPTY", 'VariableNames', {'GeneratedAt','Note'});
    end
    writetable(T, masterCSV);
    fprintf('[OK] Master stats CSV: %s\n', masterCSV);
catch ME
    warning(ME.identifier, 'Failed writing master stats CSV: %s', ME.message);
end

if ~builtSOL || ~builtSPU
    fprintf('NOTE: You can still find individual PNGs in their output folders.\n');
end

fprintf('=== Pipeline_Main done ===\n\n');
end

% ================= helpers =================

function logColumn(label, files)
fprintf('> Using %s (%d):\n', label, numel(files));
if isempty(files)
    fprintf('   (none)\n');
else
    for i = 1:numel(files)
        try
            info = imfinfo(files{i});
            fprintf('   %02d: %s  [%dx%d]\n', i, files{i}, info.Width, info.Height);
        catch
            fprintf('   %02d: %s  [could not read size]\n', i, files{i});
        end
    end
end
end

function cellOut = filterExisting(cellIn)
cellOut = {};
for i = 1:numel(cellIn)
    p = string(cellIn{i});
    if strlength(p) > 0 && isfile(p)
        cellOut{end+1} = char(p); %#ok<AGROW>
    end
end
end

function v = getFieldSafe(S, fieldName)
if ~(isstruct(S) && isfield(S, fieldName))
    v = "";
else
    v = string(S.(fieldName));
end
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

% ---------- image composition (native res, borders, gutters) ----------

function makeThreeColPanelHiRes(leftPngs, midPngs, rightPngs, outPath)
% Build three columns at native resolution.
% Each column stacks its images vertically (with borders) → pad columns to equal
% height → concat side-by-side. No resampling.

fprintf('Composing 3-column panel → %s\n', outPath);

% Spacing / styles
colSep    = 12;   % px between columns
tileSep   = 8;    % px between tiles inside a column
borderPx  = 2;    % tile border width (px)
borderRGB = [0 0 0]; % black borders
padRGB    = 255;  % white padding

% Build raw columns (possibly empty)
colL = makeColumn(leftPngs, tileSep, borderPx, borderRGB, padRGB);
colM = makeColumn(midPngs,  tileSep, borderPx, borderRGB, padRGB);
colR = makeColumn(rightPngs,tileSep, borderPx, borderRGB, padRGB);

% If a column is empty, substitute a 1×1 spacer *now*
[cls, ch] = pickClassAndCh({colL,colM,colR});
if isempty(colL), colL = makeSpacer(1,1,cls,ch,padRGB); end
if isempty(colM), colM = makeSpacer(1,1,cls,ch,padRGB); end
if isempty(colR), colR = makeSpacer(1,1,cls,ch,padRGB); end

% Harmonize class/ch across all columns
colL = castToSimple(colL, cls, ch, padRGB);
colM = castToSimple(colM, cls, ch, padRGB);
colR = castToSimple(colR, cls, ch, padRGB);

% Target height from actual (post-substitution) columns
H = max([size(colL,1), size(colM,1), size(colR,1)]);

% Pad each column to exactly H
colL = padToHeight(colL, H, cls, ch, padRGB);
colM = padToHeight(colM, H, cls, ch, padRGB);
colR = padToHeight(colR, H, cls, ch, padRGB);

% Final widths
Wl = size(colL,2); Wm = size(colM,2); Wr = size(colR,2);

% Final canvas
W = Wl + Wm + Wr + colSep*2;
out = makeSpacer(H, W, cls, ch, padRGB);

% Blit columns using their actual widths
x = 1;
out(:, x:(x+Wl-1), :) = colL; x = x + Wl + colSep;
out(:, x:(x+Wm-1), :) = colM; x = x + Wm + colSep;
out(:, x:(x+Wr-1), :) = colR;

imwrite(out, outPath);
end

function C = makeColumn(pngList, sep, borderPx, borderRGB, padRGB)
% Stack images vertically with borders at native resolution. Returns [] if no images.
C = [];
if isempty(pngList), return; end

imgs = cell(0,1);
w = []; h = [];

for i = 1:numel(pngList)
    p = pngList{i};
    if ~isfile(p)
        fprintf('  [skip] not found: %s\n', p);
        continue;
    end
    I = imread(p);
    I = addBorder(I, borderPx, borderRGB);
    imgs{end+1} = I; %#ok<AGROW>
    [hi,wi,~] = size(I);
    h(end+1) = hi; %#ok<AGROW>
    w(end+1) = wi; %#ok<AGROW>
end

if isempty(imgs), return; end

W = max(w);
H = sum(h) + sep*(numel(imgs)-1);

cls = class(imgs{1});
ch  = size(imgs{1},3);
C = makeSpacer(H, W, cls, ch, padRGB);

y = 1;
for i = 1:numel(imgs)
    I = imgs{i};
    [hi,wi,ci] = size(I);
    C(y:y+hi-1, 1:wi, 1:ci) = I;
    y = y + hi;
    if i < numel(imgs), y = y + sep; end
end
end

function I2 = addBorder(I, px, rgb)
if px<=0, I2 = I; return; end
if size(I,3)==1
    v = round((0.299*rgb(1)+0.587*rgb(2)+0.114*rgb(3)));
    v = max(0,min(255,v));
    switch class(I)
        case 'uint8',  padVal = uint8(v);
        case 'uint16', padVal = uint16(round(v*(65535/255)));
        case 'double', padVal = double(v/255);
        case 'single', padVal = single(v/255);
        otherwise,     padVal = uint8(v);
    end
    I2 = padarray(I, [px px], padVal, 'both');
else
    cls = class(I);
    I2 = padarray(I, [px px], 0, 'both');
    switch cls
        case 'uint8',  col = uint8(reshape(rgb,1,1,3));
        case 'uint16', col = uint16(reshape(rgb,1,1,3)*(65535/255));
        case 'double', col = reshape(rgb/255,1,1,3);
        case 'single', col = single(reshape(rgb/255,1,1,3));
        otherwise,     col = uint8(reshape(rgb,1,1,3));
    end
    I2(1:px,:,:)            = col;
    I2(end-px+1:end,:,:)    = col;
    I2(:,1:px,:)            = col;
    I2(:,end-px+1:end,:,:)  = col;
end
end

function S = makeSpacer(H, W, cls, ch, padRGB)
switch cls
    case 'uint8',  base = uint8(padRGB);
    case 'uint16', base = uint16(round(padRGB*(65535/255)));
    case 'double', base = double(padRGB/255);
    case 'single', base = single(padRGB/255);
    otherwise,     base = uint8(padRGB);
end
if ch==1
    S = repmat(base, [H W 1]);
else
    S = repmat(reshape(base,1,1,[]), [H W ch]);
end
end

function [cls, ch] = pickClassAndCh(cols)
cls = 'uint8'; ch = 3;
for i = 1:numel(cols)
    if ~isempty(cols{i})
        cls = class(cols{i});
        if ndims(cols{i})==2, ch = 1; else, ch = size(cols{i},3); end
        return;
    end
end
end

function A = castToSimple(A, cls, ch, padRGB)
if isempty(A), return; end
if ~strcmp(class(A), cls)
    switch cls
        case 'uint8',  A = uint8(A);
        case 'uint16', A = uint16(A);
        case 'double', A = double(A);
        case 'single', A = single(A);
        otherwise
    end
end
if size(A,3) ~= ch
    if ch==3 && size(A,3)==1
        A = repmat(A, [1 1 3]);
    elseif ch==1 && size(A,3)==3
        if isa(A,'uint8') || isa(A,'uint16')
            A = mean(A,3,'native');
        else
            A = mean(A,3);
        end
    else
        A = makeSpacer(size(A,1), size(A,2), cls, ch, padRGB);
    end
end
end

function B = padToHeight(A, H, cls, ch, padRGB)
if isempty(A), B = A; return; end
[h,w,~] = size(A);
if h==H, B = A; return; end
pad = makeSpacer(H-h, w, cls, ch, padRGB);
B = [A; pad];
end
