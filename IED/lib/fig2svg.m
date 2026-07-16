unction fig2svg(figFilePath)
% FIG2SVG Converts a MATLAB .fig file to an SVG file.
%
% This function takes the file path of a MATLAB figure (.fig) file,
% loads it invisibly, saves it as an SVG file in the same directory,
% and then closes the figure handle.
%
% INPUT:
%   figFilePath - String containing the full path to the .fig file.
%
% EXAMPLE USAGE (assuming you have a figure named 'my_plot.fig'):
%   fig2svg('C:\Users\User\Documents\my_plot.fig');
%
% NOTE: The 'svg' format requires MATLAB's rendering engine to be able to
% export the figure successfully, which sometimes requires the figure to be
% closed or invisible during the process.

    disp(['Attempting to convert: ', figFilePath]);

    % 1. Check if the file exists
    if ~exist(figFilePath, 'file')
        error('fig2svg:FileNotFound', 'Error: The specified file was not found.');
    end

    % 2. Open the .fig file and obtain the figure handle (hFig).
    % 'invisible' flag is used so the figure window does not pop up on the screen.
    try
        hFig = openfig(figFilePath, 'invisible');
    catch ME
        error('fig2svg:OpenError', 'Could not open the figure file. Details: %s', ME.message);
    end

    % 3. Determine the output path by replacing the extension.
    [path, name, ~] = fileparts(figFilePath);
    svgFilePath = fullfile(path, [name, '.svg']);

    % 4. Save the figure handle to the new SVG file.
    try 
        saveas(hFig, svgFilePath, 'svg');
        disp(['Successfully converted to: ', svgFilePath]);
    catch ME
        % Ensure the figure is closed even if saving fails.
        close(hFig);
        error('fig2svg:SaveError', 'Could not save the figure as SVG. Details: %s', ME.message);
    end

    % 5. Clean up by closing the figure handle.
    close(hFig);

end
