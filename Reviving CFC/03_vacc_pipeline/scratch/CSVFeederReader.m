path_xls='D:\PupProbePilot\Matlab Code for amplitude and frequency and feeder sheet';
cd = path_xls;
files = dir(fullfile(path_xls,'*.xlsx'));
for j = 1:length(files)
    currentFile = fullfile(path_xls, files(j).name);
[data] =  table2cell(readtable(currentFile));

for ii = 1:size(data,1)
  ratId = data{ii,2}
    Group = data{ii,7}
    Cond = data{ii,6}
    eegnum = cell2mat(data(ii,3))
    Side = data{ii,9}
    Layer = data{ii,10}
    
    SessID1 = data{ii,4}
    Path1 = cell2mat(data(ii,5))
    file1 = cell2mat(data(ii,8))

end
end
