function VACC_TheVision(dataDir, varargin)
% VACC_TheVision — simple IED event viewer for Neuralynx .ncs
% - Loads ets.mat / ech.mat from dataDir
% - Reads header ONCE to get ADBitVolts & SamplingFrequency
% - Loads raw samples per channel (single-output call)
% - Converts to microvolts ONCE after stacking
% - Plots ±50 ms (default) around event midpoint
%
% Example:
%   VACC_TheVision("D:\PTEN\PTEN\M13_pten\HF4s\IED DATA");

%% -------- Args --------
p = inputParser;
p.addRequired('dataDir', @(s)ischar(s)||isstring(s));
p.addParameter('halfWidthMs', 50, @(x)isfinite(x)&&x>0);
p.addParameter('minCh', 6, @(x)isfinite(x)&&x>=0);
p.addParameter('maxCh', 8, @(x)isfinite(x)&&x>=0);
p.addParameter('evenOnly', true, @(x)islogical(x));
p.addParameter('invertPolarity', true, @(x)islogical(x));
p.parse(dataDir, varargin{:});
dataDir        = string(p.Results.dataDir);
halfWidthMs    = p.Results.halfWidthMs;
minCh          = p.Results.minCh;
maxCh          = p.Results.maxCh;
evenOnly       = p.Results.evenOnly;
invertPolarity = p.Results.invertPolarity;

fprintf('\n=== VACC_TheVision ===\n');

%% -------- Load ets / ech --------
load(fullfile(dataDir,'ets.mat'),'ets');
load(fullfile(dataDir,'ech.mat'),'ech');
fprintf('Loaded %d events × %d channels from ets/ech\n', size(ets,1), size(ech,2));

%% -------- Find CSC files --------
files = dir(fullfile(dataDir,'CSC*.ncs'));
if isempty(files), error('No CSC*.ncs files in: %s', dataDir); end
nums = cellfun(@(n) sscanf(n,'CSC%d.ncs'), {files.name});
keep = ~isnan(nums);
if evenOnly, keep = keep & mod(nums,2)==0; end
files = files(keep); nums = nums(keep);
[nums, ord] = sort(nums); files = files(ord);
nCh = numel(files);
fprintf('Using %d %s-numbered channels\n', nCh, tern(evenOnly,'even','all'));

%% -------- Read header ONCE (units & fs) --------
% Header only: FieldSelection=[0 0 0 0 0], ExtractHeader=1, ExtractAll=1
% Header only: request exactly ONE output
hdr = Nlx2MatCSC(fullfile(files(1).folder, files(1).name), [0 0 0 0 0], 1, 1, []);
ADBitVolts = parse_adbitvolts(hdr);              % volts / bit
fsHdr      = parse_samplingfreq(hdr);            % Hz (if present)
if isnan(ADBitVolts), error('ADBitVolts not found in header.'); end
fs = fsHdr; if isnan(fs), fs = 30000; end        % fallback
fprintf('Header: ADBitVolts=%.12g V/bit | fs=%.0f Hz\n', ADBitVolts, fs);


%% -------- Load raw samples per channel --------
fprintf('Loading raw samples...\n');
raw = cell(1,nCh);
maxLen = 0;
for i = 1:nCh
    fn = fullfile(files(i).folder, files(i).name);
    try
        % Samples only: FieldSelection=[0 0 0 0 1], ExtractHeader=0, ExtractAll=1
        S = Nlx2MatCSC(fn, [0 0 0 0 1], 0, 1, []);
        s = reshape(S,1,[]);                % [1 x N]
        s = single(s);                       % keep lean
        if invertPolarity, s = -s; end
        raw{i} = s;
        if numel(s) > maxLen, maxLen = numel(s); end
    catch ME
        fprintf('  !! %s failed: %s\n', files(i).name, ME.message);
        raw{i} = [];
    end
end
fprintf('Longest channel: %.2f sec\n', maxLen/fs);

% Stack to rectangular matrix in A/D counts
D = zeros(nCh, maxLen, 'single');
for i = 1:nCh
    v = raw{i}; if isempty(v), continue; end
    D(i,1:numel(v)) = v;
end
clear raw

% Convert ONCE to microvolts
D = D .* single(ADBitVolts * 1e6);        % µV

%% -------- Select events --------
chCount = sum(ech(:,1:nCh), 2);
evtIdx  = find(chCount>=minCh & chCount<=maxCh);
fprintf('Selected %d events (%d–%d channels)\n', numel(evtIdx), minCh, maxCh);
if isempty(evtIdx), fprintf('No events to plot.\n'); return; end

%% -------- Plot windows --------
HW = round((halfWidthMs/1000) * fs);      % samples
nS = size(D,2);
outDir = fullfile(dataDir,'VACC_TheVision_out');
if ~exist(outDir,'dir'), mkdir(outDir); end

for k = 1:numel(evtIdx)
    e = evtIdx(k);
    active = logical(ech(e,1:nCh));
    nActive = sum(active);

    anchor = round(mean(ets(e,:)));
    s0 = max(1, anchor - HW);
    s1 = min(nS, anchor + HW);
    if s1 <= s0
        fprintf('Evt %d skipped (window out of bounds)\n', e);
        continue;
    end

    Y = D(:, s0:s1);
    tRel = ((s0:s1) - anchor) / fs * 1e3; % ms (centered on 0)

    maxAbs = max(abs(Y(:))); if ~isfinite(maxAbs)||maxAbs==0, maxAbs=1; end
    yL = 1.05*maxAbs*[-1 1];

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

    exportgraphics(f, fullfile(outDir, sprintf('Evt%03d_%dch.png', e, nActive)), 'Resolution', 220);
    close(f);
    fprintf('Saved Evt %03d (%d ch)\n', e, nActive);
end

fprintf('\nDone. Output in: %s\n', outDir);
end

%% -------- helpers --------
function v = parse_adbitvolts(hdr)
v = NaN;
for i=1:numel(hdr)
    line = strtrim(hdr{i});
    if contains(line,'ADBitVolts','IgnoreCase',true)
        tok = regexp(line, 'ADBitVolts\s+([Ee0-9\.\+\-]+)', 'tokens','once');
        if ~isempty(tok), v = str2double(tok{1}); return; end
    end
end
end

function fs = parse_samplingfreq(hdr)
fs = NaN;
for i=1:numel(hdr)
    line = strtrim(hdr{i});
    if contains(line,'SamplingFrequency','IgnoreCase',true)
        tok = regexp(line, 'SamplingFrequency\s+([0-9\.\+\-Ee]+)', 'tokens','once');
        if ~isempty(tok), fs = str2double(tok{1}); return; end
    end
end
end

function s = tern(c,a,b); if c, s=a; else, s=b; end; end
