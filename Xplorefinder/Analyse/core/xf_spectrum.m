function [Y, f] = xf_spectrum(Samples, SF, minf, maxf, useDiff)
%XF_SPECTRUM  Welch power spectrum -- xplorefinder Analyse modes 2 and 3.
%
%   [Y, F] = xf_spectrum(SAMPLES, SF, MINF, MAXF)          % mode 2, 'Spectrum'
%   [Y, F] = xf_spectrum(SAMPLES, SF, MINF, MAXF, true)    % mode 3, 'Diff Spectrum'
%
%   With USEDIFF true the spectrum is taken of diff(SAMPLES) rather than
%   SAMPLES -- a crude first-derivative pre-whitening that tilts the
%   spectrum up by ~6 dB/octave and suppresses the 1/f slope, making
%   higher-frequency peaks easier to see.
%
%   Y is returned on pwelch's native scale (linear PSD).  The GUI plots it
%   raw -- plot(f,Y) -- and only restricts the x-axis to [MINF MAXF]; it does
%   not crop the data, so F here spans 0..SF/2 as pwelch returns it.
%
%   Window length and NFFT come from xf_pwelchWindow, which scales them to
%   MAXF so the curve stays smooth as you zoom the frequency axis.
%
%   Extracted from xplorefinder.m update_graph, case {2,3}.
%
%   See also XF_PWELCHWINDOW, XF_ANALYSE, PWELCH.

if nargin < 5 || isempty(useDiff), useDiff = false; end

nSamples = size(Samples,1);
[window, res] = xf_pwelchWindow(nSamples, SF, minf, maxf);

nfft    = round(SF / res);
noverl  = round(window / 2);

if useDiff
    [Y, f] = pwelch(diff(Samples), window, noverl, nfft, SF);
else
    [Y, f] = pwelch(Samples,       window, noverl, nfft, SF);
end
