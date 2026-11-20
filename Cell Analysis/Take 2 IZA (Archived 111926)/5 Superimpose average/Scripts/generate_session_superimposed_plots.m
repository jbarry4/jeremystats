%% generate_session_superimposed_plots.m
%
% For every "Collected Solid IED" session, render ONE summary figure that
% superimposes every IED event on top of each other (aligned to each
% event's own onset), laid out the same way as "4 Adding all waveforms"
% (waveform montage on top, cluster raster on the bottom of the same
% figure) but pooling every event into that single session-level figure
% instead of one figure per event:
%
%   top    - all CSC channels stacked. Every event's trace for a channel
%            is drawn faint gray, except when that channel was the driver
%            (largest |deflection| during onset->offset) for that
%            specific event -- then it's drawn faint red, same convention
%            as the per-event plots. The across-event average trace for
%            each channel is drawn on top in solid bold black.
%   bottom - one row per cell cluster that fired at least once inside any
%            event's window. Every event's spike ticks (relative to that
%            event's own onset) are superimposed on the same row as very
%            faint marks; ticks from different events that land at
%            similar latencies overlap and accumulate to a bolder/darker
%            mark.
%
% Run this script directly in MATLAB (no .sbat / cluster submission
% needed -- everything lives on the local D: drive).
%
% Inputs (same as "4 Adding all waveforms"):
%   IED events      D:\Data\Archive\Take 2 IZA\Collected Solid IED\<m#s#>_solid_ied.xlsx
%   Cluster spikes  D:\Data\Archive\PTEN Project\PTEN\M#_s#\<date>\timestamps\<clusterId>.mat
%   Raw CSC         D:\Data\Archive\PTEN Project\PTEN\M#_s#\<date>\CSC*.ncs
%
% Output:
%   D:\Data\Archive\Take 2 IZA\5 Superimpose average\Output\<M#_s#>\<M#_s#>_Superimposed.png

%% ---- Parameters ----
dataRoot = 'D:\Data\Archive\PTEN Project\PTEN';
iedDir   = 'D:\Data\Archive\Take 2 IZA\Collected Solid IED';
reqsDir  = 'D:\Data\Archive\Take 2 IZA\reqsPath';

preWinS  = 1;       % seconds shown before IED onset
postWinS = 1;       % seconds shown after IED offset
loadMaxCh = 64;     % ignore CSC numbers above this
fiftyNineBad = false;   % set true to drop CSC59 (matches original pipeline option)
invertPolarity = true;  % matches the polarity flip applied in the IED detector

% ROYGBIV, cycled if more clusters are active than colours
colors = [ ...
    1.00 0.00 0.00;   % Red
    1.00 0.55 0.00;   % Orange
    0.85 0.85 0.00;   % Yellow
    0.00 0.60 0.00;   % Green
    0.00 0.30 1.00;   % Blue
    0.29 0.00 0.51;   % Indigo
    0.58 0.00 0.83];  % Violet

scriptDir = fileparts(mfilename('fullpath'));
outRoot   = fullfile(fileparts(scriptDir), 'Output');
addpath(scriptDir);
addpath(reqsDir);

if ~exist(outRoot, 'dir'), mkdir(outRoot); end

%% ---- Iterate over every "Collected Solid IED" spreadsheet ----
xlsxFiles = dir(fullfile(iedDir, '*.xlsx'));
xlsxFiles = xlsxFiles(~startsWith({xlsxFiles.name}, '~$'));   % skip Excel lock files
fprintf('[INFO] %d IED spreadsheet(s) found.\n', numel(xlsxFiles));

for i = 1:numel(xlsxFiles)
    [~, base, ~] = fileparts(xlsxFiles(i).name);
    try
        sessionName = session_name_from_ied_filename(base);
    catch ME
        warning('%s -- skipping.', ME.message);
        continue;
    end

    fprintf('\n[SESSION] %s  (%s)\n', sessionName, xlsxFiles(i).name);
    try
        dataDir = find_session_data_dir(dataRoot, sessionName);
    catch ME
        warning('%s -- skipping session.', ME.message);
        continue;
    end
    fprintf('[INFO] Data dir: %s\n', dataDir);

    T = readtable(fullfile(xlsxFiles(i).folder, xlsxFiles(i).name));
    fprintf('[INFO] %d IED events.\n', height(T));
    if height(T) == 0
        warning('No IED events -- skipping session.');
        continue;
    end

    %% ---- Locate and filter CSC files ----
    files = dir(fullfile(dataDir, 'CSC*.n*'));
    nums = nan(1, numel(files));
    for k = 1:numel(files)
        tok = regexp(files(k).name, 'CSC(\d+)', 'tokens', 'once');
        if ~isempty(tok), nums(k) = str2double(tok{1}); end
    end
    keep = ~isnan(nums) & (nums <= loadMaxCh);
    if fiftyNineBad, keep = keep & (nums ~= 59); end
    [~, ia] = unique(nums(keep));
    tmpIdx = find(keep);
    keep(:) = false;
    keep(tmpIdx(ia)) = true;

    files = files(keep); nums = nums(keep);
    [nums, ord] = sort(nums); files = files(ord);
    nCh = numel(files);
    if nCh == 0
        warning('No CSC files in %s -- skipping session.', dataDir);
        continue;
    end
    fprintf('[INFO] %d channels.\n', nCh);

    %% ---- ADBitVolts from header ----
    hdr = Nlx2MatCSC(fullfile(files(1).folder, files(1).name), [0 0 0 0 0], 1, 1, []);
    ADBitVolts = parseNcsField(hdr, 'ADBitVolts');
    if isnan(ADBitVolts)
        warning('ADBitVolts not found for %s -- skipping session.', sessionName);
        continue;
    end

    %% ---- sfx / global_min_T_us (mirrors 1_1_ied_detect.m Pass 1) ----
    all_Fs = nan(1, nCh);
    all_first_T_us = nan(1, nCh);
    for ch = 1:nCh
        fn = fullfile(files(ch).folder, files(ch).name);
        [ts_us, Fs_vec] = Nlx2MatCSC(fn, [1 0 1 0 0], 0, 1, []);
        Fs = mode(double(Fs_vec(Fs_vec > 0)));
        if ~(isfinite(Fs) && Fs > 0), Fs = 30000; end
        all_Fs(ch) = Fs;
        if ~isempty(ts_us), all_first_T_us(ch) = ts_us(1); end
    end
    good = isfinite(all_Fs);
    sfx = mode(round(all_Fs(good)));
    global_min_T_us = min(all_first_T_us(good));
    fprintf('[INFO] sfx=%g Hz  global_min_T_us=%.0f us\n', sfx, global_min_T_us);

    %% ---- Cluster spike times (kilosort timestamps folder) ----
    tsDir = fullfile(dataDir, 'timestamps');
    matFiles = dir(fullfile(tsDir, '*.mat'));
    if isempty(matFiles)
        warning('No cluster timestamp files in %s -- skipping session.', tsDir);
        continue;
    end
    clusterIds = zeros(numel(matFiles), 1);
    for k = 1:numel(matFiles)
        [~, cbase, ~] = fileparts(matFiles(k).name);
        clusterIds(k) = str2double(cbase);
    end
    [clusterIds, sortIdx] = sort(clusterIds);
    matFiles = matFiles(sortIdx);

    clusterSpikeSec = cell(numel(matFiles), 1);
    for k = 1:numel(matFiles)
        s = load(fullfile(matFiles(k).folder, matFiles(k).name));
        fn2 = fieldnames(s);
        spikeSamples = double(s.(fn2{1}));
        clusterSpikeSec{k} = (spikeSamples(:) - 1) / sfx;
    end
    fprintf('[INFO] %d clusters.\n', numel(clusterIds));

    %% ---- Render the session-level superimposed figure ----
    sessionOutDir = fullfile(outRoot, sessionName);
    if ~exist(sessionOutDir, 'dir'), mkdir(sessionOutDir); end

    try
        plot_session_superimposed(sessionName, T, files, nums, ...
            ADBitVolts, sfx, global_min_T_us, invertPolarity, ...
            clusterIds, clusterSpikeSec, preWinS, postWinS, colors, sessionOutDir);
        fprintf('[OK] Superimposed figure.\n');
    catch ME
        warning('Superimposed figure failed: %s', ME.message);
    end
end

fprintf('\n[DONE] Output saved under: %s\n', outRoot);
