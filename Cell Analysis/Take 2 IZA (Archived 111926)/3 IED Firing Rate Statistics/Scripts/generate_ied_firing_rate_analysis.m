%% generate_ied_firing_rate_analysis.m
%
% Top-level driver: for every "Collected Solid IED" session, compute each
% kilosort cluster's instantaneous (1/ISI-based) firing rate in the
% pre-onset, during (onset->offset), and post-offset epochs of every IED
% event, alongside its whole-recording average firing rate, then run a
% Friedman + Holm-corrected Wilcoxon signed-rank comparison across the
% three epochs per cluster, and render summary plots.
%
% Run this script directly in MATLAB (no .sbat / cluster submission
% needed -- everything lives on the local D: drive), same as stage 2.
%
% Outputs (under ..\Output\):
%   ied_epoch_firing_rates.csv   one row per Session x ClusterID x EventNumber
%   ied_firing_rate_stats.csv    one row per Session x ClusterID
%   Plots\<Session>_ied_firing_rate.png
%   Plots\pooled_ied_firing_rate_summary.png

%% ---- Parameters ----
dataRoot = 'D:\Data\Archive\PTEN Project\PTEN';
iedDir   = 'D:\Data\Archive\Take 2 IZA\Collected Solid IED';

sfx       = 30000;  % Hz -- confirmed constant across all 10 IED sessions
                     % (kilosort_tl6_tu7_fs30000.0 folder name; matches sfx
                     % logged by generate_ied_cluster_waveform_plots.m).
                     % Raw CSC files aren't needed for this analysis, so
                     % this is a parameter rather than re-derived from headers.
preWinS   = 1;       % seconds before IED onset ("pre" epoch)
postWinS  = 1;       % seconds after IED offset ("post" epoch)
minEvents = 5;       % minimum complete pre/during/post triplets to run stats

scriptDir = fileparts(mfilename('fullpath'));
stageDir  = fileparts(scriptDir);
izaDir    = fileparts(stageDir);
outDir    = fullfile(stageDir, 'Output');
if ~exist(outDir, 'dir'), mkdir(outDir); end

addpath(scriptDir);
addpath(fullfile(izaDir, '2 Cluster Waveform Visualization', 'Scripts'));
addpath(fullfile(izaDir, '1 Preliminary Cell Cluster Analysis', 'Scripts', 'Full time cluster scripts'));
addpath(fullfile(izaDir, '1 Preliminary Cell Cluster Analysis', 'Scripts', 'Cluster count and firing rate scripts'));

%% ---- Step 1: per-event, per-cluster epoch rates ----
fprintf('[STEP 1] Collecting IED-locked epoch firing rates...\n');
epochTable = collect_ied_epoch_rates(dataRoot, iedDir, sfx, preWinS, postWinS);
writetable(epochTable, fullfile(outDir, 'ied_epoch_firing_rates.csv'));
fprintf('[OK] %d rows written to ied_epoch_firing_rates.csv\n', height(epochTable));

%% ---- Step 2: per-cluster statistics ----
fprintf('[STEP 2] Running Friedman / Wilcoxon signed-rank statistics...\n');
statsTable = run_ied_firing_rate_stats(epochTable, minEvents);
writetable(statsTable, fullfile(outDir, 'ied_firing_rate_stats.csv'));
fprintf('[OK] %d cluster rows written to ied_firing_rate_stats.csv\n', height(statsTable));

%% ---- Step 3: plots ----
fprintf('[STEP 3] Rendering plots...\n');
generate_ied_firing_rate_plots(epochTable, statsTable, outDir);

fprintf('\n[DONE] Output saved under: %s\n', outDir);
