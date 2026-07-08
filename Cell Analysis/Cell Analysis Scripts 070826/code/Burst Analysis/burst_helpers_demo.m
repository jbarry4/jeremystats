
function burst_helpers_demo()
% burst_helpers_demo  Minimal usage example for the burst metrics.
% Generates a synthetic spike train and prints metrics.

% Synthetic: Poisson with a few injected bursts
rng(0);
T = 10; % seconds
rate = 5; % Hz
n = poissrnd(rate*T);
st = sort(rand(n,1)*T);
% Inject 3 artificial bursts (triplets within 5 ms)
st = sort([st; 1.000; 1.003; 1.008; 4.200; 4.204; 4.208; 7.5; 7.503; 7.507]);

% Thresholds to test
for th = [6 9 12]
    bp = burst_probability(st, th);
    bl = burst_length_stats(st, th);
    bi = burst_index_acg(st);
    fprintf('ISIth=%d ms | NB=%d, NS=%d, pBurst=%.3f | L2=%d L3=%d L4=%d L>4=%d | BI=%.3f\n', ...
            th, bp.NB, bp.NS, bp.p_burst, ...
            bl.counts.n2, bl.counts.n3, bl.counts.n4, bl.counts.nMore, bi.index);
end
