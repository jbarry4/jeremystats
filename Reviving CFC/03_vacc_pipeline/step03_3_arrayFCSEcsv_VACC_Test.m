function step03_3_arrayFCSEcsv_VACC_Test(arrayIdx)
arrayIdx = str2num(arrayIdx);

% set the path to the top of the analysis directory
workdir = 'C:\Users\Z390\Desktop\PTEN_CFCs\VACC\VACC_CFC_Input\VACCQuickstart';
cd (workdir)

% need functions in the workdir, so set path
addpath(fullfile(workdir));

disp(['SLURM_ARRAY_TASK_ID is: ', num2str(arrayIdx)])

% Get the number of processors available from job
% otherwise use 4
if isempty(getenv('SLURM_CPUS_PER_TASK'))
    NP = 4;
else
    NP = str2num(getenv('SLURM_CPUS_PER_TASK'));
end
disp(['NP is ', num2str(NP)])


% Set the job storage location to what we made in the job script
JSL = fullfile(getenv('HOME'), 'scratch', 'matlabdata', getenv('SLURM_JOBID'));

% set up the cluster object so we can set the job storage location
myCluster = parcluster('local');
myCluster.JobStorageLocation = JSL;

% Create the parpool
myPool = parpool(myCluster, NP);

% set the name of the file that lists the feeder sheets
% this could instead be an argument to the function
% Ensure the .csv has a filler top row
feeders = readtable('feeder_sheets.csv','NumHeaderLines',0,'Delimiter',',');

% Convert the table to an array (easier to work with) 
feeders = table2array(feeders);

% set my feeder sheet name from array_id
my_feeder = feeders(arrayIdx);

% Convert the 1x1 cell into a character vector
my_feeder = char(my_feeder);

% read the data from this feeder sheet
txt = readcell(fullfile(workdir, 'C:\Users\Z390\Desktop\PTEN_CFCs\VACC\VACC_CFC_Input', my_feeder)) ;

%remove the first row, which is column headers
% make sure there is only one row to remove (there may have been two)
% in each sheet prior to running this.
txt(1:1,:) = [];

% We will read each row of the feeder sheet and get the variables needed to
% properly label the figures.
disp('Running 128 .ncs files. . . .')
for ii = 1:64
    cd (workdir)
    % Read variables for later use
    ratId = txt{ii,2};
    eegnum = txt{ii,3};
    session = txt{ii,4};
    eegpath = fullfile(txt{ii, 5});
    cond = txt{ii,6}
    group = txt{ii,7};
    region = txt{ii,10};  % This is called Layer in some places
    ncs_file = fullfile(eegpath, strcat('CSC', num2str(ii), '.ncs'));

    disp(['Running RatID: "', ratId, '"   EEG number: "', eegnum,...
          '"   group: "', group, '"   Region: "', region, '"'])
    disp(['  using: ', ncs_file])
    disp(['Does ', ncs_file, ' exist?  ', num2str(isfile(ncs_file))])

    % uncomment this when running for real
    step04_newFCSE(workdir, ratId, eegnum, session, eegpath, cond, group, region, ncs_file);
end

delete(myPool);
exit
