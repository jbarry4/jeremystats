function []=Conor_CohandVcorr();
% a template to perform analyses on plenty of files
path_xls='/Users/jeremybarry/Documents/UVM/projects/Connor_MultiSite/Lists/';
path_out='/Users/jeremybarry/Documents/UVM/projects/Connor_MultiSite';
cd (path_xls);
[data,txt] =  xlsread('spreadsheet.xlsx');
txt(1:2,:)=[];


for i = 1:size(data,1);
    ratId = txt{i,2};
    Group = txt{i,3};
    SessID1 = txt{i,4};
    Path1 = cell2mat(txt(i,6)); 
    Cond =  txt{i,7};
    eegnum  = data(i,8);
%     Side1 = txt{i,10};
%     Side2 = txt{i,13};
   Region1 = txt{i,11};
   Region2=  txt{i,14};
    file1 = cell2mat(txt(i,9));
    file2 = cell2mat(txt(i,12));

 %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
 %Process Tracking Info and Synchroize with BSG; Open EEG files 1(A) and 2(B) 
 %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
 disp(['Treating Rat ', ratId, ' EEG',num2str(eegnum,'%d'),' session ', SessID1])
    if ~isempty(Path1)
        if exist(Path1)
            cd (Path1);
            % Read both eeg files in data path
            [RecSz1,SampleFrequencies,EEGTs,EEG1]=read_csc (file1,30);
            [RecSz2,SampleFrequencies,EEGTs,EEG2]=read_csc (file2,30); %All outputs for each file should be the same except EEG2
            %number after file is added subsampling, use 5 for SWR's
        else
           
            disp('path does not exist')
        end;
    else
        disp('empty path')  
    end;   
    
    SF=SampleFrequencies;
%%Notch filter the EEG signals    
    d = designfilt('bandstopiir','FilterOrder',2, ...
        'HalfPowerFrequency1',59,'HalfPowerFrequency2',61, ...
        'DesignMethod','butter','SampleRate',SF);
    EEG1 = filtfilt(d,EEG1);
    EEG2 = filtfilt(d,EEG2);
    
    
  %% open BSG tracking from .dat file and synch with NLX Event file
            %first use structures (structure find = strfind) to find the .dat file in the current directory
%             cd('..')
            BlaBla=dir;
            line=0;
            for BB=1:length(BlaBla)
                good=strfind(BlaBla(BB).name,'_Room.dat');
                if ~isempty (good), line=BB; end;
            end;
            DatfileName = BlaBla(line).name;
            [FramNum, PosTS, X, Y, Shocks, Sectors,  State, CurrentLevel, Flags, Finfo, header, ArCenterCoord,TargetData3, x, y, xshk2, yshk2, Radius, ACX,ACY,Nshocks,Nent,hb] = read_biosigAA_new (DatfileName, 1); 
            
    %% Also open up the file for tracking in the arena frame
            BlaBla2=dir;
            line=0;
            for BB2=1:length(BlaBla2)
                good=strfind(BlaBla2(BB2).name,'_Arena.dat');
                if ~isempty (good), line=BB2; end;
            end; 
            ArenaDatfileName = BlaBla2(line).name;       
            [FramNumA, PosTSA, XA, YA, ShocksA, SectorsA,  StateA, CurrentLevelA, FlagsA, FinfoA, headerA]=read_biosigAA_new (ArenaDatfileName, 0);   
            
            %% Now read event file for synching
             cd (Path1);
            [RecSz,EventTS,ID,TTL,EventString]=read_nev ('Events.nev');
            %Remove header from events to avoid mixing them up
            if isempty (EventTS), error('Empty file'), end;
            EventTS=EventTS(TTL~=0);
            PosTS=(PosTS*1E3)+EventTS(1);
     %% harmonise TS all start at the first EEGts time
            PosTS=PosTS-EEGTs(1);
            EEGTs=EEGTs-EEGTs(1);
            X=X+5;
            Y=Y+5;
            % computing the diameter in pixels
            DiamInPix=max(X)-min(X);
            %%%% extract diameter from header
            
            Arenadiamfnd=strfind(header,'%ArenaDiameter_m.0');
            for ind=1:length(Arenadiamfnd)
                if ~isempty(Arenadiamfnd{ind})
                    where=ind;
                end;
            end;
            Arenadiam=header{where};
            blanks=strfind(Arenadiam,' ');
            Diam=str2double(Arenadiam(blanks(2):blanks(3)))*100;
            %%%%%% compute pixel size
            pixSz=Diam/DiamInPix;  
      %%      Do the speed filtering in the arena frame and the room frame
              [SpeedMtxA]=Speed_MtxEZ(PosTS,XA,YA,pixSz);%Took out PosTSA
              [SpeedMtxR]=Speed_MtxEZ(PosTS,X,Y,pixSz);      
               
     SF=SampleFrequencies; 
    [Sspect,fspect,tspect] = spectrogram((double(EEG1)),round(SF),round(SF/2),[1:.2:58,62:.2:178,182:.2:300],SF);%Just using this for tspect and time
    Spectro=10*log10(abs(Sspect).^2);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%               
    PosTS=PosTS*1E-6;
    EEGTs_secs=EEGTs*1E-6;%Put EEGTs and PosTS into seconds timescale
        newSpeedMtxA=interp1(PosTS,SpeedMtxA,tspect)
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

    Accel=diff(newSpeedMtxA)./diff(tspect);
    Accel2=smooth(Accel);%Should I just smooth for plots and not for analysis?
    AccelRaw=Accel(1:end)';
    FirstEl=[0];
    Accel3=cat(1,FirstEl,Accel2);
    Accel4=cat(1,FirstEl,AccelRaw);
    Accel4plot=cat(1,FirstEl,smooth(AccelRaw));

    fspectplot=fspect(1:96,:);
    Spectroplot=Spectro(1:96,1:end);

    h0=figure%I love these figures, should save them here too
    imagesc(tspect,fspectplot,Spectroplot)
    colorbar
    colormap (jet)
    axis xy
    hold on
    xlabel('Time(secs)')
    ylabel('Frequency(Hz)')  
    ylimmax=ylim;
    ylimmax=ylimmax(2);
    ylim([max(Accel4plot)*-1 ylimmax])
    hold on
    plot(tspect, Accel4plot,'b.','linewidth',0.9)
    
    Rest=Accel4plot>=-1 & Accel4plot<=1;
    Rest_times=tspect(Rest);
    Rest_accel=Accel4plot(Rest);
    hold on
    plot(Rest_times, Rest_accel,'r.','linewidth',0.3)


    [pks,locs] = findpeaks2(Accel4plot, tspect);

    Peaks=pks>5;
    Peaks1=pks.*Peaks;
    Peaks2=[Peaks1,locs'];
    Peaks3=Peaks2;
    Peaks3(any(Peaks2==0,2),:) = [];%The second column of Peaks3 are the key times
    hold on
    plot(Peaks3(:,2), Peaks3(:,1),'Ko','linewidth',0.9)
    hold on
    plot(tspect, Accel4plot,'b','linewidth',0.3)

    PeakAccelTimes=(Peaks3(:,2))';
    
    PeakAccelTimes_Rd= roundn(PeakAccelTimes,-1);%Changing resoultion to tenths of a second
    EEGTs_secs_Rd=roundn(EEGTs_secs,-1);
    
   % XX=intersect(PeakAccelTimes_Rd,EEGTs_secs_Rd);%Test to see if this is
   % on the right track
   
    lia_E0=ismember(EEGTs_secs_Rd,PeakAccelTimes_Rd);%Make a logical array to throw at EEG signal
    lia_EM3= ismember(EEGTs_secs_Rd,PeakAccelTimes_Rd-3);
    lia_EM2= ismember(EEGTs_secs_Rd,PeakAccelTimes_Rd-2);
    lia_EM1= ismember(EEGTs_secs_Rd,PeakAccelTimes_Rd-1);
    lia_EP3= ismember(EEGTs_secs_Rd,PeakAccelTimes_Rd+3);
    lia_EP2= ismember(EEGTs_secs_Rd,PeakAccelTimes_Rd+2);
    lia_EP1= ismember(EEGTs_secs_Rd,PeakAccelTimes_Rd+1);
    
  
    EM3_EEG1=EEG1(lia_EM3);
    EM3_EEG2=EEG2(lia_EM3);
    
    EM2_EEG1=EEG1(lia_EM2);
    EM2_EEG2=EEG2(lia_EM2);
    
    EM1_EEG1=EEG1(lia_EM1);
    EM1_EEG2=EEG2(lia_EM1);
    
    E0_EEG1=EEG1(lia_E0);
    E0_EEG2=EEG2(lia_E0);
    
    EP3_EEG1=EEG1(lia_EP3);
    EP3_EEG2=EEG2(lia_EP3);
    
    EP2_EEG1=EEG1(lia_EP2);
    EP2_EEG2=EEG2(lia_EP2);
    
    EP1_EEG1=EEG1(lia_EP1);
    EP1_EEG2=EEG2(lia_EP1);

    

    
    
    %%%%%%%%%%%%%%%%%%%%%%%% 
%     A=find(lia_Peak==1)
% %     B=find(lia_PeakMinus3==1)
%     
%     %A=find(lia==1);%Test to see if overlapping timepoints are correct
%     
%     epoch1=PeakAccelTimes_Rd-3;
%     
%     a=[34.8 31.2 29 26.7 39.5];%dummy data
%     n=33;
%     [~,~,idx]=unique(round(abs(a-n)),'stable');
%     minVal=a(idx==2)
%     
%     dist    = round(abs(a - n));
%     minDist = min(dist);
%     idx     = find(dist == minDist);
%     minVal=a(idx==1)
%     
%     
%     lia=ismember(EEGTs_secs,PeakAccelTimes);
%     % A=find(lia==1)%find time points in lia where peakaccel times overlap
%     % with EET timestamps
%     dummy=ones(1,length(EEGTs_secs));
%     rt=dummy.*lia;








 %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
 %  Try without Shock mask first      
 %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
 
  
 %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
 %  Coherence calculations between CSCA and CSCB      
 %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
 
  %Assume 1000Hz SF -Start with Coherence for delta involving 3 s windows
wsize = 3072;
% wsize = 1024;t SR of 1000Hz , 1024 = 1 s, 3072 = 3 s
%3s should be good for Michelle but not so great for Rhys and active
%avoidance - which should be 1 s 
%T = Window Size/SR
%F0=lowest frequency of interest
%F0=5(SF/WS)%5(1000/3072)=1.6

%Accommodating delta is the biggest determinant of window size
%WS = 5(SF/F0)% 5*1000/2=2500

[P1,F1] = pwelch(EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch

[P2,F2] = pwelch(EEG2,hanning(wsize),wsize/2,2*wsize,SF);

[C,Fc] = mscohere(EEG1,EEG2,hanning(wsize),wsize/2,2*wsize,SF); 
%[cxy,f] = mscohere(x,y,window,noverlap,f,fs) returns the magnitude-squared coherence estimate at the frequencies specified in f.
%wsize/2 gives 50% overlap between segments
%2*wsize changes the frequency resolution

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Do The plots for the whole session for long window

h1=figure
subplot(5,4,1:4)
plot(EEGTs_secs,EEG1)
ylabel('Voltage (microV)')
xlabel('Time (s)')
title('Notch Filtered EEG Signal CSCA')
set(gca,'XLim',[0 max(EEGTs_secs)]); grid on;
legend('CSCA','Location','Northeast'); legend boxoff;

subplot(5,4,5:8)
plot(EEGTs_secs,EEG2,'-r')
ylabel('Voltage (microV)')
xlabel('Time (s)')
title('Notch Filtered EEG Signal CSCB')
set(gca,'XLim',[0 max(EEGTs_secs)]); grid on;
legend('CSCB','Location','Northeast'); legend boxoff;

subplot(5,4,9)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(5,4,10)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(5,4,11:12)
[ccf,lags] = xcorr(EEG1,EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag Whole LW')

subplot(5,4,13)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(5,4,14)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(5,4,15)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(5,4,16)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(5,4,17)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(5,4,18)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(5,4,19)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(5,4,20)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_LW=Fc(1:616);%Trimmed for output for 3072 samples
C_trim_LW=C(1:616);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Do The plots for the whole session for short window
  %Assume 1000Hz SF -Start with Coherence for delta involving 3 s windows
wsize = 1024;
% wsize = 1024;t SR of 1000Hz , 1024 = 1 s, 3072 = 3 s
%3s should be good for Michelle but not so great for Rhys and active
%avoidance - which should be 1 s 
%T = Window Size/SR
%F0=lowest frequency of interest
%F0=5(SF/WS)%5(1000/3072)=1.6

%Accommodating delta is the biggest determinant of window size
%WS = 5(SF/F0)% 5*1000/2=2500

[P1,F1] = pwelch(EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch

[P2,F2] = pwelch(EEG2,hanning(wsize),wsize/2,2*wsize,SF);

[C,Fc] = mscohere(EEG1,EEG2,hanning(wsize),wsize/2,2*wsize,SF); 
%[cxy,f] = mscohere(x,y,window,noverlap,f,fs) returns the magnitude-squared coherence estimate at the frequencies specified in f.
%wsize/2 gives 50% overlap between segments
%2*wsize changes the frequency resolution

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Do The plots for the whole session with short window

h2=figure
subplot(5,4,1:4)
plot(EEGTs_secs,EEG1)
ylabel('Voltage (microV)')
xlabel('Time (s)')
title('Notch Filtered EEG Signal CSCA')
set(gca,'XLim',[0 max(EEGTs_secs)]); grid on;
legend('CSCA','Location','Northeast'); legend boxoff;

subplot(5,4,5:8)
plot(EEGTs_secs,EEG2,'-r')
ylabel('Voltage (microV)')
xlabel('Time (s)')
title('Notch Filtered EEG Signal CSCB')
set(gca,'XLim',[0 max(EEGTs_secs)]); grid on;
legend('CSCB','Location','Northeast'); legend boxoff;

subplot(5,4,9)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(5,4,10)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(5,4,11:12)
[ccf,lags] = xcorr(EEG1,EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag Whole SW')

subplot(5,4,13)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(5,4,14)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(5,4,15)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(5,4,16)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(5,4,17)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(5,4,18)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(5,4,19)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(5,4,20)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_SW=Fc(1:616);%Trimmed for output for 1024 samples
C_trim_SW=C(1:616);


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Whole sesssions Done at each sample window size. Run now for each epoch
%relative to peak accel (-3,-2,-1,0,+1,+2,+3) at long window
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%Assume 1000Hz SF -Start with Coherence for delta involving 3 s windows
wsize = 3072;
% wsize = 1024;t SR of 1000Hz , 1024 = 1 s, 3072 = 3 s
%3s should be good for Michelle but not so great for Rhys and active
%avoidance - which should be 1 s 
%T = Window Size/SR
%F0=lowest frequency of interest
%F0=5(SF/WS)%5(1000/3072)=1.6

%Accommodating delta is the biggest determinant of window size
%WS = 5(SF/F0)% 5*1000/2=2500

[P1,F1] = pwelch(EM3_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch

[P2,F2] = pwelch(EM3_EEG2,hanning(wsize),wsize/2,2*wsize,SF);

[C,Fc] = mscohere(EM3_EEG1,EM3_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 
%[cxy,f] = mscohere(x,y,window,noverlap,f,fs) returns the magnitude-squared coherence estimate at the frequencies specified in f.
%wsize/2 gives 50% overlap between segments
%2*wsize changes the frequency resolution

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
h3=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(EM3_EEG1,EM3_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag M3')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccelDelta_EM3=Fc(1:616);
C_trimPkAccelDelta_EM3=C(1:616);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Run coherence at peak accel with the clunky window size for delta
[P1,F1] = pwelch(EM2_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch
[P2,F2] = pwelch(EM2_EEG2,hanning(wsize),wsize/2,2*wsize,SF);
[C,Fc] = mscohere(EM2_EEG1,EM2_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 

h4=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(EM2_EEG1,EM2_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag M2')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccelDelta_EM2=Fc(1:616);
C_trimPkAccelDelta_EM2=C(1:616);

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%Run coherence at peak accel with the clunky window size for delta
[P1,F1] = pwelch(EM1_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch
[P2,F2] = pwelch(EM1_EEG2,hanning(wsize),wsize/2,2*wsize,SF);
[C,Fc] = mscohere(EM1_EEG1,EM1_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 

h5=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(EM1_EEG1,EM1_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag M1')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccelDelta_EM1=Fc(1:616);
C_trimPkAccelDelta_EM1=C(1:616);

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Run coherence at peak accel with the clunky window size for delta
[P1,F1] = pwelch(E0_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch
[P2,F2] = pwelch(E0_EEG2,hanning(wsize),wsize/2,2*wsize,SF);
[C,Fc] = mscohere(E0_EEG1,E0_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 

h6=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(E0_EEG1,E0_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag 0')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccelDelta_E0=Fc(1:616);
C_trimPkAccelDelta_E0=C(1:616);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Run coherence at peak accel with the clunky window size for delta
[P1,F1] = pwelch(EP1_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch
[P2,F2] = pwelch(EP1_EEG2,hanning(wsize),wsize/2,2*wsize,SF);
[C,Fc] = mscohere(EP1_EEG1,EP1_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 

h7=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(EP1_EEG1,EP1_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag P1')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccelDelta_EP1=Fc(1:616);
C_trimPkAccelDelta_EP1=C(1:616);

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Run coherence at peak accel with the clunky window size for delta
[P1,F1] = pwelch(EP2_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch
[P2,F2] = pwelch(EP2_EEG2,hanning(wsize),wsize/2,2*wsize,SF);
[C,Fc] = mscohere(EP2_EEG1,EP2_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 

h8=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(EP2_EEG1,EP2_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag P2')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccelDelta_EP2=Fc(1:616);
C_trimPkAccelDelta_EP2=C(1:616);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Run coherence at peak accel with the clunky window size for delta
[P1,F1] = pwelch(EP3_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch
[P2,F2] = pwelch(EP3_EEG2,hanning(wsize),wsize/2,2*wsize,SF);
[C,Fc] = mscohere(EP3_EEG1,EP3_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 

h9=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(EP3_EEG1,EP3_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag P3')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccelDelta_EP3=Fc(1:616);
C_trimPkAccelDelta_EP3=C(1:616);

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Whole sesssions Done at each sample window size. Run now for each epoch
%relative to peak accel (-3,-2,-1,0,+1,+2,+3) at short window
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%Assume 1000Hz SF -Start with Coherence for delta involving 3 s windows
wsize = 1024
% wsize = 1024;t SR of 1000Hz , 1024 = 1 s, 3072 = 3 s
%3s should be good for Michelle but not so great for Rhys and active
%avoidance - which should be 1 s 
%T = Window Size/SR
%F0=lowest frequency of interest
%F0=5(SF/WS)%5(1000/3072)=1.6

%Accommodating delta is the biggest determinant of window size
%WS = 5(SF/F0)% 5*1000/2=2500

[P1,F1] = pwelch(EM3_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch

[P2,F2] = pwelch(EM3_EEG2,hanning(wsize),wsize/2,2*wsize,SF);

[C,Fc] = mscohere(EM3_EEG1,EM3_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 
%[cxy,f] = mscohere(x,y,window,noverlap,f,fs) returns the magnitude-squared coherence estimate at the frequencies specified in f.
%wsize/2 gives 50% overlap between segments
%2*wsize changes the frequency resolution

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
h10=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(EM3_EEG1,EM3_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag M3SW')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccel_EM3=Fc(1:616);
C_trimPkAccel_EM3=C(1:616);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Run coherence at peak accel with the clunky window size for delta
[P1,F1] = pwelch(EM2_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch
[P2,F2] = pwelch(EM2_EEG2,hanning(wsize),wsize/2,2*wsize,SF);
[C,Fc] = mscohere(EM2_EEG1,EM2_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 

h11=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(EM2_EEG1,EM2_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag M2SW')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccel_EM2=Fc(1:616);
C_trimPkAccel_EM2=C(1:616);

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%Run coherence at peak accel with the clunky window size for delta
[P1,F1] = pwelch(EM1_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch
[P2,F2] = pwelch(EM1_EEG2,hanning(wsize),wsize/2,2*wsize,SF);
[C,Fc] = mscohere(EM1_EEG1,EM1_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 

h12=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(EM1_EEG1,EM1_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag M1SW')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccel_EM1=Fc(1:616);
C_trimPkAccel_EM1=C(1:616);

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Run coherence at peak accel with the clunky window size for delta
[P1,F1] = pwelch(E0_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch
[P2,F2] = pwelch(E0_EEG2,hanning(wsize),wsize/2,2*wsize,SF);
[C,Fc] = mscohere(E0_EEG1,E0_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 

h13=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(E0_EEG1,E0_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag 0SW')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccel_E0=Fc(1:616);
C_trimPkAccel_E0=C(1:616);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Run coherence at peak accel with the clunky window size for delta
[P1,F1] = pwelch(EP1_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch
[P2,F2] = pwelch(EP1_EEG2,hanning(wsize),wsize/2,2*wsize,SF);
[C,Fc] = mscohere(EP1_EEG1,EP1_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 

h14=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(EP1_EEG1,EP1_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag P1SW')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccel_EP1=Fc(1:616);
C_trimPkAccel_EP1=C(1:616);

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Run coherence at peak accel with the clunky window size for delta
[P1,F1] = pwelch(EP2_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch
[P2,F2] = pwelch(EP2_EEG2,hanning(wsize),wsize/2,2*wsize,SF);
[C,Fc] = mscohere(EP2_EEG1,EP2_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 

h15=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(EP2_EEG1,EP2_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag P2SW')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccel_EP2=Fc(1:616);
C_trimPkAccel_EP2=C(1:616);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Run coherence at peak accel with the clunky window size for delta
[P1,F1] = pwelch(EP3_EEG1,hanning(wsize),wsize/2,2*wsize,SF);%Please note that this line of code has nothing to do with Vermont congressman Peter Welch
[P2,F2] = pwelch(EP3_EEG2,hanning(wsize),wsize/2,2*wsize,SF);
[C,Fc] = mscohere(EP3_EEG1,EP3_EEG2,hanning(wsize),wsize/2,2*wsize,SF); 

h16=figure
subplot(3,4,1)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[0 100],'XTick',0:25:150,'FontSize',12); grid on;
legend('CSCA','CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');

subplot(3,4,2)
plot(Fc,C,'LineWidth',2); hold on;%Save this one
set(gca,'XLim',[0 100],'XTick',0:25:100,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northeast'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,3:4)
[ccf,lags] = xcorr(EP3_EEG1,EP3_EEG2,100,'coeff'); % now a cross-correlationn; 100 = SF/10
lags = lags.*(1./SF); % convert samples to time
plot(lags,ccf); grid on;
title('XCorr Signal CSCA-CSCB: Phase lag P3SW')

subplot(3,4,5)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Delta','FontSize',12)

subplot(3,4,6)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('Theta','FontSize',12)

subplot(3,4,7)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('SGamma','FontSize',12)

subplot(3,4,8)
plot(F1,10*log10(P1),'LineWidth',2); 
hold on
plot(F2,10*log10(P2),'LineWidth',2); 
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Amplitude (dB)');
title('MGamma','FontSize',12)

subplot(3,4,9)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[2 4],'XTick',2:0.5:4,'FontSize',12); grid on;
legend('CSCA-CSCB','Location','Northwest'); legend boxoff;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,10)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[4 15],'XTick',4:2:15,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,11)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[20 50],'XTick',20:5:50,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

subplot(3,4,12)
plot(Fc,C,'LineWidth',2); hold on;
set(gca,'XLim',[70 90],'XTick',70:5:90,'FontSize',12); grid on;
xlabel('Frequency (Hz)'); ylabel('Coherence');

Fc_trim_PkAccel_EP3=Fc(1:616);
C_trimPkAccel_EP3=C(1:616);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%On to Voltage correlations: From Gordon lab 2010: https://www.sciencedirect.com/science/article/pii/S0165027010003432
%Whole Session
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
low_freq=2;
high_freq=5;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EEG1,EEG2,SF,low_freq,high_freq);

% figure%Plot figures to see if filters are working properly
% plot(EEGTs1,EEG1)
% ylabel('Voltage (microV)')
% xlabel('Time (s)')
% title('Notch Filtered EEG Signal CSCA')
% set(gca,'XLim',[0 max(EEGTs1)]); grid on;
% legend('CSCA','Location','Northeast'); legend boxoff;
% 
% hold on
% figure
% plot(EEGTs1,amp1)
% ylabel('Voltage (microV)')
% xlabel('Time (s)')
% title('Notch Filtered EEG Signal CSCA')
% set(gca,'XLim',[0 max(EEGTs1)]); grid on;
% legend('CSCA','Location','Northeast'); legend boxoff;

xClagTime_max_Delta=lags(g);
xClagTime_corr_Delta=max(crosscorr);

h17=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
low_freq=5;
high_freq=12;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EEG1,EEG2,SF,low_freq,high_freq);

xClagTime_max_Theta=lags(g);
xClagTime_corr_Theta=max(crosscorr);

h18=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=17;
high_freq=23;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EEG1,EEG2,SF,low_freq,high_freq);

xClagTime_max_Beta=lags(g);
xClagTime_corr_Beta=max(crosscorr);

low_freq=30;
high_freq=50;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EEG1,EEG2,SF,low_freq,high_freq);

xClagTime_max_SGamma=lags(g);
xClagTime_corr_SGamma=max(crosscorr);

h19=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

low_freq=70;
high_freq=90;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EEG1,EEG2,SF,low_freq,high_freq);

xClagTime_max_MGamma=lags(g);
xClagTime_corr_MGamma=max(crosscorr);

h20=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
low_freq=120;
high_freq=200;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EEG1,EEG2,SF,low_freq,high_freq);

xClagTime_max_Ripple=lags(g);
xClagTime_corr_Ripple=max(crosscorr);

h21=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Separating for each epoch and frequency band
low_freq=2;
high_freq=5;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM3_EEG1,EM3_EEG2,SF,low_freq,high_freq);

xClagTime_max_Delta_M3=lags(g);
xClagTime_corr_Delta_M3=max(crosscorr);

h22=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)

low_freq=5;
high_freq=12;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM3_EEG1,EM3_EEG2,SF,low_freq,high_freq);

xClagTime_max_Theta_M3=lags(g);
xClagTime_corr_Theta_M3=max(crosscorr);

h23=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=17;
high_freq=23;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM3_EEG1,EM3_EEG2,SF,low_freq,high_freq);

xClagTime_max_Beta_M3=lags(g);
xClagTime_corr_Beta_M3=max(crosscorr);


low_freq=30;
high_freq=50;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM3_EEG1,EM3_EEG2,SF,low_freq,high_freq);

xClagTime_max_SGamma_M3=lags(g);
xClagTime_corr_SGamma_M3=max(crosscorr);

h24=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)



low_freq=70;
high_freq=90;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM3_EEG1,EM3_EEG2,SF,low_freq,high_freq);

xClagTime_max_MGamma_M3=lags(g);
xClagTime_corr_MGamma_M3=max(crosscorr);

h25=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Separating for each epoch and frequency band
low_freq=2;
high_freq=5;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM2_EEG1,EM2_EEG2,SF,low_freq,high_freq);

xClagTime_max_Delta_M2=lags(g);
xClagTime_corr_Delta_M2=max(crosscorr);

h26=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)



low_freq=5;
high_freq=12;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM2_EEG1,EM2_EEG2,SF,low_freq,high_freq);

xClagTime_max_Theta_M2=lags(g);
xClagTime_corr_Theta_M2=max(crosscorr);

h27=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=17;
high_freq=23;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM2_EEG1,EM2_EEG2,SF,low_freq,high_freq);

xClagTime_max_Beta_M2=lags(g);
xClagTime_corr_Beta_M2=max(crosscorr);



low_freq=30;
high_freq=50;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM2_EEG1,EM2_EEG2,SF,low_freq,high_freq);

xClagTime_max_SGamma_M2=lags(g);
xClagTime_corr_SGamma_M2=max(crosscorr);

h28=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)



low_freq=70;
high_freq=90;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM2_EEG1,EM2_EEG2,SF,low_freq,high_freq);

xClagTime_max_MGamma_M2=lags(g);
xClagTime_corr_MGamma_M2=max(crosscorr);

h29=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Separating for each epoch and frequency band
low_freq=2;
high_freq=5;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM1_EEG1,EM1_EEG2,SF,low_freq,high_freq);

xClagTime_max_Delta_M1=lags(g);
xClagTime_corr_Delta_M1=max(crosscorr);

h30=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=5;
high_freq=12;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM1_EEG1,EM1_EEG2,SF,low_freq,high_freq);

xClagTime_max_Theta_M1=lags(g);
xClagTime_corr_Theta_M1=max(crosscorr);

h31=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=17;
high_freq=23;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM1_EEG1,EM1_EEG2,SF,low_freq,high_freq);

xClagTime_max_Beta_M1=lags(g);
xClagTime_corr_Beta_M1=max(crosscorr);


low_freq=30;
high_freq=50;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM1_EEG1,EM1_EEG2,SF,low_freq,high_freq);

xClagTime_max_SGamma_M1=lags(g);
xClagTime_corr_SGamma_M1=max(crosscorr);

h32=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)



low_freq=70;
high_freq=90;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EM1_EEG1,EM1_EEG2,SF,low_freq,high_freq);

xClagTime_max_MGamma_M1=lags(g);
xClagTime_corr_MGamma_M1=max(crosscorr);

h33=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Separating for each epoch and frequency band
low_freq=2;
high_freq=5;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(E0_EEG1,E0_EEG2,SF,low_freq,high_freq);

xClagTime_max_Delta_0=lags(g);
xClagTime_corr_Delta_0=max(crosscorr);

h34=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=5;
high_freq=12;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(E0_EEG1,E0_EEG2,SF,low_freq,high_freq);

xClagTime_max_Theta_0=lags(g);
xClagTime_corr_Theta_0=max(crosscorr);

h35=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=17;
high_freq=23;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(E0_EEG1,E0_EEG2,SF,low_freq,high_freq);

xClagTime_max_Beta_0=lags(g);
xClagTime_corr_Beta_0=max(crosscorr);

low_freq=30;
high_freq=50;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(E0_EEG1,E0_EEG2,SF,low_freq,high_freq);

xClagTime_max_SGamma_0=lags(g);
xClagTime_corr_SGamma_0=max(crosscorr);

h36=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)



low_freq=70;
high_freq=90;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(E0_EEG1,E0_EEG2,SF,low_freq,high_freq);

xClagTime_max_MGamma_0=lags(g);
xClagTime_corr_MGamma_0=max(crosscorr);

h37=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


%%
%Separating for each epoch and frequency band
low_freq=2;
high_freq=5;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP1_EEG1,EP1_EEG2,SF,low_freq,high_freq);

xClagTime_max_Delta_EP1=lags(g);
xClagTime_corr_Delta_EP1=max(crosscorr);

h38=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=5;
high_freq=12;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP1_EEG1,EP1_EEG2,SF,low_freq,high_freq);

xClagTime_max_Theta_EP1=lags(g);
xClagTime_corr_Theta_EP1=max(crosscorr);

h39=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=17;
high_freq=23;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP1_EEG1,EP1_EEG2,SF,low_freq,high_freq);

xClagTime_max_Beta_EP1=lags(g);
xClagTime_corr_Beta_EP1=max(crosscorr);


low_freq=30;
high_freq=50;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP1_EEG1,EP1_EEG2,SF,low_freq,high_freq);

xClagTime_max_SGamma_EP1=lags(g);
xClagTime_corr_SGamma_EP1=max(crosscorr);

h40=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)



low_freq=70;
high_freq=90;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP1_EEG1,EP1_EEG2,SF,low_freq,high_freq);

xClagTime_max_MGamma_EP1=lags(g);
xClagTime_corr_MGamma_EP1=max(crosscorr);

h41=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)

%%
%Separating for each epoch and frequency band
low_freq=2;
high_freq=5;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP2_EEG1,EP2_EEG2,SF,low_freq,high_freq);

xClagTime_max_Delta_EP2=lags(g);
xClagTime_corr_Delta_EP2=max(crosscorr);

h42=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)



low_freq=5;
high_freq=12;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP2_EEG1,EP2_EEG2,SF,low_freq,high_freq);

xClagTime_max_Theta_EP2=lags(g);
xClagTime_corr_Theta_EP2=max(crosscorr);

h43=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=17;
high_freq=23;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP2_EEG1,EP2_EEG2,SF,low_freq,high_freq);

xClagTime_max_Beta_EP2=lags(g);
xClagTime_corr_Beta_EP2=max(crosscorr);


low_freq=30;
high_freq=50;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP2_EEG1,EP2_EEG2,SF,low_freq,high_freq);

xClagTime_max_SGamma_EP2=lags(g);
xClagTime_corr_SGamma_EP2=max(crosscorr);

h44=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=70;
high_freq=90;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP2_EEG1,EP2_EEG2,SF,low_freq,high_freq);

xClagTime_max_MGamma_EP2=lags(g);
xClagTime_corr_MGamma_EP2=max(crosscorr);

h45=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)

%%
%Separating for each epoch and frequency band
low_freq=2;
high_freq=5;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP3_EEG1,EP3_EEG2,SF,low_freq,high_freq);

xClagTime_max_Delta_EP3=lags(g);
xClagTime_corr_Delta_EP3=max(crosscorr);

h46=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=5;
high_freq=12;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP3_EEG1,EP3_EEG2,SF,low_freq,high_freq);

xClagTime_max_Theta_EP3=lags(g);
xClagTime_corr_Theta_EP3=max(crosscorr);

h47=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


low_freq=17;
high_freq=23;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP3_EEG1,EP3_EEG2,SF,low_freq,high_freq);

xClagTime_max_Beta_EP3=lags(g);
xClagTime_corr_Beta_EP3=max(crosscorr);


low_freq=30;
high_freq=50;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP3_EEG1,EP3_EEG2,SF,low_freq,high_freq);

xClagTime_max_SGamma_EP3=lags(g);
xClagTime_corr_SGamma_EP3=max(crosscorr);

h48=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)



low_freq=70;
high_freq=90;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EP3_EEG1,EP3_EEG2,SF,low_freq,high_freq);

xClagTime_max_MGamma_EP3=lags(g);
xClagTime_corr_MGamma_EP3=max(crosscorr);

h49=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
 cd (path_out)
%%
%Output image files as ps formats and output .mat files for coherence
%analysis in SPSS

filename0 = [num2str(eegnum),num2str(SessID1),'Accel_spectrogram'];%Convention will be that CSCA is the HC and CSCB will be PFC, output named for CSCA
print(h0, '-dpsc', fullfile(path_out,filename0));
savefig(h0,fullfile(path_out,filename0));
close(h0);

filename1 = [num2str(eegnum),num2str(SessID1),'Coherence_WholeSessLW'];
print(h1, '-dpsc', fullfile(path_out,filename1));
savefig(h1,fullfile(path_out,filename1));
close(h1);

filename2 = [num2str(eegnum),num2str(SessID1),'Coherence_WholeSessSW'];
print(h2, '-dpsc', fullfile(path_out,filename2));
savefig(h2,fullfile(path_out,filename2));
close(h2);

filename3 = [num2str(eegnum),num2str(SessID1),'Coherence_M3LW'];
print(h3, '-dpsc', fullfile(path_out,filename3));
savefig(h3,fullfile(path_out,filename3));
close(h3);

filename4 = [num2str(eegnum),num2str(SessID1),'Coherence_M2LW'];
print(h4, '-dpsc', fullfile(path_out,filename4));
savefig(h4,fullfile(path_out,filename4));
close(h4);

filename5 = [num2str(eegnum),num2str(SessID1),'Coherence_M1LW'];
print(h5, '-dpsc', fullfile(path_out,filename5));
savefig(h5,fullfile(path_out,filename5));
close(h5);

filename6 = [num2str(eegnum),num2str(SessID1),'Coherence_0LW'];
print(h6, '-dpsc', fullfile(path_out,filename6));
savefig(h6,fullfile(path_out,filename6));
close(h6);

filename7 = [num2str(eegnum),num2str(SessID1),'Coherence_P1LW'];
print(h7, '-dpsc', fullfile(path_out,filename7));
savefig(h7,fullfile(path_out,filename7));
close(h7);

filename8 = [num2str(eegnum),num2str(SessID1),'Coherence_P2LW'];
print(h8, '-dpsc', fullfile(path_out,filename8));
savefig(h8,fullfile(path_out,filename7));
close(h8);

filename9 = [num2str(eegnum),num2str(SessID1),'Coherence_P3LW'];
print(h9, '-dpsc', fullfile(path_out,filename9));
savefig(h9,fullfile(path_out,filename9));
close(h9);

filename10 = [num2str(eegnum),num2str(SessID1),'Coherence_M3SW'];
print(h10, '-dpsc', fullfile(path_out,filename10));
savefig(h10,fullfile(path_out,filename10));
close(h10);

filename11 = [num2str(eegnum),num2str(SessID1),'Coherence_M2SW'];
print(h11, '-dpsc', fullfile(path_out,filename11));
savefig(h11,fullfile(path_out,filename11));
close(h11);

filename12 = [num2str(eegnum),num2str(SessID1),'Coherence_M1SW'];
print(h12, '-dpsc', fullfile(path_out,filename12));
savefig(h12,fullfile(path_out,filename12));
close(h12);

filename13 = [num2str(eegnum),num2str(SessID1),'Coherence_0SW'];
print(h13, '-dpsc', fullfile(path_out,filename13));
savefig(h13,fullfile(path_out,filename13));
close(h13);

filename14 = [num2str(eegnum),num2str(SessID1),'Coherence_P1SW'];
print(h14, '-dpsc', fullfile(path_out,filename14));
savefig(h14,fullfile(path_out,filename14));
close(h14);

filename15 = [num2str(eegnum),num2str(SessID1),'Coherence_P2SW'];
print(h15, '-dpsc', fullfile(path_out,filename15));
savefig(h15,fullfile(path_out,filename15));
close(h15);

filename16 = [num2str(eegnum),num2str(SessID1),'Coherence_P3SW'];
print(h16, '-dpsc', fullfile(path_out,filename16));
savefig(h16,fullfile(path_out,filename16));
close(h16);

%Output coherence and frequency for each analysis into a .mat file
Specs{1,:}=SessID1;
Specs{2,:}=eegnum;
Specs{3,:}=Fc_trim_LW;
Specs{4,:}=C_trim_LW;
Specs{5,:}=C_trim_SW;
Specs{6,:}=C_trimPkAccelDelta_EM3;
Specs{7,:}=C_trimPkAccelDelta_EM2;
Specs{8,:}=C_trimPkAccelDelta_EM1;
Specs{9,:}=C_trimPkAccelDelta_E0;
Specs{10,:}=C_trimPkAccelDelta_EP1;
Specs{11,:}=C_trimPkAccelDelta_EP2;
Specs{12,:}=C_trimPkAccelDelta_EP3;
Specs{13,:}=C_trimPkAccel_EM3;
Specs{14,:}=C_trimPkAccel_EM2;
Specs{15,:}=C_trimPkAccel_EM1;
Specs{16,:}=C_trimPkAccel_E0;
Specs{17,:}=C_trimPkAccel_EP1;
Specs{18,:}=C_trimPkAccel_EP2;
Specs{19,:}=C_trimPkAccel_EP3;
save([num2str(eegnum),num2str(SessID1),'Specs2.mat'],'Specs');
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
filename17 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_WholeDelta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h17, '-dpsc', fullfile(path_out,filename17));
savefig(h17,fullfile(path_out,filename17));
close(h17);

filename18 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_WholeTheta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h18, '-dpsc', fullfile(path_out,filename18));
savefig(h18,fullfile(path_out,filename18));
close(h18);

filename19 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_WholeSGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h19, '-dpsc', fullfile(path_out,filename19));
savefig(h19,fullfile(path_out,filename19));
close(h19);

filename20 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_WholeMGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h20, '-dpsc', fullfile(path_out,filename20));
savefig(h20,fullfile(path_out,filename20));
close(h20);

filename21 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_WholeRipple'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h21, '-dpsc', fullfile(path_out,filename21));
savefig(h21,fullfile(path_out,filename21));
close(h21);
    
filename22 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_M3Delta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h22, '-dpsc', fullfile(path_out,filename22));
savefig(h22,fullfile(path_out,filename22));
close(h22);     
     
filename23 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_M3Theta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h23, '-dpsc', fullfile(path_out,filename23));
savefig(h23,fullfile(path_out,filename23));
close(h23);     
     
filename24 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_M3SGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h24, '-dpsc', fullfile(path_out,filename24));
savefig(h24,fullfile(path_out,filename24));
close(h24);      
     
filename25 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_M3MGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h25, '-dpsc', fullfile(path_out,filename25));
savefig(h25,fullfile(path_out,filename25));
close(h25);      
     
filename26 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_M2Delta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h26, '-dpsc', fullfile(path_out,filename26));
savefig(h26,fullfile(path_out,filename26));
close(h26);      
         
filename27 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_M2Theta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h27, '-dpsc', fullfile(path_out,filename27));
savefig(h27,fullfile(path_out,filename27));
close(h27);      
     
filename28 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_M2SGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h28, '-dpsc', fullfile(path_out,filename28));
savefig(h28,fullfile(path_out,filename28));
close(h28);  

filename29 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_M2MGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h29, '-dpsc', fullfile(path_out,filename29));
savefig(h29,fullfile(path_out,filename29));
close(h29);

filename30 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_M1Delta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h30, '-dpsc', fullfile(path_out,filename30));
savefig(h30,fullfile(path_out,filename30));
close(h30);

filename31 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_M1Theta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h31, '-dpsc', fullfile(path_out,filename31));
savefig(h31,fullfile(path_out,filename31));
close(h31);

filename32 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_M1SGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h32, '-dpsc', fullfile(path_out,filename32));
savefig(h32,fullfile(path_out,filename32));
close(h32);

filename33 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_M1MGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h33, '-dpsc', fullfile(path_out,filename33));
savefig(h33,fullfile(path_out,filename33));
close(h33);

filename34 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_0Delta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h34, '-dpsc', fullfile(path_out,filename34));
savefig(h34,fullfile(path_out,filename34));
close(h34);

filename35 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_0Theta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h35, '-dpsc', fullfile(path_out,filename35));
savefig(h35,fullfile(path_out,filename35));
close(h35);

filename36 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_0SGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h36, '-dpsc', fullfile(path_out,filename36));
savefig(h36,fullfile(path_out,filename36));39
close(h36);

filename37 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_0MGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h37, '-dpsc', fullfile(path_out,filename37));
savefig(h37,fullfile(path_out,filename37));
close(h37);

filename38 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_P1Delta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h38, '-dpsc', fullfile(path_out,filename38));
savefig(h38,fullfile(path_out,filename38));
close(h38);

filename39 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_P1Theta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h39, '-dpsc', fullfile(path_out,filename39));
savefig(h39,fullfile(path_out,filename39));
close(h39);

filename40 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_P1SGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h40, '-dpsc', fullfile(path_out,filename40));
savefig(h40,fullfile(path_out,filename40));
close(h40);

filename41 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_P1MGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h41, '-dpsc', fullfile(path_out,filename41));
savefig(h41,fullfile(path_out,filename41));
close(h41);

filename42 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_P2Delta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h42, '-dpsc', fullfile(path_out,filename42));
savefig(h42,fullfile(path_out,filename42));
close(h42);

filename43 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_P2Theta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h43, '-dpsc', fullfile(path_out,filename43));
savefig(h43,fullfile(path_out,filename43));
close(h43);

filename44 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_P2SGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h44, '-dpsc', fullfile(path_out,filename44));
savefig(h44,fullfile(path_out,filename44));
close(h44);

filename45 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_P2MGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h45, '-dpsc', fullfile(path_out,filename45));
savefig(h45,fullfile(path_out,filename45));
close(h45);

filename46 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_P3Delta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h46, '-dpsc', fullfile(path_out,filename46));
savefig(h46,fullfile(path_out,filename46));
close(h46);

filename47 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_P3Theta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h47, '-dpsc', fullfile(path_out,filename47));
savefig(h47,fullfile(path_out,filename47));
close(h47);

filename48 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_P3SGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h48, '-dpsc', fullfile(path_out,filename48));
savefig(h48,fullfile(path_out,filename48));
close(h48);

filename49 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_P3MGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
print(h49, '-dpsc', fullfile(path_out,filename49));
savefig(h49,fullfile(path_out,filename49));
close(h49);

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Export data into and excel spreadsheet for SPSS analysis of coherence by
%frequency and Amp correlation (max corr and time lag at max corr)


    columnheaders1={'Frequency','Coherence_Whole_LW','Coherence_Whole_SW',...
        'Coherence_M3_LW', 'Coherence_M2_LW', 'Coherence_M1_LW', 'Coherence_0_LW', 'Coherence_P1_LW', 'Coherence_P2_LW', 'Coherence_P3_LW',...
        'Coherence_M3_SW', 'Coherence_M2_SW', 'Coherence_M1_SW', 'Coherence_0_SW', 'Coherence_P1_SW', 'Coherence_P2_SW', 'Coherence_P3_SW'};
        
    columnheaders2={'ratId', 'Group', 'EEGNum', 'Region1','Region2','Cond', 'SessID1',...
        'XCorrLagTime_wholeDelta','XCorrLagTime_wholeTheta','XCorrLagTime_wholeBeta','XCorrLagTime_wholeSGamma','XCorrLagTime_wholeMGamma','XCorrLagTime_wholeRipple',...
        'XCorrMaxCorr_wholeDelta','XCorrMaxCorr_wholeTheta','XCorrMaxCorr_wholeBeta','XCorrMaxCorr_wholeSGamma','XCorrMaxCorr_wholeMGamma','XCorrMaxCorr_wholeRippple',...
        'XCorrLagTime_Delta_M3','XCorrLagTime_Delta_M2','XCorrLagTime_Delta_M1','XCorrLagTime_Delta_0','XCorrLagTime_Delta_P1','XCorrLagTime_Delta_P2','XCorrLagTime_Delta_P3',...
        'XCorrMaxCorr_Delta_M3','XCorrMaxCorr_Delta_M2','XCorrMaxCorr_Delta_M1','XCorrMaxCorr_Delta_0','XCorrMaxCorr_Delta_P1','XCorrMaxCorr_Delta_P2','XCorrMaxCorr_Delta_P3',...
        'XCorrLagTime_Theta_M3','XCorrLagTime_Theta_M2','XCorrLagTime_Theta_M1','XCorrLagTime_Theta_0','XCorrLagTime_Theta_P1','XCorrLagTime_Theta_P2','XCorrLagTime_Theta_P3',...
        'XCorrMaxCorr_Theta_M3','XCorrMaxCorr_Theta_M2','XCorrMaxCorr_Theta_M1','XCorrMaxCorr_Theta_0','XCorrMaxCorr_Theta_P1','XCorrMaxCorr_Theta_P2','XCorrMaxCorr_Theta_P3',...
        'XCorrLagTime_Beta_M3','XCorrLagTime_Beta_M2','XCorrLagTime_Beta_M1','XCorrLagTime_Beta_0','XCorrLagTime_Beta_P1','XCorrLagTime_Beta_P2','XCorrLagTime_Beta_P3',...
        'XCorrMaxCorr_Beta_M3','XCorrMaxCorr_Beta_M2','XCorrMaxCorr_Beta_M1','XCorrMaxCorr_Beta_0','XCorrMaxCorr_Beta_P1','XCorrMaxCorr_Beta_P2','XCorrMaxCorr_Beta_P3',...
        'XCorrLagTime_SGamma_M3','XCorrLagTime_SGamma_M2','XCorrLagTime_SGamma_M1','XCorrLagTime_SGamma_0','XCorrLagTime_SGamma_P1','XCorrLagTime_SGamma_P2','XCorrLagTime_SGamma_P3',...
        'XCorrMaxCorr_SGamma_M3','XCorrMaxCorr_SGamma_M2','XCorrMaxCorr_SGamma_M1','XCorrMaxCorr_SGamma_0','XCorrMaxCorr_SGamma_P1','XCorrMaxCorr_SGamma_P2','XCorrMaxCorr_SGamma_P3',...
        'XCorrLagTime_MGamma_M3','XCorrLagTime_MGamma_M2','XCorrLagTime_MGamma_M1','XCorrLagTime_MGamma_0','XCorrLagTime_MGamma_P1','XCorrLagTime_MGamma_P2','XCorrLagTime_MGamma_P3',...
        'XCorrMaxCorr_MGamma_M3','XCorrMaxCorr_MGamma_M2','XCorrMaxCorr_MGamma_M1','XCorrMaxCorr_MGamma_0','XCorrMaxCorr_MGamma_P1','XCorrMaxCorr_MGamma_P2','XCorrMaxCorr_MGamma_P3'};
    
    celldatajb=[Fc_trim_LW,C_trim_LW,C_trim_SW,...
    C_trimPkAccelDelta_EM3, C_trimPkAccelDelta_EM2, C_trimPkAccelDelta_EM1, C_trimPkAccelDelta_E0,C_trimPkAccelDelta_EP1, C_trimPkAccelDelta_EP2, C_trimPkAccelDelta_EP3,...
    C_trimPkAccel_EM3, C_trimPkAccel_EM2, C_trimPkAccel_EM1, C_trimPkAccel_E0,C_trimPkAccel_EP1, C_trimPkAccel_EP2, C_trimPkAccel_EP3];
         
    celldataj=[{ratId},{Group}, num2str(eegnum),{Region1},{Region2},{Cond},{SessID1},...
        num2str(xClagTime_max_Delta),num2str(xClagTime_max_Theta),num2str(xClagTime_max_Beta), num2str(xClagTime_max_SGamma),num2str(xClagTime_max_MGamma),num2str(xClagTime_max_Ripple),...
        num2str(xClagTime_corr_Delta),num2str(xClagTime_corr_Theta),num2str(xClagTime_corr_Beta),num2str(xClagTime_corr_SGamma), num2str(xClagTime_corr_MGamma),num2str(xClagTime_corr_Ripple),...
        num2str(xClagTime_max_Delta_M3),num2str(xClagTime_max_Delta_M2),num2str(xClagTime_max_Delta_M1),num2str(xClagTime_max_Delta_0),num2str(xClagTime_max_Delta_EP1),num2str(xClagTime_max_Delta_EP2),num2str(xClagTime_max_Delta_EP3),...
        num2str(xClagTime_corr_Delta_M3),num2str(xClagTime_corr_Delta_M2),num2str(xClagTime_corr_Delta_M1),num2str(xClagTime_corr_Delta_0),num2str(xClagTime_corr_Delta_EP1),num2str(xClagTime_corr_Delta_EP2),num2str(xClagTime_corr_Delta_EP3),...
        num2str(xClagTime_max_Theta_M3),num2str(xClagTime_max_Theta_M2),num2str(xClagTime_max_Theta_M1),num2str(xClagTime_max_Theta_0),num2str(xClagTime_max_Theta_EP1),num2str(xClagTime_max_Theta_EP2),num2str(xClagTime_max_Theta_EP3),...
        num2str(xClagTime_corr_Theta_M3),num2str(xClagTime_corr_Theta_M2),num2str(xClagTime_corr_Theta_M1),num2str(xClagTime_corr_Theta_0),num2str(xClagTime_corr_Theta_EP1),num2str(xClagTime_corr_Theta_EP2),num2str(xClagTime_corr_Theta_EP3),...
        num2str(xClagTime_max_Beta_M3),num2str(xClagTime_max_Beta_M2),num2str(xClagTime_max_Beta_M1),num2str(xClagTime_max_Beta_0),num2str(xClagTime_max_Beta_EP1),num2str(xClagTime_max_Beta_EP2),num2str(xClagTime_max_Beta_EP3),...
        num2str(xClagTime_corr_Beta_M3),num2str(xClagTime_corr_Beta_M2),num2str(xClagTime_corr_Beta_M1),num2str(xClagTime_corr_Beta_0),num2str(xClagTime_corr_Beta_EP1),num2str(xClagTime_corr_Beta_EP2),num2str(xClagTime_corr_Beta_EP3),...
        num2str(xClagTime_max_SGamma_M3),num2str(xClagTime_max_SGamma_M2),num2str(xClagTime_max_SGamma_M1),num2str(xClagTime_max_SGamma_0),num2str(xClagTime_max_SGamma_EP1),num2str(xClagTime_max_SGamma_EP2),num2str(xClagTime_max_SGamma_EP3),...
        num2str(xClagTime_corr_SGamma_M3),num2str(xClagTime_corr_SGamma_M2),num2str(xClagTime_corr_SGamma_M1),num2str(xClagTime_corr_SGamma_0),num2str(xClagTime_corr_SGamma_EP1),num2str(xClagTime_corr_SGamma_EP2),num2str(xClagTime_corr_SGamma_EP3),...
        num2str(xClagTime_max_MGamma_M3),num2str(xClagTime_max_MGamma_M2),num2str(xClagTime_max_MGamma_M1),num2str(xClagTime_max_MGamma_0),num2str(xClagTime_max_MGamma_EP1),num2str(xClagTime_max_MGamma_EP2),num2str(xClagTime_max_MGamma_EP3),...
        num2str(xClagTime_corr_MGamma_M3),num2str(xClagTime_corr_MGamma_M2),num2str(xClagTime_corr_MGamma_M1),num2str(xClagTime_corr_MGamma_0),num2str(xClagTime_corr_MGamma_EP1),num2str(xClagTime_corr_MGamma_EP2),num2str(xClagTime_corr_MGamma_EP3)];
    
%         if i==1
%             XLcellrange1=strcat('A',num2str(i),':Q', num2str(616*i)); %define range in celldataj
%         else 
%             XLcellrange1=strcat('A',num2str((616*i)-615),':Q', num2str(616*i)); %define range in celldataj
%         end
        
    XLcellrange1=strcat('A',num2str((616*i)-615),':Q', num2str(616*i)); %define range in celldataj    
    XLcellrange2=strcat('A',num2str(i),':CK', num2str(i)); %define range in celldataj
    
    jeremy_barry=('Coherence_props.xlsx');
    xlwrite(jeremy_barry, columnheaders1,'Column Key1');
    xlwrite(jeremy_barry, celldatajb, 'Coherence Data', XLcellrange1);

    jeremy_barry2=('AmpCorr_props.xlsx');
    xlwrite(jeremy_barry2, columnheaders2,'Column Key2');
    xlwrite(jeremy_barry2, celldataj, 'Coherence Data', XLcellrange2);
     
%      xlwrite(jeremy_barry, columnheaders1,'Coherence Data1');
    
%     xlwrite(jeremy_barry, [Fc_trim_LW,C_trim_LW,C_trim_SW,...
%     C_trimPkAccelDelta_EM3, C_trimPkAccelDelta_EM2, C_trimPkAccelDelta_EM1, C_trimPkAccelDelta_E0,C_trimPkAccelDelta_EP1, C_trimPkAccelDelta_EP2, C_trimPkAccelDelta_EP3,...
%     C_trimPkAccel_EM3, C_trimPkAccel_EM2, C_trimPkAccel_EM1, C_trimPkAccel_E0,C_trimPkAccel_EP1, C_trimPkAccel_EP2, C_trimPkAccel_EP3],'Coherence Data1');
   
end;
%  
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/poi-3.8-20120326.jar');
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/poi-ooxml-3.8-20120326.jar');
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/poi-ooxml-schemas-3.8-20120326.jar');
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/xmlbeans-2.3.0.jar');
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/dom4j-1.6.1.jar');
fclose all;      
        
              