function sessionName = session_name_from_ied_filename(baseName)
% session_name_from_ied_filename  "m13s2_solid_ied" -> "M13_s2"
%
% Matches the PTEN Project\PTEN\M#_s# folder naming convention used by
% find_session_data_dir / find_pten_sessions.

tok = regexpi(baseName, '^m(\d+)s(\d+)_solid_ied$', 'tokens', 'once');
if isempty(tok)
    error('session_name_from_ied_filename:badFormat', ...
        'Filename "%s" does not match pattern m<mouse>s<session>_solid_ied', baseName);
end
sessionName = sprintf('M%s_s%s', tok{1}, tok{2});
end
