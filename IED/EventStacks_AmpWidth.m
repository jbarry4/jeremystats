function EventStacks_AmpWidth(excelPath, dataMatPath, varargin)

p = inputParser;
p.addRequired('excelPath', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

% Data / channels / scaling
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);

% Peak detection & alignment (display center)
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'})));
p.addParameter('align','midpoint', @(s) any(strcmpi(s,{'midpoint','peak'})));   % default: preserve temporal lags

% Windows
p.addParameter('displayHalfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);               % for plotting
p.addParameter('metricHalfWidthMs',  7.5e-3, @(x)isfinite(x)&&x>0);              % for amp & half-width calc (±7.5ms)

% Excel mapping & bounds
p.addParameter('indexBase','auto', @(s) any(strcmpi(s,{'auto','zero','one'})));
p.addParameter('evtOffset',0, @(x)isscalar(x)&&isfinite(x));
p.addParameter('maxEvents',[], @(x) isempty(x) || (isscalar(x) && x>0));

% Output
p.addParameter('saveDir','', @(s)ischar(s)||isstring(s));
p.addParameter('tag','ALL', @(s)ischar(s)||isstring(s));

p.parse(excelPath, dataMatPath, varargin{:});

excelPath      = string(p.Results.excelPath);
dataMatPath    = string(p.Results.dataMatPath);
channelIndices = p.Results.channelIndices;
scaleToMicroV  = p.Results.scaleToMicroV;
peakPolarity   = lower(string(p.Results.peakPolarity));
alignMode      = lower(string(p.Results.align));
displayHWms    = p.Results.displayHalfWidthMs;
metricHWms     = p.Results.metricHalfWidthMs;
indexBase      = lower(string(p.Results.indexBase));
evtOffset      = p.Results.evtOffset;
maxEvents      = p.Results.maxEvents;
saveDir        = string(p.Results.saveDir);
tagStr         = string(p.Results.tag);

assert(isfile(excelPath),  'Excel not found: %s', excelPath);
assert(isfile(dataMatPath),'Data MAT not found: %s', dataMatPath);

% --- Load raw data ---
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
HWdisp  = max(1, round(displayHWms * sfx));      % display half-width in samples
HWmet   = max(1, round(metricHWms  * sfx));      % metric half-width in samples
tRelDisp = (-HWdisp:HWdisp) / sfx * 1e3;         % ms

fprintf('EventStacks_AmpWidth: %d event rows (using %d), %d channels, sfx=%.1f Hz, display ±%.1f ms, metrics ±%.1f ms\n', ...
    NeventsAll, Nevents, nCh, sfx, 1e3*HWdisp/sfx, 1e3*HWmet/sfx);

% --- Iterate events ---
nBad = 0;
for e = 1:Nevents
    rowXL = e + evtOffset;
    if rowXL < 1 || rowXL > NeventsAll
        alt = e;
        if alt >= 1 && alt <= NeventsAll
            rowXL = alt;
        else
            nBad = nBad + 1; continue;
        end
    end
    s0_ev = max(1, round(onSamp(rowXL)));
    s1_ev = min(nSamp, round(offSamp(rowXL)));
    if ~isfinite(s0_ev) || ~isfinite(s1_ev) || s1_ev <= s0_ev
        nBad = nBad + 1; continue;
    end

    if alignMode == "midpoint"
        anchor = round((s0_ev + s1_ev)/2);
    else
        % you could implement per-channel peak centers for display if needed; midpoint is stable for lag viewing
        anchor = round((s0_ev + s1_ev)/2);
    end

    s0_disp = max(1, anchor - HWdisp);
    s1_disp = min(nSamp, anchor + HWdisp);

    % --- Figure (one per event) ---
    perRowPx = 92; basePx = 230; maxPx = 5200;
    figH = min(maxPx, basePx + perRowPx * nCh);
    f = figure('Color','w','Position',[60 60 980 figH],'Visible','off');
    tl = tiledlayout(f, nCh, 1, 'Padding','compact','TileSpacing','compact');

    % consistent y-limits across channels for this event
    yMaxAbs = 1;
    for k = 1:nCh
        ch = chList(k);
        yplot = double(mf.d(ch, s0_disp:s1_disp)) * scaleToMicroV;
        if ~isempty(yplot)
            yMaxAbs = max(yMaxAbs, max(abs(yplot(~isnan(yplot)))));
        end
    end
    yPad = 1.08; yL = [-yPad*yMaxAbs, yPad*yMaxAbs];

    for k = 1:nCh
        ch = chList(k);

        % --- Signals: display and metric (metrics limited to ±metricHW around anchor) ---
        yplot = double(mf.d(ch, s0_disp:s1_disp)) * scaleToMicroV;               % for plotting (±display)
        s0_met = max(1, anchor - HWmet);
        s1_met = min(nSamp, anchor + HWmet);
        ymet  = double(mf.d(ch, s0_met:s1_met)) * scaleToMicroV;                 % for metrics only (±7.5ms)

        % --- Compute amplitude (peak from zero) and half-width within metric window only ---
        amp_uV = NaN; width_ms = NaN; tPk_ms = NaN; tL_ms = NaN; tR_ms = NaN;

        if ~isempty(ymet) && all(isfinite(ymet)) && numel(ymet) >= 5
            switch peakPolarity
                case "pos"
                    [pVal, pkRel] = max(ymet); sig = ymet; sgn = +1;
                case "neg"
                    [pVal, pkRel] = min(ymet); sig = -ymet; sgn = -1; pVal = -pVal;
                otherwise % 'abs'
                    [pMax, kMax] = max(ymet);
                    [pMin, kMin] = min(ymet);
                    if abs(pMin) > abs(pMax)
                        pVal  = -pMin; pkRel = kMin; sig = -ymet; sgn = -1;
                    else
                        pVal  =  pMax; pkRel = kMax; sig =  ymet; sgn = +1;
                    end
            end

            % Prominence-like base inside metric window
            left_min  = min(sig(1:pkRel));
            right_min = min(sig(pkRel:end));
            baseLevel = max(left_min, right_min);
            prom_uV   = pVal - baseLevel;

            if isfinite(prom_uV) && prom_uV > 0
                h = pVal - 0.5*prom_uV;  % half-prom height

                % Left crossing within metric window
                kL = pkRel;
                while kL > 1 && sig(kL) >= h, kL = kL - 1; end
                if kL >= 1 && (kL+1) <= numel(sig)
                    x0=kL; y0=sig(kL); x1=kL+1; y1=sig(kL+1);
                    left_ip = x0 + (h - y0) / (y1 - y0);
                else
                    left_ip = NaN;
                end

                % Right crossing within metric window
                kR = pkRel; L = numel(sig);
                while kR < L && sig(kR) >= h, kR = kR + 1; end
                if (kR-1) >= 1 && kR <= L
                    x0=kR-1; y0=sig(kR-1); x1=kR; y1=sig(kR);
                    right_ip = x0 + (h - y0) / (y1 - y0);
                else
                    right_ip = NaN;
                end

                if isfinite(left_ip) && isfinite(right_ip) && right_ip > left_ip
                    width_samp = right_ip - left_ip;
                    width_ms   = (width_samp / sfx) * 1e3;
                    amp_uV     = abs(sgn * ymet(pkRel));     % amplitude from zero
                    % Convert to display-time axis (relative to anchor)
                    tPk_ms = ((s0_met + pkRel   - 1) - anchor) / sfx * 1e3;
                    tL_ms  = ((s0_met + left_ip - 1) - anchor) / sfx * 1e3;
                    tR_ms  = ((s0_met + right_ip- 1) - anchor) / sfx * 1e3;
                end
            end
        end

        % --- Plot ---
        nexttile(tl); hold on; box on; grid on;
        if ~isempty(yplot)
            plot(tRelDisp, yplot, 'LineWidth', 1.5);
        end
        xline(0,'--k','LineWidth',0.9); yline(0,':','Color',[0.7 0.7 0.7]);
        ylim(yL);

        % half-width markers (RED, thicker)
        if isfinite(tL_ms) && isfinite(tR_ms)
            xl1 = xline(tL_ms, '-', 'Color',[0.85 0.10 0.10], 'LineWidth',2.0, 'HandleVisibility','off');
            xl2 = xline(tR_ms, '-', 'Color',[0.85 0.10 0.10], 'LineWidth',2.0, 'HandleVisibility','off');
            % optional: draw a faint red bar between them at y=0 for visibility
            plot([tL_ms tR_ms],[0 0], '-', 'Color',[0.85 0.10 0.10], 'LineWidth',1.2, 'HandleVisibility','off');
        end

        % peak dot (only if within display window)
        if isfinite(tPk_ms) && tPk_ms >= tRelDisp(1) && tPk_ms <= tRelDisp(end)
            yPkVal = sgn * (isfinite(amp_uV) * amp_uV);  %#ok<NASGU>
            % get actual peak value from ymet to plot (original sign)
            yPkVal = sgn * pVal;
            plot(tPk_ms, yPkVal, 'o', 'MarkerSize', 4.5, 'MarkerFaceColor',[0 0 0], 'MarkerEdgeColor','none', 'HandleVisibility','off');
        end

        % Title & per-channel label (ALWAYS draw one label)
        if ~isempty(kept_channels)
            ttl = sprintf('row %d (CSC%d)', ch, kept_channels(ch));
        else
            ttl = sprintf('row %d', ch);
        end
        title(ttl, 'FontSize', 8);

        if isfinite(amp_uV) && isfinite(width_ms)
            txt = sprintf('amp=%.1f \\muV  |  HW=%.2f ms', amp_uV, width_ms);
        else
            txt = 'amp=NA  |  HW=NA';
        end

        % Place top-right, always inside axes; make it visible
        text(0.985, 0.95, txt, 'Units','normalized', ...
            'HorizontalAlignment','right','VerticalAlignment','top', ...
            'FontSize',8, 'BackgroundColor','w', 'Margin',3, ...
            'EdgeColor',[0.85 0.85 0.85], 'Clipping','on');

        ax = gca; ax.FontSize = 8;
        if k < nCh, ax.XTickLabel = []; else, xlabel('ms'); end
        ylabel('\muV');
    end

    alignLabel = 'midpoint';
    if alignMode ~= "midpoint"
        alignLabel = sprintf('peak(%s)', peakPolarity);
    end
    sg = sprintf('Event %d  |  align: %s  |  display: \\pm%.1f ms  |  metrics: \\pm%.1f ms  |  channels=%d  |  %s', ...
                 e, alignLabel, 1e3*HWdisp/sfx, 1e3*HWmet/sfx, nCh, tagStr);
    sgtitle(tl, sg, 'FontSize',12,'FontWeight','bold');

    outPng = fullfile(saveDir, sprintf('Evt%03d_Stack_ampHW_align-%s_dispHW%ds_metHW%ds.png', ...
        e, regexprep(alignLabel,'[^a-zA-Z0-9]+','_'), HWdisp, HWmet));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved: %s\n', outPng);
end

if nBad>0
    fprintf('Skipped %d event(s) (bad/missing indices/out-of-bounds).\n', nBad);
end
end
