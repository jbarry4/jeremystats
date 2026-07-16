function VACC_TheVision(dataDir, varargin)
% VACC_TheVision — simple, robust IED visualizer (Neuralynx .ncs)
% - Loads ets.mat / ech.mat from dataDir
% - Loads ALL (even-only by default) CSC*.ncs once
% - Converts to microvolts using ADBitVolts from header
% - Plots ±50 ms around each event midpoint
%
% Example:
%   VACC_TheVision("D:\PTEN\PTEN\M13_pten\HF4s\IED DATA");

% ---------------- Args ----------------
p = inputParser;
p.addRequired('dataDir', @(s)ischar(s)||isstring(s));
p.addParameter('halfWidthMs', 50, @(x)isfinite(x)&&x>0);        % ±50 ms
p.addParameter('minCh', 6, @(x)isfinite(x)&&x>=0);
p.addParameter('maxCh', 8, @(x)isfinite(x)&&x>=0);
p.addParameter('evenOnly', true, @(x)islogical(x));
p.addParameter('invertPolarity', true, @(x)islogical(x));       % keep your invert default
p.parse(dataDir, varargin{:});

dataDir        = string(p.Results.dataDir);
halfWidthMs    = p.Results.halfWidthMs;
minCh          = p.Results.minCh;
maxCh          = p.Results.maxCh;
evenOnly       = p.Results.evenOnly;
invertPolarity = p.Results.invertPolarity;

fprintf('\n=== VACC_TheVision ===\n');

% ---------------- Load ets / ech ----------------
load(fullfile(dataDir,'ets.mat'),'ets');
load(fullfile(dataDir,'ech.mat'),'ech');
nEvents = size(ets,1);
fprintf('Loaded %d events × %d channels from ets/ech\n', nEvents, size(ech,2));

% ---------------- Find CSC files ----------------
files = dir(fullfile(dataDir,'CSC*.ncs'));
if isempty(files), error('No CSC*.ncs files in %s', dataDir); end

nums = cellfun(@(n) sscanf(n,'CSC%d.ncs'), {files.name});
keep = ~isnan(nums);
if evenOnly, keep = keep & mod(nums,2)==0; end
files = files(keep); nums = nums(keep);
[nums, ord] = sort(nums); files = files(ord);
nCh = numel(files);
fprintf('Using %d %s-numbered channels\n', nCh, tern(evenOnly,'even','all'));

% ---------------- Load channels (ALL FIELDS + HEADER) ----------------
% Use the universal-safe 6-output signature:
% [Timestamps, ChanNum, SampFreq, NumValid, Samples, Header] = Nlx2MatCSC(..., [1 1 1 1 1], ExtractHeader=1, ExtractAll=1, [])
fprintf('Loading CSC data and headers...\n');

% Pre-scan first valid file to get ADBitVolts & sampling rate
refADBV = NaN; refFS = NaN;

S = cell(1,nCh);                          % samples per channel (µV, single)
maxLen = 0;

for i = 1:nCh
    fn = fullfile(dataDir, files(i).name);
    try
        [~,~,sampFreq,~,samples,header] = Nlx2MatCSC(fn,[1 1 1 1 1], 1, 1, []);
        % samples: [512 x Nrec] → flatten
        s = reshape(samples,1,[]);
        % header: cellstr → get ADBitVolts (per file)
        ADBitVolts = parse_adbitvolts(header);
        if isnan(ADBitVolts)
            error('ADBitVolts not found in header.');
        end
        if isnan(refADBV), refADBV = ADBitVolts; end
        % sampling frequency (prefer header if present, else median(sampFreq))
        fs_hdr = parse_samplingfreq(header);
        if isnan(refFS)
            if ~isnan(fs_hdr)
                refFS = fs_hdr;
            else
                refFS = median(double(sampFreq(:)));
            end
        end
        % convert to µV
        s = single(s) * single(ADBitVolts * 1e6);
        if invertPolarity, s = -s; end
        S{i} = s;
        if numel(s) > maxLen, maxLen = numel(s); end
    catch ME
        fprintf('  !! %s load failed: %s\n', files(i).name, ME.message);
        S{i} = []; % keep going
    end
end

if isnan(refFS)
    % last resort: assume 30 kHz if nothing available
    refFS = 30000;
end

fprintf('Sampling rate used: %.0f Hz | ADBitVolts example: %.9g (µV scale applied)\n', refFS, refADBV);
fprintf('Longest channel length: %.2f sec\n', maxLen/refFS);

% Rectangular matrix [nCh x maxLen]
D = zeros(nCh, maxLen, 'single');
for i = 1:nCh
    v = S{i}; if isempty(v), continue; end
    D(i,1:numel(v)) = v;
end
clear S

% ---------------- Event selection ----------------
chCount = sum(ech(:,1:nCh), 2);
evtIdx  = find(chCount>=minCh & chCount<=maxCh);
fprintf('Selected %d events (%d–%d channels)\n', numel(evtIdx), minCh, maxCh);
if isempty(evtIdx)
    fprintf('No events to plot.\n'); return;
end

% ---------------- Output dir ----------------
outDir = fullfile(dataDir,'VACC_TheVision_out');
if ~exist(outDir,'dir'), mkdir(outDir); end

% ---------------- Iterate events ----------------
HW   = round((halfWidthMs/1000) * refFS);   % half-window in samples
nS   = size(D,2);

for k = 1:numel(evtIdx)
    e = evtIdx(k);
    active = logical(ech(e,1:nCh));
    nActive = sum(active);

    % midpoint anchor
    anchor = round(mean(ets(e,:)));

    % clamp window to data bounds
    s0 = max(1, anchor - HW);
    s1 = min(nS, anchor + HW);
    if s1 <= s0
        fprintf('Evt %d skipped (window out of bounds)\n', e);
        continue;
    end

    Y = D(:, s0:s1);
    % local time axis aligned to anchor
    tRel = ((s0:s1) - anchor) / refFS * 1e3; % ms

    % y-limits (symmetric)
    maxAbs = max(abs(Y(:)));
    if ~isfinite(maxAbs) || maxAbs==0, maxAbs = 1; end
    yL = 1.05*maxAbs*[-1 1];

    % -------- Plot --------
    figH = min(150 + 90*nCh, 5000);
    f = figure('Color','w','Position',[80 80 900 figH],'Visible','off');
    tl = tiledlayout(f, nCh, 1, 'Padding','compact','TileSpacing','compact');

    for ch = 1:nCh
        nexttile(tl); hold on; box on; grid on;
        if active(ch), lw=1.4; col=[0 0 0]; else, lw=0.6; col=[0.6 0.6 0.6]; end
        plot(tRel, Y(ch,:), 'LineWidth', lw, 'Color', col);
        xline(0,'--k'); yline(0,':','Color',[0.7 0.7 0.7]);
        ylim(yL);
        title(sprintf('CSC%d%s', nums(ch), tern(active(ch),' *','')), 'FontSize', 8);
        if ch==nCh, xlabel('ms'); end
        ylabel('\muV');
    end

    sgtitle(tl, sprintf('Event %03d | %d ch | ±%.0f ms | yLim ±%.1f µV',...
        e, nActive, halfWidthMs, yL(2)), 'FontSize', 12, 'FontWeight', 'bold');

    outPng = fullfile(outDir, sprintf('Evt%03d_%dch.png', e, nActive));
    exportgraphics(f, outPng, 'Resolution', 220);
    close(f);
    fprintf('Saved %s\n', outPng);
end

fprintf('\nDone. Output in: %s\n', outDir);
end

% -------- helpers --------
function v = parse_adbitvolts(headerCell)
% header lines like: '-ADBitVolts 0.000000061037'
v = NaN;
for i=1:numel(headerCell)
    line = strtrim(headerCell{i});
    if contains(line, 'ADBitVolts','IgnoreCase',true)
        tok = regexp(line, 'ADBitVolts\s+([Ee0-9\.\+\-]+)', 'tokens', 'once');
        if ~isempty(tok)
            v = str2double(tok{1});
            return
        end
    end
end
end

function fs = parse_samplingfreq(headerCell)
% header lines like: '-SamplingFrequency 30000'
fs = NaN;
for i=1:numel(headerCell)
    line = strtrim(headerCell{i});
    if contains(line, 'SamplingFrequency','IgnoreCase',true)
        tok = regexp(line, 'SamplingFrequency\s+([0-9\.\+\-Ee]+)', 'tokens', 'once');
        if ~isempty(tok)
            fs = str2double(tok{1});
            return
        end
    end
end
end

function s = tern(c,a,b), if c, s=a; else, s=b; end, end
