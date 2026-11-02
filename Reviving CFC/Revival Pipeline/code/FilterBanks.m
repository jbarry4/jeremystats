function bank = FilterBanks(sig, P)
%FILTERBANKS  The two parfor loops from newFCSE.m, on the whole trace.
%
%   bank = FilterBanks(sig, P)
%
%   Same arithmetic as step04_newFCSE.m: eegfilt (EEGLAB firls + filtfilt,
%   zero phase) then Hilbert. Filtering the WHOLE trace once and cutting it
%   into epochs afterwards is the point -- it avoids 300 separate filter
%   transients, and filtfilt on a 6 s block with a 2441-tap filter would be
%   mostly edge effect.
%
%   Returns
%     bank.Phase    nSlow x T   phase of each slow band, radians in (-pi, pi]
%     bank.Amp      nFast x T   amplitude envelope of each fast band
%     bank.SlowEnv  nSlow x T   envelope of each SLOW band (ThetaPower uses it)
%     bank.taps     filter length actually used per band
%
%   Memory: at 3255 Hz for 30 minutes, T = 5.86e6 and the three matrices are
%   about 1.7 GB in single, 3.4 GB in double. P.store = 'single' by default.
%   Everything is computed in double and cast on the way out.

if nargin < 2, P = params(); end

T  = sig.T;
fs = sig.fs;
lfp = sig.lfp;                       % 1 x T double, eegfilt wants a row

nSlow = P.nSlow;  nFast = P.nFast;

Phase   = zeros(nSlow, T, P.store);
SlowEnv = zeros(nSlow, T, P.store);
Amp     = zeros(nFast, T, P.store);
tapsSlow = zeros(nSlow, 1);
tapsFast = zeros(nFast, 1);

slowVec = P.slowVec;  slowBW = P.slowBW;
fastVec = P.fastVec;  fastBW = P.fastBW;
store   = P.store;

fprintf('FilterBanks: %d slow bands (%g-%g Hz) + %d fast bands (%g-%g Hz)\n', ...
        nSlow, slowVec(1), slowVec(end)+slowBW, ...
        nFast, fastVec(1), fastVec(end)+fastBW);

% ---- slow bank: phase AND envelope from one analytic signal ------------
tic;
parfor j = 1:nSlow
    f1 = slowVec(j);
    y  = eegfilt(lfp, fs, f1, f1 + slowBW);
    h  = hilbert(y')';
    Phase(j, :)   = cast(angle(h), store);
    SlowEnv(j, :) = cast(abs(h),   store);
    tapsSlow(j)   = 3 * fix(fs / f1);
end
fprintf('   slow bank: %.1f s   (longest filter %d taps at %g Hz)\n', ...
        toc, max(tapsSlow), slowVec(1));

% ---- fast bank: envelope only ------------------------------------------
tic;
parfor i = 1:nFast
    f1 = fastVec(i);
    y  = eegfilt(lfp, fs, f1, f1 + fastBW);
    Amp(i, :)   = cast(abs(hilbert(y')'), store);
    tapsFast(i) = 3 * fix(fs / f1);
end
fprintf('   fast bank: %.1f s   (%d taps at %g Hz down to %d at %g Hz)\n', ...
        toc, tapsFast(1), fastVec(1), tapsFast(end), fastVec(end));

bank = struct();
bank.Phase    = Phase;
bank.Amp      = Amp;
bank.SlowEnv  = SlowEnv;
bank.tapsSlow = tapsSlow;
bank.tapsFast = tapsFast;
bank.fs       = fs;

% The longest filter sets how far into the trace edge effects reach.
bank.edgeSamples = max([tapsSlow; tapsFast]);
bank.edgeSec     = bank.edgeSamples / fs;
fprintf('   filter-safe margin: %.2f s at each end (%d samples)\n', ...
        bank.edgeSec, bank.edgeSamples);
end
