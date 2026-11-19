function sessions = find_pten_sessions(dataRoot)
% Locate each M#_s# session's top-level "timestamps" folder (kilosort
% cluster spike-time .mat files), skipping the duplicate copy nested
% under binary\kilosort_.../timestamps.

sessions = struct('name', {}, 'timestampsDir', {});

mouseDirs = dir(fullfile(dataRoot, 'M*_s*'));
mouseDirs = mouseDirs([mouseDirs.isdir]);

for i = 1:numel(mouseDirs)
    mouseSessionName = mouseDirs(i).name;
    mouseSessionPath = fullfile(dataRoot, mouseSessionName);

    dateDirs = dir(mouseSessionPath);
    dateDirs = dateDirs([dateDirs.isdir] & ~ismember({dateDirs.name}, {'.', '..'}));

    for j = 1:numel(dateDirs)
        candidate = fullfile(mouseSessionPath, dateDirs(j).name, 'timestamps');
        if isfolder(candidate)
            sessions(end+1) = struct('name', mouseSessionName, 'timestampsDir', candidate); %#ok<AGROW>
        end
    end
end
end
