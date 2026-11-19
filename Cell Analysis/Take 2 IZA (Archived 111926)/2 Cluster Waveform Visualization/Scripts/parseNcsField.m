function v = parseNcsField(hdr, fieldName)
% parseNcsField  Extract a numeric value from a Neuralynx NCS header cell array.
    v = NaN;
    for i = 1:numel(hdr)
        line = strtrim(hdr{i});
        if contains(line, fieldName, 'IgnoreCase', true)
            tok = regexp(line, [fieldName, '\s+([Ee0-9\.\+\-]+)'], 'tokens', 'once');
            if ~isempty(tok), v = str2double(tok{1}); return; end
        end
    end
end
