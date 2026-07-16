function T = BuildBatchInputCSV_fromSheet(sheetPath, baseRoot, varargin)
% BuildBatchInputCSV_simple(sheetPath, baseRoot, ...)
% Minimal: only needs the sheet path and the base root.
% - outRoot: sibling of baseRoot named "LL_ready_outputs"
% - outCsvPath: "batch_input.csv" next to this script
%
% Optional Name-Value:
%   'maxDepth'   (Inf)
%   'verbose'    (true)
%   'outFolderName' ('LL_ready_outputs')   % sibling folder name
%   'csvName'       ('batch_input.csv')    % filename next to this script

ip = inputParser;
ip.addRequired('sheetPath', @(s)ischar(s)||isstring(s));
ip.addRequired('baseRoot',  @(s)ischar(s)||isstring(s));
ip.addParameter('maxDepth', Inf, @(x)isfinite(x)&&x>=1);
ip.addParameter('verbose',  true, @(x)islogical(x)||ismember(x,[0 1]));
ip.addParameter('outFolderName','LL_ready_outputs', @(s)ischar(s)||isstring(s));
ip.addParameter('csvName','batch_input.csv', @(s)ischar(s)||isstring(s));
ip.parse(sheetPath, baseRoot, varargin{:});
opts = ip.Results;

baseRoot = char(baseRoot);
if ~isfolder(baseRoot), error('Base folder not found: %s', baseRoot); end

% ---- Derive outRoot (sibling of baseRoot) and outCsvPath (next to script) ----
baseParent = fileparts(baseRoot);
if isempty(baseParent), baseParent = pwd; end
outRoot    = fullfile(baseParent, char(opts.outFolderName));
if ~isfolder(outRoot), mkdir(outRoot); end

scriptDir  = fileparts(mfilename('fullpath'));
if isempty(scriptDir), scriptDir = pwd; end
outCsvPath = fullfile(scriptDir, char(opts.csvName));
if ~isfolder(fileparts(outCsvPath)), mkdir(fileparts(outCsvPath)); end

if opts.verbose
    fprintf('Base root : %s\n', baseRoot);
    fprintf('Out root  : %s\n', outRoot);
    fprintf('CSV path  : %s\n', outCsvPath);
end

% ---------- Load sheet (flexible headers) ----------
Tsheet = readtable(sheetPath);
cn = lower(regexprep(string(Tsheet.Properties.VariableNames), '\s+', ''));
Tsheet.Properties.VariableNames = cellstr(cn);

col_mouse = find(ismember(cn, ["mouse_id","mouse","mouseid","animal","subject"]), 1);
col_sess  = find(ismember(cn, ["session","sess"]), 1);
col_bad   = find(ismember(cn, ["badchannel","badchannels","bad_channel","bad_channels","bad"]), 1);
if isempty(col_mouse) || isempty(col_sess)
    error('Sheet needs at least "mouse_id" and "session" columns.');
end

rows = struct('mouse_num',{},'session_num',{},'bad_channels',{}, ...
              'src_dir',{},'rel_path',{},'dst_dir',{},'out_mat',{});

for r = 1:height(Tsheet)
    mouse_id_raw = string(Tsheet{r, col_mouse});
    sess_raw     = Tsheet{r, col_sess};
    bad_raw      = ""; if ~isempty(col_bad), bad_raw = string(Tsheet{r, col_bad}); end

    % Parse m##
    mdig = regexp(lower(strtrim(mouse_id_raw)), 'm\s*0*(\d+)', 'tokens', 'once');
    if isempty(mdig), warning('Row %d: cannot parse mouse_id "%s". Skipping.', r, mouse_id_raw); continue; end
    mouseNum = str2double(mdig{1});

    % Parse s## or digits
    if ischar(sess_raw) || isstring(sess_raw)
        sdig = regexp(lower(string(sess_raw)), 's\s*0*(\d+)', 'tokens', 'once');
        if isempty(sdig), sdig = regexp(lower(string(sess_raw)), '0*(\d+)', 'tokens', 'once'); end
        if isempty(sdig), warning('Row %d: cannot parse session "%s". Skipping.', r, string(sess_raw)); continue; end
        sessNum = str2double(sdig{1});
    else
        sessNum = double(sess_raw);
    end

    % Bad list text
    badList = [];
    if strlength(strtrim(bad_raw))>0
        toks = regexp(char(bad_raw), '\d+', 'match');
        badList = unique(str2double(toks));
    end
    badTxt = strjoin(string(badList), ' ');

    if opts.verbose
        fprintf('\n[%3d/%3d] m%d | s%d | badList=%s\n', r, height(Tsheet), mouseNum, sessNum, badTxt);
    end

    % Find mouse dir (shallowest)
    mousePat  = sprintf('m0*%d(?!\\d)', mouseNum);
    mouseHits = findDirsNameContainsRegex(baseRoot, mousePat, opts.maxDepth);
    if isempty(mouseHits), warning('  m%d not found under baseRoot.', mouseNum); continue; end
    depths = cellfun(@(p) numel(strfind(p, filesep)), mouseHits);
    [~, ix] = sort(depths, 'ascend'); mouseHits = mouseHits(ix);

    % Find session dir(s)
    sessPat  = sprintf('s0*%d(?!\\d)', sessNum);
    sessHits = findDirsNameContainsRegex(mouseHits{1}, sessPat, opts.maxDepth);
    if isempty(sessHits), warning('  s%d not found under %s', sessNum, mouseHits{1}); continue; end

    % Collect recording dirs that contain CSC*.ncs
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
    if isempty(recDirs), warning('  No CSC*.ncs found under session path(s).'); continue; end

    % Emit rows
    for d = 1:numel(recDirs)
        srcDir  = recDirs{d};
        relPath = pathRelativeTo(srcDir, baseRoot);
        dstDir  = fullfile(outRoot, relPath);
        [~, leaf] = fileparts(srcDir);
        outFull = fullfile(dstDir, sprintf('LL_input_%s_uV.mat', leaf));

        rows(end+1) = struct( ... %#ok<AGROW>
            'mouse_num',    mouseNum, ...
            'session_num',  sessNum, ...
            'bad_channels', badTxt, ...
            'src_dir',      srcDir, ...
            'rel_path',     relPath, ...
            'dst_dir',      dstDir, ...
            'out_mat',      outFull );
    end
end

% Table + CSV
if isempty(rows)
    warning('No recording folders found. Writing empty CSV.');
    T = cell2table(cell(0,7), 'VariableNames', ...
        {'mouse_num','session_num','bad_channels','src_dir','rel_path','dst_dir','out_mat'});
else
    T = struct2table(rows);
end
writetable(T, outCsvPath);
fprintf('\nWrote %s (%d rows)\n', outCsvPath, height(T));
fprintf('Mirrored outputs would go under: %s\n', outRoot);

end % ===== main =====

% ---------------- Helpers ----------------
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
            if ~isKey(depth, sub), depth(sub) = curDepth + 1; end
            if ~isempty(regexpi(dd(k).name, nameRegex))
                hits{end+1} = sub; %#ok<AGROW>
            end
            if depth(sub) < maxDepth, q{end+1} = sub; end %#ok<AGROW>
        end
    end
    hits = unique(hits);
end

function rel = pathRelativeTo(p, root)
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
        pat = ['^', regexptranslate('escape', [rootCan filesep])];
        rel = regexprep(pCan, pat, '', 'ignorecase');
        if strcmp(rel, pCan), rel = pCan; end
    end
end
