function vacc_ied_detect_per_channel2()
% Chunked minute-by-minute detection using per-channel global LL thresholds.
% Saves ets.mat / ech.mat next to this script.

scriptDir = fileparts(mfilename('fullpath'));
addpath(scriptDir);
addpath("C:\Users\Z390\Desktop\jeremystats\IED\reqsPath");  % Nlx2MatCSC.* path

% ---- data discovery (even-numbered CSC, numeric sort) ----
dataRoot = "D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26";
files = dir(fullfile(dataRoot,'CSC*.ncs'));
if isempty(files), error('No .ncs in %s', dataRoot); end
nums = cellfun(@(s) sscanf(s,'CSC%d.ncs'), {files.name});
keep = mod(nums,2)==0 & ~isnan(nums);
files = files(keep); nums = nums(keep);
[nums,ord] = sort(nums,'ascend'); files = files(ord);

% ---- parameters ----
sfx       = 30000;         % Hz
llw       = 0.04;          % sec
prcPct    = 99.9;          % percentile for per-channel thresholds
CHUNK_S   = 60;            % interior seconds per chunk
mergeSamp = round(0.3*sfx);
ovlSamp   = ceil(llw*sfx) + mergeSamp;   % overlap covers LL window + merge horizon
chunkSamp = CHUNK_S * sfx;

% ---- load channels (single rows, inverted polarity) ----
nChan = numel(files);
S = cell(1,nChan);
for k=1:nChan
  fn = fullfile(files(k).folder, files(k).name);
  samples = Nlx2MatCSC(fn, [0 0 0 0 1], 0, 1, []);   % 512 x N blocks
  v = reshape(samples,1,[]);
  S{k} = single(-v);
end
T = min(cellfun(@numel,S));          % common duration across channels

% ---- PASS 0: compute per-channel global LL thresholds (thinned) ----
CAP_PER_CH         = 200000;         % max LL samples kept per channel
TARGET_PER_CHUNK   = 20000;          % ~per chunk, after thinning
LLbuf = nan(nChan, CAP_PER_CH, 'single');
cnt   = zeros(nChan,1,'uint32');

startIdx = 1;
while startIdx <= T && any(cnt < CAP_PER_CH)
  interiorStart = startIdx;
  interiorEnd   = min(startIdx + chunkSamp - 1, T);
  chunkStart    = max(1, interiorStart - ovlSamp);
  chunkEnd      = min(interiorEnd + ovlSamp, T);

  % assemble chunk: channels x time
  d = zeros(nChan, chunkEnd - chunkStart + 1, 'single');
  for ch=1:nChan, d(ch,:) = S{ch}(chunkStart:chunkEnd); end

  % quick LL (same as detector step 1)
  numsamples = round(llw*sfx);
  L = nan(size(d),'single');
  for i=1:size(d,2)-numsamples
    L(:,i) = sum(abs(diff(d(:,i:i+numsamples-1),1,2)),2);
  end

  % thin per channel and append into capped buffers
  for ch=1:nChan
    row = L(ch,:); row(isnan(row)) = [];
    if isempty(row) || cnt(ch) >= CAP_PER_CH, continue; end
    step = max(1, floor(numel(row)/TARGET_PER_CHUNK));
    pick = row(1:step:end);
    take = min(numel(pick), CAP_PER_CH - cnt(ch));
    if take>0
      LLbuf(ch, cnt(ch)+1:cnt(ch)+take) = pick(1:take);
      cnt(ch) = cnt(ch) + take;
    end
  end

  startIdx = interiorEnd + 1;  % next minute
end

thr_ch = zeros(nChan,1,'single');
for ch=1:nChan
  vals = LLbuf(ch,1:cnt(ch));
  vals = vals(~isnan(vals));
  if isempty(vals), error('LL sample buffer empty for channel %d', ch); end
  thr_ch(ch) = prctile(vals, prcPct);
end
% FIXED per-channel thresholds for all chunks:
fixed_thr = single(thr_ch);    % vector nChan x 1

% ---- PASS 1: chunked detection using fixed per-channel thresholds ----
ets_all = zeros(0,2,'uint64');
ech_all = false(0,nChan);

startIdx = 1;
while startIdx <= T
  interiorStart = startIdx;
  interiorEnd   = min(startIdx + chunkSamp - 1, T);
  chunkStart    = max(1, interiorStart - ovlSamp);
  chunkEnd      = min(interiorEnd + ovlSamp, T);

  d = zeros(nChan, chunkEnd - chunkStart + 1, 'single');
  for ch=1:nChan, d(ch,:) = S{ch}(chunkStart:chunkEnd); end

  % Call per-channel aware detector with fixed thresholds (vector)
  [etsC, echC] = LLspikedetector2(d, sfx, llw, fixed_thr);

  % keep only events whose ONSET lies in the interior
  if ~isempty(etsC)
    intLo = interiorStart - chunkStart + 1;
    intHi = interiorEnd   - chunkStart + 1;
    keep = etsC(:,1) >= intLo & etsC(:,1) <= intHi;

    etsC = etsC(keep,:);
    echC = echC(keep,:);
    if ~isempty(etsC)
      etsC = uint64(etsC) + uint64(chunkStart - 1);   % to global samples
      ets_all = [ets_all; etsC];                       %#ok<AGROW>
      ech_all = [ech_all; echC];                       %#ok<AGROW>
    end
  end

  startIdx = interiorEnd + 1;   % hop by 60 s
end

% ---- final global merge (<300 ms), then save ----
[ets, ech] = local_merge_close(ets_all, ech_all, sfx);

save(fullfile(scriptDir,'ets.mat'), 'ets');
save(fullfile(scriptDir,'ech.mat'), 'ech');

end  % function end


% ---- helpers ----
function [etsM, echM] = local_merge_close(ets, ech, sfx)
if isempty(ets), etsM=ets; echM=ech; return; end
[~,ord] = sort(ets(:,1),'ascend'); ets = ets(ord,:); ech = ech(ord,:);
s = size(ets,1); kill=false(s,1);
gap = round(0.3*sfx);
for i=1:s-1
  if (ets(i+1,1)-ets(i,2)) < gap
    ets(i+1,1) = ets(i,1);
    ech(i+1,:) = logical(ech(i+1,:) | ech(i,:));
    kill(i)=true;
  end
end
etsM = ets(~kill,:); echM = ech(~kill,:);
end
