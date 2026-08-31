function V = VACC_loadNeuralynxData(dataDir, varargin)
% VACC_loadNeuralynxData — read Neuralynx CSCs into µV (single).
% Returns struct V with:
%   V.D    : [nCh x nSamp] microvolts, single
%   V.fs   : sampling rate (Hz)
%   V.nums : CSC channel numbers (e.g., [2 4 6 ...])
%   V.ADBitVolts : volts per A/D count (from header)

p = inputParser;
p.addRequired('dataDir', @(s)ischar(s)||isstring(s));
p.addParameter('evenOnly', true, @(x)islogical(x));
p.addParameter('invertPolarity', true, @(x)islogical(x));
p.parse(dataDir, varargin{:});
dataDir        = string(p.Results.dataDir);
evenOnly       = p.Results.evenOnly;
invertPolarity = p.Results.invertPolarity;

% Find CSCs
files = dir(fullfile(dataDir, 'CSC*.ncs'));
if isempty(files), error('No CSC*.ncs in %s', dataDir); end
nums  = cellfun(@(n) sscanf(n,'CSC%d.ncs'), {files.name});
keep  = ~isnan(nums);
if evenOnly, keep = keep & mod(nums,2)==0; end
files = files(keep); nums = nums(keep);
[nums, order] = sort(nums); files = files(order);
nCh = numel(files);
fprintf('Loading %d %s-numbered channels from %s\n', nCh, tern(evenOnly,'even','all'), dataDir);

% Header ONCE (one output only)
hdr = Nlx2MatCSC(fullfile(files(1).folder, files(1).name), [0 0 0 0 0], 1, 1, []);
ADBitVolts = parse_adbitvolts(hdr);
fsHdr      = parse_samplingfreq(hdr);
if isnan(ADBitVolts), error('ADBitVolts not found in header.'); end
fs = fsHdr; if isnan(fs), fs = 30000; end
fprintf('Header: ADBitVolts=%.12g V/bit | fs=%.0f Hz\n', ADBitVolts, fs);

% Raw samples per channel (one output only)
raw = cell(1,nCh);
maxLen = 0;
for i = 1:nCh
    fn = fullfile(files(i).folder, files(i).name);
    try
        S = Nlx2MatCSC(fn, [0 0 0 0 1], 0, 1, []);
        s = reshape(S,1,[]);
        s = single(s);
        if invertPolarity, s = -s; end
        raw{i} = s;
        if numel(s) > maxLen, maxLen = numel(s); end
    catch ME
        fprintf('  !! %s failed: %s\n', files(i).name, ME.message);
        raw{i} = [];
    end
end

% Stack & convert to µV once
D = zeros(nCh, maxLen, 'single');
for i = 1:nCh
    v = raw{i}; if isempty(v), continue; end
    D(i,1:numel(v)) = v;
end
D = D .* single(ADBitVolts * 1e6); % µV

% Pack
V = struct('D', D, 'fs', fs, 'nums', nums, 'ADBitVolts', ADBitVolts, ...
           'evenOnly', evenOnly, 'invertPolarity', invertPolarity);
end

% ---- helpers ----
function v = parse_adbitvolts(hdr)
v = NaN;
for i=1:numel(hdr)
    line = strtrim(hdr{i});
    if contains(line,'ADBitVolts','IgnoreCase',true)
        tok = regexp(line,'ADBitVolts\s+([Ee0-9\.\+\-]+)','tokens','once');
        if ~isempty(tok), v = str2double(tok{1}); return; end
    end
end
end

function fs = parse_samplingfreq(hdr)
fs = NaN;
for i=1:numel(hdr)
    line = strtrim(hdr{i});
    if contains(line,'SamplingFrequency','IgnoreCase',true)
        tok = regexp(line,'SamplingFrequency\s+([0-9\.\+\-Ee]+)','tokens','once');
        if ~isempty(tok), fs = str2double(tok{1}); return; end
    end
end
end

function s = tern(c,a,b); if c, s=a; else, s=b; end; end
