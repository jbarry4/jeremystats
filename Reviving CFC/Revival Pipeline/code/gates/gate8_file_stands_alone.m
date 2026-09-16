function [pass, info] = gate8_file_stands_alone(matFile, outDir)
%GATE8  The file stands alone.
%
%   Launches a FRESH MATLAB with an empty path, loads only the .mat, and
%   redraws the mean comodulogram from it. If anything needed is missing,
%   this fails now rather than at channel 64.
%
%   A fresh process is the point. Checking inside the current session would
%   pass on variables that merely happen to still be in memory, and on
%   functions that happen to still be on the path.

if nargin < 2, outDir = fileparts(matFile); end
fprintf('\n--- GATE 8: the file stands alone ---\n');

info = struct('matFile', matFile);
assert(isfile(matFile), 'gate8:noFile', 'No such file: %s', matFile);

[~, uniq]  = fileparts(tempname);                      % tpXXXXXXXX
scriptName = ['gate8_' regexprep(uniq, '[^A-Za-z0-9]', '')];
scriptFile = fullfile(tempdir, [scriptName '.m']);
pngFile    = fullfile(outDir, 'gate8_standalone.png');

lines = {
'restoredefaultpath;'
'clear all; close all;'
sprintf('R = load(''%s'');', strrep(matFile, '\', '\\'))
'req = {''MI'',''slowCenters'',''fastCenters'',''epochs'',''params'',''sourcePath'',''fs''};'
'miss = req(~isfield(R, req));'
'if ~isempty(miss)'
'    fprintf(''MISSING: %s\n'', strjoin(miss, '', ''));'
'    exit(3);'
'end'
'm = mean(R.MI, 3, ''omitnan'');'
'f = figure(''Color'',''w'',''Visible'',''off'',''Position'',[0 0 620 470]);'
'ax = axes(f);'
'imagesc(ax, R.slowCenters, R.fastCenters, m.''); set(ax,''YDir'',''normal''); colorbar(ax);'
'xlabel(ax,''phase freq (Hz)''); ylabel(ax,''amplitude freq (Hz)'');'
'title(ax, sprintf(''redrawn from the .mat alone  -  %d epochs'', size(R.MI,3)));'
sprintf('exportgraphics(f, ''%s'', ''Resolution'', 130);', strrep(pngFile, '\', '\\'))
'fprintf(''REDREW %dx%dx%d from %s\n'', size(R.MI,1), size(R.MI,2), size(R.MI,3), R.sourcePath);'
'exit(0);'
};

fid = fopen(scriptFile, 'w');
fprintf(fid, '%s\n', lines{:});
fclose(fid);
cleaner = onCleanup(@() delete(scriptFile));

exe = fullfile(matlabroot, 'bin', 'matlab');
cmd = sprintf('"%s" -batch "addpath(''%s'');%s"', exe, tempdir, scriptName);

fprintf('    launching a fresh MATLAB with restoredefaultpath...\n');
t0 = tic;
[st, out] = system(cmd);
info.elapsed = toc(t0);
info.status  = st;
info.output  = strtrim(out);

fprintf('%s\n', localIndent(info.output));
pass = (st == 0);
info.png = pngFile;

if pass
    fprintf('    fresh session redrew the map in %.0f s: %s\n', info.elapsed, pngFile);
    fprintf('    GATE 8 PASSES - the file is self-contained.\n');
else
    fprintf('    GATE 8 FAILS (exit %d) - the .mat is missing something it needs.\n', st);
    fprintf('    Add it to SaveChannel.m now, not at channel 64.\n');
end
info.pass = pass;
end


function s = localIndent(s)
s = regexprep(s, '(^|\n)', '$1      ');
end
