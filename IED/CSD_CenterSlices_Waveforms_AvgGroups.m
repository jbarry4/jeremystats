function CSD_CenterSlices_Waveforms_AvgGroups(inputFolder, dataMatPath, varargin)
% CSD_CenterSlices_Waveforms_AvgGroups
% For each group (SOLID, SPUTTER):
%   • Align events by first channel's POSITIVE peak (±anchorHalfWidthMs) using Excel on/off windows
%   • Compute per-event CSD in a ±winHalfWidthMs window
%   • Extract the CSD slice at time = 0 ms (center of the aligned window)
%   • FIGURE (per group):
%       LEFT  : image of all per-event 0 ms CSD slices (channels × events), each repeated in X by 'sliceThickness'
%       RIGHT : vertical-wave view (x = CSD value, y = channels), all events (thin gray) + mean (bold)
%   • Common robust scaling for both panels (symmetric, shared between left/right inside each group)
%
% OUTPUT:
%   <inputFolder>/CSD Center Slices Output/CSD_CenterSlices_SOLID.png
%   <inputFolder>/CSD Center Slices Output/CSD_CenterSlices_SPUTTER.png
%
% REQUIRED in dataMat:
%   d [nRows x nSamp], sfx (Hz). kept_channels optional (for labels).
%
% -------------------------------------------------------------------------

% ---------- Args ----------
p = inputParser;
p.addRequired('inputFolder', @(s)ischar(s)||isstring(s));
p.addRequired('dataMatPath', @(s)ischar(s)||isstring(s));

p.addParameter('excelPath', "", @(s)ischar(s)||isstring(s));
p.addParameter('channelIndices', [], @(v) isempty(v) || (isnumeric(v) && all(v>=1)));
p.addParameter('scaleToMicroV', 1, @(x)isnumeric(x) && all(isfinite(x)) && all(x>0));

p.addParameter('winHalfWidthMs',    20e-3, @(x)isfinite(x)&&x>0);   % ±20 ms around anchor
p.addParameter('anchorHalfWidthMs',  5e-3, @(x)isfinite(x)&&x>0);   % ±5 ms anchor search

p.addParameter('sliceThickness', 6, @(x)isfinite(x) && x>=1 && mod(x,1)==0); % pixels/columns per event
p.addParameter('robustPct',    99.5, @(x) isfinite(x) && x>0 && x<100);
p.addParameter('padFrac',       0.12, @(x) isfinite(x) && x>=0 && x<=0.5);

p.addParameter('maxEventsPerGroup', [], @(x) isempty(x) || (isscalar(x) && x>0));

p.parse(inputFolder, dataMatPath, varargin{:});

inputFolder   = string(p.Results.inputFolder);
dataMatPath   = string(p.Results.dataMatPath);
excelPath     = string(p.Results.excelPath);
channelIdx    = p.Results.channelIndices;
scaleToMicroV = p.Results.scaleToMicroV;

winHWms       = p.Results.winHalfWidthMs;
anchorHWms    = p.Results.anchorHalfWidthMs;

sliceThick    = p.Results.sliceThickness;
robPct        = p.Results.robustPct;
padFrac       = p.Results.padFrac;

maxEventsPer  = p.Results.maxEventsPerGroup;

% ---------- Layout ----------
solidDir   = fullfile(inputFolder, "Solid");
sputterDir = fullfile(inputFolder, "Sputter");
assert(isfolder(solidDir),   'Missing folder: %s', solidDir);
assert(isfolder(sputterDir), 'Missing folder: %s', sputterDir);

if excelPath == ""
    xl = dir(fullfile(inputFolder, "*.xlsx"));
    assert(~isempty(xl), 'No Excel file (*.xlsx) found in %s', inputFolder);
    excelPath = fullfile(xl(1).folder, xl(1).name);
end
assert(isfile(excelPath), 'Excel not found: %s', excelPath);

outRoot = fullfile(inputFolder, "CSD Center Slices Output");
if ~exist(outRoot,'dir'), mkdir(outRoot); end
outSOL = fullfile(outRoot, "CSD_CenterSlices_SOLID.png");
outSPU = fullfile(outRoot, "CSD_CenterSlices_SPUTTER.png");

% ---------- Data ----------
assert(isfile(dataMatPath), 'Data MAT not found: %s', dataMatPath);
mf = matfile(dataMatPath);
try sfx = mf.sfx; catch, error('Missing "sfx" in data MAT.'); end
nRowsAll = size(mf,'d',1);
nSamp    = size(mf,'d',2);
try kept_channels = mf.kept_channels; catch, kept_channels = []; end %#ok<NASGU>

% Channels
if isempty(channelIdx)
    chList = 1:nRowsAll;
else
    chList = channelIdx(:).';
    chList = chList(chList>=1 & chList<=nRowsAll);
end
nCh = numel(chList);

% Scaling
if numel(scaleToMicroV)==1
    scaleVec = repmat(scaleToMicroV, nRowsAll, 1);
else
    assert(numel(scaleToMicroV) >= nRowsAll, 'scaleToMicroV must be scalar or length >= nRowsAll.');
    scaleVec = scaleToMicroV(:);
end

% ---------- Windows ----------
HWwin    = max(1, round(winHWms    * sfx));  % ±display half-width
HWanchor = max(1, round(anchorHWms * sfx));  % ±anchor search
tRelMs   = (-HWwin:HWwin) / sfx * 1e3;       % centered at 0
centerIdx= HWwin + 1;

fprintf('CSD Center Slices: sfx=%.1f Hz | window ±%.1f ms | anchor: firstCh max (±%.1f ms)\n', ...
    sfx, 1e3*HWwin/sfx, 1e3*HWanchor/sfx);

% ---------- Excel -> sample indices ----------
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

% ---------- Events from PNG names ----------
evtSOL = parseEvtNumsFromPngs(solidDir);
evtSPU = parseEvtNumsFromPngs(sputterDir);
fprintf('Found %d SOLID, %d SPUTTER events (by filenames).\n', numel(evtSOL), numel(evtSPU));
if ~isempty(maxEventsPer)
    evtSOL = evtSOL(1:min(end, maxEventsPer));
    evtSPU = evtSPU(1:min(end, maxEventsPer));
end

% ---------- Build & render ----------
buildAndRender(evtSOL, 'SOLID', outSOL);
buildAndRender(evtSPU, 'SPUTTER', outSPU);

fprintf('Saved:\n  %s\n  %s\n', outSOL, outSPU);

% ============================= HELPERS =============================

    function buildAndRender(evtList, tag, outPath)
        if isempty(evtList)
            warning('%s: no events to plot.', tag); 
            return;
        end

        S = nan(nCh, numel(evtList));  % per-event slice at 0 ms (channels x events)
        used = false(numel(evtList),1);

        for ii = 1:numel(evtList)
            e = evtList(ii);
            rowXL = e;
            if rowXL < 1 || rowXL > NrowsXL, continue; end

            s0_ev = round(onSamp(rowXL));
            s1_ev = round(offSamp(rowXL));
            if ~(isfinite(s0_ev) && isfinite(s1_ev) && s1_ev > s0_ev), continue; end

            % Anchor by first-channel positive peak (±anchor window)
            ancMid = round((s0_ev + s1_ev)/2);
            s0a = max(1, ancMid - HWanchor);
            s1a = min(nSamp, ancMid + HWanchor);
            refCh = chList(1);
            y0 = double(mf.d(refCh, s0a:s1a)) * scaleVec(refCh);
            if isempty(y0) || all(~isfinite(y0)), continue; end
            [~, k_rel] = max(y0);
            anchor = s0a + k_rel - 1;

            % Window around anchor
            s0 = anchor - HWwin;
            s1 = anchor + HWwin;
            if s0 < 1 || s1 > nSamp, continue; end

            % Extract voltage block (channels x time) then CSD
            Y = nan(nCh, 2*HWwin+1);
            for k = 1:nCh
                ch = chList(k);
                sc = scaleVec(ch);
                y = double(mf.d(ch, s0:s1)) * sc;
                if any(isfinite(y)), Y(k,:) = y; end
            end
            if all(~isfinite(Y(:))), continue; end

            C = computeCSD(Y); % channels x time

            % Slice at t = 0 ms
            S(:,ii) = C(:,centerIdx);
            used(ii) = true;
        end

        if ~any(used)
            warning('%s: no usable events after alignment and windowing.', tag);
            return;
        end

        S = S(:,used);          % keep only used
        nEvt = size(S,2);
        MU  = mean(S,2, 'omitnan'); % mean vertical waveform (channels)

        % Robust symmetric scale (shared by both panels)
        vals = abs(S(:));
        vals = vals(isfinite(vals));
        if isempty(vals), pval = 1; else, pval = prctile(vals, robPct); end
        clim = (1 + padFrac) * max(1, pval);

        % -------- Figure --------
        % Taller figure to fit labels & title; 1 at top (YDir=reverse)
        figH = min(300 + 14*nCh, 3200);
        f = figure('Color','w','Position',[60 60 1200 figH],'Visible','off');
        tl = tiledlayout(f, 1, 2, 'Padding','compact', 'TileSpacing','compact');

        % LEFT: slices “tiled” with thickness
        nexttile(tl); 
        hold on;
        % Build a (channels x (events*thickness)) image by repeating each column
        if sliceThick==1
            Img = S;
        else
            Img = repelem(S, 1, sliceThick); % repeat each event column sliceThick times
        end
        imagesc(1:size(Img,2), 1:nCh, Img);
        set(gca,'YDir','reverse');
        caxis([-clim, +clim]);
        colormap(jet); 
        colorbar;
        % x ticks at event centers
        if sliceThick >= 2
            centers = ( (0:nEvt-1)*sliceThick ) + ceil(sliceThick/2);
        else
            centers = 1:nEvt;
        end
        xticks(centers);
        xticklabels(string(1:nEvt));
        xlabel('Event #');
        % Channel labels
        if isempty(kept_channels)
            L = arrayfun(@(kk) sprintf('row %d', chList(kk)), 1:nCh, 'UniformOutput',false);
        else
            L = arrayfun(@(kk) sprintf('row %d (CSC%d)', chList(kk), kept_channels(chList(kk))), 1:nCh, 'UniformOutput',false);
        end
        set(gca,'YTick',1:nCh,'YTickLabel',L,'FontSize',9);
        ylabel('Channel (1 at top)');
        title(sprintf('%s — CSD slices at 0 ms (n=%d), CLim=\\pm%.2f', tag, nEvt, clim), 'FontSize', 10, 'FontWeight','bold');

        % RIGHT: vertical waveform — all (gray) + average (bold)
        nexttile(tl);
        hold on; box on; grid on;
        y = 1:nCh;
        set(gca,'YDir','reverse'); % 1 at top
        % all contributors (thin gray)
        for i = 1:nEvt
            plot(S(:,i), y, '-', 'Color', [0.6 0.6 0.6 0.7], 'LineWidth', 0.8);
        end
        % average (bold)
        plot(MU, y, '-', 'Color', [0 0 0], 'LineWidth', 2.0);
        % zero line (source/sink center)
        xline(0, '--k', 'LineWidth', 0.8);
        xlim([-clim, +clim]);
        ylim([1, nCh]);
        xlabel('CSD (− sink   |   + source)');
        yticks(1:nCh); yticklabels(L); set(gca,'FontSize',9);
        title(sprintf('%s — Vertical waveform @ 0 ms (mean in black)', tag), 'FontSize', 10, 'FontWeight','bold');

        % Super-title with window/anchor info (smaller to avoid crop)
        sg = sprintf('%s  |  align: first-channel max (\\pm%.1f ms)  |  window: \\pm%.1f ms  |  channels=%d', ...
            tag, 1e3*HWanchor/sfx, 1e3*HWwin/sfx, nCh);
        sgtitle(tl, sg, 'FontSize', 10, 'FontWeight', 'bold');

        exportgraphics(f, outPath, 'Resolution', 220);
        close(f);
        fprintf('Saved %s: %s\n', tag, outPath);
    end

end

% --------- utilities ---------

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

function C = computeCSD(Ych_t)
% Ych_t: (channels x time) voltage (µV). Returns (channels x time) CSD.
% Interior: standard 3-point stencil; edges replicated from nearest interior.
    [nCh, nT] = size(Ych_t);
    if nCh < 2
        C = nan(nCh, nT); return;
    elseif nCh == 2
        C = zeros(nCh, nT); return; % degenerate but not blank
    end
    Cint = -( Ych_t(3:end,:) - 2*Ych_t(2:end-1,:) + Ych_t(1:end-2,:) );
    C = zeros(nCh, nT);
    C(2:end-1,:) = Cint;
    C(1,:)   = C(2,:);
    C(end,:) = C(end-1,:);
    % (divide by h^2 if you want physical units)
end
