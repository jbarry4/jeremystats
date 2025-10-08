function vacc_ied_detect_chunked()
  % Chunked LLspikedetector runner with verbose progress prints.
  % Saves ets.mat / ech.mat in the same folder as this script.

  tic;
  scriptDir = fileparts(mfilename('fullpath'));
  fprintf('\n[vacc_ied_detect_chunked] Script dir: %s\n', scriptDir);

  % --- deps/paths ---
  addpath(scriptDir);
  addpath("C:\Users\Z390\Desktop\jeremystats\IED\reqsPath");
  fprintf('[setup] Added deps.\n');

  % --- data discovery (even-numbered CSC*.ncs) ---
  dataRoot = "D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26";
  files = dir(fullfile(dataRoot, 'CSC*.ncs'));
  if isempty(files), error('No .ncs files found in: %s', dataRoot); end
  nums  = cellfun(@(s) sscanf(s,'CSC%d.ncs'), {files.name});
  keep  = mod(nums,2)==0 & ~isnan(nums);
  files = files(keep);
  if isempty(files), error('No even-numbered CSC files in: %s', dataRoot); end
  fprintf('[discovery] Found %d even-numbered channels.\n', numel(files));

  % --- params ---
  sfx = 30000;     % Hz
  llw = 0.04;      % seconds (40ms)
  prc = 99.9;      % percentile threshold
  CHUNK_S   = 60;                 % interior duration (seconds)
  ovlSamp   = ceil(llw * sfx);    % overlap in samples (LL window)
  chunkSamp = CHUNK_S * sfx;      % interior length in samples
  fprintf('[params] sfx=%d Hz | llw=%.3fs | prc=%.3f | chunk=%ds | overlap=%d samp\n', ...
          sfx, llw, prc, CHUNK_S, ovlSamp);

  % --- read channels into memory as row vectors (single) ---
  S = cell(1, numel(files));
  for k = 1:numel(files)
    fn = fullfile(files(k).folder, files(k).name);
    fprintf('[load] %2d/%d  %s ... ', k, numel(files), files(k).name);
    samples = Nlx2MatCSC(fn, [0 0 0 0 1], 0, 1, []);  % 512×N blocks
    v = reshape(samples,1,[]);
    S{k} = single(-v);  % invert polarity, keep single
    fprintf('OK (%d samples)\n', numel(v));
  end
  nPerCh = cellfun(@numel, S);
  T = min(nPerCh);                    % analyze common duration across channels
  nChan = numel(S);
  nChunks = ceil(T / chunkSamp);
  fprintf('[sizes] channels=%d | common length=%d samples (%.2f min)\n', ...
          nChan, T, T/sfx/60);
  fprintf('[plan] %d chunks of %d samples (~%ds) with %d-sample overlap.\n', ...
          nChunks, chunkSamp, CHUNK_S, ovlSamp);

  % --- chunked detection ---
  ets_all = zeros(0,2); 
  ech_all = false(0, nChan);

  startIdx = 1;
  chunkIdx = 0;
  while startIdx <= T
    chunkIdx = chunkIdx + 1;

    interiorStart = startIdx;
    interiorEnd   = min(startIdx + chunkSamp - 1, T);
    chunkStart    = max(1, interiorStart - ovlSamp);
    chunkEnd      = min(interiorEnd + ovlSamp, T);

    secsLo = (interiorStart-1)/sfx;
    secsHi = (interiorEnd-1)/sfx;
    fprintf('[chunk %3d/%d] samples [%d..%d] (interior %.2f–%.2f s) ... ', ...
            chunkIdx, nChunks, chunkStart, chunkEnd, secsLo, secsHi);

    % Assemble channels×time slice just for this chunk
    d_chunk = zeros(nChan, chunkEnd - chunkStart + 1, 'single');
    for ch = 1:nChan
      d_chunk(ch,:) = S{ch}(chunkStart:chunkEnd);
    end

    % Detect in this chunk
    [etsC, echC] = LLspikedetector(d_chunk, sfx, llw, prc);

    % Keep only events whose ONSET lies inside the interior (avoid dups)
    kept = 0;
    if ~isempty(etsC)
      intLo = interiorStart - chunkStart + 1;
      intHi = interiorEnd   - chunkStart + 1;
      keep = etsC(:,1) >= intLo & etsC(:,1) <= intHi;

      etsC = etsC(keep,:);
      echC = echC(keep,:);
      kept = size(etsC,1);

      % Shift to global indices and append
      if kept > 0
        etsC = etsC + (chunkStart - 1);
        ets_all = [ets_all; etsC];   %#ok<AGROW>
        ech_all = [ech_all; echC];   %#ok<AGROW>
      end
    end
    fprintf('events kept: %d | total so far: %d\n', kept, size(ets_all,1));

    % Next interior
    startIdx = interiorEnd + 1;
  end

  % --- done; save next to the script ---
  ets = ets_all; %#ok<NASGU>
  ech = ech_all; %#ok<NASGU>
  save(fullfile(scriptDir,'ets.mat'),'ets');
  save(fullfile(scriptDir,'ech.mat'),'ech');

  fprintf('[save] ets.mat & ech.mat written to: %s\n', scriptDir);
  fprintf('[done] Total events: %d | elapsed: %.1f s\n\n', size(ets_all,1), toc);
end
