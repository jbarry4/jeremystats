function R = RunBeta(source, opts)
%RUNBETA  One channel, end to end, with a gate after every step.
%
%   R = RunBeta('Y:\...\CSC12.ncs')
%   R = RunBeta(sig)                              % a struct from SyntheticChannel
%   R = RunBeta(ncs, RefMat="...\Comodulogram_12.mat", OutDir="...")
%
%   opts
%     OutDir      where the .png and .mat go        (default <Revival Pipeline>/out)
%     Tag         basename for the outputs          (default from the source)
%     RefMat      a newFCSE Comodulogram_*.mat for gate 5
%     Surrogates  run the surrogate step            (default true)
%     RunGate6    run the phase-randomised null     (default true)
%     RunGate8    launch a fresh MATLAB to reload   (default true)
%     Params      a params() struct to override
%
%   Stops at the first HARD gate failure. Gates 1, 2, 4, 7 and 8 are hard:
%   they mean the code is wrong. Gates 3, 5 and 6 print loudly but only gate
%   5 moving the blob should make you stop and think rather than debug.

arguments
    source
    opts.OutDir     (1,:) char = ''
    opts.Tag        (1,:) char = ''
    opts.RefMat     (1,:) char = ''
    opts.Surrogates (1,1) logical = true
    opts.RunGate6   (1,1) logical = true
    opts.RunGate8   (1,1) logical = true
    opts.Params            = []
end

root = betapath();
if isempty(opts.OutDir), opts.OutDir = fullfile(root, 'out'); end
if ~isfolder(opts.OutDir), mkdir(opts.OutDir); end

if isempty(opts.Params), P = params(); else, P = opts.Params; end

tAll = tic;
fprintf('\n==========================================================\n');
fprintf('  CFC BETA RUN  -  one channel, eight gates  (%s)\n', P.version);
fprintf('==========================================================\n');
localPrintParams(P);

R = struct('params', P, 'gates', struct(), 'outDir', opts.OutDir);

% ---- 1. load -----------------------------------------------------------
if ischar(source) || isstring(source)
    sig = LoadCSC(char(source), P);
    if isempty(opts.Tag)
        [~, b] = fileparts(char(source));  opts.Tag = b;
    end
else
    sig = source;
    fprintf('LoadCSC: skipped, using a supplied signal (%s)\n', sig.path);
    if isempty(opts.Tag), opts.Tag = 'synthetic'; end
end
R.sig = rmfield(sig, 'lfp');       % keep the metadata, not the trace
R.tag = opts.Tag;

[g1, R.gates.g1] = gate1_looks_like_lfp(sig, P, opts.OutDir);
localHard(g1, 1);

% ---- 2. epochs ---------------------------------------------------------
ep = MakeEpochs(sig, P);
R.epochs = ep;

% ---- 3. filter banks ---------------------------------------------------
bank = FilterBanks(sig, P);

[g2, R.gates.g2] = gate2_epochs(sig, ep, P, bank);
localHard(g2, 2);

[g3, R.gates.g3] = gate3_envelope_tracks_phase(sig, bank, ep, P, opts.OutDir);

% ---- 4. the fast modulation index agrees with the reference ------------
[g4, R.gates.g4] = gate4_fast_matches_reference(bank, ep, P);
localHard(g4, 4);

% ---- 5. MI, no surrogates, compared against the old pipeline -----------
cfc0 = CFC(bank, ep, P, false);
[g5, R.gates.g5] = gate5_reproduces_newFCSE(cfc0, P, opts.RefMat, opts.OutDir);
if ~g5
    fprintf('\n  *** GATE 5 FAILED: the blob moved. Stopping. ***\n');
    fprintf('  Nothing below this point is worth computing until that is understood.\n');
    R.stoppedAt = 5;  return
end

% ---- 6. surrogates -----------------------------------------------------
if opts.Surrogates
    cfc = CFC(bank, ep, P, true);
else
    cfc = cfc0;
    fprintf('\nCFC: surrogates skipped by request - z will be empty.\n');
end
R.cfc = rmfield(cfc, {'MI'});      % the big array is saved separately

% the time-averaged map is small (nSlow x nFast) and worth carrying around
R.meanMI = mean(cfc.MI, 3, 'omitnan');
[~, lin] = max(R.meanMI(:));
[jPk, iPk]   = ind2sub(size(R.meanMI), lin);
R.peakSlowHz = P.slowCenters(jPk);
R.peakFastHz = P.fastCenters(iPk);
R.peakMI     = R.meanMI(jPk, iPk);

if opts.RunGate6
    [g6, R.gates.g6] = gate6_null_is_flat(sig, ep, P, opts.OutDir);
else
    g6 = true;  R.gates.g6 = struct('skipped', true);
    fprintf('\n--- GATE 6: skipped by request ---\n');
end

% ---- 7. power ----------------------------------------------------------
Pw = ThetaPower(bank, ep, P);
[g7, R.gates.g7] = gate7_power_mi_aligned(cfc, Pw, ep, P);
localHard(g7, 7);

clear bank                                   % 1.7 GB, done with it

% ---- 8. figure, file, and the reload test ------------------------------
fig = ChannelQC(sig, ep, cfc, Pw, P, opts.Tag, opts.OutDir);
R.qcFigure = fullfile(opts.OutDir, sprintf('%s_qc.png', opts.Tag));

R.matFile = SaveChannel(opts.OutDir, opts.Tag, sig, ep, cfc, Pw, P);

if opts.RunGate8
    [g8, R.gates.g8] = gate8_file_stands_alone(R.matFile, opts.OutDir);
else
    g8 = true;  R.gates.g8 = struct('skipped', true);
    fprintf('\n--- GATE 8: skipped by request ---\n');
end

% ---- the scoreboard ----------------------------------------------------
R.elapsed = toc(tAll);
names = {'looks like an LFP', 'epochs line up', 'envelope tracks phase', ...
         'fast == reference', 'reproduces newFCSE', 'null is flat', ...
         'power/MI aligned', 'file stands alone'};
res = [g1 g2 g3 g4 g5 g6 g7 g8];
skipped = [false false false false ...
           isfield(R.gates.g5,'skipped') && R.gates.g5.skipped, ...
           isfield(R.gates.g6,'skipped') && R.gates.g6.skipped, ...
           false, ...
           isfield(R.gates.g8,'skipped') && R.gates.g8.skipped];

fprintf('\n==========================================================\n');
fprintf('  SCOREBOARD                            %6.1f s total\n', R.elapsed);
fprintf('----------------------------------------------------------\n');
for k = 1:8
    if skipped(k), mark = 'SKIP'; elseif res(k), mark = 'PASS'; else, mark = 'FAIL'; end
    fprintf('  gate %d  [%s]  %s\n', k, mark, names{k});
end
fprintf('----------------------------------------------------------\n');
fprintf('  figure : %s\n', R.qcFigure);
fprintf('  data   : %s\n', R.matFile);
if all(res)
    fprintf('\n  All gates pass. Look at panels A, E and F before scaling up.\n');
else
    fprintf('\n  Not every gate passed. Read the output above before scaling up.\n');
end
fprintf('==========================================================\n\n');
R.allPassed = all(res);
end


% =======================================================================
function localHard(pass, n)
if ~pass
    error('RunBeta:gate%d', ...
        ['Gate %d failed. This one means the code is wrong, not the data. ' ...
         'Fix it before going further.'], n);
end
end


% =======================================================================
function localPrintParams(P)
fprintf('  epoch        %g s, %d phase bins\n', P.epochSec, P.nbin);
fprintf('  slow (phase) %g:%g:%g Hz, bandwidth %g  -> %d bands\n', ...
        P.slowVec(1), P.slowVec(2)-P.slowVec(1), P.slowVec(end), P.slowBW, P.nSlow);
fprintf('  fast (amp)   %g:%g:%g Hz, bandwidth %g  -> %d bands\n', ...
        P.fastVec(1), P.fastVec(2)-P.fastVec(1), P.fastVec(end), P.fastBW, P.nFast);
fprintf('  surrogates   %d, minimum shift %g s, seed %d\n', P.nSurr, P.minShiftSec, P.seed);
fprintf('  notch        %g-%g Hz, decimation /%d\n\n', P.notch(1), P.notch(2), P.downsample);
end
