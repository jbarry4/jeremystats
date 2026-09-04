function xf_selftest()
%XF_SELFTEST  Run every Analyse function on synthetic data. Needs no data files.
%
%   xf_selftest()
%
%   Builds an 8 s synthetic LFP -- 8 Hz theta, 45 Hz gamma amplitude-modulated
%   by the theta phase, and a random-walk 1/f-ish background -- plus a second
%   channel that is the same theta delayed by 25 ms with weaker gamma.  Then
%   runs all eight Analyse modes, the event detector, the waveform cutter and
%   the CSD, and prints what came back.
%
%   Use it to check the folder is wired up correctly after moving it, or after
%   a MATLAB upgrade.  Expected results are annotated in the output.
%
%   See also XF_DEMO, XF_ANALYSE.

xf_setpath;

SF  = 1000;
dur = 8;
t   = (0:1/SF:dur-1/SF)';

rng(0);                                     % repeatable
theta = sin(2*pi*8*t);
gamma = 0.4*sin(2*pi*45*t) .* (0.5 + 0.5*sin(2*pi*8*t));
back  = @() 0.3*cumsum(randn(size(t)))/sqrt(numel(t));

x1 = theta            + gamma      + back();
x2 = circshift(theta,25) + 0.4*gamma + back();

fprintf('\nsynthetic LFP: SF=%g Hz, n=%d, %g s, 8 Hz theta + 45 Hz gamma\n', ...
        SF, numel(x1), dur);
fprintf('Image Processing Toolbox (corr2, modes 4 and 7): %s\n\n', ...
        char(string(logical(license('test','image_toolbox')))));

%% the eight Analyse modes
fprintf('--- Analyse modes (band 2-120 Hz, recording start t=100 s) ---\n');
for m = 1:8
    try
        R = xf_analyse(m, x1, SF, 'MinF',2, 'MaxF',120, 'Samples2',x2, 'Start',100);
        switch R.kind
            case 'image'
                fprintf('  %d %-24s %-6s  %dx%d  F=[%.1f %.1f]  T=[%.2f %.2f]', ...
                        m, R.name, R.kind, size(R.Z,1), size(R.Z,2), ...
                        min(R.F), max(R.F), min(R.T)+R.start, max(R.T)+R.start);
                if isfield(R,'corrCoef'), fprintf('  corr2=%.4f', R.corrCoef); end
                fprintf('\n');
            case 'curve'
                inband = R.X >= 2 & R.X <= 120;
                [~,i]  = max(R.Y .* inband);
                fprintf('  %d %-24s %-6s  n=%d  peak in band %.2f Hz\n', ...
                        m, R.name, R.kind, numel(R.Y), R.X(i));
            case 'ridge'
                fprintf('  %d %-24s %-6s  n=%d  median %.2f Hz\n', ...
                        m, R.name, R.kind, numel(R.P), median(R.P));
            case 'cohere'
                [~,i] = max(R.C);
                fprintf('  %d %-24s %-6s  n=%d  peak |C|=%.3f at %.2f Hz\n', ...
                        m, R.name, R.kind, numel(R.C), R.C(i), R.F(i));
        end
    catch err
        fprintf('  %d FAILED: %s (%s)\n', m, err.message, err.identifier);
    end
end
fprintf(['\n  expect: mode 2 peaks near 8 Hz (theta dominates);\n' ...
         '          mode 3 peaks near 45 Hz (diff pre-whitens, gamma wins);\n' ...
         '          mode 6 tracks ~8 Hz; mode 8 peaks near 8 Hz.\n\n']);

%% mode lookup by name
R = xf_analyse('max freq in time', x1, SF, 'MinF',4, 'MaxF',12);
fprintf('--- name dispatch ---\n  ''max freq in time'' -> mode %d, ridge median %.2f Hz\n\n', ...
        R.mode, median(R.P));

%% frame defaults
fprintf('--- frame defaults ---\n');
[fl,fo] = xf_frameDefaults(numel(x1), SF, 0, 0);
fprintf('  auto:             %.2f ms frame, %.2f ms overlap (%.1f%% -- see xf_frameDefaults)\n', ...
        fl, fo, 100*fo/fl);
[fl,fo] = xf_frameDefaults(numel(x1), SF, 500, 250);
fprintf('  explicit 500/250: %.2f ms frame, %.2f ms overlap\n\n', fl, fo);

%% event detector
fprintf('--- event detector ---\n');
[TS,~] = xf_findEvents(x1, SF, 100, 50, 0.8, true, false);
fprintf('  minima below -0.8, 50 ms refractory: %d events, first at %.4f s\n', ...
        numel(TS), TS(1));
TSboth = xf_findEvents(x1, SF, 100, 50, 0.8, true, true);
fprintf('  both polarities:                     %d events\n\n', numel(TSboth));

%% waveform cutting
fprintf('--- waveform cutting ---\n');
chan = struct('Samples',x1, 'currentSF',SF, 'start',0);
W = xf_extractWaveforms(TS(1:5)-100, chan, -16, 32, 4);
fprintf('  5 events x 32 samples, padded 1 -> 4 channels: %dx%d (expect 128x5)\n\n', ...
        size(W,1), size(W,2));

%% CSD
fprintf('--- CSD ---\n');
D = [x1, circshift(x1,3), circshift(x1,6), circshift(x1,9), circshift(x1,12)];
[csd, tsec, ch] = xf_csd(D, SF, 100);
fprintf('  5 channels in -> csd %dx%d, channel axis %.1f..%.1f (interior only), t=[%.2f %.2f]\n\n', ...
        size(csd,1), size(csd,2), min(ch), max(ch), min(tsec), max(tsec));

%% plotting
fprintf('--- plotting ---\n');
fig = figure('Visible','off', 'Position',[80 40 1100 900]);
for m = 1:8
    ax = subplot(4,2,m);
    R  = xf_analyse(m, x1, SF, 'MinF',2, 'MaxF',120, 'Samples2',x2, 'Start',100);
    xf_plotAnalyse(R, ax);
end
close(fig);
fprintf('  all eight modes drew without error\n\n');

fprintf('xf_selftest complete.\n');
