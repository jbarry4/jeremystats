function xf_setpath()
%XF_SETPATH  Put the Analyse folders on the MATLAB path.
%
%   xf_setpath()  adds core/, io/, vendor/misc/ and vendor/chronux_spectral/
%   relative to this file.  Run it once per MATLAB session.
%
%   gui/ is deliberately NOT added: it holds the reference copy of
%   xplorefinder.m, and putting it on the path would shadow whichever
%   xplorefinder you actually run.
%
%   The vendored chronux subset is only the 14 files the Analyse modes
%   need.  If you already have the full chronux on your path, this folder
%   will shadow it with identical copies -- harmless, but you can skip it
%   by editing the list below.

here = fileparts(mfilename('fullpath'));

addpath(fullfile(here, 'core'));
addpath(fullfile(here, 'io'));
addpath(fullfile(here, 'vendor', 'misc'));
addpath(fullfile(here, 'vendor', 'chronux_spectral'));

fprintf('Xplorefinder Analyse on path (%s)\n', here);
