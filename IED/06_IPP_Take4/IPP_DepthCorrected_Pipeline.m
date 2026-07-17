function res = IPP_DepthCorrected_Pipeline(inputFolder, dataMatPath, varargin)
% IPP_DepthCorrected_Pipeline
% -------------------------------------------------------------------------
% Per-IED depth-profile analysis WITH anatomical depth correction.
%
% For every SOLID IED event this:
%   1) finds ONE anchor (same logic as IPP_Combined_Pipeline_v2),
%   2) time-averages CSD and Voltage over two windows relative to the anchor
%          IP : [-1, +1] ms      PP : [+2, +10] ms
%      giving a per-channel value profile for EACH event (channel space),
%   3) DEPTH-CORRECTS that per-event profile by region-specific linear
%      interpolation onto a "Golden Template" of canonical layer thicknesses
%      (same warp method as CSDRaster/VoltageRaster_GrandAverage_Spatial_Norm.m),
%      so every event/session lives on a common anatomical depth axis.
%
% This is the SAME spatial-normalization used for the grand-average rasters,
% but applied PER IED EVENT rather than to a session-averaged raster.
%
% OUTPUTS (written into <outputDir>):
%   Figures (PNG + PDF), all on the normalized anatomical depth axis:
%     CSD_IP / CSD_PP                (waveform + per-event heatmap)
%     Voltage_IP / Voltage_PP        (waveform + per-event heatmap)
%     Voltage_Raster_DepthCorrected  (time x normalized-depth, event-avg)
%     Montage                        (Raster | CSD IP | CSD PP | Volt IP | Volt PP)
%   Spreadsheet (4 sheets), per-event depth-corrected values + average column:
%     <sessionName>_DepthCorrected_Values.xlsx
%        -> CSD_IP  CSD_PP  Voltage_IP  Voltage_PP
%        (rows = normalized depth bins, with Region label column)
%   Stats:
%     <sessionName>_DepthCorrected_stats.csv
%
% Depth-correction parameters:
%   'anatCsv'        ("")    : channel->region CSV (Row,Region). Auto-found in
%                              inputFolder (*anatomical*detail*.csv) if empty.
%   'goldenTemplate' ("")    : Golden_Template_Full_Probe.xlsx. Defaults to the
%                              copy shipped next to this script's Take 3 root.
%   'cropToInternal' (true)  : keep only CA1 SLM .. DG OML2 (drop buffers).
%   'groupLabel'     ("")    : Base | CNO (metadata only).
%   'shortId'        ("")    : e.g. m13s2 (metadata only; auto from folder).
%
% Anchor parameters (shared by all measures), identical to v2:
%   'anchorMidpoint' (false) : use event midpoint, skip peak search
%   'anchorChannel'  (0)     : matrix row for anchor search (0 = last channel)
%   'anchorPolarity' ('pos') : 'pos' | 'neg' | 'abs'

% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('excelPath', "", @(s)ischar(s)||isstring(s));
p.addParameter('outputDir', "", @(s)ischar(s)||isstring(s));
p.addParameter('sessionName', "", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));

p.addParameter('winHalfWidthMs',   20e-3, @(x)isfinite(x)&&x>0);
p.addParameter('anchorHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);

p.addParameter('ipStartMs', -1e-3, @(x)isfinite(x));
p.addParameter('ipEndMs',    1e-3, @(x)isfinite(x));
p.addParameter('ppStartMs',  2e-3, @(x)isfinite(x));
p.addParameter('ppEndMs',   10e-3, @(x)isfinite(x));

p.addParameter('sliceThickness', 6, @(x)isfinite(x) && x>=1 && mod(x,1)==0);
p.addParameter('robustPct',    99.5, @(x) isfinite(x) && x>0 && x<100);
p.addParameter('padFrac',       0.12, @(x) isfinite(x) && x>=0 && x<=0.5);
p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('absoluteClimCSD',  [], @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('climMicroV',       [], @(x) isempty(x) || (isscalar(x) && x>0));

p.addParameter('anchorMidpoint', false, @(x)islogical(x)||ismember(x,[0 1]));
p.addParameter('anchorChannel', 0, @(x)isscalar(x)&&isnumeric(x)&&x>=0);
p.addParameter('anchorPolarity', 'pos', @(s) any(validatestring(s, {'pos','neg','abs'})));

% depth-correction specific
p.addParameter('anatCsv', "", @(s)ischar(s)||isstring(s));
p.addParameter('goldenTemplate', "", @(s)ischar(s)||isstring(s));
p.addParameter('cropToInternal', true, @(x)islogical(x)||ismember(x,[0 1]));
p.addParameter('groupLabel', "", @(s)ischar(s)||isstring(s));
p.addParameter('shortId', "", @(s)ischar(s)||isstring(s));

p.parse(inputFolder, dataMatPath, varargin{:});
inputFolder    = string(p.Results.inputFolder);
dataMatPath    = string(p.Results.dataMatPath);
excelPath      = string(p.Results.excelPath);
outputDir      = string(p.Results.outputDir);
sessionName    = string(p.Results.sessionName);
channelIdx     = p.Results.channelIndices;
scaleToMicroV  = p.Results.scaleToMicroV;
winHWms        = p.Results.winHalfWidthMs;
anchorHWms     = p.Results.anchorHalfWidthMs;
ipStartMs      = p.Results.ipStartMs;
ipEndMs        = p.Results.ipEndMs;
ppStartMs      = p.Results.ppStartMs;
ppEndMs        = p.Results.ppEndMs;
sliceThick     = p.Results.sliceThickness;
robPct         = p.Results.robustPct;
padFrac        = p.Results.padFrac;
maxEventsPer   = p.Results.maxEventsPerGroup;
absClimCSD     = p.Results.absoluteClimCSD;
climMicroVOpt  = p.Results.climMicroV;
anchorMidpoint = p.Results.anchorMidpoint;
anchorChannel  = p.Results.anchorChannel;
anchorPolarity = p.Results.anchorPolarity;
anatCsv        = string(p.Results.anatCsv);
goldenTemplate = string(p.Results.goldenTemplate);
cropInternal   = logical(p.Results.cropToInternal);
groupLabel     = string(p.Results.groupLabel);
shortId        = string(p.Results.shortId);

% ---------------- Layout & IO ----------------
solidDir = fullfile(inputFolder, "Solid");
assert(isfolder(solidDir), 'Missing folder: %s', solidDir);

if excelPath == ""
    xl = dir(fullfile(inputFolder, "*.xlsx"));
    xl = xl(~startsWith({xl.name}, '~$'));
    assert(~isempty(xl), 'No Excel file (*.xlsx) found in %s', inputFolder);
    excelPath = fullfile(xl(1).folder, xl(1).name);
end
assert(isfile(excelPath), 'Excel not found: %s', excelPath);

if outputDir == "", outputDir = inputFolder; end
if ~exist(outputDir,'dir'), mkdir(outputDir); end
if sessionName == ""
    [~, sessionName] = fileparts(char(inputFolder));
    sessionName = string(sessionName);
end
if shortId == ""
    m = regexp(lower(char(sessionName)), 'm\d+s\d+', 'match', 'once');
    if ~isempty(m), shortId = string(m); end
end

% ---------------- Anatomy (channel -> region) ----------------
if anatCsv == ""
    ac = dir(fullfile(inputFolder, "*anatomical*detail*.csv"));
    assert(~isempty(ac), 'No anatomical detail CSV found in %s', inputFolder);
    anatCsv = fullfile(ac(1).folder, ac(1).name);
end
assert(isfile(anatCsv), 'Anatomy CSV not found: %s', anatCsv);
RegMap = loadRegionMap(anatCsv);   % containers.Map region -> [minChan maxChan]
fprintf('Anatomy: %s (%d labeled regions)\n', anatCsv, RegMap.Count);

% ---------------- Golden Template ----------------
if goldenTemplate == ""
    % default: <two levels up from Take 3 session>\Golden_Template_Full_Probe.xlsx
    guess = fullfile(fileparts(char(inputFolder)), 'Golden_Template_Full_Probe.xlsx');
    if isfile(guess), goldenTemplate = string(guess); end
end
assert(goldenTemplate ~= "" && isfile(goldenTemplate), ...
    'Golden template not found. Pass ''goldenTemplate'',<path>.');
try
    T_gold = readtable(goldenTemplate, 'Sheet', 'Golden_Template');
catch
    T_gold = readtable(goldenTemplate, 'Sheet', 1);
end
fprintf('Golden template: %s (sum=%d ch)\n', goldenTemplate, sum(T_gold.Target_Thickness));

% ---------------- Data ----------------
assert(isfile(dataMatPath), 'Data MAT not found: %s', dataMatPath);
mf = matfile(dataMatPath);
try sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRowsAll = size(mf,'d',1);
nSamp    = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end

if isempty(channelIdx)
    chList = 1:nRowsAll;
else
    chList = channelIdx(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);
assert(nCh > 0, 'No valid channels selected.');

if isempty(kept_channels)
    actualChans = chList;
else
    actualChans = kept_channels(chList);
end
actualChans = double(actualChans(:).');      % physical channel numbers (e.g. 2:2:64)
chanLabels = arrayfun(@(k) sprintf('%d', actualChans(k)), 1:nCh, 'UniformOutput', false);

if numel(scaleToMicroV)==1
    scaleVec = repmat(scaleToMicroV, nRowsAll, 1);
else
    assert(numel(scaleToMicroV) >= nRowsAll, 'scaleToMicroV must be scalar or length >= nRowsAll.');
    scaleVec = scaleToMicroV(:);
end

% ---------------- Windows ----------------
HWwin    = max(1, round(winHWms    * sfx));
HWanchor = max(1, round(anchorHWms * sfx));
tRelMs   = (-HWwin:HWwin) / sfx * 1e3;
winN     = numel(tRelMs);
centerIdx= HWwin + 1;

[ipI0, ipI1] = winIdx(ipStartMs, ipEndMs);
[ppI0, ppI1] = winIdx(ppStartMs, ppEndMs);
ipLabel = sprintf('[%+.0f, %+.0f] ms', 1e3*ipStartMs, 1e3*ipEndMs);
ppLabel = sprintf('[%+.0f, %+.0f] ms', 1e3*ppStartMs, 1e3*ppEndMs);

fprintf('IPP_DepthCorrected (SOLID only): sfx=%.1f Hz | IP %s | PP %s | win +/-%.1f ms\n', ...
    sfx, ipLabel, ppLabel, 1e3*HWwin/sfx);

% ---------------- Excel -> sample indices ----------------
T = readtable(excelPath, 'ReadVariableNames', true);
canon = lower(regexprep(T.Properties.VariableNames, '[^a-zA-Z0-9]', ''));
i_onSamp  = find(strcmp(canon,'onsamp')  | strcmp(canon,'startsample') | strcmp(canon,'startsamp') | strcmp(canon,'on'), 1);
i_offSamp = find(strcmp(canon,'offsamp') | strcmp(canon,'endsample')   | strcmp(canon,'endsamp')   | strcmp(canon,'off'), 1);
i_onSec   = find(strcmp(canon,'onsec')   | strcmp(canon,'startsec')    | strcmp(canon,'onsecs'), 1);
i_offSec  = find(strcmp(canon,'offsec')  | strcmp(canon,'endsec')      | strcmp(canon,'offsecs'), 1);

if ~isempty(i_onSamp) && ~isempty(i_offSamp)
    onSamp  = double(T{:, i_onSamp});
    offSamp = double(T{:, i_offSamp});
elseif ~isempty(i_onSec) && ~isempty(i_offSec)
    onSamp  = round(double(T{:, i_onSec})  * sfx);
    offSamp = round(double(T{:, i_offSec}) * sfx);
else
    assert(width(T) >= 2, 'Excel must have [on_samp, off_samp] or [on_sec, off_sec].');
    onSamp  = double(T{:,1});
    offSamp = double(T{:,2});
end
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));
NrowsXL = numel(onSamp);

% ---------------- Events (SOLID only) ----------------
evtSOL = parseEvtNumsFromPngs(solidDir);
fprintf('Found %d SOLID events (by filenames).\n', numel(evtSOL));
if ~isempty(maxEventsPer) && ~isempty(evtSOL)
    evtSOL = evtSOL(1:min(end, maxEventsPer));
end

% ---------------- Compute SOLID group (channel space) ----------------
Gd = computeGroup(evtSOL, 'SOLID');

% ---------------- Depth-correct each per-event profile ----------------
% Build the normalized-depth layout once (region names / thicknesses kept).
[~, rowRegion, regNames, regThick] = warpProfileToTemplate(zeros(nCh,1), ...
    RegMap, T_gold, actualChans, cropInternal);
nNorm = numel(rowRegion);

DC = struct();
DC.CSD_IP     = warpProfileToTemplate(Gd.CSD_IP, RegMap, T_gold, actualChans, cropInternal);
DC.CSD_PP     = warpProfileToTemplate(Gd.CSD_PP, RegMap, T_gold, actualChans, cropInternal);
DC.Voltage_IP = warpProfileToTemplate(Gd.V_IP,   RegMap, T_gold, actualChans, cropInternal);
DC.Voltage_PP = warpProfileToTemplate(Gd.V_PP,   RegMap, T_gold, actualChans, cropInternal);
if isempty(Gd.Vrast)
    DC.Vrast = [];
else
    DC.Vrast = warpProfileToTemplate(Gd.Vrast, RegMap, T_gold, actualChans, cropInternal);
end

% ---------------- CLim per measure ----------------
climCSD_IP = pickClim(absClimCSD,   {DC.CSD_IP});
climCSD_PP = pickClim(absClimCSD,   {DC.CSD_PP});
climVrast  = pickClim(climMicroVOpt,{DC.Vrast});
climV_IP   = pickClim(climMicroVOpt,{DC.Voltage_IP});
climV_PP   = pickClim(climMicroVOpt,{DC.Voltage_PP});

% ---------------- Render figures ----------------
res = struct();
res.sessionName = sessionName;
res.shortId     = shortId;
res.groupLabel  = groupLabel;
files = struct('ipCsd',"", 'ppCsd',"", 'ipVolt',"", 'ppVolt',"", 'volt',"", 'montage',"");

if Gd.nEvt == 0
    fprintf('(SOLID) no usable events -> skipping figures.\n');
else
    ipCsdPng = fullfile(outputDir, 'CSD_IP.png');   ipCsdPdf = fullfile(outputDir, 'CSD_IP.pdf');
    ppCsdPng = fullfile(outputDir, 'CSD_PP.png');   ppCsdPdf = fullfile(outputDir, 'CSD_PP.pdf');
    ipVPng   = fullfile(outputDir, 'Voltage_IP.png');   ipVPdf = fullfile(outputDir, 'Voltage_IP.pdf');
    ppVPng   = fullfile(outputDir, 'Voltage_PP.png');   ppVPdf = fullfile(outputDir, 'Voltage_PP.pdf');
    vPng     = fullfile(outputDir, 'Voltage_Raster_DepthCorrected.png'); vPdf = fullfile(outputDir, 'Voltage_Raster_DepthCorrected.pdf');
    montPng  = fullfile(outputDir, 'Montage.png');

    renderSlicesDepth(DC.CSD_IP, 'CSD',     'a.u.',  ['IP  ' ipLabel], climCSD_IP, ipCsdPng, ipCsdPdf);
    renderSlicesDepth(DC.CSD_PP, 'CSD',     'a.u.',  ['PP  ' ppLabel], climCSD_PP, ppCsdPng, ppCsdPdf);
    renderSlicesDepth(DC.Voltage_IP, 'Voltage', '\muV',  ['IP  ' ipLabel], climV_IP,   ipVPng,   ipVPdf);
    renderSlicesDepth(DC.Voltage_PP, 'Voltage', '\muV',  ['PP  ' ppLabel], climV_PP,   ppVPng,   ppVPdf);
    renderVoltRasterDepth(DC.Vrast, climVrast, vPng, vPdf);

    try
        composeRowHiRes({char(vPng), char(ipCsdPng), char(ppCsdPng), char(ipVPng), char(ppVPng)}, char(montPng), 12);
    catch ME
        warning(ME.identifier, 'Montage failed: %s', ME.message); montPng = "";
    end

    files.ipCsd = ipCsdPng; files.ppCsd = ppCsdPng;
    files.ipVolt = ipVPng;  files.ppVolt = ppVPng;
    files.volt = vPng;      files.montage = montPng;
end
res.files = files;

% ---------------- 4-sheet workbook (depth-corrected) ----------------
xlsxPath = fullfile(outputDir, sprintf('%s_DepthCorrected_Values.xlsx', sessionName));
if isfile(xlsxPath), delete(xlsxPath); end
writeSheet(xlsxPath, 'CSD_IP',     DC.CSD_IP);
writeSheet(xlsxPath, 'CSD_PP',     DC.CSD_PP);
writeSheet(xlsxPath, 'Voltage_IP', DC.Voltage_IP);
writeSheet(xlsxPath, 'Voltage_PP', DC.Voltage_PP);
res.valuesXlsx = xlsxPath;
fprintf('Saved 4-sheet depth-corrected workbook: %s\n', xlsxPath);

% ---------------- Stats CSV ----------------
statsCSV = fullfile(outputDir, sprintf('%s_DepthCorrected_stats.csv', sessionName));
St = table(string(sessionName), string(shortId), string(groupLabel), string('SOLID'), Gd.nEvt, nCh, nNorm, sfx, ...
    climCSD_IP, climCSD_PP, climVrast, climV_IP, climV_PP, ...
    string(ipLabel), string(ppLabel), logical(cropInternal), ...
    logical(anchorMidpoint), anchorChannel, string(anchorPolarity), 1e3*anchorHWms, ...
    'VariableNames', {'Session','ShortID','Group','Type','Events','InputChannels','NormDepthBins','SampRateHz', ...
    'CLim_CSD_IP','CLim_CSD_PP','CLim_Volt_Raster_uV','CLim_Volt_IP_uV','CLim_Volt_PP_uV', ...
    'IP_Window','PP_Window','CropToInternal','AnchorMidpoint','AnchorChannelRow','AnchorPolarity','AnchorHalfWidth_ms'});
try
    writetable(St, statsCSV);
    res.statsCSV = statsCSV;
catch ME
    warning(ME.identifier, 'Failed to write stats CSV: %s', ME.message);
    res.statsCSV = "";
end

% ---------------- Normalized-depth averages (for combined workbook) ----------------
res.normDepthIndex = (1:nNorm).';
res.rowRegion      = rowRegion(:);
res.regNames       = regNames(:);
res.regThick       = regThick(:);
res.nEvt           = Gd.nEvt;
res.avg = struct();
res.avg.CSD_IP     = meanCol(DC.CSD_IP, nNorm);
res.avg.CSD_PP     = meanCol(DC.CSD_PP, nNorm);
res.avg.Voltage_IP = meanCol(DC.Voltage_IP, nNorm);
res.avg.Voltage_PP = meanCol(DC.Voltage_PP, nNorm);
% Also keep per-event depth-corrected matrices (for pooled grand averages).
res.events = DC;

% ================= NESTED HELPERS =================

    function [i0, i1] = winIdx(startMs, endMs)
        i0 = centerIdx + round(startMs * sfx);
        i1 = centerIdx + round(endMs   * sfx);
        i0 = max(1, min(i0, winN));
        i1 = max(1, min(i1, winN));
        if i1 < i0, [i0, i1] = deal(i1, i0); end
    end

    function Gd = computeGroup(evtList, tag)
        Gd = struct('nEvt',0,'evtIds',[], ...
            'CSD_IP',zeros(nCh,0),'CSD_PP',zeros(nCh,0), ...
            'V_IP',zeros(nCh,0),'V_PP',zeros(nCh,0), 'Vrast',[]);
        if isempty(evtList), return; end

        nE   = numel(evtList);
        CIP  = nan(nCh, nE); CPP = nan(nCh, nE);
        VIP  = nan(nCh, nE); VPP = nan(nCh, nE);
        sumV = zeros(nCh, winN);
        used = false(nE,1);
        anchorDesc = "";

        for ii = 1:nE
            rowXL = evtList(ii);
            if rowXL < 1 || rowXL > NrowsXL, continue; end
            s0_ev = round(onSamp(rowXL));
            s1_ev = round(offSamp(rowXL));
            if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev), continue; end

            ancMid = round((s0_ev + s1_ev)/2);
            if anchorMidpoint == true
                anchor = ancMid;
                if ii==1, anchorDesc = "Event Midpoint"; end
            else
                if anchorChannel == 0
                    refCh = chList(end);
                elseif anchorChannel < 1 || anchorChannel > nRowsAll || ~any(chList == anchorChannel)
                    refCh = chList(end);
                else
                    refCh = anchorChannel;
                end
                if ii==1, anchorDesc = sprintf('%s peak on row %d (+/-%.1f ms)', anchorPolarity, refCh, 1e3*anchorHWms); end
                s0a = max(1, ancMid - HWanchor);
                s1a = min(nSamp, ancMid + HWanchor);
                y0  = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
                if isempty(y0) || all(~isfinite(y0)), continue; end
                switch anchorPolarity
                    case 'pos', [~, k_rel] = max(y0);
                    case 'neg', [~, k_rel] = min(y0);
                    case 'abs', [~, k_rel] = max(abs(y0));
                    otherwise,  [~, k_rel] = max(y0);
                end
                anchor = s0a + k_rel - 1;
            end
            if ii==1, fprintf('(%s) Align: %s\n', tag, anchorDesc); end

            s0 = anchor - HWwin; s1 = anchor + HWwin;
            if s0 < 1 || s1 > nSamp, continue; end

            Y = nan(nCh, winN);
            for k = 1:nCh
                ch = chList(k);
                Y(k,:) = double(mf.d(ch, s0:s1)) * scaleVec(ch);
            end
            if all(~isfinite(Y(:))), continue; end

            C = computeCSD(Y);

            CIP(:,ii) = mean(C(:, ipI0:ipI1), 2, 'omitnan');
            CPP(:,ii) = mean(C(:, ppI0:ppI1), 2, 'omitnan');
            VIP(:,ii) = mean(Y(:, ipI0:ipI1), 2, 'omitnan');
            VPP(:,ii) = mean(Y(:, ppI0:ppI1), 2, 'omitnan');

            Yz = Y; Yz(~isfinite(Yz)) = 0;
            sumV = sumV + Yz;
            used(ii) = true;
        end

        if ~any(used), return; end
        Gd.nEvt   = sum(used);
        Gd.evtIds = evtList(used);
        Gd.CSD_IP = CIP(:,used);
        Gd.CSD_PP = CPP(:,used);
        Gd.V_IP   = VIP(:,used);
        Gd.V_PP   = VPP(:,used);
        Gd.Vrast  = sumV / Gd.nEvt;
    end

    function clim = pickClim(absOpt, mats)
        if ~isempty(absOpt), clim = absOpt; return; end
        vals = [];
        for m = 1:numel(mats)
            v = mats{m}; if isempty(v), continue; end
            vals = [vals; abs(v(:))]; %#ok<AGROW>
        end
        vals = vals(isfinite(vals));
        if isempty(vals), clim = 1; else, clim = (1+padFrac) * max(1, prctile(vals, robPct)); end
    end

    % ---- depth-corrected "slices" figure: waveform + per-event heatmap ----
    function renderSlicesDepth(S, measLabel, unitStr, winLabel, clim, outPng, outPdf)
        if isempty(S) || size(S,2)==0, return; end
        nEvt = size(S,2);
        MU   = mean(S,2,'omitnan');
        titleSize = 18; axisFontSize = 14;

        figH = min(320 + 16*nNorm, 3400);
        f = figure('Color','w','Position',[60 60 1240 figH],'Visible','off');
        set(f,'Units','inches'); fp = get(f,'Position');
        set(f,'PaperUnits','inches','PaperSize',fp(3:4),'PaperPosition',[0 0 fp(3:4)]);
        colormap(f, jet);
        tl = tiledlayout(f, 1, 50, 'Padding','compact', 'TileSpacing','none');

        yL = [0.5, nNorm+0.5];
        [ctrs, bnds] = regionLayout(regThick);

        ax1 = nexttile(tl, 1, [1 24]); hold(ax1,'on'); grid(ax1,'off'); box(ax1,'off');
        yv = 1:nNorm;
        for i = 1:nEvt
            plot(ax1, S(:,i), yv, '-', 'Color', [0.6 0.6 0.6 0.8], 'LineWidth', 0.9);
        end
        plot(ax1, MU, yv, '-', 'Color', [0 0 0], 'LineWidth', 2.0);
        xline(ax1, 0, '--k'); xlim(ax1, [-clim, clim]);
        set(ax1,'YDir','reverse','YLim',yL,'TickDir','out','FontSize',axisFontSize,'Layer','top');
        yticks(ax1, ctrs); yticklabels(ax1, regNames);
        set(ax1,'TickLabelInterpreter','none');
        for b = 1:numel(bnds), yline(ax1, bnds(b), 'k-', 'LineWidth', 0.75); end
        ylabel(ax1,'Anatomical region (normalized depth)','FontSize',axisFontSize,'FontWeight','bold');
        xlabel(ax1,sprintf('%s (%s)',measLabel,unitStr),'FontSize',axisFontSize,'FontWeight','bold');
        xl1 = xlim(ax1); yl1 = ylim(ax1);
        plot(ax1,[xl1(1) xl1(2) xl1(2) xl1(1) xl1(1)],[yl1(1) yl1(1) yl1(2) yl1(2) yl1(1)],'k-','LineWidth',2,'Clipping','off');

        ax2 = nexttile(tl, 26, [1 25]); hold(ax2,'on'); grid(ax2,'off'); box(ax2,'off');
        if sliceThick==1, Img = S; else, Img = repelem(S,1,sliceThick); end
        imagesc(ax2, 1:size(Img,2), 1:nNorm, Img);
        set(ax2,'YDir','reverse','YLim',yL,'TickDir','out','FontSize',axisFontSize, ...
            'YTick',[],'YTickLabel',[],'Layer','top','TickLength',[0 0]);
        xlim(ax2,[0.5, size(Img,2)+0.5]); caxis(ax2,[-clim, clim]);
        for b = 1:numel(bnds), yline(ax2, bnds(b), 'k-', 'LineWidth', 0.75); end
        axes(ax2); cb = colorbar;
        try, cb.Layout.Tile = 'east'; catch, set(cb,'Location','eastoutside'); end
        cb.Label.String = sprintf('%s (%s)', measLabel, unitStr);
        cb.FontSize = axisFontSize; cb.Label.FontSize = axisFontSize;
        if sliceThick >= 2
            centers = ((0:nEvt-1)*sliceThick) + (sliceThick/2) + 0.5;
        else
            centers = 1:nEvt;
        end
        xticks(ax2, centers); xticklabels(ax2, string(1:nEvt));
        ax2.XTickLabelRotation = 0;
        xlabel(ax2,'Event #','FontSize',axisFontSize,'FontWeight','bold');
        xl2 = xlim(ax2); yl2 = ylim(ax2);
        plot(ax2,[xl2(1) xl2(2) xl2(2) xl2(1) xl2(1)],[yl2(1) yl2(1) yl2(2) yl2(2) yl2(1)],'k-','LineWidth',2,'Clipping','off');
        linkaxes([ax1 ax2],'y');

        sgtitle(tl, sprintf('%s (%s)  |  %s %s  (n=%d, depth-corrected)', sessionName, groupLabel, measLabel, winLabel, nEvt), ...
            'FontSize', titleSize, 'FontWeight','bold', 'Interpreter','none');
        exportgraphics(f, outPng, 'Resolution', 300);
        try, print(f, outPdf, '-dpdf', '-painters'); catch, end
        close(f);
        fprintf('Saved %s\n', outPng);
    end

    % ---- depth-corrected event-averaged voltage raster (time x depth) ----
    function renderVoltRasterDepth(MU, clim, outPng, outPdf)
        if isempty(MU), return; end
        titleSize = 18; axisFontSize = 14;
        perRowPx = 16; basePx = 260; maxPx = 2600;
        figH = min(maxPx, basePx + perRowPx*nNorm);
        f = figure('Color','w','Position',[90 90 1100 figH],'Visible','off');
        set(f,'Units','inches'); fp = get(f,'Position');
        set(f,'PaperUnits','inches','PaperSize',fp(3:4),'PaperPosition',[0 0 fp(3:4)]);
        ax1 = axes('Parent', f);
        imagesc(ax1, tRelMs, 1:nNorm, MU);
        set(ax1,'YDir','reverse'); caxis(ax1,[-clim, clim]); colormap(ax1, jet);
        cb = colorbar(ax1); cb.Label.String = 'Voltage (\muV)';
        cb.FontSize = axisFontSize; cb.Label.FontSize = axisFontSize;
        xlabel(ax1,'Time (ms)','FontSize',axisFontSize,'FontWeight','bold');
        ylabel(ax1,'Anatomical region (normalized depth)','FontSize',axisFontSize,'FontWeight','bold');
        title(ax1,{sprintf('%s (%s)  Depth-Corrected Voltage Raster', sessionName, groupLabel),' '}, ...
            'FontSize',titleSize,'FontWeight','bold','Interpreter','none');
        [ctrs, bnds] = regionLayout(regThick);
        yticks(ax1, ctrs); yticklabels(ax1, regNames); set(ax1,'TickLabelInterpreter','none');
        set(ax1,'FontSize',axisFontSize,'TickDir','out','Layer','top','YLim',[0.5 nNorm+0.5]);
        box(ax1,'off'); grid(ax1,'off');
        hold(ax1,'on');
        for b = 1:numel(bnds), yline(ax1, bnds(b), 'k-', 'LineWidth', 0.75); end
        xl = [tRelMs(1) tRelMs(end)]; yl = [0.5 nNorm+0.5]; xlim(ax1, xl);
        plot(ax1,[xl(1) xl(2) xl(2) xl(1) xl(1)],[yl(1) yl(1) yl(2) yl(2) yl(1)],'k-','LineWidth',2,'Clipping','off');
        drawnow;
        exportgraphics(f, outPng, 'Resolution', 300);
        try, print(f, outPdf, '-dpdf', '-painters'); catch, end
        close(f);
        fprintf('Saved %s\n', outPng);
    end

    function writeSheet(xlsx, sheetName, S)
        if isempty(S) || size(S,2)==0
            C = [ {'DepthIndex','Region','Avg'}; ...
                  [num2cell((1:nNorm).'), rowRegion(:), num2cell(nan(nNorm,1))] ];
        else
            nE = size(S,2);
            hdr = arrayfun(@(k) sprintf('Evt%d', k), 1:nE, 'UniformOutput', false);
            header = [{'DepthIndex','Region'}, hdr, {'Avg'}];
            body   = [num2cell((1:nNorm).'), rowRegion(:), num2cell(S), num2cell(mean(S,2,'omitnan'))];
            C = [header; body];
        end
        writecell(C, xlsx, 'Sheet', sheetName);
    end

    function v = meanCol(S, n)
        if isempty(S) || size(S,2)==0, v = nan(n,1); else, v = mean(S,2,'omitnan'); end
    end
end

% ================= LOCAL HELPERS =================

function [ctrs, bnds] = regionLayout(regThick)
    % centers (for ticks) and interior boundaries (for separator lines)
    regThick = regThick(:).';
    cum = cumsum(regThick);
    starts = [0, cum(1:end-1)];
    ctrs = starts + regThick/2 + 0.5;
    bnds = cum(1:end-1) + 0.5;   % between region k and k+1
end

function RegMap = loadRegionMap(anatCsv)
    % Build region -> [minChannel maxChannel] from a (Row,Region) CSV.
    T = readtable(anatCsv, 'ReadVariableNames', true);
    vn = lower(regexprep(T.Properties.VariableNames, '[^a-zA-Z0-9]', ''));
    iRow = find(strcmp(vn,'row') | strcmp(vn,'channel') | strcmp(vn,'chan'), 1);
    iReg = find(strcmp(vn,'region') | strcmp(vn,'label'), 1);
    if isempty(iRow), iRow = 1; end
    if isempty(iReg), iReg = 2; end
    rows = double(T{:, iRow});
    regs = string(T{:, iReg});
    RegMap = containers.Map('KeyType','char','ValueType','any');
    uregs = unique(regs);
    for r = 1:numel(uregs)
        nm = char(strtrim(uregs(r)));
        if strlength(nm)==0 || strcmpi(nm,'NaN'), continue; end
        ch = rows(strcmp(regs, uregs(r)));
        ch = ch(isfinite(ch));
        if ~isempty(ch), RegMap(nm) = [min(ch), max(ch)]; end
    end
end

function [Pn, rowRegion, regNames, regThick] = warpProfileToTemplate(P, RegMap, T_gold, keptCh, cropInternal)
% Region-specific linear interpolation of a channel x N matrix onto the
% Golden Template depth axis. Each COLUMN of P (an event, or a time sample)
% is warped independently. Missing regions -> NaN rows (probe depth limit).
    keptCh = double(keptCh(:).');
    regions = T_gold.Region;
    targets = T_gold.Target_Thickness;
    Pn = []; rowRegion = {}; regNames = {}; regThick = [];

    for k = 1:numel(regions)
        regName = char(regions{k});
        tH = targets(k);
        if tH <= 0, continue; end
        isBuffer = contains(upper(regName),'ABOVE') || contains(upper(regName),'BELOW');
        if cropInternal && isBuffer, continue; end

        physStart = nan; physEnd = nan; isMissing = false;
        if strcmpi(regName, 'ABOVE CA1 SLM')
            if isKey(RegMap,'CA1 SLM'), r = RegMap('CA1 SLM'); physEnd = r(1)-1; physStart = -inf;
            else, isMissing = true; end
        elseif strcmpi(regName, 'BELOW DG OML2')
            if isKey(RegMap,'DG OML2'), r = RegMap('DG OML2'); physStart = r(2)+1; physEnd = inf;
            else, isMissing = true; end
        else
            if isKey(RegMap, regName), r = RegMap(regName); physStart = r(1); physEnd = r(2);
            else, isMissing = true; end
        end

        chunk = [];
        if ~isMissing && ~isnan(physStart)
            vi = find(keptCh >= physStart & keptCh <= physEnd);
            if ~isempty(vi), chunk = P(vi, :); end
        end

        if isempty(chunk)
            warpedChunk = nan(tH, size(P,2));          % probe depth limit / missing region
        else
            h = size(chunk,1);
            if h == tH
                warpedChunk = chunk;
            elseif h == 1
                warpedChunk = repmat(chunk, tH, 1);
            else
                xq = linspace(1, h, tH).';
                warpedChunk = interp1((1:h).', chunk, xq, 'linear');
            end
        end

        Pn = [Pn; warpedChunk]; %#ok<AGROW>
        regNames{end+1} = regName; %#ok<AGROW>
        regThick(end+1) = tH; %#ok<AGROW>
        for rr = 1:tH, rowRegion{end+1} = regName; end %#ok<AGROW>
    end
end

function evts = parseEvtNumsFromPngs(dirpath)
    L = dir(fullfile(dirpath, '*.png')); evts = [];
    for k = 1:numel(L)
        m = regexp(L(k).name, 'Evt(\d+)', 'tokens', 'once');
        if ~isempty(m)
            ev = str2double(m{1}); if isfinite(ev), evts(end+1) = ev; end %#ok<AGROW>
        end
    end
    evts = sort(unique(evts));
end

function C = computeCSD(Ych_t)
    [nCh, ~] = size(Ych_t);
    if nCh < 2, C = nan(size(Ych_t)); return;
    elseif nCh == 2, C = zeros(size(Ych_t)); return; end
    Cint = -( Ych_t(3:end,:) - 2*Ych_t(2:end-1,:) + Ych_t(1:end-2,:) );
    C = zeros(size(Ych_t));
    C(2:end-1,:) = Cint;
    C(1,:)   = C(2,:);
    C(end,:) = C(end-1,:);
end

function composeRowHiRes(pngList, outPath, colSep)
    pngList = pngList(cellfun(@(s) ~isempty(s) && isfile(s), pngList));
    if isempty(pngList), error('composeRowHiRes: no valid inputs'); end
    imgs = cellfun(@imread, pngList, 'UniformOutput', false);
    hh = cellfun(@(I) size(I,1), imgs);
    Hmax = max(hh);
    for i = 1:numel(imgs)
        if size(imgs{i},1) ~= Hmax
            sf = Hmax / size(imgs{i},1);
            imgs{i} = imresize(imgs{i}, [Hmax, round(size(imgs{i},2)*sf)]);
        end
    end
    ww = cellfun(@(I) size(I,2), imgs);
    Wsum = sum(ww) + colSep*(numel(imgs)-1);
    out = repmat(uint8(255), [Hmax, Wsum, 3]);
    x = 1;
    for i = 1:numel(imgs)
        I = imgs{i}; if size(I,3)==1, I = repmat(I,1,1,3); end
        [h,w,~] = size(I);
        out(1:h, x:x+w-1, :) = I(:,:,1:3);
        x = x + w + colSep;
    end
    imwrite(out, outPath);
end
