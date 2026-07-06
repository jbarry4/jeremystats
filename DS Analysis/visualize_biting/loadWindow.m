function seg = loadWindow(fn, t0_us, t1_us, sfx, ADBitVolts, invertPolarity, nSamp)
% loadWindow  Load a uV window from a Neuralynx NCS file via timestamp range.
% Uses Nlx2MatCSC extract mode 4 (timestamp range) to avoid loading full files.
    seg = zeros(1, nSamp, 'single');
    try
        % Nlx2MatCSC returns one output per selected field: [1 0 0 1 1]
        % -> Timestamps, NumberOfValidSamples, Samples (3 outputs).
        [rec_ts, numValid, samples] = ...
            Nlx2MatCSC(fn, [1 0 0 1 1], 0, 4, [t0_us, t1_us]);
    catch err
        warning('loadWindow:nlxFail', 'Nlx2MatCSC failed for %s: %s', fn, err.message);
        return;
    end
    if isempty(rec_ts), return; end
    spu    = sfx / 1e6;
    recLen = size(samples, 1);
    for r = 1:numel(rec_ts)
        vCount = min(recLen, numValid(r));
        if vCount < 1, continue; end
        s = double(samples(1:vCount, r));
        if invertPolarity, s = -s; end
        s  = single(s .* (ADBitVolts * 1e6));
        iS = round((double(rec_ts(r)) - t0_us) * spu) + 1;
        iE = iS + vCount - 1;
        wS = max(1, iS);           wE = min(nSamp, iE);
        dS = max(1, 1-(iS-1));     dE = vCount - max(0, iE-nSamp);
        if wS > wE || dS > dE, continue; end
        seg(wS:wE) = s(dS:dE);
    end
end
