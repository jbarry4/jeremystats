function SpikeAmpWidthScatter(excelPath, dataMatPath, varargin)
% Minimal script-style function: reads spike windows from Excel + raw .mat
% Computes per-event, per-channel peak amplitude and half-prominence width
% Outputs a single scatter plot: Half-width (ms) vs Amplitude (µV)

p = inputParser;
p.addRequired('excelPath', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);
p.addParameter('peakPolarity','abs', @(s) any(strcmpi(s,{'abs','pos','neg'}))); % how to pick the peak in a window
p.addParameter('ampMetric','prominence', @(s) any(strcmpi(s,{'prominence','peak'}))); % y-axis metric
p.addParameter('indexBase','auto', @(s) any(strcmpi(s,{'auto','zero','one'}))); % Excel sample base
p.addParameter('evtOffset',0, @(x)isscalar(x)&&isfinite(x)); % if your Excel rows are shifted
p.addParameter('maxEvents',[], @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('saveDir','', @(s)ischar(s)||isstring(s));
p.addParameter('tag','ALL', @(s)ischar(s)||isstring(s)); % label for output filenames
p.parse(excelPath, dataMatPath, varargin{:});

excelPath      = string(p.Results.excelPath);
dataMatPath    = string(p.Results.dataMatPath);
channelIndices = p.Results.channelIndices;
scaleToMicroV  = p.Results.scaleToMicroV;
peakPolarity   = lower(string(p.Results.peakPolarity));
ampMetric      = lower(string(p.Results.ampMetric));
indexBase      = lower(string(p.Results.indexBase));
evtOffset      = p.Results.evtOffset;
maxEvents      = p.Results.maxEvents;
saveDir        = string(p.Results.saveDir);
tagStr         = string(p.Results.tag);

assert(isfile(excelPath), 'Excel not found: %s', excelPath);
assert(isfile(dataMatPath), 'Data MAT not found: %s', dataMatPath);

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

% ---------- Read Excel (robust columns) ----------
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

Nevents = numel(onSamp);
onSamp  = max(1, min(onSamp,  nSamp));
offSamp = max(1, min(offSamp, nSamp));
if ~isempty(maxEvents), Nevents = min(Nevents, maxEvents); end

fprintf('SpikeAmpWidthScatter: %d events, %d channels, sfx=%.1f Hz\n', Nevents, nCh, sfx);

% ---------- Compute metrics ----------
xs_width_ms = [];   % x = half-width (ms)
ys_amp_uV   = [];   % y = amplitude (µV)
ev_idx      = [];   % event index
ch_idx      = [];   % channel index

nBad = 0;
for e = 1:Nevents
    rowXL = e + evtOffset;
    if rowXL < 1 || rowXL > numel(onSamp)
        alt = e;
        if alt >= 1 && alt <= numel(onSamp)
            rowXL = alt;
        else
            nBad = nBad + 1;
            continue;
        end
    end

    s0 = max(1, round(onSamp(rowXL)));
    s1 = min(nSamp, round(offSamp(rowXL)));
    if ~isfinite(s0) || ~isfinite(s1) || s1 <= s0
        nBad = nBad + 1;
        continue;
    end

    if e <= 3
        fprintf('Evt %d -> on=%d off=%d (len=%d samp; %.2f ms)\n', ...
            e, s0, s1, s1-s0+1, 1e3*(s1-s0+1)/sfx);
    end

    for k = 1:nCh
        ch = chList(k);
        yseg = double(mf.d(ch, s0:s1)) * scaleToMicroV; % µV
        if any(~isfinite(yseg)) || numel(yseg) < 5, continue; end

        % choose peak
        switch peakPolarity
            case "pos"
                [pVal, pkRel] = max(yseg);
                sig = yseg; sgn = +1;
            case "neg"
                [pVal, pkRel] = min(yseg);
                sig = -yseg; sgn = -1;      % make it positive-peak for width math
                pVal = -pVal;               % magnitude
            otherwise % 'abs'
                [pMax, kMax] = max(yseg);
                [pMin, kMin] = min(yseg);
                if abs(pMin) > abs(pMax)
                    pVal  = -pMin; pkRel = kMin; sig = -yseg; sgn = -1;
                else
                    pVal  =  pMax; pkRel = kMax; sig =  yseg; sgn = +1;
                end
        end

        % prominence-like base within the window (SciPy-style)
        left_min  = min(sig(1:pkRel));
        right_min = min(sig(pkRel:end));
        baseLevel = max(left_min, right_min);
        prom_uV   = pVal - baseLevel;
        if ~isfinite(prom_uV) || prom_uV <= 0, continue; end

        % half-prominence height
        h = pVal - 0.5*prom_uV;

        % find left crossing
        kL = pkRel;
        while kL > 1 && sig(kL) >= h
            kL = kL - 1;
        end
        if kL == pkRel && sig(kL) < h, continue; end
        if kL < 1, continue; end
        x0 = kL;    y0 = sig(kL);
        x1 = kL+1;  y1 = sig(kL+1);
        left_ip = x0 + (h - y0) / (y1 - y0);

        % find right crossing
        kR = pkRel;
        L  = numel(sig);
        while kR < L && sig(kR) >= h
            kR = kR + 1;
        end
        if kR > L, continue; end
        x0 = kR-1;  y0 = sig(kR-1);
        x1 = kR;    y1 = sig(kR);
        right_ip = x0 + (h - y0) / (y1 - y0);

        width_samp = right_ip - left_ip;          % samples
        width_ms   = (width_samp / sfx) * 1e3;    % ms

        switch ampMetric
            case "prominence"
                amp_uV = prom_uV;                 % relative to base
            otherwise % 'peak'
                amp_uV = abs(sgn * yseg(pkRel));  % absolute peak magnitude from zero
        end

        if isfinite(width_ms) && isfinite(amp_uV) && width_ms > 0
            xs_width_ms(end+1,1) = width_ms; %#ok<AGROW>
            ys_amp_uV(end+1,1)   = amp_uV;   %#ok<AGROW>
            ev_idx(end+1,1)      = e;        %#ok<AGROW>
            ch_idx(end+1,1)      = ch;       %#ok<AGROW>
        end
    end
end

if nBad>0
    fprintf('Skipped %d event(s) (bad indices/out-of-bounds).\n', nBad);
end
fprintf('Collected %d spike measurements.\n', numel(xs_width_ms));

% ---------- Plot scatter ----------
f = figure('Color','w','Position',[80 80 920 700]);
scatter(xs_width_ms, ys_amp_uV, 12, ch_idx, 'filled'); % color by channel index
grid on; box on;
xlabel('Half-width at half-prominence (ms)');
ylabel( sprintf('Spike amplitude (%s) [\\muV]', ampMetric) );
cb = colorbar; cb.Label.String = 'Channel index';
title(sprintf('Amplitude vs Half-width  |  events=%d  channels=%d  (%s)', Nevents, nCh, tagStr));

outPng = fullfile(saveDir, sprintf('AmpVsHalfWidth_%s_%s.png', ampMetric, tagStr));
exportgraphics(f, outPng, 'Resolution', 220);
close(f);
fprintf('Saved: %s\n', outPng);

% ---------- Save table of results ----------
outMat = fullfile(saveDir, sprintf('AmpWidthMetrics_%s_%s.mat', ampMetric, tagStr));
outCsv = fullfile(saveDir, sprintf('AmpWidthMetrics_%s_%s.csv', ampMetric, tagStr));
metrics = table(ev_idx, ch_idx, xs_width_ms, ys_amp_uV, ...
    'VariableNames', {'event','channel','halfWidth_ms','amplitude_uV'});
save(outMat, 'metrics', 'ampMetric', 'scaleToMicroV', 'sfx', 'channelIndices');
writetable(metrics, outCsv);
fprintf('Saved: %s\nSaved: %s\n', outMat, outCsv);
end
