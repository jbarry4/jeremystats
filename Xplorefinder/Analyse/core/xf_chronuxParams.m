function params = xf_chronuxParams(SF, minf, maxf, withErr)
%XF_CHRONUXPARAMS  Chronux params struct as xplorefinder builds it.
%
%   PARAMS = xf_chronuxParams(SF, MINF, MAXF)
%   PARAMS = xf_chronuxParams(SF, MINF, MAXF, true)   % adds err/trialave/segave
%
%   Fields, verbatim from xplorefinder.m:
%       tapers  = [3 5]     time-bandwidth product 3, 5 tapers
%       Fs      = SF
%       pad     = 0         pad to the next power of 2
%       fpass   = [MINF MAXF]
%
%   With WITHERR true (the coherency path, eegcorrelation nlyztype==8) it
%   also sets err=[2 3] (jackknife, p=3?? -- chronux reads err(2) as the
%   p-value, so 3 is out of range and coherr falls back on its default
%   behaviour), trialave=1 and segave=1.
%
%   NOTE  tapers=[3 5] with fpass cropping is the reason the chronux modes
%   look much smoother than the plain STFT modes: 5 Slepian tapers are
%   averaged per frame.
%
%   See also XF_CHRONUXSPECGRAM, XF_COHERENCY, GETPARAMS.

if nargin < 4 || isempty(withErr), withErr = false; end

params.tapers = [3 5];
params.Fs     = SF;
params.pad    = 0;
params.fpass  = [minf maxf];

if withErr
    params.err      = [2 3];
    params.trialave = 1;
    params.segave   = 1;
end
