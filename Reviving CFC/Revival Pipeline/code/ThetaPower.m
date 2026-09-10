function Pw = ThetaPower(bank, ep, P)
%THETAPOWER  Mean band power per epoch, for each of the slow bands.
%
%   Pw = ThetaPower(bank, ep, P)
%
%   Pw   nSlow x nEp   double, microvolts^2
%
%   Power is the mean squared envelope of the SAME analytic signal whose
%   phase drove the modulation index. That is the point of computing it here
%   rather than with a periodogram: no new filtering, no second definition of
%   "theta", and MI and power are guaranteed to be talking about the same
%   band and the same samples.
%
%   Output C -- theta power against MI, one panel per slow band -- depends on
%   Pw and MI being indexed the same way. Gate 7 asserts that.

if nargin < 3, P = params(); end

nEp   = height(ep);
nSlow = size(bank.SlowEnv, 1);
Pw    = zeros(nSlow, nEp);

i0 = ep.i0;  i1 = ep.i1;
for e = 1:nEp
    seg     = double(bank.SlowEnv(:, i0(e):i1(e)));
    Pw(:, e) = mean(seg.^2, 2);
end

fprintf('ThetaPower: %d slow bands x %d epochs\n', nSlow, nEp);
[~, kPeak] = max(mean(Pw, 2));
fprintf('   strongest band on average: %.2f Hz (%.1f uV^2)\n', ...
        P.slowCenters(kPeak), mean(Pw(kPeak, :)));
end
