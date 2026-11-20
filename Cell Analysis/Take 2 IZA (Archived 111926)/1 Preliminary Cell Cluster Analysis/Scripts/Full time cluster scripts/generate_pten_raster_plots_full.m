% Generate a spike-time raster plot for every M#_s# session in the PTEN
% kilosort dataset, covering each recording's full length. Spike sample
% indices are converted to seconds by dividing by the 30 kHz sampling
% rate. The x-axis is normalized to the same upper bound across all
% sessions: the longest recording time found in the whole dataset.
% Figures are saved as PNGs named "<M#_s#>_raster_full.png".

dataRoot  = 'D:\Data\Archive\PTEN Project\PTEN';
outputDir = 'D:\Data\Archive\Take 2 IZA\Output\Full time cluster analysis';
fs        = 30000;

if ~exist(outputDir, 'dir')
    mkdir(outputDir);
end

sessions = find_pten_sessions(dataRoot);
fprintf('Found %d sessions.\n', numel(sessions));

fprintf('Scanning sessions for longest recording time...\n');
maxTime = 0;
for i = 1:numel(sessions)
    t = session_max_time(sessions(i).timestampsDir, fs);
    fprintf('  %s: %.2f s\n', sessions(i).name, t);
    maxTime = max(maxTime, t);
end
xWindow = [0, maxTime];
fprintf('Longest recording: %.2f s. Using this as the shared x-axis limit.\n', maxTime);

for i = 1:numel(sessions)
    sess = sessions(i);
    fprintf('[%d/%d] %s\n', i, numel(sessions), sess.name);
    try
        plot_session_raster_full(sess.timestampsDir, sess.name, fs, xWindow, outputDir);
    catch ME
        warning('Failed on %s: %s', sess.name, ME.message);
    end
end

fprintf('Done. Figures saved to %s\n', outputDir);
