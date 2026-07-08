function out = burst_all_metrics(spike_times_s, isi_thresh_ms)
% burst_all_metrics  Compute all burst-related metrics in one call.
%
% INPUT
%   spike_times_s : vector of spike times (s, sorted)
%   isi_thresh_ms : ISI threshold (ms) for burst detection
%
% OUTPUT (struct)
%   out.NB, out.NS, out.p_burst
%   out.lengths, out.length_counts, out.length_probs
%   out.acg_index, out.acg_details
%   out.details (full detect_bursts output)

    % --- 1. Core detection ---
    b = detect_bursts(spike_times_s, isi_thresh_ms);

    % --- 2. Burst probability ---
    den = b.NB + b.NS;
    if den > 0
        p_burst = b.NB / den;
    else
        p_burst = NaN;
    end

    % --- 3. Burst length stats ---
    lens = b.lengths;
    n2 = sum(lens==2);
    n3 = sum(lens==3);
    n4 = sum(lens==4);
    nMore = sum(lens>=5);
    tot = numel(lens);

    if tot > 0
        probs = [n2 n3 n4 nMore] / tot;
    else
        probs = [NaN NaN NaN NaN];
    end

    % --- 4. Burst index from ACG ---
    bi = burst_index_acg(spike_times_s);

    % --- Collect results ---
    out = struct();
    out.NB = b.NB;
    out.NS = b.NS;
    out.p_burst = p_burst;
    out.lengths = lens;
    out.length_counts = struct('n2',n2,'n3',n3,'n4',n4,'nMore',nMore);
    out.length_probs  = struct('p2',probs(1),'p3',probs(2), ...
                               'p4',probs(3),'pMore',probs(4));
    out.acg_index = bi.index;
    out.acg_details = bi; % keep full ACG info
    out.details = b;      % keep full burst grouping
end
