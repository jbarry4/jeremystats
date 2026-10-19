current_folder = 'C:\Users\Z390\Desktop\PTEN_CFCs\VACC\CFC\CNO_Data\IED+\2\m13';
% Get a list of all files in the folder with the desired file name pattern.
filePattern = fullfile(current_folder, '*.mat'); % Change to whatever pattern you need.
theFiles = dir(filePattern);
final_list = [];
for current_file = 1 : length(theFiles)
    baseFileName = theFiles(current_file).name;
    fullFileName = fullfile(theFiles(current_file).folder, baseFileName);
    fprintf(1, 'Now adjusting %s\n', fullFileName);
    data = load(baseFileName);
    comod = data.Comodulogram;
    transposed_comod = comod.';
    filenumber = baseFileName(38:end-4);
    filenumber = str2double(filenumber);
    [nRows,nCols] = size(transposed_comod);
    transposed_comod = [transposed_comod filenumber*ones(nRows,1)];
    cellcomod(1,:) = {transposed_comod};
    comodstruct = cell2struct(cellcomod,'Comodulogram');
    savefilename = convertCharsToStrings(sprintf(append(baseFileName(1:end-4), '_transposed.mat')));
    save(strcat(baseFileName(1:end-4),'_transposed.mat'),'transposed_comod')
end