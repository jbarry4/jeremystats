function dataDir = find_session_data_dir(dataRoot, sessionName)
% find_session_data_dir  Locate the date-stamped recording folder for a
% PTEN M#_s# session -- the folder that holds both the raw CSC*.ncs files
% and the sibling "timestamps" folder (kilosort cluster spike times).

sessionPath = fullfile(dataRoot, sessionName);
if ~isfolder(sessionPath)
    error('find_session_data_dir:noSession', 'Session folder not found: %s', sessionPath);
end

dateDirs = dir(sessionPath);
dateDirs = dateDirs([dateDirs.isdir] & ~ismember({dateDirs.name}, {'.', '..'}));

for i = 1:numel(dateDirs)
    candidate = fullfile(sessionPath, dateDirs(i).name);
    if isfolder(fullfile(candidate, 'timestamps'))
        dataDir = candidate;
        return;
    end
end
error('find_session_data_dir:noTimestamps', ...
    'No date subfolder with a "timestamps" folder found under: %s', sessionPath);
end
