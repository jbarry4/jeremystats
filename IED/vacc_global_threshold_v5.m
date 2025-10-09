function vacc_global_threshold_v5(recDir, prc, sfx, llw)
% V5 — GLOBAL LL THRESHOLD (streamed, exact percentile)
% ---------------------------------------------------------
% Computes the identical global LL percentile threshold
% used by LLspikedetector, but avoids large matrices.
% Works channel-by-channel directly from .ncs files.
%
% Output:
%   Saves "global_ll_threshold.mat" in recDir.
%
% Default params: prc=99.5, sfx=30000 Hz, llw=0.04 s
% ---------------------------------------------------------

if nargin<2||isempty(prc), prc=99.5; end
if nargin<3||isempty(sfx), sfx=30000; end
if nargin<4||isempty(llw), llw=0.04; end
W = max(2, round(sfx*llw));

fprintf('\n=== GLOBAL LL THRESHOLD (v5) ===\n');
fprintf('Directory : %s\n', recDir);
fprintf('Params    : sfx = %d Hz | llw = %.3f s | window = %d samples | percentile = %.2f\n\n', ...
        sfx, llw, W, prc);

% ---------- 1) Find even-numbered CSC files ----------
fprintf('Scanning for CSC*.ncs files...\n');
files = dir(fullfile(recDir,'CSC*.ncs'));
if isempty(files)
    error('No CSC*.ncs in %s', recDir);
end

names = {files.name};
nums  = cellfun(@(s) sscanf(s,'CSC%d.ncs'), names);
keep  = mod(nums,2)==0 & ~isnan(nums);
files = files(keep); nums = nums(keep);
[~,ix] = sort(nums); files = files(ix); nums = nums(ix);
if isempty(files)
    error('No even-numbered CSC files found.');
end
fprintf('Found %d even channels: %s\n\n', numel(nums), mat2str(nums));

% ---------- 2) Stream LL values to temp file ----------
tmp = [tempname,'.bin'];
fid = fopen(tmp,'w');
assert(fid>0, 'Cannot open temp file for writing');
nLL = uint64(0); vmin = +inf; vmax = -inf;

fprintf('--- PASS 1: Computing and streaming LL values ---\n');
for k=1:numel(files)
    fn = fullfile(files(k).folder, files(k).name);
    fprintf('  [%2d/%2d] Reading %s ... ', k, numel(files), files(k).name);
    samples = Nlx2MatCSC(fn,[0 0 0 0 1],0,1,[]);
    x = single(-samples(:)); L = numel(x);
    fprintf('(%d samples)\n', L);

    if L < W
        fprintf('    Skipped (too short)\n');
        continue;
    end

    % Initial LL window
    curLL = 0;
    for i=1:W-1
        curLL = curLL + abs(x(i+1)-x(i));
    end
    fwrite(fid, single(curLL), 'single');
    nLL = nLL + 1;
    vmin = min(vmin, double(curLL));
    vmax = max(vmax, double(curLL));

    % Slide window
    for t=W+1:L
        curLL = curLL - abs(x(t-W+1)-x(t-W)) + abs(x(t)-x(t-1));
        fwrite(fid, single(curLL), 'single');
        nLL = nLL + 1;
        if curLL < vmin, vmin = double(curLL); end
        if curLL > vmax, vmax = double(curLL); end
    end

    fprintf('    Done. Total LL windows so far: %s\n', string(nLL));
end
fclose(fid);
fprintf('--- PASS 1 complete ---\n');
fprintf('Total LL windows: %s | Range: [%.4g, %.4g]\n\n', string(nLL), vmin, vmax);

% ---------- 3) Compute exact percentile ----------
if nLL==0
    threshold = NaN;
    fprintf('No data to process.\n');
else
    fprintf('--- PASS 2: Computing exact percentile (%.2f) ---\n', prc);
    threshold = exact_percentile_from_disk(tmp, nLL, prc, vmin, vmax);
    fprintf('--- PASS 2 complete ---\n\n');
end

% ---------- 4) Save results ----------
if exist(tmp,'file'), try, delete(tmp); catch, end, end
filesUsed = arrayfun(@(f) fullfile(f.folder,f.name), files, 'UniformOutput', false);
outPath = fullfile(recDir,'global_ll_threshold.mat');
save(outPath,'threshold','prc','sfx','llw','W','nLL','filesUsed');

fprintf('=== RESULT ===\n');
fprintf('Global LL threshold (%.2f%%) = %.6g\n', prc, threshold);
fprintf('Saved: %s\n', outPath);
fprintf('===============================================\n\n');
end

% ---------- Helper: percentile from disk ----------
function v = exact_percentile_from_disk(binPath, N, prc, vmin, vmax)
k = max(1, min(double(N), round(prc/100 * double(N))));
lo = vmin; hi = vmax;
maxBin = 65536; chunk = 5e6;

iter = 1;
while true
    if ~isfinite(lo) || ~isfinite(hi) || lo==hi
        v = lo; return;
    end

    fprintf('  [Iter %d] Narrowing range [%.4g, %.4g]\n', iter, lo, hi);

    nb    = min(maxBin, max(256, ceil(sqrt(double(N)))));
    edges = linspace(lo, hi, nb+1);
    cnt   = zeros(1, nb);   % double is fine for counting

    % ---- count pass (use histcounts) ----
    fid = fopen(binPath,'r'); assert(fid>0);
    while true
        buf = fread(fid, chunk, 'single=>double');
        if isempty(buf), break; end
        % histcounts ignores NaNs by default
        cnt = cnt + histcounts(buf, edges);
    end
    fclose(fid);

    csum = cumsum(cnt);
    b = find(csum>=k, 1, 'first');
    if isempty(b), v = hi; return; end
    left = (b>1)*csum(b-1); need = k - left;
    binLo = edges(b); binHi = edges(b+1);

    fprintf('    Bin %d contains target (count=%g)\n', b, cnt(b));
    fprintf('    Refining to [%.4g, %.4g]\n', binLo, binHi);

    % ---- collect only values in target bin ----
    pool = [];
    fid = fopen(binPath,'r'); assert(fid>0);
    while true
        buf = fread(fid, chunk, 'single=>double');
        if isempty(buf), break; end
        mask = (buf>=binLo & buf<binHi) | (binHi==hi & buf==hi);
        if any(mask), pool = [pool, buf(mask)]; %#ok<AGROW>
        end
    end
    fclose(fid);

    if numel(pool) <= 2e7
        fprintf('    Final sort (%d values)...\n', numel(pool));
        pool = sort(pool);
        need = max(1, min(need, numel(pool)));
        v = pool(need);
        fprintf('    Exact percentile found: %.6g\n', v);
        return;
    else
        fprintf('    Still too many (%d), narrowing again...\n', numel(pool));
        lo = binLo; hi = binHi; iter = iter + 1;
    end
end
end
