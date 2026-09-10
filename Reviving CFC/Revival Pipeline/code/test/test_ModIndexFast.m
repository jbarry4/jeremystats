function results = test_ModIndexFast()
%TEST_MODINDEXFAST  Gate 4, as a test you can re-run without a recording.
%
%   results = test_ModIndexFast()
%
%   ModIndexFast must return the same numbers as ModIndex_v2.m -- the
%   reference implementation, kept unchanged in 01_core_tort/ -- to machine
%   precision. Everything else in the beta rests on that, because the
%   surrogate step calls it 18.9 million times and nothing else is ever
%   compared against the published analysis.
%
%   Run it: betapath(); test_ModIndexFast()

betapath();
fprintf('\n=== test_ModIndexFast ===\n');

nbin     = 18;
winsize  = 2*pi/nbin;
position = -pi + (0:nbin-1)*winsize;      % exactly as ModIndex_v2 builds it
tol      = 1e-12;

results = struct('name', {}, 'maxDiff', {}, 'pass', {});

% ---------------------------------------------------------------- case 1
% Ordinary coupled data, the case that actually runs.
rng(1, 'twister');
fs = 3255.6;  n = round(6*fs);
t  = (0:n-1)/fs;
ph = angle(hilbert(sin(2*pi*7*t) + 0.3*randn(1,n))')';
am = (1 + 0.8*sin(ph - pi/2)) .* (1 + 0.2*randn(1,n));
results(end+1) = localCompare('coupled 6 s epoch', ph, am, position, nbin, tol);

% ---------------------------------------------------------------- case 2
% Many amplitude bands at once: the blocked path CFC.m actually uses.
Am = repmat(am, 37, 1) .* (1 + 0.1*randn(37, n));
[miF, maF] = ModIndexFast(ph, Am, nbin);
worst = 0;
for i = 1:size(Am,1)
    [miR, maR] = ModIndex_v2(ph, Am(i,:), position);
    worst = max([worst, abs(miF(i)-miR), max(abs(maF(i,:)-maR))]);
end
results(end+1) = struct('name','37 bands blocked in one call', ...
                        'maxDiff', worst, 'pass', worst < tol);
localSay(results(end));

% ---------------------------------------------------------------- case 3
% Uniform phase: MI must be ~0, and both must agree it is.
ph3 = linspace(-pi, pi, n);  ph3(end) = [];
am3 = ones(1, numel(ph3)) + 0.01*randn(1, numel(ph3));
results(end+1) = localCompare('flat, MI near zero', ph3, am3, position, nbin, tol);
fprintf('      (MI = %.3e, should be near 0)\n', ModIndexFast(ph3, am3, nbin));

% ---------------------------------------------------------------- case 4
% THE edge case. angle() returns values in (-pi, pi], so phase can be exactly
% +pi. ModIndex_v2's bins are half-open, so such a sample belongs to no bin
% and is silently dropped. A floor()-and-clamp implementation would put it in
% the last bin instead, and disagree. This is the failure gate 4 is for.
rng(4, 'twister');
ph4 = (rand(1, 5000)*2 - 1) * pi;
ph4(1:25) = pi;                 % exactly the top edge
ph4(26:50) = -pi;               % exactly the bottom edge
am4 = 1 + rand(1, 5000);
results(end+1) = localCompare('phase exactly +/-pi', ph4, am4, position, nbin, tol);
B = PhaseBins(ph4, nbin);
fprintf('      (%d sample(s) fell outside every bin, as ModIndex_v2 requires)\n', B.nDropped);

% ---------------------------------------------------------------- case 5
% Samples sitting exactly on interior bin edges.
ph5 = repelem(position, 200);
am5 = 1 + rand(1, numel(ph5));
results(end+1) = localCompare('phase exactly on bin edges', ph5, am5, position, nbin, tol);

% ---------------------------------------------------------------- case 6
% An empty bin: ModIndex_v2 gives NaN there, and so must the fast one.
ph6 = [linspace(-pi, 0, 3000), linspace(0.01, 1, 2000)];
am6 = 1 + rand(1, numel(ph6));
[miF6, maF6] = ModIndexFast(ph6, am6, nbin);
[miR6, maR6] = ModIndex_v2(ph6, am6, position);
sameNaN = isequaln(isnan(maF6(:)), isnan(maR6(:)));
d6 = max(abs(maF6(:) - maR6(:)), [], 'omitnan');
results(end+1) = struct('name','empty bins give NaN in both', ...
        'maxDiff', d6, 'pass', sameNaN && isequaln(isnan(miF6), isnan(miR6)));
localSay(results(end));
if isnan(miR6), miWord = 'NaN'; else, miWord = 'finite'; end
fprintf('      (%d empty bin(s); MI is %s in both)\n', sum(isnan(maR6)), miWord);

% ---------------------------------------------------------------- speed
fprintf('\n  speed, 6 s epoch at %.0f Hz, one modulation index:\n', fs);
nRep = 60;
t0 = tic; for k=1:nRep, ModIndex_v2(ph, am, position); end; tR = toc(t0)/nRep;
t0 = tic; for k=1:nRep, ModIndexFast(ph, am, nbin);    end; tF = toc(t0)/nRep;
B  = PhaseBins(ph, nbin);
t0 = tic; for k=1:nRep, MIFromBins(Am, B);             end; tB = toc(t0)/nRep;
fprintf('    ModIndex_v2                 %7.3f ms\n', 1000*tR);
fprintf('    ModIndexFast (1 band)       %7.3f ms   %.1fx\n', 1000*tF, tR/tF);
fprintf('    blocked, 37 bands per pass  %7.3f ms   %.3f ms per band, %.1fx\n', ...
        1000*tB, 1000*tB/37, tR/(tB/37));

% ---------------------------------------------------------------- verdict
allPass = all([results.pass]);
fprintf('\n  %d/%d cases pass (tolerance %.0e)\n', sum([results.pass]), numel(results), tol);
if allPass
    fprintf('  TEST PASSES\n\n');
else
    fprintf('  TEST FAILS\n\n');
    error('test_ModIndexFast:mismatch', 'ModIndexFast does not match ModIndex_v2.');
end
end


% =======================================================================
function r = localCompare(name, ph, am, position, nbin, tol)
[miF, maF] = ModIndexFast(ph, am, nbin);
[miR, maR] = ModIndex_v2(ph, am, position);
d = max([abs(miF - miR), max(abs(maF(:) - maR(:)))]);
r = struct('name', name, 'maxDiff', d, 'pass', d < tol);
localSay(r);
end


function localSay(r)
if r.pass, mark = 'PASS'; else, mark = 'FAIL'; end
fprintf('  [%s] %-34s max diff %.3e\n', mark, r.name, r.maxDiff);
end
