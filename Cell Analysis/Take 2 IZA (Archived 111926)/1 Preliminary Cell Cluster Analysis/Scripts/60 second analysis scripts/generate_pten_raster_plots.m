% Generate a spike-time raster plot for every M#_s# session in the PTEN
% kilosort dataset. One row per cell cluster, x-axis fixed to 0-60 s,
% spike sample indices converted to seconds by dividing by the 30 kHz
% sampling rate. Figures are saved as PNGs named "<M#_s#>_raster.png".

dataRoot  = 'D:\Data\Archive\PTEN Project\PTEN';
outputDir = 'D:\Data\Archive\Take 2 IZA\Output';
fs        = 30000;
xWindow   = [0 60];

if ~exist(outputDir, 'dir')
    mkdir(outputDir);
end

sessions = find_pten_sessions(dataRoot);
fprintf('Found %d sessions.\n', numel(sessions));

for i = 1:numel(sessions)
    sess = sessions(i);
    fprintf('[%d/%d] %s\n', i, numel(sessions), sess.name);
    try
        plot_session_raster(sess.timestampsDir, sess.name, fs, xWindow, outputDir);
    catch ME
        warning('Failed on %s: %s', sess.name, ME.message);
    end
end

fprintf('Done. Figures saved to %s\n', outputDir);
