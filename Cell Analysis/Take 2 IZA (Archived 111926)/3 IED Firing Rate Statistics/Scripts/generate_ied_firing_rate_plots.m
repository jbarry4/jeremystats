function generate_ied_firing_rate_plots(epochTable, statsTable, outDir)
% generate_ied_firing_rate_plots  Per-session small-multiple pre/during/post
% boxplots (one subplot per cluster, whole-recording baseline rate drawn as
% a reference line, Holm-corrected pairwise significance annotated) plus one
% pooled summary figure (log10 y-axis, matching the archive's existing
% IQR-in-log-space firing-rate convention) across every session/cluster.
%
% Inputs:
%   epochTable   output of collect_ied_epoch_rates
%   statsTable   output of run_ied_firing_rate_stats
%   outDir       stage Output folder (plots saved under outDir\Plots)

plotsDir = fullfile(outDir, 'Plots');
if ~exist(plotsDir, 'dir'), mkdir(plotsDir); end

sessions = unique(epochTable.Session, 'stable');

for s = 1:numel(sessions)
    sessionName = sessions{s};
    sessRows = strcmp(epochTable.Session, sessionName);
    sessStatsRows = strcmp(statsTable.Session, sessionName);

    clusterIds = sort(unique(epochTable.ClusterID(sessRows)));
    nClusters = numel(clusterIds);
    if nClusters == 0, continue; end

    nCols = min(4, nClusters);
    nRows = ceil(nClusters / nCols);
    fig = figure('Color', 'w', 'Position', [80 80 300*nCols 260*nRows], 'Visible', 'off');
    tl = tiledlayout(fig, nRows, nCols, 'TileSpacing', 'compact', 'Padding', 'compact');

    for c = 1:nClusters
        cid = clusterIds(c);
        rows = sessRows & epochTable.ClusterID == cid;
        pre = epochTable.PreInstRateHz(rows);
        dur = epochTable.DuringInstRateHz(rows);
        post = epochTable.PostInstRateHz(rows);

        ax = nexttile(tl, c);
        boxplot(ax, [pre, dur, post], 'Labels', {'Pre', 'During', 'Post'}, 'Symbol', 'k.');
        hold(ax, 'on');

        statRow = sessStatsRows & statsTable.ClusterID == cid;
        titleStr = sprintf('Cluster %d', cid);

        if any(statRow)
            baseline = statsTable.BaselineRateHz(statRow);
            if ~isnan(baseline)
                yline(ax, baseline, '--r', 'Baseline', 'LabelHorizontalAlignment', 'left');
            end

            if strcmp(statsTable.Flag{statRow}, 'OK')
                titleStr = [titleStr, sprintf('  (Friedman p=%.3g)', statsTable.FriedmanP(statRow))]; %#ok<AGROW>
                sigPairs = { ...
                    [1 2], statsTable.Wilcoxon_Pre_vs_During_p(statRow); ...
                    [2 3], statsTable.Wilcoxon_During_vs_Post_p(statRow); ...
                    [1 3], statsTable.Wilcoxon_Pre_vs_Post_p(statRow)};
                yl = ylim(ax);
                step = (yl(2) - yl(1)) * 0.08;
                if step <= 0, step = 1; end
                nSig = 0;
                for k = 1:size(sigPairs, 1)
                    pVal = sigPairs{k, 2};
                    if ~isnan(pVal) && pVal < 0.05
                        nSig = nSig + 1;
                        pair = sigPairs{k, 1};
                        yPos = yl(2) + nSig * step;
                        plot(ax, pair, [yPos yPos], '-k', 'LineWidth', 1);
                        text(ax, mean(pair), yPos, sig_stars(pVal), ...
                            'HorizontalAlignment', 'center', 'VerticalAlignment', 'bottom');
                    end
                end
                if nSig > 0
                    ylim(ax, [yl(1), yl(2) + (nSig + 1) * step]);
                end
            else
                titleStr = [titleStr, '  (insufficient data)']; %#ok<AGROW>
            end
        end
        title(ax, titleStr, 'FontSize', 9);
        ylabel(ax, 'Instantaneous rate (Hz)');
    end

    title(tl, sprintf('%s -- IED-locked instantaneous firing rate', strrep(sessionName, '_', '\_')), ...
        'FontWeight', 'bold');
    exportgraphics(fig, fullfile(plotsDir, sprintf('%s_ied_firing_rate.png', sessionName)), 'Resolution', 150);
    close(fig);
end

%% ---- pooled summary (log10 y-axis) ----
valid = ~isnan(epochTable.PreInstRateHz) & ~isnan(epochTable.DuringInstRateHz) & ~isnan(epochTable.PostInstRateHz);
pre = epochTable.PreInstRateHz(valid);
dur = epochTable.DuringInstRateHz(valid);
post = epochTable.PostInstRateHz(valid);
baseline = epochTable.BaselineRateHz(valid);

fig = figure('Color', 'w', 'Position', [80 80 700 500], 'Visible', 'off');
ax = axes(fig); %#ok<LAXES>
hold(ax, 'on');
allData = [pre, dur, post];
allData(allData <= 0) = NaN;   % guard against log10(0) for the (rare) zero-rate samples
boxplot(ax, log10(allData), 'Labels', {'Pre', 'During', 'Post'}, 'Symbol', 'k.');
if any(baseline > 0)
    yline(ax, median(log10(baseline(baseline > 0)), 'omitnan'), '--r', 'Median baseline');
end
ylabel(ax, 'log_{10} instantaneous rate (Hz)');
title(ax, sprintf('All sessions/clusters (n = %d complete event triplets)', numel(pre)));
exportgraphics(fig, fullfile(plotsDir, 'pooled_ied_firing_rate_summary.png'), 'Resolution', 150);
close(fig);
end

function s = sig_stars(p)
if p < 0.001
    s = '***';
elseif p < 0.01
    s = '**';
elseif p < 0.05
    s = '*';
else
    s = '';
end
end
