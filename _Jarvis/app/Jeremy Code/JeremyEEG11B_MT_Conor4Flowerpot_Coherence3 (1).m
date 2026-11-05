  function []=JeremyEEG4();
% a template to perform analyses on laminar probe data

path_xls='/Users/jeremybarry/Documents/UVM/projects/Connor_MultiSite/Lists/';
path_out='/Users/jeremybarry/Documents/UVM/projects/Connor_MultiSite';
cd (path_xls);
[data,txt] =  xlsread('spreadsheet.xlsx');

qqq=txt(1:2,:);
txt(1:2,:)=[];

for i = 1:size(data,1);
    ratId = txt{i,2};
    Group = txt{i,4};
    SessID1 = txt{i,3};
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
    %File 1 
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    disp(['Treating Rat ', ratId, ' EEG',num2str(eegnum,'%d'),' session ', SessID1])
    if ~isempty(Path1)
        if exist(Path1)
            cd (Path1);
            
            % Read eeg file in data path
            [RecSz1,SampleFrequencies1,EEGTs1,EEG1]=read_csc (file1,30);
            %number after file is added subsampling, use 5 for SWR's
        else
            disp('path does not exist')

        end;
        
    else
        disp('empty path')
        
    end;
    
     EEGTs1=EEGTs1-EEGTs1(1); 
     EEGTs1=EEGTs1*1E-6;
     SF=SampleFrequencies1;
     
     d = designfilt('bandstopiir','FilterOrder',2, ...
               'HalfPowerFrequency1',59,'HalfPowerFrequency2',61, ...
               'DesignMethod','butter','SampleRate',SF);
     EEG1 = filtfilt(d,EEG1);
%    [Sspect1,fspect1,tspect1] = spectrogram((double(EEG1)),round(SF),round(SF/2),[1:.2:140],SF);

%%
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    %File 2
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    disp(['Treating Rat ', ratId, ' EEG',num2str(eegnum,'%d'),' session ', SessID1])
    if ~isempty(Path1)
        if exist(Path1)
            cd (Path1);
            
            % Read eeg file in data path
            [RecSz2,SampleFrequencies2,EEGTs2,EEG2]=read_csc (file2,30);
            %number after file is added subsampling, use 5 for SWR's
        else
            disp('path does not exist')
            
        end;
        
    else
        disp('empty path')
        
    end;
    
    
     EEGTs2=EEGTs2-EEGTs2(1); 
     EEGTs2=EEGTs2*1E-6;
     SF=SampleFrequencies2;%Should always be same sample frequency
    
%     [Sspect2,fspect2,tspect2] = spectrogram((double(EEG2)),round(SF),round(SF/2),[1:.2:140],SF);

    d = designfilt('bandstopiir','FilterOrder',2, ...
        'HalfPowerFrequency1',59,'HalfPowerFrequency2',61, ...
        'DesignMethod','butter','SampleRate',SF);
    EEG2 = filtfilt(d,EEG2);
  
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    %Long Window Coherence analysis in order to get meaningful results from
    %Delta
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% wsize = 2048; This was MVDM's default example %This is an important number and needs to be considered in context with sampling rate and the bandwidths of interest, partcularly if the frequency is slow (i.e. delta) 
% wsize = 2500;%At 1000Hz SF, corresponds to 2.5 s
% wsize = 2048;
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

%%
%Do The plots

h1=figure
subplot(5,4,1:4)
plot(EEGTs1,EEG1)
ylabel('Voltage (microV)')
xlabel('Time (s)')
title('Notch Filtered EEG Signal CSCA')
set(gca,'XLim',[0 max(EEGTs1)]); grid on;
legend('CSCA','Location','Northeast'); legend boxoff;

subplot(5,4,5:8)
plot(EEGTs2,EEG2,'-r')
ylabel('Voltage (microV)')
xlabel('Time (s)')
title('Notch Filtered EEG Signal CSCB')
set(gca,'XLim',[0 max(EEGTs2)]); grid on;
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
title('XCorr Signal CSCA-CSCB: Phase lag')

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

Fc_trim_LW=Fc(1:616);
C_trim_LW=C(1:616);


    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    %Short Window Coherence analysis in order to get meaningful results from
    %all other bandwidths outside of Delta
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

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
%Do The plots 
h2=figure
subplot(5,4,1:4)
plot(EEGTs1,EEG1)
ylabel('Voltage (microV)')
xlabel('Time (s)')
title('Notch Filtered EEG Signal CSCA')
set(gca,'XLim',[0 max(EEGTs1)]); grid on;
legend('CSCA','Location','Northeast'); legend boxoff;

subplot(5,4,5:8)
plot(EEGTs1,EEG2,'-r')
ylabel('Voltage (microV)')
xlabel('Time (s)')
title('Notch Filtered EEG Signal CSCB')
set(gca,'XLim',[0 max(EEGTs1)]); grid on;
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

Fc_trim_SW=Fc(1:204);%Trimmed for output for 1024 samples
C_trim_SW=C(1:204);

%%
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    %On to Voltage correlations: From Gordon lab 2010: https://www.sciencedirect.com/science/article/pii/S0165027010003432
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

low_freq=2;
high_freq=5;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EEG1,EEG2,SF,low_freq,high_freq);

xClagTime_max_Delta=lags(g);
xClagTime_corr_Delta=max(crosscorr);

h3=figure
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

h4=figure
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

h5=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)

low_freq=30;
high_freq=50;%Set low and high bandpass filters
 
[lags, crosscorr, max_crosscorr_lag,g,amp1,amp2]=amp_crosscorr(EEG1,EEG2,SF,low_freq,high_freq);

xClagTime_max_SGamma=lags(g);
xClagTime_corr_SGamma=max(crosscorr);

h6=figure
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

h7=figure
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

h8=figure
plot(lags, crosscorr,'color',[0 0 1],'linewidth',2),hold on %plots crosscorrelations
plot(lags(g),crosscorr(g),'rp','markerfacecolor',[1 0 0],'markersize',10)%plots marker at the peak of the cross correlation
plot([0 0],[1.05*max(crosscorr) 0.95*min(crosscorr)],'color',[0 0 0],'linestyle',':', 'linewidth',2) %plots dashed line at zero lag
set(gca,'xtick',[-100 -50 0 50 100])
axis tight, box off, xlim([-101 100])
xlabel('Lag (ms)','fontsize',14)
ylabel('Crosscorrelation','fontsize',14)

%%
cd (path_out)
%%
%Output the file as a ps and matlab file - neither of which will scale very
%well
filename1 = [num2str(eegnum),num2str(SessID1),'Coherence_LW'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
     print(h1, '-dpsc', fullfile(path_out,filename1));
     savefig(h1,fullfile(path_out,filename1));
        close(h1);       
filename2 = [num2str(eegnum),num2str(SessID1),'Coherence_SW'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
     print(h2, '-dpsc', fullfile(path_out,filename2));
     savefig(h2,fullfile(path_out,filename2));
     close(h2);
filename3 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_Delta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
     print(h3, '-dpsc', fullfile(path_out,filename3));
     savefig(h3,fullfile(path_out,filename3));
     close(h3);
filename4 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_Theta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
     print(h4, '-dpsc', fullfile(path_out,filename4));
     savefig(h4,fullfile(path_out,filename4));
     close(h4);
filename5 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_Beta'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
     print(h5, '-dpsc', fullfile(path_out,filename5));
     savefig(h5,fullfile(path_out,filename5));
     close(h5); 
filename6 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_SGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
     print(h6, '-dpsc', fullfile(path_out,filename6));
     savefig(h6,fullfile(path_out,filename6));
     close(h6);
filename7 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_MGamma'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
     print(h7, '-dpsc', fullfile(path_out,filename7));
     savefig(h7,fullfile(path_out,filename7));
     close(h7); 
filename8 = [num2str(eegnum),num2str(SessID1),'AmpCorrelation_Ripple'];%Convention will be that CSCA is the SLM or DG mol layer, output named for each compared channel
     print(h8, '-dpsc', fullfile(path_out,filename8));
     savefig(h8,fullfile(path_out,filename8));
     close(h8);           

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%Export data into and excel spreadsheet for SPSS analysis of coherence by
%frequency and Amp correlation (max corr and time lag at max corr)


    columnheaders1={'ratid', 'group', 'eegnum', 'Region1', 'Region2', 'Condition', 'SessId', 'Frequency','Coherence'};
        
    columnheaders2={'ratId', 'Group', 'EEGNum', 'Channel1','Channel2','Cond', 'SessID1',...
        'XCorrLagTime_wholeDelta','XCorrLagTime_wholeTheta','XCorrLagTime_wholeBeta','XCorrLagTime_wholeSGamma','XCorrLagTime_wholeMGamma','XCorrLagTime_wholeRipple',...
        'XCorrMaxCorr_wholeDelta','XCorrMaxCorr_wholeTheta','XCorrMaxCorr_wholeBeta','XCorrMaxCorr_wholeSGamma','XCorrMaxCorr_wholeMGamma','XCorrMaxCorr_wholeRippple'};
       
       variables=[{ratId},{Group}, num2str(eegnum),{Region1},{Region2},{Cond},{SessID1}];
       variables_LW=string(repmat(variables,615,1));
       variables_SW=string(repmat(variables,204,1));
       
       celldata_LW= [Fc_trim_LW, C_trim_LW];
       celldata_SW= [Fc_trim_SW, C_trim_SW];
       
    celldataj=[{ratId},{Group}, num2str(eegnum),{Region1},{Region2},{Cond},{SessID1},...
        num2str(xClagTime_max_Delta),num2str(xClagTime_max_Theta),num2str(xClagTime_max_Beta), num2str(xClagTime_max_SGamma),num2str(xClagTime_max_MGamma),num2str(xClagTime_max_Ripple),...
        num2str(xClagTime_corr_Delta),num2str(xClagTime_corr_Theta),num2str(xClagTime_corr_Beta),num2str(xClagTime_corr_SGamma), num2str(xClagTime_corr_MGamma),num2str(xClagTime_corr_Ripple)];
    
    XLcellrange1=strcat('A',num2str((616*i)-615),':G', num2str(616*i)); %define range in celldataj
    XLcellrange2=strcat('A',num2str((616*i)-615),':B', num2str(616*i)); %define range in celldataj
    
    XLcellrange3=strcat('A',num2str((205*i)-204),':G', num2str(205*i)); %define range in celldataj
    XLcellrange4=strcat('A',num2str((205*i)-204),':B', num2str(205*i)); %define range in celldataj
    
    XLcellrange5=strcat('A',num2str(i),':S', num2str(i)); %define range in celldataj
    
    jeremy_barry=('Coherence_props.xlsx');
    xlwrite(jeremy_barry, columnheaders1,'Column Key_LWandSW');
    xlwrite(jeremy_barry, columnheaders2,'Column Key_Ampcorr');
    xlwrite(jeremy_barry, variables_LW,'Variables Data_LW',XLcellrange1);
    xlwrite(jeremy_barry, celldata_LW,'Coherence Data_LW',XLcellrange2);
    xlwrite(jeremy_barry, variables_SW,'Variables Data_SW',XLcellrange3);
    xlwrite(jeremy_barry, celldata_SW,'Coherence Data_SW',XLcellrange4);
    xlwrite(jeremy_barry, celldataj, 'AmpCorr Data', XLcellrange5);

end;
           

fclose all;
% 
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/poi-3.8-20120326.jar');
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/poi-ooxml-3.8-20120326.jar');
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/poi-ooxml-schemas-3.8-20120326.jar');
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/xmlbeans-2.3.0.jar');
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/dom4j-1.6.1.jar');
