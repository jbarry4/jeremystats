function [p, t, fRaw, maxs] = xf_maxFreqInTime(Samples, SF, minf, maxf, frame_length, frame_overlap)
%XF_MAXFREQINTIME  Dominant-frequency ridge -- Analyse mode 6, 'max freq in time'.
%
%   [P, T, FRAW, MAXS] = xf_maxFreqInTime(SAMPLES, SF, MINF, MAXF, FRAME_LENGTH, FRAME_OVERLAP)
%
%   Computes the STFT (band-limited to [MINF MAXF]), takes the frequency of
%   the strongest bin in each time frame, and low-pass smooths that track.
%
%   P      smoothed ridge frequency per frame, Hz          -- what the GUI plots
%   T      frame centre times, s, relative to SAMPLES start
%   FRAW   unsmoothed ridge frequency per frame, Hz
%   MAXS   dB magnitude at the ridge -- the GUI uses this to colour the
%          scatter overlay, so weak/unreliable frames are visibly different
%
%   Smoothing is a 2nd-order Chebyshev type II low-pass, 20 dB stopband
%   attenuation, cutoff 0.1 x Nyquist OF THE FRAME RATE (not of SF), applied
%   zero-phase with filtfilt:
%
%       [b,a] = cheby2(2,20,0.1,'low');   p = filtfilt(b,a,f);
%
%   NOTE  The ridge is the argmax over the band, so if MINF/MAXF straddle a
%   1/f-dominated low edge the track will pin to MINF.  Set MINF above the
%   DC roll-off (the GUI default band is 0-200 Hz, which does pin) for this
%   mode to say anything useful.
%
%   Extracted from xplorefinder.m update_graph, case {1,5,6} / typenlyz==6.
%   The original also contains commented-out experiments -- a NaN-and-reinterp
%   pass for weak frames, a Hilbert phase of the ridge derivative, and a
%   plotyy against MAXS.  Those are left out here; see gui/xplorefinder.m
%   around line 1424 if you want them back.
%
%   See also XF_SPECTROGRAM, XF_ANALYSE, CHEBY2, FILTFILT.

if nargin < 5, frame_length  = 0; end
if nargin < 6, frame_overlap = 0; end

[frame_length, frame_overlap] = ...
    xf_frameDefaults(size(Samples,1), SF, frame_length, frame_overlap);

windows = 'hamming';
[S, f, t] = spStft(Samples, windows, frame_overlap, frame_length, SF);

band = xf_band(f, minf, maxf);
S    = S(band, :);
f    = f(band);

S = 30 * log10(abs(S));

[maxs, maxid] = max(S);             % max over frequency, per time frame
fRaw = f(maxid);

[b, a] = cheby2(2, 20, 0.1, 'low');
p = filtfilt(b, a, fRaw);
