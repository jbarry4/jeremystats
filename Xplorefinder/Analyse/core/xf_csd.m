function [csd, tSec, chan] = xf_csd(D, SF, startTime)
%XF_CSD  Current source density across a channel stack -- the GUI's live CSD view.
%
%   [CSD, TSEC, CHAN] = xf_csd(D, SF, STARTTIME)
%
%   D          samples x channels matrix, channels in PHYSICAL DEPTH ORDER
%              (that ordering is what makes the second spatial derivative
%              meaningful -- see NOTE)
%   SF         sampling frequency, Hz
%   STARTTIME  recording time of D(1,:), s.  Added to TSEC.
%
%   CSD   time x channel CSD estimate, straight from CSDPP2
%   TSEC  time axis in SECONDS on the recording clock.  CSDPP2 returns
%         microseconds; this converts (newtrange*1E-6) and adds STARTTIME,
%         as the GUI does.
%   CHAN  channel index axis returned by CSDPP2 (interior channels only --
%         a second derivative loses the outermost channel on each side)
%
%   D is normalised by its global maximum before the derivative:
%   D = D./max(max(D)), exactly as the GUI does.  That is a single scalar
%   for the whole block, so relative channel amplitudes are preserved.
%
%   To plot it the way the GUI does:
%       pcolor(TSEC, CHAN, CSD');  shading interp;  set(gca,'YDir','rev')
%       cxmax = max(abs(caxis));   caxis([-cxmax cxmax]);
%
%   NOTE  The GUI builds D as
%       d = zeros(nSamples, numel(ncsFileMask));   d(:,i) = ...   for i = find(ncsFileMask)
%   -- sized by the TOTAL number of open files and indexed by the GLOBAL
%   file index.  So if a .ntt/.nvt/.nev is open anywhere in the list, its
%   slot stays an all-zero column and is fed to CSDPP2 as a flat channel,
%   corrupting the derivative at its neighbours.  This function takes D
%   directly so you can pass only the real channels; build it yourself as
%   D = [f(1).Samples, f(2).Samples, ...] over the .ncs files in depth order.
%
%   NOTE  CSDPP2 is called with 'd' and computes the CSD without the sign
%   inversion of the standard formulation ("my version of CSD (no
%   inversion)" in the original) -- so the sign convention for
%   source/sink is opposite to most published CSD figures.
%
%   Extracted from xplorefinder.m Csdview.
%
%   See also CSDPP2.

if nargin < 3 || isempty(startTime), startTime = 0; end

D = D ./ max(max(D));

[csd, newtrange, chan] = CSDPP2(D, 'd', SF);

tSec = startTime + (newtrange * 1E-6);
