function Generate_Connectivity_Dashboard()
% GENERATE_CONNECTIVITY_DASHBOARD
% Illustrates sliding window mechanics and 3-part metric outputs.
% No parameters required. Generates a 40-second synthetic dataset.

    % 1. Initialization & Synthetic Data Generation
    Fs = 1000;              % 1000 Hz target frequency
    T_total = 40;           % 40 seconds total duration
    t = (0:1/Fs:T_total-1/Fs); 
    
    % Generate low-noise, coupled synthetic signals (8 Hz dominant)
    % Channel 2 amplitude is modulated over time to show dynamic changes
    ch1 = sin(2*pi*8*t) + 0.1*randn(size(t)); 
    ch2 = sin(2*pi*8*t + pi/4) .* (sin(2*pi*0.05*t) + 1.2) + 0.1*randn(size(t));
    
    % 2. System Variables
    winSec = 1.0;           winSamp = round(winSec * Fs);
    stepSec = 0.1;          stepSamp = round(stepSec * Fs);
    maxLagSec = 0.5;        maxLagSamp = round(maxLagSec * Fs);
    low_freq = 4;           high_freq = 12;
    
    coh_wsize = round(winSamp / 2);
    coh_noverlap = round(coh_wsize / 2);
    coh_nfft = Fs;
    
    numWindows = floor((length(ch1) - winSamp) / stepSamp) + 1;
    timeCenters = ((1:numWindows) - 1) * stepSec + (winSec / 2);
    
    % Preallocate output matrices
    Coh_Matrix = zeros(round(coh_nfft/2)+1, numWindows);
    RawCC_Matrix = zeros(2*maxLagSamp + 1, numWindows);
    AmpCC_Matrix = zeros(2*maxLagSamp + 1, numWindows);
    
    % 3. Execute Sliding Window Pipeline
    for w = 1:numWindows
        idxStart = 1 + (w-1)*stepSamp;
        idxEnd = idxStart + winSamp - 1;
        
        s1 = ch1(idxStart:idxEnd);
        s2 = ch2(idxStart:idxEnd);
        
        % Bandpass & Envelope
        f1 = bandpass(s1, [low_freq high_freq], Fs);
        f2 = bandpass(s2, [low_freq high_freq], Fs);
        
        e1 = abs(hilbert(f1)); e1 = e1 - mean(e1);
        e2 = abs(hilbert(f2)); e2 = e2 - mean(e2);
        
        % Compute Metrics
        [C, Freqs] = mscohere(s1, s2, hanning(coh_wsize), coh_noverlap, coh_nfft, Fs);
        Coh_Matrix(:, w) = C;
        
        [rCC, Lags] = xcorr(s1, s2, maxLagSamp, 'coeff');
        RawCC_Matrix(:, w) = rCC;
        
        [aCC, ~] = xcorr(e1, e2, maxLagSamp, 'coeff');
        AmpCC_Matrix(:, w) = aCC;
    end
    Lags_ms = Lags .* (1/Fs) .* 1000;
    
    % 4. Visualization Dashboard
    % Select an arbitrary window in the middle of the dataset to illustrate
    example_w = round(numWindows / 2);
    exStart = 1 + (example_w-1)*stepSamp;
    exEnd = exStart + winSamp - 1;
    t_win = t(exStart:exEnd);
    
    s1_ex = ch1(exStart:exEnd);
    s2_ex = ch2(exStart:exEnd);
    e1_ex = abs(hilbert(bandpass(s1_ex, [low_freq high_freq], Fs))); 
    e1_ex = e1_ex - mean(e1_ex);
    e2_ex = abs(hilbert(bandpass(s2_ex, [low_freq high_freq], Fs))); 
    e2_ex = e2_ex - mean(e2_ex);
    
    figure('Name', 'Connectivity Signal Processing Dashboard', 'Position', [100, 100, 1200, 900]);
    colormap('jet');
    
    % TIER 1: Full 40s Signals
    subplot(4, 3, [1 2 3]);
    plot(t, ch1, 'b', 'DisplayName', 'Ch 1'); hold on;
    plot(t, ch2, 'r', 'DisplayName', 'Ch 2');
    % Highlight the sliding window
    y_limits = ylim;
    patch([t(exStart) t(exEnd) t(exEnd) t(exStart)], [y_limits(1) y_limits(1) y_limits(2) y_limits(2)], ...
        'k', 'FaceAlpha', 0.2, 'EdgeColor', 'none', 'DisplayName', '1s Analysis Window');
    title('TIER 1: Full 40-Second Macro Signals (Showing Sliding Window Location)');
    xlabel('Time (s)'); ylabel('Amplitude'); legend('Location', 'northeast');
    
    % TIER 2: Zoomed Standard Stream
    subplot(4, 3, [4 5 6]);
    plot(t_win, s1_ex, 'b', 'LineWidth', 1.5, 'DisplayName', 'Ch 1 (Standard)'); hold on;
    plot(t_win, s2_ex, 'r', 'LineWidth', 1.5, 'DisplayName', 'Ch 2 (Standard)');
    title('TIER 2: Isolated 1.0s Window -- Standard Broadband Stream');
    xlabel('Time (s)'); ylabel('Amplitude'); legend('Location', 'northeast');
    xlim([t(exStart) t(exEnd)]);
    
    % TIER 3: Zoomed Envelope Stream
    subplot(4, 3, [7 8 9]);
    plot(t_win, e1_ex, 'b', 'LineWidth', 1.5, 'DisplayName', 'Ch 1 (Centered Env)'); hold on;
    plot(t_win, e2_ex, 'r', 'LineWidth', 1.5, 'DisplayName', 'Ch 2 (Centered Env)');
    title('TIER 3: Isolated 1.0s Window -- Narrowband (4-12 Hz) Envelopes (Mean-Centered)');
    xlabel('Time (s)'); ylabel('Amplitude'); legend('Location', 'northeast');
    xlim([t(exStart) t(exEnd)]);
    
    % TIER 4: Final Heatmaps
    % Coherence
    subplot(4, 3, 10);
    imagesc(timeCenters, Freqs, Coh_Matrix);
    axis xy; ylim([0 30]); % Limit to 30 Hz for visibility
    title('Output 1: Dynamic Coherence');
    xlabel('Time (s)'); ylabel('Frequency (Hz)');
    c = colorbar; ylabel(c, 'Magnitude-Squared');
    
    % Raw CC
    subplot(4, 3, 11);
    imagesc(timeCenters, Lags_ms, RawCC_Matrix);
    axis xy;
    title('Output 2: Dynamic Raw CC');
    xlabel('Time (s)'); ylabel('Lag (ms)');
    c = colorbar; ylabel(c, 'Correlation (r)');
    
    % Amp CC
    subplot(4, 3, 12);
    imagesc(timeCenters, Lags_ms, AmpCC_Matrix);
    axis xy;
    title('Output 3: Dynamic Amp CC');
    xlabel('Time (s)'); ylabel('Lag (ms)');
    c = colorbar; ylabel(c, 'Correlation (r)');
    
    sgtitle('Dynamic Functional Connectivity: Signal Processing Pipeline Dashboard', 'FontSize', 16, 'FontWeight', 'bold');
end