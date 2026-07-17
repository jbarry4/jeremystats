function Run_Take4_IPP_v2(inputParent, outputParent)
% Run_Take4_IPP_v2
% Runs IPP_Combined_Pipeline_v2 (SOLID only, + Voltage IP/PP profiles) on the
% 10 PTEN sessions in Take 3 and writes results to Take 4\v2, one subfolder
% per session, plus a Collected_Results folder with all montages and a
% combined cross-session averages workbook.
%
% Usage:
%   Run_Take4_IPP_v2("C:\Users\Z390\Desktop\IED DATA\Take 3", ...
%                    "C:\Users\Z390\Desktop\IED DATA\Take 4\v2")

if nargin < 1 || strlength(string(inputParent))==0
    inputParent = "C:\Users\Z390\Desktop\IED DATA\Take 3";
end
if nargin < 2 || strlength(string(outputParent))==0
    outputParent = "C:\Users\Z390\Desktop\IED DATA\Take 4\v2";
end
inputParent  = string(inputParent);
outputParent = string(outputParent);
if ~exist(outputParent,'dir'), mkdir(outputParent); end

collectedDir = fullfile(outputParent, 'Collected_Results');
if ~exist(collectedDir,'dir'), mkdir(collectedDir); end

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

% Baked-in per-session exceptions (same as v1)
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
fprintf('\n############ Run_Take4_IPP_v2 START (%d sessions, SOLID only) ############\n', numel(sessions));

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
        res = IPP_Combined_Pipeline_v2(inFolder, dataMat, ...
            'outputDir', outFolder, 'sessionName', name, extra{:});
        allRes{end+1} = res; %#ok<AGROW>
        fprintf('  [OK] %s\n', name);

        copyIfExists(getf(res,'files','montage'), fullfile(collectedDir, [name '_Montage.png']));
        copyIfExists(getf(res,'valuesXlsx'),      fullfile(collectedDir, [name '_Values.xlsx']));
    catch ME
        fprintf('  [FAILED] %s : %s\n', name, ME.message);
        fprintf('    %s\n', getReport(ME, 'basic'));
    end
end

try
    buildCombinedWorkbook(allRes, fullfile(collectedDir, 'ALL_SESSIONS_Averages.xlsx'));
catch ME
    warning(ME.identifier, 'Failed to build combined workbook: %s', ME.message);
end

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
    warning(ME.identifier, 'Failed to merge stats: %s', ME.message);
end

fprintf('\n############ Run_Take4_IPP_v2 COMPLETE ############\n');
fprintf('Per-session output: %s\\<session>\\\n', outputParent);
fprintf('Collected results : %s\n', collectedDir);
end

% ================= HELPERS =================

function copyIfExists(src, dst)
    src = char(string(src));
    if ~isempty(src) && isfile(src)
        try, copyfile(src, dst); catch ME, warning(ME.identifier, 'copy failed %s: %s', src, ME.message); end
    end
end

function v = getf(S, varargin)
    cur = S;
    for k = 1:numel(varargin)
        key = varargin{k};
        if isstruct(cur) && isfield(cur, key), cur = cur.(key); else, v = ""; return; end
    end
    v = cur;
end

function buildCombinedWorkbook(allRes, xlsxPath)
    if isempty(allRes), return; end
    if isfile(xlsxPath), delete(xlsxPath); end
    measures = {'CSD_IP','CSD_PP','Voltage_IP','Voltage_PP'};

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
            if ~isfield(R,'avg') || ~isfield(R.avg, meas), continue; end
            v = R.avg.(meas);
            if numel(v) ~= nCh, continue; end
            header{end+1} = char(getf(R,'sessionName')); %#ok<AGROW>
            cols{end+1}   = v(:); %#ok<AGROW>
        end
        if isempty(cols)
            C = [ {'Channel'}; num2cell(double(chans)) ];
        else
            C = [ header; [num2cell(double(chans)), num2cell(cell2mat(cols))] ];
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
