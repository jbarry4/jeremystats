function EventStacks_AmpWidth(excelPath, dataMatPath, varargin)

p = inputParser;
p.addRequired('excelPath', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

% Data / channels / scaling (µV expected; keep scaleToMicroV=1 unless needed)
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);

% Alignment of display center
p.addParameter('align','midpoint', @(s) any(strcmpi(s,{'midpoint','peak'})));

% Windows
p.addParameter('displayHalfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);  % plotting (±30 ms)
p.addParameter('metricHalfWidthMs',  5e-3,  @(x)isfinite(x)&&x>0);  % metrics (±5 ms)

% Excel mapping & bounds
p.addParameter('indexBase','auto', @(s) any(strcmpi(s,{'auto','zero','one'})));
p.addParameter('evtOffset',0, @(x)isscalar(x)&&isfinite(x));
p.addParameter('maxEvents',[], @(x) isempty(x) || (isscalar(x) && x>0));

% Output
p.addParameter('saveDir','', @(s)ischar(s)||isstring(s));
p.addParameter('tag','ALL', @(s)ischar(s)||isstring(s));

% Y-axis control (GLOBAL across all figures)
p.addParameter('yLimMicroV', [], @(x) isempty(x) || (isscalar(x) && x>0)); % if set, use ±this value
p.addParameter('yRobustPct', 99.5, @(x) isfinite(x) && x>0 && x<100);      % robust percentile if yLim not provided
p.addParameter('yPadFrac', 0.10, @(x) isfinite(x) && x>=0 && x<=0.5);      % extra headroom

p.parse(excelPath, dataMatPath, varargin{:});

excelPath      = string(p.Results.excelPath);
dataMatPath    = string(p.Results.dataMatPath);
channelIndices = p.Results.channelIndices;
scaleToMicroV  = p.Results.scaleToMicroV;
alignMode      = lower(string(p.Results.align));
displayHWms    = p.Results.displayHalfWidthMs;
metricHWms     = p.Results.metricHalfWidthMs;
indexBase      = lower(string(p.Results.indexBase));
evtOffset      = p.Results.evtOffset;
maxEvents      = p.Results.maxEvents;
saveDir        = string(p.Results.saveDir);
tagStr         = string(p.Results.tag);
yLimMicroV     = p.Results.yLimMicroV;
yRobustPct     = p.Results.yRobustPct;
yPadFrac       = p.Results.yPadFrac;

assert(isfile(excelPath),  'Excel not found: %s', excelPath);
assert(isfile(dataMatPath),'Data MAT not found: %s', dataMatPath);

% --- Load raw data (expecting µV unless scaled) ---
mf = matfile(dataMatPath);
try sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRowsAll = size(mf,'d',1);
nSamp    = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end %#ok<NASGU>

if isempty(channelIndices)
    chList = 1:nRowsAll;
else
    chList = channelIndices(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);

if saveDir==""
    [saveDir,~,~] = fileparts(excelPath);
end
if ~exist(saveDir,'dir'), mkdir(saveDir); end

% --- Read Excel & normalize to sample indices ---
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
    if width(T) < 2, error('Excel must have [on_samp, off_samp] or [on_sec, off_sec].'); end
    onSamp  = double(T{:,1});
    offSamp = double(T{:,2});
end

switch indexBase
    case "zero", onSamp = onSamp+1; offSamp = offSamp+1;
    case "auto"
        if any(onSamp < 1 | offSamp < 1 | onSamp==0 | offSamp==0)
            onSamp = onSamp+1; offSamp = offSamp+1;
        end
    case "one"
        % no-op
end

NeventsAll = numel(onSamp);
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));
Nevents = NeventsAll;
if ~isempty(maxEvents), Nevents = min(NeventsAll, maxEvents); end

% --- Windows (samples & time axes) ---
HWdisp   = max(1, round(displayHWms * sfx));      % display half-width
HWmet    = max(1, round(metricHWms  * sfx));      % metrics half-width (±5 ms)
tRelDisp = (-HWdisp:HWdisp) / sfx * 1e3;          % ms

fprintf('EventStacks_AmpWidth: %d event rows (using %d), %d channels, sfx=%.1f Hz\n', ...
    NeventsAll, Nevents, nCh, sfx);

% --- Precompute anchors & global y-limit (consistent across ALL figures) ---
anchors = nan(Nevents,1);
validEvt = false(Nevents,1);
for e = 1:Nevents
    rowXL = e + evtOffset;
    if rowXL < 1 || rowXL > NeventsAll, continue; end
    s0_ev = max(1, round(onSamp(rowXL)));
    s1_ev = min(nSamp, round(offSamp(rowXL)));
    if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev), continue; end
    anchors(e) = round((s0_ev + s1_ev)/2);   % midpoint anchor
    validEvt(e) = true;
end
evtList = find(validEvt);
if isempty(evtList)
    warning('No usable events after bounds checks.'); return;
end

% Compute global y-limit
if isempty(yLimMicroV)
    rob = 0;
    for ii = 1:numel(evtList)
        e = evtList(ii);
        a = anchors(e);
        s0_disp = max(1, a - HWdisp);
        s1_disp = min(nSamp, a + HWdisp);
        for k = 1:nCh
            ch = chList(k);
            sc = scaleToMicroV; if numel(sc)>1, sc = sc(ch); end
            y = double(mf.d(ch, s0_disp:s1_disp)) * sc;
            y = y(isfinite(y));
            if isempty(y), continue; end
            p = prctile(abs(y), yRobustPct);
            if isfinite(p) && p > rob, rob = p; end
        end
    end
    if ~isfinite(rob) || rob==0, rob = 1; end
    yMax = (1 + yPadFrac) * rob;
else
    yMax = yLimMicroV;
end
yL_global = [-yMax, +yMax];
fprintf('Global y-limit set to ±%.1f µV (mode: %s)\n', yMax, tern(isempty(yLimMicroV),'robust','fixed'));

% --- Iterate events and plot (1 PNG per event) ---
for ii = 1:numel(evtList)
    e = evtList(ii);
    rowXL = e + evtOffset;
    s0_ev = max(1, round(onSamp(rowXL)));
    s1_ev = min(nSamp, round(offSamp(rowXL)));
    anchor = anchors(e);

    s0_disp = max(1, anchor - HWdisp);
    s1_disp = min(nSamp, anchor + HWdisp);

    % --- Figure (one per event) ---
    perRowPx = 92; basePx = 230; maxPx = 5200;
    figH = min(maxPx, basePx + perRowPx * nCh);
    f = figure('Color','w','Position',[60 60 980 figH],'Visible','off');
    tl = tiledlayout(f, nCh, 1, 'Padding','compact','TileSpacing','compact');

    for k = 1:nCh
        ch = chList(k);
        sc = scaleToMicroV; if numel(sc)>1, sc = sc(ch); end

        % display segment (±display window)
        yplot = double(mf.d(ch, s0_disp:s1_disp)) * sc;

        % metrics segment (±5 ms window)
        s0_met = max(1, anchor - HWmet);
        s1_met = min(nSamp, anchor + HWmet);
        ymet  = double(mf.d(ch, s0_met:s1_met)) * sc;

        % amplitude = absolute extremum within ±5 ms; half-width at half-amplitude
        amp_uV = NaN; width_ms = NaN; tPk_ms = NaN; tL_ms = NaN; tR_ms = NaN; sgn = +1;
        if ~isempty(ymet) && all(isfinite(ymet)) && numel(ymet) >= 3
            [mx, kMax] = max(ymet);
            [mn, kMin] = min(ymet);
            if abs(mn) > abs(mx)
                sgn = -1; amp_uV = abs(mn); pkRel = kMin;
            else
                sgn = +1; amp_uV = abs(mx); pkRel = kMax;
            end

            h = 0.5 * amp_uV;     % half-amplitude level from zero
            sig = sgn * ymet;     % make chosen peak positive

            % Left crossing
            kL = pkRel;
            while kL > 1 && sig(kL) >= h, kL = kL - 1; end
            if kL >= 1 && (kL+1) <= numel(sig)
                left_ip = kL + (h - sig(kL)) / (sig(kL+1) - sig(kL));
            else
                left_ip = NaN;
            end
            % Right crossing
            kR = pkRel; L = numel(sig);
            while kR < L && sig(kR) >= h, kR = kR + 1; end
            if (kR-1) >= 1 && kR <= L
                right_ip = (kR-1) + (h - sig(kR-1)) / (sig(kR) - sig(kR-1));
            else
                right_ip = NaN;
            end

            if isfinite(left_ip) && isfinite(right_ip) && right_ip > left_ip
                width_ms = (right_ip - left_ip) / sfx * 1e3;
                tPk_ms   = ((s0_met + pkRel    - 1) - anchor) / sfx * 1e3;
                tL_ms    = ((s0_met + left_ip  - 1) - anchor) / sfx * 1e3;
                tR_ms    = ((s0_met + right_ip - 1) - anchor) / sfx * 1e3;
            end
        end

        % --- Plot ---
        nexttile(tl); hold on; box on; grid on;
        if ~isempty(yplot), plot(tRelDisp, yplot, 'LineWidth', 1.5); end
        xline(0,'--k','LineWidth',0.9); yline(0,':','Color',[0.7 0.7 0.7]);
        ylim(yL_global);

        % half-width markers: RED
        if isfinite(tL_ms) && isfinite(tR_ms)
            xline(tL_ms, '-', 'Color',[0.85 0.10 0.10], 'LineWidth',2.2, 'HandleVisibility','off');
            xline(tR_ms, '-', 'Color',[0.85 0.10 0.10], 'LineWidth',2.2, 'HandleVisibility','off');
            plot([tL_ms tR_ms],[0 0], '-', 'Color',[0.85 0.10 0.10], 'LineWidth',1.4, 'HandleVisibility','off');
        end

        % peak dot (if within display window)
        if isfinite(tPk_ms) && tPk_ms >= tRelDisp(1) && tPk_ms <= tRelDisp(end) && isfinite(amp_uV)
            plot(tPk_ms, sgn*amp_uV, 'o', 'MarkerSize', 4.5, ...
                 'MarkerFaceColor',[0 0 0], 'MarkerEdgeColor','none', 'HandleVisibility','off');
        end

        % Title (unbolded) with metrics
        if ~isempty(kept_channels)
            chName = sprintf('row %d (CSC%d)', ch, kept_channels(ch));
        else
            chName = sprintf('row %d', ch);
        end
        if isfinite(amp_uV) && isfinite(width_ms)
            ttlTxt = sprintf('%s  |  amp=%.1f \\muV  |  HW=%.2f ms', chName, amp_uV, width_ms);
        else
            ttlTxt = sprintf('%s  |  amp=NA  |  HW=NA', chName);
        end
        title(ttlTxt, 'FontSize',9, 'FontWeight','normal');

        ax = gca; ax.FontSize = 8;
        if k < nCh, ax.XTickLabel = []; else, xlabel('ms'); end
        ylabel('\muV');
    end

    sg = sprintf('Event %d  |  align: midpoint  |  display: \\pm%.1f ms  |  metrics: \\pm%.1f ms  |  channels=%d  |  %s', ...
                 e, 1e3*HWdisp/sfx, 1e3*HWmet/sfx, nCh, tagStr);
    sgtitle(tl, sg, 'FontSize',12,'FontWeight','bold');

    outPng = fullfile(saveDir, sprintf('Evt%03d_Stack_ampHW_globalY_dispHW%ds_metHW%ds.png', ...
        e, HWdisp, HWmet));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved: %s\n', outPng);
end
end

% --- helper ---
function s = tern(cond, a, b)
if cond, s = a; else, s = b; end
end
