function Batch_CSC_Tree_ToDest_EvenOnly(spreadsheetPath, baseRoot, destRoot, varargin)
% Batch_CSC_Tree_ToDest_EvenOnly(spreadsheetPath, baseRoot, destRoot, Name,Value...)
% REQUIRED:
%   spreadsheetPath : .xlsx/.csv with columns [mouse, session, (...), bad channels]
%   baseRoot        : folder that contains CTL / PTEN / PTEN_DKO (case-insens.)
%   destRoot        : folder where ALL mirrored outputs will be placed
%
% Outputs are mirrored to:
%   destRoot / <Condition> / <relative path under that condition> / <outName>
%
% Options:
%   'nTotalCh'         (64)
%   'storeClass'       ('single')
%   'reqsPath'         (./reqsPath)
%   'fallbackADBV'     (0.00000006103515625)   % V/AD
%   'outNameFmt'       ('LL_input_M%02d_s%02d_uV.mat')
%   'debugMode'        (false)   % if true: only first 2 rows, only first 2 channels
%   'debugMaxRows'     (2)
%   'debugMaxChannels' (2)
%
% Depends on: CSC2LL_uV_mex_disk (on MATLAB path).

% ---------- Parse args ----------
ip = inputParser;
ip.addRequired('spreadsheetPath', @(s)ischar(s)||isstring(s));
ip.addRequired('baseRoot', @(s)ischar(s)||isstring(s));
ip.addRequired('destRoot', @(s)ischar(s)||isstring(s));
ip.addParameter('nTotalCh', 64, @(x)isnumeric(x)&&isscalar(x)&&x>=1);
ip.addParameter('storeClass', 'single', @(s)ischar(s)||isstring(s));
ip.addParameter('reqsPath', fullfile(fileparts(mfilename('fullpath')),'reqsPath'), @(s)ischar(s)||isstring(s));
ip.addParameter('fallbackADBV', 0.00000006103515625, @(x)isfinite(x)&&x>0);
ip.addParameter('outNameFmt', 'LL_input_M%02d_s%02d_uV.mat', @(s)ischar(s)||isstring(s));
ip.addParameter('debugMode', false, @(x)islogical(x)||ismember(x,[0,1]));
ip.addParameter('debugMaxRows', 2, @(x)isnumeric(x)&&isscalar(x)&&x>=1);
ip.addParameter('debugMaxChannels', 2, @(x)isnumeric(x)&&isscalar(x)&&x>=1);
ip.parse(spreadsheetPath, baseRoot, destRoot, varargin{:});

spreadsheetPath  = char(ip.Results.spreadsheetPath);
baseRoot         = char(ip.Results.baseRoot);
destRoot         = char(ip.Results.destRoot);
nTotalCh         = ip.Results.nTotalCh;
storeClass       = char(ip.Results.storeClass);
reqsPath         = char(ip.Results.reqsPath);
fallbackADBV     = ip.Results.fallbackADBV;
outNameFmt       = char(ip.Results.outNameFmt);
debugMode        = logical(ip.Results.debugMode);
debugMaxRows     = ip.Results.debugMaxRows;
debugMaxChannels = ip.Results.debugMaxChannels;

assert(isfolder(baseRoot), "Base root not found: %s", baseRoot);
if ~isfolder(destRoot), mkdir(destRoot); end

% Accept common casings of condition folders under baseRoot
condNamesWanted = {'CTL','PTEN','PTEN_DKO'};
condDirs = findConditionFolders(baseRoot, condNamesWanted);
if isempty(condDirs)
    error('None of CTL/PTEN/PTEN_DKO found under: %s', baseRoot);
end
fprintf('Conditions: %s\n', strjoin(condDirs(:,2), ', '));
fprintf('Destination mirror root: %s\n', destRoot);

% ---------- Read spreadsheet ----------
T = readtable(spreadsheetPath, 'TextType','string', 'VariableNamingRule','preserve');
if width(T) < 2
    error('Spreadsheet needs at least two columns: [mouse, session].');
end
badCol = find(contains(lower(string(T.Properties.VariableNames)),"bad"),1,'first');
if isempty(badCol), badCol = width(T); end

rowIdx = 1:height(T);
if debugMode
    rowIdx = rowIdx(1:min(debugMaxRows, numel(rowIdx)));
    fprintf('[DEBUG] limiting to %d rows; max %d channels per row\n', numel(rowIdx), debugMaxChannels);
end

% ---------- Iterate spreadsheet rows ----------
for r = rowIdx
    mouseRaw = T{r,1};     sessRaw = T{r,2};
    mouseID  = extractMouseId(mouseRaw);
    sessID   = extractFirstInt(sessRaw);
    if isnan(mouseID) || isnan(sessID)
        warning('Row %d skipped (mouse/session not parsed): mouse="%s", sess="%s"', r, string(mouseRaw), string(sessRaw));
        continue;
    end

    badList = parseBadList(T{r,badCol});
    badList = unique(badList(badList>=1 & badList<=nTotalCh));

    % ---- locate .ncs leaf by condition ----
    found = false; chosen = struct;
    for ci = 1:size(condDirs,1)
        condPath = condDirs{ci,1};
        condName = condDirs{ci,2};
        mFolder = findMouseFolder(condPath, mouseID);
        if isempty(mFolder), continue; end

        [sessLeaf, relUnderCond] = findBestSessionNcsLeaf(mFolder, mouseID, sessID, condPath);
        if isempty(sessLeaf), continue; end

        chosen.condName     = condName;
        chosen.condPath     = condPath;
        chosen.sessLeaf     = sessLeaf;
        chosen.relUnderCond = relUnderCond;  % path under condition (does NOT include condName)
        found = true; break;
    end
    if ~found
        warning('Row %d (M%d S%d): no .ncs folder found under any condition.', r, mouseID, sessID);
        continue;
    end

    % ---- choose channels: even-only w/ odd fallback ----
    [keepList, mappingPairs, presentVec] = chooseEvenWithOddFallback(chosen.sessLeaf, nTotalCh, badList);
    if isempty(keepList)
        warning('Row %d (M%d S%d): no usable channels after substitution.', r, mouseID, sessID);
        continue;
    end
    if debugMode
        keepList = keepList(1:min(debugMaxChannels, numel(keepList)));
        mappingPairs = mappingPairs(ismember(mappingPairs(:,2), keepList), :);
        fprintf('[DEBUG] channels → %s\n', mat2str(keepList));
    else
        fprintf('Channels → %s\n', prettyList(keepList, 56));
    end

    % ---- convert in-place (leaf), then copy to destRoot mirror ----
    outName = sprintf(outNameFmt, mouseID, sessID);
    try
        CSC2LL_uV_mex_disk(chosen.sessLeaf, ...
            'nTotalCh', nTotalCh, ...
            'evenOnly', false, ...
            'keep', keepList, ...
            'storeClass', storeClass, ...
            'outName', outName, ...
            'fallbackADBV', fallbackADBV, ...
            'reqsPath', reqsPath);
    catch ME
        warning('Converter failed for %s (row %d): %s', chosen.sessLeaf, r, ME.message);
        continue;
    end

    srcMat  = fullfile(chosen.sessLeaf, outName);
    if ~isfile(srcMat)
        warning('Missing expected output: %s', srcMat); continue;
    end

    % Mirror path includes condition explicitly under destRoot
    destDir = fullfile(destRoot, chosen.condName, chosen.relUnderCond);
    if ~isfolder(destDir), mkdir(destDir); end
    destMat = fullfile(destDir, outName);

    try
        copyfile(srcMat, destMat);
    catch ME
        warning('Copy to destination failed: %s', ME.message);
        continue;
    end

    % ---- annotate badch + meta in the DEST copy ----
    try
        mf = matfile(destMat, 'Writable', true);

        badch_user = false(1, nTotalCh); badch_user(badList) = true;
        try, existing_badch = mf.badch; catch, existing_badch = false(1, nTotalCh); end
        if numel(existing_badch) ~= nTotalCh
            tmp = false(1, nTotalCh);
            ncopy = min(numel(existing_badch), nTotalCh);
            tmp(1:ncopy) = existing_badch(1:ncopy);
            existing_badch = tmp;
        end
        badch_combined = existing_badch | badch_user;

        mf.badch_user      = badch_user;
        mf.badch_combined  = badch_combined;

        try, mmeta = mf.meta; catch, mmeta = struct; end
        mmeta.mouseID                 = mouseID;
        mmeta.sessionID               = sessID;
        mmeta.condition               = chosen.condName;
        mmeta.source_ncs_path         = chosen.sessLeaf;
        mmeta.destination_path        = destMat;
        mmeta.spreadsheet_row         = r;
        mmeta.badch_user_list         = badList;
        mmeta.selection_policy        = 'even_preferred_with_odd_substitution';
        mmeta.target_even_list        = 2:2:nTotalCh;
        mmeta.files_present           = find(presentVec);
        mmeta.chosen_keep_list        = keepList;
        mmeta.even_to_used_pairs      = mappingPairs;   % [target_even, used_channel]
        mf.meta = mmeta;

        fprintf('Row %d: M%d S%d → %s\n', r, mouseID, sessID, destMat);
    catch ME
        warning('Annotate failed for %s: %s', destMat, ME.message);
    end
end

fprintf('\nDone. Mirrored outputs under: %s\n', destRoot);
end

% ================= helpers (unchanged from previous drop-in) =================

function condDirs = findConditionFolders(baseRoot, wanted)
    L = dir(baseRoot); L = L([L.isdir]);
    names = string({L.name});
    names = names(~ismember(names, ["." ".."]));
    condDirs = {};
    for i = 1:numel(wanted)
        hit = names(strcmpi(names, wanted{i}));
        if ~isempty(hit)
            condDirs(end+1, :) = {fullfile(baseRoot, char(hit(1))), char(hit(1))}; %#ok<AGROW>
        end
    end
end

function n = extractMouseId(x)
    s = string(x);
    tok = regexp(s, '^\s*[mM]\s*0*(\d+)', 'tokens', 'once');
    if ~isempty(tok), n = str2double(tok{1}); return; end
    n = extractFirstInt(s);
end

function n = extractFirstInt(x)
    if ismissing(x) || (ischar(x) && isempty(x)), n = NaN; return; end
    s = string(x); tok = regexp(s, '(\d+)', 'tokens', 'once');
    n = iff(isempty(tok), NaN, str2double(tok{1}));
end

function v = parseBadList(x)
    if ismissing(x) || (ischar(x) && isempty(x)), v = []; return; end
    s = string(x); toks = regexp(s, '(\d+)', 'tokens');
    v = [];
    for k=1:numel(toks)
        if ~isempty(toks{k}), v = [v, str2double([toks{k}{:}])]; end %#ok<AGROW>
    end
    v = unique(v);
end

function out = iff(cond,a,b), if cond, out=a; else, out=b; end, end

function mFolder = findMouseFolder(condPath, mouseID)
    mFolder = '';
    D = dir(fullfile(condPath, 'M*')); D = D([D.isdir]);
    pat = sprintf('^M0*%d\\b', mouseID); % starts with M + digits, allow suffix
    for i = 1:numel(D)
        if ~isempty(regexpi(D(i).name, pat, 'once'))
            mFolder = fullfile(condPath, D(i).name); return;
        end
    end
end

function [sessLeaf, relUnderCond] = findBestSessionNcsLeaf(mFolder, mouseID, sessID, condPath)
    tagM = sprintf('m0*%d', mouseID);
    tagS = sprintf('s0*%d', sessID);

    C = dir(fullfile(mFolder, '**')); C = C([C.isdir]);
    paths = strings(0,1);
    for i = 1:numel(C)
        nm = string(C(i).name); if nm=="."||nm=="..", continue; end
        p = string(fullfile(C(i).folder, nm));
        if ~isempty(regexpi(p, tagM, 'once')) && ~isempty(regexpi(p, tagS, 'once'))
            paths(end+1) = p; %#ok<AGROW>
        end
    end
    if isempty(paths)
        paths = string(mFolder);
    end

    [bestLeaf, bestCount, bestDepth] = deal("", -inf, -inf);
    for i = 1:numel(paths)
        [leaf, count, depth] = findNcsLeafWithCount(paths(i));
        if count > bestCount || (count==bestCount && depth>bestDepth)
            bestLeaf = leaf; bestCount = count; bestDepth = depth;
        end
    end

    if bestCount <= 0
        sessLeaf = ''; relUnderCond = ''; return;
    end
    sessLeaf = char(bestLeaf);
    % relUnderCond = path under the condition folder (does NOT include the condition name)
    relUnderCond = erase(sessLeaf, [condPath filesep]);
end

function [leaf, count, depth] = findNcsLeafWithCount(rootDir)
    F = dir(fullfile(rootDir, '**', 'CSC*.ncs'));
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

function [keepList, mappingPairs, present] = chooseEvenWithOddFallback(sessLeaf, nTotalCh, bad_user_list)
    present = false(1, nTotalCh);
    F = dir(fullfile(sessLeaf, 'CSC*.ncs'));
    for i=1:numel(F)
        tok = regexp(F(i).name, '^CSC(\d+)\.ncs$', 'tokens', 'once');
        if ~isempty(tok)
            ch = str2double(tok{1});
            if ch>=1 && ch<=nTotalCh, present(ch) = true; end
        end
    end
    bad_user = false(1, nTotalCh); bad_user(bad_user_list) = true;
    good = present & ~bad_user;

    targetEvens = 2:2:nTotalCh;
    used = false(1, nTotalCh);
    keep = []; pairs = [];

    for e = targetEvens
        if e<=nTotalCh && good(e) && ~used(e)
            keep(end+1) = e; used(e) = true; pairs(end+1,:) = [e e]; %#ok<AGROW>
            continue;
        end
        maxDelta = max(e-1, nTotalCh-e);
        chosen = NaN;
        for d = 1:2:(2*ceil(maxDelta)+1)  % odd deltas only
            for c = unique([e-d, e+d])
                if c>=1 && c<=nTotalCh && mod(c,2)==1 && good(c) && ~used(c)
                    chosen = c; break;
                end
            end
            if ~isnan(chosen), break; end
        end
        if ~isnan(chosen)
            keep(end+1) = chosen; used(chosen)=true; pairs(end+1,:) = [e chosen]; %#ok<AGROW>
        else
            pairs(end+1,:) = [e 0]; %#ok<AGROW>
        end
    end

    keepList     = unique(keep, 'stable');
    mappingPairs = pairs;
end

function s = prettyList(v, maxChars)
    s = mat2str(v);
    if nargin<2, maxChars=60; end
    if strlength(s) > maxChars
        s = extractBefore(s, maxChars) + " …]";
    end
end
