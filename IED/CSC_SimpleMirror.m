function CSC_SimpleMirror(baseRoot, sheetPath, destRoot)
% CSC_SimpleMirror(baseRoot, sheetPath, destRoot)
% Simple, literal walker:
%  baseRoot -> <GROUP> -> m# -> session s# -> timestamp -> .ncs
% Copies EVEN channels only to dest. If an even is bad/missing, takes the next odd.
%
% Spreadsheet must have at least: mouse_id, session, and group (or condition).
%
% Example:
%   CSC_SimpleMirror('D:\', 'D:\Mouse Recording Sessions.xlsx', 'D:\data');

assert(isfolder(baseRoot), 'baseRoot not found: %s', baseRoot);
if ~isfolder(destRoot), mkdir(destRoot); end

% --- read sheet (very tolerant col names) ---
T = readtable(sheetPath, 'FileType', 'spreadsheet');
v = lower(string(T.Properties.VariableNames));
col.mouse   = pickVar(v, ["mouse_id","mouse"]);
col.sess    = pickVar(v, ["session","sess","s"]);
col.group   = pickVar(v, ["group","condition"]);

need = fieldnames(col);
for i = 1:numel(need)
    assert(~isempty(col.(need{i})), 'Missing column like "%s".', need{i});
end

rows = 1:height(T);
for r = rows
    grp  = string(T{r, col.group});
    mouseStr = string(T{r, col.mouse});
    sessVal  = T{r, col.sess};
    badStr   = ""; % optional column
    if any(strcmpi(v, "bad channel"))
        badStr = string(T{r, find(strcmpi(v,"bad channel"),1)});
    elseif any(strcmpi(v, "bad_channel"))
        badStr = string(T{r, find(strcmpi(v,"bad_channel"),1)});
    end

    [okM, mnum]   = parseMouse(mouseStr);
    snum          = parseSess(sessVal);
    if ~okM || isnan(snum)
        fprintf('Row %d: skip (bad mouse/session)\n', r);
        continue;
    end

    % 1) GROUP folder
    gPath = findGroupFolder(baseRoot, grp);
    if gPath == ""
        fprintf('Row %d: group "%s" not found under %s\n', r, grp, baseRoot);
        continue;
    end

    % 2) mouse folder m#
    mPath = findMouseFolder(gPath, mnum);
    if mPath == ""
        fprintf('Row %d: mouse m%d not found under %s\n', r, mnum, gPath);
        continue;
    end

    % 3) session folder(s) for s#
    sPaths = findSessionFolders(mPath, snum);
    if isempty(sPaths)
        fprintf('Row %d: session s%d not found under %s\n', r, snum, mPath);
        continue;
    end

    % parse bad list as numbers
    badList = parseBad(badStr);

    fprintf('\nRow %d  [%s]  m%d  s%d\n', r, upper(string(grp)), mnum, snum);
    for si = 1:numel(sPaths)
        sp = sPaths(si);
        % 4) timestamp leaves (do ALL)
        leaves = findTimestampLeaves(sp);
        if isempty(leaves)
            fprintf('  session: %s  (no timestamp/.ncs)\n', sp);
            continue;
        end

        for li = 1:numel(leaves)
            leaf = leaves(li);
            % find CSC files available
            [srcMap, presentCh] = collectCSC(leaf);
            if isempty(fieldnames(srcMap))
                fprintf('    leaf: %s  (no CSC*.ncs)\n', leaf);
                continue;
            end

            % targets: even channels up to max present (cap 64)
            maxCh = max([presentCh(:); 64]);
            targets = 2:2:min(64, maxCh);

            % decide destination path mirror under destRoot
            relPath = erase(leaf, [gPath filesep]);
            outLeaf = fullfile(destRoot, getGroupName(gPath), relPath);
            if ~isfolder(outLeaf), mkdir(outLeaf); end

            fprintf('    → %s\n', outLeaf);

            % for each even target, choose source (even, else next odd e+1, else e-1)
            for e = targets
                src = chooseSourceForEven(e, presentCh, badList);
                if isnan(src)
                    fprintf('      CSC%02d: (skip) no good neighbor\n', e);
                    continue;
                end

                srcFile = srcMap.(sprintf('c%d', src));
                dstFile = fullfile(outLeaf, sprintf('CSC%d.ncs', e));

                % copy (overwrite OK)
                [ok,msg] = copyfile(srcFile, dstFile, 'f');
                if ~ok
                    fprintf('      CSC%02d: copy FAIL from CSC%d (%s)\n', e, src, msg);
                else
                    if src==e
                        fprintf('      CSC%02d: copied\n', e);
                    else
                        fprintf('      CSC%02d: substituted from CSC%d\n', e, src);
                    end
                end
            end
        end
    end
end

fprintf('\nDone.\n');
end

% --------------------- helpers ---------------------

function idx = pickVar(vnames, aliases)
idx = [];
for a = 1:numel(aliases)
    k = find(vnames == lower(aliases(a)), 1);
    if ~isempty(k), idx = k; return; end
end
for a = 1:numel(aliases)
    k = find(contains(vnames, lower(aliases(a))), 1);
    if ~isempty(k), idx = k; return; end
end
end

function [ok, num] = parseMouse(s)
tok = regexp(char(s), '(?i)m\s*0*([0-9]+)', 'tokens', 'once');
ok = ~isempty(tok);
num = NaN;
if ok, num = str2double(tok{1}); end
end

function sess = parseSess(x)
if isnumeric(x), sess = double(x); return; end
tok = regexp(char(string(x)), '0*([0-9]+)', 'tokens', 'once');
if isempty(tok), sess = NaN; else, sess = str2double(tok{1}); end
end

function nums = parseBad(s)
if ismissing(s) || strlength(s)==0, nums = []; return; end
tok = regexp(char(s), '([0-9]+)', 'tokens');
if isempty(tok), nums = []; return; end
nums = unique(str2double(string([tok{:}])));
end

function g = getGroupName(gPath)
[~, g] = fileparts(gPath); 
end

function gPath = findGroupFolder(baseRoot, grp)
names = dir(baseRoot); names = names([names.isdir]);
cands = string({names.name});
cands = cands(~ismember(cands, [".",".."]));
s = lower(strtrim(string(grp)));

% exacts first
if any(strcmpi(cands, "CTL"))      && any(strcmp(s,["ctl","control"])), gPath = fullfile(baseRoot,'CTL'); return; end
if any(strcmpi(cands, "PTEN"))     && any(strcmp(s,["pten"])),           gPath = fullfile(baseRoot,'PTEN'); return; end
if any(strcmpi(cands, "PTEN_DKO")) && contains(s,"dko"),                 gPath = fullfile(baseRoot,'PTEN_DKO'); return; end

% fuzzy
if any(strcmp(s,["ctl","control"]))
    hit = cands(contains(lower(cands), "ctl"));
    if ~isempty(hit), gPath = fullfile(baseRoot, hit(1)); return; end
elseif contains(s,"pten") && ~contains(s,"dko")
    hit = cands(contains(lower(cands), "pten") & ~contains(lower(cands),"dko"));
    if ~isempty(hit), gPath = fullfile(baseRoot, hit(1)); return; end
elseif contains(s,"dko")
    hit = cands(contains(lower(cands), "pten") & contains(lower(cands),"dko"));
    if ~isempty(hit), gPath = fullfile(baseRoot, hit(1)); return; end
end
gPath = "";
end

function mPath = findMouseFolder(gPath, mnum)
D = dir(gPath); D = D([D.isdir]);
mPath = "";
pat = sprintf('(?i)(?<!\\d)m0*%d(?!\\d)', mnum); % "m<num>" not followed by a digit
for i = 1:numel(D)
    nm = D(i).name;
    if any(strcmp(nm,{'.','..'})), continue; end
    if ~isempty(regexp(nm, pat, 'once'))
        mPath = fullfile(gPath, nm);
        return;
    end
end
end

function sPaths = findSessionFolders(mPath, snum)
D = dir(mPath); D = D([D.isdir]);
sPaths = strings(0,1);
patS  = sprintf('(?i)s0*%d(?!\\d)', snum);     % s2 but not s21/s22
patN  = sprintf('(?<!\\d)0*%d(?!\\d)', snum);  % bare "2" not part of 21
for i = 1:numel(D)
    nm = D(i).name;
    if any(strcmp(nm,{'.','..'})), continue; end
    if ~isempty(regexp(nm, patS, 'once')) || ~isempty(regexp(nm, patN, 'once'))
        sPaths(end+1,1) = string(fullfile(mPath, nm)); %#ok<AGROW>
    end
end
end

function leaves = findTimestampLeaves(sPath)
% Prefer immediate subfolders that look like "YYYY-MM-DD_HH-MM-SS"
D = dir(sPath); D = D([D.isdir]);
cand = strings(0,1);
for i = 1:numel(D)
    nm = string(D(i).name);
    if any(nm==["." ".."]), continue; end
    if ~isempty(regexp(nm, '^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$', 'once'))
        cand(end+1,1) = string(fullfile(sPath, nm)); %#ok<AGROW>
    end
end
if ~isempty(cand)
    leaves = cand; return;
end

% If no timestamp folder, maybe .ncs is directly inside sPath
if ~isempty(dir(fullfile(sPath,'CSC*.ncs')))
    leaves = string(sPath);
    return;
end

% One level deeper: any folder that contains .ncs
leaves = strings(0,1);
D2 = dir(fullfile(sPath, '*')); D2 = D2([D2.isdir]);
for i = 1:numel(D2)
    p = fullfile(sPath, D2(i).name);
    if ~isempty(dir(fullfile(p, 'CSC*.ncs')))
        leaves(end+1,1) = string(p); %#ok<AGROW>
    end
end
end

function [srcMap, presentCh] = collectCSC(leaf)
F = dir(fullfile(leaf, 'CSC*.ncs'));
srcMap = struct(); presentCh = [];
for i = 1:numel(F)
    t = regexp(F(i).name, '^CSC(\d+)\.ncs$', 'tokens', 'once');
    if isempty(t), continue; end
    ch = str2double(t{1});
    srcMap.(sprintf('c%d', ch)) = fullfile(leaf, F(i).name);
    presentCh(end+1) = ch; %#ok<AGROW>
end
presentCh = unique(presentCh);
end

function src = chooseSourceForEven(e, presentCh, badList)
% if even is bad or missing, take next odd (e+1). If not available, try e-1 once.
isBadEven = ismember(e, badList) || ~ismember(e, presentCh);
if ~isBadEven
    src = e; return;
end
cand = e + 1; % next odd
if mod(cand,2)==1 && ismember(cand, presentCh) && ~ismember(cand, badList)
    src = cand; return;
end
cand = e - 1; % previous odd as last resort
if cand>=1 && mod(cand,2)==1 && ismember(cand, presentCh) && ~ismember(cand, badList)
    src = cand; return;
end
src = NaN; % give up
end
