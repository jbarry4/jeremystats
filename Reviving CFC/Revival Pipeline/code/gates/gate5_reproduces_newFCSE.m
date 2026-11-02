function [pass, info] = gate5_reproduces_newFCSE(cfc, P, refMat, outDir)
%GATE5  It reproduces the old pipeline.
%
%   mean(MI,3) should put the blob where step04_newFCSE.m puts it for this
%   channel. The VALUES will differ -- a 6 s epoch gives a more biased
%   modulation index than one 30-minute window, and the beta averages 300 of
%   them -- but the LOCATION must not move.
%
%   FAILS IF: the blob moves. Stop if it does.
%
%   refMat is a Comodulogram_*.mat written by the old pipeline. Two shapes
%   are handled: a bare numeric matrix, and newFCSE's cell array with the
%   ratId / group / layer columns appended.

if nargin < 4, outDir = ''; end
fprintf('\n--- GATE 5: it reproduces the old pipeline ---\n');

info = struct('skipped', true);
pass = true;

if isempty(refMat) || ~isfile(refMat)
    fprintf('    SKIPPED - no reference comodulogram supplied.\n');
    fprintf('    Point RunBeta at a Comodulogram_*.mat that newFCSE produced for\n');
    fprintf('    THIS channel. Without it this gate cannot run, and it is the only\n');
    fprintf('    check that the rewrite still agrees with the published analysis.\n');
    info.pass = true;  info.skipped = true;
    return
end

% ---- load whatever shape the old file is in ----------------------------
S = load(refMat);
fn = fieldnames(S);
C  = S.(fn{1});
if iscell(C)
    num = cellfun(@(x) isnumeric(x) && isscalar(x), C);
    keepCols = all(num, 1);
    C = cell2mat(C(:, keepCols));
end
C = double(C);

% newFCSE saves the comodulogram transposed (fast x slow) before appending
% columns; the raw driver saves it slow x fast. Orient by the known axes.
oldSlow = 1:0.5:26;    oldSlowC = oldSlow + 0.5/2;
oldFast = 20:5:200;    oldFastC = oldFast + 10/2;
if size(C,1) == numel(oldFast) && size(C,2) == numel(oldSlow)
    C = C.';                              % -> slow x fast
elseif ~(size(C,1) == numel(oldSlow) && size(C,2) == numel(oldFast))
    fprintf('    SKIPPED - reference is %dx%d, which matches neither\n', size(C,1), size(C,2));
    fprintf('    %dx%d (slow x fast) nor its transpose. Check the file.\n', ...
            numel(oldSlow), numel(oldFast));
    info.pass = true;  info.skipped = true;
    return
end

% ---- restrict the old grid to the beta's window, then compare peaks ----
selSlow = oldSlowC >= P.slowCenters(1) & oldSlowC <= P.slowCenters(end);
selFast = oldFastC >= P.fastCenters(1) & oldFastC <= P.fastCenters(end);
Cw = C(selSlow, selFast);
sC = oldSlowC(selSlow);  fC = oldFastC(selFast);

[~, lin] = max(Cw(:));  [jo, io] = ind2sub(size(Cw), lin);
oldPeak = [sC(jo), fC(io)];

mMI = mean(cfc.MI, 3, 'omitnan');
[~, lin] = max(mMI(:));  [jn, in] = ind2sub(size(mMI), lin);
newPeak = [P.slowCenters(jn), P.fastCenters(in)];

dSlow = abs(newPeak(1) - oldPeak(1));
dFast = abs(newPeak(2) - oldPeak(2));

tolSlow = 2;      % Hz. one theta band's worth
tolFast = 20;     % Hz. two fast bands' worth

info = struct('skipped', false, 'oldPeak', oldPeak, 'newPeak', newPeak, ...
              'dSlow', dSlow, 'dFast', dFast, 'refMat', refMat);

fprintf('    old peak (newFCSE): %.2f Hz phase / %.0f Hz amplitude\n', oldPeak(1), oldPeak(2));
fprintf('    new peak (beta):    %.2f Hz phase / %.0f Hz amplitude\n', newPeak(1), newPeak(2));
fprintf('    moved by %.2f Hz phase, %.0f Hz amplitude (tolerance %g / %g)\n', ...
        dSlow, dFast, tolSlow, tolFast);

pass = dSlow <= tolSlow && dFast <= tolFast;
if pass
    fprintf('    GATE 5 PASSES - the blob is in the same place.\n');
else
    fprintf('    GATE 5 FAILS - the blob moved. STOP. Do not run 64 channels.\n');
end
info.pass = pass;

% ---- the two maps side by side -----------------------------------------
fig = figure('Color','w','Position',[80 80 1150 430],'Visible','on');
tiledlayout(fig,1,2,'TileSpacing','compact','Padding','compact');
ax1 = nexttile;
imagesc(ax1, sC, fC, Cw.'); set(ax1,'YDir','normal'); colorbar(ax1);
hold(ax1,'on'); plot(ax1, oldPeak(1), oldPeak(2), 'w+','MarkerSize',12,'LineWidth',1.5);
xlabel(ax1,'phase freq (Hz)'); ylabel(ax1,'amplitude freq (Hz)');
title(ax1,'newFCSE (old), cropped to the beta window','FontWeight','normal');
ax2 = nexttile;
imagesc(ax2, P.slowCenters, P.fastCenters, mMI.'); set(ax2,'YDir','normal'); colorbar(ax2);
hold(ax2,'on'); plot(ax2, newPeak(1), newPeak(2), 'w+','MarkerSize',12,'LineWidth',1.5);
xlabel(ax2,'phase freq (Hz)'); ylabel(ax2,'amplitude freq (Hz)');
title(ax2,'beta, mean over epochs','FontWeight','normal');

if ~isempty(outDir)
    if ~isfolder(outDir), mkdir(outDir); end
    exportgraphics(fig, fullfile(outDir,'gate5_vs_newFCSE.png'), 'Resolution', 130);
end
end
