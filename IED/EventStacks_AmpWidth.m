function EventStacks_AmpWidth(excelPath, dataMatPath, varargin)
% Creates ONE PNG per event:
%   - rows-only (stacked) view of all channels
%   - each subplot labels spike amplitude (µV) and half-width at half-prominence (ms)
%   - vertical markers show left/right half-width crossings; dot marks peak
%
% INPUTS:
%   excelPath   : spreadsheet with on/off (samples or seconds)
%   dataMatPath : MAT with fields: d [nRows x nSamp], sfx (Hz), kept_channels (optional)
%
% DEFAULTS aim to preserve temporality across channels (align='midpoint').

p = inputParser;
p.addRequired('excelPath', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

% Data / channels / scaling
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);

% Peak detection & alignment
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'})));
p.addParameter('align','midpoint', @(s) any(strcmpi(s,{'midpoint','peak'})));  % default: preserve temporal lags
p.addParameter('displayHalfWidthMs', 30e-3, @(x)isfinite(x)&&x>0);              % half-window for plotting (ms)

% Excel mapping & bounds
p.addParameter('indexBase','auto', @(s) any(strcmpi(s,{'auto','zero','one'})));
p.addParameter('evtOffset',0, @(x)isscalar(x)&&isfinite(x));  % only set if your sheet is shifted
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
indexBase      = lower(string(p.Results.indexBase));
evtOffset      = p.Results.evtOffset;
maxEvents      = p.Results.maxEvents;
saveDir        = string(p.Results.saveDir);
tagStr         = string(p.Results.tag);

assert(isfile(excelPath),  'Excel not found: %s', excelPath);
assert(isfile(dataMatPath),'Data MAT not found: %s', dataMatPath);

% --- Load raw data (disk-backed) ---
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
    case "zero"
        onSamp  = onSamp + 1; offSamp = offSamp + 1;
    case "auto"
        if any(onSamp < 1 | offSamp < 1 | onSamp==0 | offSamp==0)
            onSamp  = onSamp + 1; offSamp = offSamp + 1;
        end
    case "one"
        % no-op
end

NeventsAll = numel(onSamp);
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));
Nevents = NeventsAll;
if ~isempty(maxEvents)
    Nevents = min(NeventsAll, maxEvents);
end

% --- Plot window (for display) ---
HW = max(1, round(displayHWms * sfx));        % half-width in samples for display panes
tRelSamples = -HW:HW;
tRelMs = (tRelSamples / sfx) * 1e3;

fprintf('EventStacks_AmpWidth: %d event rows (using %d), %d channels, sfx=%.1f Hz, display ±%.1f ms\n', ...
        NeventsAll, Nevents, nCh, sfx, 1e3*HW/sfx);

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

    if e <= 5
        fprintf('Evt %d -> on=%d off=%d (len=%d samp; %.2f ms)\n', ...
            e, s0_ev, s1_ev, s1_ev - s0_ev + 1, 1e3*(s1_ev - s0_ev + 1)/sfx);
    end

    % Shared anchor for display (preserve temporality)
    if alignMode == "midpoint"
        anchor = round((s0_ev + s1_ev)/2);
    else
        % Optional: channel-wise peak anchor for display (less temporal comparability)
        anchor = round((s0_ev + s1_ev)/2);
    end

    s0_disp = max(1, anchor - HW);
    s1_disp = min(nSamp, anchor + HW);

    % --- Figure (one per event) ---
    perRowPx = 90; basePx = 220; maxPx = 5200;
    figH = min(maxPx, basePx + perRowPx * nCh);
    f = figure('Color','w','Position',[60 60 980 figH],'Visible','off');
    tl = tiledlayout(f, nCh, 1, 'Padding','compact','TileSpacing','compact');

    % Collect a quick y-limit for consistent scaling within the event
    yMaxAbs = 1;
    for k = 1:nCh
        ch = chList(k);
        yplot = double(mf.d(ch, s0_disp:s1_disp)) * scaleToMicroV;
        if ~isempty(yplot)
            yMaxAbs = max(yMaxAbs, max(abs(yplot(~isnan(yplot)))));
        end
    end
    yPad = 1.05; yL = [-yPad*yMaxAbs, yPad*yMaxAbs];

    % Per-channel metrics for optional saving
    amp_uV_arr  = nan(nCh,1);
    hw_ms_arr   = nan(nCh,1);

    % --- Channel loop ---
    for k = 1:nCh
        ch = chList(k);

        % Measurement segment (within detected event)
        yseg = double(mf.d(ch, s0_ev:s1_ev)) * scaleToMicroV; % µV
        if isempty(yseg) || any(~isfinite(yseg))
            yseg = [];
        end

        % Display segment (anchor ± HW)
        yplot = double(mf.d(ch, s0_disp:s1_disp)) * scaleToMicroV; % µV

        % Compute peak & half-width within event window
        peak_ok = false; left_ip = NaN; right_ip = NaN; pkRel = NaN; amp_uV = NaN; width_ms = NaN; h = NaN; sig = []; sgn = +1;
        if ~isempty(yseg)
            switch peakPolarity
                case "pos"
                    [pVal, pkRel] = max(yseg); sig = yseg; sgn = +1;
                case "neg"
                    [pVal, pkRel] = min(yseg); sig = -yseg; sgn = -1; pVal = -pVal;
                otherwise % 'abs'
                    [pMax, kMax] = max(yseg);
                    [pMin, kMin] = min(yseg);
                    if abs(pMin) > abs(pMax)
                        pVal  = -pMin; pkRel = kMin; sig = -yseg; sgn = -1;
                    else
                        pVal  =  pMax; pkRel = kMax; sig =  yseg; sgn = +1;
                    end
            end

            if isfinite(pVal)
                left_min  = min(sig(1:pkRel));
                right_min = min(sig(pkRel:end));
                baseLevel = max(left_min, right_min);
                prom_uV   = pVal - baseLevel;

                if prom_uV > 0 && isfinite(prom_uV)
                    h = pVal - 0.5*prom_uV;          % half-prom height

                    % Left crossing
                    kL = pkRel;
                    while kL > 1 && sig(kL) >= h, kL = kL - 1; end
                    if kL >= 1 && (kL+1) <= numel(sig)
                        x0=kL; y0=sig(kL); x1=kL+1; y1=sig(kL+1);
                        left_ip = x0 + (h - y0) / (y1 - y0);
                    end

                    % Right crossing
                    kR = pkRel; L = numel(sig);
                    while kR < L && sig(kR) >= h, kR = kR + 1; end
                    if (kR-1) >= 1 && kR <= L
                        x0=kR-1; y0=sig(kR-1); x1=kR; y1=sig(kR);
                        right_ip = x0 + (h - y0) / (y1 - y0);
                    end

                    if isfinite(left_ip) && isfinite(right_ip) && right_ip>left_ip
                        width_samp = right_ip - left_ip;
                        width_ms   = (width_samp / sfx) * 1e3;
                        amp_uV     = abs(sgn * yseg(pkRel));   % amplitude from zero
                        peak_ok    = true;
                    end
                end
            end
        end

        amp_uV_arr(k) = amp_uV;
        hw_ms_arr(k)  = width_ms;

        % --- Plot channel ---
        nexttile(tl); hold on; box on; grid on;

        if ~isempty(yplot)
            plot(tRelMs, yplot, 'LineWidth', 1.4);
        end
        xline(0,'--k','LineWidth',0.8); yline(0,':','Color',[0.7 0.7 0.7]);
        ylim(yL);

        % Map feature times to display axis (relative to anchor)
        if peak_ok
            tPk_ms   = ((s0_ev + pkRel - 1) - anchor) / sfx * 1e3;
            tL_ms    = ((s0_ev + left_ip  - 1) - anchor) / sfx * 1e3;
            tR_ms    = ((s0_ev + right_ip - 1) - anchor) / sfx * 1e3;

            % half-width markers
            xl1 = xline(tL_ms, ':', 'HandleVisibility','off');
            xl2 = xline(tR_ms, ':', 'HandleVisibility','off');
            xl1.Color = [0.25 0.25 0.25];
            xl2.Color = [0.25 0.25 0.25];

            % peak dot (at display y if within plotting window)
            if tPk_ms >= tRelMs(1) && tPk_ms <= tRelMs(end)
                yPk = sgn * pVal; % in "sig", but peak amplitude from zero is amp_uV * sign
                plot(tPk_ms, sgn*amp_uV, 'o', 'MarkerSize', 4, 'HandleVisibility','off');
            end

            % annotation text
            txt = sprintf('amp=%.1f \\muV | HW=%.2f ms', amp_uV, width_ms);
        else
            txt = 'amp=NA | HW=NA';
            tPk_ms = NaN;
        end

        % Title & labels
        if ~isempty(kept_channels)
            ttl = sprintf('row %d (CSC%d)', ch, kept_channels(ch));
        else
            ttl = sprintf('row %d', ch);
        end
        title(ttl, 'FontSize', 8);

        % place annotation in upper-left corner of axes
        text(0.01, 0.92, txt, 'Units','normalized', 'FontSize',8, ...
            'BackgroundColor','w', 'Margin',2, 'EdgeColor',[0.85 0.85 0.85]);

        ax = gca; ax.FontSize = 8;
        if k < nCh, ax.XTickLabel = []; else, xlabel('ms'); end
        ylabel('\muV');
    end

    alignLabel = 'midpoint';
    if alignMode ~= "midpoint"
        alignLabel = sprintf('peak(%s)', peakPolarity);
    end
    sg = sprintf('Event %d  |  align: %s  |  display: \\pm%.1f ms  |  channels=%d  |  %s', ...
                 e, alignLabel, 1e3*HW/sfx, nCh, tagStr);
    sgtitle(tl, sg, 'FontSize',12,'FontWeight','bold');

    % Save one PNG per event
    outPng = fullfile(saveDir, sprintf('Evt%03d_Stack_ampHW_align-%s_HW%ds_%dms.png', ...
                    e, regexprep(alignLabel,'[^a-zA-Z0-9]+','_'), HW, round(1e3*HW/sfx)));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved: %s\n', outPng);
end

if nBad>0
    fprintf('Skipped %d event(s) (bad/missing indices/out-of-bounds).\n', nBad);
end

end
