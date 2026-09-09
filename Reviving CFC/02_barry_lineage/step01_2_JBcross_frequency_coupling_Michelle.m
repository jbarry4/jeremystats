function []=step01_2_JBcross_frequency_coupling_Michelle ()
% read an EEG file and analyze it
% retrieve file
% [FileName,PathName,FilterIndex] = uigetfile('*.ncs','Selct EEG');
% % 
% 
% cd (PathName) % go to file
% DownSample=10%was4
% [RecSz,SF,EEGTS,EEG]=read_csc (FileName,DownSample); % read file
global input_file

path_xls=input_file;
path_out=input_file + '\Comod_results_060321';
cd (path_xls);
[data,txt] =  xlsread('eeglist_opto.xlsx');
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
 
%%
EEGTS=EEGTS-EEGTS(1); 
 % time stamps are in micro seconds
 % plot the first second of EEG
 
 EEG = double(EEG);
 
 % load('lfp');

data_length = length(EEG);
srate=SF
t=EEGTS;

lfp=EEG.';

PhaseFreqVector=2:2:26;
AmpFreqVector=30:5:300;

PhaseFreq_BandWidth=4;
AmpFreq_BandWidth=12;


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

clf
Comod_Figure = contourf(PhaseFreqVector+PhaseFreq_BandWidth/2,AmpFreqVector+AmpFreq_BandWidth/2,Comodulogram',30,'lines','none')
set(gca,'fontsize',14)
ylabel('Amplitude Frequency (Hz)')
xlabel('Phase Frequency (Hz)')
colorbar

%TRY Stopping it here

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%  Use the routine below to look at specific pairs of frequency range:

Pf1 = 5
Pf2 = 12
Af1 = 70
Af2 = 90

[MI,MeanAmp] = ModIndex_v1(lfp,srate,Pf1,Pf2,Af1,Af2)



%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Or use the routine below to make a comodulogram using ModIndex_v1; this takes longer than
%% the method outlined above using ModIndex_v2 because in this routine multiple filtering of the same
%% frequency range is employed (the Amp frequencies are filtered multiple times, one
%% for each phase frequency). This routine might be the only choice though
%% for computers with low memory, because it does not create the matrices
%% AmpFreqTransformed and PhaseFreqTransformed as the routine above

tic


Comodulogram=zeros(length(PhaseFreqVector),length(AmpFreqVector));

counter1=0;
for Pf1=PhaseFreqVector
    counter1=counter1+1;
    Pf1 % just to check the progress
    Pf2=Pf1+PhaseFreq_BandWidth;
    
    counter2=0;
    for Af1=AmpFreqVector
        counter2=counter2+1;
        Af2=Af1+AmpFreq_BandWidth;
        
        [MI,MeanAmp]=ModIndex_v1(lfp,srate,Pf1,Pf2,Af1,Af2);

        Comodulogram(counter1,counter2)=MI;

    end    
end

toc

%%

clf
Comod_Figure2 = figure
contourf(PhaseFreqVector+PhaseFreq_BandWidth/2,AmpFreqVector+AmpFreq_BandWidth/2,Comodulogram',30,'lines','none')
set(gca,'fontsize',14)
ylabel('Amplitude Frequency (Hz)')
xlabel('Phase Frequency (Hz)')
colorbar

% file_name = strsplit(FileName, '.');
% Final_name = file_name{1};
new_name = ['Comodulogram','_','eegnum2'];
save ([new_name, '.mat'], 'Comodulogram');
saveas (Comod_Figure2, new_name);
% save([new_name,'.fig'], Comod_Figure2);
end;
