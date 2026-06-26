function fPath = findCscFile(chNum, allNcsNames, targetPath)
% findCscFile  Locate a CSC file by channel number, tolerating naming variants.
% Matches CSC<N>.ncs, CSC0<N>.ncs, CSC<N>_001.ncs, CSC<N>.nsc, etc.
    pat      = ['^CSC0*', num2str(chNum), '([^0-9].*)?\.(ncs|nsc)$'];
    matchIdx = ~cellfun(@isempty, regexpi(allNcsNames, pat));
    matches  = allNcsNames(matchIdx);
    if isempty(matches)
        fPath = ''; return;
    end
    exactName = sprintf('CSC%d.ncs', chNum);
    exactIdx  = strcmpi(matches, exactName);
    if any(exactIdx)
        fPath = fullfile(targetPath, matches{find(exactIdx,1)});
    else
        fPath = fullfile(targetPath, matches{1});
    end
end
