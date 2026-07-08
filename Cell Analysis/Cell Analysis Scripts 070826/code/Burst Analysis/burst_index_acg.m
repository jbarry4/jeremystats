
function out = burst_index_acg(spike_times_s)
% burst_index_acg  Compute burst index from 1-ms ACG as in the paper.
%
% Steps:
%   - Build ACG with 1-ms bins.
%   - Baseline = mean ACG between 40 and 50 ms (absolute lag).
%   - Peak     = maximum ACG between 0 and 10 ms (exclude 0 if needed).
%   - Amplitude = Peak - Baseline.
%   - Index in [-1, 1]:
%       if Amplitude >= 0: index = Amplitude / Peak
%       else              : index = Amplitude / Baseline
%
% OUTPUT (struct)
%   out.index
%   out.peak_val, out.t_peak_ms
%   out.baseline_mean, out.baseline_window_ms
%   out.acg_lags_ms, out.acg
%
[lags_ms, acg] = acg1ms(spike_times_s, 100);
% Use absolute lags for baseline window (40-50 ms, excluding the negative side duplicates)
mask_base = (abs(lags_ms) >= 40) & (abs(lags_ms) <= 50);
baseline_mean = mean(acg(mask_base));

% Peak in 0..10 ms (exclude 0 lag bin if present)
mask_peak = (lags_ms > 0) & (lags_ms <= 10);
[peak_val, idxRel] = max(acg(mask_peak));
idxPeak = find(mask_peak);
if isempty(idxPeak)
    t_peak_ms = NaN;
else
    t_peak_ms = lags_ms(idxPeak(idxRel));
end

amp = peak_val - baseline_mean;

if amp >= 0
    if peak_val > 0
        index = amp / peak_val;
    else
        index = 0; % degenerate
    end
else
    if baseline_mean > 0
        index = amp / baseline_mean; % negative
    else
        index = -1; % extreme case
    end
end

out = struct();
out.index = index;
out.peak_val = peak_val;
out.t_peak_ms = t_peak_ms;
out.baseline_mean = baseline_mean;
out.baseline_window_ms = [40 50];
out.acg_lags_ms = lags_ms;
out.acg = acg;
