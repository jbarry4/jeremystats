function vacc_ied_detect_chunked_thr(globalThr)
% Chunked LLspikedetector runner (fixed global threshold), verbose prints.
% Saves ets.mat / ech.mat next to this script.
%
% Usage:
%   vacc_ied_detect_chunked_thr(THRESHOLD)

  if nargin<1 || isempty(globalThr)
    error('Pass the numeric global threshold as globalThr.');
  end

  tic;
  scriptDir = fileparts(mfilename('fullpath'));
  fprintf('\n[vacc_ied_detect_chunked_thr] Script dir: %s\n', scriptDir);

  % --- deps/paths ---
  addpath(scriptDir);
  addpath("C:\Users\Z390\Desktop\jeremystats\IED\reqsPath");
  fprintf('[setup] Added deps. Using globalThr=%.6g\n', globalThr);

  % --- data discovery (even-numbered CSC*.ncs) ---
  dataRoot = "D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26";
  files = dir(fullfile(dataRoot, 'CSC*.ncs'));
  if isempty(files), error('No .ncs files found in: %s', dataRoot); end

  nums = cellfun(@(s) sscanf(s,'CSC%d.ncs'), {files.name});
  keep  = mod(nums,2)==0 & ~isnan(nums);
  files = files(keep); nums = nums(keep);
  [nums, order] = sort(nums, 'ascend');
  files = files(order);
  if isempty(files), error('No even-numbered CSC files in: %s', dataRoot); end
  fprintf('[discovery] %d even-numbered channels: %s\n', numel(nums), mat2str(nums));

  % --- params ---
  sfx   = 30000;     % Hz
  llw   = 0.04;      % sec
  CHUNK_S = 60;      % interior sec per chunk
  W        = max(2, round(llw*sfx));    % LL window (samples)
  mergeMs  = 0.300;                     % 300 ms event-merge margin
  mergeSmp = round(mergeMs * sfx);
  ovlSamp  = W + mergeSmp;              % <-- IMPORTANT: LL win + 300ms
  chunkSmp = CHUNK_S * sfx;

  fprintf('[params] sfx=%d | llw=%.3fs | W=%d | chunk=%ds | overlap=%d (W=%d + merge=%d)\n', ...
          sfx, llw, W, CHUNK_S, ovlSamp, W, mergeSmp);

  % --- read channels (single row vectors) ---
  S = cell(1, numel(files));
  for k = 1:numel(files)
    fn = fullfile(files(k).folder, files(k).name);
    fprintf('[load] %2d/%d  %s ... ', k, numel(files), files(k).name);
    samples = Nlx2MatCSC(fn, [0 0 0 0 1], 0, 1, []);  % 512×N
    v = reshape(samples,1,[]);
    S{k} = single(-v);  % invert, single
    fprintf('OK (%d samples)\n', numel(v));
  end

  nPerCh  = cellfun(@numel, S);
  T       = min(nPerCh);                 % common length
  nChan   = numel(S);
  nChunks = ceil(T / chunkSmp);
  fprintf('[sizes] channels=%d | common length=%d (%.2f min)\n', nChan, T, T/sfx/60);
  fprintf('[plan] %d chunks of %d samp (~%ds) with %d-samp overlap.\n', ...
          nChunks, chunkSmp, CHUNK_S, ovlSamp);

  % --- chunked detection ---
  ets_all = zeros(0,2);
  ech_all = false(0, nChan);

  startIdx = 1;
  chunkIdx = 0;
  while startIdx <= T
    chunkIdx = chunkIdx + 1;

    interiorStart = startIdx;
    interiorEnd   = min(startIdx + chunkSmp - 1, T);

    % extend chunk by LL + merge both sides (bounded by [1..T])
    chunkStart = max(1, interiorStart - ovlSamp);
    chunkEnd   = min(interiorEnd   + ovlSamp,   T);

    secsLo = (interiorStart-1)/sfx;
    secsHi = (interiorEnd-1)/sfx;
    fprintf('[chunk %3d/%d] [%d..%d] (interior %.2f–%.2f s) ... ', ...
            chunkIdx, nChunks, chunkStart, chunkEnd, secsLo, secsHi);

    % assemble channels×time slice for this chunk
    d_chunk = zeros(nChan, chunkEnd - chunkStart + 1, 'single');
    for ch = 1:nChan
      d_chunk(ch,:) = S{ch}(chunkStart:chunkEnd);
    end

    % detect in this chunk with FIXED THRESHOLD
    [etsC, echC] = LLspikedetector_fixedthr(d_chunk, sfx, llw, globalThr);

    % keep only events whose *centered onset* lies inside the interior
    kept = 0;
    if ~isempty(etsC)
      intLo = interiorStart - chunkStart + 1;   % interior bounds in chunk coords
      intHi = interiorEnd   - chunkStart + 1;

      keep = (etsC(:,1) >= intLo) & (etsC(:,1) <= intHi);
      etsC = etsC(keep,:);  echC = echC(keep,:);
      kept = size(etsC,1);

      if kept > 0
        etsC = etsC + (chunkStart - 1);  % shift to global indices
        ets_all = [ets_all; etsC];       %#ok<AGROW>
        ech_all = [ech_all; echC];       %#ok<AGROW>
      end
    end
    fprintf('kept=%d | total=%d\n', kept, size(ets_all,1));

    startIdx = interiorEnd + 1;  % next interior
  end

  % --- done; save next to the script ---
  ets = ets_all; %#ok<NASGU>
  ech = ech_all; %#ok<NASGU>
  save(fullfile(scriptDir,'ets.mat'),'ets');
  save(fullfile(scriptDir,'ech.mat'),'ech');

  fprintf('[save] ets.mat & ech.mat → %s\n', scriptDir);
  fprintf('[done] Total events: %d | elapsed: %.1f s\n\n', size(ets_all,1), toc);
end
