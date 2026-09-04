% Cscfile2 : class to read *.ncs (Neuralynx EEG file) file by part
%exemple : read file from 2s to 10s (get 8 s long recording)
% myfile=myfile.setstart(2);
%myfile=myfile.setrange(8);
%   % optional setup :
%    myfile=myfile.setfiltertype("cheby2"); %or "fir1"
%    myfile=myfile.setlowpass(5000);    lowpass at 5000Hz
%    myfile=myfile.sethighpass(500);    highpass at 500Hz
% myfile=myfile.readdata();
% %start time could be change if you are voer the file limit
% realstart = myfile.start;
% % to read eeg :  myfile.Samples
% % acquisition frequency :  myfile.SF
% % acquisition frequency :  myfile.SF
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
classdef Cscfile2
    
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
            for i=1:4 %was 4 changed to 9 for Cheetah 2019, discovered by Willie C.Or is it 33?
                header=fgetl(this.fid);
            end
            for i=1:24%was 23 or 24, oct 2020, removed the fgetl from above and changed to 29 for old cheetah files, which I never understood the purpose of and only messes things up with older cheetah settings
                [prop,value]=fscanf(this.fid,'%s/n',this.header_sz);
                %                 prop
                switch prop
                    case '-AcqEntName',
                        this.AcqEntName=fscanf(this.fid,'%s/n',this.header_sz);
                    case '-NLX_Base_Class_Name'
                        this.AcqEntName=fscanf(this.fid,'%s/n',this.header_sz);
                    case '-SamplingFrequency',
                        this.SF=fscanf(this.fid,'%f/n',this.header_sz);
                    case '-ADMaxValue',
                        this.ADMaxVal=fscanf(this.fid,'%f/n',this.header_sz);
                    case '-ADBitVolts',
                        this.ADbitVolts=fscanf(this.fid,'%f/n',this.header_sz);
                    case '-InputInverted',
                        this.Inverted=fscanf(this.fid,'%s/n',this.header_sz);
                        if strcmpi( this.Inverted,'True')
                            this.Inverted=1;
                            this.readmodeinvert=1;
                        else
                            this.Inverted=0;
                            this.readmodeinvert=0;
                        end
                    case '-SubSamplingInterleave',
                        this.SubSamplingInterleave=fscanf(this.fid,'%f/n',this.header_sz);
                    otherwise
                        fscanf(this.fid,'%s/n',this.header_sz);
                end
            end
        end
        function this=Cscfile2(filename)
            if nargin < 1
                this.name='none';
            else
                this.name=filename;
                this.highpass=0;
                this.lowpass=0;
                this.notch=0;
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
                            n=2;
                            %ampli
                            R=20;
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
                            n=2;
                            %ampli
                            R=20;
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
                            n=2;
                            %ampli
                            R=20;
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