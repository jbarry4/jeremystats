function epochTable = collect_ied_epoch_rates(dataRoot, iedDir, sfx, preWinS, postWinS)
% collect_ied_epoch_rates  Instantaneous (1/ISI-based) firing rate for every
% kilosort cluster in the pre/during/post epochs of every "Collected Solid
% IED" event, across every session that has an IED spreadsheet.
%
% Instantaneous rate: for a cluster's full spike train (not clipped to the
% epoch), instRate(i) = 1 / (spikeTime(i+1) - spikeTime(i)), assigned at
% spikeTime(i). An epoch's rate is the mean of instRate(i) over every spike
% i whose spikeTime falls in that epoch (NaN if none qualify -- e.g. very
% short "during" epochs for sparsely-firing clusters).
%
% Inputs:
%   dataRoot   PTEN Project\PTEN root (session folders M#_s#)
%   iedDir     Collected Solid IED folder (per-session *_solid_ied.xlsx)
%   sfx        sample rate (Hz), e.g. 30000
%   preWinS    seconds before IED onset for the "pre" epoch
%   postWinS   seconds after IED offset for the "post" epoch
%
% Output:
%   epochTable  one row per Session x ClusterID x EventNumber:
%     Session, ClusterID, EventNumber, OnsetSec, OffsetSec, DuringDurationSec,
%     PreSpikeCount, DuringSpikeCount, PostSpikeCount,
%     PreInstRateHz, DuringInstRateHz, PostInstRateHz, BaselineRateHz
%
% BaselineRateHz is each cluster's whole-recording mean firing rate
% (SpikeCount / SessionDurationSec), reused verbatim from collect_cluster_stats.m
% ("1 Preliminary Cell Cluster Analysis\Scripts\Cluster count and firing rate
% scripts") so it matches the rest of the archive exactly.

xlsxFiles = dir(fullfile(iedDir, '*.xlsx'));
xlsxFiles = xlsxFiles(~startsWith({xlsxFiles.name}, '~$'));

baselineTable = collect_cluster_stats(dataRoot, sfx);

Session = {}; ClusterID = []; EventNumber = [];
OnsetSec = []; OffsetSec = []; DuringDurationSec = [];
PreSpikeCount = []; DuringSpikeCount = []; PostSpikeCount = [];
PreInstRateHz = []; DuringInstRateHz = []; PostInstRateHz = [];
BaselineRateHz = [];

for i = 1:numel(xlsxFiles)
    [~, base, ~] = fileparts(xlsxFiles(i).name);
    try
        sessionName = session_name_from_ied_filename(base);
    catch ME
        warning('%s -- skipping.', ME.message);
        continue;
    end

    try
        dataDir = find_session_data_dir(dataRoot, sessionName);
    catch ME
        warning('%s -- skipping session.', ME.message);
        continue;
    end

    T = readtable(fullfile(xlsxFiles(i).folder, xlsxFiles(i).name));

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
    nClusters = numel(clusterIds);

    spikeSec = cell(nClusters, 1);
    instTime = cell(nClusters, 1);   % == spikeSec{c}(1:end-1)
    instRate = cell(nClusters, 1);   % instRate{c}(k) assigned at instTime{c}(k)
    clusterBaseline = nan(nClusters, 1);

    for c = 1:nClusters
        s = load(fullfile(matFiles(c).folder, matFiles(c).name));
        fn = fieldnames(s);
        spikeSamples = double(s.(fn{1}));
        spk = sort(spikeSamples(:)) / sfx;
        spikeSec{c} = spk;
        if numel(spk) >= 2
            isi = diff(spk);
            instTime{c} = spk(1:end-1);
            instRate{c} = 1 ./ isi;
        else
            instTime{c} = [];
            instRate{c} = [];
        end

        rowMatch = strcmp(baselineTable.Session, sessionName) & baselineTable.ClusterID == clusterIds(c);
        if any(rowMatch)
            clusterBaseline(c) = baselineTable.FiringRateHz(find(rowMatch, 1));
        end
    end

    fprintf('[INFO] %s: %d clusters, %d IED events.\n', sessionName, nClusters, height(T));

    for j = 1:height(T)
        eventNumber = T.EventNumber(j);
        onS  = (double(T.onsamp(j)) - 1) / sfx;
        offS = (double(T.offsamp(j)) - 1) / sfx;

        preT0  = onS - preWinS;  preT1  = onS;
        durT0  = onS;            durT1  = offS;
        postT0 = offS;           postT1 = offS + postWinS;

        for c = 1:nClusters
            [preRate, ~]  = epoch_inst_rate(instTime{c}, instRate{c}, preT0, preT1);
            [durRate, ~]  = epoch_inst_rate(instTime{c}, instRate{c}, durT0, durT1);
            [postRate, ~] = epoch_inst_rate(instTime{c}, instRate{c}, postT0, postT1);

            Session{end+1, 1}           = sessionName; %#ok<AGROW>
            ClusterID(end+1, 1)         = clusterIds(c); %#ok<AGROW>
            EventNumber(end+1, 1)       = eventNumber; %#ok<AGROW>
            OnsetSec(end+1, 1)          = onS; %#ok<AGROW>
            OffsetSec(end+1, 1)         = offS; %#ok<AGROW>
            DuringDurationSec(end+1, 1) = offS - onS; %#ok<AGROW>
            PreSpikeCount(end+1, 1)     = raw_spike_count(spikeSec{c}, preT0, preT1); %#ok<AGROW>
            DuringSpikeCount(end+1, 1)  = raw_spike_count(spikeSec{c}, durT0, durT1); %#ok<AGROW>
            PostSpikeCount(end+1, 1)    = raw_spike_count(spikeSec{c}, postT0, postT1); %#ok<AGROW>
            PreInstRateHz(end+1, 1)     = preRate; %#ok<AGROW>
            DuringInstRateHz(end+1, 1)  = durRate; %#ok<AGROW>
            PostInstRateHz(end+1, 1)    = postRate; %#ok<AGROW>
            BaselineRateHz(end+1, 1)    = clusterBaseline(c); %#ok<AGROW>
        end
    end
end

epochTable = table(Session, ClusterID, EventNumber, OnsetSec, OffsetSec, DuringDurationSec, ...
    PreSpikeCount, DuringSpikeCount, PostSpikeCount, ...
    PreInstRateHz, DuringInstRateHz, PostInstRateHz, BaselineRateHz);
end

function [rate, nSamples] = epoch_inst_rate(instTime, instRate, t0, t1)
if isempty(instTime)
    rate = NaN; nSamples = 0; return;
end
inWin = instTime >= t0 & instTime < t1;
nSamples = sum(inWin);
if nSamples == 0
    rate = NaN;
else
    rate = mean(instRate(inWin));
end
end

function n = raw_spike_count(spk, t0, t1)
n = sum(spk >= t0 & spk < t1);
end
