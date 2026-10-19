function P = params()
%PARAMS  Every setting for the CFC beta run, in one place.
%
%   P = params()
%
%   Nothing downstream invents a number. If a value matters, it is here, it
%   is saved into the output .mat, and it is printed by RunBeta at startup.
%
%   Grid is deliberately narrower than newFCSE.m: the beta is theta-focused
%   (4-12 Hz phase) rather than the full 1-26 Hz sweep, because the point is
%   to check the machinery, not to survey.

% ---- acquisition -------------------------------------------------------
P.downsample   = 10;      % read_csc decimation. 32556 Hz -> ~3255.6 Hz
P.notch        = [59 61]; % mains bandstop, 2nd-order butter, filtfilt
P.notchOrder   = 2;

% ---- epochs ------------------------------------------------------------
P.epochSec     = 6;       % non-overlapping. 6 s ~= 24-72 slow cycles at 4-12 Hz
P.sharpSD      = 6;       % nSharp counts |x| > sharpSD * robust SD (recorded only)

% ---- the grid ----------------------------------------------------------
P.slowVec      = 4:0.5:12;    % 17 phase bands, low edge of each
P.slowBW       = 0.5;         % contiguous, same convention as newFCSE.m
P.fastVec      = 20:5:200;    % 37 amplitude bands, low edge of each
P.fastBW       = 10;          % same as newFCSE.m

% ---- the measure -------------------------------------------------------
P.nbin         = 18;      % 20 deg phase bins. Tort ModIndex_v2 convention

% ---- surrogates --------------------------------------------------------
P.nSurr        = 100;     % see README: 50 is defensible and halves runtime
P.minShiftSec  = 0.5;     % smallest circular shift, keeps surrogate honest
P.seed         = 42;      % rng seed, so a re-run reproduces the same z
% 'within' = circular shift inside the epoch (the specified design).
% 'cross'  = pair this epoch's phase with another epoch's amplitude. Measured
%            to give a better-behaved null; see README, "What gate 6 found".
P.surrogate    = 'within';

% ---- storage -----------------------------------------------------------
P.store        = 'single';  % filter banks are large; see FilterBanks.m

% ---- derived (never set these by hand) ---------------------------------
P.slowCenters  = P.slowVec + P.slowBW/2;   % what you plot against
P.fastCenters  = P.fastVec + P.fastBW/2;
P.nSlow        = numel(P.slowVec);
P.nFast        = numel(P.fastVec);

P.version      = 'beta-1';
end
