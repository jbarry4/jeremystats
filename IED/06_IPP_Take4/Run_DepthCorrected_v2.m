function Run_DepthCorrected_v2(inputParent, outputParent)
% Run_DepthCorrected_v2
% Runs IPP_DepthCorrected_Pipeline (SOLID only) on the 10 PTEN sessions in
% Take 3 and writes DEPTH-CORRECTED results to Take 4\depth_corrected_v2,
% one subfolder per session, plus a Collected_Results folder with:
%   - all per-session montages + depth-corrected value workbooks
%   - a combined cross-session workbook of normalized-depth averages
%   - pooled grand-average IP/PP depth profiles by group (Base / CNO / All)
%
% Depth correction = region-specific linear interpolation of each IED's
% per-channel profile onto the Golden Template (same warp as the existing
% *_GrandAverage_Spatial_Norm.m), applied PER EVENT.
%
% Usage:
%   Run_DepthCorrected_v2("C:\Users\Z390\Desktop\IED DATA\Take 3", ...
%                         "C:\Users\Z390\Desktop\IED DATA\Take 4\depth_corrected_v2")

if nargin < 1 || strlength(string(inputParent))==0
    inputParent = "C:\Users\Z390\Desktop\IED DATA\Take 3";
end
if nargin < 2 || strlength(string(outputParent))==0
    outputParent = "C:\Users\Z390\Desktop\IED DATA\Take 4\depth_corrected_v2";
end
inputParent  = string(inputParent);
outputParent = string(outputParent);
if ~exist(outputParent,'dir'), mkdir(outputParent); end

collectedDir = fullfile(outputParent, 'Collected_Results');
if ~exist(collectedDir,'dir'), mkdir(collectedDir); end

goldenTemplate = fullfile(inputParent, 'Golden_Template_Full_Probe.xlsx');

% session folder name  ->  {shortId, group}
sessions = { ...
    'PTEN_M3_pten_m3s2sept20 (Handsorted)',            'm3s2',   'Base'; ...
    'PTEN_M3_pten_m3s7sept22 (Handsorted)',            'm3s7',   'CNO';  ...
    'PTEN_M5_Pten_m5s2nov16',                          'm5s2',   'Base'; ...
    'PTEN_M5_Pten_m5s7nov17',                          'm5s7',   'CNO';  ...
    'PTEN_M13_pten_m13s2aug1',                         'm13s2',  'Base'; ...
    'PTEN_M13_pten_m13s17aug4',                        'm13s17', 'CNO';  ...
    'PTEN_m28_ptenblind_m28s2jun18',                   'm28s2',  'Base'; ...
    'PTEN_m28_ptenblind_m28s7jun18 (Handsorted)',      'm28s7',  'CNO';  ...
    'PTEN_M34_ptenblind_m34s5jun10',                   'm34s5',  'Base'; ...
    'PTEN_M34_ptenblind_m34s8jun10 (w Neaurlynx fix)', 'm34s8',  'CNO'   ...
};

% Baked-in per-session anchor exceptions (same as v1/v2)
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
fprintf('\n############ Run_DepthCorrected_v2 START (%d sessions, SOLID only) ############\n', size(sessions,1));

for i = 1:size(sessions,1)
    name    = sessions{i,1};
    shortId = sessions{i,2};
    grp     = sessions{i,3};
    inFolder = fullfile(inputParent, name);
    outFolder= fullfile(outputParent, name);
    fprintf('\n===== [%d/%d] %s (%s, %s) =====\n', i, size(sessions,1), name, shortId, grp);

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
            if ischar(extra{q}) || isstring(extra{q}), parts{q} = char(extra{q});
            else, parts{q} = num2str(extra{q}); end
        end
        fprintf('  [EXCEPTION] extra args: %s\n', strjoin(parts, ' '));
    end

    try
        res = IPP_DepthCorrected_Pipeline(inFolder, dataMat, ...
            'outputDir', outFolder, 'sessionName', name, ...
            'goldenTemplate', goldenTemplate, ...
            'shortId', shortId, 'groupLabel', grp, extra{:});
        allRes{end+1} = res; %#ok<AGROW>
        fprintf('  [OK] %s\n', name);

        copyIfExists(getf(res,'files','montage'), fullfile(collectedDir, [name '_Montage.png']));
        copyIfExists(getf(res,'valuesXlsx'),      fullfile(collectedDir, [name '_DepthCorrected_Values.xlsx']));
    catch ME
        fprintf('  [FAILED] %s : %s\n', name, ME.message);
        fprintf('    %s\n', getReport(ME, 'basic'));
    end
end

% ---- Combined cross-session workbook of normalized-depth averages ----
try
    buildCombinedWorkbook(allRes, fullfile(collectedDir, 'ALL_SESSIONS_DepthCorrected_Averages.xlsx'));
catch ME
    warning(ME.identifier, 'Failed to build combined workbook: %s', ME.message);
end

% ---- Pooled grand-average depth profiles by group ----
try
    buildGrandAverages(allRes, collectedDir);
catch ME
    warning(ME.identifier, 'Failed to build grand averages: %s', ME.message);
end

% ---- Merge stats ----
try
    Tall = table();
    for i = 1:numel(allRes)
        sc = getf(allRes{i}, 'statsCSV');
        if strlength(string(sc))>0 && isfile(sc)
            Tall = vertcatSafe(Tall, readtable(sc, 'TextType','string'));
        end
    end
    if ~isempty(Tall)
        writetable(Tall, fullfile(collectedDir, 'ALL_SESSIONS_DepthCorrected_Stats.csv'));
        fprintf('\nSaved merged stats: %s\n', fullfile(collectedDir, 'ALL_SESSIONS_DepthCorrected_Stats.csv'));
    end
catch ME
    warning(ME.identifier, 'Failed to merge stats: %s', ME.message);
end

fprintf('\n############ Run_DepthCorrected_v2 COMPLETE ############\n');
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

function [refIdx] = firstWithLayout(allRes)
    refIdx = 0;
    for i = 1:numel(allRes)
        if isfield(allRes{i},'rowRegion') && ~isempty(allRes{i}.rowRegion)
            refIdx = i; return;
        end
    end
end

function buildCombinedWorkbook(allRes, xlsxPath)
    if isempty(allRes), return; end
    if isfile(xlsxPath), delete(xlsxPath); end
    measures = {'CSD_IP','CSD_PP','Voltage_IP','Voltage_PP'};

    ri = firstWithLayout(allRes);
    if ri == 0, return; end
    rowRegion = allRes{ri}.rowRegion;
    nNorm = numel(rowRegion);

    for mi = 1:numel(measures)
        meas = measures{mi};
        header = {'DepthIndex','Region'};
        cols   = {};
        for i = 1:numel(allRes)
            R = allRes{i};
            if ~isfield(R,'avg') || ~isfield(R.avg, meas), continue; end
            if ~isfield(R,'rowRegion') || numel(R.rowRegion) ~= nNorm, continue; end
            v = R.avg.(meas);
            if numel(v) ~= nNorm, continue; end
            header{end+1} = char(getf(R,'sessionName')); %#ok<AGROW>
            cols{end+1}   = v(:); %#ok<AGROW>
        end
        left = [num2cell((1:nNorm).'), rowRegion(:)];
        if isempty(cols)
            C = [ {'DepthIndex','Region'}; left ];
        else
            C = [ header; [left, num2cell(cell2mat(cols))] ];
        end
        writecell(C, xlsxPath, 'Sheet', meas);
    end
    fprintf('Saved combined workbook: %s\n', xlsxPath);
end

function buildGrandAverages(allRes, collectedDir)
    if isempty(allRes), return; end
    ri = firstWithLayout(allRes);
    if ri == 0, return; end
    rowRegion = allRes{ri}.rowRegion;
    regNames  = allRes{ri}.regNames;
    regThick  = allRes{ri}.regThick;
    nNorm     = numel(rowRegion);

    measures = {'CSD_IP','CSD_PP','Voltage_IP','Voltage_PP'};
    unitOf   = containers.Map({'CSD_IP','CSD_PP','Voltage_IP','Voltage_PP'}, ...
                              {'a.u.','a.u.','\muV','\muV'});
    groups = {'Base','CNO','All'};

    % Pool per-event depth-corrected columns across sessions.
    xlsxPath = fullfile(collectedDir, 'GRAND_AVERAGE_DepthCorrected.xlsx');
    if isfile(xlsxPath), delete(xlsxPath); end

    for mi = 1:numel(measures)
        meas = measures{mi};
        header = {'DepthIndex','Region'};
        cols = {}; colHdr = {};
        muByGroup = struct();

        for gi = 1:numel(groups)
            grp = groups{gi};
            pooled = [];
            for i = 1:numel(allRes)
                R = allRes{i};
                if ~isfield(R,'events') || ~isfield(R.events, meas), continue; end
                if ~isfield(R,'rowRegion') || numel(R.rowRegion) ~= nNorm, continue; end
                if ~strcmp(grp,'All') && ~strcmpi(char(getf(R,'groupLabel')), grp), continue; end
                M = R.events.(meas);
                if isempty(M) || size(M,1) ~= nNorm, continue; end
                pooled = [pooled, M]; %#ok<AGROW>
            end
            if isempty(pooled)
                mu = nan(nNorm,1); n = 0;
            else
                mu = mean(pooled, 2, 'omitnan'); n = size(pooled,2);
            end
            muByGroup.(grp) = mu;
            header{end+1} = sprintf('%s_mean(n=%d)', grp, n); %#ok<AGROW>
            cols{end+1} = mu; %#ok<AGROW>
            colHdr{end+1} = grp; %#ok<AGROW>
        end

        left = [num2cell((1:nNorm).'), rowRegion(:)];
        C = [ header; [left, num2cell(cell2mat(cols))] ];
        writecell(C, xlsxPath, 'Sheet', meas);

        % Figure: grand-average profile lines (Base vs CNO) over depth
        renderGrandProfile(muByGroup, regNames, regThick, nNorm, meas, unitOf(meas), ...
            fullfile(collectedDir, sprintf('GrandAvg_%s.png', meas)), ...
            fullfile(collectedDir, sprintf('GrandAvg_%s.pdf', meas)));
    end
    fprintf('Saved grand-average workbook + figures in %s\n', collectedDir);
end

function renderGrandProfile(muByGroup, regNames, regThick, nNorm, measLabel, unitStr, outPng, outPdf)
    cum = cumsum(regThick(:).');
    starts = [0, cum(1:end-1)];
    ctrs = starts + regThick(:).'/2 + 0.5;
    bnds = cum(1:end-1) + 0.5;

    f = figure('Color','w','Position',[80 80 620 900],'Visible','off');
    ax = axes('Parent', f); hold(ax,'on'); box(ax,'off');
    yv = (1:nNorm).';
    hLines = []; hLabels = {};
    colBase = [0.10 0.35 0.85]; colCNO = [0.85 0.20 0.15];
    if isfield(muByGroup,'Base') && any(isfinite(muByGroup.Base))
        h = plot(ax, muByGroup.Base, yv, '-', 'Color', colBase, 'LineWidth', 2.2);
        hLines(end+1)=h; hLabels{end+1}='Base'; %#ok<AGROW>
    end
    if isfield(muByGroup,'CNO') && any(isfinite(muByGroup.CNO))
        h = plot(ax, muByGroup.CNO, yv, '-', 'Color', colCNO, 'LineWidth', 2.2);
        hLines(end+1)=h; hLabels{end+1}='CNO'; %#ok<AGROW>
    end
    xline(ax, 0, '--k');
    for b = 1:numel(bnds), yline(ax, bnds(b), '-', 'Color', [0.7 0.7 0.7], 'LineWidth', 0.6); end
    set(ax,'YDir','reverse','YLim',[0.5 nNorm+0.5],'TickDir','out','FontSize',12,'Layer','top');
    yticks(ax, ctrs); yticklabels(ax, regNames); set(ax,'TickLabelInterpreter','none');
    ylabel(ax,'Anatomical region (normalized depth)','FontWeight','bold');
    xlabel(ax, sprintf('%s (%s)', measLabel, unitStr),'FontWeight','bold');
    title(ax, sprintf('Grand-average depth profile: %s', measLabel), 'Interpreter','none','FontWeight','bold');
    if ~isempty(hLines), legend(ax, hLines, hLabels, 'Location','best'); end
    exportgraphics(f, outPng, 'Resolution', 300);
    try, exportgraphics(f, outPdf, 'ContentType','vector'); catch, end
    close(f);
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
