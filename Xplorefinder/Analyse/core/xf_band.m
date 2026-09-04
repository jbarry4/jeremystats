function mask = xf_band(F, minf, maxf)
%XF_BAND  Logical mask selecting the displayed frequency band.
%
%   MASK = xf_band(F, MINF, MAXF) is F >= MINF & F <= MAXF.
%
%   xplorefinder writes this comparison inline dozens of times as
%   logical(F>=...nlyzminf & F<=...nlyzmaxf); this is the same thing, once.

mask = F >= minf & F <= maxf;
