function vacc_compile_ech_ets()
% ----------------------------------------------------------
% VACC_COMPILE_ECH_ETS
% ----------------------------------------------------------
% Loads ech.mat and ets.mat from each given data folder.
% Creates a single combined .mat per folder and saves it into:
%   /gpfs2/scratch/sakhava1/Batch_Process_All/compiled_out/
%
% Each output .mat contains:
%   path    : full source folder path
%   ech     : channel participation data (if found)
%   ets     : event times data (if found)
%   missing : struct of logical flags
%   when    : timestamp of compilation
%
% Missing files or folders are still recorded with warnings.
% ----------------------------------------------------------

  % === USER: Edit this list if you add/remove sessions ===
 folders = {
    "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M1_Pten/M1ptens2oct2/2023-10-02_16-58-03"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M1_Pten/M1ptens8oct4/2023-10-05_14-09-57"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M10_HF6_pten/m10s4aug23/2023-08-23_17-14-35"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M10_HF6_pten/m10s7aug28/2023-08-28_14-17-49"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M11_Pten/HF2_s10jul25/2023-07-25_14-40-32"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M11_Pten/HF2_s11jul25/2023-07-25_16-10-46"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M13_pten/HF4s2aug1/2023-08-01_12-11-26"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M13_pten/HF4s17aug4/2023-08-04_13-43-48"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M13_pten/HF4s1aug1/2023-08-01_11-37-10"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/M2_CTL/M2ctls3jan23/2024-01-23_16-04-25"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/M2_CTL/M2s8jan26/2024-01-26_17-48-00"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/m21_ptenblind/m21s2jul29/2024-07-29_13-05-17"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/m21_ptenblind/m21s6jul29/2024-07-29_15-28-43"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/m22_ptenblind/m22s3jul15/2024-07-15_16-12-27"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/m22_ptenblind/m22s6jul15/2024-07-15_17-49-43"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/m23_ptenblind/m23s1aug6/2024-08-06_12-36-23"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/m23_ptenblind/m23s5aug7/2024-08-06_15-12-51"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/m24_ptenblind/m24s1jul16/2024-07-16_12-20-40"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/m24_ptenblind/m24s4jul16/2024-07-16_14-11-34"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/m26_ptenblind/m26s2jun28/2024-06-28_12-00-26"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/m26_ptenblind/m26s5jun28/2024-06-28_15-19-00"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/m28_ptenblind/m28s2jun18/2024-06-18_13-33-44"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/m28_ptenblind/m28s7jun18/2024-06-18_16-37-05"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/m29_ptenblind/m29s1jul23/2024-07-23_13-03-51"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/m29_ptenblind/m29s4jul23/2024-07-23_15-31-49"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M3_pten/m3s2sept20/2023-09-20_12-55-14"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M3_pten/m3s7sept22/2023-09-22_16-15-23"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/m30_ptenblind/m30s1jul1/2024-07-01_13-58-59"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/m30_ptenblind/m30s4jul1/2024-07-01_15-55-11"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/m33_ptenblind/m33s4jun14/2024-06-14_11-46-54"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/m33_ptenblind/m33s8jun14/2024-06-14_14-16-58"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M34_ptenblind/m34s5jun10/2024-06-10_14-45-34"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M34_ptenblind/m34s8jun10/2024-06-10_17-00-07"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENDKOM41/M41s1nov26/2024-11-26_11-55-25"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENDKOM41/M41s6nov26/2024-11-26_16-16-02"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PtenDKOM44/M44S1/2024-11-11_09-36-17"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PtenDKOM44/m44s5nov11/2024-11-11_16-17-54"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENDKOm46/m46s1jan15/2025-01-15_14-32-19"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENDKOm46/m46s7jan15/2025-01-15_17-51-31"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENDKOM47/m47s1dec04/2024-12-04_11-13-32"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENKDOM48/m48s2feb4/2025-02-04_12-48-12"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENKDOM48/m48s6cno90feb4/2025-02-04_15-27-16"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M5_Pten/M5s2bnov16/2023-11-16_15-05-01"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M5_Pten/M5s2cnov16/2023-11-16_15-24-07"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M5_Pten/M5s7nov17/2023-11-17_14-23-24"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/M51/m51s1apr8/2025-04-08_16-58-56"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENDKOM53/m53s1mar4/2025-03-04_13-02-15"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENDKOM53/m53s7mar4-2025/2025-03-04_17-03-31"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENDKOM53/m53s7mar4-2025/2025-03-06_13-17-00"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENDKOm55/m55s1jun11/2025-06-11_13-22-40"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENDKOm56/m56s2_061925/2025-06-19_13-34-29"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN_DKO/PTENDKOm56/m56s8_06192025/2025-06-19_16-39-58"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/PTENDKOM59/m59s4jul7/2025-07-07_12-52-42"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/PTENDKOM59/m59s11jul8/2025-07-09_12-19-54"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/PTENDKOM59/m59s10jul7/2025-07-07_16-42-40"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/M6_PtenMissCTL/M6s4sept13/2023-09-13_17-24-49"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/M6_PtenMissCTL/M6s8sept14/2023-09-14_18-04-54"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/PTENDKOM60/m60s1jul10/2025-07-10_11-41-45"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/PTENDKOM60/m60s4jul10/2025-07-10_13-51-27"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/PTENDKOM61/m61s1jul11/2025-07-11_12-16-56"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/CTL/PTENDKOM61/m61s7jul11/2025-07-11_15-53-22"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M7_HF5_pten/M7s2aug22/2023-08-22_15-46-13"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M7_HF5_pten/M7s6aug24/2023-08-24_13-49-57"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M8_Pten/M8s2feb6/2024-02-06_17-52-07"
  "/gpfs2/scratch/sakhava1/Batch_Process_All/myDATA/PTEN/M8_Pten/M8s9feb8/2024-02-09_16-43-46"
  };

  outRoot = '/gpfs2/scratch/sakhava1/Batch_Process_All/compiled_out';
  if ~isfolder(outRoot), mkdir(outRoot); end

  % -------- per-session compile --------
  for i = 1:numel(folders)
    folder = folders{i};
    fprintf('\n=== Processing: %s ===\n', folder);

    S.path = folder;
    S.when = datestr(now, 31);
    S.ech  = [];
    S.ets  = [];
    S.missing = struct('folder', false, 'ech', false, 'ets', false);

    if ~isfolder(folder)
      S.missing.folder = true;
      fprintf('[WARN] Folder missing, recording anyway.\n');
    else
      ef = fullfile(folder, 'ech.mat');
      if isfile(ef)
        t = load(ef);
        if isfield(t,'ech'), S.ech = t.ech; end
        fprintf('Loaded ech.mat\n');
      else
        S.missing.ech = true; fprintf('[WARN] Missing ech.mat\n');
      end

      tf = fullfile(folder, 'ets.mat');
      if isfile(tf)
        t = load(tf);
        if isfield(t,'ets'), S.ets = t.ets; end
        fprintf('Loaded ets.mat\n');
      else
        S.missing.ets = true; fprintf('[WARN] Missing ets.mat\n');
      end
    end

    safeName = sanitize_path(folder);                                % string
    outFile  = fullfile(outRoot, "compiled_" + safeName + ".mat");   % string
    save(char(outFile), '-struct', 'S');                             % save wants char or string
    fprintf('Saved: %s\n', outFile);
  end

  % -------- master compile (aggregate everything currently in compiled_out) --------
  files = dir(fullfile(outRoot, 'compiled_*.mat'));
  Sessions = repmat(struct('path',"",'when',"",'ech',[],'ets',[],'missing',struct('folder',false,'ech',false,'ets',false)), 0, 1);

  for k = 1:numel(files)
    F = fullfile(files(k).folder, files(k).name);
    T = load(F); % expects fields: path, when, ech, ets, missing
    S.path    = maybe_field(T, 'path', "");
    S.when    = maybe_field(T, 'when', "");
    S.ech     = maybe_field(T, 'ech',  []);
    S.ets     = maybe_field(T, 'ets',  []);
    S.missing = maybe_field(T, 'missing', struct('folder',false,'ech',false,'ets',false));
    Sessions(end+1,1) = S; %#ok<AGROW>
  end

  % lightweight summary (counts + flags)
  n = numel(Sessions);
  summary = struct('path', strings(n,1), 'when', strings(n,1), ...
                   'missing_folder', false(n,1), 'missing_ech', false(n,1), 'missing_ets', false(n,1), ...
                   'n_events', zeros(n,1), 'n_channels', zeros(n,1));
  for i = 1:n
    summary.path(i)           = string(Sessions(i).path);
    summary.when(i)           = string(Sessions(i).when);
    summary.missing_folder(i) = Sessions(i).missing.folder;
    summary.missing_ech(i)    = Sessions(i).missing.ech;
    summary.missing_ets(i)    = Sessions(i).missing.ets;
    summary.n_events(i)       = numel(Sessions(i).ets);
    summary.n_channels(i)     = size_or_zero(Sessions(i).ech, 1);
  end

  masterFile = fullfile(outRoot, "compiled_master.mat");
  save(char(masterFile), 'Sessions', 'summary');
  fprintf('\n=== Master saved: %s ===\n', masterFile);
end

% ---- helpers ----
function safe = sanitize_path(pathStr)
  p = string(pathStr);
  safe = replace(p, filesep, "__");
  safe = regexprep(safe, "\s+", "_");
  safe = regexprep(safe, "[:*?""<>|]", "_");
end

function v = maybe_field(S, f, default)
  if isfield(S, f), v = S.(f); else, v = default; end
end

function n = size_or_zero(x, dim)
  if isempty(x), n = 0; else, n = size(x, dim); end
end