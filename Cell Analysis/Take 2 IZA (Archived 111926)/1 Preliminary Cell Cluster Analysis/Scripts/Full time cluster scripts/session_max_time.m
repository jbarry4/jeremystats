function maxSeconds = session_max_time(timestampsDir, fs)
% Return the latest spike time (in seconds) across all clusters in a
% session's timestamps folder.

maxSeconds = 0;
matFiles = dir(fullfile(timestampsDir, '*.mat'));

for k = 1:numel(matFiles)
    s = load(fullfile(matFiles(k).folder, matFiles(k).name));
    fn = fieldnames(s);
    spikeSamples = double(s.(fn{1}));
    if isempty(spikeSamples)
        continue;
    end
    maxSeconds = max(maxSeconds, max(spikeSamples(:)) / fs);
end
end
