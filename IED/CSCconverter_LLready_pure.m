function CSCconverter_LLready_mex_disk()
% Convert Neuralynx CSC#.ncs to LLspikedetector-ready .mat using Nlx2MatCSC (MEX)
% - Disk-backed write with progress (no 14+ GB RAM allocation)
% - Option to include only even channels (2,4,6,...)
% - Stores data as 'single' (default) or 'double'
%
% Outputs inside the .mat:
%   d            : [channels x time] (disk-backed HDF5)
%   sfx          : unified sampling frequency (Hz)
%   badch        : logical(1, nTotalCh) marks bad/missing in original indexing
%   chan_labels  : cellstr for all original channels (CSC1..CSC64)
%   kept_channels: indices of channels actually written into d
%   headersCell  : headers for kept channels
%   meta         : struct with provenance

% --------- USER SETTINGS ----------
reqsPath   = fullfile(fileparts(mfilename('fullpath')), 'reqsPath'); % where Nlx2MatCSC.* lives
basePath   = 'C:\Users\info\Desktop\Barry\Data\TestIEDData\M13s2aug1\2023-08-01_12-11-26';
nTotalCh   = 64;            % expects CSC1.ncs ... CSC64.ncs
evenOnly   = true;         % <-- set true to include only even channels (2,4,6,...)
storeClass = 'single';      % 'single' (recommended) or 'double'
outName    = 'LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat';
% ----------------------------------

% --- PATH & MEX checks ---
if isfolder(reqsPath), addpath(reqsPath); end
rehash toolboxcache; clear mex;
nlxPaths = which('-all','Nlx2MatCSC');
if isempty(nlxPaths)
    error('Nlx2MatCSC not found. Place Nlx2MatCSC.%s in reqsPath or add the Neuralynx Import/Export folder to path.', mexext);
end
if ~any(endsWith(string(nlxPaths), ['.',mexext], 'IgnoreCase',true))
    error('MATLAB sees only Nlx2MatCSC.m (help). Ensure Nlx2MatCSC.%s is earlier on the path.', mexext);
end
fprintf('Using Nlx2MatCSC found at:\n'); disp(nlxPaths(:));

% --- Channel selection ---
allCh = 1:nTotalCh;
if evenOnly
    kept_channels = allCh(mod(allCh,2)==0); % 2,4,6,...
else
    kept_channels = allCh;                  % 1..nTotalCh
end
nKept = numel(kept_channels);
fprintf('Channels to include: %d of %d\n', nKept, nTotalCh);
fprintf('First few: %s\n', mat2str(kept_channels(1:min(10,nKept))));

% --- Containers for a first pass (to get lengths & sfx) ---
FS = [1 1 1 1 1];  EH = 1;  EM = 1;
fileListKept = strings(1, nKept);
headersCell  = cell(1, nKept);
sfxArr       = nan(1, nKept);
lenArr       = nan(1, nKept);
badch_full   = false(1, nTotalCh);   % marks bad/missing in original index space
ADBitVoltsK  = nan(1, nKept);

fprintf('\nFirst pass: scan files, sizes, and sampling rates\n');
for i = 1:nKept
    ch   = kept_channels(i);
    fname = fullfile(basePath, sprintf('CSC%d.ncs', ch));
    fileListKept(i) = string(fname);

    if ~isfile(fname)
        warning('Missing file: %s (ch %d). Marking bad.', fname, ch);
        badch_full(ch) = true;
        lenArr(i)      = 0;
        continue;
    end

    try
        [Timestamps, ~, SampleFrequencies, NValid, Samples, Header] = ...
            Nlx2MatCSC(fname, FS, EH, EM, []);

        % Per-record sample count → effective flattened length honoring NValid
        blkN = size(Samples,1);               % 512
        nv   = min(blkN, max(0, NValid(:)')); % row vector
        lenArr(i) = sum(nv);

        % Sampling frequency: prefer modal per-record value; fallback parse header
        sfxCh = mode(double(SampleFrequencies(SampleFrequencies>0)));
        if ~(isfinite(sfxCh) && sfxCh > 0)
            sfLine = Header(contains(Header,'SamplingFrequency','IgnoreCase',true));
            if ~isempty(sfLine)
                tok = regexp(sfLine{1}, 'SamplingFrequency[^0-9eE.\-]*([\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?)', 'tokens', 'once');
                if ~isempty(tok), sfxCh = str2double(tok{1}); end
            end
        end
        sfxArr(i) = sfxCh;

        % Parse ADBitVolts:
        ADBV = NaN;
        k = find(contains(Header,'ADBitVolts','IgnoreCase',true),1,'first');
        if ~isempty(k)
            tok = regexp(Header{k}, 'ADBitVolts[^0-9eE.\-]*([\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?)', 'tokens', 'once');
            if ~isempty(tok), ADBV = str2double(tok{1}); end
        end
        ADBitVoltsK(i) = ADBV;

        headersCell{i} = Header;

        fprintf('  CSC%-2d: %10d samples (effective) @ %g Hz\n', ch, lenArr(i), sfxArr(i));

        % Optional rough continuity check (block-to-block)
        if ~isempty(Timestamps) && isfinite(sfxCh) && sfxCh>0
            expectedStep_us = 512 * (1e6 / sfxCh);
            dt = diff(double(Timestamps));
            if any(abs(dt - expectedStep_us) > 0.5 * expectedStep_us)
                warning('Timing irregularity in %s (ch %d). Internal gaps not interpolated.', fname, ch);
            end
        end

    catch ME
        warning('Read failure %s (ch %d): %s. Marking bad.', fname, ch, ME.message);
        badch_full(ch) = true;
        lenArr(i)      = 0;
        headersCell{i} = {};
        sfxArr(i)      = NaN;
    end
end

% --- Unified sampling rate (mode across good kept channels) ---
good = (lenArr>0) & isfinite(sfxArr) & sfxArr>0;
if ~any(good)
    error('No valid channels found (or no sampling frequency could be determined).');
end
sfx = mode(round(sfxArr(good)));

% --- Final shape and disk-backed array creation ---
maxN = max(lenArr(good));
bytesPer = strcmpi(storeClass,'single')*4 + strcmpi(storeClass,'double')*8;
approxGB = (nKept*maxN*bytesPer)/1e9;
fprintf('\nCreating disk-backed array: %d x %d (%s) ~ %.2f GB on disk\n', nKept, maxN, storeClass, approxGB);

outFull = fullfile(basePath, outName);
if exist(outFull, 'file')
    delete(outFull); % ensure a clean new file
end
mf = matfile(outFull, 'Writable', true);

% Predefine 'd' on disk (this writes metadata and reserves space)
switch lower(storeClass)
    case 'single'
        mf.d = single(NaN(nKept, maxN));
    case 'double'
        mf.d = NaN(nKept, maxN);
    otherwise
        error('storeClass must be ''single'' or ''double''.');
end

% Also store placeholders; we'll fill/update after writing d
mf.sfx          = sfx;
mf.badch        = badch_full;
mf.chan_labels  = arrayfun(@(k) sprintf('CSC%d', k), 1:nTotalCh, 'UniformOutput', false);
mf.kept_channels= kept_channels;
mf.headersCell  = headersCell;   % headers only for kept channels
meta.basePath     = basePath;
meta.createdOn    = datestr(now);
meta.nTotalCh     = nTotalCh;
meta.nKept        = nKept;
meta.reader       = ['Nlx2MatCSC (', mexext, ')'];
meta.storeClass   = storeClass;
meta.note         = 'Disk-backed; NaN-padded to equalize length. No downsampling.';
meta.fileListKept = fileListKept;
meta.ADBitVolts   = ADBitVoltsK;
mf.meta = meta;

% --- Second pass: write each kept channel to disk with progress ---
fprintf('\nSecond pass: writing channel data to disk (progress below)\n');
t0 = tic;
for i = 1:nKept
    ch = kept_channels(i);
    if badch_full(ch) || lenArr(i)==0
        % leave as NaN row
        fprintf('  CSC%-2d: skipped (bad/missing)\n', ch);
        continue;
    end

    fname = fullfile(basePath, sprintf('CSC%d.ncs', ch));
    [~, ~, ~, NValid, Samples] = Nlx2MatCSC(fname, FS, 0, EM, []); % no header needed now

    % Flatten honoring NumberValidSamples
    blkN = size(Samples,1); nRec = size(Samples,2);
    x    = nan(1, lenArr(i));   % final effective length
    pos  = 1;
    for r = 1:nRec
        nv = min(blkN, max(0, NValid(r)));
        if nv>0
            x(pos:pos+nv-1) = double(Samples(1:nv, r));
            pos = pos + nv;
        end
    end

    % Cast to desired class and write to disk-backed matrix
    switch lower(storeClass)
        case 'single', x = single(x);
        case 'double', x = double(x);
    end
    mf.d(i, 1:numel(x)) = x;

    if mod(i, 2)==0 || i==nKept
        elapsed = toc(t0);
        fprintf('  [%3d/%3d] CSC%-2d written | %.1f%% | elapsed %s\n', ...
            i, nKept, ch, 100*i/nKept, duration(0,0,elapsed,"Format","mm:ss"));
    end
end

fprintf('\nDone.\nSaved LL-ready file:\n  %s\n', outFull);
fprintf('Usage examples:\n');
fprintf('  %% Load metadata only (fast):\n');
fprintf('  m = matfile(''%s''); sfx = m.sfx; kept = m.kept_channels; size(m, ''d'')\n', outFull);
fprintf('  %% If you have enough RAM and want it in memory:\n');
fprintf('  S = load(''%s'', ''d'', ''sfx'', ''badch'', ''chan_labels'', ''kept_channels'');\n', outFull);
fprintf('  %% Or work disk-backed without loading all of d:\n');
fprintf('  m = matfile(''%s''); x2 = m.d(2,:); %% read row 2 only\n', outFull);
fprintf('  %% Run LLspikedetector (prefer double math):\n');
fprintf('  %% [ets, ech] = LLspikedetector(double(m.d), m.sfx, 0.04, 99.9, m.badch);\n');

end
