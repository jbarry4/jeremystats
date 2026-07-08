function replot_phase_polar_corrected_with_rayleigh()
% Replot phase histograms with:
%   - 0° on the right
%   - CCW angle direction
%   - Mean vector
%   - Rayleigh test (r, p)
%
% Uses phi_keep from .mat files
% Run inside a folder containing .mat files

files = dir('*.mat');

for iF = 1:numel(files)

    fname = files(iF).name;
    data  = load(fname);

    if ~isfield(data,'phi_keep')
        fprintf('Skipping %s (no phi_keep)\n', fname);
        continue;
    end

    theta = data.phi_keep(:);        % radians
    theta = theta(~isnan(theta));    % safety
    n = numel(theta);

    if n < 5
        fprintf('Skipping %s (too few samples)\n', fname);
        continue;
    end

    % ---------- circular statistics ----------
    C = mean(cos(theta));
    S = mean(sin(theta));

    mean_ang = atan2(S, C);          % mean direction (rad)
    r = sqrt(C^2 + S^2);             % mean resultant length
    Z = n * r^2;

    % Rayleigh p-value (Berens 2009)
    if n > 50
        p = exp(-Z);
    else
        p = exp(-Z) * (1 + (2*Z - Z^2)/(4*n) ...
            - (24*Z - 132*Z^2 + 76*Z^3 - 9*Z^4)/(288*n^2));
    end

    % ---------- plotting ----------
    fig = figure('Visible','off');
    pax = polaraxes(fig);
    pax.ThetaZeroLocation = 'right';
    pax.ThetaDir = 'counterclockwise';
    hold(pax,'on');

    % Histogram
    polarhistogram(pax, theta, 18, ...
        'Normalization','probability', ...
        'FaceColor',[0.3 0.6 0.85], ...
        'EdgeColor','k');

    % Mean vector
    rmax = pax.RLim(2);
    polarplot(pax, [mean_ang mean_ang], [0 r*rmax], ...
        'LineWidth',3, 'Color',[0.85 0.33 0.1]);

    % Title
    ttl = sprintf('%s | n=%d, r=%.3f, p=%.4g', ...
        strrep(fname,'_','\_'), n, r, p);
    title(ttl, 'Interpreter','tex');

    % Save
    [~, base, ~] = fileparts(fname);
    outname = [base '_corrected.png'];
    exportgraphics(fig, outname, 'Resolution',300);
    close(fig);

    fprintf('Saved: %s\n', outname);
end

fprintf('All files processed.\n');
end
