function root = betapath()
%BETAPATH  Put everything the beta run needs on the MATLAB path.
%
%   betapath()
%
%   Adds this folder, gates/, test/, and the two dependency folders that live
%   next door in the repo: the Tort core (eegfilt, ModIndex_v2) and the VACC
%   lib (read_csc). Nothing is copied -- the beta uses the same eegfilt and
%   the same reference ModIndex_v2 as the pipeline it is checking.

here = fileparts(mfilename('fullpath'));
root = fileparts(here);                 % .../Reviving CFC/Revival Pipeline
repo = fileparts(root);                 % .../Reviving CFC

addpath(here);
addpath(fullfile(here, 'gates'));
addpath(fullfile(here, 'test'));

core = fullfile(repo, '01_core_tort');
lib  = fullfile(repo, '03_vacc_pipeline', 'lib');
if isfolder(core), addpath(core); else
    warning('betapath:core', 'Not found: %s (need eegfilt.m, ModIndex_v2.m)', core);
end
if isfolder(lib),  addpath(lib);  else
    warning('betapath:lib',  'Not found: %s (need read_csc.m)', lib);
end
end
