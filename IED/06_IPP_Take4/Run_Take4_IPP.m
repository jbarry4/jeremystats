function Run_Take4_IPP(inputParent, outputParent)
% Run_Take4_IPP
% Runs IPP_Combined_Pipeline on the 10 PTEN sessions in Take 3 and writes
% results to Take 4, one subfolder per session, plus a Collected_Results
% folder with all montages and a combined cross-session averages workbook.
%
% Usage:
%   Run_Take4_IPP("C:\Users\Z390\Desktop\IED DATA\Take 3", ...
%                 "C:\Users\Z390\Desktop\IED DATA\Take 4")

if nargin < 1 || strlength(string(inputParent))==0
    inputParent = "C:\Users\Z390\Desktop\IED DATA\Take 3";
end
if nargin < 2 || strlength(string(outputParent))==0
    outputParent = "C:\Users\Z390\Desktop\IED DATA\Take 4";
end
inputParent  = string(inputParent);
outputParent = string(outputParent);
if ~exist(outputParent,'dir'), mkdir(outputParent); end

collectedDir = fullfile(outputParent, 'Collected_Results');
if ~exist(collectedDir,'dir'), mkdir(collectedDir); end

% ---- The 10 sessions (folder names inside Take 3) ----
sessions = { ...
    'PTEN_M3_pten_m3s2sept20 (Handsorted)'; ...
    'PTEN_M3_pten_m3s7sept22 (Handsorted)'; ...
    'PTEN_M5_Pten_m5s2nov16'; ...
    'PTEN_M5_Pten_m5s7nov17'; ...
    'PTEN_M13_pten_m13s2aug1'; ...
    'PTEN_M13_pten_m13s17aug4'; ...
    'PTEN_m28_ptenblind_m28s2jun18'; ...
    'PTEN_m28_ptenblind_m28s7jun18 (Handsorted)'; ...
    'PTEN_M34_ptenblind_m34s5jun10'; ...
    'PTEN_M34_ptenblind_m34s8jun10 (w Neaurlynx fix)' ...
};

% ---- Baked-in per-session exceptions (name substring -> extra args) ----
% m13s17aug4 : anchorChannel 24, anchorHalfWidthMs 10e-3
% m5s7nov17  : anchorHalfWidthMs 20e-3
% everything else: defaults
    function extra = exceptionArgs(name)
        if contains(name, 'm13s17aug4', 'IgnoreCase', true)
            extra = {'anchorChannel', 24, 'anchorHalfWidthMs', 10e-3};
        elseif contains(name, 'm5s7nov17', 'IgnoreCase', true)
            extra = {'anchorHalfWidthMs', 20e-3};
        else
            extra = {};
        end
    end

allRes = {};
fprintf('\n############ Run_Take4_IPP START (%d sessions) ############\n', numel(sessions));

for i = 1:numel(sessions)
    name = sessions{i};
    inFolder = fullfile(inputParent, name);
    outFolder= fullfile(outputParent, name);
    fprintf('\n===== [%d/%d] %s =====\n', i, numel(sessions), name);

    if ~isfolder(inFolder)
        fprintf('  [SKIP] Session folder not found: %s\n', inFolder);
        continue;
    end
    if ~exist(outFolder,'dir'), mkdir(outFolder); end

    % Auto-detect data .mat (exclude ets.mat)
    mats = dir(fullfile(inFolder, '*.mat'));
    mats = mats(~startsWith({mats.name}, 'ets.mat', 'IgnoreCase', true));
    if isempty(mats)
        fprintf('  [SKIP] No data .mat found in %s\n', inFolder);
        continue;
    end
    dataMat = fullfile(mats(1).folder, mats(1).name);

    extra = exceptionArgs(name);
    if ~isempty(extra)
        parts = cell(1, numel(extra));
        for q = 1:numel(extra)
            if ischar(extra{q}) || isstring(extra{q})
                parts{q} = char(extra{q});
            else
                parts{q} = num2str(extra{q});
            end
        end
        fprintf('  [EXCEPTION] extra args: %s\n', strjoin(parts, ' '));
    end

    try
        res = IPP_Combined_Pipeline(inFolder, dataMat, ...
            'outputDir', outFolder, 'sessionName', name, extra{:});
        allRes{end+1} = res; %#ok<AGROW>
        fprintf('  [OK] %s\n', name);

        % Copy montages + workbook into Collected_Results
        copyIfExists(getf(res,'files','montage_SOLID'),   fullfile(collectedDir, [name '_Montage_SOLID.png']));
        copyIfExists(getf(res,'files','montage_SPUTTER'), fullfile(collectedDir, [name '_Montage_SPUTTER.png']));
        copyIfExists(getf(res,'valuesXlsx'),              fullfile(collectedDir, [name '_Values.xlsx']));
    catch ME
        fprintf('  [FAILED] %s : %s\n', name, ME.message);
        fprintf('    %s\n', getReport(ME, 'basic'));
    end
end

% ---- Combined cross-session averages workbook ----
try
    buildCombinedWorkbook(allRes, fullfile(collectedDir, 'ALL_SESSIONS_Averages.xlsx'));
catch ME
    warning('Failed to build combined workbook: %s', ME.message);
end

% ---- Merge all stats CSVs ----
try
    Tall = table();
    for i = 1:numel(allRes)
        sc = getf(allRes{i}, 'statsCSV');
        if strlength(string(sc))>0 && isfile(sc)
            Tall = vertcatSafe(Tall, readtable(sc, 'TextType','string'));
        end
    end
    if ~isempty(Tall)
        writetable(Tall, fullfile(collectedDir, 'ALL_SESSIONS_Stats.csv'));
        fprintf('\nSaved merged stats: %s\n', fullfile(collectedDir, 'ALL_SESSIONS_Stats.csv'));
    end
catch ME
    warning('Failed to merge stats: %s', ME.message);
end

fprintf('\n############ Run_Take4_IPP COMPLETE ############\n');
fprintf('Per-session output: %s\\<session>\\\n', outputParent);
fprintf('Collected results : %s\n', collectedDir);
end

% ================= HELPERS =================

function copyIfExists(src, dst)
    src = char(string(src));
    if ~isempty(src) && isfile(src)
        try, copyfile(src, dst); catch ME, warning('copy failed %s: %s', src, ME.message); end
    end
end

function v = getf(S, varargin)
    % Nested-safe field getter: getf(S,'a','b') -> S.a.b, or "" on any miss.
    cur = S;
    for k = 1:numel(varargin)
        key = varargin{k};
        if isstruct(cur) && isfield(cur, key)
            cur = cur.(key);
        else
            v = ""; return;
        end
    end
    v = cur;
end

function buildCombinedWorkbook(allRes, xlsxPath)
    if isempty(allRes), return; end
    if isfile(xlsxPath), delete(xlsxPath); end
    measures = {'CSD_IP','CSD_PP','Voltage_IP','Voltage_PP'};
    groups   = {'SOLID','SPUTTER'};

    % Use the channel list from the first result that has one
    chans = [];
    for i = 1:numel(allRes)
        if isfield(allRes{i},'channels') && ~isempty(allRes{i}.channels)
            chans = allRes{i}.channels; break;
        end
    end
    if isempty(chans), return; end
    nCh = numel(chans);

    for mi = 1:numel(measures)
        meas = measures{mi};
        header = {'Channel'};
        cols   = {};
        for i = 1:numel(allRes)
            R = allRes{i};
            if ~isfield(R,'avg'), continue; end
            sName = char(getf(R,'sessionName'));
            for gi = 1:numel(groups)
                fld = [meas '_' groups{gi}];
                if isfield(R.avg, fld)
                    v = R.avg.(fld);
                    if numel(v) == nCh
                        header{end+1} = sprintf('%s|%s', sName, groups{gi}); %#ok<AGROW>
                        cols{end+1}   = v(:); %#ok<AGROW>
                    end
                end
            end
        end
        if isempty(cols)
            C = [ {'Channel'}; num2cell(double(chans)) ];
        else
            body = [ num2cell(double(chans)), num2cell(cell2mat(cols)) ];
            C = [ header; body ];
        end
        writecell(C, xlsxPath, 'Sheet', meas);
    end
    fprintf('Saved combined workbook: %s\n', xlsxPath);
end

function T = vertcatSafe(A, B)
    if isempty(A), T = B; return; end
    if isempty(B), T = A; return; end
    allVars = union(A.Properties.VariableNames, B.Properties.VariableNames, 'stable');
    A = addMissingVars(A, allVars);
    B = addMissingVars(B, allVars);
    T = [A; B];
end

function T = addMissingVars(T, allVars)
    missingV = setdiff(allVars, T.Properties.VariableNames, 'stable');
    for k = 1:numel(missingV), T.(missingV{k}) = repmat(missing, height(T), 1); end
    T = T(:, allVars);
end
