   function []=JeremyEEG4();
% a template to perform analyses on plenty of files

path_xls='/Users/jeremybarry/Documents/UVM/projects/PTEN/PTENDREADD/Lists/CFC/';
path_out='/Users/jeremybarry/Documents/UVM/projects/PTEN/PTENDREADD/Output/CFC/';
cd (path_xls);
[data,txt] =  xlsread('EEGData.xlsx');
qqq=txt(1:2,:);
txt(1:2,:)=[];

for i = 1:size(data,1);
    h=figure
    ratId = txt{i,2};
    eegnum = data(i,3);
    SessID1 = txt{i,4};
    Path1 = cell2mat(txt(i,5));
    Cond = txt{i,6};
    Group = txt{i,7};
    file1 = cell2mat(txt(i,8));
    Side = txt{i,9};
    Layer = txt{i,10};
    bof = data(i,11);
    eof = data(i,12); 
    %Use due dilligence on bof and eof from xplorefinder. Make sure by
    %subtracting both from EEGTs(1), and from each other to make sure
    %there's no negative number
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    %Block 1 only
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    disp(['Treating Rat ', ratId, ' EEG',num2str(eegnum,'%d'),' session ', SessID1])
    if ~isempty(Path1)
        if exist(Path1)
            cd (Path1);
            
            % Read eeg file in data path
            [RecSz,SampleFrequencies,EEGTs,EEG]=read_csc (file1,10);
            %number after file is added subsampling, use 5 for SWR's
        else
            disp('path does not exist')

        end;
        
    else
        disp('empty path')
        
    end;
    %%
    Segment=EEGTs <= eof & EEGTs >= bof;
    EEGTs2=EEGTs(Segment);
    EEG2=EEG(Segment');
  
%%
    %%FFT standard spectrogram analysis
    SF=SampleFrequencies;
    [Sspect,fspect,tspect] = spectrogram((double(EEG2)),round(SF),round(SF/2),[0.1:.2:200],SF);%Upper Limit was 140

     Spectro=10*log10(abs(Sspect).^2); % (10log10 is dB)
     SpecPSD=abs(Sspect).^2;  

     fspectplot=fspect(1:71,:);
     Spectroplot=Spectro(1:71,:);
     SpecPSDplot=SpecPSD(1:71,:);
     
      figure(h)
      subplot(4,2,1:2)
      plot(EEGTs2,EEG2)
      axis xy
      hold on
      ylabel('Voltage(microV)')
      title('Segement Timestamps')
      set(gca,'XLim',[EEGTs2(1) max(EEGTs2)]); grid on;
      
      subplot(4,2,5:6)
      imagesc(tspect,fspectplot,Spectroplot)
      colorbar
      colormap (jet)
      axis xy
      hold on
      xlabel('Time(secs)')
      ylabel('Frequency(Hz)')
      title(['Power Spectrum ', 'Mouse', ratId,' EEG',num2str(eegnum,'%d'),'  ', SessID1,'  ', Layer])
 
      subplot(4,2,7)
      plot(fspectplot, mean(Spectroplot,2))
      xlabel('Frequency(Hz)')
      ylabel('Amplitude (A.U.)')
      xlim([0 15]);
      set(gca,'xtick',0:2:15)
      title('dB')    

      subplot(4,2,8)
      plot(fspectplot, mean(SpecPSDplot,2))
      xlabel('Frequency(Hz)')
      ylabel('Amplitude (A.U.)')
      xlim([0 15]);
      set(gca,'xtick',0:2:15)
      title('PSD')  
      
      OverallMean_dB=mean(Spectro(1:1000,:),2);
      OverallMean_PSD=mean(SpecPSD(1:1000,:),2);
      TheThetaF= fspect(1:1000);
      
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
     filename = num2str(eegnum);
     print(h, '-dpsc', fullfile(path_out,filename));
        close(h);
    Spectromn=mean(Spectro,2);
   
    Thetafreq=tspect;
    Thetatempf=fspect(fspect>=4 & fspect<=12);
    
    Gammafreq=tspect;
    Gammatempf=fspect(fspect>=30 & fspect<=50);
    
    HGammafreq=tspect;
    HGammatempf=fspect(fspect>=70 & fspect<=90);
     
    for ii=1:length(tspect)
        % normalize power value by the sum of spectrum
        Spectro(:,ii)=Spectro(:,ii)./sum(Spectro(:,ii));
        
        % find theta freq peak for all i's
        tmpMaxTheta=(find(Spectro(fspect>=4 & fspect<=12,ii)==max(Spectro(fspect>=4 & fspect<=12,ii))));
        Thetafreq(ii)=Thetatempf(tmpMaxTheta);
        
        % find gamma freq peak for all i's
        tmpMaxGamma=(find(Spectro(fspect>=30 & fspect<=50,ii)==max(Spectro(fspect>=30 & fspect<=50,ii))));
        Gammafreq(ii)=Gammatempf(tmpMaxGamma);
        
        % find high gamma freq peak for all i's
        tmpMaxHGamma=(find(Spectro(fspect>=70 & fspect<=90,ii)==max(Spectro(fspect>=70 & fspect<=90,ii))));
        HGammafreq(ii)=HGammatempf(tmpMaxHGamma);
       
    end;
   
   if length(Spectromn)>1
        ThetaNormA=sum(Spectromn(find(fspect>=4 & fspect<=12)));
        ThetaNormB= ThetaNormA/(sum(Spectromn));
        
        GammaNormA= sum(Spectromn(find(fspect>=30 & fspect<=50)));
        GammaNormB=GammaNormA/(sum(Spectromn));
        
        HGammaNormA= sum(Spectromn(find(fspect>=70 & fspect<=90)));
        HGammaNormB=HGammaNormA/(sum(Spectromn));
        
    else
        ThetaNormB=nan;
        GammaNormB=nan;
        HGammaNormB=nan;

    end;
       
    %Peak thetaFreq calc for dB
    f2=fspect(fspect>=4 & fspect<=12);
        SmaxThetadB=max (Spectromn(fspect>=4 & fspect<=12));
        PkThetadB = f2(find(Spectromn(fspect>=4 & fspect<=12)==SmaxThetadB));
    %slow GammaFreq calculation
    f3=fspect(fspect>=30 & fspect<=50);
        SmaxGdB=max (Spectromn(fspect>=30 & fspect<=50));
        PkGammadB = f3(find(Spectromn(fspect>=30 & fspect<=50)==SmaxGdB));
    %fast GammaFreq calculation    
    f4=fspect(fspect>=70 & fspect<=90);
        SmaxHGdB=max (Spectromn(fspect>=70 & fspect<=90));
        PkHGammadB=f4(find(Spectromn(fspect>=70 & fspect<=90)==SmaxHGdB));
    
    
    TFreqMn=mean(Thetafreq);
    TFreqSd=std(Thetafreq);
    GFreqMn=mean(Gammafreq);
    GFreqSd=std(Gammafreq);
    HGFreqMn=mean(HGammafreq);
    HGFreqSd=std(HGammafreq);
    
    %% 
        Sf=mean(SpecPSD,2);% use SpecPSD for averages of 'power'
        
    %Peak thetaFreq calc for PSD
    f2=fspect(fspect>=4 & fspect<=12);
        SmaxThetaPSD=max (Sf(fspect>=4 & fspect<=12));
        PkThetaPSD = f2(find(Sf(fspect>=4 & fspect<=12)==SmaxThetaPSD));
        
    %slow GammaFreq calculation
    f3=fspect(fspect>=30 & fspect<=50);
        SmaxGPSD=max (Sf(fspect>=30 & fspect<=50));
        PkGammaPSD = f3(find(Sf(fspect>=30 & fspect<=50)==SmaxGPSD));
     
    %fast GammaFreq calculation    
    f4=fspect(fspect>=70 & fspect<=90);
        SmaxHGPSD=max (Sf(fspect>=70 & fspect<=90));
        PkHGammaPSD=f4(find(Sf(fspect>=70 & fspect<=90)==SmaxHGPSD));
 
   cd (path_out)
   
   Specs{1,:}=SessID1;
   Specs{2,:}=eegnum;
   Specs{3,:}=OverallMean_dB;
   save([num2str(eegnum),num2str(SessID1),'Specs2.mat'],'Specs');
   
   % variables=[{ratId},{Group}, num2str(eegnum)];
   
    columnheaders1={'Frequency','OverallMean_dB','OverallMean_PSD','ratid', 'group', 'eegnum'};
         
    columnheaders2={'ratId', 'Group', 'EEGNum', 'Cell region','Cond', 'SessID1',... 
        'TFreqMn','TFreqSd','PkThetadB','ThetaNorm','MaxTPwerdB','PkThetaPSD', 'MaxTPwerPSD',...
        'SGFreqMn','SGFreqSd','PkSGammadB','SGammaNorm','MaxSGPwerdB','PkSGammaPSD','MaxSGPwerPSD',...
        'MGFreqMn','MGFreqSD','PkMGammadB','MGammaNorm','MaxMGPwerdB','PkMGammaPSD','MaxMGPwerPSD'};
     
    celldatajb=[TheThetaF,OverallMean_dB,OverallMean_PSD,string(repmat({ratId},1000,1)),string(repmat({Group},1000,1)),string(repmat(num2str(eegnum),1000,1))];
    
    celldataj=[{ratId},{Group}, num2str(eegnum),{Layer},{Cond},{SessID1},... 
        num2str(TFreqMn),num2str(TFreqSd),num2str(PkThetadB),num2str(ThetaNormB),num2str(SmaxThetadB),num2str(PkThetaPSD),num2str(SmaxThetaPSD),...
        num2str(GFreqMn),num2str(GFreqSd),num2str(PkGammadB),num2str(GammaNormB),num2str(SmaxGdB),num2str(PkGammaPSD),num2str(SmaxGPSD),...
        num2str(HGFreqMn),num2str(HGFreqSd),num2str(PkHGammadB),num2str(HGammaNormB),num2str(SmaxHGdB), num2str(PkHGammaPSD),num2str(SmaxHGPSD)];
    
    XLcellrange1=strcat('A',num2str((1001*i)-1000),':F', num2str(1001*i)); %define range in celldataj 
    XLcellrange2=strcat('A',num2str(i),':AA', num2str(i)); %define range in celldataj
    
    jeremy_barry1=('MeanTheta.xlsx');
    xlwrite(jeremy_barry1, columnheaders1,'Column Key1');
    xlwrite(jeremy_barry1, celldatajb, 'MeanTheta', XLcellrange1);
    
    jeremy_barry2=('spectral_props.xlsx');
    xlwrite(jeremy_barry2, columnheaders2,'Column Key');
    xlwrite(jeremy_barry2, celldataj, 'EEG_data', XLcellrange2);
    
end;
           
fclose all;
% 
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/poi-3.8-20120326.jar');
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/poi-ooxml-3.8-20120326.jar');
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/poi-ooxml-schemas-3.8-20120326.jar');
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/xmlbeans-2.3.0.jar');
% javaaddpath('/Users/jeremybarry/Documents/matlab/matlabProgs/FileHandling/poi_library/dom4j-1.6.1.jar');
