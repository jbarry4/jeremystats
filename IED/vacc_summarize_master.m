function vacc_summarize_master(masterFile)
% VACC summary + plots from compiled_master.mat
% USAGE:
%   vacc_summarize_master('/gpfs2/scratch/sakhava1/Batch_Process_All/compiled_out/compiled_master.mat')
%
% Assumes compiled_master.mat has:
%   Sessions (struct array with fields: path, when, ech, ets, missing)

  if nargin < 1
    masterFile = '/gpfs2/scratch/sakhava1/Batch_Process_All/compiled_out/compiled_master.mat';
  end

  S = load(masterFile);
  Sessions = S.Sessions;

  n = numel(Sessions);
  if n == 0
    fprintf('No sessions in master. Nothing to summarize.\n');
    return;
  end

  % ---------- basic tallies ----------
  missing_folder = false(n,1);
  missing_ech    = false(n,1);
  missing_ets    = false(n,1);
  spikes_per_session = zeros(n,1);
  chans_per_spike_all = [];  % big vector across all sessions (integers)
  max_ch = 0;

  for i = 1:n
    m = Sessions(i).missing;
    missing_folder(i) = logical(m.folder);
    missing_ech(i)    = logical(m.ech);
    missing_ets(i)    = logical(m.ets);

    % spikes
    spikes = 0;
    if ~missing_ech(i) && ~isempty(Sessions(i).ech)
      spikes = size(Sessions(i).ech, 1);
      % per-spike # triggered channels = sum of row
      counts = sum(Sessions(i).ech ~= 0, 2);
      chans_per_spike_all = [chans_per_spike_all; counts]; %#ok<AGROW>
      max_ch = max(max_ch, size(Sessions(i).ech, 2));
    elseif ~missing_ets(i) && ~isempty(Sessions(i).ets)
      spikes = numel(Sessions(i).ets);  % fallback if ech missing but ets present
    end
    spikes_per_session(i) = spikes;
  end

  has_all = ~(missing_folder | missing_ech | missing_ets);
  usable  = (~missing_folder) & (spikes_per_session > 0);

  % ---------- success & missing ----------
  fprintf('\n=== SESSION COUNTS ===\n');
  fprintf('Total sessions:                %d\n', n);
  fprintf('Usable (folder+ech+ets):       %d (%.1f%%)\n', sum(has_all), 100*mean(has_all));
  fprintf('Usable (folder & >0 spikes):   %d (%.1f%%)\n', sum(usable), 100*mean(usable));
  fprintf('Missing folder:                %d\n', sum(missing_folder));
  fprintf('Missing ech.mat:               %d\n', sum(missing_ech));
  fprintf('Missing ets.mat:               %d\n', sum(missing_ets));

  if any(missing_folder)
    fprintf('\n-- Paths with MISSING FOLDER --\n');
    disp(string({Sessions(missing_folder).path}'));
  end
  if any(missing_ech)
    fprintf('\n-- Paths with MISSING ech.mat --\n');
    disp(string({Sessions(missing_ech).path}'));
  end
  if any(missing_ets)
    fprintf('\n-- Paths with MISSING ets.mat --\n');
    disp(string({Sessions(missing_ets).path}'));
  end

  % ---------- aggregates ----------
  avg_ch_per_spike = NaN;
  if ~isempty(chans_per_spike_all)
    avg_ch_per_spike = mean(chans_per_spike_all);
  end

  avg_spikes_per_session_all = mean(spikes_per_session);
  if any(usable)
    avg_spikes_per_session_usable = mean(spikes_per_session(usable));
  else
    avg_spikes_per_session_usable = NaN;
  end

  fprintf('\n=== QUANT STATS ===\n');
  fprintf('Average channels per spike (across all spikes with ECH): %.3f\n', avg_ch_per_spike);
  fprintf('Average spikes per session (all):                        %.3f\n', avg_spikes_per_session_all);
  fprintf('Average spikes per session (usable only):                %.3f\n', avg_spikes_per_session_usable);

  % ---------- top / bottom 10 by spikes ----------
  [sorted_counts, idx] = sort(spikes_per_session, 'descend');
  topK = min(10, n);
  botK = min(10, n);

  fprintf('\n=== TOP %d BY SPIKE COUNT ===\n', topK);
  for k = 1:topK
    ii = idx(k);
    fprintf('%4d  %6d  %s\n', k, sorted_counts(k), Sessions(ii).path);
  end

  fprintf('\n=== BOTTOM %d BY SPIKE COUNT ===\n', botK);
  for k = 1:botK
    ii = idx(end-k+1);
    fprintf('%4d  %6d  %s\n', k, sorted_counts(end-k+1), Sessions(ii).path);
  end

  % ---------- plots ----------
  % 1) Histogram: # triggered channels per spike (integers)
  if ~isempty(chans_per_spike_all)
    figure('Name','Channels per spike');
    histogram(chans_per_spike_all, 'BinMethod','integers');
    xlabel('Triggered channels per spike');
    ylabel('Count of spikes');
    title('Histogram: Triggered channels per spike');
    grid on;
  else
    fprintf('\n(no ECH matrices with spikes were found; skipping channels-per-spike histogram)\n');
  end

  % 2) Histogram: # spikes per session
  figure('Name','Spikes per session');
  histogram(spikes_per_session);
  xlabel('Spikes per session');
  ylabel('Count of sessions');
  title('Histogram: Spikes per session');
  grid on;

end
