function vacc_ied_detect_chunked3()
% Two-pass chunked runner that matches whole-file results:
% Pass A: exact global LL percentile via streaming order stats (no giant arrays)
% Pass B: chunked detection w/ fixed threshold, overlap (llw + 300ms), final merge.

tic;
scriptDir = fileparts(mfilename('fullpath'));
addpath(scriptDir);
addpath("C:\Users\Z390\Desktop\jeremystats\IED\reqsPath");  % Nlx2MatCSC path

% ---- data discovery (even-numbered CSC; numeric sort) ----
dataRoot = "D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26";
files = dir(fullfile(dataRoot,'CSC*.ncs'));
if isempty(files), error('No .ncs in %s', dataRoot); end
nums = cellfun(@(s) sscanf(s,'CSC%d.ncs'), {files.name});
keep = mod(nums,2)==0 & ~isnan(nums);
files = files(keep); nums = nums(keep);
[nums,ord] = sort(nums,'ascend'); files = files(ord);
if isempty(files), error('No even-numbered CSC files in %s', dataRoot); end

% ---- parameters ----
sfx       = 30000;      % Hz
llw       = 0.04;       % s
prcPct    = 99.9;       % percentile for global threshold
CHUNK_S   = 60;         % interior seconds per chunk
mergeSamp = round(0.3*sfx);
ovlSamp   = ceil(llw*sfx) + mergeSamp;   % cover LL and merge horizon
chunkSamp = CHUNK_S * sfx;
numsamples = round(llw*sfx);

% ---- load channels into row vectors (single, inverted polarity) ----
nChan = numel(files);
S = cell(1,nChan);
for k=1:nChan
  fn = fullfile(files(k).folder, files(k).name);
  blk = Nlx2MatCSC(fn,[0 0 0 0 1],0,1,[]); % 512xN blocks
  v = reshape(blk,1,[]);
  S{k} = single(-v);
end
T = min(cellfun(@numel,S));      % analyze common duration

% =========================
% PASS A: exact global threshold (prctile) without big arrays
% =========================
% We'll exactly match MATLAB's default prctile linear interpolation:
% k = (p/100)*(N-1) + 1; j=floor(k); g=k-j; threshold = v_j + g*(v_{j+1}-v_j)
% where v_j is the j-th order statistic of all LL values across channels/time.

% A1) sweep to get global min/max and total count N of LL values
[minLL, maxLL, N] = sweep_min_max_count(S, nChan, T, numsamples, chunkSamp, ovlSamp);

% A2) compute j, g as per MATLAB prctile
k  = (prcPct/100)*(N-1) + 1;
j  = floor(k);
g  = k - j;
if j < 1, j = 1; end
if j >= N, j = N-1; g = 1; end   % guard

% A3) find v_j (j-th order statistic) and v_{j+1} by count-based binary search
vj  = kth_order_value(j,  S, nChan, T, numsamples, chunkSamp, ovlSamp, minLL, maxLL);
vj1 = kth_order_value(j+1,S, nChan, T, numsamples, chunkSamp, ovlSamp, minLL, maxLL);

% A4) linear interpolation to match prctile exactly
global_thr = vj + g * (vj1 - vj);
fixed_prc  = {num2str(global_thr)};
fprintf('[threshold] exact global LL P%.3f = %.8g (N=%d)\n', prcPct, global_thr, N);

% =========================
% PASS B: chunked detection with fixed threshold
% =========================
ets_all = zeros(0,2,'uint64'); 
ech_all = false(0,nChan);

startIdx = 1;
while startIdx <= T
  interiorStart = startIdx;
  interiorEnd   = min(startIdx + chunkSamp - 1, T);
  chunkStart    = max(1, interiorStart - ovlSamp);
  chunkEnd      = min(interiorEnd + ovlSamp, T);

  % assemble chunk
  d = zeros(nChan, chunkEnd - chunkStart + 1, 'single');
  for ch=1:nChan, d(ch,:) = S{ch}(chunkStart:chunkEnd); end

  % detect with fixed global threshold (identical logic to whole-file)
  [etsC, echC] = LLspikedetector3(d, sfx, llw, fixed_prc);

  % keep only events whose ONSET is in the interior
  if ~isempty(etsC)
    intLo = interiorStart - chunkStart + 1;
    intHi = interiorEnd   - chunkStart + 1;
    keep = (etsC(:,1) >= intLo) & (etsC(:,1) <= intHi);
    etsC = etsC(keep,:); echC = echC(keep,:);
    if ~isempty(etsC)
      etsC = uint64(etsC) + uint64(chunkStart - 1);  % to global sample indices
      ets_all = [ets_all; etsC]; %#ok<AGROW>
      ech_all = [ech_all; echC]; %#ok<AGROW>
    end
  end

  startIdx = interiorEnd + 1;  % hop by exactly 60s interior
end

% Final global merge (<300 ms) to match whole-file behavior
[ets, ech] = merge_close_global(ets_all, ech_all, sfx);

% Save next to the script
save(fullfile(scriptDir,'ets.mat'),'ets');
save(fullfile(scriptDir,'ech.mat'),'ech');
fprintf('[save] ets.mat & ech.mat written to: %s (elapsed %.1fs)\n', scriptDir, toc);

end % ---- main function end ----



% ===== helpers: streaming LL computations & exact order stats =====

function [mn, mx, N] = sweep_min_max_count(S, nChan, T, numsamples, chunkSamp, ovlSamp)
mn = inf; mx = -inf; N = 0;
startIdx = 1;
while startIdx <= T
  interiorStart = startIdx;
  interiorEnd   = min(startIdx + chunkSamp - 1, T);
  chunkStart    = max(1, interiorStart - ovlSamp);
  chunkEnd      = min(interiorEnd + ovlSamp, T);
  d = zeros(nChan, chunkEnd - chunkStart + 1, 'single');
  for ch=1:nChan, d(ch,:) = S{ch}(chunkStart:chunkEnd); end
  % LL (channels x time-valid)
  L = nan(size(d),'single');
  last = size(d,2)-numsamples;
  for i=1:last
    L(:,i)=sum(abs(diff(d(:,i:i+numsamples-1),1,2)),2);
  end
  % min/max & count of valid LL
  if last > 0
    block = L(:,1:last);
    mn = min(mn, double(min(block(:))));
    mx = max(mx, double(max(block(:))));
    N  = N + nnz(~isnan(block));
  end
  startIdx = interiorEnd + 1;
end
if ~isfinite(mn), mn = 0; end
if ~isfinite(mx), mx = 0; end
end

function v = kth_order_value(k, S, nChan, T, numsamples, chunkSamp, ovlSamp, lo, hi)
% Find smallest value v such that count(LL <= v) >= k  (binary search)
lo = double(lo); hi = double(hi);
while lo < hi
  mid = floor((lo + hi)/2);
  c = count_leq(mid, S, nChan, T, numsamples, chunkSamp, ovlSamp);
  if c >= k
    hi = mid;
  else
    lo = mid + 1;
  end
end
v = lo;
end

function c = count_leq(th, S, nChan, T, numsamples, chunkSamp, ovlSamp)
c = 0;
startIdx = 1;
while startIdx <= T
  interiorStart = startIdx;
  interiorEnd   = min(startIdx + chunkSamp - 1, T);
  chunkStart    = max(1, interiorStart - ovlSamp);
  chunkEnd      = min(interiorEnd + ovlSamp, T);
  d = zeros(nChan, chunkEnd - chunkStart + 1, 'single');
  for ch=1:nChan, d(ch,:) = S{ch}(chunkStart:chunkEnd); end
  last = size(d,2)-numsamples;
  if last > 0
    % streaming count without storing full L
    for i=1:last
      ll = sum(abs(diff(d(:,i:i+numsamples-1),1,2)),2); % nChan x 1
      c = c + sum(ll <= th);
    end
  end
  startIdx = interiorEnd + 1;
end
end

function [etsM, echM] = merge_close_global(ets, ech, sfx)
if isempty(ets), etsM=ets; echM=ech; return; end
[~,ord]=sort(ets(:,1),'ascend'); ets=ets(ord,:); ech=ech(ord,:);
s=size(ets,1); kill=false(s,1); gap=round(0.3*sfx);
for i=1:s-1
  if (ets(i+1,1)-ets(i,2)) < gap
    ets(i+1,1)=ets(i,1);
    ech(i+1,:)=logical(ech(i+1,:) | ech(i,:));
    kill(i)=true;
  end
end
etsM=ets(~kill,:); echM=ech(~kill,:);
end
