function ExtractTTL()
% EXTRACTTTL
% Scans D:\HOF DATA\ACTIVE DATA for all Events.nev files,
% extracts TTL codes with timestamps, and saves to All_TTL_Events.xlsx.
% No arguments needed — root path is hard-coded below.

    ROOT_DIR    = 'D:\HOF DATA\ACTIVE DATA';
    OUTPUT_FILE = fullfile(ROOT_DIR, 'All_TTL_Events.xlsx');

    % --- ADD reqsPath (search script folder then parent) ---
    scriptDir  = fileparts(mfilename('fullpath'));
    reqsFolder = fullfile(scriptDir, 'reqsPath');
    if ~exist(reqsFolder, 'dir')
        reqsFolder = fullfile(fileparts(scriptDir), 'reqsPath');
    end
    if exist(reqsFolder, 'dir')
        addpath(reqsFolder);
    end

    % --- CHECK LOADER ---
    if exist('Nlx2MatEV', 'file') == 0
        error('Nlx2MatEV not found. Add it to your MATLAB path or place it in the reqsPath folder.');
    end

    fprintf('Scanning: %s\n\n', ROOT_DIR);
    files = dir(fullfile(ROOT_DIR, '**', 'Events.nev'));

    if isempty(files)
        error('No Events.nev files found under: %s', ROOT_DIR);
    end

    fprintf('Found %d file(s). Processing...\n\n', length(files));
    MasterTable = table();

    % Pre-compute root depth for path anchoring
    rootParts  = strsplit(ROOT_DIR, filesep);
    rootDepth  = length(rootParts);

    for i = 1:length(files)
        filePath = fullfile(files(i).folder, files(i).name);

        try
            % --- PARSE SESSION IDENTITY ---
            % Structure: ROOT_DIR \ SessionFolder \ DATA \ Events.nev
            % e.g. D:\HOF DATA\ACTIVE DATA\J2_PRECON2_SP_091325\DATA\Events.nev
            pathParts = strsplit(files(i).folder, filesep);

            if length(pathParts) > rootDepth
                sessionFolder = pathParts{rootDepth + 1};
            else
                sessionFolder = pathParts{end};
            end

            % Parse: J2_PRECON2_SP_091325  ->  RatID | Session | Protocol | Date
            tokens = strsplit(sessionFolder, '_');
            if length(tokens) >= 4
                RatID    = tokens{1};
                Session  = strjoin(tokens(2:end-2), '_');
                Protocol = tokens{end-1};
                RecDate  = tokens{end};
            elseif length(tokens) == 3
                RatID    = tokens{1};
                Session  = tokens{2};
                Protocol = tokens{3};
                RecDate  = 'Unknown';
            else
                RatID    = sessionFolder;
                Session  = 'Unknown';
                Protocol = 'Unknown';
                RecDate  = 'Unknown';
            end

            fprintf('[%d/%d] %-4s | %-8s | %-4s | %s ... ', ...
                i, length(files), RatID, Session, Protocol, RecDate);

            % --- LOAD EVENTS ---
            [TimeStamps, EventIDs, TTLs, EventStrings] = ...
                Nlx2MatEV(filePath, [1 1 1 0 1], 0, 1);

            if isempty(TimeStamps)
                fprintf('SKIPPED (empty).\n');
                continue;
            end

            % --- NORMALIZE & BUILD TABLE ---
            t_sec   = double(TimeStamps(:) - TimeStamps(1)) / 1e6;
            ttl_val = double(TTLs(:));
            evt_id  = double(EventIDs(:));
            evt_str = string(EventStrings(:));

            n = length(t_sec);
            T = table( ...
                repmat(string(RatID),    n, 1), ...
                repmat(string(Session),  n, 1), ...
                repmat(string(Protocol), n, 1), ...
                repmat(string(RecDate),  n, 1), ...
                t_sec, ttl_val, evt_id, evt_str, ...
                'VariableNames', ...
                {'RatID','Session','Protocol','Date','Time_s','TTL','EventID','EventString'});

            MasterTable = [MasterTable; T]; %#ok<AGROW>
            fprintf('OK (%d events).\n', n);

        catch ME
            fprintf('\n   !!! ERROR: %s\n   %s\n\n', files(i).folder, ME.message);
        end
    end

    % --- SAVE ---
    fprintf('\n');
    if ~isempty(MasterTable)
        writetable(MasterTable, OUTPUT_FILE);
        fprintf('================================================\n');
        fprintf('DONE. %d total events -> %s\n', height(MasterTable), OUTPUT_FILE);
        fprintf('================================================\n');
    else
        disp('No valid data found. Nothing saved.');
    end
end
