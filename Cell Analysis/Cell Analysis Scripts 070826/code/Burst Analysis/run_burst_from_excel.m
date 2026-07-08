function run_burst_from_excel_scan(feeder_xlsx)
% run_burst_from_excel_scan  Read session names/paths, scan timestamps/, and export burst summary.
%
% INPUT Excel (each column = one session):
%   Row 1 : session name   (used for output file name)
%   Row 2 : session path   (contains a subfolder named "timestamps" with .mat files)
%
% BEHAVIOR
%   - Scans "<session_path>/timestamps/" for *.mat files
%   - Cluster ID = filename without extension
%   - Loads the FIRST variable in each .mat as spike SAMPLES (integers)
%   - Converts to seconds via st_seconds = double(samples)/30000 (Fs fixed)
%   - Computes burst metrics (burst_all_metrics), writes one Excel per session
%
% OUTPUT
%   <session_path>/<session_name>_burst_summary.xlsx
%
% DEPENDENCIES ON PATH
%   burst_all_metrics.m, detect_bursts.m, burst_index_acg.m, acg1ms.m

    isi_thresh_ms = 9;    % fixed threshold
    Fs = 30000;           % fixed sampling rate (Hz)

    T = readcell(feeder_xlsx);
    nSessions = size(T, 2);

    for s = 1:nSessions
        % Read session name and path (row 1 & 2 of column s)
        session_name = char(string(T{1, s}));
        session_path = char(string(T{2, s}));

        if isempty(session_name) || isempty(session_path)
            warning('Skipping column %d: missing session name or path.', s);
            continue;
        end

        timestamps_dir = fullfile(session_path, 'timestamps');
        if ~isfolder(timestamps_dir)
            warning('No "timestamps" folder at: %s (skipping %s)', timestamps_dir, session_name);
            continue;
        end

        files = dir(fullfile(timestamps_dir, '*.mat'));
        if isempty(files)
            warning('No .mat files in %s (skipping %s)', timestamps_dir, session_name);
            continue;
        end

        % Sort clusters numerically when possible
        cluster_ids = arrayfun(@(f) erase(f.name, '.mat'), files, 'UniformOutput', false);
        [~, order] = sort_nat(cluster_ids);  % natural string sort
        files = files(order);

        fprintf('▶ Session: %s | %d clusters found\n', session_name, numel(files));
        out_rows = [];

        for k = 1:numel(files)
            cluster_id = erase(files(k).name, '.mat');
            fpath = fullfile(files(k).folder, files(k).name);

            S  = load(fpath);
            fn = fieldnames(S);
            if isempty(fn)
                warning('Empty MAT: %s', fpath);
                continue;
            end
            spike_samples = S.(fn{1});
            if ~isnumeric(spike_samples) || isempty(spike_samples)
                warning('Non-numeric/empty spike vector in %s (var: %s)', fpath, fn{1});
                continue;
            end

            st_seconds = double(spike_samples(:)) ./ Fs;

            % Compute metrics
            res = burst_all_metrics(st_seconds, isi_thresh_ms);

            % Build one row
            row = table({cluster_id}, res.NB, res.NS, res.p_burst, ...
                res.length_counts.n2, res.length_counts.n3, ...
                res.length_counts.n4, res.length_counts.nMore, ...
                res.length_probs.p2, res.length_probs.p3, ...
                res.length_probs.p4, res.length_probs.pMore, ...
                res.acg_index, ...
                'VariableNames', {'Cluster','NB','NS','pBurst','n2','n3','n4','nMore', ...
                                  'p2','p3','p4','pMore','ACGindex'});
            out_rows = [out_rows; row]; %#ok<AGROW>

            fprintf('   • %s OK\n', cluster_id);
        end

        out_xlsx = fullfile(session_path, [session_name '_burst_summary.xlsx']);
        writetable(out_rows, out_xlsx);
        fprintf('✅ Saved: %s\n', out_xlsx);
    end
end

% -------- natural sort helper (keeps "1,2,10" in numeric order) ----------
function [sortedStrings, sortIndex] = sort_nat(strings)
    % Convert to string array for robust handling
    strings = string(strings(:));
    % Extract numeric chunks for sorting
    tokens = regexp(strings, '(\d+)|(\D+)', 'match');
    maxlen = max(cellfun(@numel, tokens));
    % Pad tokens so all have same length
    for i = 1:numel(tokens)
        if numel(tokens{i}) < maxlen
            tokens{i}(end+1:maxlen) = {''};
        end
    end
    % Build key columns: numeric chunks as numbers, non-numeric lexicographic (lowercase)
    n = numel(strings);
    cols = cell(maxlen, 1);
    isnum = false(maxlen, 1);
    for j = 1:maxlen
        colj = strings; % placeholder to size
        col = strings.empty(0,1); %#ok<STRNU>
        col = strings; %#ok<NASGU>
        this = strings; %#ok<NASGU>
        kj = cell(n,1);
        for i = 1:n
            tok = tokens{i};
            if j <= numel(tok)
                kj{i} = tok{j};
            else
                kj{i} = '';
            end
        end
        % numeric?
        numMask = cellfun(@(x) ~isempty(x) && all(isstrprop(x,'digit')), kj);
        vals = zeros(n,1);
        vals(numMask) = str2double(string(kj(numMask)));
        % For non-numeric chunks, use categorical order by lower-case string
        strVals = lower(string(kj));
        cols{j} = [vals, double(strVals>""), double(strVals)]; % tie-breaker
        isnum(j) = any(numMask);
    end
    % Build composite sort key: interleave numeric priority then string code
    key = [];
    for j = 1:maxlen
        key = [key, cols{j}]; %#ok<AGROW>
    end
    [~, sortIndex] = sortrows(key);
    sortedStrings = strings(sortIndex);
end
