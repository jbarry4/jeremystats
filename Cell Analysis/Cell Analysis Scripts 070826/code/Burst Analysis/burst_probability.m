
function out = burst_probability(spike_times_s, isi_thresh_ms)
% burst_probability  Compute NB, NS, and burst probability as defined in the paper.
%
% Burst probability = NB / (NB + NS)
%
% INPUT
%   spike_times_s : spike times in seconds
%   isi_thresh_ms : ISI threshold in ms (e.g., 9)
%
% OUTPUT (struct)
%   out.NB, out.NS, out.p_burst
%   out.details = detect_bursts(...) for convenience
%
b = detect_bursts(spike_times_s, isi_thresh_ms);
den = b.NB + b.NS;
if den == 0
    p = NaN;
else
    p = b.NB / den;
end
out = struct('NB', b.NB, 'NS', b.NS, 'p_burst', p, 'details', b);
