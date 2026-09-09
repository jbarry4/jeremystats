function step04_newFCSE(workdir, ratId, eegnum, session, eegpath, cond, group, region, ncs_file)

%% Initialize a figure -- should this be done as part of a figure function?
% h = figure

%% pull data from the various cells in the input sheet row we are using
% ratId = txt{ii,2}
% Group = txt{ii,7} % This is unused
% Cond = txt{ii,6}  % This is used
% eegnum = data(ii,3)
% eegnum2 = txt(ii,3) % This is unused
% Side = txt{ii,9} % This is unused
% Layer = txt{ii,11} % This is unused

%Appending useful information
   z = 37;
    IdClear = CFCMatrix(ratId,z);
    GroupClear = CFCMatrix(group,z);
    LayerClear = CFCMatrix(region,z);

%% for testing
% ncs_file = 'CSC1.ncs';

display(['Path to NCS file will be:  ', ncs_file])


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%  Block 1 only
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

disp(['Treating Rat: ', ratId, '  EEG: ', num2str(eegnum,'%d'),'  session: ', session])
if isfile(ncs_file)
    % Read eeg file in data path
    [RecSz,SF,EEGTS,EEG] = read_csc (ncs_file, 10);
    %number after file is added subsampling, use 5 for SWR's
else
    disp([ncs_file, ' does not exist!'])
end

EEGTS=EEGTS-EEGTS(1);
 
 % time stamps are in micro seconds
 % plot the first second of EEG
 
EEG = double(EEG);
d = designfilt('bandstopiir','FilterOrder',2, ...
          'HalfPowerFrequency1',59,'HalfPowerFrequency2',61, ...
          'DesignMethod','butter','SampleRate',SF);
EEG1 = filtfilt(d,EEG);
 % load('lfp');

data_length = length(EEG1);
srate=SF
t=EEGTS;

lfp=EEG1.';

PhaseFreqVector=1:0.5:26;%with 1 x is 1.5 increments of 0.5
AmpFreqVector=20:5:200;% with 20 y is 25 increments of 5
PhaseFreqIdx = 1:length(PhaseFreqVector);
AmpFreqIdx = 1:length(AmpFreqVector);

%for both the increments are as bandwidths defined below, but divided by 2 
PhaseFreq_BandWidth=0.5;
AmpFreq_BandWidth=10;


%% For comodulation calculation (only has to be calculated once)
nbin = 18;

% this variable will get the beginning (not the center) of each phase bin (in rads)
position=zeros(1,nbin);
winsize = 2*pi/nbin;
for j=1:nbin 
    position(j) = -pi+(j-1)*winsize; 
end

    %% Do filtering and Hilbert transform on CPU

'CPU filtering'
Comodulogram=single(zeros(length(PhaseFreqVector),length(AmpFreqVector)));
AmpFreqTransformed = zeros(length(AmpFreqVector), data_length);
PhaseFreqTransformed = zeros(length(PhaseFreqVector), data_length);

'Filtering AmpFreqVector'

tic ; parfor ii=1:length(AmpFreqVector)
    Af1 = AmpFreqVector(ii);
    Af2 = Af1 + AmpFreq_BandWidth;
    % just filtering
    AmpFreq = eegfilt(lfp,srate,Af1,Af2);
    % getting the amplitude envelope
    AmpFreqTransformed(ii, :) = abs(hilbert(AmpFreq));
end ; toc
% Elapsed time is 57.645103 seconds.

'Filtering PhaseFreqVector'

tic ; parfor jj=1:length(PhaseFreqVector)
    Pf1 = PhaseFreqVector(jj);
    Pf2 = Pf1 + PhaseFreq_BandWidth;
    % this is just filtering 
    PhaseFreq=eegfilt(lfp,srate,Pf1,Pf2);
    % this is getting the phase time series
    PhaseFreqTransformed(jj, :) = angle(hilbert(PhaseFreq));
end ; toc
% Elapsed time is 470.465164 seconds.

%% Do comodulation calculation
%% This procedure seems able to run at 200%

% counter1 seems to be the same as ii, so substituting in the following loop
% counter1=0;

'Comodulation calculations, Phase Frequency Vector'

tic ; parfor ii=1:length(PhaseFreqVector)
    data_vector = single(length(AmpFreqVector));
    Pf1 = PhaseFreqVector(ii);
    Pf2 = Pf1+PhaseFreq_BandWidth;
    for jj=1:length(AmpFreqVector)
        Af1 = AmpFreqVector(jj);
        Af2 = Af1 + AmpFreq_BandWidth;
        [MI,MeanAmp] = ModIndex_v2(PhaseFreqTransformed(ii, :),...
                            AmpFreqTransformed(jj, :), position);
        data_vector(ii, jj) = MI;
        % Comodulogram(ii) = [jj, MI];
    end
    Comodulogram(ii, :) = data_vector(ii, :)
end ; toc
% top showed this running at ~200%
% Elapsed time is 854.968632 seconds.

%% Graph comodulogram
%% to functionalize, needs ratID, eegnum, directory for .mat and .fig files
%%  Use the routine below to look at specific pairs of frequency range:

% clf
'Creating figure'
tic ; figure1 = contourf(PhaseFreqVector + PhaseFreq_BandWidth/2,...
        AmpFreqVector+AmpFreq_BandWidth/2,...
        Comodulogram',30,'lines','none'); toc
set(gca,'fontsize',14);
ylabel('Amplitude Frequency (Hz)');
xlabel('Phase Frequency (Hz)');
colorbar

% Pf1 = 3.5
% Pf2 = 5.5 %or beta?
% Af1 = 40
% Af2 = 90
% 
% [MI,MeanAmp] = ModIndex_v1(lfp,srate,Pf1,Pf2,Af1,Af2)

%Appending information for later statistical analysis
Comodulogram = num2cell(Comodulogram);
Comodulogram = transpose(Comodulogram);
Comodulogram = [Comodulogram,IdClear,GroupClear,LayerClear];

%Set new WD, make sure it exists before this runs



newcd = fullfile(workdir, 'CFC')
cd (newcd)
new_name = [ratId,'_', cond, '_Comodulogram','_',num2str(eegnum)];
new_name2 = [ratId,'_', cond, '_ComodFig','_',num2str(eegnum)]; 
save ([new_name,'.mat'],'Comodulogram');
savefig([new_name2,'.fig']);

end
