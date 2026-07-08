
function out = burst_length_stats(spike_times_s, isi_thresh_ms)
% burst_length_stats  Count bursts by length (2,3,4,>4) and compute probabilities.
%
% INPUT
%   spike_times_s : spike times in seconds
%   isi_thresh_ms : ISI threshold in ms (e.g., 9)
%
% OUTPUT (struct)
%   out.counts    : struct with fields n2, n3, n4, nMore
%   out.total_bursts : total number of bursts
%   out.prob      : struct with fields p2, p3, p4, pMore (each = count/total_bursts)
%   out.lengths   : vector of burst lengths for each burst (>=2)
%
b = detect_bursts(spike_times_s, isi_thresh_ms);
lens = b.lengths;
n2 = sum(lens==2);
n3 = sum(lens==3);
n4 = sum(lens==4);
nMore = sum(lens>=5);
tot = numel(lens);

if tot>0
    p2 = n2/tot; p3 = n3/tot; p4 = n4/tot; pMore = nMore/tot;
else
    p2 = NaN; p3 = NaN; p4 = NaN; pMore = NaN;
end

out = struct();
out.counts = struct('n2',n2,'n3',n3,'n4',n4,'nMore',nMore);
out.total_bursts = tot;
out.prob = struct('p2',p2,'p3',p3,'p4',p4,'pMore',pMore);
out.lengths = lens;
