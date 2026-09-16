path_xls='D:\PupProbePilot\Matlab Code for amplitude and frequency and feeder sheet\FeedersUpload';
cd = path_xls
%Let's try to read the entire directory.
files = dir(fullfile(path_xls,'*.xlsx'));
for i = 1:length(files)
    currentFile = fullfile(path_xls, files(i).name);
[data,txt] =  xlsread(currentFile);
qqq=txt(1:2,:);
txt(1:2,:)=[];
for i = 1()
    ratId = txt{i,2}
    Group = txt{i,7};
    Cond = txt{i,6};
    eegnum = data(i,3);
    eegnum2 = txt(i,3);
    Side = txt{i,9};
    Layer = txt{i,11};
    
    SessID1 = txt{i,4};
    Path1 = cell2mat(txt(i,5));
    file1 = cell2mat(txt(i,8));

end