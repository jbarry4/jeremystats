workdir = 'C:/Users/Z390/Desktop/PTEN_CFCs/VACC/VACC_CFC_Input/VACCQuickstart';
cd (workdir)
arrayIdx = 1;
% set the name of the file that lists the feeder sheets
% this could instead be an argument to the function
feeders = readtable('feeder_sheets.csv','NumHeaderLines',0);

feeders = table2array(feeders);

% set my feeder sheet name from array_id
my_feeder = feeders(arrayIdx);
my_feeder = char(my_feeder);

% read the data from this feeder sheet
txt = readcell(fullfile(workdir, 'FeedersUpload', my_feeder)) ;
