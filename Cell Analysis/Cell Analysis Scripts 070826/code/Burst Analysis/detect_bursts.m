
function bursts = detect_bursts(spike_times_s, isi_thresh_ms)
% detect_bursts  Identify bursts and single spikes based on ISI threshold.
%
% INPUT
%   spike_times_s : vector of spike times in seconds (monotonic increasing)
%   isi_thresh_ms : scalar threshold in ms (e.g., 9) to join spikes into bursts
%
% OUTPUT (struct)
%   bursts.groups      : cell array; each cell contains indices of spikes in one burst (length>=2)
%   bursts.NB          : number of bursts
%   bursts.singles_idx : indices of spikes considered "single spikes" (not in any burst)
%   bursts.NS          : number of single spikes
%   bursts.lengths     : vector of burst lengths (>=2) for each burst
%
% Notes:
%   - Two consecutive spikes belong to the same burst if their ISI < isi_thresh_ms.
%   - Single spikes are spikes that are not part of any burst (i.e., both adjacent ISIs >= thresh).
%
if isempty(spike_times_s)
    bursts = struct('groups', {{}}, 'NB', 0, 'singles_idx', [], 'NS', 0, 'lengths', []);
    return;
end

st = spike_times_s(:);
isi_ms = diff(st) * 1e3;
th = isi_thresh_ms;

in_burst = false;
curr_group = [];
groups = {};

% We traverse spikes, grouping consecutive ISIs below threshold
for i = 1:length(isi_ms)
    if isi_ms(i) < th
        if ~in_burst
            % start a new burst including spike i and i+1
            curr_group = [i, i+1];
            in_burst = true;
        else
            % extend burst to include spike i+1
            curr_group(end+1) = i+1;
        end
    else
        if in_burst
            groups{end+1} = curr_group; %#ok<AGROW>
            in_burst = false;
            curr_group = [];
        end
    end
end
if in_burst
    groups{end+1} = curr_group; %#ok<AGROW>
end

% Mark all spikes that are in any burst
in_any_burst = false(length(st),1);
for k = 1:numel(groups)
    in_any_burst(groups{k}) = true;
end

singles_idx = find(~in_any_burst);

% Build output
bursts.groups   = groups;
bursts.NB       = numel(groups);
bursts.singles_idx = singles_idx;
bursts.NS       = numel(singles_idx);
bursts.lengths  = cellfun(@numel, groups);
