function res = IPP_Combined_Pipeline(inputFolder, dataMatPath, varargin)
% IPP_Combined_Pipeline
% Combines the logic of CSD_CenterSlices + CSD_TimeAvgSlices + VoltageRaster
% into a single pass, using ONE anchor per event so every measure lines up.
%
% For every event (per group SOLID / SPUTTER) it time-averages over two
% windows relative to the anchor:
%   IP  ("center slices", renamed)  : [-1, +1] ms
%   PP  ("time-avg slices", renamed): [+2, +10] ms
% and computes those averages for BOTH the CSD and the raw Voltage.
%
% OUTPUTS (written into <outputDir>):
%   Figures (PNG + PDF), per group:
%     CSD_IP_SOLID / CSD_IP_SPUTTER          (waveform + per-event heatmap)
%     CSD_PP_SOLID / CSD_PP_SPUTTER          (waveform + per-event heatmap)
%     Voltage_Raster_SOLID / _SPUTTER        (full +/-win averaged raster)
%     Montage_SOLID / Montage_SPUTTER        (Volt | IP-CSD | PP-CSD)
%   Spreadsheet (4 sheets), per-event values + average column:
%     <sessionName>_Values.xlsx  -> sheets  CSD_IP  CSD_PP  Voltage_IP  Voltage_PP
%   Stats:
%     <sessionName>_stats.csv
%
% RETURNS struct with all file paths plus per-channel average profiles
% (res.avg.*) so a driver can build a combined cross-session workbook.
%
% Anchor parameters (shared by all measures):
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

p.addParameter('winHalfWidthMs',   20e-3, @(x)isfinite(x)&&x>0);   % +/-display half-width
p.addParameter('anchorHalfWidthMs', 5e-3, @(x)isfinite(x)&&x>0);   % +/-anchor search

% --- IP / PP time-average windows (relative to anchor) ---
p.addParameter('ipStartMs', -1e-3, @(x)isfinite(x));
p.addParameter('ipEndMs',    1e-3, @(x)isfinite(x));
p.addParameter('ppStartMs',  2e-3, @(x)isfinite(x));
p.addParameter('ppEndMs',   10e-3, @(x)isfinite(x));

p.addParameter('sliceThickness', 6, @(x)isfinite(x) && x>=1 && mod(x,1)==0);
p.addParameter('robustPct',    99.5, @(x) isfinite(x) && x>0 && x<100);
p.addParameter('padFrac',       0.12, @(x) isfinite(x) && x>=0 && x<=0.5);
p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('absoluteClimCSD',  [], @(x) isempty(x) || (isscalar(x) && x>0)); % [] = auto robust
p.addParameter('climMicroV',       [], @(x) isempty(x) || (isscalar(x) && x>0)); % voltage raster clim

% --- Anchor parameters ---
p.addParameter('anchorMidpoint', false, @(x)islogical(x)||ismember(x,[0 1]));
p.addParameter('anchorChannel', 0, @(x)isscalar(x)&&isnumeric(x)&&x>=0);
p.addParameter('anchorPolarity', 'pos', @(s) any(validatestring(s, {'pos','neg','abs'})));

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

% ---------------- Layout & IO ----------------
solidDir   = fullfile(inputFolder, "Solid");
sputterDir = fullfile(inputFolder, "Sputter");
assert(isfolder(solidDir),   'Missing folder: %s', solidDir);
assert(isfolder(sputterDir), 'Missing folder: %s', sputterDir);

if excelPath == ""
    xl = dir(fullfile(inputFolder, "*.xlsx"));
    xl = xl(~startsWith({xl.name}, '~$'));   % skip Excel lock files
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

% ---------------- Data ----------------
assert(isfile(dataMatPath), 'Data MAT not found: %s', dataMatPath);
mf = matfile(dataMatPath);
try sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRowsAll = size(mf,'d',1);
nSamp    = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end

% Channel selection
if isempty(channelIdx)
    chList = 1:nRowsAll;
else
    chList = channelIdx(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);
assert(nCh > 0, 'No valid channels selected.');

% Actual hardware channel numbers + string labels
if isempty(kept_channels)
    actualChans = chList;
else
    actualChans = kept_channels(chList);
end
chanLabels = arrayfun(@(k) sprintf('%d', actualChans(k)), 1:nCh, 'UniformOutput', false);

% Scaling
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

fprintf('IPP_Combined: sfx=%.1f Hz | IP %s | PP %s | win +/-%.1f ms\n', ...
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

% ---------------- Events per group ----------------
evtSOL = parseEvtNumsFromPngs(solidDir);
evtSPU = parseEvtNumsFromPngs(sputterDir);
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));
if ~isempty(maxEventsPer)
    if ~isempty(evtSOL), evtSOL = evtSOL(1:min(end, maxEventsPer)); end
    if ~isempty(evtSPU), evtSPU = evtSPU(1:min(end, maxEventsPer)); end
end

% ---------------- Compute both groups ----------------
G.SOLID   = computeGroup(evtSOL,  'SOLID');
G.SPUTTER = computeGroup(evtSPU,  'SPUTTER');

% ---------------- CLim (shared per measure across groups) ----------------
climCSD_IP = pickClim(absClimCSD, {G.SOLID.CSD_IP, G.SPUTTER.CSD_IP});
climCSD_PP = pickClim(absClimCSD, {G.SOLID.CSD_PP, G.SPUTTER.CSD_PP});
climVolt   = pickClim(climMicroVOpt, {G.SOLID.Vrast,  G.SPUTTER.Vrast});

% ---------------- Render figures ----------------
res = struct();
res.sessionName = sessionName;
files = struct();
groups = {'SOLID','SPUTTER'};
for gi = 1:2
    tag = groups{gi};
    Gd  = G.(tag);
    if Gd.nEvt == 0
        fprintf('(%s) no usable events -> skipping figures.\n', tag);
        files.(['ipCsd_' tag])  = "";
        files.(['ppCsd_' tag])  = "";
        files.(['volt_'   tag])  = "";
        files.(['montage_' tag]) = "";
        continue;
    end

    % CSD IP slices
    ipPng = fullfile(outputDir, sprintf('CSD_IP_%s.png', tag));
    ipPdf = fullfile(outputDir, sprintf('CSD_IP_%s.pdf', tag));
    renderSlices(Gd.CSD_IP, tag, 'CSD', ['IP  ' ipLabel], climCSD_IP, ipPng, ipPdf);

    % CSD PP slices
    ppPng = fullfile(outputDir, sprintf('CSD_PP_%s.png', tag));
    ppPdf = fullfile(outputDir, sprintf('CSD_PP_%s.pdf', tag));
    renderSlices(Gd.CSD_PP, tag, 'CSD', ['PP  ' ppLabel], climCSD_PP, ppPng, ppPdf);

    % Voltage raster (full window)
    vPng = fullfile(outputDir, sprintf('Voltage_Raster_%s.png', tag));
    vPdf = fullfile(outputDir, sprintf('Voltage_Raster_%s.pdf', tag));
    renderVoltRaster(Gd.Vrast, tag, climVolt, vPng, vPdf);

    % Montage (Voltage | IP-CSD | PP-CSD)
    montPng = fullfile(outputDir, sprintf('Montage_%s.png', tag));
    try
        composeRowHiRes({char(vPng), char(ipPng), char(ppPng)}, char(montPng), 12);
    catch ME
        warning('Montage %s failed: %s', tag, ME.message); montPng = "";
    end

    files.(['ipCsd_' tag])   = ipPng;
    files.(['ppCsd_' tag])   = ppPng;
    files.(['volt_'   tag])  = vPng;
    files.(['montage_' tag]) = montPng;
end
res.files = files;

% ---------------- 4-sheet workbook (per-event values + avg col) ----------------
xlsxPath = fullfile(outputDir, sprintf('%s_Values.xlsx', sessionName));
if isfile(xlsxPath), delete(xlsxPath); end   % start clean so stale sheets don't linger
writeSheet(xlsxPath, 'CSD_IP',     G.SOLID.CSD_IP, G.SPUTTER.CSD_IP);
writeSheet(xlsxPath, 'CSD_PP',     G.SOLID.CSD_PP, G.SPUTTER.CSD_PP);
writeSheet(xlsxPath, 'Voltage_IP', G.SOLID.V_IP,   G.SPUTTER.V_IP);
writeSheet(xlsxPath, 'Voltage_PP', G.SOLID.V_PP,   G.SPUTTER.V_PP);
res.valuesXlsx = xlsxPath;
fprintf('Saved 4-sheet workbook: %s\n', xlsxPath);

% ---------------- Stats CSV ----------------
statsCSV = fullfile(outputDir, sprintf('%s_stats.csv', sessionName));
St = table();
St = [St; statRow('SOLID',   G.SOLID)];   %#ok<AGROW>
St = [St; statRow('SPUTTER', G.SPUTTER)]; %#ok<AGROW>
try
    writetable(St, statsCSV);
    res.statsCSV = statsCSV;
catch ME
    warning('Failed to write stats CSV: %s', ME.message);
    res.statsCSV = "";
end

% ---------------- Per-channel averages (for combined workbook) ----------------
res.channels = string(actualChans(:));
res.avg = struct();
for gi = 1:2
    tag = groups{gi}; Gd = G.(tag);
    res.avg.(['CSD_IP_'     tag]) = meanCol(Gd.CSD_IP, nCh);
    res.avg.(['CSD_PP_'     tag]) = meanCol(Gd.CSD_PP, nCh);
    res.avg.(['Voltage_IP_' tag]) = meanCol(Gd.V_IP,   nCh);
    res.avg.(['Voltage_PP_' tag]) = meanCol(Gd.V_PP,   nCh);
end

% ================= NESTED HELPERS (share parsed scope) =================

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
            'V_IP',zeros(nCh,0),'V_PP',zeros(nCh,0), ...
            'Vrast',[]);
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

    function renderSlices(S, tag, measLabel, winLabel, clim, outPng, outPdf)
        nEvt = size(S,2);
        MU   = mean(S,2,'omitnan');
        titleSize = 18; axisFontSize = 14;

        figH = min(320 + 14*nCh, 3400);
        f = figure('Color','w','Position',[60 60 1200 figH],'Visible','off');
        set(f,'Units','inches'); fp = get(f,'Position');
        set(f,'PaperUnits','inches','PaperSize',fp(3:4),'PaperPosition',[0 0 fp(3:4)]);
        colormap(f, jet);
        tl = tiledlayout(f, 1, 50, 'Padding','compact', 'TileSpacing','none');

        if nCh >= 3, yL = [1.5, nCh-0.5]; else, yL = [0.5, nCh+0.5]; end
        evenIdx = find(mod(actualChans,2)==0);

        % LEFT: vertical waveform
        ax1 = nexttile(tl, 1, [1 24]); hold(ax1,'on'); grid(ax1,'off'); box(ax1,'off');
        yv = 1:nCh;
        for i = 1:nEvt
            plot(ax1, S(:,i), yv, '-', 'Color', [0.6 0.6 0.6 0.8], 'LineWidth', 0.9);
        end
        plot(ax1, MU, yv, '-', 'Color', [0 0 0], 'LineWidth', 2.0);
        xline(ax1, 0, '--k'); xlim(ax1, [-clim, clim]);
        set(ax1,'YDir','reverse','YLim',yL,'TickDir','out','FontSize',axisFontSize,'Layer','top');
        yticks(ax1, evenIdx); yticklabels(ax1, string(actualChans(evenIdx)));
        ylabel(ax1,'Channel #','FontSize',axisFontSize,'FontWeight','bold');
        xlabel(ax1,sprintf('%s (a.u.)',measLabel),'FontSize',axisFontSize,'FontWeight','bold');
        xl1 = xlim(ax1); yl1 = ylim(ax1);
        plot(ax1,[xl1(1) xl1(2) xl1(2) xl1(1) xl1(1)],[yl1(1) yl1(1) yl1(2) yl1(2) yl1(1)],'k-','LineWidth',2,'Clipping','off');

        % RIGHT: per-event heatmap
        ax2 = nexttile(tl, 26, [1 25]); hold(ax2,'on'); grid(ax2,'off'); box(ax2,'off');
        if sliceThick==1, Img = S; else, Img = repelem(S,1,sliceThick); end
        imagesc(ax2, 1:size(Img,2), 1:nCh, Img);
        set(ax2,'YDir','reverse','YLim',yL,'TickDir','out','FontSize',axisFontSize, ...
            'YTick',[],'YTickLabel',[],'Layer','top','TickLength',[0 0]);
        xlim(ax2,[0.5, size(Img,2)+0.5]); caxis(ax2,[-clim, clim]);
        axes(ax2); cb = colorbar;
        try, cb.Layout.Tile = 'east'; catch, set(cb,'Location','eastoutside'); end
        cb.Label.String = sprintf('%s (a.u.)', measLabel);
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

        sgtitle(tl, sprintf('%s  |  %s %s  (n=%d)', tag, measLabel, winLabel, nEvt), ...
            'FontSize', titleSize, 'FontWeight','bold');
        exportgraphics(f, outPng, 'Resolution', 300);
        try, print(f, outPdf, '-dpdf', '-painters'); catch, end
        close(f);
        fprintf('Saved %s\n', outPng);
    end

    function renderVoltRaster(MU, tag, clim, outPng, outPdf)
        titleSize = 18; axisFontSize = 14;
        perRowPx = 12; basePx = 260; maxPx = 2600;
        figH = min(maxPx, basePx + perRowPx*nCh);
        f = figure('Color','w','Position',[90 90 1100 figH],'Visible','off');
        set(f,'Units','inches'); fp = get(f,'Position');
        set(f,'PaperUnits','inches','PaperSize',fp(3:4),'PaperPosition',[0 0 fp(3:4)]);
        ax1 = axes('Parent', f);
        imagesc(ax1,'XData',[tRelMs(1) tRelMs(end)],'YData',[1 nCh],'CData',MU);
        set(ax1,'YDir','reverse'); caxis(ax1,[-clim, clim]); colormap(ax1, jet);
        cb = colorbar(ax1); cb.Label.String = 'Voltage (\muV)';
        cb.FontSize = axisFontSize; cb.Label.FontSize = axisFontSize;
        xlabel(ax1,'Time (ms)','FontSize',axisFontSize,'FontWeight','bold');
        ylabel(ax1,'Channel #','FontSize',axisFontSize,'FontWeight','bold');
        title(ax1,{sprintf('%s Average Voltage Raster', tag),' '},'FontSize',titleSize,'FontWeight','bold');
        evenIdx = find(mod(actualChans,2)==0);
        yticks(ax1, evenIdx); yticklabels(ax1, string(actualChans(evenIdx)));
        set(ax1,'FontSize',axisFontSize,'TickDir','out','Layer','top'); box(ax1,'off'); grid(ax1,'off');
        axis(ax1,'tight'); xl = xlim(ax1); yl = ylim(ax1);
        hold(ax1,'on');
        plot(ax1,[xl(1) xl(2) xl(2) xl(1) xl(1)],[yl(1) yl(1) yl(2) yl(2) yl(1)],'k-','LineWidth',2,'Clipping','off');
        drawnow;
        exportgraphics(f, outPng, 'Resolution', 300);
        try, print(f, outPdf, '-dpdf', '-painters'); catch, end
        close(f);
        fprintf('Saved %s\n', outPng);
    end

    function writeSheet(xlsx, sheetName, Ssolid, Sspu)
        % Build a cell block: Channel | Solid_Evt.. | Solid_Avg | (gap) | Sputter_Evt.. | Sputter_Avg
        blkS = groupBlock('Solid',   Ssolid);
        blkP = groupBlock('Sputter', Sspu);
        gap  = repmat({''}, nCh+1, 1);
        C = [ [{'Channel'}; chanLabels(:)], blkS, gap, blkP ];
        writecell(C, xlsx, 'Sheet', sheetName);
    end

    function blk = groupBlock(prefix, S)
        if isempty(S) || size(S,2)==0
            blk = [ {sprintf('%s_Avg', prefix)}; num2cell(nan(nCh,1)) ];
            return;
        end
        nE = size(S,2);
        hdr  = arrayfun(@(k) sprintf('%s_Evt%d', prefix, k), 1:nE, 'UniformOutput', false);
        avgH = {sprintf('%s_Avg', prefix)};
        header = [hdr, avgH];
        body   = [num2cell(S), num2cell(mean(S,2,'omitnan'))];
        blk = [header; body];
    end

    function Trow = statRow(tag, Gd)
        Trow = table(string(sessionName), string(tag), Gd.nEvt, nCh, sfx, ...
            climCSD_IP, climCSD_PP, climVolt, ...
            string(ipLabel), string(ppLabel), ...
            logical(anchorMidpoint), anchorChannel, string(anchorPolarity), 1e3*anchorHWms, ...
            'VariableNames', {'Session','Group','Events','Channels','SampRateHz', ...
            'CLim_CSD_IP','CLim_CSD_PP','CLim_Volt_uV','IP_Window','PP_Window', ...
            'AnchorMidpoint','AnchorChannelRow','AnchorPolarity','AnchorHalfWidth_ms'});
    end

    function v = meanCol(S, n)
        if isempty(S) || size(S,2)==0, v = nan(n,1); else, v = mean(S,2,'omitnan'); end
    end
end

% ================= LOCAL (non-nested) HELPERS =================

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
% Horizontal concat of PNGs, resized to a common height (native-ish res).
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
