function CSC2LL_uV_mex_disk(basePath, varargin)
% CSC2LL_uV_mex_disk(basePath, Name,Value,...)
% Convert a folder of Neuralynx CSC#.ncs → LLspikedetector-ready .mat (disk-backed) in MICROVOLTS.
%
% REQUIRED:
%   basePath   : folder that contains CSC#.ncs files (e.g., CSC1.ncs..CSC64.ncs)
%
% OPTIONS (Name,Value):
%   'nTotalCh'    (default 64)      : total channels expected (1..nTotalCh)
%   'evenOnly'    (default true)    : keep only even channels (2,4,6,...) if true
%   'keep'        (default [])      : explicit list of channels to keep (overrides evenOnly)
%   'storeClass'  (default 'single'): 'single' or 'double' for saved data
%   'outName'     (default auto)    : output MAT filename (placed in basePath)
%   'fallbackADBV'(default 0.00000006103515625) : V/AD used if header lacks ADBitVolts
%   'reqsPath'    (default ./reqsPath): folder containing Nlx2MatCSC MEX if not already on path
%
% OUTPUT .mat (disk-backed; saved in basePath):
%   d              : [nKept x maxN] MICROVOLTS (µV), NaN-padded
%   sfx            : unified sampling rate (Hz), mode across good kept channels
%   badch          : logical(1,nTotalCh), marks missing/bad (original indexing)
%   chan_labels    : {'CSC1'..'CSCn'}
%   kept_channels  : channels written
%   headersCell    : header lines for each kept channel
%   units          : 'microvolts'
%   meta           : provenance (fileListKept, ADBitVolts per kept ch, etc.)
%
% USAGE:
%   CSC2LL_uV_mex_disk('C:\data\AnimalX\2023-08-01_12-11-26');
%   CSC2LL_uV_mex_disk('C:\data\Rec', 'nTotalCh', 32, 'evenOnly', false, 'keep', [1 3 5], 'storeClass','double');

% ---------- Parse inputs ----------
ip = inputParser;
ip.addRequired('basePath', @(s)ischar(s)||isstring(s));
ip.addParameter('nTotalCh', 64, @(x)isnumeric(x)&&isscalar(x)&&x>=1);
ip.addParameter('evenOnly', true, @(x)islogical(x)||ismember(x,[0,1]));
ip.addParameter('keep', [], @(v)isnumeric(v)&&isvector(v)&&all(v>=1));
ip.addParameter('storeClass', 'single', @(s)ischar(s)||isstring(s));
ip.addParameter('outName', '', @(s)ischar(s)||isstring(s));
ip.addParameter('fallbackADBV', 0.00000006103515625, @(x)isfinite(x)&&x>0); % V/AD
ip.addParameter('reqsPath', fullfile(fileparts(mfilename('fullpath')), 'reqsPath'), @(s)ischar(s)||isstring(s));
ip.parse(basePath, varargin{:});

basePath     = char(ip.Results.basePath);
nTotalCh     = ip.Results.nTotalCh;
evenOnly     = logical(ip.Results.evenOnly);
keep         = ip.Results.keep;
storeClass   = char(ip.Results.storeClass);
outName      = char(ip.Results.outName);
fallbackADBV = ip.Results.fallbackADBV;
reqsPath     = char(ip.Results.reqsPath);

if ~isfolder(basePath)
    error('Base folder not found: %s', basePath);
end

% ---------- PATH & MEX checks ----------
if isfolder(reqsPath), addpath(reqsPath); end
rehash toolboxcache; clear mex;
nlxPaths = which('-all','Nlx2MatCSC');
if isempty(nlxPaths)
    error('Nlx2MatCSC not found. Put Nlx2MatCSC.%s in reqsPath or add its folder to path.', mexext);
end
if ~any(endsWith(string(nlxPaths), ['.',mexext], 'IgnoreCase',true))
    error('Only Nlx2MatCSC.m is visible. Ensure Nlx2MatCSC.%s (MEX) is earlier on the path.', mexext);
end
fprintf('Using Nlx2MatCSC found at:\n'); disp(nlxPaths(:));

% ---------- Channel selection ----------
allCh = 1:nTotalCh;
if ~isempty(keep)
    kept_channels = intersect(allCh, unique(keep(:)'));
elseif evenOnly
    kept_channels = allCh(mod(allCh,2)==0); % 2,4,6,...
else
    kept_channels = allCh;                   % 1..nTotalCh
end
nKept = numel(kept_channels);
if nKept==0, error('No channels selected to keep.'); end

fprintf('Channels to include: %d of %d\n', nKept, nTotalCh);
fprintf('First few: %s\n', mat2str(kept_channels(1:min(10,nKept))));

% ---------- Auto output name if empty ----------
if isempty(strtrim(outName))
    [~, tail] = fileparts(basePath);
    outName = sprintf('LL_input_%s_mex_disk_uV.mat', tail);
end
outFull = fullfile(basePath, outName);

% ---------- First pass: sizes, sfx, ADBV ----------
FS = [1 1 1 1 1];  EH = 1;  EM = 1;
fileListKept = strings(1, nKept);
headersCell  = cell(1, nKept);
sfxArr       = nan(1, nKept);
lenArr       = nan(1, nKept);
badch_full   = false(1, nTotalCh);
ADBitVoltsK  = nan(1, nKept);

fprintf('\nFirst pass: scan files, sizes, sampling rates, ADBitVolts\n');
for i = 1:nKept
    ch    = kept_channels(i);
    fname = fullfile(basePath, sprintf('CSC%d.ncs', ch));
    fileListKept(i) = string(fname);

    if ~isfile(fname)
        warning('Missing file: %s (ch %d). Marking bad.', fname, ch);
        badch_full(ch) = true;
        lenArr(i) = 0;
        headersCell{i} = {};
        continue;
    end

    try
        [Timestamps, ~, SampleFrequencies, NValid, Samples, Header] = ...
            Nlx2MatCSC(fname, FS, EH, EM, []);

        % Effective flattened length honoring NValid
        blkN = size(Samples,1);             % usually 512
        nv   = min(blkN, max(0, NValid(:)'));
        lenArr(i) = sum(nv);

        % Sampling frequency: modal per-record; header fallback
        sfxCh = mode(double(SampleFrequencies(SampleFrequencies>0)));
        if ~(isfinite(sfxCh) && sfxCh>0)
            sfLine = Header(contains(Header,'SamplingFrequency','IgnoreCase',true));
            if ~isempty(sfLine)
                tok = regexp(sfLine{1}, 'SamplingFrequency[^0-9eE.\-]*([\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?)', 'tokens', 'once');
                if ~isempty(tok), sfxCh = str2double(tok{1}); end
            end
        end
        sfxArr(i) = sfxCh;

        % ADBitVolts (V/AD)
        ADBV = NaN;
        k = find(contains(Header,'ADBitVolts','IgnoreCase',true),1,'first');
        if ~isempty(k)
            tok = regexp(Header{k}, 'ADBitVolts[^0-9eE.\-]*([\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?)', 'tokens', 'once');
            if ~isempty(tok), ADBV = str2double(tok{1}); end
        end
        if ~(isfinite(ADBV) && ADBV>0)
            ADBV = fallbackADBV;
            warning('ADBitVolts missing for CSC%d; using fallback %.12g V/AD', ch, ADBV);
        end
        ADBitVoltsK(i) = ADBV;

        headersCell{i} = Header;

        fprintf('  CSC%-2d: %10d samples eff @ %g Hz | ADBitVolts=%.12g V/AD\n', ...
            ch, lenArr(i), sfxArr(i), ADBV);

        % Optional continuity check
        if ~isempty(Timestamps) && isfinite(sfxCh) && sfxCh>0
            expectedStep_us = 512 * (1e6 / sfxCh);
            dt = diff(double(Timestamps));
            if any(abs(dt - expectedStep_us) > 0.5 * expectedStep_us)
                warning('Timing irregularity in %s (ch %d). Gaps not interpolated.', fname, ch);
            end
        end

    catch ME
        warning('Read failure %s (ch %d): %s. Marking bad.', fname, ch, ME.message);
        badch_full(ch) = true;
        lenArr(i)      = 0; 
        headersCell{i} = {}; 
        sfxArr(i)      = NaN; 
        ADBitVoltsK(i) = NaN;
    end
end

% ---------- Unified sfx ----------
good = (lenArr>0) & isfinite(sfxArr) & sfxArr>0;
if ~any(good)
    error('No valid channels found / no sampling frequency could be determined.');
end
sfx = mode(round(sfxArr(good)));

% ---------- Prepare disk-backed target ----------
maxN = max(lenArr(good));
bytesPer = strcmpi(storeClass,'single')*4 + strcmpi(storeClass,'double')*8;
approxGB = (nKept*maxN*bytesPer)/1e9;
fprintf('\nCreating disk-backed array: %d x %d (%s) ~ %.2f GB on disk\n', nKept, maxN, storeClass, approxGB);

if exist(outFull, 'file')
    delete(outFull); % clean new file
end
mf = matfile(outFull, 'Writable', true);

switch lower(storeClass)
    case 'single', mf.d = single(NaN(nKept, maxN));
    case 'double', mf.d = NaN(nKept, maxN);
    otherwise, error('storeClass must be ''single'' or ''double''.');
end

% Save meta first so partial files are still useful
mf.sfx           = sfx;
mf.badch         = badch_full;
mf.chan_labels   = arrayfun(@(k) sprintf('CSC%d', k), 1:nTotalCh, 'UniformOutput', false);
mf.kept_channels = kept_channels;
mf.headersCell   = headersCell;
mf.units         = 'microvolts';
meta.basePath     = basePath;
meta.createdOn    = datestr(now);
meta.nTotalCh     = nTotalCh;
meta.nKept        = nKept;
meta.reader       = ['Nlx2MatCSC (', mexext, ')'];
meta.storeClass   = storeClass;
meta.note         = 'Disk-backed; NaN-padded; per-channel AD→µV scaling during write.';
meta.fileListKept = fileListKept;
meta.ADBitVolts   = ADBitVoltsK;           % V/AD used per kept channel
meta.scaleFactor  = ADBitVoltsK * 1e6;     % µV/AD per kept channel
mf.meta = meta;

% ---------- Second pass: read, flatten (NValid), SCALE to µV, write ----------
fprintf('\nSecond pass: writing MICROVOLT data to disk (progress below)\n');
t0 = tic;
for i = 1:nKept
    ch = kept_channels(i);
    if badch_full(ch) || lenArr(i)==0
        fprintf('  CSC%-2d: skipped (bad/missing)\n', ch);
        continue;
    end

    fname = fullfile(basePath, sprintf('CSC%d.ncs', ch));
    [~, ~, ~, NValid, Samples] = Nlx2MatCSC(fname, [1 1 1 1 1], 0, 1, []); % no header now

    blkN = size(Samples,1);
    nRec = size(Samples,2);
    x    = nan(1, lenArr(i)); % AD units
    pos  = 1;
    for r = 1:nRec
        nv = min(blkN, max(0, NValid(r)));
        if nv>0
            x(pos:pos+nv-1) = double(Samples(1:nv, r));
            pos = pos + nv;
        end
    end

    % Scale to microvolts for this channel
    sf_uV = ADBitVoltsK(i) * 1e6; % µV/AD
    if ~(isfinite(sf_uV) && sf_uV>0), sf_uV = fallbackADBV * 1e6; end
    x = x * sf_uV;

    % Cast + write
    switch lower(storeClass)
        case 'single', x = single(x);
        case 'double', x = double(x);
    end
    mf.d(i, 1:numel(x)) = x;

    if mod(i,2)==0 || i==nKept
        elapsed = toc(t0);
        fprintf('  [%3d/%3d] CSC%-2d written | %.1f%% | elapsed %s\n', ...
            i, nKept, ch, 100*i/nKept, duration(0,0,elapsed,"Format","mm:ss"));
    end
end

fprintf('\nDone.\nSaved LL-ready (µV) file:\n  %s\n', outFull);
fprintf('Quick check:\n  m = matfile(''%s''); size(m,''d''), m.units, m.sfx\n', outFull);
fprintf('Run LLspikedetector (double math recommended):\n  %% [ets, ech] = LLspikedetector(double(m.d), m.sfx, 0.04, 99.9, m.badch);\n');

end
