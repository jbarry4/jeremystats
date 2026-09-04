function [SdBdiff, corrCoef, F, T] = xf_specgramDiff(Samples1, Samples2, SF, minf, maxf, method, frame_length, frame_overlap)
%XF_SPECGRAMDIFF  Spectrogram difference between two channels -- Analyse modes 4 and 7.
%
%   [SDBDIFF, CORRCOEF, F, T] = xf_specgramDiff(SAMPLES1, SAMPLES2, SF, ...
%                                   MINF, MAXF, METHOD, FRAME_LENGTH, FRAME_OVERLAP)
%
%   METHOD selects which spectrogram engine is used, and that is the ONLY
%   difference between the two GUI modes:
%       'chronux'  multitaper via mtspecgramc  -- mode 4, 'Correlation...'
%       'stft'     hamming STFT via spStft     -- mode 7, 'Correlation classic...'
%
%   SDBDIFF   abs(SdB1 - SdB2), always returned as numel(F) x numel(T)
%             (frequency down the rows) regardless of METHOD
%   CORRCOEF  corr2(SdB1, SdB2) -- a SINGLE scalar 2-D correlation between
%             the two whole dB spectrograms.  The GUI shows it in the y-label.
%   F, T      band-limited frequencies (Hz) and frame times (s, relative to
%             the start of SAMPLES1)
%
%   Both channels must be sampled at SF and cover the same time window --
%   that is guaranteed inside the GUI because every Cscfile2_PP is read with
%   the same start/range, but it is your responsibility when calling this
%   directly.  Mismatched lengths will either error in corr2 or silently
%   compare different times.
%
%   NOTE  Despite the mode names, this is not a per-frequency or
%   per-time correlation -- it is one global corr2 plus a difference IMAGE.
%   The picture is the difference; the correlation is a single number.
%
%   NOTE  corr2 requires the Image Processing Toolbox.  If you do not have
%   it, corrcoef(SdB1(:),SdB2(:)) gives the same value in element (1,2).
%
%   Extracted from xplorefinder.m eegcorrelation, nlyztype 4 and 7.  In the
%   GUI the second channel is chosen by a listdlg and stored in
%   Data.xtraFileData(i).correlationeeg.
%
%   See also XF_SPECTROGRAM, XF_CHRONUXSPECGRAM, XF_COHERENCY, CORR2.

if nargin < 6 || isempty(method), method = 'chronux'; end
if nargin < 7, frame_length  = 0; end
if nargin < 8, frame_overlap = 0; end

switch lower(method)
    case 'stft'
        % mode 7 -- both channels through spStft, then band-crop
        [SdB1, F, T] = xf_spectrogram(Samples1, SF, minf, maxf, frame_length, frame_overlap);
        SdB2         = xf_spectrogram(Samples2, SF, minf, maxf, frame_length, frame_overlap);
        % both already freq x time and band-cropped

    case 'chronux'
        % mode 4 -- both channels through mtspecgramc (fpass does the crop)
        [SdB1, F, T] = xf_chronuxSpecgram(Samples1, SF, minf, maxf, frame_length, frame_overlap);
        SdB2         = xf_chronuxSpecgram(Samples2, SF, minf, maxf, frame_length, frame_overlap);
        SdB1 = SdB1.';                  % time x freq -> freq x time
        SdB2 = SdB2.';

    otherwise
        error('xf_specgramDiff:badMethod', ...
              'METHOD must be ''chronux'' (mode 4) or ''stft'' (mode 7), got ''%s''.', method);
end

if ~isequal(size(SdB1), size(SdB2))
    error('xf_specgramDiff:sizeMismatch', ...
          ['Spectrograms differ in size (%dx%d vs %dx%d). ', ...
           'The two channels must have the same sampling rate and the same ', ...
           'number of samples.'], size(SdB1,1), size(SdB1,2), size(SdB2,1), size(SdB2,2));
end

corrCoef = corr2(SdB1, SdB2);
SdBdiff  = abs(SdB1 - SdB2);
