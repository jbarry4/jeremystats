function res = EventStacks_ampWidth_Avg_Pipeline_Farrell(inputFolder, dataMatPath, varargin)
% EventStacks_ampWidth_Avg_Pipeline_Farrell ("Farrell" Version - Waterfall F)
%
% STANDALONE version for stacked/waterfall plotting.
%
% CHANGES:
%   - ZOOM: Fixed x-axis to +/- 10ms.
%   - LAYOUT: Channel numbers on Left Y-axis. Vertical "Channel #" label.
%   - SCALE: Voltage numbers removed.
%   - SPACING: "Tight Packing" (Maximized size without overlap).
%   - OUTPUT: Saves PNG + Vector PDF.
%
% USAGE:
%   EventStacks_ampWidth_Avg_Pipeline_F(inputFolder, dataMatPath, ... same args ...)

% ---------------- Args ----------------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
% Data / channels / scaling
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);
% Alignment & windows (Original calculation params kept, plot will override zoom)
p.addParameter('halfWidthMs',         50e-3, @(x)isfinite(x)&&x>0); 
p.addParameter('metricHalfWidthMs',    5e-3, @(x)isfinite(x)&&x>0); 
p.addParameter('anchorHalfWidthMs',    5e-3, @(x)isfinite(x)&&x>0); 
% Spreadsheet + mapping
p.addParameter('excelPath',"", @(s)ischar(s)||isstring(s));
p.addParameter('indexBase','auto', @(s) any(strcmpi(s,{'auto','zero','one'})));
p.addParameter('evtOffset',0, @(x)isscalar(x)&&isfinite(x));
p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));
% Output + y-axis
p.addParameter('saveDir',"", @(s)ischar(s)||isstring(s));
p.addParameter('tag','ALL', @(s)ischar(s)||isstring(s));
p.addParameter('yLimMicroV', [], @(x) isempty(x) || (isscalar(x) && x>0)); 
p.addParameter('yRobustPct', 99.5, @(x) isfinite(x) && x>0 && x<100);      
p.addParameter('yPadFrac', 0.12, @(x) isfinite(x) && x>=0 && x<=0.5);      
% --- ANCHOR PARAMETERS ---
p.addParameter('anchorMidpoint', false, @(x)islogical(x)||ismember(x,[0 1]));
p.addParameter('anchorChannel', 0, @(x)isscalar(x)&&isnumeric(x)&&x>=0);
p.addParameter('anchorPolarity', 'pos', @(s) any(validatestring(s, {'pos','neg','abs'})));
% --- END PARAMETERS ---
p.parse(inputFolder, dataMatPath, varargin{:});

% Unpack results
inputFolder     = string(p.Results.inputFolder);
dataMatPath     = string(p.Results.dataMatPath);
channelIndices  = p.Results.channelIndices;
scaleToMicroV   = p.Results.scaleToMicroV;
halfWidthMs     = p.Results.halfWidthMs;
anchorHWms      = p.Results.anchorHalfWidthMs;
excelPath       = string(p.Results.excelPath);
indexBase       = lower(string(p.Results.indexBase));
evtOffset       = p.Results.evtOffset;
maxEventsPerGrp = p.Results.maxEventsPerGroup;
saveDir         = string(p.Results.saveDir);
yLimMicroV      = p.Results.yLimMicroV;
yRobustPct      = p.Results.yRobustPct;
yPadFrac        = p.Results.yPadFrac;
anchorMidpoint  = p.Results.anchorMidpoint;
anchorChannel   = p.Results.anchorChannel;
anchorPolarity  = p.Results.anchorPolarity;

% ---------------- Layout ----------------
solidDir   = fullfile(inputFolder, "Solid");
sputterDir = fullfile(inputFolder, "Sputter");
if ~isfolder(solidDir) || ~isfolder(sputterDir)
    error('Missing Solid/Sputter folders in %s', inputFolder);
end

if excelPath == ""
    xl = dir(fullfile(inputFolder, "*.xlsx"));
    if isempty(xl), error('No Excel file found.'); end
    excelPath = fullfile(xl(1).folder, xl(1).name);
end

% ---------------- Data ----------------
mf = matfile(dataMatPath);
try sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRowsAll = size(mf,'d',1);
nSamp    = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end

if isempty(channelIndices)
    chList = 1:nRowsAll;
else
    chList = channelIndices(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);

% ---------- Output directory ----------
if saveDir == ""
    outDir = fullfile(inputFolder, 'EventStacks AmpWidth Output');
else
    outDir = char(saveDir);
end
if ~exist(outDir,'dir'), mkdir(outDir); end

% Define Farrell Output Paths (PNG + PDF)
farColSOL_png = fullfile(outDir, 'AvgStack_SOLID_Farrell_Color.png');
farColSOL_pdf = fullfile(outDir, 'AvgStack_SOLID_Farrell_Color.pdf');

farBlkSOL_png = fullfile(outDir, 'AvgStack_SOLID_Farrell_Black.png');
farBlkSOL_pdf = fullfile(outDir, 'AvgStack_SOLID_Farrell_Black.pdf');

farColSPU_png = fullfile(outDir, 'AvgStack_SPUTTER_Farrell_Color.png');
farColSPU_pdf = fullfile(outDir, 'AvgStack_SPUTTER_Farrell_Color.pdf');

farBlkSPU_png = fullfile(outDir, 'AvgStack_SPUTTER_Farrell_Black.png');
farBlkSPU_pdf = fullfile(outDir, 'AvgStack_SPUTTER_Farrell_Black.pdf');

% ---------------- Windows ----------------
HWdisp    = max(1, round(halfWidthMs * sfx));
HWanchor  = max(1, round(anchorHWms  * sfx));
tRelSamp  = -HWdisp:HWdisp;
tRelMs    = (tRelSamp / sfx) * 1e3;
winN      = numel(tRelSamp);

fprintf('Farrell Pipeline: sfx=%.1f Hz | display ±%.1f ms | channels=%d\n', sfx, 1e3*HWdisp/sfx, nCh);

% ---------------- Spreadsheet -> samples ----------------
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
    onSamp  = double(T{:,1});
    offSamp = double(T{:,2});
end

switch indexBase
    case "zero", onSamp = onSamp+1; offSamp = offSamp+1;
    case "auto"
        if any(onSamp < 1 | offSamp < 1 | onSamp==0 | offSamp==0)
            onSamp = onSamp+1; offSamp = offSamp+1;
        end
end
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));

% ---------------- Events from PNG names ----------------
evtSOL = unique(parseEvtNumsFromPngs(solidDir));
evtSPU = unique(parseEvtNumsFromPngs(sputterDir));

if ~isempty(maxEventsPerGrp)
    evtSOL = evtSOL(1:min(end, maxEventsPerGrp));
    evtSPU = evtSPU(1:min(end, maxEventsPerGrp));
end

% ---------------- Build Data ----------------
[SOL, robSOL] = avgForGroup(evtSOL, 'SOLID');
[SPU, robSPU] = avgForGroup(evtSPU, 'SPUTTER');

% ---------------- Global y-limit ----------------
if isempty(yLimMicroV)
    yMaxSOL = computeYMaxForGroup(SOL);
    yMaxSPU = computeYMaxForGroup(SPU);
    rob     = max([robSOL, robSPU, yMaxSOL, yMaxSPU, 10]);
    yMax    = (1 + yPadFrac) * rob;
else
    yMax = yLimMicroV;
end
yL_global = [-yMax, +yMax];
fprintf('Global y-limit (base): ±%.1f µV\n', yMax);

% ---------------- Generate Farrell Plots ----------------
% Passing yMax is less relevant now as we calculate spacing internally for "encroaching" look
plotFarrellWaterfall(SOL, 'SOLID', farColSOL_png, farColSOL_pdf, true);  % Color
plotFarrellWaterfall(SOL, 'SOLID', farBlkSOL_png, farBlkSOL_pdf, false); % Black

plotFarrellWaterfall(SPU, 'SPUTTER', farColSPU_png, farColSPU_pdf, true);  % Color
plotFarrellWaterfall(SPU, 'SPUTTER', farBlkSPU_png, farBlkSPU_pdf, false); % Black

% ---------------- Return Struct ----------------
res = struct('farrellSolidColorPng', farColSOL_png, ...
             'farrellSolidColorPdf', farColSOL_pdf, ...
             'farrellSolidBlackPng', farBlkSOL_png, ...
             'farrellSolidBlackPdf', farBlkSOL_pdf, ...
             'farrellSputterColorPng', farColSPU_png, ...
             'farrellSputterColorPdf', farColSPU_pdf, ...
             'farrellSputterBlackPng', farBlkSPU_png, ...
             'farrellSputterBlackPdf', farBlkSPU_pdf);

% ================= HELPERS =================

    function evts = parseEvtNumsFromPngs(dirpath)
        L = dir(fullfile(dirpath, '*.png'));
        evts = [];
        for k = 1:numel(L)
            m = regexp(L(k).name, 'Evt(\d+)', 'tokens', 'once');
            if ~isempty(m)
                ev = str2double(m{1});
                if isfinite(ev), evts(end+1) = ev; end %#ok<AGROW>
            end
        end
        evts = sort(unique(evts));
    end

    function yMax = computeYMaxForGroup(G)
        if isempty(G) || all(all(isnan(G.MU)))
            yMax = 0; return;
        end
        mm = max(abs([G.MU(:)+G.SE(:); G.MU(:)-G.SE(:)]), [], 'omitnan');
        yMax = max([mm, 0], [], 'omitnan');
    end

    function [G, robAll] = avgForGroup(evtList, tag)
        G = struct('MU',nan(nCh,winN),'SE',nan(nCh,winN),'tRelMs',tRelMs);
        robAll = 0;
        if isempty(evtList), return; end
        
        stacks = cell(nCh,1);
        for i=1:nCh, stacks{i} = []; end
        
        for ii = 1:numel(evtList)
            e = evtList(ii);
            rowXL = e + evtOffset;
            if rowXL < 1 || rowXL > numel(onSamp), continue; end
            
            s0_ev = onSamp(rowXL); s1_ev = offSamp(rowXL);
            if ~isfinite(s0_ev), continue; end
            ancMid = round((s0_ev + s1_ev)/2);
            
            % Anchor Logic
            if anchorMidpoint
                commonAnchor = ancMid;
            else
                if anchorChannel == 0, refCh = chList(end); else, refCh = anchorChannel; end
                s0srch = max(1, ancMid - HWanchor);
                s1srch = min(nSamp, ancMid + HWanchor);
                
                scRef = scaleToMicroV; if numel(scRef)>1, scRef = scRef(refCh); end
                yseg = double(mf.d(refCh, s0srch:s1srch)) * scRef;
                
                if isempty(yseg), continue; end
                switch anchorPolarity
                    case 'pos', [~, k] = max(yseg);
                    case 'neg', [~, k] = min(yseg);
                    case 'abs', [~, k] = max(abs(yseg));
                    otherwise,  [~, k] = max(yseg);
                end
                commonAnchor = s0srch + k - 1;
            end
            
            for k = 1:nCh
                ch = chList(k);
                sc = scaleToMicroV; if numel(sc)>1, sc = sc(ch); end
                s0 = commonAnchor - HWdisp; s1 = commonAnchor + HWdisp;
                if s0 < 1 || s1 > nSamp, continue; end
                y = double(mf.d(ch, s0:s1)) * sc;
                if all(isnan(y)), continue; end
                
                stacks{k}(end+1,:) = y; %#ok<AGROW>
                
                yy = y(isfinite(y));
                if ~isempty(yy)
                    p = prctile(abs(yy), yRobustPct);
                    if p > robAll, robAll = p; end
                end
            end
        end
        
        for k = 1:nCh
            X = stacks{k};
            if ~isempty(X)
                G.MU(k,:) = mean(X, 1, 'omitnan');
                G.SE(k,:) = std(X, 0, 1, 'omitnan') ./ sqrt(size(X,1));
            end
        end
    end

    function plotFarrellWaterfall(G, tag, outPng, outPdf, useColor)
        if isempty(G) || all(all(isnan(G.MU))), return; end
        
        % --- DYNAMIC TIGHT PACKING CALCULATION ---
        % Find the absolute largest peak-to-peak range of ANY channel average.
        % This ensures the "biggest" waveform defines the slot height.
        ranges = max(G.MU, [], 2) - min(G.MU, [], 2);
        maxRange = max(ranges);
        
        % Safety fallback
        if isempty(maxRange) || maxRange < 1e-9, maxRange = 10; end
        
        % Spacing = MaxRange + small padding (1%)
        % This creates the "encroaching but no overlap" effect.
        spacing = maxRange * 1.01; 
        
        stdColors = [0 0.4470 0.7410; 0.8500 0.3250 0.0980; 0.9290 0.6940 0.1250;
                     0.4940 0.1840 0.5560; 0.4660 0.6740 0.1880; 0.3010 0.7450 0.9330;
                     0.6350 0.0780 0.1840];
        nColors = size(stdColors, 1);
        
        % Figure setup
        f1 = figure('Visible','off','Color','w','Position',[100 100 800 900]);
        ax1 = axes(f1); hold(ax1, 'on');
        
        % We will collect offset positions and labels for the Y-axis
        yTickPos = zeros(nCh, 1);
        yTickLabs = cell(nCh, 1);
        
        % Loop channels from bottom (1) to top (nCh)
        for k = 1:nCh
            mu = G.MU(k,:);
            if all(isnan(mu)), continue; end
            
            % Offset calculation: Ch1 at 0, Ch2 at +spacing...
            yOffset = (k-1) * spacing;
            
            % Store tick info
            yTickPos(k) = yOffset;
            
            % Label: Use "CSC#" if available, else just number
            if ~isempty(kept_channels)
                % Just number per request ("then the numbers")
                yTickLabs{k} = sprintf('%d', kept_channels(chList(k)));
            else
                yTickLabs{k} = sprintf('%d', k);
            end
            
            % Color
            if useColor
                cIdx = mod(k-1, nColors) + 1;
                col = stdColors(cIdx, :);
            else
                col = 'k';
            end
            
            % Plot Trace
            plot(ax1, G.tRelMs, mu + yOffset, 'LineWidth', 1.5, 'Color', col);
            
            % Subtle zero line
            yline(ax1, yOffset, ':', 'Color', [0.8 0.8 0.8], 'LineWidth', 0.5);
        end
        
        % --- AXES & LABELS ---
        grid(ax1, 'on'); 
        box(ax1, 'on');
        
        xlabel(ax1, 'Time (ms)', 'FontSize', 12, 'FontWeight', 'bold');
        
        % Custom Left Y-Axis
        set(ax1, 'YTick', yTickPos, 'YTickLabel', yTickLabs);
        ylabel(ax1, 'Channel #', 'FontSize', 12, 'FontWeight', 'bold');
        
        % TITLE
        title(ax1, sprintf('%s Waveforms (%s)', tag, tern(useColor,'Color','Black')), 'FontSize', 14);
        
        % Adjust Limits
        % Y: Slightly padded around the stack
        ylim(ax1, [-spacing*0.6, (nCh-1)*spacing + spacing*0.6]);
        
        % X: HARDCODED ZOOM +/- 10ms per request
        xlim(ax1, [-10, 10]);
        
        % Save PNG
        exportgraphics(f1, outPng, 'Resolution', 300);
        
        % Save Vector PDF
        try
            set(f1, 'PaperPositionMode', 'auto');
            print(f1, outPdf, '-dpdf', '-painters', '-bestfit');
        catch ME
            warning('Failed to save vector PDF %s: %s', outPdf, ME.message);
        end
        
        close(f1);
        fprintf('Saved Farrell Stack: %s & PDF\n', outPng);
    end
    
    function s = tern(cond,a,b), if cond, s=a; else, s=b; end; end
end