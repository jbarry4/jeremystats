% Cscfile2 : class to read *.ncs (Neuralynx EEG file) file by part
%exemple : read file from 2s to 10s (get 8 s long recording)
% myfile=myfile.setstart(2);
%myfile=myfile.setrange(8);
%   % optional setup :
%    myfile=myfile.setfiltertype("cheby2"); %or "fir1"


%    myfile=myfile.setlowpass(5000);    lowpass at 5000Hz
%    myfile=myfile.sethighpass(500);    highpass at 500Hz
% myfile=myfile.readdata();
% myfile.Samples contain the eeg infos
%[myfile,TS]= getTS;
%   TS and myfile.TS will be fill with the timestamps of each samples

% %start time could be change if you are voer the file limit
% realstart = myfile.start;
% % to read eeg :  myfile.Samples
% % acquisition frequency :  myfile.SF
% % acquisition frequency :  myfile.SF

%myfile=myfile.setchebyprop( orderN,ampliR) can be use to set order and
%amplification o your cheyby filter default value order= 2 ampli=20
%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%% Formats ncs %%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%
%  ts='uint64';%8bytes    %
%  chnum='uint32';%4      %
%  SF='uint32';%4         %
%  numsamples='uint32';%4 %
%  sample='int16';%512*2  %
% total=1044              %
%%%%%%%%%%%%%%%%%%%%%%%%%%%
classdef Cscfile2_PP
    
    properties (SetAccess=private)
        startchunk=0;
        start=0;
        filter='cheby2';
        %filter='fir1';
        rangechunck=inf;
        range=inf;
        Downsampling=1;
        data
        name
        
        
    end
    properties (GetAccess=private)
        
    end
    properties (Constant)
        header_sz=16384;
        
    end
    properties (Dependent)
    end
    properties (SetAccess = public)
        
        fid
        %file name
        AcqEntName
        % acquisition frequency
        SF
        SubSamplingInterleave
        % sampling frequency after filtering and automatic resampling
        currentSF
        %option Input invert
        Inverted
        readmodeinvert
        ADMaxVal
        ADbitVolts
        filesize
        nbenchant
        cheybyn
        cheybyR
        % lowpass value
        lowpass
        %haighpass value
        highpass
        TS
        firstttimestamps
        timestamps
        headinfos
        % EEG data extracted
        Samples
        % full recording time
        filerecordtotaltime
        
        %define if Sample reading param changed from the last reading
        changereaddataparam
        notch
    end
    methods
        function this=ReadHeader(this)
            header_sz=16384;
            
            %%%%%%%%%%%%%%%%%%%%%%%%%%%
            
            headernum=fscanf(this.fid,'%c',header_sz);
            returns=find(headernum==13);
            header=cell(length(returns),1);
            
            for i=2:length(returns)-1
                header{i}=char(headernum(returns(i):returns(i+1)-1));
            end
            header{1}=char(headernum(1:returns(1)));
            header{end}=char(headernum(returns(end):end));
            
            %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
            
            
            %%%%%%
            whereSF=strfind(header,'SamplingFrequency' );
            for k=1:length(whereSF)
                if ~isempty(whereSF{k}), myline=k; end;
            end
            
            
            SF=char(header(myline));
            blancs=strfind(SF, 'y');
            this.SF=str2double(SF(blancs(1)+1:end));
            
            %%%
            whereAcqName=strfind(header,'-AcqEntName' );
            for k=1:length(whereAcqName)
                if ~isempty(whereAcqName{k}), myline=k; end;
            end
            
            
            
            AcqName=char(header(myline));
            blancs=strfind(AcqName,'e');
            this.AcqEntName=(AcqName(blancs+1:end));
%             this.ADMaxVal=str2double(AcqName(blancs+1:end));
            
            %%%
            
            whereIInv=strfind(header,'-InputInverted');
            for k=1:length(whereIInv)
                if ~isempty(whereIInv{k}), myline=k; end;
            end
            
            IInv=char(header(myline));
            blancs=strfind(IInv,'d');
            this.Inverted=IInv(blancs+1:end);
            
            if strcmpi( this.Inverted,'True')
                this.Inverted=1;
                this.readmodeinvert=1;
            else
                this.Inverted=0;
                this.readmodeinvert=0;
            end
            
            %%%
            whereAD=strfind(header,'ADMaxValue' );
            for k=1:length(whereAD)
                if ~isempty(whereAD{k}), myline=k; end;
            end
            
            
            
            ADMaxVal=char(header(myline));
            blancs=strfind(ADMaxVal,'e');
%             this.ADMaxVal=(ADMaxVal(blancs+1:end));
            this.ADMaxVal=str2double(ADMaxVal(blancs+1:end));
            
            %%%
            % whereBCN=strfind(header,'-NLX_Base_Class_Name' );
            % for k=1:length(whereBCN)
            % if ~isempty(whereBCN{k}), myline=k; end;
            % end
            %
            %
            % %
            % BCN=char(header(myline));
            % blancs=strfind(BCN,'e',1,'last');
            % this.AcqEntName=str2double(BCN(blancs+1:end));
            %
            
            
            %%%
            whereAD2=strfind(header,'ADBitVolts' );
            for k=1:length(whereAD2)
                if ~isempty(whereAD2{k}), myline=k; end;
            end
            
            
            ADbitVolts=char(header(myline));
            blancs=strfind(ADbitVolts,'s');
            this.ADbitVolts=str2double(ADbitVolts(blancs+1:end));
            found=0;
            whereSubSpl=strfind(header,'-SubSamplingInterleave' );
            for k=1:length(whereSubSpl)
                if ~isempty(whereSubSpl{k}), myline=k; found=1;end;
            end
            
            if found ==1
                
                Interleave=char(header(myline));
                blancs=strfind(Interleave,'ve');
                this.SubSamplingInterleave=str2double(Interleave(blancs+2:end));
                
                %     if SF>=30000
                %
                %     SF=SF/Interleave;
                %     end
            end;
            
            
            %%%
            
            
            %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
            %             for i=1:4
            %                 header=fgetl(this.fid);
            %             end
            %             for i=1:24
            %                 [prop,value]=fscanf(this.fid,'%s/n',this.header_sz);
            %                 %                 prop
            %                 switch prop
            %                     case '-AcqEntName',
            %                         this.AcqEntName=fscanf(this.fid,'%s/n',this.header_sz);
            %                     case '-NLX_Base_Class_Name'
            %                         this.AcqEntName=fscanf(this.fid,'%s/n',this.header_sz);
            %                     case '-SamplingFrequency',
            %                         this.SF=fscanf(this.fid,'%f/n',this.header_sz);
            %                     case '-ADMaxValue',
            %                         this.ADMaxVal=fscanf(this.fid,'%f/n',this.header_sz);
            %                     case '-ADBitVolts',
            %                         this.ADbitVolts=fscanf(this.fid,'%f/n',this.header_sz);
            %                     case '-InputInverted',
            %                         this.Inverted=fscanf(this.fid,'%s/n',this.header_sz);
            %                         if strcmpi( this.Inverted,'True')
            %                             this.Inverted=1;
            %                             this.readmodeinvert=1;
            %                         else
            %                             this.Inverted=0;
            %                             this.readmodeinvert=0;
            %                         end
            %                     case '-SubSamplingInterleave',
            %                         this.SubSamplingInterleave=fscanf(this.fid,'%f/n',this.header_sz);
            %                     otherwise
            %                         fscanf(this.fid,'%s/n',this.header_sz);
            %                 end
            %             end
        end
        function this=Cscfile2_PP(filename)
            if nargin < 1
                this.name='none';
            else
                this.name=filename;
                this.highpass=0;
                this.lowpass=0;
                this.notch=0;
                this.cheybyn=2;
                this.cheybyR=20;
                this.Inverted=NaN;
                this.SubSamplingInterleave=1;
                this.fid=fopen(this.name,'r');
                this=this.ReadHeader();
                if this.SubSamplingInterleave~=1
                    this.SF= this.SF/this.SubSamplingInterleave;
                end
                this.currentSF=this.SF;
                fseek(this.fid,0,'eof');
                this.filesize = ftell(this.fid);
                this.changereaddataparam=1;
                
                this.rangechunck = ((this.filesize-this.header_sz)/(20+512*2));
                this.nbenchant = this.rangechunck*512;
                
                this.filerecordtotaltime=this.nbenchant*(1/this.SF);
                this.range = this.filerecordtotaltime;
                
                fseek(this.fid,this.header_sz,'bof');
                this.firstttimestamps=fread(this.fid,1,'uint64');
                
            end
            %             'total'
            %             this.nbenchant/this.SF
        end
        function this = setchebyprop(this, orderN,ampliR)
            this.cheybyn=orderN;
            this.cheybyR=ampliR;
        end
        function this = setfiltertype(this, type)
            if ~strcmp(type,this.filter)&& (strcmp(type,'cheby2') || strcmp(type,'fir1')|| strcmp(type,'med'))
                this.filter=type;
                this.changereaddataparam=1;
            end
        end
        function this = sethighpass(this,high)
            old= this.highpass;
            if high<0
                this.highpass=0;
            elseif high>this.SF/2
                this.highpass=this.SF/2;
            else
                this.highpass=high;
            end
            if old~= this.highpass
                this.changereaddataparam=1;
            end
        end
        function this = setrange(this,range)
            
            
            old=this.range;
            
            if(range<=0)
                this.range=1;
            elseif range>this.filerecordtotaltime
                this.range=this.filerecordtotaltime;
            else
                this.range=range;
            end
            if old~= this.range
                this.changereaddataparam=1;
            end
        end
        
        function this = setstart(this,start)
            if this.start~=start
                if(start>=0)
                    this.start=start;
                    this.changereaddataparam=1;
                else
                    this.start=0;
                    this.changereaddataparam=1;
                end
            end
        end
        %         function this = setDonwnsampling(this,Downsampling)
        %             this.currentSF=this.SF/Downsampling;
        %             this.Downsampling=Downsampling;
        %         end
        
        %         function this = getDonwnsampling(this,Downsampling)
        %             this.currentSF=this.SF/Downsampling;
        %             this.Downsampling=Downsampling;
        %         end
        function this = setlowpass(this,lowpass,nosampling)
            if nargin < 3
                nosampling = 0;
            end
            if this.lowpass~=lowpass || (this.Downsampling~=1 &&nosampling~=0 )
                this.lowpass=lowpass;
                this.changereaddataparam=1;
                if lowpass==0 || ((this.SF/lowpass)/4)<1 || nosampling
                    this.Downsampling=1;
                else
                    this.Downsampling=floor((this.SF/lowpass)/4);
                end
                this.currentSF=this.SF/this.Downsampling;
            end
        end
        function [this,TS]= getTS(this)
            tsstartread=(this.start*1E6)+this.firstttimestamps;
            TS=[tsstartread:(1/this.currentSF)*1E6:tsstartread+this.range*1E6-(1/this.currentSF)*1E6];
            this.TS=TS;
        end
        function this= readdata(this,novolt,nofilter)
            if nargin <2
                novolt = 0;
                nofilter=0;
            elseif nargin <3
                nofilter=0;
            end
            if  this.changereaddataparam==1 || novolt || nofilter
                this.Samples=[];
                %                 this.range =ceil(this.range/(512*(1/this.SF)));
                
                this.startchunk =floor(this.start/(512/this.SF));
                startdelaysec=this.start -(this.startchunk*(512/this.SF) );
                this.rangechunck =ceil((this.range+startdelaysec)/(512*(1/this.SF)));
                
                %                 if this.start>0
                %                     this.start = this.start -1;
                %                 end
                
                if (this.startchunk+this.rangechunck)*512>this.nbenchant
                    this.startchunk=this.startchunk-((this.startchunk+this.rangechunck)-(this.nbenchant/512));
                    this.start=(this.startchunk*(512/this.SF) )+startdelaysec;
                end
                %this.TS=fread(this.fid,'uint64',1036)
                offset=(20+(512*2))*this.startchunk;
                fseek(this.fid,this.header_sz+offset,'bof');
                %             this.timestamps= fread(this.fid,1,'uint64');
                %             this.headinfos=fread(this.fid,3,'uint32');
                %cpt=this.range;
                % while ~feof(this.fid)&& cpt>0
                this.timestamps=fread(this.fid,1,'uint64');
                this.headinfos=fread(this.fid,3,'uint32');
                this.Samples=fread(this.fid,512*this.rangechunck,'512*int16=>int16',20);
                if novolt
                    this.Samples=double(this.Samples);
                else
                    this.Samples=double(this.Samples).*(this.ADbitVolts*1E6);
                end
                if ~nofilter
                    if this.lowpass>0 && this.lowpass <round(this.SF/2)
                        if this.highpass <=0 || this.highpass >=round(this.SF/2)
                            %order
                            n=this.cheybyn;
                            %ampli
                            R=this.cheybyR;
                            %band filter
                            Wst=this.lowpass/round(this.SF/2);
                            %                     disp('wst low');
                            %                     disp(Wst*this.SF);
                            if strcmp(this.filter,'cheby2')
                                [b,a] = cheby2(n,R,Wst,'low');
                            else
                                b = fir1(150,Wst,'low');
                                a=1;
                            end
                        else
                            %order
                            n=this.cheybyn;
                            %ampli
                            R=this.cheybyR;
                            %band filter
                            Wst=[ this.highpass/round(this.SF/2), this.lowpass/round(this.SF/2)];
                            %                     disp('wst band');
                            %                     disp(Wst*this.SF);
                            if strcmp(this.filter,'cheby2')
                                [b,a] = cheby2(n,R,Wst );
                            elseif strcmp(this.filter,'fir1')
                                b = fir1(150,Wst);
                                a=1;
                            elseif strcmp(this.filter,'besself')
                                
                                [b,a]=besself(20,Wst);
                                [numd,dend]=bilinear(num,den,Fs);
                                
                            end
                        end
                        %                     figure
                        %                               [h,w] = freqz(b,1,128);
                        %                               h = fvtool(b,a);
                        %                               plot(w/pi,abs(h))
                        if ~strcmp(this.filter,'med')
                            this.Samples=filtfilt(b,a,this.Samples);
                        else
                            ss=medfilt1(this.Samples,this.SF*2*1E-3);
                            this.Samples=this.Samples-ss;
                        end
                        %this.Samples=filtfilt(b,a,this.Samples);
                        if this.Downsampling~=1
                            this.Samples=this.Samples(1:this.Downsampling:end);
                            %this.Samples=resample(this.Samples,1,this.Downsampling);
                        end
                    else
                        if this.highpass >0 && this.highpass <round(this.SF/2)
                            n=this.cheybyn;
                            %ampli
                            R=this.cheybyR;
                            %band filter
                            Wst=this.highpass/round(this.SF/2);
                            %                     disp('wst high');
                            %                     disp(Wst*this.SF);
                            if strcmp(this.filter,'cheby2')
                                [b,a] = cheby2(n,R,Wst,'high' );
                            else
                                %                                 f = [0 Wst Wst 1]; m = [ 0 0 1 1];
                                %                                 b = fir2(30,f,m);
                                b = fir1(150,Wst,'high');
                                a=1;
                            end
                            
                            %                         h = fvtool(b,a);
                            
                            this.Samples=filtfilt(b,a,this.Samples);
                        end
                    end
                    
                    if this.notch
                        wo = 60/round(this.currentSF/2);  bw = wo/35;
                        [b,a] = iirnotch(wo,bw);
                        %                         fvtool(b,a);
                        this.Samples=filtfilt(b,a,this.Samples);
                    end
                else
                    %% high pass fix
                    %                      n=2;  R=20;
                    %                             Wst=300/round(this.SF/2);
                    %                             [b,a] = cheby2(n,R,Wst,'high' );
                    %                             this.Samples=filtfilt(b,a,this.Samples);
                    %% medpass fix
                    %                        ss=medfilt1(this.Samples,this.SF*3*1E-3);
                    %                        this.Samples=this.Samples-ss;
                    
                    
                end
                
                startdelay=startdelaysec* this.currentSF;
                %                 endelay= ((this.range+startdelaysec) -this.range*512*(1/this.SF) )* this.currentSF;
                %                 endelay=length(this.Samples)+endelay;
                
                endelay=min(this.range*this.currentSF+startdelay, length(this.Samples));
                if round(this.range*this.currentSF)> length(this.Samples)
                    disp('Warning : possible error on the number of sample');
                end
                
                this.Samples=this.Samples(round(startdelay)+1:round(endelay));
                
                if this.Inverted ~= this.readmodeinvert
                    this.Samples=this.Samples*-1;
                end
                
                
                if novolt||nofilter
                    this.changereaddataparam=1;
                end
            end
        end
        
        function delete(this)
            try
                fclose(this.fid);
            catch
            end
        end
    end
end