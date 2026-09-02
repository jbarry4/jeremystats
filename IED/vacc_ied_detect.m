% vacc_ied_detect.m — minimal, folder-based IED batch detector (single-precision)
% Runs on 'basePath' and writes ets.mat / ech.mat back there.
%
% INPUTS:
%   basePath: (string) Full path to the directory containing CSC*.ncs files.
%   eightBad: (logical) If true, replace CSC8.ncs with CSC9.ncs in the analysis.

function vacc_ied_detect(basePath, eightBad)
  % basePath is now the data directory
  dataDir = basePath; 

  % Setup paths relative to this script's location
  baseScriptDir = fileparts(mfilename('fullpath'));
  
  % Add required deps (LLspikedetector.m, Nlx2MatCSC.m/.mexa64)
  addpath(baseScriptDir);
  % This path was hardcoded in your original file. You may need to update it.
  addpath(fullfile("C:\\Users\\Z390\\Desktop\\jeremystats\\IED\\reqsPath"));  % contains Nlx2MatCSC.* per repo layout
  fprintf('[INFO] Added script directory to path: %s\n', baseScriptDir);

  % Find all CSC files in the specified basePath
  files = dir(fullfile(dataDir, 'CSC*.ncs'));
  if isempty(files)
    error('No .ncs files found in: %s', dataDir);
  end

  % --- Channel selection logic ---
  names = {files.name};
  nums  = cellfun(@(s) sscanf(s,'CSC%d.ncs'), names);
  
  % Create masks for file numbers
  isValidNum = ~isnan(nums);
  isEven = mod(nums, 2) == 0;
  isCSC8 = (nums == 8);
  isCSC9 = (nums == 9);

  % Default: keep even-numbered CSC files
  keep_mask = isEven & isValidNum;
  
  nTotalCh = numel(files);
  
  fprintf('[INFO] Total .ncs files found: %d\n', nTotalCh);

  % Handle the eightBad flag
  if eightBad
    fprintf('[INFO] eightBad flag is TRUE.\n');
    isChannel8Kept = any(keep_mask & isCSC8);
    fprintf('[INFO] isChannel8Kept (based on even filter): %d\n', isChannel8Kept);
    
    if isChannel8Kept
      fprintf('[INFO] Replacing CSC8.ncs with CSC9.ncs.\n');
      % Remove CSC8 from the mask
      keep_mask = keep_mask & ~isCSC8;
      
      % Check if CSC9 exists
      if any(isCSC9 & isValidNum)
        % Add CSC9 to the mask
        keep_mask = keep_mask | (isCSC9 & isValidNum);
      else
        fprintf('[WARN] eightBad is true and CSC8 was kept, but CSC9.ncs does not exist in the folder. CSC8 will be excluded and not replaced.\n');
      end
    end
  else
     fprintf('[INFO] eightBad flag is FALSE. Standard even channel selection.\n');
  end

  % Apply the final mask
  files_to_process = files(keep_mask);
  
  kept_channels_info = nums(keep_mask);
  numberOfKeptChannels = numel(files_to_process);

  if numberOfKeptChannels == 0
    error('[ERROR] No channels selected to keep after filtering. Check data and flags.'); 
  end
  
  fprintf('[INFO] Channels to include: %d\n', numberOfKeptChannels);
  fprintf('[INFO] Kept channels (file numbers): %s\n', mat2str(kept_channels_info(1:min(10,numberOfKeptChannels))));
  % --- End channel selection ---


  % Read all samples (ExtractMode 1, Samples only), invert polarity, collect as single
  S = cell(1, numel(files_to_process));
  fprintf('[INFO] Loading %d files...\n', numel(files_to_process));
  for k = 1:numel(files_to_process)
    fn = fullfile(files_to_process(k).folder, files_to_process(k).name);
    fprintf('       Loading %s\n', files_to_process(k).name);
    % Samples only: FieldSelectionFlags=[0 0 0 0 1], no header, Extract All (mode 1), vec []
    samples = Nlx2MatCSC(fn, [0 0 0 0 1], 0, 1, []);
    s = reshape(samples, 1, []);        % 512-by-N → row
    s = single(-s);                     % invert default Neuralynx polarity, keep single (no doubles)
    S{k} = s; 
  end
  fprintf('[INFO] File loading complete.\n');

  % Pad to rectangle
  maxlen = max(cellfun(@numel, S));
  d = zeros(numel(S), maxlen, 'single');
  for i = 1:numel(S)
    v = S{i};
    d(i, 1:numel(v)) = v;
  end

  % Fixed params per request
  sfx = 30000;         % Hz
  llw = 0.04;          % 40 ms window
  prc = 99.9;          % percentile threshold

  fprintf('[INFO] Detecting spikes with sfx=%.1f, llw=%.3f, prc=D%.1f...\n', sfx, llw, prc);
  % Detect spikes (rows of ets are [on off] in samples; ech marks channels per event)
  [ets, ech] = LLspikedetector(d, sfx, llw, prc);
  fprintf('[INFO] Spike detection complete. Found %d events.\n', size(ets, 1));

  % Save outputs right next to data (in basePath)
  output_ets_file = fullfile(dataDir, 'ets.mat');
  output_ech_file = fullfile(dataDir, 'ech.mat');
  
  fprintf('[INFO] Saving outputs to: %s\n', dataDir);
  save(output_ets_file, 'ets');
  save(output_ech_file, 'ech');
  fprintf('[INFO] Save complete.\n');
end