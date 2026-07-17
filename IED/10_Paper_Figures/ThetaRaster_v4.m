function ThetaRaster_v4()
% ThetaRaster_v4 — hard-coded batch re-run of the theta raster analysis.
% -------------------------------------------------------------------------
% - Walks a fixed list of IED-_PTEN_* session folders (under "Take 3").
% - Processes EVERY .fig in each folder (all are theta; names vary).
% - Opens each figure (invisible), extracts x1/y1/c1 (JB style).
% - Computes MeanPositive / MeanNegative (same math as ThetaRaster.m).
% - Saves x1,y1,c1 + means as .mat into the SAME session folder.
% - Renders a clean heatmap and writes a PDF + PNG into the SAME folder,
%   named after each source .fig so multiple figs don't collide.
% -------------------------------------------------------------------------

    % ---------- Hard-coded inputs ----------
    rootDir = 'C:\Users\Z390\Desktop\IED DATA\Take 3';

    sessionFolders = { ...
        'IED-_PTEN_M10s4', ...
        'IED-_PTEN_M11s10', ...
        'IED-_PTEN_M1s2', ...
        'IED-_PTEN_M29s1', ...
        'IED-_PTEN_M30s1', ...
        'IED-_PTEN_M33s4', ...
        'IED-_PTEN_M7s2', ...
        'IED-_PTEN_M8s2' ...
    };

    fprintf('\n===== ThetaRaster_v4: %d sessions =====\n', numel(sessionFolders));

    for i = 1:numel(sessionFolders)
        folder = fullfile(rootDir, sessionFolders{i});
        fprintf('\n--- %s ---\n', sessionFolders{i});

        figs = dir(fullfile(folder, '*.fig'));
        if isempty(figs)
            fprintf(2, '  No .fig files found in: %s\n', folder);
            continue;
        end

        for k = 1:numel(figs)
            figPath = fullfile(figs(k).folder, figs(k).name);
            try
                processOne(figPath);
            catch ME
                fprintf(2, '  !!! ERROR on %s:\n      %s\n', figs(k).name, ME.message);
            end
        end
    end

    fprintf('\n===== ThetaRaster_v4 done =====\n\n');
end


function processOne(figPath)
    [folder, stem, ~] = fileparts(figPath);
    fprintf('  Opening (invisible): %s\n', figPath);

    % ---------- Open invisible + extract data (JB snippet style) ----------
    srcFig = openfig(figPath, 'invisible');

    obj = findobj(srcFig, '-property', 'CData');  c1 = obj(1).CData;
    obj = findobj(srcFig, '-property', 'XData');  x1 = obj(1).XData;
    obj = findobj(srcFig, '-property', 'YData');  y1 = obj(1).YData;

    x1 = x1(:).';  % row vectors
    y1 = y1(:).';

    fprintf('  Extracted -> x1:%d | y1:%d | c1:%dx%d\n', ...
        numel(x1), numel(y1), size(c1,1), size(c1,2));

    close(srcFig);

    % ---------- Positive / negative means (unchanged math) ----------
    c2 = c1;  Positive = c2 > 0;  c2(~Positive) = 0;
    MeanPositive = sum(c2, 2) ./ sum(Positive, 2);

    c3 = c1;  Negative = c3 < 0;  c3(~Negative) = 0;
    MeanNegative = sum(c3, 2) ./ sum(Negative, 2);

    % ---------- Save mats into the SAME folder (named after the .fig) ----------
    save(fullfile(folder, [stem '_x1.mat']),           'x1');
    save(fullfile(folder, [stem '_y1.mat']),           'y1');
    save(fullfile(folder, [stem '_c1.mat']),           'c1');
    save(fullfile(folder, [stem '_MeanPositive.mat']), 'MeanPositive');
    save(fullfile(folder, [stem '_MeanNegative.mat']), 'MeanNegative');

    % ---------- Render heatmap -> PDF + PNG into the SAME folder ----------
    pngPath = fullfile(folder, [stem '_Raster.png']);
    pdfPath = fullfile(folder, [stem '_Raster.pdf']);
    renderThetaRaster(x1, y1, c1, pngPath, pdfPath);

    fprintf('  Wrote:\n    %s\n    %s\n', pngPath, pdfPath);
end


function renderThetaRaster(xValues, yValues, cMatrix, pngPath, pdfPath)
% Invisible figure -> PNG + PDF, then close. Same look as ThetaRaster.m.

    % ---- simple knobs ----
    gaussianSigma  = 0.75;
    upsampleFactor = 3;
    colormapName   = 'jet';
    colorScale     = [-0.2, 0.2];
    titleText      = 'Theta-Ripple Heatmap - Channel 64 at Bottom';

    % ---- orientation check ----
    expectedRows = numel(yValues);
    expectedCols = numel(xValues);
    if ~isequal(size(cMatrix), [expectedRows, expectedCols])
        if isequal(size(cMatrix), [expectedCols, expectedRows])
            cMatrix = cMatrix.';
        else
            error('cMatrix must be [%d x %d]. Got %dx%d.', ...
                  expectedRows, expectedCols, size(cMatrix,1), size(cMatrix,2));
        end
    end

    % ---- smoothing + upsample ----
    interior = imgaussfilt(cMatrix, gaussianSigma);
    if upsampleFactor > 1
        interior = imresize(interior, upsampleFactor, 'bicubic');
    end

    % ---- add NaN rows for channels 1 & 64 only ----
    nCols  = size(interior, 2);
    nanRow = nan(1, nCols);
    fullMatrix = [nanRow; interior; nanRow];

    % ---- extents + ticks ----
    channels = 1:64;
    xExtent  = [xValues(1), xValues(end)];
    yExtent  = [channels(1), channels(end)];

    % ---- plot INVISIBLE, save, close ----
    f = figure('Color','w','Position',[100 100 900 700], 'Visible','off');
    imagesc('XData', xExtent, 'YData', yExtent, 'CData', fullMatrix);
    set(gca,'YDir','reverse');
    colormap(colormapName);
    clim(colorScale);
    colorbar;

    xlabel('X'); ylabel('Channel #');
    title(titleText,'FontWeight','bold');

    yticks(channels);
    yticklabels(string(channels));
    set(gca,'FontSize',8,'TickDir','out','LineWidth',1);
    grid on; box on;
    xlim(xExtent); ylim([1 64]);
    drawnow;

    exportgraphics(f, pngPath, 'Resolution', 220);
    exportgraphics(f, pdfPath, 'ContentType','vector', 'BackgroundColor','white');

    close(f);
end
