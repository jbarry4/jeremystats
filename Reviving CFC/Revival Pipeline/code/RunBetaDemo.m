function R = RunBetaDemo(varargin)
%RUNBETADEMO  The whole beta run on synthetic data with known coupling.
%
%   R = RunBetaDemo()
%   R = RunBetaDemo('durSec', 180, 'nSurr', 50)
%
%   Exercises every step and every gate without touching a recording, so you
%   can check the install, and so a change to the pipeline can be smoke-tested
%   in a couple of minutes rather than by re-running a channel.
%
%   The coupling is put in on purpose at 7 Hz phase / 65 Hz amplitude. If the
%   blob does not land there, the bug is in the code.
%
%   Gate 5 is skipped: there is no newFCSE output for synthetic data. That is
%   the one gate this demo cannot stand in for.

p = inputParser;
p.addParameter('durSec', 120);
p.addParameter('nSurr',  20);
p.addParameter('fSlow',  7);
p.addParameter('fFast',  65);
p.addParameter('spikes', 0.4);      % a few transients, to give panel G something
p.addParameter('RunGate8', true);
p.parse(varargin{:});
a = p.Results;

betapath();

P        = params();
P.nSurr  = a.nSurr;
P.fastBW = 20;    % see gate 3: a 10 Hz band cannot carry 7 Hz modulation

sig = SyntheticChannel(a.durSec, 3255.6, ...
        'fSlow', a.fSlow, 'fFast', a.fFast, 'depth', 0.8, 'spikes', a.spikes);

root = betapath();
R = RunBeta(sig, 'Params', P, 'Tag', 'demo_synthetic', ...
            'OutDir', fullfile(root, 'out_demo'), ...
            'RunGate8', a.RunGate8);

% ---- did it find what we planted? --------------------------------------
fprintf('\n--- ground truth check (demo only) ---\n');
fprintf('    planted: %.1f Hz phase / %.0f Hz amplitude\n', a.fSlow, a.fFast);
fprintf('    found:   %.2f Hz phase / %.0f Hz amplitude\n', ...
        R.peakSlowHz, R.peakFastHz);
ok = abs(R.peakSlowHz - a.fSlow) <= 1.0 && abs(R.peakFastHz - a.fFast) <= 15;
if ok
    fprintf('    [PASS] the blob is where it was planted\n\n');
else
    fprintf('    [FAIL] the blob is NOT where it was planted - the code is wrong\n\n');
end
end
