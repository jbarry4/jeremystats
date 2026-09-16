function sig = LoadCSC(ncsPath, P)
%LOADCSC  One channel, one recording, nothing else.
%
%   sig = LoadCSC(ncsPath, P)
%
%   read_csc -> decimate by P.downsample -> mains notch -> gap and clip check.
%
%   Returns
%     sig.lfp        1 x T double, microvolts, notched
%     sig.fs         sampling rate AFTER decimation
%     sig.T          numel(lfp)
%     sig.durSec     T / fs
%     sig.path       source .ncs
%     sig.gaps       table of recording gaps found in the RAW record stamps
%     sig.clipRuns   number of flat runs (>= 3 identical consecutive samples)
%     sig.clipFrac   fraction of samples inside such a run
%
%   Two things worth knowing about read_csc, both pre-existing and both left
%   alone so this stays comparable with newFCSE.m (gate 5):
%
%   1. It decimates with Samples(1:D:end) and NO anti-alias filter. Content
%      above the new Nyquist (~1628 Hz) folds down into the band we analyse.
%      For the 20-200 Hz amplitude axis this is a real but historical risk.
%   2. It overwrites the true per-record timestamps with a uniform grid, so
%      gaps cannot be seen in its TS output. This function re-reads the raw
%      record stamps itself to check.

if nargin < 2, P = params(); end

assert(isfile(ncsPath), 'LoadCSC:noFile', 'No such file: %s', ncsPath);

% ---- raw record timestamps, before read_csc flattens them --------------
[recTS, hdrFs] = localRecordStamps(ncsPath);

% ---- the lab's reader --------------------------------------------------
[~, SF, ~, Samples] = read_csc(ncsPath, P.downsample);

lfp = double(Samples(:)).';        % 1 x T, microvolts
T   = numel(lfp);

% ---- mains notch (same design as newFCSE.m) ----------------------------
d = designfilt('bandstopiir', 'FilterOrder', P.notchOrder, ...
        'HalfPowerFrequency1', P.notch(1), ...
        'HalfPowerFrequency2', P.notch(2), ...
        'DesignMethod', 'butter', 'SampleRate', SF);
lfp = filtfilt(d, lfp')';

% ---- gap check on the RAW stamps ---------------------------------------
% Neuralynx writes one timestamp per 512-sample record. A clean recording
% has a constant inter-record interval.
gaps = table();
if numel(recTS) > 2
    dt      = diff(double(recTS));          % microseconds between records
    nominal = median(dt);
    bad     = find(abs(dt - nominal) > 0.5 * nominal);
    if ~isempty(bad)
        gaps = table(bad(:), double(recTS(bad))', dt(bad)'/1e6, ...
              'VariableNames', {'afterRecord', 'tsUs', 'gapSec'});
    end
end

% ---- clip / dropout check ----------------------------------------------
% A rail-clipped or dropped segment shows up as identical consecutive
% samples. Real LFP essentially never repeats a value three times running.
[nRuns, fracInRun] = localFlatRuns(lfp, 3);

sig = struct();
sig.lfp      = lfp;
sig.fs       = SF;
sig.T        = T;
sig.durSec   = T / SF;
sig.path     = ncsPath;
sig.headerFs = hdrFs;
sig.gaps     = gaps;
sig.clipRuns = nRuns;
sig.clipFrac = fracInRun;
sig.loadedAt = datetime('now');

fprintf('LoadCSC: %s\n', ncsPath);
fprintf('   fs = %.4f Hz after /%d   T = %d samples   %.1f s (%.1f min)\n', ...
        SF, P.downsample, T, sig.durSec, sig.durSec/60);
fprintf('   gaps found: %d      flat runs (>=3): %d  (%.4f%% of samples)\n', ...
        height(gaps), nRuns, 100*fracInRun);
end


% =======================================================================
function [ts, fs] = localRecordStamps(ncsPath)
%LOCALRECORDSTAMPS  The uint64 timestamp at the head of every 1044-byte record.
headerSz = 16384;
fid = fopen(ncsPath, 'r');
assert(fid > 0, 'LoadCSC:fopen', 'Could not open %s', ncsPath);
cleaner = onCleanup(@() fclose(fid));

hdr = fscanf(fid, '%c', headerSz);
fs  = NaN;
tok = regexp(hdr, '-SamplingFrequency\s+([\d.]+)', 'tokens', 'once');
if ~isempty(tok), fs = str2double(tok{1}); end

fseek(fid, headerSz, 'bof');
ts = fread(fid, 'uint64', 1036);   % 1044-byte record, 8 bytes of stamp
ts = ts(:).';
end


% =======================================================================
function [nRuns, fracInRun] = localFlatRuns(x, minLen)
%LOCALFLATRUNS  Count runs of >= minLen identical consecutive samples.
same = [false, diff(x) == 0];
d    = diff([0, same, 0]);
starts = find(d == 1);
stops  = find(d == -1) - 1;
runLen = (stops - starts + 1) + 1;      % +1: n equal diffs => n+1 samples
keep   = runLen >= minLen;
nRuns  = sum(keep);
fracInRun = sum(runLen(keep)) / numel(x);
end
