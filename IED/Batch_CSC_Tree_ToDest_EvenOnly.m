function BranchRun_CSC_toDest(sheetPath, baseRoot, destRoot, varargin)
% BranchRun_CSC_toDest
% Batch-convert Neuralynx CSC#.ncs trees to LLspikedetector-ready .mat (disk-backed),
% scaling to microvolts, keeping only even targets with odd fallbacks for bad evens.
%
% Outputs mirror the source tree under destRoot/<Condition>/... and include:
%   d            : [rows x time] disk-backed (HDF5). Rows correspond to target evens (2,4,6,...) in order,
%                  but a row may be sourced from a nearby odd if the even was missing/bad.
%   sfx          : unified sampling rate (Hz)
%   badch        : logical(1, nTotalCh), original channel indices flagged bad/missing or user-bad
%   chan_labels  : {'CSC1','CSC2',...,'CSC64'}
%   kept_targets : vector of target evens (e.g., 2:2:64) actually attempted for rows
%   row_source   : [nRows x 1] actual source channel used per row (odd fallback or same even)
%   headersCell  : 1 x nRows cell, header of the *source* channel used for that row
%   meta         : struct with provenance (paths, ADBitVolts per source, mapping table, etc.)
%
% Required args:
%   sheetPath : .xlsx with columns:
%       mouse_id (e.g., m1, m21, M10)
%       session  (numeric like 2, 10, ...)
%       group    (CTL / PTEN / PTEN_DKO or variants; used to prioritize the top-level folder)
%       bad channel (comma-separated list like "41,55,59")
%   baseRoot  : folder that contains CTL / PTEN / PTEN_DKO trees (case-insensitive, fuzzy)
%   destRoot  : destination root; outputs are mirrored under this root
%
% Name/Value:
%   'Debug'         : true to process only first 2 rows and only 2 target rows (2 & 4)
%   'TotalChannels' : default 64
%   'StoreClass'    : 'single' (default) or 'double'
%   'ReqsPath'      : folder containing Nlx2MatCSC.mex* (default: ./reqsPath next to this file)

% ------------------ Parse inputs ------------------
ip = inputParser;
ip.addRequired('sheetPath', @(s)ischar(s)||isstring(s));
ip.addRequired('baseRoot',  @(s)ischar(s)||isstring(s));
ip.addRequired('destRoot',  @(s)ischar(s)||isstring(s));
ip.addParameter('Debug', false, @(b)islogical(b)||ismember(b,[0 1]));
ip.addParameter('TotalChannels', 64, @(x)isnumeric(x)&&isscalar(x)&&x>0);
ip.addParameter('StoreClass', 'single', @(s)ischar(s)||isstring(s));
ip.addParameter('ReqsPath', '', @(s)ischar(s)||isstring(s));
ip.parse(sheetPath, baseRoot, destRoot, varargin{:});
args = ip.Results;

sheetPath = char(args.sheetPath);
baseRoot  = char(args.baseRoot);
destRoot  = char(args.destRoot);
DEBUG     = logical(args.Debug);
nTotalCh  = double(args.TotalChannels);
storeClass= char(args.StoreClass);
reqsPath  = char(args.ReqsPath);

if isempty(reqsPath)
    reqsPath = fullfile(fileparts(mfilename('fullpath')), 'reqsPath');
end

if ~isfolder(baseRoot), error('baseRoot not found: %s', baseRoot); end
if ~isfolder(destRoot)
    fprintf('Creating destRoot: %s\n', destRoot);
    mkdir(destRoot);
end
if isfolder(reqsPath), addpath(reqsPath); end
rehash toolboxcache; clear mex;

% --------------- Check Nlx2MatCSC MEX ---------------
mexname = 'Nlx2MatCSC';
p = which('-all', mexname);
if isempty(p)
    error(['%s not found. Place %s.%s in ReqsPath (%s) or add the Neuralynx Import/Export ' ...
           'folder earlier on the path.'], mexname, mexname, mexext, reqsPath);
end
if ~any(endsWith(string(p), ['.',mexext], 'IgnoreCase', true))
    error('MATLAB finds only %s.m; ensure %s.%s is earlier on path.', mexname, mexname, mexext);
end
fprintf('Using %s at:\n', mexname); disp(p(:));

% --------------- Load spreadsheet ---------------
T = readtable(sheetPath, 'FileType', 'spreadsheet');
vn = lower(string(T.Properties.VariableNames));

% Identify columns (case/fuzzy tolerant)
col.mouse   = pickVar(vn, ["mouse_id","mouse","mice","animal"]);
col.session = pickVar(vn, ["session","sess","s"]);
col.group   = pickVar(vn, ["group","grp","condition_group","genotype"]);
col.bad     = pickVar(vn, ["bad channel","bad_channel","badchan","bad","badchannels"]);

need = fieldnames(col);
for k = 1:numel(need)
    if isempty(col.(need{k}))
        error('Spreadsheet is missing a required column like "%s".', need{k});
    end
end

% Trim and normalize
mouseStr  = string(T{:, col.mouse});
sessVal   = T{:, col.session};
grpStr    = string(T{:, col.group});
badStr    = string(T{:, col.bad});

nRows = height(T);
rowIdx = 1:nRows;
if DEBUG
    rowIdx = rowIdx(1:min(2, nRows));
    fprintf('DEBUG: limiting to %d rows\n', numel(rowIdx));
end

% --------------- Find top-level condition folders ---------------
condDirs = findConditionFolders(baseRoot);  % {fullpath, "CTL"/"PTEN"/"PTEN_DKO"}

if isempty(condDirs)
    error('No CTL/PTEN/PTEN_DKO-like folders found under: %s', baseRoot);
end
fprintf('Condition roots:\n');
for i = 1:size(condDirs,1)
    fprintf('  - [%s] %s\n', condDirs{i,2}, condDirs{i,1});
end

% --------------- Process rows ---------------
for r = rowIdx
    % Parse mouse number from "m1", "M21", etc.
    [okM, mouseID] = parseMouseID(mouseStr(r));
    if ~okM
        warning('Row %d: could not parse mouse_id "%s" → skipping', r, mouseStr(r)); 
        continue;
    end
    % Session numeric
    sessID = parseSessionID(sessVal(r));
    if isnan(sessID)
        warning('Row %d: session value invalid → skipping', r); 
        continue;
    end

    % Parse bad channels list
    badList = parseBadList(badStr(r), nTotalCh);

    % Prefer group if present
    preferredCond = mapGroupToConditionName(grpStr(r));

    % Order conditions so we try the preferred one first
    condOrder = 1:size(condDirs,1);
    if preferredCond ~= ""
        hits = find(strcmpi(condDirs(:,2), preferredCond));
        if ~isempty(hits)
            condOrder = [hits(:).' setdiff(condOrder, hits(:).', 'stable')];
        end
    end

    % Locate session leaf that actually contains CSC files
    found = false; chosen = struct;
    for ci = condOrder
        condPath = condDirs{ci,1};
        condName = condDirs{ci,2};
        mFolder  = findMouseFolder(condPath, mouseID);
        if isempty(mFolder), continue; end

        [sessLeaf, relUnderCond] = findBestSessionNcsLeaf(mFolder, mouseID, sessID, condPath);
        if isempty(sessLeaf), continue; end

        chosen.condName     = condName;
        chosen.condPath     = condPath;
        chosen.sessLeaf     = sessLeaf;
        chosen.relUnderCond = relUnderCond;
        found = true; 
        break;
    end

    if ~found
        warning('Row %d: no CSC leaf found for mouse %d / session %d', r, mouseID, sessID);
        continue;
    end

    fprintf('\nRow %d → [%s] mouse m%d, session %d\n', r, chosen.condName, mouseID, sessID);
    fprintf('  session leaf: %s\n', chosen.sessLeaf);

    % Decide row set: even targets with odd fallback; debug → only [2 4]
    if DEBUG
        targetEvens = 2:2:min(4, nTotalCh);  % → [2 4]
    else
        targetEvens = 2:2:nTotalCh;
    end
    [keepTargets, srcForTarget, present, userBadFlags] = ...
        chooseEvenTargetsWithOddFallback(chosen.sessLeaf, nTotalCh, badList, targetEvens);

    % Build destination path (mirror under destRoot / condName / relUnderCond)
    destSessDir = fullfile(destRoot, chosen.condName, chosen.relUnderCond);
    if ~isfolder(destSessDir), mkdir(destSessDir); end

    try
        outFile = runOneSession_convertToLL_uV(chosen.sessLeaf, destSessDir, ...
            keepTargets, srcForTarget, present, userBadFlags, ...
            'StoreClass', storeClass, 'TotalChannels', nTotalCh);
        fprintf('  ✓ Saved: %s\n', outFile);
    catch ME
        warning('  ✗ Failed on %s: %s', chosen.sessLeaf, ME.message);
    end
end

fprintf('\nDone.\n');

end % ====== end main ======


%% ========================= Helper: pick var by aliases =========================
function idx = pickVar(vnames, aliases)
idx = [];
for a = 1:numel(aliases)
    hit = find(strcmp(vnames, lower(aliases(a))), 1, 'first');
    if ~isempty(hit), idx = hit; return; end
end
% try contains
for a = 1:numel(aliases)
    hit = find(contains(vnames, lower(aliases(a))), 1, 'first');
    if ~isempty(hit), idx = hit; return; end
end
end

%% ========================= Helper: parse mouse ID =========================
function [ok, num] = parseMouseID(s)
s = string(s);
tok = regexp(s, '(?i)m\s*0*([0-9]+)', 'tokens', 'once');
if isempty(tok), ok=false; num=NaN; else, ok=true; num=str2double(tok{1}); end
end

%% ========================= Helper: parse session ID =========================
function sess = parseSessionID(val)
if ischar(val) || isstring(val)
    tok = regexp(char(val), '0*([0-9]+)', 'tokens', 'once');
    if isempty(tok), sess = NaN; else, sess = str2double(tok{1}); end
elseif isnumeric(val)
    sess = double(val);
else
    sess = NaN;
end
end

%% ========================= Helper: parse bad list =========================
function bad = parseBadList(s, nTotal)
% "41,55,59" or "8,41,59"
if ismissing(s) || isempty(s)
    bad = [];
    return;
end
s = char(s);
tok = regexp(s, '([0-9]+)', 'tokens');
if isempty(tok), bad = []; return; end
vals = unique(str2double(string([tok{:}])));
vals = vals(isfinite(vals) & vals>=1 & vals<=nTotal);
bad  = vals(:).';
end

%% ========================= Helper: map group → condition name =========================
function out = mapGroupToConditionName(x)
s = lower(strtrim(string(x)));
if any(strcmp(s, ["ctl","control"])),           out = "CTL";      return; end
if any(strcmp(s, ["pten","pten+","pten-"])),    out = "PTEN";     return; end
if ~isempty(regexp(s,"dko",'once')),            out = "PTEN_DKO"; return; end
out = "";
end

%% ========================= Helper: find condition folders =========================
function condDirs = findConditionFolders(baseRoot)
L = dir(baseRoot); L = L([L.isdir]);
names = string({L.name});
names = names(~ismember(names, ["." ".."]));

patt.CTL      = "(?i)^CTL$";
patt.PTEN     = "(?i)^PTEN$";
patt.PTEN_DKO = "(?i)^(PTEN[_-]?DKO|PTENDKO|PTENDKOM\d+)$";

condDirs = {};
keys = {'CTL','PTEN','PTEN_DKO'};
for i = 1:numel(keys)
    canon = keys{i};
    hit = names(~cellfun('isempty', regexp(names, patt.(canon), 'once')));
    if ~isempty(hit)
        for k = 1:numel(hit)
            condDirs(end+1, :) = {fullfile(baseRoot, char(hit(k))), canon}; %#ok<AGROW>
        end
    end
end
end

%% ========================= Helper: find mouse folder under a condition =========================
function mFolder = findMouseFolder(condPath, mouseID)
mFolder = '';
D = dir(condPath); D = D([D.isdir]);
for i = 1:numel(D)
    nm = D(i).name;
    if any(strcmp(nm,{'.','..'})), continue; end
    if ~isempty(regexpi(nm, sprintf('^m0*%d\\b', mouseID), 'once'))
        mFolder = fullfile(condPath, nm);
        return;
    end
end
end

%% ========================= Helper: find session leaf that has CSC files =========================
function [sessLeaf, relUnderCond] = findBestSessionNcsLeaf(mFolder, mouseID, sessID, condPath)
tagS = sprintf('s0*%d', sessID);

C = dir(fullfile(mFolder, '**')); C = C([C.isdir]);
cand = strings(0,1);
for i = 1:numel(C)
    nm = string(C(i).name);
    if any(nm==["." ".."]), continue; end
    p  = string(fullfile(C(i).folder, nm));
    if ~isempty(regexpi(nm, tagS, 'once')) || ~isempty(regexpi(p, tagS, 'once'))
        cand(end+1) = p; %#ok<AGROW>
    end
end
if isempty(cand)
    cand = string(mFolder); % fallback search entire mouse tree
end

[bestLeaf, bestCount, bestDepth] = deal("", -inf, -inf);
for i = 1:numel(cand)
    [leaf, count, depth] = findNcsLeafWithCount(cand(i));
    if count > bestCount || (count==bestCount && depth>bestDepth)
        bestLeaf = leaf; bestCount = count; bestDepth = depth;
    end
end

if bestCount <= 0
    sessLeaf = ''; relUnderCond = ''; return;
end
sessLeaf = char(bestLeaf);
relUnderCond = erase(sessLeaf, [condPath filesep]);
end

function [leaf, count, depth] = findNcsLeafWithCount(rootDir)
F = dir(fullfile(rootDir, '**', '*.ncs'));
if isempty(F), leaf = ""; count = 0; depth = -inf; return; end
keep = false(numel(F),1);
for i=1:numel(F)
    keep(i) = ~isempty(regexpi(F(i).name, '^CSC(\d+)\.ncs$', 'once'));
end
F = F(keep);
if isempty(F), leaf = ""; count = 0; depth = -inf; return; end

folders = string({F.folder});
u = unique(folders);
counts = arrayfun(@(p) sum(folders==p), u);
depths = arrayfun(@(p) numel(strfind(char(p), filesep)), u);

[~, k] = max(counts);
mx = counts(k); idx = find(counts==mx);
if numel(idx) > 1
    [~, j] = max(depths(idx)); k = idx(j);
end
leaf = u(k); count = counts(k); depth = depths(k);
end

%% ========================= Helper: pick even targets with odd fallback =========================
function [keepTargets, srcForTarget, present, userBadFlags] = ...
    chooseEvenTargetsWithOddFallback(sessLeaf, nTotalCh, bad_user_list, targetEvens)

% Scan present CSC files
present = false(1, nTotalCh);
D = dir(fullfile(sessLeaf, '*.ncs'));
for i=1:numel(D)
    tok = regexpi(D(i).name, '^CSC(\d+)\.ncs$', 'tokens', 'once');
    if ~isempty(tok)
        ch = str2double(tok{1});
        if ch>=1 && ch<=nTotalCh, present(ch) = true; end
    end
end

userBadFlags = false(1, nTotalCh);
if ~isempty(bad_user_list)
    userBadFlags(bad_user_list) = true;
end

good = present & ~userBadFlags;

used = false(1, nTotalCh);
keepTargets  = targetEvens(:).';
srcForTarget = zeros(size(keepTargets));

for ii = 1:numel(keepTargets)
    e = keepTargets(ii);
    if e<=nTotalCh && good(e) && ~used(e)
        srcForTarget(ii) = e; used(e) = true; continue;
    end
    % nearest good odd fallback
    maxDelta = max(e-1, nTotalCh-e); chosen = 0;
    for d = 1:2:(2*ceil(maxDelta)+1)
        cands = unique([e-d, e+d]);
        for c = cands
            if c>=1 && c<=nTotalCh && mod(c,2)==1 && good(c) && ~used(c)
                chosen = c; break;
            end
        end
        if chosen>0, break; end
    end
    srcForTarget(ii) = chosen; % 0 if none
    if chosen>0, used(chosen) = true; end
end
end

%% ========================= Core worker: convert one session to LL-ready (µV) =========================
function outFull = runOneSession_convertToLL_uV(basePath, destSessDir, ...
    keepTargets, srcForTarget, present, userBadFlags, varargin)

ip = inputParser;
ip.addParameter('StoreClass','single', @(s)ischar(s)||isstring(s));
ip.addParameter('TotalChannels',64, @(x)isnumeric(x)&&isscalar(x)&&x>0);
ip.parse(varargin{:});
storeClass = char(ip.Results.StoreClass);
nTotalCh   = double(ip.Results.TotalChannels);

% Flags for Nlx2MatCSC
FS = [1 1 1 1 1];  EH = 1;  EM = 1;

% Map: unique sources actually needed
srcNeeded = unique(srcForTarget(srcForTarget>0), 'stable');
if isempty(srcNeeded)
    error('No valid channels available for targets: %s', mat2str(keepTargets));
end
% DEBUG: If we only kept [2 4], srcNeeded is 1-2 items accordingly.

% ---- First pass: get lengths, sfx, headers for needed sources ----
headersCell_src = cell(1, numel(srcNeeded));
sfxArr          = nan(1, numel(srcNeeded));
lenArr          = zeros(1, numel(srcNeeded));
ADBitVolts_src  = nan(1, numel(srcNeeded));

fprintf('  First pass (sources): scanning %d channels\n', numel(srcNeeded));
for k = 1:numel(srcNeeded)
    ch = srcNeeded(k);
    fname = fullfile(basePath, sprintf('CSC%d.ncs', ch));
    if ~isfile(fname)
        error('Expected source file missing: %s', fname);
    end

    [Timestamps, ~, SampleFrequencies, NValid, Samples, Header] = ...
        Nlx2MatCSC(fname, FS, EH, EM, []);

    blkN = size(Samples,1); nv = min(blkN, max(0, NValid(:)'));
    lenArr(k) = sum(nv);

    sfxCh = mode(double(SampleFrequencies(SampleFrequencies>0)));
    if ~(isfinite(sfxCh) && sfxCh>0)
        sfLine = Header(contains(Header,'SamplingFrequency','IgnoreCase',true));
        if ~isempty(sfLine)
            tok = regexp(sfLine{1}, 'SamplingFrequency[^0-9eE.\-]*([\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?)', 'tokens', 'once');
            if ~isempty(tok), sfxCh = str2double(tok{1}); end
        end
    end
    sfxArr(k) = sfxCh;

    % Parse ADBitVolts
    ADBV = NaN;
    j = find(contains(Header,'ADBitVolts','IgnoreCase',true),1,'first');
    if ~isempty(j)
        tok = regexp(Header{j}, 'ADBitVolts[^0-9eE.\-]*([\-+]?\d+(\.\d+)?([eE][\-+]?\d+)?)', 'tokens', 'once');
        if ~isempty(tok), ADBV = str2double(tok{1}); end
    end
    ADBitVolts_src(k) = ADBV;

    headersCell_src{k} = Header;

    % Rough continuity warning
    if ~isempty(Timestamps) && isfinite(sfxCh) && sfxCh>0
        expectedStep_us = 512 * (1e6 / sfxCh);
        dt = diff(double(Timestamps));
        if any(abs(dt - expectedStep_us) > 0.5 * expectedStep_us)
            warning('    Timing irregularity in CSC%d (internal gaps not interpolated).', ch);
        end
    end
end

goodSfx = isfinite(sfxArr) & sfxArr>0 & (lenArr>0);
if ~any(goodSfx)
    error('No valid sampling frequency determined among needed sources.');
end
sfx = mode(round(sfxArr(goodSfx)));
maxN= max(lenArr(goodSfx));

% ---- Disk-backed allocate ----
bytesPer = strcmpi(storeClass,'single')*4 + strcmpi(storeClass,'double')*8;
nRows = numel(keepTargets);  % rows correspond to targets in order
approxGB = (nRows*maxN*bytesPer)/1e9;
fprintf('  Creating disk-backed d: %d x %d (%s) ~ %.2f GB\n', nRows, maxN, storeClass, approxGB);

% Name output by session folder name
leafName = getLastFolder(basePath);
outName  = sprintf('LL_input_%s_uV.mat', leafName);
outFull  = fullfile(destSessDir, outName);
if exist(outFull, 'file'), delete(outFull); end

mf = matfile(outFull, 'Writable', true);
switch lower(storeClass)
    case 'single', mf.d = single(NaN(nRows, maxN));
    case 'double', mf.d = NaN(nRows, maxN);
    otherwise, error('StoreClass must be ''single'' or ''double''.');
end

% Placeholders/static meta
mf.sfx          = sfx;
badch_full      = ~present | userBadFlags;   % original-index bad/missing
badch_full      = badch_full(1:nTotalCh);
mf.badch        = badch_full;
mf.chan_labels  = arrayfun(@(k) sprintf('CSC%d', k), 1:nTotalCh, 'UniformOutput', false);
mf.kept_targets = keepTargets;
mf.row_source   = srcForTarget(:).';
mf.headersCell  = cell(1, nRows); % will fill row order with source headers

meta.basePath       = basePath;
meta.destSessDir    = destSessDir;
meta.createdOn      = datestr(now);
meta.nTotalCh       = nTotalCh;
meta.nRows          = nRows;
meta.reader         = ['Nlx2MatCSC (', mexext, ')'];
meta.storeClass     = storeClass;
meta.note           = 'Disk-backed; NaN-padded; data scaled to microvolts; rows=target evens with odd fallbacks.';
meta.srcNeeded      = srcNeeded;
meta.lenPerSrc      = lenArr;
meta.sfxPerSrc      = sfxArr;
meta.ADBitVolts_src = ADBitVolts_src;
meta.mapping_table  = [keepTargets(:), srcForTarget(:)];
mf.meta = meta;

% Map source → ADBitVolts for quick lookup
defaultADBV = 0.00000006103515625; % V/AD fallback
ADmap = containers.Map('KeyType','int32','ValueType','double');
for k = 1:numel(srcNeeded)
    ch = int32(srcNeeded(k));
    ad = ADBitVolts_src(k);
    if ~isfinite(ad) || ad<=0, ad = defaultADBV; end
    ADmap(ch) = ad;
end

% ---- Second pass: write each row (target) using its source channel ----
fprintf('  Second pass: writing data (scaled to µV)\n');
t0 = tic;
for ri = 1:nRows
    target = keepTargets(ri);
    src    = srcForTarget(ri);

    if src<=0
        % no source → leave NaNs
        mf.headersCell{ri} = {};
        fprintf('    [%3d/%3d] target %2d → (none)\n', ri, nRows, target);
        continue;
    end

    fname = fullfile(basePath, sprintf('CSC%d.ncs', src));
    [~, ~, ~, NValid, Samples, Header] = Nlx2MatCSC(fname, [1 1 1 1 1], 0, 1, []);
    blkN = size(Samples,1); nRec = size(Samples,2);

    effLen = sum(min(blkN, max(0, NValid(:)')));
    x = nan(1, effLen);
    pos = 1;
    for r = 1:nRec
        nv = min(blkN, max(0, NValid(r)));
        if nv>0
            x(pos:pos+nv-1) = double(Samples(1:nv, r));
            pos = pos + nv;
        end
    end

    % Scale to microvolts using channel-specific ADBitVolts
    ADBV = defaultADBV;
    if isKey(ADmap, int32(src)), ADBV = ADmap(int32(src)); end
    x = x .* (ADBV * 1e6); % µV

    switch lower(class(mf.d))
        case 'single', x = single(x);
        case 'double', x = double(x);
    end
    mf.d(ri, 1:numel(x)) = x;

    mf.headersCell{ri} = Header;

    if mod(ri, max(1, floor(nRows/10)))==0 || ri==nRows
        elapsed = toc(t0);
        fprintf('    [%3d/%3d] target %2d ← src %2d | %.1f%% | %s\n', ...
            ri, nRows, target, src, 100*ri/nRows, duration(0,0,elapsed,"Format","mm:ss"));
    end
end
end

%% ========================= small helper =========================
function s = getLastFolder(p)
[~, s] = fileparts(p);
if s=="", s = p; end
end
