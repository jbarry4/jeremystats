function [pass, info] = gate2_epochs(sig, ep, P, bank)
%GATE2  The epochs line up.
%
%   nEp == floor(T/epochSec). Blocks are contiguous, inside the trace, and
%   every one has maxAbs and nSharp filled. The filter-safe margin is
%   reported, and epochs overlapping it are flagged.
%
%   FAILS IF: off-by-one at the edges. Output C then breaks silently, because
%   MI and power would be indexed against different epochs.

if nargin < 4, bank = []; end
fprintf('\n--- GATE 2: the epochs line up ---\n');

n        = round(P.epochSec * sig.fs);
expected = floor(sig.T / n);
nEp      = height(ep);

checks = {};
checks{end+1} = {'nEp == floor(T/epochSec)', nEp == expected, ...
                 sprintf('%d epochs, expected %d', nEp, expected)};
checks{end+1} = {'first epoch starts at sample 1', ep.i0(1) == 1, ...
                 sprintf('i0(1) = %d', ep.i0(1))};
checks{end+1} = {'last epoch inside the trace', ep.i1(end) <= sig.T, ...
                 sprintf('i1(end) = %d, T = %d', ep.i1(end), sig.T)};
checks{end+1} = {'blocks are contiguous', ...
                 isempty(ep.i0(2:end)) || all(ep.i0(2:end) - ep.i1(1:end-1) == 1), ...
                 'i0(k+1) == i1(k)+1 throughout'};
checks{end+1} = {'every block is the same length', ...
                 all((ep.i1 - ep.i0 + 1) == n), sprintf('%d samples each', n)};
checks{end+1} = {'maxAbs filled everywhere', ...
                 all(isfinite(ep.maxAbs)), sprintf('%d non-finite', sum(~isfinite(ep.maxAbs)))};
checks{end+1} = {'nSharp filled everywhere', ...
                 all(isfinite(ep.nSharp)), sprintf('%d non-finite', sum(~isfinite(ep.nSharp)))};
checks{end+1} = {'nothing was dropped', ...
                 all(ep.idx(:).' == 1:nEp), 'idx is 1..nEp with no holes'};

pass = localReport(checks, 2);

% ---- filter-safe margin: reported, not failed on -----------------------
info = struct('nEp', nEp, 'expected', expected);
if ~isempty(bank)
    m = bank.edgeSamples;
    head = ep.i0 <= m;
    tail = ep.i1 >  sig.T - m;
    info.edgeSec     = bank.edgeSec;
    info.edgeEpochs  = find(head | tail).';
    fprintf('    filter-safe margin is %.2f s (%d samples) at each end.\n', bank.edgeSec, m);
    if any(head | tail)
        fprintf('    NOTE  %d epoch(s) overlap it: %s\n', ...
                sum(head|tail), mat2str(info.edgeEpochs));
        fprintf('          Nothing is dropped. Treat their MI as suspect if they stand out.\n');
    else
        fprintf('    No epoch overlaps it.\n');
    end
else
    fprintf('    (filter bank not supplied - margin not checked)\n');
end
info.pass = pass;
end


function pass = localReport(checks, g)
pass = true;
for k = 1:numel(checks)
    c = checks{k};
    if c{2}, mark = 'PASS'; else, mark = 'FAIL'; pass = false; end
    fprintf('    [%s] %-34s %s\n', mark, c{1}, c{3});
end
if pass, fprintf('    GATE %d PASSES\n', g); else, fprintf('    GATE %d FAILS\n', g); end
end
