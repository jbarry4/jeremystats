function xf_demo(ncsfile, startSec, rangeSec)
%XF_DEMO  Run every Analyse mode on one .ncs file and plot the lot.
%
%   xf_demo()                          prompts for a file
%   xf_demo('CSC1.ncs')                first 10 s
%   xf_demo('CSC1.ncs', 120, 5)        5 s starting at t=120 s
%
%   Single-channel modes (1,2,3,5,6) run on the file itself.  The
%   two-channel modes (4,7,8) need a second channel, so this demo compares
%   the file against itself -- which makes them degenerate on purpose
%   (difference = 0, coherency = 1).  That is a wiring check, not an
%   analysis; pass two different channels to xf_analyse for real results.
%
%   See also XF_ANALYSE, XF_PLOTANALYSE.

if nargin < 1 || isempty(ncsfile)
    [n, p] = uigetfile({'*.ncs;*.NCS'}, 'Select a Neuralynx CSC file');
    if isequal(n, 0), return; end
    ncsfile = fullfile(p, n);
end
if nargin < 2 || isempty(startSec), startSec = 0;  end
if nargin < 3 || isempty(rangeSec), rangeSec = 10; end

f = Cscfile2_PP(ncsfile);
f = f.setstart(startSec);
f = f.setrange(rangeSec);
f = f.readdata();

fprintf('%s: %g s from t=%g s, SF=%g Hz, %d samples\n', ...
        f.AcqEntName, rangeSec, startSec, f.currentSF, numel(f.Samples));

modes = 1:8;
figure('Name', sprintf('Analyse modes -- %s', f.AcqEntName), ...
       'Position', [80 40 1100 900]);   % roomy -- 8 stacked titles collide otherwise

for k = 1:numel(modes)
    m = modes(k);
    ax = subplot(4, 2, k);
    try
        R = xf_analyse(m, f.Samples, f.currentSF, ...
                       'MinF', 0, 'MaxF', 200, ...
                       'Start', startSec, ...
                       'Samples2', f.Samples);
        xf_plotAnalyse(R, ax);
    catch err
        title(ax, sprintf('mode %d failed: %s', m, err.message), ...
              'Interpreter', 'none');
    end
end
