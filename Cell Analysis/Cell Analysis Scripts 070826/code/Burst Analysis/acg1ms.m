
function [lags_ms, acg] = acg1ms(spike_times_s, maxlag_ms)
% acg1ms  Autocorrelogram with 1-ms bins up to maxlag_ms (default 100 ms).
%
% INPUT
%   spike_times_s : spike times in seconds
%   maxlag_ms     : positive scalar (default 100)
%
% OUTPUT
%   lags_ms : bin centers in ms, symmetric from -maxlag_ms .. +maxlag_ms (excluding 0 bin by convention)
%   acg     : counts per bin
%
if nargin<2 || isempty(maxlag_ms), maxlag_ms = 100; end
st = spike_times_s(:);
if numel(st)<2
    lags_ms = (-maxlag_ms:maxlag_ms)';
    acg = zeros(size(lags_ms));
    return;
end

bin_ms = 1;
edges_ms = -maxlag_ms - 0.5 : bin_ms : maxlag_ms + 0.5;
lags_ms = (-maxlag_ms:maxlag_ms).';
acg = zeros(size(lags_ms));

% Compute all pairwise lags within window efficiently
% Use convolution-style trick: build time differences within a sliding window.
% For simplicity/clarity, do a two-pointer approach.
st_ms = st*1e3;
N = numel(st_ms);
j1 = 1;
for i = 1:N
    % Move j1 to maintain lower bound
    while (st_ms(i) - st_ms(j1)) > maxlag_ms, j1 = j1 + 1; end
    % Find upper bound j2
    j2 = i;
    while (j2 <= N) && (st_ms(j2) - st_ms(i) <= maxlag_ms), j2 = j2 + 1; end
    if j2 - j1 <= 1, continue; end
    lags = [st_ms(j1:i-1) - st_ms(i); st_ms(i) - st_ms(i+1:j2-1)];
    % Bin
    acg = acg + histcounts(lags, edges_ms).';
end
