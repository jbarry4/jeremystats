
%% 1_1_ied_detect.m  Step 1 (v2): IED detection with 1-300 Hz band-pass + 60 Hz notch
%
% Variant of 1_ied_detect.m. Same loading / time-alignment / detection, but the
% filtering stage is a band-pass (1 Hz high-pass + 300 Hz low-pass) followed by a
% 60 Hz US-mains notch (and its in-band harmonics) instead of a high-pass only.
%
% Called via run() from a .sbat (cannot use a '.' in the filename -> underscore).
% Required workspace variables (set by sbat before run):
%   basePath      - raw data folder (e.g. .../KCNT1_DATA/Kcnt1_M10s2)
%   fiftyNineBad  - logical true/false  (true = drop CSC59)
%
% Outputs saved to basePath:
%   ets_hp_1_lp_300_nf.mat
%   ech_hp_1_lp_300_nf.mat
%   detector_meta.mat   <- required as input by 2_visualize.m

if ~exist('fiftyNineBad','var') || isempty(fiftyNineBad)
    fiftyNineBad = false;
end

fprintf('\n[STEP 1v2] %s  fiftyNineBad=%d\n', basePath, fiftyNineBad);
if ~isfolder(basePath), error('[ERROR] Folder not found: %s', basePath); end

%% ---- Step into data subfolder ----
subDirs = dir(basePath);
subDirs = subDirs([subDirs.isdir] & ~ismember({subDirs.name},{'.','..'}));
if isempty(subDirs), error('[ERROR] No subfolders in: %s', basePath); end
targetPath = fullfile(basePath, subDirs(1).name);
fprintf('[INFO] Data subfolder: %s\n', targetPath);

%% ---- Locate CSC files ----
dirStruct   = dir(fullfile(targetPath,'CSC*.*'));
allNcsNames = {dirStruct.name};

foundChannels = [];
foundPaths    = strings(0);
for c = 1:64
    fp = findCscFile(c, allNcsNames, targetPath);
    if ~isempty(fp)
        foundChannels(end+1) = c;
        foundPaths(end+1)    = string(fp);
    end
end
if isempty(foundChannels), error('[ERROR] No CSC files in: %s', targetPath); end

keep = true(size(foundChannels));
if fiftyNineBad
    keep = keep & (foundChannels ~= 59);
    fprintf('[INFO] CSC59 excluded.\n');
end
foundChannels = foundChannels(keep);
foundPaths    = foundPaths(keep);
nCh = numel(foundChannels);
fprintf('[INFO] Using %d channels.\n', nCh);

%% ---- Pass 1: metadata scan ----
fprintf('[INFO] Pass 1: scanning %d files...\n', nCh);
S_meta         = cell(1, nCh);
all_first_T_us = nan(1, nCh);
all_last_T_us  = nan(1, nCh);
all_Fs         = nan(1, nCh);

for k = 1:nCh
    fn = char(foundPaths(k));
    [~,nm,ex] = fileparts(fn);
    fprintf('  %s%s\n', nm, ex);
    [ts_us, ~, Fs_vec, nValid, samplesAD] = Nlx2MatCSC(fn,[1 1 1 1 1],0,1,[]);
    S_meta{k}.ts_us     = ts_us;
    S_meta{k}.nValid    = nValid;
    S_meta{k}.samplesAD = samplesAD;
    Fs = mode(double(Fs_vec(Fs_vec>0)));
    if ~(isfinite(Fs)&&Fs>0), Fs=30000; fprintf('[WARN] Fs fallback for %s%s\n',nm,ex); end
    all_Fs(k) = Fs;
    if ~isempty(ts_us)
        all_first_T_us(k) = ts_us(1);
        all_last_T_us(k)  = double(ts_us(end)) + (double(nValid(end))-1)/(Fs/1e6);
    end
end
fprintf('[INFO] Pass 1 done.\n');

%% ---- Build global time grid ----
good = isfinite(all_Fs);
sfx  = mode(round(all_Fs(good)));
fprintf('[INFO] Sampling rate: %g Hz\n', sfx);
global_min_T_us = min(all_first_T_us(good));
global_max_T_us = max(all_last_T_us(good));
spu             = sfx / 1e6;
maxSamples      = round((global_max_T_us - global_min_T_us) * spu) + 1;
fprintf('[INFO] Duration: %.2f s  allocating [%d x %d]...\n', ...
    (global_max_T_us-global_min_T_us)/1e6, nCh, maxSamples);
d = single(NaN(nCh, maxSamples));

%% ---- Pass 2: time-align onto global grid ----
fprintf('[INFO] Pass 2: time-aligning...\n');
for k = 1:nCh
    meta = S_meta{k};
    if isempty(meta.ts_us), continue; end
    recLen = size(meta.samplesAD,1);
    nRec   = size(meta.samplesAD,2);
    for r = 1:nRec
        vCount = min(recLen, max(0, meta.nValid(r)));
        if vCount==0, continue; end
        raw = single(-double(meta.samplesAD(1:vCount,r)));
        iS  = round((double(meta.ts_us(r)) - global_min_T_us)*spu) + 1;
        iE  = iS + vCount - 1;
        wS = max(1,iS);  wE = min(maxSamples,iE);
        dS = max(1,1-(iS-1));  dE = vCount-(iE-wE);
        if wS>wE || dS>dE, continue; end
        d(k,wS:wE) = raw(dS:dE);
    end
end
clear S_meta;
fprintf('[INFO] Pass 2 done.\n');

%% ---- Band-pass (1-300 Hz) + 60 Hz US-mains notch ----
% HP 1 Hz and LP 300 Hz are built as SOS (zp2sos) and applied zero-phase with
% filtfilt: numerically stable, no phase distortion. Direct-form butter at the
% extreme low cutoff (1/15000 at 30 kHz) is degenerate and rings, hence SOS.
% A 60 Hz notch (US line frequency) plus its harmonics that fall below the
% low-pass cutoff are removed with iirnotch.
hp_cut   = 1.0;     % high-pass cutoff (Hz)
lp_cut   = 300.0;   % low-pass cutoff  (Hz)
notch_f0 = 60.0;    % US mains fundamental (Hz)
notch_Q  = 35;      % notch quality factor (higher = narrower)

[z_hp,p_hp,k_hp] = butter(4, hp_cut/(sfx/2), 'high');
[sos_hp, g_hp]   = zp2sos(z_hp, p_hp, k_hp);
[z_lp,p_lp,k_lp] = butter(4, lp_cut/(sfx/2), 'low');
[sos_lp, g_lp]   = zp2sos(z_lp, p_lp, k_lp);

% Precompute 60 Hz notch + in-band harmonics (60, 120, 180, ... < lp_cut)
notchFreqs = notch_f0 : notch_f0 : min(lp_cut, sfx/2 - 1);
notchB = cell(1, numel(notchFreqs));
notchA = cell(1, numel(notchFreqs));
for n = 1:numel(notchFreqs)
    w0 = notchFreqs(n)/(sfx/2);
    [notchB{n}, notchA{n}] = iirnotch(w0, w0/notch_Q);
end

fprintf('[INFO] Filtering: HP %.1f Hz, LP %.1f Hz, notch %s Hz (Q=%g) on %d channels...\n', ...
    hp_cut, lp_cut, mat2str(notchFreqs), notch_Q, nCh);
d_filt = d; clear d;
for k = 1:nCh
    ch = double(d_filt(k,:));
    nm = isnan(ch);
    ch(nm) = 0;
    ch = filtfilt(sos_hp, g_hp, ch);          % 1 Hz high-pass
    ch = filtfilt(sos_lp, g_lp, ch);          % 300 Hz low-pass
    for n = 1:numel(notchB)                   % 60 Hz notch + harmonics
        ch = filtfilt(notchB{n}, notchA{n}, ch);
    end
    ch(nm) = NaN;
    d_filt(k,:) = single(ch);
end
fprintf('[INFO] Filtering done.\n');

%% ---- IED detection ----
llw = 0.075;   % 75 ms window matched to LFP IED morphology
prc = 99.9;
fprintf('[INFO] LLspikedetector: llw=%.3f s  prc=%.1f%%\n', llw, prc);
[ets, ech] = LLspikedetector(d_filt, sfx, llw, prc);
fprintf('[INFO] Detected %d events.\n', size(ets,1));

%% ---- Save outputs ----
detector_meta.global_min_T_us = global_min_T_us;
detector_meta.sfx              = sfx;
save(fullfile(basePath,'ets_hp_1_lp_300_nf.mat'), 'ets');
save(fullfile(basePath,'ech_hp_1_lp_300_nf.mat'), 'ech');
save(fullfile(basePath,'detector_meta.mat'), 'detector_meta');
fprintf('[STEP 1v2] Done. Saved to: %s\n', basePath);
