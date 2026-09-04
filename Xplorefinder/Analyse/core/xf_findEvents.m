function [TS, idx] = xf_findEvents(Samples, SF, startTime, notCloserThan, moreThan, findMin, findMax)
%XF_FINDEVENTS  Threshold/peak detector -- xplorefinder's "local min" spike finder.
%
%   [TS, IDX] = xf_findEvents(SAMPLES, SF, STARTTIME, NOTCLOSERTHAN, MORETHAN, FINDMIN, FINDMAX)
%
%   SAMPLES        signal for the displayed window
%   SF             sampling frequency, Hz
%   STARTTIME      recording time of SAMPLES(1), s (GUI: Data.start).  Added
%                  to the result so TS is on the recording clock.
%   NOTCLOSERTHAN  refractory period in MILLISECONDS (GUI: 'not closer than',
%                  Data.spkypesrch(i).closerth).  Converted internally to
%                  samples as notCloserThan*1E-3*SF.
%   MORETHAN       amplitude threshold in signal units (GUI: 'more than',
%                  Data.spkypesrch(i).moreth).  Pass [] for no threshold --
%                  every local extremum is returned, which on a real EEG
%                  window is a very large number of events.
%   FINDMIN        detect negative-going peaks (GUI checkboxfmin)
%   FINDMAX        detect positive-going peaks (GUI checkboxfmax)
%
%   TS   event times in SECONDS on the recording clock
%   IDX  event positions as 1-based indices into SAMPLES
%
%   Detection is LocalMinima(x*direction, refractorySamples, -MORETHAN),
%   where direction is -1 to find maxima and +1 to find minima.  The
%   returned index is decremented by 1 before dividing by SF, exactly as the
%   GUI does -- ((LocalMinima(...)-1)/SF)+start -- so a detection on the
%   first sample maps to STARTTIME.
%
%   NOTE  When BOTH FINDMIN and FINDMAX are set, the GUI switches to
%   detecting on abs(SAMPLES) and sets its direction list to [-1 0].  The
%   -1 pass finds peaks of |signal| (i.e. both polarities at once, which is
%   the intent).  The 0 pass multiplies the signal by zero and searches a
%   flat line -- it finds nothing whenever MORETHAN > 0, and is simply dead
%   work.  Reproduced here for fidelity; the 0 pass is skipped when it
%   provably cannot match, so results are identical but faster.  See
%   gui/xplorefinder.m showsearchmin (~line 2799) for the original.
%
%   Extracted from xplorefinder.m showsearchmin.
%
%   See also LOCALMINIMA, XF_EXTRACTWAVEFORMS.

if nargin < 3 || isempty(startTime),     startTime = 0;     end
if nargin < 4 || isempty(notCloserThan), notCloserThan = 2; end
if nargin < 5,                           moreThan = [];     end
if nargin < 6 || isempty(findMin),       findMin = true;    end
if nargin < 7 || isempty(findMax),       findMax = false;   end

if ~findMin && ~findMax
    TS = []; idx = [];
    return;
end

refractory = notCloserThan * 1E-3 * SF;     % ms -> samples

% GUI mapping: [max min] selects from [-1 1]; -1 finds maxima, +1 finds minima
init_max_min = [-1 1];
directions   = init_max_min(logical([findMax findMin]));

useAbs = false;
if numel(directions) == 2 && directions(1) == -1 && directions(2) == 1
    directions = [-1 0];
    useAbs     = true;      % detect on |signal| -- both polarities at once
end

idx = [];
for direction = directions
    % the direction==0 pass in the original is a flat-line search; it can
    % only ever match when there is no threshold, so skip it otherwise
    if direction == 0 && ~isempty(moreThan)
        continue;
    end

    if useAbs
        x = abs(Samples) * direction;
    else
        x = Samples * direction;
    end

    if isempty(moreThan)
        found = LocalMinima(x, refractory);
    else
        found = LocalMinima(x, refractory, -1 * moreThan);
    end
    idx = [idx; found(:)];                                          %#ok<AGROW>
end

TS = ((idx - 1) / SF) + startTime;
