% set the name of the file that lists the feeder sheets
% this could instead be an argument to the function
% Ensure the .csv has a filler top row
feeders = readtable('feeder_sheets.csv','NumHeaderLines',0);

% Convert the table to an array (easier to work with) 
feeders = table2array(feeders);

% set my feeder sheet name from array_id
my_feeder = feeders(arrayIdx);

% Convert the 1x1 cell into a character vector
my_feeder = char(my_feeder);

% read the data from this feeder sheet
txt = readcell(fullfile(workdir, 'FeedersUpload', my_feeder)) ;