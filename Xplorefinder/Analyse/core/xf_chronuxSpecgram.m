function [SdB, f, t] = xf_chronuxSpecgram(Samples, SF, minf, maxf, frame_length, frame_overlap)
%XF_CHRONUXSPECGRAM  Multitaper spectrogram -- Analyse mode 5, 'chronus spectogram'.
%
%   [SDB, F, T] = xf_chronuxSpecgram(SAMPLES, SF, MINF, MAXF, FRAME_LENGTH, FRAME_OVERLAP)
%
%   Same inputs as XF_SPECTROGRAM.  FRAME_LENGTH / FRAME_OVERLAP are in ms
%   and are converted to the chronux movingwin = [win step] in SECONDS as
%
%       movingwin = [frame_length*1E-3  (frame_length-frame_overlap)*1E-3]
%
%   so the step is the non-overlapping part of the frame.
%
%   SDB is returned in chronux orientation: numel(T) x numel(F), i.e. TIME
%   DOWN THE ROWS.  This is the transpose of what XF_SPECTROGRAM returns.
%   The GUI plots it as pcolor(t+start, f, S') -- note the transpose.
%   XF_PLOTANALYSE handles this for you.
%
%   Cropping to [MINF MAXF] is done by chronux itself via params.fpass, so
%   F already spans only the requested band.
%
%   Extracted from xplorefinder.m update_graph, case {1,5,6} / else-branch
%   with typenlyz==5.  Same 30*log10 caveat as XF_SPECTROGRAM.
%
%   See also XF_SPECTROGRAM, XF_CHRONUXPARAMS, MTSPECGRAMC.

if nargin < 5, frame_length  = 0; end
if nargin < 6, frame_overlap = 0; end

[frame_length, frame_overlap] = ...
    xf_frameDefaults(size(Samples,1), SF, frame_length, frame_overlap);

params    = xf_chronuxParams(SF, minf, maxf);
movingwin = [frame_length*1E-3  (frame_length-frame_overlap)*1E-3];

[S, t, f] = mtspecgramc(Samples, movingwin, params);

SdB = 30 * log10(abs(S));           % time x freq (chronux orientation)
