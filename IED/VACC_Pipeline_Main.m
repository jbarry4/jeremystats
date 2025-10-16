function VACC_Pipeline_Main(dataDir, varargin)
% VACC_Pipeline_Main — minimal runner that works with ONLY EventStacks set up.
% INPUT: dataDir containing CSC*.ncs, ets.mat, ech.mat, and VACC_TheVision_out/{Solid,Sputter}
%
% It:
%   - converts Neuralynx once (even-only by default, flips polarity, µV)
%   - runs VACC_EventStacks_ampWidth_Avg(dataDir, V)
%   - builds a minimal SPUTTER "triptych" by copying the center PNG
%   - writes Master_Stats.csv from EventStacks stats only (if available)

% ---------- Options ----------
p = inputParser;
p.addRequired('dataDir', @(s)ischar(s)||isstring(s));
p.addParameter('evenOnly', true, @(x)islogical(x));
p.addParameter('invertPolarity', true, @(x)islogical(x));
p.parse(dataDir, varargin{:});
dataDir        = string(p.Results.dataDir);
evenOnly       = p.Results.evenOnly;
invertPolarity = p.Results.invertPolarity;

fprintf('\n=== VACC_Pipeline_Main (minimal) ===\n');

% ---------- Output hub ----------
masterOutDir    = fullfile(dataDir, 'Pipeline Output');
if ~exist(masterOutDir, 'dir'), mkdir(masterOutDir); end
triptychSPUTTER = fullfile(masterOutDir, 'Master_Compact_SPUTTER.png');
masterCSV       = fullfile(masterOutDir, 'Master_Stats.csv');

% ---------- Load converted data once ----------
V = VACC_loadNeuralynxData(dataDir, 'evenOnly', evenOnly, 'invertPolarity', invertPolarity);
% V.D (µV, single) | V.fs (Hz) | V.nums (CSC labels)

% ---------- EventStacks (CENTER) ----------
evtStacksRes = struct('pngSolid',"",'pngSputter',"",'statsCSV',"");
try
    evtStacksRes = VACC_EventStacks_ampWidth_Avg(dataDir, V);
catch ME
    wid = ME.identifier; if isempty(wid), wid = 'VACC:EventStacksFailed'; end
    warning(wid, 'EventStacks failed: %s', ME.message);
end

% ---------- Minimal SPUTTER "triptych" ----------
% If center PNG exists, just copy it to Master_Compact_SPUTTER.png
try
    centerPng = getFileIfExists(getFieldSafe(evtStacksRes,'pngSputter'));
    if ~isempty(centerPng)
        safeCopy(centerPng, triptychSPUTTER);
        fprintf('Master SPUTTER compact montage saved (center-only): %s\n', triptychSPUTTER);
    else
        warning('VACC:NoSputterCenter', 'No SPUTTER center PNG found; montage not created.');
    end
catch ME
    wid = ME.identifier; if isempty(wid), wid = 'VACC:SputterMontageFailed'; end
    warning(wid, 'Failed to build SPUTTER montage: %s', ME.message);
end

% ---------- Master stats CSV (EventStacks only) ----------
try
    T = table();
    evtCSV = getFieldSafe(evtStacksRes, 'statsCSV');
    if strlength(evtCSV) > 0 && isfile(evtCSV)
        C = readtable(evtCSV);
        if ~ismember('source', C.Properties.VariableNames)
            C.source = repmat("EventStacks", height(C), 1);
        else
            C.source = string(C.source);
        end
        T = C;
    end

    if isempty(T)
        T = table(string(datetime('now')), "EMPTY", 'VariableNames', {'GeneratedAt','Note'});
    end
    writetable(T, masterCSV);
    fprintf('Master stats CSV: %s\n', masterCSV);
catch ME
    wid = ME.identifier; if isempty(wid), wid = 'VACC:MasterCSVWriteFailed'; end
    warning(wid, 'Failed writing master stats CSV to %s: %s', masterCSV, ME.message);
end
end

% =================== tiny local helpers ===================

function v = getFieldSafe(S, fieldName)
    if ~(isstruct(S) && isfield(S, fieldName))
        v = "";
    else
        v = string(S.(fieldName));
    end
end

function p = getFileIfExists(s)
    p = "";
    if strlength(s) > 0
        c = char(s);
        if isfile(c), p = c; end
    end
end

function safeCopy(src, dst)
    % copyfile preserves the image exactly; if it fails, fallback to read/write
    ok = false;
    try
        [ok, msg] = copyfile(src, dst, 'f');
        if ~ok, error('copyfile failed: %s', msg); end
    catch
        I = imread(src);
        imwrite(I, dst);
    end
end
