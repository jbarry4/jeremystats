function stats = ChannelDataRangeReport(dataMatPath, varargin)
% QuickDataRangeReport  (10-min capped version)
% Fast range check: aggregate histogram, per-channel boxplot, CSV stats.
% NEW:
%   'FirstDurationSec' (default 600)  % analyze only first N seconds (needs sfx)
%   'FirstSamples'     (default [])   % OR analyze only first N samples (overrides)
%
% Example:
%   stats = QuickDataRangeReport('LL_input_data.mat', ...
%       'SaveDir','C:\tmp\quicklook', 'FirstDurationSec',30);  
%
%   % If your file lacks sfx, use sample cap instead (e.g., 30k Hz * 600 s):
%   % 'FirstSamples', 18e6

p = inputParser;
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('SaveDir','', @(s)ischar(s)||isstring(s));
p.addParameter('SubsetChannels', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('MaxSamplesPerChannel', 2e5, @(x)isfinite(x)&&x>0);
p.addParameter('BoxplotSamplesPerChannel', 5e3, @(x)isfinite(x)&&x>0);
p.addParameter('Bins', 120, @(x)isfinite(x)&&x>=10);
p.addParameter('PerChannelPNGs', false, @(x)islogical(x)||ismember(x,[0 1]));
p.addParameter('Scale', 1, @(x)isfinite(x)&&x>0);
p.addParameter('UnitLabel','', @(s)ischar(s)||isstring(s));
p.addParameter('RandomSeed', 0, @(x)isnumeric(x)&&isscalar(x));

% NEW parameters
p.addParameter('FirstDurationSec', 30, @(x) (isfinite(x) && x>0) || isinf(x));
p.addParameter('FirstSamples', [], @(x) isempty(x) || (isfinite(x) && x>=1));

p.parse(dataMatPath, varargin{:});
opts = p.Results;
dataMatPath = string(dataMatPath);

if ~isfile(dataMatPath), error('Data MAT not found: %s', dataMatPath); end
mf = matfile(dataMatPath);

% sizes without loading all data
try nRows = size(mf,'d',1); catch, error('MAT must contain variable "d"'); end
try nSampTotal = size(mf,'d',2); catch, error('Can''t read size(d,2).'); end

% sfx optional (needed for time-based cap)
try sfx = mf.sfx; catch, sfx = []; end
try kept_channels = mf.kept_channels; catch, kept_channels = []; end

% --------- EFFECTIVE ANALYSIS WINDOW (cap to first N seconds/samples) ---------
if ~isempty(opts.FirstSamples)
    nSampEff = min(nSampTotal, round(opts.FirstSamples));
    capNote  = sprintf('first %d samples', nSampEff);
elseif isfinite(opts.FirstDurationSec)
    if isempty(sfx)
        warning('FirstDurationSec=%.1f requested but sfx missing; analyzing full file instead.', opts.FirstDurationSec);
        nSampEff = nSampTotal;
        capNote  = 'FULL file';
    else
        nSampEff = min(nSampTotal, round(opts.FirstDurationSec * sfx));
        capNote  = sprintf('first %.1f min (~%d samples @ %.0f Hz)', opts.FirstDurationSec/60, nSampEff, sfx);
    end
else
    nSampEff = nSampTotal;
    capNote  = 'FULL file';
end

% ---------- Output dir (FORCED: same as the .mat being analyzed) ----------
[outDir,~,~] = fileparts(char(dataMatPath));
if isempty(outDir), outDir = pwd; end
if ~exist(outDir,'dir'), mkdir(outDir); end


% Channel list
if isempty(opts.SubsetChannels)
    chList = 1:nRows;
else
    chList = opts.SubsetChannels(:).';
    chList = chList(chList>=1 & chList<=nRows);
end

rng(opts.RandomSeed);

% ---------- Sampling plan ----------
maxPerCh = min(nSampEff, round(opts.MaxSamplesPerChannel));
boxPerCh = min(nSampEff, round(opts.BoxplotSamplesPerChannel));

% Preallocate stats containers
K = numel(chList);
col = @(n) nan(K, n);
v_min = col(1); v_p1 = col(1); v_p5 = col(1); v_q25 = col(1); v_med = col(1);
v_q75 = col(1); v_p95 = col(1); v_p99 = col(1); v_max = col(1);
v_mean = col(1); v_std = col(1); v_rms = col(1); v_iqr = col(1); v_mad = col(1);
n_valid = col(1);

p1s = nan(K,1); p99s = nan(K,1);

fprintf('QuickDataRangeReport: %d channel(s), %d samples total, analyzing %s.\n', ...
        K, nSampTotal, capNote);

% ---------- First pass: stats + percentiles ----------
for ii = 1:K
    ch = chList(ii);
    idx = sample_indices(nSampEff, maxPerCh);
    y = double(mf.d(ch, idx)) * opts.Scale;
    y = y(isfinite(y));
    if isempty(y), continue; end

    n_valid(ii) = numel(y);
    v_min(ii)   = min(y);     v_max(ii) = max(y);
    v_mean(ii)  = mean(y);    v_std(ii) = std(y,0);
    v_rms(ii)   = sqrt(mean(y.^2));
    v_med(ii)   = median(y);
    v_q25(ii)   = quantile(y,0.25);
    v_q75(ii)   = quantile(y,0.75);
    v_iqr(ii)   = iqr(y);
    v_mad(ii)   = mad(y,1);

    v_p1(ii)    = quantile(y,0.01);
    v_p5(ii)    = quantile(y,0.05);
    v_p95(ii)   = quantile(y,0.95);
    v_p99(ii)   = quantile(y,0.99);

    p1s(ii)  = v_p1(ii);
    p99s(ii) = v_p99(ii);
end

% Determine histogram edges from robust combined range
rob_lo = nanmin(p1s);  rob_hi = nanmax(p99s);
if ~isfinite(rob_lo) || ~isfinite(rob_hi) || rob_lo>=rob_hi
    rob_lo = nanmin(v_min); rob_hi = nanmax(v_max);
end
edges = linspace(rob_lo, rob_hi, opts.Bins+1);
agg_counts = zeros(1, numel(edges)-1);

% For boxplot, gather thinner sample per channel
box_vals = []; box_grp = [];

% ---------- Second pass: aggregate histogram + boxplot sample ----------
for ii = 1:K
    ch = chList(ii);

    % Histogram accumulation
    idxH = sample_indices(nSampEff, maxPerCh);
    yh = double(mf.d(ch, idxH)) * opts.Scale; yh = yh(isfinite(yh));
    if ~isempty(yh), agg_counts = agg_counts + histcounts(yh, edges); end

    % Boxplot sampling
    idxB = sample_indices(nSampEff, boxPerCh);
    yb = double(mf.d(ch, idxB)) * opts.Scale; yb = yb(isfinite(yb));
    if ~isempty(yb)
        box_vals = [box_vals; yb(:)]; %#ok<AGROW>
        box_grp  = [box_grp; ii*ones(numel(yb),1)]; %#ok<AGROW>
    end

    % Optional per-channel histogram PNG
    if opts.PerChannelPNGs && ~isempty(yh)
        figure('Color','w','Position',[80 80 600 420],'Visible','off');
        histogram(yh, edges, 'Normalization','pdf');
        grid on; box on;
        xlabel(with_units('Amplitude', opts.UnitLabel));
        ylabel('PDF');
        ttl = sprintf('Channel %d', ch);
        if ~isempty(kept_channels)
            ttl = sprintf('Row %d (CSC%d)', ch, kept_channels(ch));
        end
        title(ttl);
        outPNG = fullfile(outDir, sprintf('hist_channel_%03d.png', ch));
        exportgraphics(gcf, outPNG, 'Resolution', 220);
        close(gcf);
    end
end

% ---------- Unit guess ----------
typ_amp = median(abs(v_p95(~isnan(v_p95))));
typ_iqr = median(v_iqr(~isnan(v_iqr)));
[unit_guess, ~] = guess_units(typ_amp, typ_iqr);
unit_label_final = string(opts.UnitLabel);
if unit_label_final == "", unit_label_final = unit_guess; end

fprintf('Heuristic unit guess: %s (typ_amp≈%.1f, typ_IQR≈%.1f in scaled units)\n', ...
    tern(unit_label_final~="", unit_label_final, "(unknown)"), typ_amp, typ_iqr);

% ---------- Save aggregate histogram ----------
figure('Color','w','Position',[80 80 720 480],'Visible','off');
centers = 0.5*(edges(1:end-1)+edges(2:end));
bar(centers, agg_counts/sum(agg_counts), 'EdgeColor','none');
grid on; box on;
xlabel(with_units('Amplitude', unit_label_final));
ylabel('Probability');
ttl = sprintf('Aggregate amplitude distribution (first segment: %s)', capNote);
title(ttl);
outHist = fullfile(outDir, 'hist_aggregate.png');
exportgraphics(gcf, outHist, 'Resolution', 220);
close(gcf);

% ---------- Save per-channel boxplot ----------
if ~isempty(box_vals)
    figure('Color','w','Position',[60 60 1000 500],'Visible','off');
    boxplot(box_vals, box_grp, 'PlotStyle','compact', 'Symbol','.');
    grid on; box on;
    xlabel('Channel index');
    ylabel(with_units('Amplitude', unit_label_final));
    title(sprintf('Per-channel boxplots (sampled; %s)', capNote));
    if ~isempty(kept_channels) && K<=96
        xt = get(gca,'XTick'); xt = xt(xt>=1 & xt<=K);
        labs = arrayfun(@(k) sprintf('%d|CSC%d', chList(k), kept_channels(chList(k))), xt, 'UniformOutput',false);
        set(gca,'XTickLabel',labs,'XTickLabelRotation',90);
    end
    outBox = fullfile(outDir, 'boxplot_per_channel.png');
    exportgraphics(gcf, outBox, 'Resolution', 220);
    close(gcf);
else
    outBox = '';
end

% ---------- Save CSV summary ----------
ch_col = chList(:);
if ~isempty(kept_channels), csc_col = kept_channels(chList(:)); else, csc_col = nan(numel(chList),1); end

stats = table( ...
    ch_col, csc_col, n_valid, ...
    v_min, v_p1, v_p5, v_q25, v_med, v_q75, v_p95, v_p99, v_max, ...
    v_mean, v_std, v_rms, v_iqr, v_mad, ...
    'VariableNames', {'Row','CSC','N','Min','P01','P05','Q25','Median','Q75','P95','P99','Max','Mean','Std','RMS','IQR','MAD'});

csvPath = fullfile(outDir, 'channel_stats.csv');
writetable(stats, csvPath);

% ---------- Console summary ----------
fprintf('Saved:\n  %s\n', outHist);
if ~isempty(outBox), fprintf('  %s\n', outBox); end
fprintf('  %s\n', csvPath);
if ~isempty(sfx), fprintf('Sampling rate: %.2f Hz\n', sfx); end
fprintf('Unit label used in plots: %s\n', tern(unit_label_final~="", unit_label_final, '(none)'));

end

% ===== helpers =====
function idx = sample_indices(nSamp, k)
    if k >= nSamp
        idx = 1:nSamp;
    else
        step = max(1, floor(nSamp / k));
        start = randi(step);
        idx = start:step:min(nSamp, start + step*(k-1));
        if numel(idx) > k, idx = idx(1:k); end
    end
end

function s = tern(cond, a, b), if cond, s = a; else, s = b; end, end
function lbl = with_units(name, unitLabel)
    unitLabel = string(unitLabel);
    if unitLabel==""; lbl = name; else; lbl = sprintf('%s (%s)', name, unitLabel); end
end
function [lab, factor] = guess_units(typ_amp, typ_iqr)
    lab = ""; factor = 1;
    a = median([abs(typ_amp), abs(typ_iqr)]);
    if ~isfinite(a), return; end
    if a >= 20 && a <= 2e4, lab = 'µV';
    elseif a >= 0.02 && a <= 20, lab = 'mV';
    else, lab = ''; end
end
