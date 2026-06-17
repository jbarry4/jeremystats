function vacc_collect_vision_out(sessionDirs)
% Copy ONLY VACC_TheVision_out from one or more session directories
% into a fixed output root, naming each dest folder like:
%   PTEN_M13_pten_HF4s1aug1
% (i.e., the last 3 path parts BEFORE the final timestamp folder),
% then group Evt###_##ch.png by channel ranges.
%
% - Accepts a string or string array of session directories.
% - Caps ALL created folder names to the last 25 chars.
% - Fixed output root:
%     /gpfs2/scratch/sakhava1/Batch_Process_All/compiled_out_vision

  if ischar(sessionDirs), sessionDirs = string(sessionDirs); end
  if isstring(sessionDirs) && isscalar(sessionDirs)
      sessionDirs = sessionDirs(:);
  end

  outRoot = "/gpfs2/scratch/sakhava1/Batch_Process_All/compiled_out_vision";
  if ~isfolder(outRoot), mkdir(outRoot); end

  for s = 1:numel(sessionDirs)
    sessionDir = sessionDirs(s);
    src = fullfile(sessionDir, "VACC_TheVision_out");
    if ~isfolder(src)
      warning("Skipping (no VACC_TheVision_out): %s", sessionDir);
      continue;
    end

    % Build pretty folder name from last 3 parts prior to timestamp
    pretty = build_pretty_name(sessionDir);         % e.g., PTEN_M13_pten_HF4s1aug1
    pretty = shorten_name(pretty, 50);              % cap to 25 chars

    dest = fullfile(outRoot, pretty);
    fprintf("\nSRC:  %s\nDEST: %s\n", src, dest);

    if ~isfolder(dest), mkdir(dest); end

    % Copy ONLY the contents of VACC_TheVision_out into dest (no extras)
    ok = copy_contents(src, dest);
    if ~ok
      warning("Copy failed: %s", src);
      continue;
    end

    % Group images by channel ranges inside dest
    group_and_move_images(dest);
  end

  fprintf("\nAll done. Outputs in: %s\n", outRoot);
end


% ---------- helpers ----------
function nameOut = build_pretty_name(sessionDir)
% Take path .../<A>/<B>/<C>/<timestamp>  -> "A_B_C"
% Example:
%   .../PTEN/M13_pten/HF4s1aug1/2023-08-01_11-37-10  -> PTEN_M13_pten_HF4s1aug1

  parts = split(string(sessionDir), filesep);
  if numel(parts) < 4
    % Fallback to last 3 parts if no timestamp leaf
    k = max(1, numel(parts)-2):numel(parts);
    keep = parts(k);
  else
    % Drop final leaf (timestamp), keep prior 3
    keep = parts(end-3:end-1);
  end
  keep = keep(:)';
  nameOut = strjoin(keep, "_");
  nameOut = sanitize_path(nameOut);
end

function ok = copy_contents(srcFolder, destFolder)
% Copy only the CONTENTS of srcFolder into destFolder.
  ok = true;
  list = dir(srcFolder);
  for i = 1:numel(list)
    if list(i).name=="." || list(i).name=="..", continue; end
    from = fullfile(srcFolder, list(i).name);
    to   = fullfile(destFolder, list(i).name);
    tf = copyfile(from, to);
    if ~tf, ok = false; end
  end
end

function group_and_move_images(destRoot)
% Move Evt###_##ch.png files into channel-range folders based on ##ch (1..32)

  % Create group folders (cap names to 25 chars just in case)
  g1 = fullfile(destRoot, shorten_name("group_01-04", 25));
  g2 = fullfile(destRoot, shorten_name("group_05-10", 25));
  g3 = fullfile(destRoot, shorten_name("group_11-20", 25));
  g4 = fullfile(destRoot, shorten_name("group_21-32", 25));
  for d = [g1,g2,g3,g4], if ~isfolder(d), mkdir(d); end, end

  % Only look at top-level copied files
  entries = dir(destRoot);
  entries = entries(~[entries.isdir]);

  if isempty(entries)
    fprintf("  No files found in %s\n", destRoot);
    return;
  end

  % Case-insensitive match: Evt###_##ch.png where ###=1..9999, ##=1..32
  pat = "^Evt(\d{1,4})_([1-9]|[12]\d|3[0-2])ch\.png$";

  moved = 0; skipped = 0;
  for i = 1:numel(entries)
    fn = string(entries(i).name);
    if ~endsWith(lower(fn), ".png"), continue; end

    tok = regexpi(fn, pat, "tokens", "once");
    if isempty(tok)
      skipped = skipped + 1;
      continue;
    end

    ch = str2double(tok{2});
    if ch>=1 && ch<=4
      tgtDir = g1;
    elseif ch>=5 && ch<=10
      tgtDir = g2;
    elseif ch>=11 && ch<=20
      tgtDir = g3;
    elseif ch>=21 && ch<=32
      tgtDir = g4;
    else
      skipped = skipped + 1;
      continue;
    end

    srcPath  = fullfile(destRoot, fn);
    destPath = fullfile(tgtDir, fn);

    if isfile(destPath)
      [~,name,ext] = fileparts(fn);
      destPath = fullfile(tgtDir, name + "_dup" + ext);
    end

    [ok,msg] = movefile(srcPath, destPath);
    if ~ok
      warning("  Move failed: %s -> %s (%s)", srcPath, destPath, msg);
      skipped = skipped + 1;
    else
      moved = moved + 1;
    end
  end

  fprintf("  Grouped images: moved=%d, skipped=%d\n", moved, skipped);
end

function safe = sanitize_path(p)
% Replace slashes/spaces and illegal characters for a safe name
  s = string(p);
  s = replace(s, filesep, "__");
  s = regexprep(s, "\s+", "_");
  s = regexprep(s, "[:*?""<>|]", "_");
  safe = s;
end

function short = shorten_name(nameStr, maxLen)
% Truncate to the last maxLen characters
  nameStr = string(nameStr);
  if strlength(nameStr) > maxLen
    short = extractAfter(nameStr, strlength(nameStr) - maxLen);
  else
    short = nameStr;
  end
end
