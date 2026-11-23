function statsTable = run_ied_firing_rate_stats(epochTable, minEvents)
% run_ied_firing_rate_stats  Per Session x ClusterID: Friedman omnibus test
% across (pre, during, post) instantaneous firing rate (event = repeated
% measure), plus Holm-Bonferroni-corrected post-hoc Wilcoxon signed-rank
% pairwise tests. Clusters with fewer than minEvents complete (non-NaN)
% pre/during/post triplets are flagged 'InsufficientData' and left untested.
% Omnibus p-values across all tested clusters are additionally corrected
% via Benjamini-Hochberg FDR (FDR_q column), since many clusters are tested.
%
% Input:
%   epochTable  output of collect_ied_epoch_rates
%   minEvents   minimum complete triplets required to run the test (default 5)
%
% Output:
%   statsTable  one row per Session x ClusterID

if nargin < 2, minEvents = 5; end

[groups, sessionU, clusterU] = findgroups(epochTable.Session, epochTable.ClusterID);
nGroups = numel(sessionU);

Session = cell(nGroups, 1);
ClusterID = zeros(nGroups, 1);
NEventsTotal = zeros(nGroups, 1);
NEventsComplete = zeros(nGroups, 1);
MedianPreHz = nan(nGroups, 1);
MedianDuringHz = nan(nGroups, 1);
MedianPostHz = nan(nGroups, 1);
BaselineRateHz = nan(nGroups, 1);
FriedmanChiSq = nan(nGroups, 1);
FriedmanP = nan(nGroups, 1);
Wilcoxon_Pre_vs_During_p = nan(nGroups, 1);
Wilcoxon_During_vs_Post_p = nan(nGroups, 1);
Wilcoxon_Pre_vs_Post_p = nan(nGroups, 1);
Flag = cell(nGroups, 1);

for g = 1:nGroups
    rows = groups == g;
    sub = epochTable(rows, :);

    Session{g} = sessionU{g};
    ClusterID(g) = clusterU(g);
    NEventsTotal(g) = height(sub);

    baseVals = sub.BaselineRateHz(~isnan(sub.BaselineRateHz));
    if ~isempty(baseVals)
        BaselineRateHz(g) = baseVals(1);
    end

    complete = ~isnan(sub.PreInstRateHz) & ~isnan(sub.DuringInstRateHz) & ~isnan(sub.PostInstRateHz);
    nComplete = sum(complete);
    NEventsComplete(g) = nComplete;

    pre = sub.PreInstRateHz(complete);
    dur = sub.DuringInstRateHz(complete);
    post = sub.PostInstRateHz(complete);

    if nComplete > 0
        MedianPreHz(g) = median(pre);
        MedianDuringHz(g) = median(dur);
        MedianPostHz(g) = median(post);
    end

    if nComplete < minEvents
        Flag{g} = 'InsufficientData';
        continue;
    end
    Flag{g} = 'OK';

    [FriedmanP(g), tbl] = friedman([pre, dur, post], 1, 'off');
    FriedmanChiSq(g) = tbl{2, 5};

    pRaw = [signrank(pre, dur), signrank(dur, post), signrank(pre, post)];
    pHolm = holm_bonferroni(pRaw);
    Wilcoxon_Pre_vs_During_p(g) = pHolm(1);
    Wilcoxon_During_vs_Post_p(g) = pHolm(2);
    Wilcoxon_Pre_vs_Post_p(g) = pHolm(3);
end

FDR_q = nan(nGroups, 1);
tested = strcmp(Flag, 'OK');
if any(tested)
    FDR_q(tested) = benjamini_hochberg(FriedmanP(tested));
end

statsTable = table(Session, ClusterID, NEventsTotal, NEventsComplete, ...
    MedianPreHz, MedianDuringHz, MedianPostHz, BaselineRateHz, ...
    FriedmanChiSq, FriedmanP, FDR_q, ...
    Wilcoxon_Pre_vs_During_p, Wilcoxon_During_vs_Post_p, Wilcoxon_Pre_vs_Post_p, Flag);
end

function pHolm = holm_bonferroni(pRaw)
% Holm's step-down Bonferroni correction for a small fixed set of p-values.
[pSorted, idx] = sort(pRaw(:)');
m = numel(pRaw);
pAdjSorted = nan(1, m);
maxSoFar = 0;
for k = 1:m
    maxSoFar = max(maxSoFar, (m - k + 1) * pSorted(k));
    pAdjSorted(k) = min(1, maxSoFar);
end
pHolm = nan(1, m);
pHolm(idx) = pAdjSorted;
end

function q = benjamini_hochberg(pRaw)
% Benjamini-Hochberg FDR correction across the tested clusters' omnibus p-values.
pRaw = pRaw(:);
m = numel(pRaw);
[pSorted, idx] = sort(pRaw);
qSorted = pSorted .* m ./ (1:m)';
for k = m-1:-1:1
    qSorted(k) = min(qSorted(k), qSorted(k+1));
end
qSorted = min(1, qSorted);
q = nan(m, 1);
q(idx) = qSorted;
end
