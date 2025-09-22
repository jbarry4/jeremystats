function Pipeline_Main(inputFolder, dataMatPath, varargin)
% Pipeline_Main
% Orchestrates the analysis and figure creation across multiple sub-pipelines.
%
% Creates TWO master plots at full/native PNG resolution:
%   Pipeline Output/Master_Montage_SOLID.png
%   Pipeline Output/Master_Montage_SPUTTER.png
%
% (For now only EventStacks_ampWidth_Avg_Pipeline is active; others are placeholders.)

opts = struct(varargin{:});

% ---------- Output hub for the master ----------
masterOutDir = fullfile(inputFolder, 'Pipeline Output');
if ~exist(masterOutDir, 'dir'), mkdir(masterOutDir); end
masterPngSOLID   = fullfile(masterOutDir, 'Master_Montage_SOLID.png');
masterPngSPUTTER = fullfile(masterOutDir, 'Master_Montage_SPUTTER.png');
masterCSV        = fullfile(masterOutDir, 'Master_Stats.csv');

% ---------- 1) EventStacks_ampWidth_Avg_Pipeline (ACTIVE) ----------
evtStacksRes = [];
try
    evtStacksRes = EventStacks_ampWidth_Avg_Pipeline(inputFolder, dataMatPath, varargin{:});
catch ME
    warning('EventStacks_ampWidth_Avg_Pipeline failed: %s', ME.message);
end

% ---------- 2) VoltageRaster_EventsAvg_Pipeline ----------
% try
%     voltRasterRes = VoltageRaster_EventsAvg_Pipeline(inputFolder, dataMatPath, varargin{:});
% catch ME
%     warning('VoltageRaster_EventsAvg_Pipeline failed: %s', ME.message);
% end

% ---------- 3) CSDRaster_Avg_Pipeline ----------
% try
%     csdRasterRes = CSDRaster_Avg_Pipeline(inputFolder, dataMatPath, varargin{:});
% catch ME
%     warning('CSDRaster_Avg_Pipeline failed: %s', ME.message);
% end

% ---------- 4) CSD_CenterSlices_Waveform_AvgGroups_Pipeline ----------
% try
%     csdSlicesRes = CSD_CenterSlices_Waveform_AvgGroups_Pipeline(inputFolder, dataMatPath, varargin{:});
% catch ME
%     warning('CSD_CenterSlices_Waveform_AvgGroups_Pipeline failed: %s', ME.message);
% end

% ---------- 5) CSD_TimeAvg_Waveform_AvgGroups_Pipeline ----------
% try
%     csdTimeAvgRes = CSD_TimeAvg_Waveform_AvgGroups_Pipeline(inputFolder, dataMatPath, varargin{:});
% catch ME
%     warning('CSD_TimeAvg_Waveform_AvgGroups_Pipeline failed: %s', ME.message);
% end

% ---------- Gather whatever PNGs exist (keep paths; maintain native res) ----------
pngSOL = {};
pngSPU = {};

% EventStacks outputs
if ~isempty(evtStacksRes)
    if isfield(evtStacksRes, 'pngSolid') && isfile(evtStacksRes.pngSolid)
        pngSOL{end+1} = evtStacksRes.pngSolid;
    end
    if isfield(evtStacksRes, 'pngSputter') && isfile(evtStacksRes.pngSputter)
        pngSPU{end+1} = evtStacksRes.pngSputter;
    end
end

% % Voltage raster (placeholder)
% if exist('voltRasterRes','var') && ~isempty(voltRasterRes)
%     if isfield(voltRasterRes, 'pngSolid') && isfile(voltRasterRes.pngSolid),   pngSOL{end+1} = voltRasterRes.pngSolid;   end
%     if isfield(voltRasterRes, 'pngSputter') && isfile(voltRasterRes.pngSputter), pngSPU{end+1} = voltRasterRes.pngSputter; end
% end

% % CSD raster (placeholder)
% if exist('csdRasterRes','var') && ~isempty(csdRasterRes)
%     if isfield(csdRasterRes, 'pngSolid') && isfile(csdRasterRes.pngSolid),   pngSOL{end+1} = csdRasterRes.pngSolid;   end
%     if isfield(csdRasterRes, 'pngSputter') && isfile(csdRasterRes.pngSputter), pngSPU{end+1} = csdRasterRes.pngSputter; end
% end

% % CSD center slices (placeholder)
% if exist('csdSlicesRes','var') && ~isempty(csdSlicesRes)
%     if isfield(csdSlicesRes, 'pngSolid') && isfile(csdSlicesRes.pngSolid),   pngSOL{end+1} = csdSlicesRes.pngSolid;   end
%     if isfield(csdSlicesRes, 'pngSputter') && isfile(csdSlicesRes.pngSputter), pngSPU{end+1} = csdSlicesRes.pngSputter; end
% end

% % CSD time-avg (placeholder)
% if exist('csdTimeAvgRes','var') && ~isempty(csdTimeAvgRes)
%     if isfield(csdTimeAvgRes, 'pngSolid') && isfile(csdTimeAvgRes.pngSolid),   pngSOL{end+1} = csdTimeAvgRes.pngSolid;   end
%     if isfield(csdTimeAvgRes, 'pngSputter') && isfile(csdTimeAvgRes.pngSputter), pngSPU{end+1} = csdTimeAvgRes.pngSputter; end
% end

% ---------- Build TWO hi-res montages (no resampling) ----------
if isempty(pngSOL)
    warning('No SOLID PNGs found; SOLID montage not created.');
else
    try
        makeMontageHiRes(pngSOL, masterPngSOLID);
        fprintf('Master SOLID montage saved: %s\n', masterPngSOLID);
    catch ME
        warning('Failed to build SOLID montage: %s', ME.message);
    end
end

if isempty(pngSPU)
    warning('No SPUTTER PNGs found; SPUTTER montage not created.');
else
    try
        makeMontageHiRes(pngSPU, masterPngSPUTTER);
        fprintf('Master SPUTTER montage saved: %s\n', masterPngSPUTTER);
    catch ME
        warning('Failed to build SPUTTER montage: %s', ME.message);
    end
end

% ---------- Merge whatever stats exist into CSV ----------
T = table(); % start empty

if ~isempty(evtStacksRes) && isfield(evtStacksRes, 'statsCSV') && isfile(evtStacksRes.statsCSV)
    try
        T1 = readtable(evtStacksRes.statsCSV);
        T = vertcatSafe(T, T1);
    catch ME
        warning('Failed reading EventStacks stats CSV: %s', ME.message);
    end
end

% (Append more CSVs here as new pipeline steps come online...)

try
    if isempty(T)
        T = table(string(datetime('now')), "EMPTY", 'VariableNames', {'GeneratedAt','Note'});
    end
    writetable(T, masterCSV);
    fprintf('Master stats CSV: %s\n', masterCSV);
catch ME
    warning('Failed writing master stats CSV: %s', ME.message);
end

end

% ----------------- helpers -----------------

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
% Pads narrower images to the max width with white. Adds 6 px white spacer between rows.

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

% Determine output class and white value
cls = class(imgs{1});
switch cls
    case {'uint8'},  whiteVal = uint8(255);
    case {'uint16'}, whiteVal = uint16(65535);
    case {'double'}, whiteVal = 1;
    case {'single'}, whiteVal = single(1);
    otherwise, error('Unsupported image class: %s', cls);
end

% Build stacked image
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
    out(y:y+h-1, 1:w, 1:c) = I; % left-align; pad on right with white
    y = y + h;
    if i < numel(imgs)
        y = y + sep;
    end
end

imwrite(out, outPath); % no resampling, preserves pixel fidelity
end
