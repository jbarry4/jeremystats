function [pass, info] = gate7_power_mi_aligned(cfc, Pw, ep, P)
%GATE7  Power and MI share an index.
%
%   size(Pw,2) == size(MI,3) == height(ep), and the slow axis is the same
%   length in both. Then a peak-theta sanity check on the band that carries
%   the most power.
%
%   FAILS IF: off by one. Output C -- theta power against MI -- is then
%   quietly wrong, and quietly is the problem: the scatter still looks like
%   a scatter.

fprintf('\n--- GATE 7: power and MI share an index ---\n');

nEp = height(ep);
checks = {};
checks{end+1} = {'epochs agree', ...
    size(Pw,2) == nEp && size(cfc.MI,3) == nEp, ...
    sprintf('power %d, MI %d, table %d', size(Pw,2), size(cfc.MI,3), nEp)};
checks{end+1} = {'slow axis agrees', ...
    size(Pw,1) == size(cfc.MI,1) && size(Pw,1) == P.nSlow, ...
    sprintf('power %d, MI %d, params %d', size(Pw,1), size(cfc.MI,1), P.nSlow)};
checks{end+1} = {'fast axis agrees', ...
    size(cfc.MI,2) == P.nFast, sprintf('MI %d, params %d', size(cfc.MI,2), P.nFast)};
checks{end+1} = {'power is finite and positive', ...
    all(isfinite(Pw(:))) && all(Pw(:) >= 0), ...
    sprintf('%d non-finite, %d negative', sum(~isfinite(Pw(:))), sum(Pw(:) < 0))};

pass = true;
for k = 1:numel(checks)
    c = checks{k};
    if c{2}, mark = 'PASS'; else, mark = 'FAIL'; pass = false; end
    fprintf('    [%s] %-30s %s\n', mark, c{1}, c{3});
end

[~, kPeak] = max(mean(Pw, 2));
info = struct('peakBandHz', P.slowCenters(kPeak), ...
              'peakPower',  mean(Pw(kPeak,:)), 'pass', pass);
fprintf('    strongest slow band: %.2f Hz (%.1f uV^2 mean).\n', ...
        P.slowCenters(kPeak), mean(Pw(kPeak,:)));
fprintf('    Is that a band you believe for this layer? If not, stop here.\n');

if pass, fprintf('    GATE 7 PASSES\n'); else, fprintf('    GATE 7 FAILS\n'); end
info.pass = pass;
end
