function outFile = SaveChannel(outDir, tag, sig, ep, cfc, Pw, P)
%SAVECHANNEL  One .mat that stands on its own.
%
%   outFile = SaveChannel(outDir, tag, sig, ep, cfc, Pw, P)
%
%   Gate 8 is the test of this function: open a fresh MATLAB session, load
%   ONLY this file, and redraw the mean comodulogram. If you need anything
%   that is not in the file, the file is incomplete -- and the time to find
%   that out is now, not at channel 64.
%
%   So this deliberately stores the axes as numbers rather than leaving them
%   to be recomputed from params, keeps the epoch table, and records where
%   the data came from and which commit produced it.
%
%   The filter banks are NOT stored: 1.7 GB per channel, and they are
%   reproducible from the source file plus params.

if ~isfolder(outDir), mkdir(outDir); end

R = struct();

% --- the results ---------------------------------------------------------
R.MI          = cfc.MI;                 % nSlow x nFast x nEp
R.z           = cfc.z;
R.p           = cfc.p;                  % use THIS for significance, not z --
                                        % see gate 6: z is over-dispersed
R.surrMean    = cfc.surrMean;
R.surrSD      = cfc.surrSD;
R.surrMode    = cfc.surrMode;
R.nSurr       = cfc.nSurr;
R.power       = Pw;                     % nSlow x nEp
R.epochs      = ep;

% --- the axes, so nothing has to be recomputed to plot -------------------
R.slowCenters = P.slowCenters(:);       % Hz, what MI is plotted against
R.fastCenters = P.fastCenters(:);
R.epochTime   = ep.t0 + (ep.t1 - ep.t0)/2;
R.dims        = 'MI is [slow x fast x epoch]';

% --- provenance ----------------------------------------------------------
R.params      = P;
R.sourcePath  = sig.path;
R.fs          = sig.fs;
R.nSamples    = sig.T;
R.durSec      = sig.durSec;
R.gaps        = sig.gaps;
R.clipRuns    = sig.clipRuns;
R.clipFrac    = sig.clipFrac;
R.gitHash     = localGitHash();
R.matlab      = version();
R.host        = localHost();
R.createdAt   = datetime('now');
R.code        = fileparts(mfilename('fullpath'));

outFile = fullfile(outDir, sprintf('%s_cfc.mat', tag));
save(outFile, '-struct', 'R', '-v7.3');

d = dir(outFile);
fprintf('SaveChannel: %s  (%.1f MB)\n', outFile, d.bytes/1e6);
fprintf('   git %s   matlab %s\n', R.gitHash, R.matlab);
end


% =======================================================================
function h = localGitHash()
h = 'unknown';
try
    here = fileparts(mfilename('fullpath'));
    [st, out] = system(sprintf('git -C "%s" rev-parse --short HEAD', here));
    if st == 0
        h = strtrim(out);
        [~, dirty] = system(sprintf('git -C "%s" status --porcelain', here));
        if ~isempty(strtrim(dirty)), h = [h '-dirty']; end
    end
catch
end
end


% =======================================================================
function h = localHost()
h = 'unknown';
try
    if ispc, h = getenv('COMPUTERNAME'); else, [~, h] = system('hostname'); end
    h = strtrim(h);
catch
end
end
