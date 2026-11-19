function [clusterTable, sessionCounts] = collect_cluster_stats(dataRoot, fs)
% Walk every M#_s# session and compute, for each cluster, its spike
% count and firing rate (Hz). A session's duration is taken as the
% latest spike time across all of its clusters (the same proxy for
% recording length used for the full-length raster plots), since the
% true recording length isn't otherwise available from the timestamp
% files alone.

sessions = find_pten_sessions(dataRoot);

sessionNameCol = {};
numClustersCol = [];

allSession   = {};
allClusterId = [];
allSpikeCount = [];
allDuration   = [];
allFiringRate = [];

for i = 1:numel(sessions)
    sess = sessions(i);
    matFiles = dir(fullfile(sess.timestampsDir, '*.mat'));
    nClusters = numel(matFiles);

    sessionNameCol{end+1} = sess.name; %#ok<AGROW>
    numClustersCol(end+1) = nClusters; %#ok<AGROW>

    clusterIds = zeros(nClusters, 1);
    spikeCounts = zeros(nClusters, 1);
    sessionDuration = 0;

    for k = 1:nClusters
        [~, base, ~] = fileparts(matFiles(k).name);
        clusterIds(k) = str2double(base);

        s = load(fullfile(matFiles(k).folder, matFiles(k).name));
        fn = fieldnames(s);
        spikeSamples = double(s.(fn{1}));
        spikeSeconds = spikeSamples(:) / fs;

        spikeCounts(k) = numel(spikeSeconds);
        if ~isempty(spikeSeconds)
            sessionDuration = max(sessionDuration, max(spikeSeconds));
        end
    end

    for k = 1:nClusters
        allSession{end+1}   = sess.name; %#ok<AGROW>
        allClusterId(end+1) = clusterIds(k); %#ok<AGROW>
        allSpikeCount(end+1) = spikeCounts(k); %#ok<AGROW>
        allDuration(end+1)   = sessionDuration; %#ok<AGROW>
        allFiringRate(end+1) = spikeCounts(k) / sessionDuration; %#ok<AGROW>
    end
end

clusterTable = table(allSession', allClusterId', allSpikeCount', allDuration', allFiringRate', ...
    'VariableNames', {'Session', 'ClusterID', 'SpikeCount', 'SessionDurationSec', 'FiringRateHz'});

sessionCounts = table(sessionNameCol', numClustersCol', ...
    'VariableNames', {'Session', 'NumClusters'});
end
