function [SdB, F, T] = xf_spectrogram(Samples, SF, minf, maxf, frame_length, frame_overlap)
%XF_SPECTROGRAM  STFT spectrogram -- xplorefinder Analyse mode 1, 'Spectogram'.
%
%   [SDB, F, T] = xf_spectrogram(SAMPLES, SF, MINF, MAXF, FRAME_LENGTH, FRAME_OVERLAP)
%
%   SAMPLES        column vector of EEG samples (one displayed window)
%   SF             sampling frequency of SAMPLES, Hz (Cscfile2_PP.currentSF)
%   MINF, MAXF     displayed frequency band, Hz (GUI: nlyzminf / nlyzmaxf)
%   FRAME_LENGTH   STFT frame length, ms; 0 or omitted = default
%   FRAME_OVERLAP  STFT frame overlap, ms; 0 or omitted = default
%
%   SDB  power in dB, already cropped to [MINF MAXF], size numel(F) x numel(T)
%   F    frequencies inside the band, Hz
%   T    frame centre times in seconds, RELATIVE to the start of SAMPLES.
%        The GUI plots at T + Data.start to put it back on the recording clock.
%
%   Extracted verbatim from xplorefinder.m update_graph, case {1,5,6} /
%   typenlyz==1.  Windowing is always hamming (the 'rectwin' alternative is
%   commented out in the original).
%
%   NOTE  The dB conversion is 30*log10(abs(S)), NOT the conventional
%   20*log10 (amplitude) or 10*log10 (power).  This is what the GUI has
%   always used, so absolute dB numbers are not comparable to other tools --
%   only relative structure within a plot is meaningful.  Preserved so
%   output matches the GUI exactly.
%
%   See also XF_ANALYSE, XF_CHRONUXSPECGRAM, SPSTFT.

if nargin < 5, frame_length  = 0; end
if nargin < 6, frame_overlap = 0; end

[frame_length, frame_overlap] = ...
    xf_frameDefaults(size(Samples,1), SF, frame_length, frame_overlap);

windows = 'hamming';
[S, F, T] = spStft(Samples, windows, frame_overlap, frame_length, SF);

SdB = 30 * log10(abs(S));           % dB (see NOTE above)

band = xf_band(F, minf, maxf);
SdB  = SdB(band, :);
F    = F(band);
