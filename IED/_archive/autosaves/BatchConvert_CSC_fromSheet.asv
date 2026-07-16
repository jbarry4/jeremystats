function BatchConvert_CSC_fromSheet(sheetPath, baseRoot, outRoot, varargin)
% BatchConvert_CSC_fromSheet
% Reads a sheet listing mouse/session rows, finds folders whose NAMES contain
% "m<digits>" and "s<digits>" ANYWHERE (case-insensitive), converts CSC*.ncs
% to LLspikedetector-ready MATs in microvolts, and mirrors the source path
% under outRoot.
%
% Required:
%   sheetPath : .xlsx or .csv with columns like mouse_id, session, (group optional), bad channel
%   baseRoot  : top-level folder to scan (recursively)
%   outRoot   : destination top-level folder (mirrors relative path)
%
% Options (Name,Value):
%   'nTotalCh'     (64)   total channel count available on disk
%   'storeClass'   ('single') 'single'|'double'
%   'reqsPath'     ('./reqsPath') location of Nlx2MatCSC MEX if not on path
%   'fallbackADBV' (6.103515625e-8) volts/AD if header missing ADBitVolts
%   'dryRun'       (false) don’t write files, just print actions
%   'verbose'      (true)
%   'maxDepth'     (Inf)   optional depth limit for directory scanning
%
% Example:
% BatchConvert_CSC_fromSheet( ...
%   'C:\path\to\samples.xlsx', ...
%   'D:\NeuralynxRaw', ...
%   'E:\LL_ready_outputs', ...
%   'nTotalCh', 64, 'storeClass', 'single', ...
%   'reqsPath', 'C:\path\to\NeuralynxMex', ...
%   'dryRun', false, 'verbose', true, 'maxDepth', Inf);

% ---------- Parse args ----------
ip = inputParser;
ip.addRequired('sheetPath', @(s)ischar(s)||isstring(s));
ip.addRequired('baseRoot',  @(s)ischar(s)||isstring(s));
ip.addRequired('outRoot',   @(s)ischar(s)||isstring(s));
ip.addParameter('nTotalCh', 64, @(x)isnumeric(x)&&isscalar(x)&&x>=1);
ip.addParameter('storeClass','single', @(s)ischar(s)||isstring(s));
ip.addParameter('reqsPath', fullfile(fileparts(mfilename('fullpath')),'reqsPath'), @(s)ischar(s)||isstring(s));
ip.addParameter('fallbackADBV', 0.00000006103515625, @(x)isfinite(x)&&x>0);
ip.addParameter('dryRun', false, @(x)islogical(x)||ismember(x,[0 1]));
ip.addParameter('verbose', true, @(x)islogical(x)||ismember(x,[0 1]));
ip.addParameter('maxDepth', Inf, @(x)isfinite(x)&&x>=1);
ip.parse(sheetPath, baseRoot, outRoot, varargin{:});
opts = ip.Results;
baseRoot = char(baseRoot);
outRoot  = char(outRoot);
if ~isfolder(baseRoot), error('Base folder not found: %s', baseRoot); end
if ~isfolder(outRoot),  mkdir(outRoot); end

% ---------- Load sheet ----------
T = readtable(sheetPath);
cn = lower(regexprep(string(T.Properties.VariableNames), '\s+', ''));
T.Properties.VariableNames = cellstr(cn);
col_mouse = find(ismember(cn, ["mouse_id","mouse","mouseid","animal","subject"]), 1);
col_sess  = find(ismember(cn, ["session","sess"]), 1);
col_bad   = find(ismember(cn, ["badchannel","badchannels","bad_channel","bad_channels","bad"]), 1);
if isempty(col_mouse) || isempty(col_sess)
    error('Sheet needs at least "mouse_id" and "session" columns.');
end

for r = 1:height(T)
    mouse_id_raw = string(T{r, col_mouse});
    sess_raw     = T{r, col_sess};
    bad_raw      = ""; if ~isempty(col_bad), bad_raw = string(T{r, col_bad}); end

    % Parse mouse number: accept "m61", "M061", etc. anywhere in cell
    mdig = regexp(lower(strtrim(mouse_id_raw)), 'm\s*0*(\d+)', 'tokens', 'once');
    if isempty(mdig), warning('Row %d: cannot parse mouse_id "%s". Skipping.', r, mouse_id_raw); continue; end
    mouseNum = str2double(mdig{1});

    % Parse session: accept numeric or text with s##
    if ischar(sess_raw) || isstring(sess_raw)
        sdig = regexp(lower(string(sess_raw)), 's\s*0*(\d+)', 'tokens', 'once');
        if isempty(sdig), sdig = regexp(lower(string(sess_raw)), '0*(\d+)', 'tokens', 'once'); end
        if isempty(sdig), warning('Row %d: cannot parse session "%s". Skipping.', r, string(sess_raw)); continue; end
        sessNum = str2double(sdig{1});
    else
        sessNum = double(sess_raw);
    end

    % Bad channel list
    badList = [];
    if strlength(strtrim(bad_raw))>0
        toks = regexp(char(bad_raw), '\d+', 'match');
        badList = unique(str2double(toks));
    end

    if opts.verbose
        fprintf('\n[%3d/%3d] m%d | s%d | badList=%s\n', r, height(T), mouseNum, sessNum, mat2str(badList));
    end

    % ---------- Find ANY folder whose NAME contains "m<mouseNum>" anywhere ----------
    mousePat  = sprintf('m0*%d(?!\\d)', mouseNum);
    mouseHits = findDirsNameContainsRegex(baseRoot, mousePat, opts.maxDepth);
    if isempty(mouseHits)
        warning('  m%d not found anywhere under baseRoot.', mouseNum);
        continue;
    end
    % Prefer the shallowest path (closest to baseRoot)
    depths = cellfun(@(p) numel(strfind(p, filesep)), mouseHits);
    [~, ix] = sort(depths, 'ascend');
    mouseHits = mouseHits(ix);

    % ---------- Inside that mouse path, find ANY folder name containing "s<sessNum>" ----------
    sessPat = sprintf('s0*%d(?!\\d)', sessNum);
    sessHits = findDirsNameContainsRegex(mouseHits{1}, sessPat, opts.maxDepth);
    if isempty(sessHits)
        warning('  s%d not found under mouse path: %s', sessNum, mouseHits{1});
        continue;
    end

    % ---------- Under each session hit, find leaf dirs that contain CSC*.ncs ----------
    recDirs = {};
    for s = 1:numel(sessHits)
        cscFiles = dir(fullfile(sessHits{s}, '**', 'CSC*.ncs'));
        if ~isempty(cscFiles)
            parents = unique(cellfun(@fileparts, ...
                fullfile({cscFiles.folder}, {cscFiles.name}), 'UniformOutput', false));
            recDirs = [recDirs, parents]; %#ok<AGROW>
        end
    end
    recDirs = unique(recDirs);
    if isempty(recDirs)
        warning('  No CSC*.ncs found under session path(s).');
        continue;
    end

    % ---------- Build keep set: evens; replace even bads with odd neighbor ----------
    keep = 2:2:opts.nTotalCh;
    badEven = intersect(keep, badList);
    replacements = [];
    for k = 1:numel(badEven)
        be  = badEven(k);
        rep = be + 1;
        if rep > opts.nTotalCh, rep = be - 1; end
        % Remove the bad even
        keep(keep == be) = [];
        % Add replacement odd only if it's in range (fix scalar logical issue)
        if all([rep >= 1, rep <= opts.nTotalCh])
            keep = unique([keep, rep]); %#ok<AGROW>
            replacements(end+1, :) = [be, rep]; %#ok<AGROW>
        else
            warning('  Cannot replace even ch %d: neighbor out of range.', be);
        end
    end
    if opts.verbose
        if ~isempty(replacements)
            fprintf('  Replace even→odd: %s\n', mat2str(replacements));
        end
        fprintf('  Keep (%d): %s ...\n', numel(keep), mat2str(keep(1:min(12,end))));
    end

    % ---------- Convert each recording folder; mirror path under outRoot ----------
    for d = 1:numel(recDirs)
        srcDir  = recDirs{d};
        relPath = pathRelativeTo(srcDir, baseRoot);
        dstDir  = fullfile(outRoot, relPath);

        % compute the exact output .mat path this folder would produce
        [~, leaf] = fileparts(srcDir);
        outFull   = fullfile(dstDir, sprintf('LL_input_%s_uV.mat', leaf));

        % If already processed, report and skip
        if exist(outFull, 'file')
            fprintf('  Skipping (already processed): %s\n             → %s\n', srcDir, outFull);
            continue;
        end

        if ~isfolder(dstDir), mkdir(dstDir); end

        if opts.dryRun
            fprintf('  [dry-run] %s\n           → %s\n', srcDir, outFull);
            continue;
        end

        try
            convertFolderToLL_uV(srcDir, dstDir, keep, opts);
        catch ME
            warning('  Conversion failed for %s: %s', srcDir, ME.message);
        end
    end
end

fprintf('\nAll rows processed.\n');
end % ===== main =====


% ===== Helper: BFS find subdirs whose NAME regex-matches ANYWHERE (case-insensitive) =====
function hits = findDirsNameContainsRegex(rootDir, nameRegex, maxDepth)
    hits = {};
    q = {rootDir};
    depth = containers.Map({rootDir}, {0});
    while ~isempty(q)
        d = q{1}; q(1) = [];
        curDepth = depth(d);
        dd = dir(d);
        dd = dd([dd.isdir] & ~startsWith({dd.name}, '.'));
        for k = 1:numel(dd)
            sub = fullfile(d, dd(k).name);
            if ~isKey(depth, sub)
                depth(sub) = curDepth + 1;
            end
            % MATCH ANYWHERE in folder name (no boundary requirement before the token)
            if ~isempty(regexpi(dd(k).name, nameRegex))
                hits{end+1} = sub; %#ok<AGROW>
            end
            if depth(sub) < maxDepth
                q{end+1} = sub; %#ok<AGROW>
            end
        end
    end
    hits = unique(hits);
end

% ===== Helper: relative path from root to path (case-insensitive) =====
function rel = pathRelativeTo(p, root)
    % Canonicalize (case-insensitive handling on Windows/macOS)
    pObj    = java.io.File(p);
    rootObj = java.io.File(root);
    try
        pCan    = char(pObj.getCanonicalPath());
        rootCan = char(rootObj.getCanonicalPath());
    catch
        pCan    = char(pObj.getAbsolutePath());
        rootCan = char(rootObj.getAbsolutePath());
    end
    if strncmpi(pCan, [rootCan filesep], length(rootCan)+1)
        rel = pCan(length(rootCan)+2:end);
    elseif strcmpi(pCan, rootCan)
        rel = '';
    else
        % Fallback: anchored removal
        pat = ['^', regexptranslate('escape', [rootCan filesep])];
        rel = regexprep(pCan, pat, '', 'ignorecase');
        if strcmp(rel, pCan), rel = pCan; end
    end
end

% ===== Engine: convert one folder of CSC*.ncs → LL-ready µV MAT under dstDir =====
function convertFolderToLL_uV(basePath, outDir, keep, opts)
    % Ensure MEX is available
    if isfolder(opts.reqsPath), addpath(opts.reqsPath); end
    rehash toolboxcache; clear mex;
    nlxPaths = which('-all','Nlx2MatCSC');
    if isempty(nlxPaths)
        error('Nlx2MatCSC not found. Put Nlx2MatCSC.%s in reqsPath or on the path.', mexext);
    end
    if ~any(endsWith(string(nlxPaths), ['.',mexext], 'IgnoreCase',true))
        error('Nlx2MatCSC.%s (MEX) must be ahead of Nlx2MatCSC.m on the path.', mexext);
    end

    [~, leaf] = fileparts(basePath);
    outFull   = fullfile(outDir, sprintf('LL_input_%s_uV.mat', leaf));

    % Defensive skip inside converter too
    if exist(outFull, 'file')
        fprintf('    Skipping (already exists): %s\n', outFull);
        return;
    end

    nTotalCh     = opts.nTotalCh;
    storeClass   = char(opts.storeClass);
    fallbackADBV = opts.fallbackADBV;
    verbose      = opts.verbose;

    if isempty(dir(fullfile(basePath, 'CSC*.ncs')))
        error('No CSC*.ncs in %s', basePath);
    end

    allCh = 1:nTotalCh;
    kept_channels = intersect(allCh, unique(keep(:)'));
    if isempty(kept_channels)
        error('No channels to keep after replacement.');
    end
    nKept = numel(kept_channels);
    if verbose
        fprintf('  Converting: %s\n', basePath);
        fprintf('  Output   : %s\n', outFull);
        fprintf('  Kept (%d): %s ...\n', nKept, mat2str(kept_channels(1:min(12,end))));
    end

    % ----- First pass -----
    FS = [1 1 1 1 1]; EH = 1; EM = 1;
    headersCell  = cell(1, nKept);
    sfxArr       = nan(1, nKept);
    lenArr       = nan(1, nKept);
    badch_full   = false(1, nTotalCh);
    fileListKept = strings(1, nKept);
    ADBitVoltsK  = nan(1, nKept);

    fprintf('    First pass (sizes, sfx, ADBitVolts)\n');
    for i = 1:nKept
        ch = kept_channels(i);
        fname = fullfile(basePath, sprintf('CSC%d.ncs', ch));
        fileListKept(i) = string(fname);
        if ~isfile(fname)
            warning('    Missing %s (ch %d).', fname, ch);
            badch_full(ch) = true; lenArr(i)=0; headersCell{i}={}; continue;
        end
        try
            [Timestamps, ~, SampleFrequencies, NValid, Samples, Header] = ...
                Nlx2MatCSC(fname, FS, EH, EM, []);
            blkN = size(Samples,1);
            nv   = min(blkN, max(0, NValid(:)'));
            lenArr(i) = sum(nv);
%%% MAKE IT SINGLE, SO IT'S NOT SO HUGE.
            sfxCh = mode(double(SampleFrequencies(SampleFrequencies>0)));
            if ~(isfinite(sfxCh) && sfxCh>0)
                sfLine = Header(contains(Header,'SamplingFrequency','IgnoreCase',true));
                if ~isempty(sfLine)
                    tok = regexp(sfLine{1}, 'SamplingFrequency[^0-9eE.\-]*([\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?)', 'tokens', 'once');
                    if ~isempty(tok), sfxCh = str2double(tok{1}); end
                end
            end
            sfxArr(i) = sfxCh;

            ADBV = NaN;
            k = find(contains(Header,'ADBitVolts','IgnoreCase',true),1,'first');
            if ~isempty(k)
                tok = regexp(Header{k}, 'ADBitVolts[^0-9eE.\-]*([\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?)', 'tokens', 'once');
                if ~isempty(tok), ADBV = str2double(tok{1}); end
            end
            if ~(isfinite(ADBV) && ADBV>0)
                ADBV = fallbackADBV;
                warning('    ADBitVolts missing for CSC%d; fallback %.12g V/AD', ch, ADBV);
            end
            ADBitVoltsK(i) = ADBV;
            headersCell{i} = Header;

            if verbose
                fprintf('      CSC%-2d: %10d @ %g Hz | ADBitVolts %.12g\n', ch, lenArr(i), sfxArr(i), ADBV);
            end

            if ~isempty(Timestamps) && isfinite(sfxCh) && sfxCh>0
                expectedStep_us = 512*(1e6/sfxCh);
                dt = diff(double(Timestamps));
                if any(abs(dt - expectedStep_us) > 0.5*expectedStep_us)
                    warning('    Timing irregularity CSC%d (gaps not interpolated).', ch);
                end
            end
        catch ME
            warning('    Read failure %s (ch %d): %s', fname, ch, ME.message);
            badch_full(ch)=true; lenArr(i)=0; headersCell{i}={}; sfxArr(i)=NaN; ADBitVoltsK(i)=NaN;
        end
    end

    good = (lenArr>0) & isfinite(sfxArr) & sfxArr>0;
    if ~any(good), error('    No valid channels / sampling frequency.'); end
    sfx = mode(round(sfxArr(good)));

    % ----- Disk-backed target -----
    maxN = max(lenArr(good));
    if exist(outFull,'file')
        fprintf('    Skipping (already exists): %s\n', outFull);
        return;
    end
    mf = matfile(outFull,'Writable',true);
    switch lower(storeClass)
        case 'single', mf.d = single(NaN(nKept, maxN));
        case 'double', mf.d = NaN(nKept, maxN);
        otherwise, error('storeClass must be ''single'' or ''double''.');
    end

    mf.sfx           = sfx;
    mf.badch         = badch_full;
    mf.chan_labels   = arrayfun(@(k) sprintf('CSC%d', k), 1:nTotalCh, 'UniformOutput', false);
    mf.kept_channels = kept_channels;
    mf.headersCell   = headersCell;
    mf.units         = 'microvolts';
    meta.sourcePath   = basePath;
    meta.savePath     = outDir;
    meta.createdOn    = datestr(now);
    meta.nTotalCh     = nTotalCh;
    meta.nKept        = nKept;
    meta.reader       = ['Nlx2MatCSC (', mexext, ')'];
    meta.storeClass   = storeClass;
    meta.note         = 'Disk-backed; NaN-padded; per-channel AD→µV scaling during write.';
    meta.fileListKept = fileListKept;
    meta.ADBitVolts   = ADBitVoltsK;
    meta.scaleFactor  = ADBitVoltsK*1e6; % µV/AD
    mf.meta = meta;

    % ----- Second pass -----
    fprintf('    Second pass (write µV)\n');
    t0 = tic;
    for i = 1:nKept
        ch = kept_channels(i);
        if badch_full(ch) || lenArr(i)==0
            fprintf('      CSC%-2d: skipped\n', ch); continue;
        end
        fname = fullfile(basePath, sprintf('CSC%d.ncs', ch));
        [~, ~, ~, NValid, Samples] = Nlx2MatCSC(fname, [1 1 1 1 1], 0, 1, []);
        blkN = size(Samples,1); nRec = size(Samples,2);
        x = nan(1, lenArr(i)); pos = 1;
        for r = 1:nRec
            nv = min(blkN, max(0, NValid(r)));
            if nv>0
                x(pos:pos+nv-1) = double(Samples(1:nv, r));
                pos = pos + nv;
            end
        end
        sf_uV = ADBitVoltsK(i)*1e6; if ~(isfinite(sf_uV)&&sf_uV>0), sf_uV = opts.fallbackADBV*1e6; end
        x = x * sf_uV;
        switch lower(storeClass)
            case 'single', x = single(x);
            case 'double', x = double(x);
        end
        mf.d(i,1:numel(x)) = x;

        if mod(i,2)==0 || i==nKept
            fprintf('      [%3d/%3d] CSC%-2d | %.1f%% | %s\n', ...
                i, nKept, ch, 100*i/nKept, duration(0,0,toc(t0),"Format","mm:ss"));
        end
    end
    fprintf('    Saved: %s\n', outFull);
end
