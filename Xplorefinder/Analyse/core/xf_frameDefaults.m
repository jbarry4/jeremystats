function [frame_length, frame_overlap] = xf_frameDefaults(nSamples, SF, frame_length, frame_overlap)
%XF_FRAMEDEFAULTS  Resolve STFT frame length / overlap the way xplorefinder does.
%
%   [FL, FO] = xf_frameDefaults(NSAMPLES, SF, FRAME_LENGTH, FRAME_OVERLAP)
%
%   A value of 0 (or []) for FRAME_LENGTH / FRAME_OVERLAP means "use the
%   default", exactly as the GUI stores it in Data.xtraFileData(i).
%
%   Both returned values are in MILLISECONDS (spStft expects ms).
%
%   Defaults, verbatim from xplorefinder.m update_graph, case {1,5,6}:
%       frame_length  = (1/SF)*nSamples*100          % = 100/SF * nSamples ms
%       frame_overlap = ((1/SF)*nSamples*100)/1.02
%
%   NOTE  The setup dialog (popmenunlyztypecallback, case 1) advertises the
%   default overlap as frame_length/1.2, but the drawing code divides by
%   1.02.  The 1.02 value is what actually renders; the prompt text is
%   stale.  Kept as-is so output matches the GUI.
%
%   See also XF_ANALYSE, SPSTFT.

if nargin < 3, frame_length  = 0; end
if nargin < 4, frame_overlap = 0; end

defaultLen = (1/SF) * nSamples * 100;   % ms

if isempty(frame_length) || frame_length == 0
    frame_length = defaultLen;
end
if isempty(frame_overlap) || frame_overlap == 0
    frame_overlap = defaultLen / 1.02;
end
