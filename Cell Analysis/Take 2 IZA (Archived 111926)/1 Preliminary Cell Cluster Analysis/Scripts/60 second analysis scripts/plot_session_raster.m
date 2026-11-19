function plot_session_raster(timestampsDir, sessionName, fs, xWindow, outputDir)
% Build and save a spike-time raster plot for one M#_s# session.
% Each cluster's <id>.mat file holds a struct with one int64 field of
% spike sample indices; dividing by fs converts samples to seconds.

matFiles = dir(fullfile(timestampsDir, '*.mat'));
if isempty(matFiles)
    warning('No .mat files found in %s', timestampsDir);
    return;
end

clusterIds = zeros(numel(matFiles), 1);
for k = 1:numel(matFiles)
    [~, base, ~] = fileparts(matFiles(k).name);
    clusterIds(k) = str2double(base);
end
[clusterIds, sortIdx] = sort(clusterIds);
matFiles = matFiles(sortIdx);

fig = figure('Visible', 'off', 'Position', [100 100 1200 700]);
ax = axes(fig);
hold(ax, 'on');

for k = 1:numel(matFiles)
    s = load(fullfile(matFiles(k).folder, matFiles(k).name));
    fn = fieldnames(s);
    spikeSamples = double(s.(fn{1}));
    spikeSeconds = spikeSamples(:) / fs;
    plot(ax, spikeSeconds, k * ones(size(spikeSeconds)), ...
        'Marker', '|', 'LineStyle', 'none', 'Color', 'k', 'MarkerSize', 6);
end

hold(ax, 'off');
xlim(ax, xWindow);
ylim(ax, [0, numel(matFiles) + 1]);
set(ax, 'YTick', 1:numel(matFiles), 'YTickLabel', string(clusterIds));
xlabel(ax, 'Time (s)');
ylabel(ax, 'Cell Cluster');
title(ax, format_session_title(sessionName));

outName = fullfile(outputDir, [sessionName '_raster.png']);
exportgraphics(fig, outName, 'Resolution', 200);
close(fig);
end

function t = format_session_title(sessionName)
tok = regexpi(sessionName, '^M(\d+)_s(\d+)$', 'tokens');
if ~isempty(tok)
    t = sprintf('M%s S%s', tok{1}{1}, tok{1}{2});
else
    t = strrep(sessionName, '_', ' ');
end
end
