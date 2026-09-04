function [C, phi, f, phistd, confC, Cerr, S12, S1, S2] = xf_coherency(Samples1, Samples2, SF, minf, maxf, segLength)
%XF_COHERENCY  Segmented multitaper coherency -- Analyse mode 8, 'coherency...'.
%
%   [C, PHI, F, PHISTD, CONFC, CERR, S12, S1, S2] = ...
%       xf_coherency(SAMPLES1, SAMPLES2, SF, MINF, MAXF, SEGLENGTH)
%
%   C        magnitude coherency vs frequency (0..1)
%   PHI      coherency phase vs frequency, radians
%   F        frequencies, Hz (cropped to [MINF MAXF] by params.fpass)
%   PHISTD   standard deviation of PHI -- the GUI plots this on the right
%            y-axis against C on the left, so you can see where a high
%            coherency is actually phase-stable
%   CONFC    confidence level for C at the requested p
%   CERR     jackknife error bars on C
%   S12,S1,S2  cross- and auto-spectra
%
%   SEGLENGTH is the segment length in SECONDS (chronux coherencysegc's
%   third argument).  Defaults to 2, which is what the GUI hardcodes.
%   The record is chopped into SEGLENGTH segments and averaged
%   (params.segave=1, params.trialave=1) -- that averaging is what makes
%   this different from a single-shot coherencyc on the whole window.
%
%   NOTE  The GUI sets params.err=[2 3].  Chronux reads err(2) as a
%   p-value, so 3 is nonsensical; treat CONFC/CERR from the default call
%   with suspicion and pass your own params if you need trustworthy error
%   bars.  Kept as-is for GUI fidelity -- see xf_chronuxParams.
%
%   NOTE  xplorefinder.m also contains a commented-out coherencyc call (no
%   segmentation) immediately below the live coherencysegc line, if you
%   want the unsegmented version.
%
%   Extracted from xplorefinder.m eegcorrelation, nlyztype==8.
%
%   See also XF_SPECGRAMDIFF, XF_CHRONUXPARAMS, COHERENCYSEGC, COHERENCYC.

if nargin < 6 || isempty(segLength), segLength = 2; end

params = xf_chronuxParams(SF, minf, maxf, true);

[C, phi, S12, S1, S2, f, confC, phistd, Cerr] = ...
    coherencysegc(Samples1, Samples2, segLength, params);
