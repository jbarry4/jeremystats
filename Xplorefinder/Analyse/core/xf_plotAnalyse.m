function h = xf_plotAnalyse(R, ax)
%XF_PLOTANALYSE  Draw an XF_ANALYSE result the way xplorefinder draws it.
%
%   H = xf_plotAnalyse(R)        draws into gca (creating a figure if needed)
%   H = xf_plotAnalyse(R, AX)    draws into axes AX
%
%   R is the struct returned by XF_ANALYSE.  Time axes are shifted by
%   R.start so the x-axis reads recording time, matching the GUI's
%   T + Data.start.
%
%   Rendering per R.kind, following the GUI:
%     'image'   imagesc + YDir normal, y-limits clamped to the band
%     'curve'   plot, x-limits clamped to the band, minor grid on
%     'ridge'   plot of the smoothed track + scatter coloured by magnitude
%     'cohere'  plotyy -- coherency left, phase std right
%
%   H is the handle (or handle vector for 'ridge'/'cohere') of the drawn
%   object(s).
%
%   NOTE  mode 5 ('chronus spectogram') is drawn here with imagesc, whereas
%   the GUI uses pcolor+shading interp.  imagesc places one pixel per frame
%   at the frame centre; pcolor interpolates between frame centres and drops
%   the last row/column.  The data are identical -- only the smoothing of
%   the picture differs.  Swap in pcolor(R.T+R.start, R.F, R.Z) if you need
%   the GUI's exact look.
%
%   NOTE  The 'cohere' case uses plotyy, matching the GUI.  plotyy is
%   deprecated (still functional as of R2023b); yyaxis is the modern
%   equivalent if you would rather not depend on it.
%
%   See also XF_ANALYSE.

if nargin < 2 || isempty(ax)
    ax = gca;
end

switch R.kind
    case 'image'
        h = imagesc(R.T + R.start, R.F, R.Z, 'Parent', ax);
        set(ax, 'YDir', 'normal');
        set(ax, 'YLim', [R.minf R.maxf]);
        ylabel(ax, 'Frequency (Hz)');
        xlabel(ax, 'Time (s)');
        if isfield(R, 'zlabel')
            title(ax, sprintf('%s -- %s', R.name, R.zlabel));
        else
            title(ax, R.name);
        end

    case 'curve'
        h = plot(ax, R.X, R.Y);
        set(ax, 'XLim', [R.minf R.maxf]);
        set(ax, 'YMinorGrid', 'on', 'XMinorGrid', 'on');
        xlabel(ax, R.xlabel);
        ylabel(ax, R.ylabel);
        title(ax, R.name);

    case 'ridge'
        t = R.T + R.start;
        h1 = plot(ax, t, R.P);
        hold(ax, 'on');
        h2 = scatter(ax, t, R.P, 10, R.Mag);
        hold(ax, 'off');
        set(ax, 'YLim', [R.minf R.maxf]);
        set(ax, 'YMinorGrid', 'on', 'XMinorGrid', 'on');
        xlabel(ax, 'Time (s)');
        ylabel(ax, 'Frequency (Hz)');
        title(ax, [R.name ' (colour = dB at ridge)']);
        h = [h1 h2];

    case 'cohere'
        axes(ax);                                   % plotyy draws into the current axes
        [hax, h1, h2] = plotyy(R.F, R.C, R.F, R.PhiStd);
        xlabel(hax(1), 'Frequency (Hz)');
        ylabel(hax(1), 'Coherency |C|');
        ylabel(hax(2), 'Phase std (rad)');
        title(hax(1), R.name);
        h = [h1 h2];

    otherwise
        error('xf_plotAnalyse:badKind', 'Unknown result kind ''%s''.', R.kind);
end
