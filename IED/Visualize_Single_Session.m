function Visualize_Single_Session(csvPath)
% Visualize_Single_Session
% Reads a single Voltage Raster CSV and plots it.
% Useful for debugging specific sessions (e.g., m5s7).
%
% Usage:
%   Visualize_Single_Session('path/to/VoltageRaster_Avg_Values_SOLID.csv')

    if nargin < 1 || ~isfile(csvPath)
        [f, p] = uigetfile('*.csv', 'Select Voltage Raster CSV');
        if isequal(f,0), return; end
        csvPath = fullfile(p, f);
    end

    fprintf('Loading: %s\n', csvPath);
    
    % 1. Read Data
    try
        T = readtable(csvPath);
    catch ME
        error('Failed to read CSV: %s', ME.message);
    end
    
    if width(T) < 2
        error('CSV has insufficient columns. Check file format.');
    end
    
    % 2. Parse Channel Labels
    % Assume first column is 'Channel'
    chanLabels = T{:, 1};
    if isnumeric(chanLabels)
        chanLabels = arrayfun(@(x) sprintf('Ch %d', x), chanLabels, 'UniformOutput', false);
    end
    
    % 3. Extract Voltage Data
    dataCols = T{:, 2:end};
    
    % 4. Parse Time Vector from Headers
    headers = T.Properties.VariableNames(2:end);
    tRelMs = parseTimeHeaders(headers);
    
    % 5. Check for NaNs / Zeros
    nNan = sum(isnan(dataCols(:)));
    nZero = sum(dataCols(:) == 0);
    fprintf('Data Stats:\n');
    fprintf('  Rows: %d, TimePoints: %d\n', size(dataCols));
    fprintf('  NaNs: %d (%.1f%%)\n', nNan, 100*nNan/numel(dataCols));
    fprintf('  Zeros: %d (%.1f%%)\n', nZero, 100*nZero/numel(dataCols));
    fprintf('  Min Val: %.2f uV\n', min(dataCols(:), [], 'omitnan'));
    fprintf('  Max Val: %.2f uV\n', max(dataCols(:), [], 'omitnan'));

    % 6. Plot
    f = figure('Color','w','Position',[200 200 1000 800]);
    
    % Auto-Scale Color (Robust)
    vals = abs(dataCols(:));
    vals = vals(isfinite(vals));
    if isempty(vals)
        clim = 100;
    else
        clim = prctile(vals, 99.5) * 1.1;
    end
    
    imagesc(tRelMs, 1:length(chanLabels), dataCols);
    set(gca, 'YDir', 'reverse');
    colormap(jet);
    colorbar;
    caxis([-clim clim]);
    
    % Formatting
    xlabel('Time (ms)');
    ylabel('Channel');
    yticks(1:length(chanLabels));
    yticklabels(chanLabels);
    set(gca, 'FontSize', 8, 'TickLabelInterpreter', 'none');
    
    [~, fname, ~] = fileparts(csvPath);
    title(sprintf('%s (CLim = +/- %.1f)', fname, clim), 'Interpreter', 'none');
    
    fprintf('Plot generated.\n');
end

% Helper to parse headers like "T_minus20p0ms"
function tVals = parseTimeHeaders(headers)
    tVals = zeros(1, numel(headers));
    for i = 1:numel(headers)
        h = headers{i};
        h = strrep(h, 'T_', ''); h = strrep(h, 'ms', '');
        h = strrep(h, 'minus', '-'); h = strrep(h, 'm', '-');
        h = strrep(h, 'p', '.'); h = strrep(h, '_', '.');
        val = str2double(regexprep(h, '[^0-9\.\-]', ''));
        if isnan(val), val = 0; end
        tVals(i) = val;
    end
end