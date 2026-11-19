% Summarize the PTEN kilosort dataset across all M#_s# sessions:
%   1) how many clusters each session has
%   2) the distribution of per-cluster firing rates (Hz), with
%      statistical outliers flagged (IQR rule, computed in log10 space
%      since firing rates are heavily right-skewed).
% Figures + underlying data tables are saved to outputDir.

dataRoot  = 'D:\Data\Archive\PTEN Project\PTEN';
outputDir = 'D:\Data\Archive\Take 2 IZA\Output\Cluster count and firing rate histograms';
fs        = 30000;

if ~exist(outputDir, 'dir')
    mkdir(outputDir);
end

fprintf('Scanning sessions and computing per-cluster firing rates...\n');
[clusterTable, sessionCounts] = collect_cluster_stats(dataRoot, fs);
fprintf('Found %d sessions, %d clusters total.\n', height(sessionCounts), height(clusterTable));

writetable(clusterTable, fullfile(outputDir, 'cluster_firing_stats.csv'));
writetable(sessionCounts, fullfile(outputDir, 'session_cluster_counts.csv'));

%% ---- Histogram 1: number of clusters per session ----
counts = sessionCounts.NumClusters;
Q1 = quantile(counts, 0.25);
Q3 = quantile(counts, 0.75);
IQR = Q3 - Q1;
lowBound  = Q1 - 1.5 * IQR;
highBound = Q3 + 1.5 * IQR;
isSessionOutlier = counts < lowBound | counts > highBound;

sessionLabels = strrep(sessionCounts.Session, '_', ' ');
barColors = repmat([0.2 0.4 0.7], numel(counts), 1);
barColors(isSessionOutlier, :) = repmat([0.8 0.1 0.1], sum(isSessionOutlier), 1);

fig1 = figure('Visible', 'off', 'Position', [100 100 1300 650]);
ax1 = axes(fig1);
b = bar(ax1, counts, 'FaceColor', 'flat');
b.CData = barColors;
set(ax1, 'XTick', 1:numel(counts), 'XTickLabel', sessionLabels, 'XTickLabelRotation', 45);
xlabel(ax1, 'Session');
ylabel(ax1, 'Number of Clusters');
title(ax1, sprintf('Number of Clusters per Recording Session (%d flagged as outliers, IQR rule)', ...
    sum(isSessionOutlier)));
exportgraphics(fig1, fullfile(outputDir, 'clusters_per_session_histogram.png'), 'Resolution', 200);
close(fig1);

sessionOutlierTable = sessionCounts(isSessionOutlier, :);
writetable(sessionOutlierTable, fullfile(outputDir, 'session_cluster_count_outliers.csv'));

%% ---- Histogram 2: cluster firing-rate distribution ----
rate = clusterTable.FiringRateHz;
validMask = rate > 0;

logRate = nan(size(rate));
logRate(validMask) = log10(rate(validMask));

Q1log = quantile(logRate(validMask), 0.25);
Q3log = quantile(logRate(validMask), 0.75);
IQRlog = Q3log - Q1log;
lowThreshLog  = Q1log - 1.5 * IQRlog;
highThreshLog = Q3log + 1.5 * IQRlog;

isHighOutlier = validMask & logRate > highThreshLog;
isLowOutlier  = validMask & logRate < lowThreshLog;
isSilent      = ~validMask;

fig2 = figure('Visible', 'off', 'Position', [100 100 1100 700]);
ax2 = axes(fig2);
histogram(ax2, logRate(validMask), 40, 'FaceColor', [0.2 0.4 0.7], 'EdgeColor', 'none');
hold(ax2, 'on');
xline(ax2, lowThreshLog, 'r--', 'LineWidth', 1.5);
xline(ax2, highThreshLog, 'r--', 'LineWidth', 1.5);
hold(ax2, 'off');

xt = ax2.XTick;
ax2.XTickLabel = arrayfun(@(v) sprintf('%.3g', 10^v), xt, 'UniformOutput', false);
xlabel(ax2, 'Firing Rate (Hz)');
ylabel(ax2, 'Number of Clusters');
title(ax2, sprintf('Cluster Firing Rate Distribution (n=%d; %d high, %d low, %d silent outliers)', ...
    numel(rate), sum(isHighOutlier), sum(isLowOutlier), sum(isSilent)));
exportgraphics(fig2, fullfile(outputDir, 'firing_rate_histogram.png'), 'Resolution', 200);
close(fig2);

outlierMask = isHighOutlier | isLowOutlier | isSilent;
outlierTable = clusterTable(outlierMask, :);
outlierType = cell(height(outlierTable), 1);
outlierType(isHighOutlier(outlierMask)) = {'High firing rate'};
outlierType(isLowOutlier(outlierMask))  = {'Low firing rate'};
outlierType(isSilent(outlierMask))      = {'Silent (0 spikes)'};
outlierTable.OutlierType = outlierType;
outlierTable = sortrows(outlierTable, 'FiringRateHz', 'descend');
writetable(outlierTable, fullfile(outputDir, 'firing_rate_outliers.csv'));

fprintf('Firing rate outlier bounds: < %.4g Hz or > %.4g Hz (IQR rule in log10 space)\n', ...
    10^lowThreshLog, 10^highThreshLog);
fprintf('Flagged %d clusters: %d high, %d low, %d silent.\n', ...
    sum(outlierMask), sum(isHighOutlier), sum(isLowOutlier), sum(isSilent));
fprintf('Done. Figures and tables saved to %s\n', outputDir);
