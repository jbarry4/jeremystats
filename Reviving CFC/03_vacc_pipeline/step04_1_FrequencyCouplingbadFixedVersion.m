function []=step04_1_FrequencyCouplingbadFixedVersion ()
% read an EEG file and analyze it
% retrieve file
% [FileName,PathName,FilterIndex] = uigetfile('*.ncs','Selct EEG','CSC1.ncs') ;
% % 
% cd (PathName) % go to file
% DownSample=10%was4
% [RecSz,SF,EEGTS,EEG]=read_csc (FileName,DownSample); % read file
% global input_file

path_xls='C:\Users\Z390\Desktop\PTEN_CFCs\VACC\VACC_CFC_Input\VACCQuickstart';

%You could deleta the "global" above and just put the path to an excel file
%that has the information below for your experiment and subject parameters.

cd (path_xls);
[data,txt] =  xlsread('M13VACCFeeder_CNO.csv');
qqq=txt(1:2,:);
txt(1:2,:)=[];

for i = 1:size(data,1);
    h=figure
    ratId = txt{i,2};
    Group = txt{i,7};
    Cond = txt{i,6};
    eegnum = data(i,3);
    eegnum2 = txt(i,3);
    Side = txt{i,10};
    Layer = txt{i,11};
    
    SessID1 = txt{i,4};
    Path1 = cell2mat(txt(i,5));
    file1 = cell2mat(txt(i,8));

    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    %Block 1 only
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    disp(['Treating Rat ', ratId, ' EEG',num2str(eegnum,'%d'),' session ', SessID1])
    if ~isempty(Path1)
        if exist(Path1)
            cd (Path1);
            
            % Read eeg file in data path
            [RecSz,SF,EEGTS,EEG]=read_csc (file1,10);
            %number after file is added subsampling, use 5 for SWR's
        else
            disp('path does not exist')

        end;
        
    else
        disp('empty path')
        
    end;


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
%for both the increments are as bandwidths defined below, but divided by 2 

PhaseFreq_BandWidth=0.5;
AmpFreq_BandWidth=10;


%% For comodulation calculation (only has to be calculated once)
nbin = 18;
position=zeros(1,nbin); % this variable will get the beginning (not the center) of each phase bin (in rads)
winsize = 2*pi/nbin;
for j=1:nbin 
    position(j) = -pi+(j-1)*winsize; 
end
%% Do filtering and Hilbert transform on CPU

'CPU filtering'
tic
Comodulogram=single(zeros(length(PhaseFreqVector),length(AmpFreqVector)));
AmpFreqTransformed = zeros(length(AmpFreqVector), data_length);
PhaseFreqTransformed = zeros(length(PhaseFreqVector), data_length);

for ii=1:length(AmpFreqVector)
    Af1 = AmpFreqVector(ii);
    Af2=Af1+AmpFreq_BandWidth;
    AmpFreq=eegfilt(lfp,srate,Af1,Af2); % just filtering
    AmpFreqTransformed(ii, :) = abs(hilbert(AmpFreq)); % getting the amplitude envelope
end

for jj=1:length(PhaseFreqVector)
    Pf1 = PhaseFreqVector(jj);
    Pf2 = Pf1 + PhaseFreq_BandWidth;
    PhaseFreq=eegfilt(lfp,srate,Pf1,Pf2); % this is just filtering 
    PhaseFreqTransformed(jj, :) = angle(hilbert(PhaseFreq)); % this is getting the phase time series
end
toc

%% Do comodulation calculation
'Comodulation loop'

counter1=0;
for ii=1:length(PhaseFreqVector)
counter1=counter1+1;

    Pf1 = PhaseFreqVector(ii);
    Pf2 = Pf1+PhaseFreq_BandWidth;
    
    counter2=0;
    for jj=1:length(AmpFreqVector)
    counter2=counter2+1;
    
        Af1 = AmpFreqVector(jj);
        Af2 = Af1+AmpFreq_BandWidth;
        [MI,MeanAmp]=ModIndex_v2(PhaseFreqTransformed(ii, :), AmpFreqTransformed(jj, :), position);
        Comodulogram(counter1,counter2)=MI;
    end
end
toc



%% Graph comodulogram

% clf
figure1 = contourf(PhaseFreqVector+PhaseFreq_BandWidth/2,AmpFreqVector+AmpFreq_BandWidth/2,Comodulogram',30,'lines','none')
set(gca,'fontsize',14)
ylabel('Amplitude Frequency (Hz)')
xlabel('Phase Frequency (Hz)')
colorbar


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%  Use the routine below to look at specific pairs of frequency range:

% Pf1 = 3.5
% Pf2 = 5.5 %or beta?
% Af1 = 40
% Af2 = 90
% 
% [MI,MeanAmp] = ModIndex_v1(lfp,srate,Pf1,Pf2,Af1,Af2)

    new_name = ['Comodulogram','_',num2str(eegnum)];
    new_name2 = ['ComodFig','_',num2str(eegnum)]; 
    save ([new_name,'.mat'],'Comodulogram');
    savefig([new_name2,'.fig']);
    close;
end;