function CSC2microVoltPatchCode(filePath, varargin)
%CSC2microVoltPatchCode Convert saved Neuralynx CSC data (AD units) to microvolts.
%
% Usage examples:
%   CSC2microVoltPatchCode("C:\path\file.mat")
%   CSC2microVoltPatchCode('C:\path\file.mat','var','d')  % if you know the var name
%
% Inputs:
%   filePath : string or char, .mat file containing AD-unit data
%   'var'    : (optional) name of variable to scale (default: largest numeric array)
%
% Output:
%   Saves <original>_uV.mat next to the input, with the selected variable scaled to µV
%
% Note: ADBitVolts taken from your header = 0.00000006103515625 V/AD

    p = inputParser;
    p.addRequired('filePath', @(s)ischar(s)||isstring(s));
    p.addParameter('var', '', @(s)ischar(s)||isstring(s));
    p.parse(filePath, varargin{:});

    filePath = p.Results.filePath;
    varName  = p.Results.var;

    % ---- constants ----
    ADBitVolts = 0.00000006103515625;  % volts per AD unit
    scaleFactor = ADBitVolts * 1e6;    % microvolts per AD

    % ---- load ----
    S = load(filePath);
    vars = fieldnames(S);

    if isempty(varName)
        % Pick the largest numeric array
        isNum = cellfun(@(v) isnumeric(S.(v)), vars);
        if ~any(isNum)
            error('No numeric variables found in file: %s', string(filePath));
        end
        numCounts = zeros(numel(vars),1);
        for i = 1:numel(vars)
            if isNum(i)
                numCounts(i) = numel(S.(vars{i}));
            end
        end
        [~, idx] = max(numCounts);
        sigName = vars{idx};
    else
        sigName = char(varName);
        if ~isfield(S, sigName)
            error('Variable "%s" not found in file: %s', sigName, string(filePath));
        end
        if ~isnumeric(S.(sigName))
            error('Variable "%s" is not numeric.', sigName);
        end
    end

    % ---- scale ----
    S.(sigName) = S.(sigName) * scaleFactor;   % in microvolts
    S.([sigName '_units']) = 'microvolts';

    % ---- save as *_uV.mat in same dir ----
    [fdir,fname,ext] = fileparts(char(filePath));
    outFile = fullfile(fdir, [fname '_uV' ext]);

    % 'save' wants char filename; also keep struct unpack with -struct
    save(char(outFile), '-struct', 'S', '-v7.3');

    fprintf('Scaled "%s" to microvolts and saved:\n%s\n', sigName, outFile);
end
