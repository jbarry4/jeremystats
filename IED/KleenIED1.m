function KleenIED1()
% a template to perform analyses on IEDs

 % Prompt user for inputs
    directory = input('Enter the directory containing .ncs files: ', 's');
    startTimeSec = input('Enter the start time (in seconds): ');
    endTimeSec = input('Enter the end time (in seconds): ');
    isExluded =input ('Do you want to exlcude any channels? Yes=1 No=0: ')
    if isExluded ==1
        Excluded_Channels = input('Enter channels to be excluded:(Enter channels in an array[]) ');
    else    
        Excluded_Channels=[]
    end    
       
    samplingRate = 30000; % Fixed sampling rate in Hz

    % Convert time to data point based on the sampling frequency 
    start_id = startTimeSec * samplingRate;
    end_id = endTimeSec * samplingRate;

    % Convert data_point to time_stamp because data is recorded in 512xN matrix
    % and every 512 data points has a time stamp
    start_time_stamp = round(start_id / 512);
    end_time_stamp = round(end_id / 512) + 1;

    % Actual start of data visualization can be different from time entered
    % by user because of how timestamps are computed
    actual_start_point = start_time_stamp * 512;
    actual_end_point = end_time_stamp * 512;

    % Compute actual times based on actual data points
    actual_start_time = actual_start_point / samplingRate;
    actual_end_time = actual_end_point / samplingRate;

    % List .ncs files in directory
    files = dir(fullfile(directory, '*.ncs'));
    disp(length(files))
    if isempty(files)
        disp('No .ncs files found in the directory.');
        return;
    end

    % Preallocate cell array for data
    dataMatrix = [];
    validChannels = [];

    % Loop through files and load samples
    for k = 1:length(files)
        chanNum = k;
        
        % Skip excluded channels
        if ismember(chanNum, Excluded_Channels)
            fprintf('Skipping channel %d...\n', chanNum);
            continue;
        end
        
        fullPath = fullfile(directory, files(k).name);

        try
            samples = Nlx2MatCSC_v3(fullPath, [0 0 0 0 1], 0, 2, [start_time_stamp end_time_stamp]);
            samplesFlat = reshape(samples, 1, []);
            samplesFlat = samplesFlat*-1;%For Neuralynx files with default box checked to invert polarity - this flips it back!
            dataMatrix = [dataMatrix; samplesFlat];
            validChannels(end+1) = chanNum;
        catch ME
            fprintf('Error loading channel %d: %s\n', chanNum, ME.message);
            continue;
        end
    end

    if isempty(dataMatrix)
        disp('No valid channel data was loaded.');
        return;
    end

%%Notch filter the EEG signals    
    ff = designfilt('bandstopiir','FilterOrder',2, ...
        'HalfPowerFrequency1',59,'HalfPowerFrequency2',61, ...
        'DesignMethod','butter','SampleRate', samplingRate);
    dataMatrix = filtfilt(ff,dataMatrix);

%where should I downsample?

%%Run the Line Length Spike Detector
d=dataMatrix;
sfx= samplingRate;%May need to downsample
llw=0.04;
prc=99.9;
cd(directory);

[ets,ech]=LLspikedetector(d,sfx,llw,prc)%Took out badch at end
save ets
save ech
%tada
%THis could get fancy and do voltage raster plots that can be saved
%relative to ets. This would require matching samples to time etc.
%But could we do the same thing for CSDs? Would be cool.Still need manual
%curation, but at least it's 5 mice.

