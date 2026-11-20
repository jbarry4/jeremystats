% Bucketed versions of the two summary histograms: instead of one bar
% per session / a fine-grained continuous histogram, group sessions and
% clusters into clearly labeled ranges so the distribution is easy to
% read at a glance. Reuses the stats already computed and saved by
% generate_cluster_histograms.m.

outputDir = 'D:\Data\Archive\Take 2 IZA\Output\Cluster count and firing rate histograms';

sessionCounts = readtable(fullfile(outputDir, 'session_cluster_counts.csv'));
clusterStats  = readtable(fullfile(outputDir, 'cluster_firing_stats.csv'));

%% ---- Bucketed histogram 1: number of clusters per session ----
countEdges = 0:10:80;
countLabels = arrayfun(@(i) sprintf('%d-%d', countEdges(i), countEdges(i+1) - 1), ...
    1:numel(countEdges) - 1, 'UniformOutput', false);
sessionBucketCounts = histcounts(sessionCounts.NumClusters, countEdges);

fig1 = figure('Visible', 'off', 'Position', [100 100 1100 650]);
ax1 = axes(fig1);
bar(ax1, sessionBucketCounts, 'FaceColor', [0.2 0.4 0.7]);
set(ax1, 'XTick', 1:numel(countLabels), 'XTickLabel', countLabels);
xlabel(ax1, 'Number of Clusters (bucketed)');
ylabel(ax1, 'Number of Sessions');
title(ax1, sprintf('Sessions Grouped by Cluster Count (n=%d sessions)', height(sessionCounts)));
ylim(ax1, [0, max(sessionBucketCounts) * 1.15]);
add_bar_labels(ax1, sessionBucketCounts);
exportgraphics(fig1, fullfile(outputDir, 'clusters_per_session_bucketed.png'), 'Resolution', 200);
close(fig1);

%% ---- Bucketed histogram 2: cluster firing rate ----
rateEdges  = [0 0.1 1 5 10 20 50 100 Inf];
rateLabels = {'0-0.1', '0.1-1', '1-5', '5-10', '10-20', '20-50', '50-100', '100+'};
rateBucketCounts = histcounts(clusterStats.FiringRateHz, rateEdges);

fig2 = figure('Visible', 'off', 'Position', [100 100 1100 650]);
ax2 = axes(fig2);
bar(ax2, rateBucketCounts, 'FaceColor', [0.2 0.4 0.7]);
set(ax2, 'XTick', 1:numel(rateLabels), 'XTickLabel', rateLabels);
xlabel(ax2, 'Firing Rate, Hz (bucketed)');
ylabel(ax2, 'Number of Clusters');
title(ax2, sprintf('Clusters Grouped by Firing Rate Range (n=%d clusters)', height(clusterStats)));
ylim(ax2, [0, max(rateBucketCounts) * 1.15]);
add_bar_labels(ax2, rateBucketCounts);
exportgraphics(fig2, fullfile(outputDir, 'firing_rate_bucketed.png'), 'Resolution', 200);
close(fig2);

fprintf('Done. Bucketed figures saved to %s\n', outputDir);

function add_bar_labels(ax, counts)
for i = 1:numel(counts)
    if counts(i) > 0
        text(ax, i, counts(i), num2str(counts(i)), ...
            'HorizontalAlignment', 'center', 'VerticalAlignment', 'bottom');
    end
end
end
