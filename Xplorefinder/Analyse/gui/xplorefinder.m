function varargout = xplorefinder(varargin)
% XPLOREFINDER MATLAB code for xplorefinder.fig
%      XPLOREFINDER, by itself, creates a new XPLOREFINDER or raises the existing
%      singleton*.
%
%      H = XPLOREFINDER returns the handle to a new XPLOREFINDER or the handle to
%      the existing singleton*.
%
%      XPLOREFINDER('CALLBACK',hObject,eventData,handles,...) calls the local
%      function named CALLBACK in XPLOREFINDER.M with the given input arguments.
%
%      XPLOREFINDER('Property','Value',...) creates a new XPLOREFINDER or raises the
%      existing singleton*.  Starting from the left, property value pairs are
%      applied to the GUI before xplorefinder_OpeningFcn gets called.  An
%      unrecognized property name or invalid value makes property application
%      stop.  All inputs are passed to xplorefinder_OpeningFcn via varargin.
%
%      *See GUI Options on GUIDE's Tools menu.  Choose "GUI allows only one
%      instance to run (singleton)".
%
% See also: GUIDE, GUIDATA, GUIHANDLES

% Edit the above text to modify the response to help xplorefinder

% Last Modified by GUIDE v2.5 02-Feb-2015 11:02:33

% Begin initialization code - DO NOT EDIT
gui_Singleton = 0;
gui_State = struct('gui_Name',       mfilename, ...
    'gui_Singleton',  gui_Singleton, ...
    'gui_OpeningFcn', @xplorefinder_OpeningFcn, ...
    'gui_OutputFcn',  @xplorefinder_OutputFcn, ...
    'gui_LayoutFcn',  [] , ...
    'gui_Callback',   []);
if nargin && ischar(varargin{1})
    gui_State.gui_Callback = str2func(varargin{1});
end

if nargout
    [varargout{1:nargout}] = gui_mainfcn(gui_State, varargin{:});
else
    gui_mainfcn(gui_State, varargin{:});
end
% End initialization code - DO NOT EDIT


% --- Executes just before xplorefinder is made visible.
function xplorefinder_OpeningFcn(hObject, eventdata, handles, varargin)
% This function has no output args, see OutputFcn.
% hObject    handle to figure
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
% varargin   command line arguments to xplorefinder (see VARARGIN)

% Choose default command line output for xplorefinder
handles.output = hObject;
%handles.compress=100;
handles.lowpass=0;
handles.range=10;
handles.start=0;
handles.TSfirstpoint=0;
handles.endtime=10;
handles.linedelmode=0;
handles.EEGloaded=0;
handles.highpass=0;
handles.stepmmin =0 ;
handles.EEGylim=0;
handles.arrowpointer=load('xplorcursorarrow.mat');
handles.arrowpointer=handles.arrowpointer.cur;
handles.currentctrlaxe =1;
handles.eeginverted=0;

handles.CSD =0 ;

set(handles.editlow,'String',handles.lowpass)
%set(handles.dnsampletxt,'String',handles.compress)
%set(handles.slidercompress,'Value',handles.compress);

% Update handles structure
guidata(hObject, handles);

% UIWAIT makes xplorefinder wait for user response (see UIRESUME)
% uiwait(handles.figure1);

% --- Outputs from this function are returned to the command line.
function varargout = xplorefinder_OutputFcn(hObject, eventdata, handles)
% varargout  cell array for returning output args (see VARARGOUT);
% hObject    handle to figure
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Get default command line output from handles structure
varargout{1} = handles.output;


% --- Executes on button press in open file button.
function pushbutton1_Callback(hObject, eventdata, handles)
% hObject    handle to pushbutton1 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
%global Data
[name, path]=uigetfile({'*.ncs;*.ntt;*.nvt;*.nev;*.nse;*.dat;*.NCS;*.NTT;*.NVT;*.NEV;*.NSE;*.txt;*.xls;*.csv;*.mpg'},'Select ALL Files','Multiselect','on');
if ~isequal(name,0)
    %% ncs files in first
    if ~iscell(name)
        name2=cell(1,1);
        name2{1,1}=name;
        name=name2;
    else
        ncstype=zeros(1,length(name));
        for i = 1:length(name)
            if ~isempty(strfind(lower(char(name{i})),'.ncs'))
                ncstype(i)=1;
            end
        end
        fncs=find(ncstype==1,1,'first');
        if ~isempty(fncs)
            lastncs=find(ncstype(fncs:end)==0,1,'first')+fncs-2;
            if isempty(lastncs)
                lastncs=length(ncstype);
            end
            name=[name(fncs:lastncs)  name(1:fncs-1) name(lastncs+1:end)];
        end
    end
    %% order CSCxx.csc file by number order
    [filenumber,match]=regexp(name,'^CSC[^0-9]*([0-9]*)[^0-9]*\.n[cs]{1}[se]{1}$','tokens');
    filenumber=[filenumber{:}];
    filenumber=str2double([filenumber{:}]);
    [~,IX] =sort(filenumber);
    tmpname=name;
    cpt=1;
    for idname=1:length(match)
        if match{idname}
            tmpname(cpt)=name(IX(cpt));
            cpt=cpt+1;
        end
    end
    name=tmpname;
    
    %%
    
    Data=guidata(gcbf);
    if(Data.EEGloaded==1)
        %reset data for open news files
        bts =get(Data.uipanelCtrlSig,'children');
        for i=1:length(bts)
            if bts(i)~=Data.pushbtnextgraphctrl &&bts(i)~=Data.pushbtprevgraphctrl&& bts(i)~=Data.btremovefile && bts(i)~=Data.pushbtsavegraph&& bts(i)~=Data.btaddfile
                delete(bts(i));
            end
        end
        
        if isfield(Data,'ctrlsig')
            for i=1:length(Data.ctrlsig)
                SNames = fieldnames(Data.ctrlsig(i));
                for loopIndex = 1:numel(SNames)
                    if ishandle(Data.ctrlsig(i).(SNames{loopIndex}))
                        delete(Data.ctrlsig(i).(SNames{loopIndex}));
                    end
                    if strcmp(SNames{loopIndex},'clustprop') && ~isempty(Data.ctrlsig(i).(SNames{loopIndex}))
                        for subcell=1:length(Data.ctrlsig(i).(SNames{loopIndex}))
                            if ishandle(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.edit);
                                delete(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.edit);
                            end
                            if ishandle(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.checkmark);
                                delete(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.checkmark);
                            end
                            if ishandle(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.name);
                                delete(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.name);
                            end
                        end
                    end
                    
                end
            end
            
            Data = rmfield( Data,{'ctrlsig'});
        end
        if isfield(Data,'file')
            for ifile=1:length(Data.file)
                %                 if Data.xtraFileData(ifile).duplicate<1
                delete(Data.file(ifile));
                %                 end
            end
            Data = rmfield( Data,{'file'});
        end
        if isfield(Data,'filentt')
            Data = rmfield( Data,{'filentt'});
        end
        if isfield(Data,'filenvt')
            Data = rmfield( Data,{'filenvt'});
        end
        if isfield(Data,'xtraFileData')
            Data = rmfield( Data,{'xtraFileData'});
        end
        
        if isfield(Data,'spkypesrch')
            Data = rmfield( Data,{'spkypesrch'});
        end
        if isfield(Data,'ax')
            Data = rmfield( Data,{'ax'});
        end
        if isfield(Data,'axftt')
            Data = rmfield( Data,{'axftt'});
        end
        if isfield(Data,'posnvt')
            Data = rmfield( Data,{'posnvt'});
        end
        
        
        Data.TSfirstpoint=0;
        Data.currentctrlaxe =1;
    else
        Data.EEGloaded=1;
    end
    
    Data.Path=path;
    cd (path)
    
    %type asignement
    nbfile=length(name);
    for i = 1:length(name)
        if ~isempty(strfind(lower(char(name{i})),'.ntt'))
            ftype='ntt';
        elseif ~isempty(strfind(lower(char(name{i})),'.nse'))
            ftype='nse';
        elseif ~isempty(strfind(lower(char(name{i})),'.ncs'))
            ftype='ncs';
        elseif ~isempty(strfind(lower(char(name{i})),'.nvt'))
            ftype='nvt';
        elseif ~isempty(strfind(lower(char(name{i})),'.dat'))
            ftype='dat';
        elseif ~isempty(strfind(lower(char(name{i})),'.mpg'))
            ftype='mpg';
        elseif ~isempty(strfind(lower(char(name{i})),'.nev'))
            ftype='nev';
        elseif ~isempty(strfind(lower(char(name{i})),'.txt')) ||~isempty(strfind(lower(char(name{i})),'.csv'))||~isempty(strfind(lower(char(name{i})),'.xls'))
            ftype='txt';
            
        end
        Data.xtraFileData(i)=struct('name','','height',5,'viewfft',0,'viewgraph',1,'ftype',ftype,'lowpass',0,'highpass',0,'frame_length',0,'frame_overlap',0,'zoom',1,'nlyzminf',0,'nlyzmaxf',200,'duplicate',0,'correlationeeg',[]);
        Data.spkypesrch(i)=struct('moreth',40,'closerth',2,'activate',0,'min',0,'max',1);
        
        %Data.file.name(i)
        
        %read file create resource data for each file, informations depends
        %of the file type
        %and initial timestamps initialisation
        switch ftype
            case {'nvt','dat'}
                if strcmp(ftype,'dat')
                    [~, TS, X, Y]=read_biosig (char(name{i}),0);
                    X=round(X);
                    Y=round(Y);
                    
                    [Eventfilename,Eventpath] = uigetfile ({'*.nev'},'Select a Neuralynx-Event file to video time');
                    dir=pwd;
                    cd (Eventpath);
                    
                    [~,EventTS,~,TTL]=read_nev (Eventfilename);
                    if isempty (EventTS), error('Empty file'), end;
                    EventTS=EventTS(TTL~=0);
                    TS=(TS*1E3)+EventTS(1);
                    cd(dir);
                else
                    [~,TS,X,Y]=Read_nvt_Automatic (char(name{i}),1);
%                     [~,TS,X,Y]=read_NVT (char(name{i}));
                end
                firstTS=TS(1);
                
                if(Data.TSfirstpoint==0)
                    if length(name)==1
                        Data.TSfirstpoint=firstTS;
                    end
                else
                    if(Data.TSfirstpoint~=firstTS)
                        %                      disp(txtname);
                        %                      disp('not same TimeStamp');
                        firstTS=Data.TSfirstpoint;
                    end
                end
                TS=TS-firstTS;
                X=bitshift(X,-3);
                Y=bitshift(Y,-3);
                [X,Y]=FixPosData0 (TS,X,Y);
                [b,a] = cheby2(2,20,0.1,'low');
                X=filtfilt(b,a,X);
                Y=filtfilt(b,a,Y);
                Data.filenvt(i)=struct('TSref',firstTS,'TS',TS,'X',X,'Y',Y,'pixelSz',0,'SpeedMtx',[]);
                txtname=char(name{i});
            case {'ntt','nse'}
                if strcmp(ftype,'ntt')
                    [RecSz,TS,probe,clust]=read_ntt(char(name{i}));
                else
                    [RecSz,TS,probe,clust]=read_Se(char(name{i}));
                end
                
                tsnttref=TS(1);
                txtname=char(name{i});
                if(Data.TSfirstpoint==0)
                    Data.TSfirstpoint=TS(1);
                else
                    if(Data.TSfirstpoint~=TS(1))
                        %  disp([txtname,'  not same TimeStamp. Decalage:',num2str(Data.TSfirstpoint-tsnttref),'�s']);
                        tsnttref=Data.TSfirstpoint;
                    end
                end
                
                TS=TS-tsnttref;
                uniqueclust=unique(clust);
                
                %X and Y and TSref maybe only data util...
                Data.filentt(i)=struct('TSref',tsnttref,'TS',TS,'clust',clust,'clustorder',uniqueclust','clusnbs',uniqueclust','showcmark',zeros(1,length(uniqueclust)),'eventId2str',[]);
                % disp([txtname,'first ntt point ',num2str(Data.filentt(i).TS(1))]);
                
            case 'txt'
                TS= load(char(name{i}));
                txtname=char(name{i});
                sz=size(TS);
                if sz(2)>sz(1)
                    TS=TS';
                end
                if sz(2)==2
                    clust=TS(:,2);
                    TS=TS(:,1);
                    uniqueclust=unique(clust);
                    eventId2str=num2str(uniqueclust,'%i');
                else
                    clust=ones(length(TS),1);
                    uniqueclust=1;
                    eventId2str=cellstr('events');
                end
                
                
                
                
                
                if(Data.TSfirstpoint==0)
                    Data.TSfirstpoint=TS(1);
                else
                    if(Data.TSfirstpoint~=TS(1))
                        %  disp([txtname,'  not same TimeStamp. Decalage:',num2str(Data.TSfirstpoint-tsnttref),'�s']);
                        tsnttref=Data.TSfirstpoint;
                    end
                end
                TS=TS-tsnttref;
                Data.filentt(i)=struct('TSref',tsnttref,'TS',TS,'clust',clust,'clustorder',uniqueclust','clusnbs',uniqueclust','showcmark',zeros(1,length(uniqueclust)),'eventId2str',char(eventId2str));
                
            case 'nev'
                [RecSz,TS,ID,TTL,EventString,header]=read_nev(char(name{i}));
                tsnttref=TS(1);
                txtname=char(name{i});
                if(Data.TSfirstpoint==0)
                    Data.TSfirstpoint=TS(1);
                else
                    if(Data.TSfirstpoint~=TS(1))
                        %  disp([txtname,'  not same TimeStamp. Decalage:',num2str(Data.TSfirstpoint-tsnttref),'�s']);
                        tsnttref=Data.TSfirstpoint;
                    end
                end
                
                TS=TS-tsnttref;
                %remove first and last event
                mask=TTL~=0;
                TS=TS(logical(mask));
                EventString=EventString(logical(mask));
                if ~isempty(EventString)
                    EventString=cellstr([EventString{:}]');
                else
                    EventString={''};
                end
                
                eventId2str=unique(EventString);
                
                
                uniqueclust=(1:length(eventId2str));
                clust=zeros(1,length(EventString));
                for idevent=1:length(eventId2str)
                    clust(logical(strcmp(EventString,eventId2str(idevent))))=idevent;
                    
                end
                
                
                %X and Y and TSref maybe only data util...
                Data.filentt(i)=struct('TSref',tsnttref,'TS',TS,'clust',clust,'clustorder',uniqueclust','clusnbs',uniqueclust','showcmark',zeros(1,length(uniqueclust)),'eventId2str',char(eventId2str));
                % disp([txtname,'first ntt point ',num2str(Data.filentt(i).TS(1))]);
                
            case 'ncs'
                try
%                     if i==0
%                         Data.file(i)= Cscfile(char(name{i}));
%                     else
                        Data.file(i)= Cscfile2_PP(char(name{i}));
%                     end
                catch
                    msgbox( [char(name{i}) ' was corrupted, impossible to open it. Please reselect good files again.'],'File corrupt','error');
                    return;
                end
                if Data.file(i).Inverted==1
                    set(Data.checkboxinvertEEG,'value',1);
                    Data.eeginverted=1;
                else
                    Data.eeginverted=0;
                end
                
                txtname=char(Data.file(i).AcqEntName);
                if(Data.TSfirstpoint==0)
                    Data.TSfirstpoint=Data.file(i).firstttimestamps;
                else
                    if(Data.TSfirstpoint~=Data.file(i).firstttimestamps)
                        disp([txtname,'not same TimeStamp. Decalage:',num2str(Data.TSfirstpoint-Data.file(i).firstttimestamps),'�s']);
                    end
                end
                if Data.stepmmin==0
                    Data.stepmmin=15/ Data.file(i).SF;
                end
                
            case 'mpg'
                Data.xtraFileData(i).viewgraph=0;
                txtname=char(name{i});
                [~, namet, extt] =fileparts(txtname);
                a=fopen([namet '.smi']);
                synctime=[];
                while ~feof(a)
                    header=fgetl(a);
                    bb=textscan(header,'<SYNC Start=%d64><P Class=ENUSCC>%f64</SYNC>','delimiter','\r');
                    if ~isempty(bb{1})
%                         synctime=[synctime;bb{1},bb{2}];
                         if bb{1}==0
                             synctime=bb{2};
                         else
                            break;
                        end
                    end
                end
                fclose(a);
%                 videoFReader=vision.VideoFileReader(txtname);
                 synctime=(Data.TSfirstpoint-synctime)*1E-6;
%                 videoPlayer = vision.VideoPlayer;
%                 Data.filevideo(i)=struct('filename',txtname,'TSlink',synctime,'videoFReader',videoFReader,'videoPlayer',videoPlayer,'frmcpt',0,'framerate',29,'streamvideo',0,'videoPlayerfigure',[]);
                 Data.filevideo(i)=struct('filename',txtname,'synctime',synctime,'streamvideo',0,'videoPlayerfigure',[]);
                
               
                
        end
        %%creation interface for each file
        %         z=(i-1)/nbfile;
        %         zbase=1/nbfile;
        
        if i==1
            visible='on';
        else
            visible='off';
        end
        Data.xtraFileData(i).name=txtname;
        %%%%%%%%%%%%%%%%%%%%%%%%%%%%5
        
        Data.ctrlsig(i)=createfilemenu(Data,visible,i);
        
    end
    
    %init button prev/next graph ctrl
    guidata(gcbf,Data);
    AxeButtonDownFcn([], [], Data.currentctrlaxe);
    %draw plot
    Data = update_graph(Data);
    %Data=updatesliderstep(Data);
    guidata(gcbf,Data);
else
    disp('open file cancel');
end

function ctrlsig = createfilemenu(Data,visible,i)
ftype = Data.xtraFileData(i).ftype;
z=0;
zbase=1;
nametxt=uicontrol(Data.uipanelCtrlSig,'style','text',...
    'units','normalized',...
    'position',[0.25 1-(z+(zbase*0.13)) 0.5 0.14],...
    'string',Data.xtraFileData(i).name,...
    'visible',visible,...
    'fontweight','bold',...
    'fontsize',12,...
    'tag','resultat');
if ~strcmp(ftype,'mpg')
btminus=uicontrol(Data.uipanelCtrlSig,'style','pushbutton',...
    'units','normalized',...
    'position',[0.0 1-(z+(zbase*0.25)) 0.1 0.05],...
    'string','v',...
    'visible',visible,...
    'callback',{@reducaxecallback,i},...
    'tag','boutonsigmin');
btplus=uicontrol(Data.uipanelCtrlSig,'style','pushbutton',...
    'units','normalized',...
    'position',[0.0 1-(z+(zbase*0.2)) 0.1 0.05],...
    'string','^',...
    'fontsize',10,...
    'visible',visible,...
    'callback',{@biggeraxecallback,i},...
    'tag','boutonsigplus');

end
if ~(strcmp(ftype,'nvt') || strcmp(ftype,'dat') || strcmp(ftype,'mpg'))
    viewgraph=uicontrol(Data.uipanelCtrlSig,'style','checkbox',...
        'units','normalized',...
        'position',[0.33 1-(z+(zbase*0.25)) 0.5 0.07],...
        'string','Trace',...
        'visible',visible,...
        'callback',{@tboutongraphcallback,i},...
        'value',1,...
        'tag','tboutongraph');
    
end
if strcmp(ftype,'mpg')
    viewgraph=uicontrol(Data.uipanelCtrlSig,'style','checkbox',...
        'units','normalized',...
        'position',[0.33 1-(z+(zbase*0.2)) 0.5 0.07],...
        'string','live video',...
        'visible',visible,...
        'callback',{@tboutonstreamvideoallback,i},...
        'value',0,...
        'tag','tboutongraph');
     btplay=uicontrol(Data.uipanelCtrlSig,'style','pushbutton',...
        'units','normalized',...
        'position',[0.1 1-(z+(zbase*0.4)) 0.3 0.2],...
        'string','play',...
        'fontsize',12,...
        'visible',visible,...
        'callback',{@playvideocallback,i},...
        'tag','boutonsigzoom');
      btminus=[]; 
   btplus=[];
   
    else
    btplay=[];
    
end
if strcmp(ftype,'ncs')
    btminuszoom=uicontrol(Data.uipanelCtrlSig,'style','pushbutton',...
        'units','normalized',...
        'position',[0.1 1-(z+(zbase*0.29)) 0.15 0.09],...
        'string','-',...
        'fontsize',12,...
        'visible',visible,...
        'callback',{@unzoomaxecallback,i},...
        'tag','boutonsigunzoom');
    btpluszoom=uicontrol(Data.uipanelCtrlSig,'style','pushbutton',...
        'units','normalized',...
        'position',[0.1 1-(z+(zbase*0.2)) 0.15 0.09],...
        'string','+',...
        'fontsize',12,...
        'visible',visible,...
        'callback',{@zoomaxecallback,i},...
        'tag','boutonsigzoom');
    viewfft=uicontrol(Data.uipanelCtrlSig,'style','checkbox',...
        'units','normalized',...
        'position',[0.05 1-(z+(zbase*0.5)) 0.6 0.07],...
        'string','Analyse',...
        'callback',{@tboutonfftcallback,i},...
        'value',0,...
        'visible',visible,...
        'tag','tboutongraph');
    x={'Spectogram';
        'Spectrum';'Diff Spectrum';'Correlation...';'chronus spectogram';'max freq in time';'Correlation classic...';'coherency...'};
    anyztype=uicontrol(Data.uipanelCtrlSig,'style','popupmenu',...
        'units','normalized',...
        'position',[0.3 1-(z+(zbase*0.6)) 0.5 0.07],...
        'string',x,...
        'visible',visible,...
        'callback',{@popmenunlyztypecallback,i},...
        'value',1,...
        'tag','popmenuanyztype');
    txtrangef=uicontrol(Data.uipanelCtrlSig,'style','text',...
        'units','normalized',...
        'position',[0.05 1-(z+(zbase*0.71)) 0.8 0.07],...
        'string','Frequency Range :',...
        'visible',visible,...
        'tag','txtrangef');
    txtminf=uicontrol(Data.uipanelCtrlSig,'style','edit',...
        'units','normalized',...
        'callback',{@txtminfcallback,i},...
        'position',[0.2 1-(z+(zbase*0.77)) 0.2 0.07],...
        'string',num2str(Data.xtraFileData(i).nlyzminf),...
        'visible',visible,...
        'TooltipString','Minmum frequency display',...
        'tag','txtminf');
    txtmaxf=uicontrol(Data.uipanelCtrlSig,'style','edit',...
        'units','normalized',...
        'callback',{@txtmaxfcallback,i},...
        'position',[0.4 1-(z+(zbase*0.77)) 0.3 0.07],...
        'string',num2str(Data.xtraFileData(i).nlyzmaxf),...
        'visible',visible,...
        'TooltipString','Maximum frequency display',...
        'tag','txtminf');
    
    
    btfilter=uicontrol(Data.uipanelCtrlSig,'style','togglebutton',...
        'units','normalized',...
        'position',[0.3 1-(z+(zbase*0.37)) 0.4 0.07],...
        'string','Filter',...
        'visible',visible,...
        'BackgroundColor','w',...
        'callback',{@individualfiltercallback,i},...
        'tag',['boutonfilter' num2str(i)]);
    
    btCSD=uicontrol(Data.uipanelCtrlSig,'style','pushbutton',...
        'units','normalized',...
        'position',[0.8 1-(z+(zbase*0.15)) 0.18 0.05],...
        'string','CSD',...
        'visible',visible,...
        'fontsize',7,... %'BackgroundColor','w',...
        'callback',{@switchcsd,i},...
        'tag',['boutonfilter' num2str(i)]);
    
    
    if Data.xtraFileData(i).duplicate <1
        duplicate=uicontrol(Data.uipanelCtrlSig,'style','togglebutton',...
            'units','normalized',...
            'position',[0.02 1-(z+(zbase*0.99)) 0.3 0.07],...
            'string','Duplicate',...
            'visible',visible,...
            'fontsize',8,...
            'BackgroundColor','w',...
            'callback',{@duplicatecallback,i},...
            'tag','boutonduplic');
    else
        duplicate=[];
    end
    
else
    btCSD=[];
    btfilter =[];
    viewfft=[];
    anyztype=[];
    btminuszoom=[];
    btpluszoom=[];
    txtrangef=[];
    txtminf=[];
    txtmaxf=[];
    duplicate=[];
end
if strcmp(ftype,'nvt')||strcmp(ftype,'dat')
    txtpixelSz=uicontrol(Data.uipanelCtrlSig,'style','edit',...
        'units','normalized',...
        'callback',{@txtpixelSzcallback,i},...
        'position',[0.6 1-(z+(zbase*0.8)) 0.3 0.07],...
        'string',0.667,...
        'visible',visible,...
        'TooltipString','Resolution cm/px',...
        'tag','resultat');
    %view graph special for NVT it's the speed only
    viewgraph=uicontrol(Data.uipanelCtrlSig,'style','checkbox',...
        'units','normalized',...
        'position',[0.15 1-(z+(zbase*0.7)) 0.4 0.07],...
        'string','Speed',...
        'visible',visible,...
        'callback',{@txtpixelSzcallback,i},...
        'value',1,...
        'tag','tboutongraph');
    
    viewX=uicontrol(Data.uipanelCtrlSig,'style','checkbox',...
        'units','normalized',...
        'position',[0.15 1-(z+(zbase*0.5)) 0.3 0.07],...
        'string','X',...
        'foregroundColor','g',...
        'visible',visible,...
        'callback',{@txtpixelSzcallback,i},...
        'value',0,...
        'tag','tboutongraph');
    
    viewY=uicontrol(Data.uipanelCtrlSig,'style','checkbox',...
        'units','normalized',...
        'position',[0.4 1-(z+(zbase*0.5)) 0.3 0.07],...
        'string','Y',...
        'visible',visible,...
        'foregroundColor','r',...
        'callback',{@txtpixelSzcallback,i},...
        'value',0,...
        'tag','tboutongraph');
    
    viewpos=uicontrol(Data.uipanelCtrlSig,'style','checkbox',...
        'units','normalized',...
        'position',[0.15 1-(z+(zbase*0.9)) 0.5 0.07],...
        'string','Position',...
        'visible',visible,...
        'callback',{@txtpixelSzcallback,i},...
        'value',0,...
        'tag','tboutongraph');
    
    
else
    viewX=[];
    viewY=[];
    viewpos=[];
    txtpixelSz=[];
end
if strcmp(ftype,'ntt')||strcmp(ftype,'nev')||strcmp(ftype,'nse')||strcmp(ftype,'txt')
    
    btprevmark=uicontrol(Data.uipanelCtrlSig,'style','pushbutton',...
        'units','normalized',...
        'position',[0.05 1-(z+(zbase*0.95)) 0.07 0.05],...
        'string','<',...
        'fontsize',10,...
        'visible',visible,...
        'callback',{@prevmarkcallback,i},...
        'TooltipString','Go to previous event',...
        'tag','boutonprevmark');
    btnextmark=uicontrol(Data.uipanelCtrlSig,'style','pushbutton',...
        'units','normalized',...
        'position',[0.12 1-(z+(zbase*0.95)) 0.07 0.05],...
        'string','>',...
        'fontsize',10,...
        'visible',visible,...
        'callback',{@nextmarkcallback,i},...
        'TooltipString','Go to next event',...
        'tag','boutonnextmark');
    
    clustprop={length(Data.filentt(i).clusnbs)};
    colo=brighten(lines(length(Data.filentt(i).clusnbs)),0.5);
    for ncl=1:length(Data.filentt(i).clusnbs)
        clustprop{ncl}=struct('edit',0,'checkmark',0,'name',0);
        %                 string=num2cell( num2str(Data.filentt(i).clusnbs'));
        %                 string= cat(1,'Hide',string);
        %                 clustprop{ncl}.edit=uicontrol(Data.uipanelCtrlSig,'style','popupmenu',...
        %                 'units','normalized',...
        %                 'callback',{@changeclustcallback,i,ncl},...
        %                 'position',[0.1+0.3*(floor(ncl*0.14)) 1-((mod(( 7-ncl)*0.08,0.56)))-0.4         0.15 0.07],...
        %                 'string',string,...
        %                 'fontsize',7,...
        %                 'value',Data.filentt(i).clusnbs(ncl)+1,...
        %                 'BackgroundColor',colo(ncl,:),...
        %                 'visible',visible,...
        %                 'TooltipString','Number of cluster (nothing to hide the track)',...
        %                 'tag',['editclust' num2str(i) '_' num2str(ncl)]);
        
        clustprop{ncl}.edit=uicontrol(Data.uipanelCtrlSig,'style','edit',...
            'units','normalized',...
            'callback',{@changeclustcallback,i,ncl},...
            'position',[0.05+0.3*(floor(ncl*0.14)) 1-((mod(( 7-ncl)*0.08,0.56)))-0.4         0.15 0.07],...
            'string',num2str(Data.filentt(i).clusnbs(ncl)),...
            'BackgroundColor',colo(ncl,:),...
            'visible',visible,...
            'TooltipString','Number of cluster (nothing to hide the track)',...
            'tag',['editclust' num2str(i) '_' num2str(ncl)]);
        
        clustprop{ncl}.checkmark=uicontrol(Data.uipanelCtrlSig,'style','checkbox',...
            'units','normalized',...
            'position',[0.2+0.3*(floor(ncl*0.14)) 1-((mod(( 7-ncl)*0.08,0.56)))-0.4         0.3 0.07],...
            'string','Mark',...
            'fontsize',8,...
            'visible',visible,...
            'callback',{@tboxmarkclustcallback,i,ncl},...
            'value',0,...
            'tag','tboutongraph');
        
        if ~isempty(Data.filentt(i).eventId2str)
            clustprop{ncl}.name=uicontrol(Data.uipanelCtrlSig,'style','edit',...
                'units','normalized',...
                'callback',{@changeclustnamecallback,i,ncl},...
                'position',[0.45+0.3*(floor(ncl*0.14)) 1-((mod(( 7-ncl)*0.08,0.56)))-0.4         0.5 0.07],...
                'string',deblank(Data.filentt(i).eventId2str(ncl,:)),...%'BackgroundColor',colo(ncl,:),...
                'visible',visible,...
                'fontsize',7,...
                'TooltipString','Event name',...
                'tag',['editclust' num2str(i) '_' num2str(ncl)]);
        else
            clustprop{ncl}.name=[];
        end
        
        
        
    end
else
    clustprop={};
    btprevmark=[];
    btnextmark=[];
end
%         Data.ctrlsig(i)
ctrlsig =struct(  'name',nametxt,...
    'btminus',btminus,...
    'btplus',btplus,...
    'viewgraph',viewgraph,...
    'viewfft',viewfft,...
    'nlyztype',anyztype,...
    'txtpixelSz',txtpixelSz,...
    'viewX',viewX,...
    'viewY',viewY,...
    'viewpos',viewpos,...
    'btfilter',btfilter,...
    'btCSD',btCSD,...
    'btminuszoom',btminuszoom,...
    'btpluszoom',btpluszoom,...
    'btplay',btplay,...
    'txtrangef',txtrangef,...
    'txtminf',txtminf,...
    'txtmaxf',txtmaxf,...
    'duplicate',duplicate,...
    'clustprop',{clustprop},...
    'btprevmark',btprevmark,...
    'btnextmark',btnextmark);

function Data = insertnewfile(Data,numfile,newxtraFileData,newfilenvt,newfilentt,newfile,newspkypesrch)

numfile=numfile-1;
Data.xtraFileData = [Data.xtraFileData(1:numfile) newxtraFileData Data.xtraFileData(numfile+1:end)];
Data.spkypesrch = [Data.spkypesrch(1:numfile) newspkypesrch Data.spkypesrch(numfile+1:end)];
newctrlsig = createfilemenu(Data,'off',numfile+1);
Data.ctrlsig = [Data.ctrlsig(1:numfile) newctrlsig Data.ctrlsig(numfile+1:end)];


if isfield(Data, 'filenvt')
    Data.filenvt = [Data.filenvt(1:numfile) newfilenvt Data.filenvt(numfile+1:end)];
    
end
if isfield(Data, 'filentt')
    Data.filentt = [Data.filentt(1:numfile) newfilentt Data.filentt(numfile+1:end)];
end
if isfield(Data, 'file')
    
    Data.file = [Data.file(1:numfile) newfile Data.file(numfile+1:end)];
end

%increment callback
for i=numfile+2:length(Data.ctrlsig)
    SNames = fieldnames(Data.ctrlsig(i));
    for loopIndex = 1:numel(SNames)
        if ishandle(Data.ctrlsig(i).(SNames{loopIndex}))
            oldcallback=get(Data.ctrlsig(i).(SNames{loopIndex}),'callback');
            if ~isempty(oldcallback)
                oldcallback{2}=oldcallback{2}+1;
                set(Data.ctrlsig(i).(SNames{loopIndex}),'callback',oldcallback);
            end
        end
        
        if strcmp(SNames{loopIndex},'clustprop') && ~isempty(Data.ctrlsig(i).(SNames{loopIndex}))
            for subcell=1:length(Data.ctrlsig(i).(SNames{loopIndex}))
                if ishandle(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.edit);
                    oldcallback=get(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.edit,'callback');
                    if ~isempty(oldcallback)
                        oldcallback{2}=oldcallback{2}+1;
                        set(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.edit,'callback',oldcallback);
                    end
                end
                if ishandle(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.checkmark);
                    oldcallback=get(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.checkmark,'callback');
                    if ~isempty(oldcallback)
                        oldcallback{2}=oldcallback{2}+1;
                        set(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.checkmark,'callback',oldcallback);
                    end
                end
                if ishandle(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.name);
                    oldcallback=get(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.name,'callback');
                    if ~isempty(oldcallback)
                        oldcallback{2}=oldcallback{2}+1;
                        set(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.name,'callback',oldcallback);
                    end
                end
            end
        end
        
    end
end

function Data = removefileo(Data,numfile)


Data.xtraFileData(numfile)=[];
Data.spkypesrch(numfile)=[];
% newctrlsig = createfilemenu(Data,'off',numfile+1);



if isfield(Data, 'filenvt')&& numfile<=length(Data.filenvt)
    Data.filenvt(numfile)=[];
    
end
if isfield(Data, 'filentt')&& numfile<=length(Data.filentt)
    Data.filentt(numfile)=[];
end
if isfield(Data, 'file')&& numfile<=length(Data.file)
    
    Data.file(numfile)=[];
end

%decrement callback and delete signal button
for i=numfile:length(Data.ctrlsig)
    SNames = fieldnames(Data.ctrlsig(i));
    for loopIndex = 1:numel(SNames)
        if ishandle(Data.ctrlsig(i).(SNames{loopIndex}))
            if i==numfile
                delete(Data.ctrlsig(i).(SNames{loopIndex}));
            else
                oldcallback=get(Data.ctrlsig(i).(SNames{loopIndex}),'callback');
                if ~isempty(oldcallback)
                    oldcallback{2}=oldcallback{2}-1;
                    set(Data.ctrlsig(i).(SNames{loopIndex}),'callback',oldcallback);
                end
            end
        end
        if strcmp(SNames{loopIndex},'clustprop') && ~isempty(Data.ctrlsig(i).(SNames{loopIndex}))
            for subcell=1:length(Data.ctrlsig(i).(SNames{loopIndex}))
                if ishandle(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.edit);
                    if i==numfile
                        delete(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.edit);
                    else
                        oldcallback=get(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.edit,'callback');
                        if ~isempty(oldcallback)
                            oldcallback{2}=oldcallback{2}-1;
                            set(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.edit,'callback',oldcallback);
                        end
                    end
                end
                if ishandle(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.checkmark);
                    if i==numfile
                        delete(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.checkmark);
                    else
                        oldcallback=get(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.checkmark,'callback');
                        if ~isempty(oldcallback)
                            oldcallback{2}=oldcallback{2}-1;
                            set(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.checkmark,'callback',oldcallback);
                        end
                    end
                end
                if ishandle(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.name);
                    if i==numfile
                        delete(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.name);
                    else
                        oldcallback=get(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.name,'callback');
                        if ~isempty(oldcallback)
                            oldcallback{2}=oldcallback{2}-1;
                            set(Data.ctrlsig(i).(SNames{loopIndex}){subcell}.name,'callback',oldcallback);
                        end
                    end
                end
            end
        end
        
    end
end
Data.ctrlsig(numfile)=[];


function duplicatecallback(hObject, eventdata, numfile)


Data=guidata(gcbf);
if get(hObject,'value')
    newxtraFileData = Data.xtraFileData(numfile);
    newxtraFileData.viewfft=0;
    newxtraFileData.viewgraph=1;
    Data.xtraFileData(numfile).duplicate=-numfile-1;
    newxtraFileData.duplicate=numfile;
    
    newxtraFileData.name = [newxtraFileData.name ' Duplicate'];
    newspkypesrch = Data.spkypesrch(numfile); % ou pas
    
    if isfield(Data, 'filenvt')
        newfilenvt = Data.filenvt(numfile);
    else
        newfilenvt =[];
    end
    
    if isfield(Data, 'filentt')
        newfilentt = Data.filentt(numfile);
    else
        newfilentt =[];
        
    end
    
    if isfield(Data, 'file')
        newfile = Data.file(numfile);
    else
        newfile =[];
        
    end
    
    
    Data=insertnewfile(Data,numfile+1,newxtraFileData,newfilenvt,newfilentt,newfile,newspkypesrch);
else
    
    Data= removefileo(Data,abs(Data.xtraFileData(numfile).duplicate));
    Data.xtraFileData(numfile).duplicate=0;
end
Data = update_graph( Data,'true');
guidata(gcbf,Data);
function prevmarkcallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
if sum(Data.filentt(numfile).showcmark)==0
    showedclust=unique(Data.filentt(numfile).clustorder(logical(Data.filentt(numfile).clustorder~=-1)));
else
    showedclust=unique(Data.filentt(numfile).clustorder(logical(Data.filentt(numfile).showcmark)));
end
showedclustTS =Data.filentt(numfile).TS(logical(ismember(Data.filentt(numfile).clust,showedclust)));
minmove=min([Data.file(:).SF]);
if ~isempty(minmove)
    minmove=512/minmove;
else
    minmove=0;
end
prevTS=find(showedclustTS<(Data.start+(Data.range/2.1)-minmove)*1E6,1,'last');
if ~isempty(prevTS)
    Data.start=showedclustTS(prevTS)*1E-6-Data.range/2;
    if Data.start<0
        Data.start=0;
    end
    Data = update_graph( Data);
    guidata(gcbf,Data);
end
function nextmarkcallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
if sum(Data.filentt(numfile).showcmark)==0
    showedclust=unique(Data.filentt(numfile).clustorder(logical(Data.filentt(numfile).clustorder~=-1)));
else
    showedclust=unique(Data.filentt(numfile).clustorder(logical(Data.filentt(numfile).showcmark)));
end
showedclustTS =Data.filentt(numfile).TS(logical(ismember(Data.filentt(numfile).clust,showedclust)));
minmove=min([Data.file(:).SF]);
if ~isempty(minmove)
    minmove=512/minmove;
else
    minmove=0;
end
nextTS=find(showedclustTS>(Data.start+(Data.range/1.9)+ minmove)*1E6,1,'first');
if ~isempty(nextTS)
    Data.start=(showedclustTS(nextTS)*1E-6)-Data.range/2;
    Data = update_graph( Data);
    guidata(gcbf,Data);
end

function changeclustnamecallback(hObject, eventdata, numfile,nclust)
Data=guidata(gcbf);
tmp=get(hObject,'string');
lengthchar=length(Data.filentt(numfile).eventId2str(nclust,:));
if length(tmp)>lengthchar
    Data.filentt(numfile).eventId2str(nclust,:)=tmp(1:lengthchar);
else
    Data.filentt(numfile).eventId2str(nclust,:)=[tmp blanks(lengthchar-length(tmp))];
end

guidata(gcbf,Data);

function changeclustcallback(hObject, eventdata, numfile,nclust)
Data=guidata(gcbf);
tmp=str2num(get(hObject,'string'));

if isempty(tmp)||(tmp>=min(Data.filentt(numfile).clusnbs) && tmp<=max(Data.filentt(numfile).clusnbs))
    if isempty(tmp)
        Data.filentt(numfile).clustorder(nclust)=-1;
    else
        Data.filentt(numfile).clustorder(nclust)=tmp;
    end
    Data = update_graph( Data,'true');
else
    msgbox(['Invalid cluster number. Choose a number between ' num2str(min(Data.filentt(numfile).clusnbs)) ' and ' num2str(max(Data.filentt(numfile).clusnbs)) ' . Or nothing to hide this track.'],'Invalid cluster number','warn');
    if Data.filentt(numfile).clustorder(nclust)~=-1
        set(hObject,'string',num2str(Data.filentt(numfile).clustorder(nclust)));
    else
        set(hObject,'string','');
    end
    
end
if  ishandle(Data.ctrlsig(numfile).clustprop{nclust}.name)
    if Data.filentt(numfile).clustorder(nclust)~=-1
        set(Data.ctrlsig(numfile).clustprop{nclust}.name,'string',deblank(Data.filentt(numfile).eventId2str(Data.filentt(numfile).clustorder(nclust),:)));
    else
        set(Data.ctrlsig(numfile).clustprop{nclust}.name,'string','');
    end
end

guidata(gcbf,Data);

function tboxmarkclustcallback(hObject, eventdata, numfile,ntrack)
Data=guidata(gcbf);
Data.filentt(numfile).showcmark(ntrack)=(get(hObject,'value'));

Data = update_graph( Data,'true');

guidata(gcbf,Data);


function switchcsd(hObject, eventdata, numfile)
Data=guidata(gcbf);
Data.CSD=~Data.CSD;
if Data.CSD==1
    if ~isfield(Data, 'figCSD') || isempty(Data.figCSD)|| ~ishandle(Data.figCSD)
        Data.figCSD=figure('name','CSD (live)');
       Data.axeCSD=axes('parent',Data.figCSD);
    else
        set(Data.figCSD,'name','CSD (live)');
    end

%     axecsd=foundobj(axes('parent',Data.figCSD);
    Csdview(Data, Data.axeCSD);
else
    if isfield(Data, 'figCSD') && ~isempty(Data.figCSD)&&ishandle(Data.figCSD)
        set(Data.figCSD,'name','CSD (inactivate)');
    end
    %unlink the windows
    Data.figCSD=[];
    Data.axeCSD=[];
end
guidata(gcbf,Data);

%individual filter callback
function individualfiltercallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
if(get(Data.ctrlsig(numfile).btfilter,'value')==1)
    %ask filters value
    prompt = {['Low pass frequency (Hz):' num2str(Data.file(numfile).SF) 'Hz max'],...
        'High pass frequency (Hz):'};
    dlg_title = 'Individual frequency filter (0 = no filter)';
    num_lines = 1;
    def = {num2str(Data.lowpass),num2str(Data.highpass)};
    if(Data.xtraFileData(numfile).lowpass~=0)
        def{1}= num2str(Data.xtraFileData(numfile).lowpass);
    end
    if(Data.xtraFileData(numfile).highpass~=0)
        def{2}=num2str(Data.xtraFileData(numfile).highpass);
    end
    
    answer = inputdlg(prompt,dlg_title,num_lines,def);
    if length(answer)==2
        Data.xtraFileData(numfile).lowpass = str2num(answer{1});
        Data.xtraFileData(numfile).highpass=str2num(answer{2});
        Data = update_graph( Data);
    else
        set(Data.ctrlsig(numfile).btfilter,'value',0)
    end
end
Data = update_graph( Data);
guidata(gcbf,Data);

function txtminfcallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
Data.xtraFileData(numfile).nlyzminf=str2num(get(hObject,'string'));
Data = update_graph( Data,'true');
guidata(gcbf,Data);
function txtmaxfcallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
Data.xtraFileData(numfile).nlyzmaxf=str2num(get(hObject,'string'));
Data = update_graph( Data,'true');
guidata(gcbf,Data);


function txtpixelSzcallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
Data.xtraFileData(numfile).viewgraph=get(Data.ctrlsig(numfile).viewgraph,'value')||get(Data.ctrlsig(numfile).viewX,'value')||get(Data.ctrlsig(numfile).viewY,'value');

Data = update_graph( Data,'true');
guidata(gcbf,Data);

function popmenunlyztypecallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
switch get(hObject,'Value')
    %spectogram setup
    case 1 
    sizeS=size(Data.file(numfile).Samples,1);
%     sizeS=sizeS(1);
    frame_length  = (1/Data.file(numfile).currentSF)*sizeS*100;% ms
    prompt = {['frame length (ms) (0=defaut [' num2str(frame_length) 'ms]) :'],...
        ['frame overlap (ms) (0=defaut [' num2str(frame_length/1.2) 'ms]) :']};
    dlg_title = 'Short time Fourrier transform setup ...';
    num_lines = 1;
    
    def = {num2str(Data.xtraFileData(numfile).frame_length),...
        num2str(Data.xtraFileData(numfile).frame_overlap)};
    
    
    answer = inputdlg(prompt,dlg_title,num_lines,def);
    if length(answer)==2
        Data.xtraFileData(numfile).frame_length = str2num(answer{1});
        Data.xtraFileData(numfile).frame_overlap=str2num(answer{2});
        Data = update_graph( Data);
    else
        set(Data.ctrlsig(numfile).btfilter,'value',0)
    end
    case {4,7,8} %correlation setup
%         Data.xtraFileData.name
        names={Data.file.name};
        [Selectionstart,ok1]=listdlg('name','Correlation setting','PromptString','Select the other EEG for correlation :',...
                'SelectionMode','single',...
                'ListString',names);
         Data.xtraFileData(numfile).correlationeeg=find(strcmp({Data.file.name},names{Selectionstart}));   
        
        
end
Data = update_graph( Data,'true');
guidata(gcbf,Data);
function tboutonstreamvideoallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
 Data.filevideo(numfile).streamvideo=~Data.filevideo(numfile).streamvideo;
 Data = update_graph( Data,'false');
 guidata(gcbf,Data);
 
function playvideocallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
% Data.filevideo(numfile).TSlink;
% videoFReader=Data.filevideo(numfile).videoFReader;
% % videoPlayer=Data.filevideo(numfile).videoPlayer;
% startframe=round(Data.start*Data.filevideo(numfile).framerate);
% frmrange=round(Data.range*Data.filevideo(numfile).framerate);
% % if startframe<Data.filevideo(numfile).frmcpt
% %     reset(videoFReader)
% %     Data.filevideo(numfile).frmcpt=0;
% % end
% % tic 
% % while Data.filevideo(numfile).frmcpt < startframe-1
% %     Data.filevideo(numfile).frmcpt=Data.filevideo(numfile).frmcpt+1;
% %     step(videoFReader);
% % end
% % toc
% % Data.filevideo(numfile).videoPlayer = vision.VideoPlayer('Position',[0 50 800 510]);
% % 
% % while Data.filevideo(numfile).frmcpt < frmrange+startframe
% %     Data.filevideo(numfile).frmcpt=Data.filevideo(numfile).frmcpt+1;
% %     videoFrame = step(videoFReader);
% %     pause(1/Data.filevideo(numfile).framerate);
% %     step(Data.filevideo(numfile).videoPlayer, videoFrame);
% % end


mainfig=gcf;
if isempty(Data.filevideo(numfile).videoPlayerfigure) || ~ishandle(Data.filevideo(numfile).videoPlayerfigure)
    Data.filevideo(numfile).videoPlayerfigure=figure;
else
    set(0,'currentfigure',Data.filevideo(numfile).videoPlayerfigure);
end
pathtmp=pwd;
mmread(fullfile(pathtmp, Data.filevideo(numfile).filename), [], [Data.start Data.start+Data.range]+Data.filevideo(numfile).synctime, 0, 1, 'processFrame');
cd(pathtmp);

set(0,'currentfigure',mainfig);


guidata(gcbf,Data);

function tboutongraphcallback(hObject, eventdata, numfile)
Data=guidata(gcbf);

Data.xtraFileData(numfile).viewgraph=get(Data.ctrlsig(numfile).viewgraph,'value');
Data = update_graph( Data,'true');
guidata(gcbf,Data);

function tboutonfftcallback(hObject, eventdata, numfile)
Data=guidata(gcbf);

Data.xtraFileData(numfile).viewfft=get(Data.ctrlsig(numfile).viewfft,'value');
Data = update_graph( Data,'true');
guidata(gcbf,Data);

function unzoomaxecallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
Data.xtraFileData(numfile).zoom=Data.xtraFileData(numfile).zoom*1.1;
set(Data.ax(numfile),'Ylim',get(Data.ax(numfile),'Ylim')*1.1);
guidata(gcbf,Data);
function zoomaxecallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
Data.xtraFileData(numfile).zoom=Data.xtraFileData(numfile).zoom*0.9;
set(Data.ax(numfile),'Ylim',get(Data.ax(numfile),'Ylim')*0.9);
guidata(gcbf,Data);

function reducaxecallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
Data.xtraFileData(numfile).height=Data.xtraFileData(numfile).height-1;
if Data.xtraFileData(numfile).height==1
    set(Data.ctrlsig(numfile).btminus,'Visible','off');
end
Data = update_graph( Data,'true');
guidata(gcbf,Data)

function biggeraxecallback(hObject, eventdata, numfile)
Data=guidata(gcbf);
Data.xtraFileData(numfile).height=Data.xtraFileData(numfile).height+1;

set(Data.ctrlsig(numfile).btminus,'Visible','on');
Data= update_graph( Data,'true');
guidata(gcbf,Data);

%
function Data = update_graph( Data,notmodifydata)
if nargin < 2
    notmodifydata = 'false';
end

order= (1:length(Data.xtraFileData));
tmpviewgraph=[Data.xtraFileData(:).viewgraph];
order= order(tmpviewgraph==1);

contents = cellstr(get(Data.popupfiltertype,'String')) ;
filtertype=contents{get(Data.popupfiltertype,'Value')};

if exist('Data', 'var') && isfield(Data, 'file')
    
    Data.ax=[];
    for i = 1:length(Data.file)
        if strcmp(Data.xtraFileData(i).ftype,'ncs')
            if ~strcmp(notmodifydata,'true')
                 Data.file(i)=Data.file(i).setfiltertype(filtertype);
                %Data.file(i)=Data.file(i).setDonwnsampling(round(Data.compress));
                if(get(Data.ctrlsig(i).btfilter,'value')==0)
                    Data.file(i)=Data.file(i).setlowpass(Data.lowpass,max([Data.spkypesrch(:).activate]));
                    Data.file(i)=Data.file(i).sethighpass(Data.highpass);
                else
                    Data.file(i)=Data.file(i).setlowpass(Data.xtraFileData(i).lowpass,max([Data.spkypesrch(:).activate]));
                    
                    %                      Data.file(i)=Data.file(i).setlowpass(Data.xtraFileData(i).lowpass,Data.spkypesrch(i).activate);
                    Data.file(i)=Data.file(i).sethighpass(Data.xtraFileData(i).highpass);
                end
                Data.file(i).notch = get(Data.tg_notch,'value');
                if i==0
                    Data.file(i)=Data.file(i).setstart(round(Data.start/(512*(1/Data.file(i).SF))));
                    Data.file(i)=Data.file(i).setrange(floor(Data.range/(512*(1/Data.file(i).SF))));
                    % disp(['Data.range ',num2str(Data.range)]);
                    % disp(['round range Csfile',num2str(floor(Data.range/(512*(1/Data.file(i).SF))))]);

                    Data.range =Data.file(i).range*512*(1/Data.file(i).SF);
                    Data.file(i)=Data.file(i).readdata();
                    Data.start = Data.file(i).start*512*(1/Data.file(i).SF);
                else
                     Data.file(i)=Data.file(i).setstart(Data.start);
                    Data.file(i)=Data.file(i).setrange(Data.range);
                    Data.range =Data.file(i).range;
                    Data.file(i)=Data.file(i).readdata();
                    Data.start = Data.file(i).start;
                end
                
                Data.endtime = Data.file(i).filerecordtotaltime;
                Data= updatesliderstep(Data);
                
                %accuracy bug crash the slider
                if Data.start> get(Data.SlidTime, 'max')
                    set(Data.SlidTime, 'Value',get(Data.SlidTime, 'max'));
                else
                    set(Data.SlidTime, 'Value',Data.start );
                end
            end
            sizeS=size(Data.file(i).Samples);
            sizeS=sizeS(1);
            
            p=1/Data.file(i).currentSF;
            %start=Data.file(i).start*512*p/Data.file(i).Downsampling;
            
            %     if i==1
            %         Data.ax(i) = subaxis(length(Data.file)+1,1  ,1,1,  1,2,'SpacingVert',0.01,'ML',0.05,'MR',0.2 );
            %     else
            if(Data.xtraFileData(i).viewgraph==1)
                Data.ax(i) = subaxis([Data.xtraFileData(:).height]*[Data.xtraFileData(:).viewgraph]'+sum([Data.xtraFileData(:).viewfft]*[Data.xtraFileData(:).height]'),1,...
                    1,sum([Data.xtraFileData(1:i-1).height]*[Data.xtraFileData(1:i-1).viewgraph]')+1+sum([Data.xtraFileData(1:i-1).viewfft]*[Data.xtraFileData(1:i-1).height]'),...
                    1,Data.xtraFileData(i).height,...
                    'SpacingVert',0.01,'ML',0.05,'MR',0.2,'PB',0,'MT',0.04 );
                
                ple=plot(Data.ax(i),...
                    Data.start :p: Data.start+sizeS*p - p,...
                    Data.file(i).Samples);
                set(ple,'ButtonDownFcn',{@AxeButtonDownFcn,i});
                title([]) ;xlabel([]); ylabel(Data.file(i).AcqEntName);axis on;
                if Data.EEGylim==0
                    Data.EEGylim=get(Data.ax(i),'Ylim');
                    set(Data.ax(i),'Ylim',get(Data.ax(i),'Ylim')*Data.xtraFileData(i).zoom);
                else
                    set(Data.ax(i),'Ylim', Data.EEGylim*Data.xtraFileData(i).zoom);
                end
                
                set(Data.ax(i),'XLim',[Data.start Data.start+Data.range-p]);
                numorder=find(order==i);
                if numorder~=length(order)
                    if numorder==1
                        set(Data.ax(i),'Xaxislocation','top');
                    else
                        set(Data.ax(i),'xticklabel',[]);
                    end
                else
                    if(Data.xtraFileData(i).viewfft==1)
                        set(Data.ax(i),'xticklabel',[]);
                    end
                    
                end
                if ~mod(numorder,2)
                    set(Data.ax(i),'yaxislocation','right');
                end
                set(Data.ax(i),'ButtonDownFcn',{@AxeButtonDownFcn,i});
                if Data.xtraFileData(i).duplicate>0
                    set(Data.ax(i),'color',[0.93,0.93,0.93]);
                end
            end
            
            
            if(Data.xtraFileData(i).viewfft==1)
                typenlyz = get(Data.ctrlsig(i).nlyztype,'value');
                if typenlyz~=1
                    PB=0.02;
                else
                    PB=0;
                end
                Data.axftt(i) = subaxis([Data.xtraFileData(:).height]*[Data.xtraFileData(:).viewgraph]'+sum([Data.xtraFileData(:).viewfft]*[Data.xtraFileData(:).height]'),1,...
                    1,sum([Data.xtraFileData(1:i).height]*[Data.xtraFileData(1:i).viewgraph]')+1+sum([Data.xtraFileData(1:i-1).viewfft]*[Data.xtraFileData(1:i-1).height]'),...
                    1,Data.xtraFileData(i).height,...
                    'SpacingVert',0.01,'ML',0.05,'MR',0.2,'PB',PB,'MT',0.04  );
                
                %frame_length  = (1/Data.file(i).currentSF)*20000;
                % oldframe_length  = (1/Data.file(i).currentSF)*20000;
                typenlyz = get(Data.ctrlsig(i).nlyztype,'value');
                switch typenlyz
                    case {1,5,6}
                        if Data.xtraFileData(i).frame_length==0
                            frame_length  =(1/Data.file(i).currentSF)*sizeS*100;% ms
                        else
                            frame_length  =Data.xtraFileData(i).frame_length;
                        end
                        if Data.xtraFileData(i).frame_overlap==0
                            frame_overlap = ((1/Data.file(i).currentSF)*sizeS*100)/1.02;%
                        else
                            frame_overlap = Data.xtraFileData(i).frame_overlap;
                        end
                        %% classic verssion
                        if typenlyz==1 
                            windows='hamming';
                            %         windows='rectwin';
                            [S, F, T]= spStft(Data.file(i).Samples, windows, frame_overlap, frame_length, Data.file(i).currentSF);%  , 'plot'
                            SdB = 30 * log10(abs(S)); % dB
                            
                            ax = imagesc(T+Data.start, F(logical(F>=Data.xtraFileData(i).nlyzminf & F<= Data.xtraFileData(i).nlyzmaxf)), SdB(logical(F>=Data.xtraFileData(i).nlyzminf & F<= Data.xtraFileData(i).nlyzmaxf),:));
                            set(get(ax, 'Parent'), 'YDir', 'normal');
                            %% chronus style
                        elseif typenlyz==6
                            windows='hamming';
                            [S, f, t]= spStft(Data.file(i).Samples, windows, frame_overlap, frame_length, Data.file(i).currentSF);
                            %                             [S,t,f]=mtspecgramc(Data.file(i).Samples,[frame_length*1E-3 (frame_length-frame_overlap)*1E-3],params);
                            S=S(logical(f>=Data.xtraFileData(i).nlyzminf & f<= Data.xtraFileData(i).nlyzmaxf),:);
                            f=f(logical(f>=Data.xtraFileData(i).nlyzminf & f<= Data.xtraFileData(i).nlyzmaxf));
                            S = 30 * log10(abs(S));
                            %experiment trace max spectogram
                            % S = 30 * log10(abs(S));
                            %                                  [maxs,maxid]=max(S);
                            %                                S=double(S);
                            % %                                 [maxs,maxid]=max(S,[],2); % for chronus spect ( bader results)
                            %                                 mask=ones(1,size(S,1));
                            %                                 tabnan=ones(1,size(S,1)-1)*NaN;
                            %                                 for ii=1:size(S,2)
                            %                                     tmpm=mask;
                            %                                     tmpm(maxid(ii))=0;
                            %                                 S(logical(tmpm),ii)=tabnan;
                            %                                 end
                            %                                 ax = imagesc(t+Data.start, f(logical(f>=Data.xtraFileData(i).nlyzminf & f<= Data.xtraFileData(i).nlyzmaxf)), S(logical(f>=Data.xtraFileData(i).nlyzminf & f<= Data.xtraFileData(i).nlyzmaxf),:));
                            %                                     set(get(ax, 'Parent'), 'YDir', 'normal');
                            [maxs,maxid]=max(S);
                            f=f(maxid);
                            %                                 plot( Data.axftt(i),t+Data.start,f,'r');
                            
                            
                            %experiment remove low value and reinterp
                                %                             f(logical(maxs<max(maxs)/10))=NaN;
                                %                              y=f;
                                %                             bd=isnan(f);
                                %                             gd=find(~bd);
                                %                             bd([1:(min(gd)-1) (max(gd)+1):end])=0;
                                %                             f(bd)=interp1(gd,y(gd),find(bd));
                                
                                 [b,a] = cheby2(2,20,0.1,'low');
                                 p= filtfilt(b,a,f);
%                                  hil=diff(p);

%             Hilb = hilbert(hil);
%             ThetaPhase = angle(Hilb);
% 
% ThetaPhase = (ThetaPhase*+pi);
%             plot(Data.axftt(i),t+Data.start,ThetaPhase);
                                 ax=plot( Data.axftt(i),t+Data.start,p);
                                 hold on;
%                                  plot( Data.axftt(i),t(2:end)+Data.start,hil,'r');
%                                  plot(Data.axftt(i),t(2:end)+Data.start,ThetaPhase);
                                 ax=scatter( Data.axftt(i),t+Data.start,p,10,maxs);
                                 hold off;
                                 
%                                 [ax,H1,H2]=plotyy(   t+Data.start,p ,t+Data.start,maxs);
                                 set(Data.axftt(i),'YLim',[Data.xtraFileData(i).nlyzminf Data.xtraFileData(i).nlyzmaxf]);
                                 set(gca,'YMinorgrid','on');
                        set(gca,'XMinorgrid','on');
%                                  linkaxes([ax  Data.axftt(i)] ,'x');
%                                  Data.axftt(i)=ax(1);
%                                 hold on;
%                                 ax=plot( Data.axftt(i),t+Data.start,maxs,'g');
%                                 hold off;
                                %                             set(ax,'LineStyle','none');
                            
                        else
                            params.tapers = [3 5];
                            params.Fs=Data.file(i).currentSF;
                            params.pad=0;
                            params.fpass=[Data.xtraFileData(i).nlyzminf Data.xtraFileData(i).nlyzmaxf];
                            [S,t,f]=mtspecgramc(Data.file(i).Samples,[frame_length*1E-3 (frame_length-frame_overlap)*1E-3],params);
                            S = 30 * log10(abs(S));
                            if typenlyz==5
                                %                                 SdB = 30 * log10(abs(S));
                                ax=pcolor( Data.axftt(i),t+Data.start,f,S');
                                set(get(ax, 'Parent'), 'YDir', 'normal');
                                set(ax,'LineStyle','none');
 
                            end
                            
                        end
                        %% end
                        
%                         set(ax,'ButtonDownFcn',{@AxeButtonDownFcn,i});
                        set(ax,'ButtonDownFcn',{@AxeButtonDownFcn,i});

                        ylabel('Frequency (Hz)')
                        set(gca,'YLim',[Data.xtraFileData(i).nlyzminf Data.xtraFileData(i).nlyzmaxf]);
                        %                         if(get(Data.ctrlsig(i).btfilter,'value')==0)
                        %                         set(gca,'YLim',[Data.highpass-1 Data.file(i).currentSF/3],'xtick',[]);
                        %                         else
                        %                             set(gca,'YLim',[Data.xtraFileData(i).highpass-1 Data.file(i).currentSF/3],'xtick',[]);
                        %                         end
                        numorder=find(order==i);
                        if numorder~=length(order)
                            set(Data.axftt(i),'xticklabel',[]);
                        end
                    case {2,3}
                        
                        %S FFT
                        %                         NFFT = 2^nextpow2(    sizeS     );% *10 increase the sampling of the fft
                        
                        
                        %                             Y = fft(Data.file(i).Samples,NFFT)/sizeS;
                        
                        ratiomaxf = Data.file(i).currentSF/Data.xtraFileData(i).nlyzmaxf;
                        %                                  subdivwindows=sizeS/(ratiomaxf*4);
                        
                        
                        if ratiomaxf*100>round(sizeS/20)
                            a=floor(sizeS/ratiomaxf );
                            if a==0
                                window=sizeS;
                            elseif a>100
                                window=ratiomaxf*100;
                            else
                                window=ratiomaxf*a;
                            end
                        else
                            window= sizeS/20;
                        end
                        window=round(window);
                        
                        res=(Data.xtraFileData(i).nlyzmaxf - Data.xtraFileData(i).nlyzminf )/400;
                        if typenlyz==3
                            %                                         Y = fft(diff(Data.file(i).Samples),NFFT)/(sizeS-1);
                            [Y,f]=pwelch(diff(Data.file(i).Samples),window,round(window/2),round(Data.file(i).currentSF/res),Data.file(i).currentSF);
                        else
                            [Y,f]=pwelch(Data.file(i).Samples,window,round(window/2),round(Data.file(i).currentSF/res),Data.file(i).currentSF);
                        end
                        
                        
                        
                        
                        %                             f = Data.file(i).currentSF/2*linspace(0,1,NFFT/2+1);
                        
                        
                        %                          f = Data.file(i).currentSF/2*linspace(0,1,NFFT/2+1);
                        %                          pl=plot(Data.axftt(i),f,2*abs(Y(1:NFFT/2+1)));
                        
                        %                             pl=plot(Data.axftt(i),f,10*log10(Y));
                        pl=plot(Data.axftt(i),f,Y);
                        
                        %                         pl=plot(Data.axftt(i),2*abs(Y(1:NFFT/2+1)));
                        
                        set(pl,'ButtonDownFcn',{@AxeButtonDownFcn,i});
                        %                         hold on;
                        %                          plot(Data.axftt(i),f,smooth(2*abs(Y(1:NFFT/2+1)),'sgolay',2),'g');
                        %                         % plot(Data.axftt(i),f,smooth(2*abs(Y(1:NFFT/2+1)),'loess'),'r');
                        % %                          hftt=hilbert(Data.file(i).Samples);
                        % %                          plot(Data.axftt(i),f,abs(hftt),'r');
                        % %                         phs = atan2(imag(abs(hftt)), real(abs(hftt)));
                        % % plot(Data.axftt(i),f,phs*100,'g');
                        % %
                        %                         hold off;
                        %if(get(Data.ctrlsig(i).btfilter,'value')==0)
                        
                        set(gca,'XLim',[Data.xtraFileData(i).nlyzminf Data.xtraFileData(i).nlyzmaxf]);
                        
                        
                        % else
                        %  set(gca,'XLim',[Data.xtraFileData(i).highpass-1 Data.file(i).currentSF/3]);
                        % end
                        set(gca,'YMinorgrid','on');
                        set(gca,'XMinorgrid','on');
                        % xlabel('Frequency (Hz)')
                        ylabel('|Y(f)|')
                        
                    case 4
                      % correlation wait all signal open  
                        
                end
                set(Data.axftt(i),'ButtonDownFcn',{@AxeButtonDownFcn,i});
                if Data.xtraFileData(i).duplicate>0
                    set(Data.axftt(i),'color',[0.93,0.93,0.93]);
                end
            end
            
            % set(data.figure1,'Ytick',flipud(ytickguys));
            %set(gca, 'LooseInset', [0,0,0,0]);
        end
    end
    
end
if exist('Data', 'var') && isfield(Data, 'filentt')
    for i = 1:length(Data.filentt)
        if (strcmp(Data.xtraFileData(i).ftype,'ntt')||strcmp(Data.xtraFileData(i).ftype,'nev')||strcmp(Data.xtraFileData(i).ftype,'txt')||strcmp(Data.xtraFileData(i).ftype,'nse'))&& Data.xtraFileData(i).viewgraph==1
            if(Data.endtime==10)
                Data.endtime=Data.filentt(i).TS(end)*10^-6;
                Data= updatesliderstep(Data);
            end
            
            Data.ax(i) = subaxis([Data.xtraFileData(:).height]*[Data.xtraFileData(:).viewgraph]'+sum([Data.xtraFileData(:).viewfft]*[Data.xtraFileData(:).height]'),1,...
                1,sum([Data.xtraFileData(1:i-1).height]*[Data.xtraFileData(1:i-1).viewgraph]')+1+sum([Data.xtraFileData(1:i-1).viewfft]*[Data.xtraFileData(1:i-1).height]'),...
                1,Data.xtraFileData(i).height,...
                'SpacingVert',0.01,'ML',0.05,'MR',0.2,'PB',0 ,'MT',0.04 );
            
            delete(get(Data.ax(i), 'Children'));
            
            begint = find(Data.filentt(i).TS>Data.start*1000000,1,'first');
            endt =find(Data.filentt(i).TS<(Data.start+Data.range)*1000000,1,'last');
            
            %              begint = find(Data.filentt(i).X>Data.start,1,'first');
            %             endt =find(Data.filentt(i).X<(Data.start+Data.range),1,'last');
            
            %             pl=plot (Data.ax(i),Data.filentt(i).X,Data.filentt(i).Y);
            
            %             set(Data.ax(i),'XLim',[Data.start Data.start+Data.range]);
            %             uX=max(Data.filentt(i).Y);
            %             set(Data.ax(i),'ytick',[0:1:floor(uX)]);
            %             set(Data.ax(i),'ylim',[-0.5 uX+0.25]);
            
            % set(Data.ax(i),'color',[0.9,0.9,0.8])
            %Data.filentt(i).clust(begint:endt)
            
            
            %            scatter( Data.ax(i-1),...
            %                Data.filentt(i).TS(begint:endt)/1000000,...
            %                 (begint:endt),100,Data.filentt(i).clust(begint:endt),'+');
            %
            uniqueclust=unique(Data.filentt(i).clust);
            colo=lines(length(uniqueclust));
            clustTSrange=Data.filentt(i).TS(begint:endt)/1000000;
            
            for ncl=1:length(Data.filentt(i).clustorder)
                if ~isempty(Data.filentt(i).clustorder(ncl))
                    tmpTSclust=clustTSrange(logical(Data.filentt(i).clust(begint:endt)==Data.filentt(i).clustorder(ncl)));
                    %                 Data.filentt(i).ln(ncl)
                    
                    if ~isempty(tmpTSclust)
                        ln=line((tmpTSclust*[1 1])',...
                            (ones(length(tmpTSclust),1)*[-0.3 0.3])'+ncl-(length(find(Data.filentt(i).clustorder(1:ncl)==-1)))-1,...
                            'color',colo(ncl,:));
                        set(ln,'ButtonDownFcn',{@AxeButtonDownFcn,i});
                    end
                    
                    
                    
                end
            end
            
            
            
            %             for ncl=1:length(uniqueclust)
            %                 tmpTSclust=clustTSrange(logical(Data.filentt(i).clust(begint:endt)==uniqueclust(ncl)));
            % %                 Data.filentt(i).ln(ncl)
            %                 ln=line((tmpTSclust*[1 1])',...
            %                                             (ones(length(tmpTSclust),1)*[-0.3 0.3])'+uniqueclust(ncl),...
            %                                             'color',colo(ncl,:));
            %
            %                 set(ln,'ButtonDownFcn',{@nttplotButtonDownFcn,i});
            %             end
            set(Data.ax(i),'XLim',[Data.start Data.start+Data.range]);
            uX=length(find(Data.filentt(i).clustorder~=-1))-0.5;
            set(Data.ax(i),'ytick',[0:1:floor(uX)]);
            set(Data.ax(i),'yticklabel',Data.filentt(i).clustorder(logical(Data.filentt(i).clustorder~=-1)));
            set(Data.ax(i),'ylim',[-0.5 uX]);
            
            % title([]) ;xlabel([]); ylabel(Data.file(i).AcqEntName);axis on;
            %             set(Data.ax(i),'color',[0.7,0.7,0.7]);
            set(Data.ax(i),'color','k');
            % set(Data.ax(i),'XLim',[Data.start Data.start+Data.range]);
            set(Data.ax(i),'ButtonDownFcn',{@AxeButtonDownFcn,i});
            
            numorder=find(order==i);
            if numorder~=length(order)
                if numorder==1
                    set(Data.ax(i),'Xaxislocation','top');
                else
                    set(Data.ax(i),'xticklabel',[]);
                end
            end
            if ~mod(numorder,2)
                set(Data.ax(i),'yaxislocation','right');
            end
            
        end
    end
end
if exist('Data', 'var') && isfield(Data, 'filenvt')
    for i = 1:length(Data.filenvt)
        
        if (strcmp(Data.xtraFileData(i).ftype,'nvt')||strcmp(Data.xtraFileData(i).ftype,'dat'))&& Data.xtraFileData(i).viewgraph==1
            if(Data.endtime==10)
                Data.endtime=Data.filenvt(i).TS(end)*10^-6;
                Data= updatesliderstep(Data);
            end
            
            pixelSz=str2double(get(Data.ctrlsig(i).txtpixelSz,'String'));
            if pixelSz ~= Data.filenvt(i).pixelSz
                Data.filenvt(i).pixelSz = pixelSz;
                [SpeedMtx] = Speed_MtxEZ(Data.filenvt(i).TS,Data.filenvt(i).X,Data.filenvt(i).Y,Data.filenvt(i).pixelSz);
                Data.filenvt(i).SpeedMtx=SpeedMtx;
            end
            Data.ax(i) = subaxis([Data.xtraFileData(:).height]*[Data.xtraFileData(:).viewgraph]'+sum([Data.xtraFileData(:).viewfft]*[Data.xtraFileData(:).height]'),1,...
                1,sum([Data.xtraFileData(1:i-1).height]*[Data.xtraFileData(1:i-1).viewgraph]')+1+sum([Data.xtraFileData(1:i-1).viewfft]*[Data.xtraFileData(1:i-1).height]'),...
                1,Data.xtraFileData(i).height,...
                'SpacingVert',0.01,'ML',0.05,'MR',0.2,'PB',0,'MT',0.04  );
            
            begint = find(Data.filenvt(i).TS>Data.start*1000000,1,'first');
            if(begint>1)
                begint=begint-1;
            end
            endt =find(Data.filenvt(i).TS<(Data.start+Data.range)*1000000,1,'last');
            if(endt<length(Data.filenvt(i).TS))
                endt=endt+1;
            end
            hold off;
            if get(Data.ctrlsig(i).viewgraph,'Value') == 1
                plot(Data.ax(i),...
                    Data.filenvt(i).TS(begint:endt)/1000000,...
                    Data.filenvt(i).SpeedMtx(begint:endt));
                hold on;
            end
            if get(Data.ctrlsig(i).viewX,'Value') == 1
                plot(Data.ax(i),...
                    Data.filenvt(i).TS(begint:endt)/1000000,...
                    Data.filenvt(i).X(begint:endt),'color','g');
                hold on;
                
            end
            if get(Data.ctrlsig(i).viewY,'Value') == 1
                plot(Data.ax(i),0,0,...
                    Data.filenvt(i).TS(begint:endt)/1000000,...
                    Data.filenvt(i).Y(begint:endt),'color','r');
                
            end
            set(Data.ax(i),'ButtonDownFcn',{@AxeButtonDownFcn,i});
            if get(Data.ctrlsig(i).viewpos,'Value') == 1
                if(~isfield(Data, 'posnvt') || ~ishandle(Data.posnvt(i)))
                    Data.posnvt(i)=figure('name','Position');
                end
                clf( Data.posnvt(i));
                Data.axpos(i)=axes('parent',Data.posnvt(i));
                hold(Data.axpos(i), 'on');
                scatter(Data.axpos(i),...
                    Data.filenvt(i).X(begint:endt),...
                    Data.filenvt(i).Y(begint:endt),5, Data.filenvt(i).TS(begint:endt)/1000000,'o');
                % hold on;
                plot(Data.axpos(i),...
                    Data.filenvt(i).X(begint:endt),...
                    Data.filenvt(i).Y(begint:endt),'Color','k','LineWidth',0.25);
                
                
                %show spyke on position
                if isfield(Data,'filentt')
                    for idfilentt=1:length(Data.filentt)
                        
                        colorm=lines(length(Data.filentt(idfilentt).clustorder));
                        begintt = find(Data.filentt(idfilentt).TS>Data.start*1000000,1,'first');
                        endtt =find(Data.filentt(idfilentt).TS<(Data.start+Data.range)*1000000,1,'last');
                        for iitrack=find(Data.filentt(idfilentt).showcmark==1)
                            nclust=Data.filentt(idfilentt).clustorder(iitrack);
                            idclusts = find(Data.filentt(idfilentt).clust(begintt:endtt)==nclust);
                            
                            clustX=interp1(Data.filenvt(i).TS(begint:endt),Data.filenvt(i).X(begint:endt),Data.filentt(idfilentt).TS(begintt-1+idclusts));
                            clustY=interp1(Data.filenvt(i).TS(begint:endt),Data.filenvt(i).Y(begint:endt),Data.filentt(idfilentt).TS(begintt-1+idclusts));
                            
                            scatter(Data.axpos(i),clustX,clustY,70,colorm(iitrack,:),'o','LineWidth',2);
                            
                        end
                    end
                end
                
                
                set(Data.axpos(i),'XLim',[min(Data.filenvt(i).X) max(Data.filenvt(i).X) ]);
                set(Data.axpos(i),'YLim',[min(Data.filenvt(i).Y) max(Data.filenvt(i).Y)]);
                set(Data.axpos(i),'YDir','reverse');
                colorbar('peer',Data.axpos(i),'location','SouthOutside');
            end
            
            set(Data.ax(i),'XLim',[Data.start Data.start+Data.range]);
            numorder=find(order==i);
            if numorder~=length(order)
                if numorder==1
                    set(Data.ax(i),'Xaxislocation','top');
                else
                    set(Data.ax(i),'xticklabel',[]);
                end
            end
            if ~mod(numorder,2)
                set(Data.ax(i),'yaxislocation','right');
            end
        end
       
        
    end
end
for i=find(strcmp({Data.xtraFileData(:).ftype},'mpg'))
 if  Data.filevideo(i).streamvideo==1
            mainfig=gcf;
            if isempty(Data.filevideo(i).videoPlayerfigure) || ~ishandle(Data.filevideo(i).videoPlayerfigure)
                Data.filevideo(i).videoPlayerfigure=figure;
            else
                set(0,'currentfigure',Data.filevideo(i).videoPlayerfigure);
            end
            mmread(Data.filevideo(i).filename, [], [Data.start Data.start+Data.range]+Data.filevideo(i).synctime, 0, 1, 'processFrame');
            set(0,'currentfigure',mainfig);
 end
end
tmplink=[];
if isfield(Data, 'ax')
    tmplink=[tmplink Data.ax(logical([Data.xtraFileData(:).viewgraph]==1))];
end



Data= eegcorrelation(Data);


if isfield(Data, 'axftt')
    for specti=find([Data.xtraFileData(:).viewfft]==1)
        if get(Data.ctrlsig(specti).nlyztype,'value')==1 || (get(Data.ctrlsig(specti).nlyztype,'value')>3 && get(Data.ctrlsig(specti).nlyztype,'value')~=8)
            tmplink=[tmplink Data.axftt(specti)];
        end
    end
end
try
    linkaxes(tmplink,'x');
catch
    warning('linkaxes error');
end

% linkaxes( Data.ax,'y');
if exist('Data', 'var') && isfield(Data, 'lineTS')
    idsTS = find([Data.lineTS(:).TS]> Data.start & [Data.lineTS(:).TS]< (Data.start +Data.range));
    for id=idsTS
        Data = updatelineTS(Data,id);
    end
end
if exist('Data', 'var') && isfield(Data, 'filentt')
    nttplotTranversalmark(Data);
end

if isfield(Data, 'ax') &&Data.xtraFileData(Data.currentctrlaxe).viewgraph==1&& ishandle(Data.ax(Data.currentctrlaxe)) && isprop(Data.ax(Data.currentctrlaxe),'LineWidth')
    set(Data.ax(Data.currentctrlaxe),'LineWidth',2);
end
if exist('Data', 'var') && isfield(Data, 'winTS')
    Data = updaterange(Data);
end
if isfield(Data, 'spkypesrch') && sum([Data.spkypesrch(:).activate])
    Data=showsearchmin(Data);
end
drawnow;
if Data.CSD==1
    if ~isfield(Data, 'figCSD') || ~ishandle(Data.figCSD)
        Data.figCSD=figure('name','CSD (live)');
       Data.axeCSD=axes('parent',Data.figCSD);
    end

%     axecsd=foundobj(axes('parent',Data.figCSD);
    Csdview(Data, Data.axeCSD);
end
%end
%select current axe (for interface) by click on graph

function Data= eegcorrelation(Data)
if isfield(Data, 'axftt')
    
    for i=find([Data.xtraFileData(:).viewfft]==1)
        if get(Data.ctrlsig(i).nlyztype,'value')==8
            sig2=Data.xtraFileData(i).correlationeeg;
             params.tapers = [3 5];
               params.Fs=Data.file(i).currentSF;
               params.pad=0;
               params.err=[2 3];
               params.fpass=[Data.xtraFileData(i).nlyzminf Data.xtraFileData(i).nlyzmaxf];
                params.trialave=1;
                params.segave=1;
             [C,phi,S12,S1,S2,f,confC,phistd,Cerr]=coherencysegc(Data.file(i).Samples,Data.file(sig2).Samples,2,params);
%              [C,phi,S12,S1,S2,f,confC,phistd,Cerr]=coherencyc(Data.file(i).Samples,Data.file(sig2).Samples,params);
             set(gcf,'CurrentAxes',Data.axftt(i));
             ax = plotyy( f, C,f,phistd,'Parent',Data.axftt(i));
%              ylabel(['Corr ' Data.xtraFileData(isig2).name '/' Data.xtraFileData(i).name ' = ' num2str(SdBcorr)])
             

        end
        
        
        
        if get(Data.ctrlsig(i).nlyztype,'value')==4 || get(Data.ctrlsig(i).nlyztype,'value')==7
            
            %% calcul spectogram
            sizeS=size(Data.file(i).Samples,1);
            if Data.xtraFileData(i).frame_length==0
                frame_length  =(1/Data.file(i).currentSF)*sizeS*100;% ms
            else
                frame_length  =Data.xtraFileData(i).frame_length;
            end
            if Data.xtraFileData(i).frame_overlap==0
                frame_overlap = ((1/Data.file(i).currentSF)*sizeS*100)/1.02;%
            else
                frame_overlap = Data.xtraFileData(i).frame_overlap;
            end
           if  get(Data.ctrlsig(i).nlyztype,'value')==7
            
            windows='hamming';
            %         windows='rectwin';
            [S, F, T]= spStft(Data.file(i).Samples, windows, frame_overlap, frame_length, Data.file(i).currentSF);%  , 'plot'
            SdB = 30 * log10(abs(S)); % dB
            
%             ax = imagesc(T+Data.start, F(logical(F>=Data.xtraFileData(i).nlyzminf & F<= Data.xtraFileData(i).nlyzmaxf)), SdB(logical(F>=Data.xtraFileData(i).nlyzminf & F<= Data.xtraFileData(i).nlyzmaxf),:));
            
            if ~isempty(Data.xtraFileData(i).correlationeeg)&& ~isempty(strcmp(Data.xtraFileData(Data.xtraFileData(i).correlationeeg).correlationeeg,'ncs'))
                isig2=Data.xtraFileData(i).correlationeeg;
                [S, F, T]= spStft(Data.file(isig2).Samples, windows, frame_overlap, frame_length, Data.file(isig2).currentSF);%  , 'plot'
                SdB2 = 30 * log10(abs(S)); % dB
%                 ax = imagesc(T+Data.start, F(logical(F>=Data.xtraFileData(i).nlyzminf & F<= Data.xtraFileData(i).nlyzmaxf)), SdB2(logical(F>=Data.xtraFileData(i).nlyzminf & F<= Data.xtraFileData(i).nlyzmaxf),:));
                
            end
           else
               params.tapers = [3 5];
               params.Fs=Data.file(i).currentSF;
               params.pad=0;
               params.fpass=[Data.xtraFileData(i).nlyzminf Data.xtraFileData(i).nlyzmaxf];
               [S, T,F]=mtspecgramc(Data.file(i).Samples,[frame_length*1E-3 (frame_length-frame_overlap)*1E-3],params);

               SdB = 30 * log10(abs(S)); % dB
%                SdB =S;
               if ~isempty(Data.xtraFileData(i).correlationeeg)&& ~isempty(strcmp(Data.xtraFileData(Data.xtraFileData(i).correlationeeg).correlationeeg,'ncs'))
                   isig2=Data.xtraFileData(i).correlationeeg;
                   [S,  T,F]= mtspecgramc(Data.file(isig2).Samples,[frame_length*1E-3 (frame_length-frame_overlap)*1E-3],params);
                   SdB2 = 30 * log10(abs(S)); % dB
%                    SdB2 =S;
                   %                 ax = imagesc(T+Data.start, F(logical(F>=Data.xtraFileData(i).nlyzminf & F<= Data.xtraFileData(i).nlyzmaxf)), SdB2(logical(F>=Data.xtraFileData(i).nlyzminf & F<= Data.xtraFileData(i).nlyzmaxf),:));
                   
               end
               
           end
            
            %% calcul correlation
            %coef total
            if  get(Data.ctrlsig(i).nlyztype,'value')==7
                SdB= SdB(logical(F>=Data.xtraFileData(i).nlyzminf & F<= Data.xtraFileData(i).nlyzmaxf),:);
                SdB2= SdB2(logical(F>=Data.xtraFileData(i).nlyzminf & F<= Data.xtraFileData(i).nlyzmaxf),:);
            end
            SdBcorr=corr2(SdB,  SdB2);
            % by freq
             SdBdiff=abs(SdB-SdB2);
             
            
            %% draw correlation
            set(gcf,'CurrentAxes',Data.axftt(i));
            if  get(Data.ctrlsig(i).nlyztype,'value')==7
             ax = imagesc(T+Data.start, F(logical(F>=Data.xtraFileData(i).nlyzminf & F<= Data.xtraFileData(i).nlyzmaxf)), SdBdiff,'Parent',Data.axftt(i));
            else
%                 ax=pcolor( Data.axftt(i),T+Data.start,F,SdBdiff');
                ax = imagesc(T+Data.start,F,SdBdiff','Parent',Data.axftt(i));
            end
            set(get(ax, 'Parent'), 'YDir', 'normal');
            ylabel(['Corr ' Data.xtraFileData(isig2).name '/' Data.xtraFileData(i).name ' = ' num2str(SdBcorr)])
        
        end
    end
end



function AxeButtonDownFcn(hObject, eventdata, id)
Data=guidata(gcbf);
if id ~= Data.currentctrlaxe
    if isfield(Data, 'ax') && Data.xtraFileData(Data.currentctrlaxe).viewgraph==1&&ishandle(Data.ax(Data.currentctrlaxe)) && isprop(Data.ax(Data.currentctrlaxe),'LineWidth')
        set(Data.ax(Data.currentctrlaxe),'LineWidth',1);
    end
    
    if isfield(Data, 'ax') &&Data.xtraFileData(id).viewgraph==1&& ishandle(Data.ax(id))  && isprop(Data.ax(id),'LineWidth')
        set(Data.ax(id),'LineWidth',2);
    end
    SNames = fieldnames(Data.ctrlsig(Data.currentctrlaxe));
    for loopIndex = 1:numel(SNames)
        if ishandle(Data.ctrlsig(Data.currentctrlaxe).(SNames{loopIndex}))
            set(Data.ctrlsig(Data.currentctrlaxe).(SNames{loopIndex}),'visible','off');
        end
        if strcmp(SNames{loopIndex},'clustprop') && ~isempty(Data.ctrlsig(Data.currentctrlaxe).(SNames{loopIndex}))
            for subcell=1:length(Data.ctrlsig(Data.currentctrlaxe).(SNames{loopIndex}))
                
                set(Data.ctrlsig(Data.currentctrlaxe).(SNames{loopIndex}){subcell}.edit,'visible','off');
                set(Data.ctrlsig(Data.currentctrlaxe).(SNames{loopIndex}){subcell}.checkmark,'visible','off');
                set(Data.ctrlsig(Data.currentctrlaxe).(SNames{loopIndex}){subcell}.name,'visible','off');
            end
        end
        
        if ishandle(Data.ctrlsig(id).(SNames{loopIndex}))
            set(Data.ctrlsig(id).(SNames{loopIndex}),'visible','on');
        end
        if strcmp(SNames{loopIndex},'clustprop') && ~isempty(Data.ctrlsig(id).(SNames{loopIndex}))
            for subcell=1:length(Data.ctrlsig(id).(SNames{loopIndex}))
                
                set(Data.ctrlsig(id).(SNames{loopIndex}){subcell}.edit,'visible','on');
                set(Data.ctrlsig(id).(SNames{loopIndex}){subcell}.checkmark,'visible','on');
                set(Data.ctrlsig(id).(SNames{loopIndex}){subcell}.name,'visible','on');
            end
        end
    end
    Data.currentctrlaxe=id;
end
nextctrl='on';
prevctrl='on';
if Data.currentctrlaxe==1
    prevctrl='off';
elseif Data.currentctrlaxe==length(Data.xtraFileData)
    nextctrl='off';
end
set(Data.pushbtnextgraphctrl,'visible',nextctrl);
set(Data.pushbtprevgraphctrl,'visible',prevctrl);


guidata(gcbf,Data)
updateminimafinder();

function updateminimafinder()
Data=guidata(gcbf);
if  strcmp(Data.xtraFileData(Data.currentctrlaxe).ftype,'ncs')
    
    set(Data.panelfindspyke,'visible','on');
    set(Data.notcloserth,'string',num2str(Data.spkypesrch(Data.currentctrlaxe).closerth));
    set(Data.morethan,'string',num2str(Data.spkypesrch(Data.currentctrlaxe).moreth));
    set(Data.localminact,'value',Data.spkypesrch(Data.currentctrlaxe).activate);
    set(Data.checkboxfmin,'value',Data.spkypesrch(Data.currentctrlaxe).min);
    set(Data.checkboxfmax,'value',Data.spkypesrch(Data.currentctrlaxe).max);
    if Data.spkypesrch(Data.currentctrlaxe).activate==1
        set(Data.bttrim,'visible','on');
        set(Data.exportspyke,'visible','on');
    else
        set(Data.bttrim,'visible','off');
        set(Data.exportspyke,'visible','off');
    end
    
else
    set(Data.panelfindspyke,'visible','off');
end


% --- Executes on slider movement.
function SlidTime_Callback(hObject, eventdata, handles)
% hObject    handle to SlidTime (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'Value') returns position of slider
%        get(hObject,'Min') and get(hObject,'Max') to determine range of slider
Data=guidata(gcbf);
Data.start=get(hObject,'Value');
Data = update_graph(Data);
guidata(gcbf,Data)

% --- Executes during object creation, after setting all properties.
function SlidTime_CreateFcn(hObject, eventdata, handles)
% hObject    handle to SlidTime (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: slider controls usually have a light gray background.
if isequal(get(hObject,'BackgroundColor'), get(0,'defaultUicontrolBackgroundColor'))
    set(hObject,'BackgroundColor',[.9 .9 .9]);
end


% --- Executes on button press in pushbutton_uprange.
function pushbutton_uprange_Callback(hObject, eventdata, handles)
% hObject    handle to pushbutton_uprange (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);

Data.range=Data.range*0.6;
if Data.range<Data.stepmmin*2
   Data.range= Data.stepmmin*2;
end
Data=updatesliderstep(Data);
Data = update_graph(Data);
guidata(gcbf,Data)

% --- Executes on button press in pushbutton_downrange.
function pushbutton_downrange_Callback(hObject, eventdata, handles)
% hObject    handle to pushbutton_downrange (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);

Data.range=Data.range*2;
Data=updatesliderstep(Data);
Data = update_graph(Data);

guidata(gcbf,Data)
function Data = updatesliderstep(Data)
%set(Data.SlidTime, 'Min', 0);
max=double((Data.endtime)-Data.range);
%[handles,levels,parentIds,listing] = findjobj(Data.SlidTime,'list');

if(max>0)
    stepm =(0.5*Data.range)/max;
    if stepm >1
        stepm =1;
    end
    if (Data.stepmmin/max)>stepm
        stepm=Data.stepmmin/max;
        
    end
    set(Data.SlidTime, 'Visible','on' );
    set(Data.SlidTime, 'Max',max );
    set(Data.SlidTime,'SliderStep',[stepm,Data.range/max]);
else
    set(Data.SlidTime, 'Visible','off' );
    %   'range/max'
    %   max
end
set(Data.editbegintime,'string',num2str(Data.start));
set(Data.editrange,'string',num2str(Data.range));


% --- Executes on selection change in popupmenu1.
function popupmenu1_Callback(hObject, eventdata, handles)
% hObject    handle to popupmenu1 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: contents = cellstr(get(hObject,'String')) returns popupmenu1 contents as cell array
%        contents{get(hObject,'Value')} returns selected item from popupmenu1


% --- Executes during object creation, after setting all properties.
function popupmenu1_CreateFcn(hObject, eventdata, handles)
% hObject    handle to popupmenu1 (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: popupmenu controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc && isequal(get(hObject,'BackgroundColor'), get(0,'defaultUicontrolBackgroundColor'))
    set(hObject,'BackgroundColor','white');
end


% --- Executes on button press in pushbuttonAddmark.
function pushbuttonAddmark_Callback(hObject, eventdata, handles)
% hObject    handle to pushbuttonAddmark (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
p=ginput(1);
if exist('Data', 'var') && isfield(Data, 'lineTS')
    id=length(Data.lineTS)+1;
else
    id=1;
end
set(Data.texttsmark,'string',sprintf( '%f s\nTS: %i',p(1), round(p(1)*1E6+Data.TSfirstpoint)));
Data.lineTS(id)=struct('TS',p(1),'line',[]);
spikeData = updatelineTS(Data,id);
guidata(gcbf,Data)


function Data = updatelineTS(Data,id)
%disp('updatellinets');
for i=find([Data.xtraFileData(:).viewgraph]==1)
    
    Data.lineTS(id).line(i)=line([Data.lineTS(id).TS Data.lineTS(id).TS],[0 0]);
    set(Data.lineTS(id).line(i),'Parent',Data.ax(i),'color','r');
    set(Data.lineTS(id).line(i),'YData',get(Data.ax(i),'YLim'),...
        'EraseMode','xor',...
        'ButtonDownFcn',{@clicklinecallback,id});
    
end

function nttplotTranversalmark(Data)

for i=1:length(Data.filentt)
    
    drawclustmark(Data,find(Data.filentt(i).showcmark==1),i);
end



function drawclustmark(Data,ntracks,idfile)
if ~isempty(ntracks)
    
    
    
    colorm=lines(length(Data.filentt(idfile).clustorder));
    begint = find(Data.filentt(idfile).TS>Data.start*1000000,1,'first');
    endt =find(Data.filentt(idfile).TS<(Data.start+Data.range)*1000000,1,'last');
    for iitrack=ntracks
        nclust=Data.filentt(idfile).clustorder(iitrack);
        %     nclust=nclusts(iiclust);
        idclusts = find(Data.filentt(idfile).clust(begint:endt)==nclust);
        %     for iclust=1:length(idclusts)
        
        for i=find([Data.xtraFileData(:).viewgraph]==1)
            TS=(Data.filentt(idfile).TS(begint-1+idclusts)/1000000);
            
            if ~isempty(TS)
                li=line( (TS*[1 1])',zeros(2,length(idclusts)));
                set(li,'Parent',Data.ax(i),'color',colorm(iitrack,:));
                set(li,'YData',get(Data.ax(i),'YLim'),...
                    'EraseMode','xor');
            end
        end
    end
end


function clicklinecallback(hObject, eventdata, id)
Data=guidata(gcbf);
for i=find([Data.xtraFileData(:).viewgraph]==1)
    set(Data.lineTS(id).line(i),'selected','on');
end
set(Data.texttsmark,'string',sprintf( '%f s\nTS: %i',Data.lineTS(id).TS, round(Data.lineTS(id).TS*1E6+Data.TSfirstpoint)));

if Data.linedelmode==0
    p=ginput(1);
    
    Data.lineTS(id).TS=p(1);
    set(Data.texttsmark,'string',sprintf( '%f s\nTS: %i',p(1), round(p(1)*1E6+Data.TSfirstpoint)));
    
    for i=find([Data.xtraFileData(:).viewgraph]==1)
        %clear Data.lineTS(id).line(i);
        % Data.lineTS(id).line(i)=line([p(1) p(1)],[0 0]);
        % set(Data.lineTS(id).line(i),'Parent',Data.ax(i),'color','r');
        set(Data.lineTS(id).line(i),'XData',[p(1) p(1)],...
            'selected','off');
        
        % set(Data.lineTS(id).line(i),'EraseMode','xor');
        % set(Data.lineTS(id).line(i),'ButtonDownFcn',{@clicklinecallback,id});
    end
    
else
    Data.lineTS(id).TS=-1;
    delete(Data.lineTS(id).line(logical([Data.xtraFileData(:).viewgraph]==1)));
    Data.linedelmode=0;
end
guidata(gcf,Data);

% --- Executes on button press in pushbuttondelline.
function pushbuttondelline_Callback(hObject, eventdata, handles)
% hObject    handle to pushbuttondelline (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
Data.linedelmode=1;
guidata(gcbf,Data);


% --- Executes on button press in pushbuttonimportts.
function pushbuttonimportts_Callback(hObject, eventdata, handles)
% hObject    handle to pushbuttonimportts (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
[name, path]=uigetfile({'*.xlsx;*.xls;*.csv;*.mat'},'Select File','Multiselect','off');
cd(path);
if ~isempty(strfind(lower(char(name)),'.mat'))
    load(name,'TS');
else
    TS= xlsread(name);
end
TS=(TS-Data.TSfirstpoint)*10^-6;

for id=1:length(TS)
    Data.lineTS(id)=struct('TS',TS(id),'line',[]);
    Data = updatelineTS(Data,id);
end


cd(Data.Path);
guidata(gcbf,Data);

% --- Executes on button press in pushbuttonexportts.
function pushbuttonexportts_Callback(hObject, eventdata, handles)
% hObject    handle to pushbuttonexportts (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
TS=[Data.lineTS(:).TS];
TS=sort(TS(TS>0));
TS= TS*10^6;
TS= TS+Data.TSfirstpoint;

[filename, pathname,filterindex] = uiputfile(...
    {'*.csv';'*.xlsx';'*.xls';'*.mat'},...
    'Save as');

if isequal(filename,0) || isequal(pathname,0)
    disp('User selected Cancel')
else
    disp(['User selected ',fullfile(pathname,filename)])
    cd( pathname);
    switch filterindex
        case {2,3}
            xlswrite(filename,round(TS))
        case 1
            dlmwrite(filename,round(TS),'delimiter','\t','precision', 20);
        case 4
            save(filename,'TS');
    end
    cd(Data.Path);
end


% --- Executes on button press in pushbtcreatewindow.
function pushbtcreatewindow_Callback(hObject, eventdata, handles)
% hObject    handle to pushbtcreatewindow (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
p=ginput(1);
%Data.winrec=rectangle('Position',[p(1),0,0.1,0.1],'FaceColor','y','EraseMode','background');
set(hObject,'visible','off');
set(Data.pushbuttondelrange,'visible','on');
set(Data.popupmenurangeaction,'visible','on');

for i=find([Data.xtraFileData(:).viewgraph]==1)
    Data.winrec(i)=rectangle('Position',[p(1),0,0.1,0.1],'FaceColor','y','EraseMode','xor','Parent',Data.ax(i),'ButtonDownFcn',{@startwindowdragrange});
end
for id=1:2
    Data.winTS(id)=struct('TS',p(1),'line',[]);
    for i=find([Data.xtraFileData(:).viewgraph]==1)
        
        
        Data.winTS(id).line(i)=line(Data.winTS(id).TS *[1 1],[0 0]);
        set(Data.winTS(id).line(i),'Parent',Data.ax(i),'color','m');
        set(Data.winTS(id).line(i),'YData',get(Data.ax(i),'YLim'),...
            'EraseMode','xor',...
            'ButtonDownFcn',{@startwindowdrag,id});
        
    end
end

guidata(gcbf,Data);
startwindowdrag(Data.winTS(2).line(1),eventdata,id);


function startwindowdrag(hObject, eventdata, id)
% disp('startdrag');
% disp(id);
Data=guidata(gcbf);

set(gcf,'Pointer','custom','PointerShapeCData',double(Data.arrowpointer),'PointerShapeHotSpot',[9 9]);
%set(gcf,'Pointer','fleur');


set(gcbf,'WindowButtonUpFcn',{@stopdragwin,id});
set(gcbf,'WindowButtonMotionFcn',{@draggingwin,id});

function draggingwin(hObject, eventdata, id)
pt=get(gca,'CurrentPoint');
updatewinTS(pt(1),id);


function  updatewinTS(ptx,id)
Data=guidata(gcbf);
%disp('updatellinets');
for i=find([Data.xtraFileData(:).viewgraph]==1)
    
    Data.winTS(id).TS=ptx;
    set(Data.winTS(id).line(i),'XData',[ptx ptx] );
    ylim=get(Data.ax(i),'YLim');
    tmptx=sort([Data.winTS(:).TS]);
    if (tmptx(2)-tmptx(1)~=0) &&  (ylim(2)-ylim(1)~=0)
        set(Data.winrec(i),'position',[tmptx(1) ylim(1)   tmptx(2)-tmptx(1)  ylim(2)-ylim(1)] );
    end
    
end
Data=updatetxtrangeinfo(Data);
guidata(gcbf,Data);
function stopdragwin(hObject, eventdata, id)

set(gcf,'WindowButtonMotionFcn','');
set(gcf,'Pointer','arrow')


function Data=updatetxtrangeinfo(Data)

T=abs(Data.winTS(1).TS-Data.winTS(2).TS);
set(Data.textrangeinfo,'visible','on','string',['T : ' num2str(T) 's  /  F : ' num2str(1/T) 'Hz']);

%%drag all the range
function startwindowdragrange(hObject, eventdata)
Data=guidata(gcbf);
set(gcf,'Pointer','fleur')
Data.tmpcurentptx=get(gca,'CurrentPoint');
Data.tmpcurentptx=Data.tmpcurentptx(1);
set(gcbf,'WindowButtonUpFcn',{@stopdragwinrange});
set(gcbf,'WindowButtonMotionFcn',{@draggingwinrange});
guidata(gcbf,Data);

function draggingwinrange(hObject, eventdata, id)

pt=get(gca,'CurrentPoint');
updatewinTSrange(pt(1));



function  updatewinTSrange(ptx)
Data=guidata(gcbf);
diff= (Data.tmpcurentptx-ptx)/6;
Data.tmpcurentptx=ptx;
%disp('updatellinets');
for id=1:2
    for i=find([Data.xtraFileData(:).viewgraph]==1)
        
        
        if (Data.winTS(id).TS-diff)<0
            Data.winTS(id).TS=0;
        elseif (Data.winTS(id).TS-diff)>Data.endtime
            Data.winTS(id).TS=Data.endtime;
        else
            Data.winTS(id).TS=Data.winTS(id).TS-diff;
        end
        set(Data.winTS(id).line(i),'XData',Data.winTS(id).TS*[1 1] );
        
    end
end

for i=find([Data.xtraFileData(:).viewgraph]==1)
    
    
    ylim=get(Data.ax(i),'YLim');
    tmptx=sort([Data.winTS(:).TS]);
    set(Data.winrec(i),'position',[tmptx(1) ylim(1)   tmptx(2)-tmptx(1)  ylim(2)-ylim(1)] );
    
end
guidata(gcbf,Data);
function stopdragwinrange(hObject, eventdata, id)
set(gcf,'WindowButtonMotionFcn','');
set(gcf,'Pointer','arrow')


function Data= updaterange(Data)
if(Data.winTS(1).TS>= Data.start &&Data.winTS(1).TS<= Data.start+Data.range)||(Data.winTS(2).TS>= Data.start &&Data.winTS(2).TS<= Data.start+Data.range)
    for i=find([Data.xtraFileData(:).viewgraph]==1)
        
        ylim=get(Data.ax(i),'YLim');
        tmptx=sort([Data.winTS(:).TS]);
        Data.winrec(i)=rectangle('Position',[tmptx(1) ylim(1)   tmptx(2)-tmptx(1)  ylim(2)-ylim(1)],'FaceColor','y','EraseMode','xor','Parent',Data.ax(i),'ButtonDownFcn',{@startwindowdragrange});
        
    end
    for id=1:2
        %Data.winTS(id)=struct('TS',p(1),'line',[]);
        for i=find([Data.xtraFileData(:).viewgraph]==1)
            
            
            Data.winTS(id).line(i)=line(Data.winTS(id).TS *[1 1],[0 0]);
            set(Data.winTS(id).line(i),'Parent',Data.ax(i),'color','m');
            set(Data.winTS(id).line(i),'YData',get(Data.ax(i),'YLim'),...
                'EraseMode','xor',...
                'ButtonDownFcn',{@startwindowdrag,id});
            
        end
    end
end



function editHighPass_Callback(hObject, eventdata, handles)
% hObject    handle to editHighPass (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of editHighPass as text
%        str2double(get(hObject,'String')) returns contents of editHighPass as a double
Data=guidata(gcbf);
Data.highpass = str2double(get(hObject,'String'));
Data = update_graph( Data);
guidata(gcbf,Data);


% --- Executes during object creation, after setting all properties.
function editHighPass_CreateFcn(hObject, eventdata, handles)
% hObject    handle to editHighPass (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc && isequal(get(hObject,'BackgroundColor'), get(0,'defaultUicontrolBackgroundColor'))
    set(hObject,'BackgroundColor','white');
end


% --- Executes on button press in pushbuttondelrange.
function pushbuttondelrange_Callback(hObject, eventdata, handles)
% hObject    handle to pushbuttondelrange (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
set(Data.textrangeinfo,'visible','off')
set(Data.pushbuttondelrange,'visible','off');
set(Data.popupmenurangeaction,'visible','off');
for i=find([Data.xtraFileData(:).viewgraph]==1)
    if ishandle(Data.winrec(i))
        delete(Data.winrec(i));
    end
    for id=1:2
        if ishandle(Data.winTS(id).line(i))
            delete(Data.winTS(id).line(i));
        end
    end
end

Data = rmfield(Data,'winTS');

set(Data.pushbtcreatewindow,'visible','on');

guidata(gcbf,Data);

% --- Executes on selection change in popupmenurangeaction.
function popupmenurangeaction_Callback(hObject, eventdata, handles)
% hObject    handle to popupmenurangeaction (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: contents = cellstr(get(hObject,'String')) returns popupmenurangeaction contents as cell array
%        contents{get(hObject,'Value')} returns selected item from popupmenurangeaction
Data=guidata(gcbf);

switch get(hObject,'Value')
    case 1
        
    case 2
        Data.start= min(Data.winTS(:).TS);
%         if strcmp(Data.xtraFileData(1).ftype,'ncs')
%             Data.start=floor(Data.start/(512*(1/Data.file(1).SF)));
%             Data.start=Data.start*512*(1/Data.file(1).SF);
%         end
        Data.range= max(Data.winTS(:).TS)-Data.start;
%         if strcmp(Data.xtraFileData(1).ftype,'ncs')
%             Data.range=ceil(Data.range/(512*(1/Data.file(1).SF)));
%             Data.range=Data.range*512*(1/Data.file(1).SF);
%         end
        Data =update_graph(Data);
        Data=updatesliderstep(Data);
        set(Data.SlidTime, 'Value',Data.start );
    case {3,4}
        startts= min(Data.winTS(:).TS);
        maxts= max(Data.winTS(:).TS);
        if startts<Data.start ||maxts> Data.start+Data.range
            if startts<Data.start
                Data.start= min(Data.winTS(:).TS);
                if strcmp(Data.xtraFileData(1).ftype,'ncs')
                    Data.start=floor(Data.start/(512*(1/Data.file(1).SF)));
                    Data.start=Data.start*512*(1/Data.file(1).SF);
                end
            end
            if maxts> Data.start+Data.range
                Data.range= max(Data.winTS(:).TS)-Data.start;
                if strcmp(Data.xtraFileData(1).ftype,'ncs')
                    Data.range=ceil(Data.range/(512*(1/Data.file(1).SF)));
                    Data.range=Data.range*512*(1/Data.file(1).SF);
                end
            end
            Data =update_graph(Data);
            Data=updatesliderstep(Data);
            set(Data.SlidTime, 'Value',Data.start );
        end
        
        cptfig=0;
        for i = 1:length(Data.file)
            if strcmp(Data.xtraFileData(i).ftype,'ncs') && Data.xtraFileData(i).viewgraph==1
                cptfig= cptfig+1 ;
            end
        end
        figure('name',['FFT of signals range [' num2str(startts),'s ; ', num2str(maxts) 's]']);
        cpt=0;
        for i = 1:length(Data.file)
            if strcmp(Data.xtraFileData(i).ftype,'ncs') && Data.xtraFileData(i).viewgraph==1
                cpt=cpt+1;
                %
                id_startts= round((startts-Data.start)*Data.file(i).currentSF);
                id_endts= round((maxts-Data.start)*Data.file(i).currentSF);
                % id_startts=round(id_startts);
                %         length(Data.file(i).Samples(id_startts:id_endts))
                %         length((startts:1/Data.file(i).currentSF:max(Data.winTS(:).TS)+1/Data.file(i).currentSF))
                %zoom
                %plot((startts:1/Data.file(i).currentSF:max(Data.winTS(:).TS)+1/Data.file(i).currentSF),Data.file(i).Samples(id_startts:id_endts));
                
                %                 NFFT = 2^nextpow2((id_endts-id_startts)*10);% *10 increase the sampling of the fft
                sizeS= (id_endts -  id_startts) +1;
                ratiomaxf = Data.file(i).currentSF/Data.xtraFileData(i).nlyzmaxf;
                
                if ratiomaxf*100>round(sizeS/20)
                    a=floor(sizeS/ratiomaxf );
                    if a==0
                        window=sizeS;
                    elseif a>100
                        window=ratiomaxf*100;
                    else
                        window=ratiomaxf*a;
                    end
                else
                    window= sizeS/20;
                end
                window=round(window);
                
                res=(Data.xtraFileData(i).nlyzmaxf - Data.xtraFileData(i).nlyzminf )/400;
                
                
                
                if get(hObject,'Value')==4
                    [Y,f]=pwelch(diff(Data.file(i).Samples(id_startts:id_endts)),window,round(window/2),round(Data.file(i).currentSF/res),Data.file(i).currentSF);
                else
                    [Y,f]=pwelch(Data.file(i).Samples(id_startts:id_endts),window,round(window/2),round(Data.file(i).currentSF/res),Data.file(i).currentSF);
                end
                
                
                %                     Y = fft(diff(Data.file(i).Samples(id_startts:id_endts)),NFFT)/((id_endts-id_startts)-1);
                %                 else
                %                     Y = fft(Data.file(i).Samples(id_startts:id_endts),NFFT)/(id_endts-id_startts);
                %                 end
                %
                %                 f = Data.file(i).currentSF/2*linspace(0,1,NFFT/2+1);
                
                % Plot single-sided amplitude spectrum.
                %subplot(1,length(Data.file),i,2*abs(Y(1:NFFT/2+1)))
                
                subplot(cptfig,1,i);
                %                 plot(f,2*abs(Y(1:NFFT/2+1)));
                pl=plot(f,Y);
                set(gca,'XLim',[Data.highpass-1 Data.file(i).currentSF/5]);
                set(gca,'YMinorgrid','on');
                set(gca,'XMinorgrid','on');
                set(gca,'XLim',[Data.xtraFileData(i).nlyzminf Data.xtraFileData(i).nlyzmaxf]);
                title(Data.file(i).AcqEntName);
                xlabel('Frequency (Hz)')
                ylabel('|Y(f)|')
            end
        end
end
set(hObject,'Value',1);

guidata(gcbf,Data);



% --- Executes during object creation, after setting all properties.
function popupmenurangeaction_CreateFcn(hObject, eventdata, handles)
% hObject    handle to popupmenurangeaction (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: popupmenu controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc && isequal(get(hObject,'BackgroundColor'), get(0,'defaultUicontrolBackgroundColor'))
    set(hObject,'BackgroundColor','white');
    
end



function editlow_Callback(hObject, eventdata, handles)
% hObject    handle to editlow (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of editlow as text
%        str2double(get(hObject,'String')) returns contents of editlow as a double
Data=guidata(gcbf);
Data.lowpass = str2double(get(hObject,'String'));
Data = update_graph( Data);
guidata(gcbf,Data);

% --- Executes during object creation, after setting all properties.
function editlow_CreateFcn(hObject, eventdata, handles)
% hObject    handle to editlow (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc && isequal(get(hObject,'BackgroundColor'), get(0,'defaultUicontrolBackgroundColor'))
    set(hObject,'BackgroundColor','white');
end




% --- Executes on button press in pushbtprevgraphctrl.
function pushbtprevgraphctrl_Callback(hObject, eventdata, handles)
% hObject    handle to pushbtprevgraphctrl (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
AxeButtonDownFcn(hObject, eventdata, Data.currentctrlaxe-1)

% --- Executes on button press in pushbtnextgraphctrl.
function pushbtnextgraphctrl_Callback(hObject, eventdata, handles)
% hObject    handle to pushbtnextgraphctrl (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
AxeButtonDownFcn(hObject, eventdata, Data.currentctrlaxe+1)



function notcloserth_Callback(hObject, eventdata, handles)
% hObject    handle to notcloserth (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of notcloserth as text
%        str2double(get(hObject,'String')) returns contents of notcloserth as a double
Data=guidata(gcbf);
Data.spkypesrch(Data.currentctrlaxe).closerth = str2num(get(hObject,'String'));
if  Data.xtraFileData(Data.currentctrlaxe).duplicate~=0
    Data.spkypesrch(abs(Data.xtraFileData(Data.currentctrlaxe).duplicate)).closerth =Data.spkypesrch(Data.currentctrlaxe).closerth ;
end
if Data.spkypesrch(Data.currentctrlaxe).activate
    Data = update_graph( Data,'true');
end
guidata(gcbf,Data);

% --- Executes during object creation, after setting all properties.
function notcloserth_CreateFcn(hObject, eventdata, handles)
% hObject    handle to notcloserth (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc && isequal(get(hObject,'BackgroundColor'), get(0,'defaultUicontrolBackgroundColor'))
    set(hObject,'BackgroundColor','white');
end



function morethan_Callback(hObject, eventdata, handles)
% hObject    handle to morethan (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of morethan as text
%        str2double(get(hObject,'String')) returns contents of morethan as a double
Data=guidata(gcbf);
Data.spkypesrch(Data.currentctrlaxe).moreth = str2num(get(hObject,'String'));
if  Data.xtraFileData(Data.currentctrlaxe).duplicate~=0
    Data.spkypesrch(abs(Data.xtraFileData(Data.currentctrlaxe).duplicate)).moreth = Data.spkypesrch(Data.currentctrlaxe).moreth;
end
if Data.spkypesrch(Data.currentctrlaxe).activate
    Data = update_graph( Data,'true');
end
guidata(gcbf,Data);
% --- Executes during object creation, after setting all properties.
function morethan_CreateFcn(hObject, eventdata, handles)
% hObject    handle to morethan (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc && isequal(get(hObject,'BackgroundColor'), get(0,'defaultUicontrolBackgroundColor'))
    set(hObject,'BackgroundColor','white');
end


% --- Executes on button press in localminact.
function localminact_Callback(hObject, eventdata, handles)
% hObject    handle to localminact (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hint: get(hObject,'Value') returns toggle state of localminact

Data=guidata(gcbf);
Data.spkypesrch(Data.currentctrlaxe).activate = get(hObject,'Value') ;
if  Data.xtraFileData(Data.currentctrlaxe).duplicate~=0
    Data.spkypesrch(abs(Data.xtraFileData(Data.currentctrlaxe).duplicate)).activate = Data.spkypesrch(Data.currentctrlaxe).activate  ;
end
guidata(gcbf,Data);
if Data.spkypesrch(Data.currentctrlaxe).activate
    Data = update_graph( Data);
    set(Data.bttrim,'visible','on');
    set(Data.exportspyke,'visible','on');
else
    set(Data.bttrim,'visible','off');
    set(Data.exportspyke,'visible','off');
    Data = update_graph( Data,'true');
end
guidata(gcbf,Data);


function Data = showsearchmin(Data)

set(Data.statussearch,'string','Searching...');
abssig=0;
Mins={};
drawnow;
% pause(0.001);
init_max_min=[-1 1];
for id=1:length(Data.spkypesrch)
    if Data.spkypesrch(id).activate && Data.xtraFileData(id).duplicate >= 0
        max_min=init_max_min(logical([Data.spkypesrch(id).max Data.spkypesrch(id).min]));
        Mins{id}=[];
        if  ~isempty(Data.spkypesrch(id).moreth)
            for direction=max_min
                li=line( [0 0],-direction* Data.spkypesrch(id).moreth*[1 1]);
                set(li,'Parent',Data.ax(id),'lineStyle','-.','color','r');
                set(li,'XData',get(Data.ax(id),'XLim'),...
                    'EraseMode','xor');%,...
            end
        end
        
        if length(max_min)==2 && max_min(1)==-1 && max_min(2)==1
            max_min=[-1 0];
            abssig=1; % if ask for min and max use absolute value of signal
        end
        for direction=max_min
            
            if  isempty(Data.spkypesrch(id).moreth)
                if abssig
                    Mins{id} = [Mins{id} ;( (LocalMinima(abs(Data.file(id).Samples)*direction,Data.spkypesrch(id).closerth*10^-3*Data.file(id).currentSF)   -1)    /Data.file(id).currentSF)+Data.start ];
                else
                    Mins{id} = [Mins{id} ;( (LocalMinima(     Data.file(id).Samples*direction,Data.spkypesrch(id).closerth*10^-3*Data.file(id).currentSF)   -1)    /Data.file(id).currentSF)+Data.start ];
                    
                end
            else
                
                %                 li=line( [0 0],-direction* Data.spkypesrch(id).moreth*[1 1]);
                %                 set(li,'Parent',Data.ax(id),'lineStyle','-.','color','r');
                %                 set(li,'XData',get(Data.ax(id),'XLim'),...
                %                     'EraseMode','xor');%,...
                if abssig
                    Mins{id} =  [Mins{id}; ( (LocalMinima(abs(Data.file(id).Samples)*direction,...
                        Data.spkypesrch(id).closerth*10^-3*Data.file(id).currentSF,...
                        -1*Data.spkypesrch(id).moreth)-1)   /Data.file(id).currentSF)+Data.start ];
                else
                    Mins{id} =  [Mins{id}; ( (LocalMinima(Data.file(id).Samples*direction,...
                        Data.spkypesrch(id).closerth*10^-3*Data.file(id).currentSF,...
                        -1*Data.spkypesrch(id).moreth)-1)   /Data.file(id).currentSF)+Data.start ];
                end
            end
        end
        %         if length(max_min)>1
        %             Mins{id}=sort(Mins{id});
        %
        %         end
    end
end
% Minsl=[];
% if length(Mins)>1
%     for i=1:length( Mins{1})
%
%         if (length( Mins)-1)==length(find(round([Mins{2:end}])==round(Mins{1}(i))))
%             Minsl=[Minsl Mins{1}(i)];
%         end
%     end
%
% else
%    Minsl= Mins{1};
% end
%Minsl=Minsl/1000;
Data.Mins=Mins;
colorm=lines(length(Mins)+1);
set(Data.statussearch,'string','Draw...');
drawnow;
% pause(0.001);


for id=1:length(Mins)
    if ~isempty(Mins{id})
        for i=find([Data.xtraFileData(:).viewgraph]==1)
            
            
            li=line( (Mins{id} *[1 1])',zeros(2,length(Mins{id})));
            set(li,'Parent',Data.ax(i),'color',colorm(id+1,:));
            set(li,'YData',get(Data.ax(i),'YLim'),...
                'EraseMode','xor');%,...
            %'ButtonDownFcn',{@startwindowdrag,id});
            
        end
    end
end



% for id=1:length(Mins)
%     for imin=1:length( Mins{id})
%         for i=1:length(Data.ax)
%             if(Data.ax(i)~=0)
%
%                 li=line( Mins{id}(imin) *[1 1],[0 0]);
%                 set(li,'Parent',Data.ax(i),'color',colorm(id+1,:));
%                 set(li,'YData',get(Data.ax(i),'YLim'),...
%                     'EraseMode','xor');%,...
%                 %'ButtonDownFcn',{@startwindowdrag,id});
%             end
%         end
%     end
% end


set(Data.statussearch,'string','');


% --- Executes on button press in exportspyke.
function exportspyke_Callback(hObject, eventdata, handles)
% hObject    handle to exportspyke (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

Data=guidata(gcbf);
exportkind=0;
searchfiles=find([Data.spkypesrch(:).activate]&[Data.xtraFileData(:).duplicate] >= 0);

choice = questdlg('What do you want to export?', ...
    'Kind of export', ...
    'Units','Spike(with manual selection)','Spikes (Auto)','Units');
switch choice
    case 'Units'
        exportkind=1;
        filetypesave={'*.ntt';'*.nse';'*.nst';'*.mat'};
        
        [filename, pathname,filterindex] = uiputfile(...
            filetypesave,...
            'Save as');
        
        helpmsg='';
        switch length(searchfiles)
            case 1
                helpmsg= ' Or use Neuralinks NSE format to save 1 signal units.';
            case 2
                helpmsg= ' Or Neuralinks NST format to save 2 signal units.';
            case 4
                helpmsg= ' Or Neuralinks NTT format to save 4 signal units.';
            otherwise
                helpmsg= [' No Neuralinks format compatible to save ',num2str(length(searchfiles)),' signals units. Please select MAT format or activate 1,2 or 4 signals for the detection.'];
        end
        choice='none';
        if filterindex==1 && length(searchfiles)~=4
            if length(searchfiles)<4
                choice=questdlg(['You have to activate 4 channels to export in  Neuralinks NTT format.',helpmsg],'Not compatible format','Add flat signals','Cancel','Add flat signals');
            else
                msgbox(['You have to activate 4 channels to export in  Neuralinks NTT format.',helpmsg],'Not compatible format', 'warn');
                choice='Cancel';
            end
        end
        if filterindex==2 && length(searchfiles)~=1
            
            msgbox(['You have to activate 1 channels to export in Neuralinks NSE format.',helpmsg],'Not compatible format', 'warn');
            filename=0;
        end
        if filterindex==3 && length(searchfiles)~=2
            if length(searchfiles)<2
                choice=questdlg(['You have to activate 2 channels to export in  Neuralinks NST format.',helpmsg],'Not compatible format','Add flat signals','Cancel','Add flat signals');
            else
                msgbox(['You have to activate 2 channels to export in Neuralinks NST format.',helpmsg],'Not compatible format', 'warn');
                choice='Cancel';
            end
        end
        if strcmp(choice,'Cancel')
            filename=0;
        end
    case 'Spike(with manual selection)'
        exportkind=2;
        pathname=Data.Path;
        filename='none';
        %         filetypesave={'*.xls';'*.mat'};
        %         answer={1 2};
        %         while(answer{1}<answer{2})
        %             prompt = {'wich size of signal do you want visualize (ms):','Spyke position (ms) :'};
        %             dlg_title = 'Signals selection setup';
        %             num_lines = 1;
        %             def = {'300','50'};
        %             answer = inputdlg(prompt,dlg_title,num_lines,def);
        %             answer{1} = str2num(answer{1});
        %             answer{2} = str2num(answer{2});
        %             if answer{1}<answer{2}
        %                 uiwait(msgbox('The range must superior to the spike position.','setup error','error'));
        %             end
        %             Data.rangespyke=answer{1}*10^-3 * Data.file(searchfiles(1)).SF;
        %             Data.trimspyke=answer{2}*10^-3 * Data.file(searchfiles(1)).SF;
        %             %todo save setup in sample
        %         end
        
    case 'Spikes (Auto)'
        exportkind=3;
        filetypesave={'*.xls';'*.csv';'*.mat'};
        
        [filename, pathname,filterindex] = uiputfile(...
            filetypesave,...
            'Save as');
        
end





if isequal(filename,0) || isequal(pathname,0)
    disp('User selected Cancel')
else
    old_data=Data;
    if exportkind==3  ||exportkind==2
        Data.rangespyke=0;
        Data.trimspyke=0;
    end
    
    disp(['User selected ',fullfile(pathname,filename)])
    cd( pathname);
    
    start=zeros(1,length(Data.spkypesrch));
    Data.start=0;
    cpt=0;
    spykes={4};
    Minsort={4};
    init_max_min=[-1 1];
    contents = cellstr(get(Data.popupfiltertype,'String')) ;
filtertype=contents{get(Data.popupfiltertype,'Value')};

    while(Data.start+Data.range<Data.endtime-10^-4 )
        cpt=cpt+1;
        Mins={length(Data.spkypesrch)};
        
        

                
                
                
                
        if(min(start(searchfiles)) ~=0)
            
            %synchronise start +margin collect spyke
            
            Data.start=min(start(searchfiles))  +  Data.spkypesrch(id).closerth*10^-3  -  Data.rangespyke/Data.file(id).currentSF ;
            
        else
            Data.start=0;
        end
        
        step=0;
        for id=searchfiles
            
            Data.range=Data.endtime/4;
            if (Data.start+Data.range)>Data.endtime-(Data.endtime/4)
                Data.range=Data.endtime-Data.start-1/Data.file(id).SF;
            end
            
            %if Data.spkypesrch(id).activate
            
            step=step+25/length(searchfiles);
            set(Data.statussearch,'string',['Export ' num2str(round((Data.start*100/Data.endtime ) +step)) '% ...']);
            drawnow;
            %             pause(0.01);
            
            %read file
            
            %todo set no sampling
            
             Data.file(id)=Data.file(id).setfiltertype(filtertype);
            if(get(Data.ctrlsig(id).btfilter,'value')==0)
                Data.file(id)=Data.file(id).setlowpass(Data.lowpass,1);
                Data.file(id)=Data.file(id).sethighpass(Data.highpass);
            else
                Data.file(id)=Data.file(id).setlowpass(Data.xtraFileData(id).lowpass,max([Data.spkypesrch(:).activate]));
                
                %                      Data.file(i)=Data.file(i).setlowpass(Data.xtraFileData(i).lowpass,Data.spkypesrch(i).activate);
                Data.file(id)=Data.file(id).sethighpass(Data.xtraFileData(id).highpass);
            end
            
            if 0
            Data.file(id)=Data.file(id).setstart(floor(Data.start/(512*(1/Data.file(id).SF))));
            Data.file(id)=Data.file(id).setrange(ceil(Data.range/(512*(1/Data.file(id).SF))));
            Data.range =Data.file(id).range*512*(1/Data.file(id).SF);
            
            Data.file(id)=Data.file(id).readdata(1);
            Data.start = Data.file(id).start*512*(1/Data.file(id).SF);
            else
                 Data.file(id)=Data.file(id).setstart(Data.start);
                Data.file(id)=Data.file(id).setrange(Data.range);
                Data.range =Data.file(id).range;
                 Data.file(id)=Data.file(id).readdata(1);
                 Data.start =Data.file(id).start;

            end
            if Data.start ~=0
                
                startsig= start(id)  +  Data.spkypesrch(id).closerth*10^-3   ;
                startfindlocalmin=round( ( startsig-Data.start )*Data.file(id).currentSF)+1;
            else
                startfindlocalmin=1;
            end
            if ~isfield(Data,'rangespyke')
                finfindlocalmin=128; %fixed max for spyke range
            else
                finfindlocalmin=Data.rangespyke+Data.trimspyke;
            end
            
            max_min=init_max_min(logical([Data.spkypesrch(id).max Data.spkypesrch(id).min]));
            Mins{id}=[];
            abssig=0;
            if length(max_min)==2  && max_min(1)==-1 && max_min(2)==1
                max_min=[-1 0];
                abssig=1;
            end
            for direction=max_min
                
                %find minima
                if  isempty(Data.spkypesrch(id).moreth)
                          %                     Mins =[Mins ( (LocalMinima(Data.file(id).Samples*-1,Data.spkypesrch(id).closerth*10^-4*Data.file(id).currentSF)   -1)    /Data.file(id).currentSF)+Data.start ];
                    if abssig
                        Mins{id} = cat(2,Mins{id},  ( (LocalMinima(abs(Data.file(id).Samples(startfindlocalmin:end-finfindlocalmin  ))*direction,Data.spkypesrch(id).closerth*10^-3*Data.file(id).currentSF)   -1+startfindlocalmin)    /Data.file(id).currentSF)'+Data.start );
                    else
                        Mins{id} = cat(2,Mins{id},  ( (LocalMinima(Data.file(id).Samples(startfindlocalmin:end-finfindlocalmin  )*direction,Data.spkypesrch(id).closerth*10^-3*Data.file(id).currentSF)   -1+startfindlocalmin)    /Data.file(id).currentSF)'+Data.start );
              
                        
                    end
                else

                    if abssig
                        Mins{id} = cat(2,Mins{id},  ( (LocalMinima(abs(Data.file(id).Samples(startfindlocalmin:end-finfindlocalmin  ))*direction,...
                            Data.spkypesrch(id).closerth*10^-3*Data.file(id).currentSF,...
                            -1*Data.spkypesrch(id).moreth/(Data.file(id).ADbitVolts*1E6))-2+startfindlocalmin)   /Data.file(id).currentSF)'+Data.start );
                    else
                         Mins{id} = cat(2,Mins{id},  ( (LocalMinima(Data.file(id).Samples(startfindlocalmin:end-finfindlocalmin  )*direction,...
                        Data.spkypesrch(id).closerth*10^-3*Data.file(id).currentSF,...
                        -1*Data.spkypesrch(id).moreth/(Data.file(id).ADbitVolts*1E6))-2+startfindlocalmin)   /Data.file(id).currentSF)'+Data.start );
               %                     -1*Data.spkypesrch(id).moreth/(Data.file(id).ADbitVolts*1E6))-1+startfindlocalmin)   /Data.file(id).currentSF)'+Data.start ];
               
                    end

                end
            end
            
            
            
            if ~isfield(Data,'rangespyke') && id==Data.currentctrlaxe &&exportkind==1 %real a remmetre
                
                %if  id==Data.currentctrlaxe%test
                % Data=rmfield(Data,'rangespyke');%for debug
                while ~isfield(Data,'rangespyke')
                    Data.Mins{id}=Mins{id};
                    guidata(hObject, Data);
                    bttrim_Callback(hObject,[],[]);
                    Data=guidata(hObject);
                    old_data.trimspyke=Data.trimspyke;
                    old_data.rangespyke=Data.rangespyke;
                    if ~isfield(Data,'rangespyke')
                        msgbox('You have to validate the trim to continue...','Please validate','error');
                    end
                    
                end
                %                 start(id) = Mins(end);
                
                
            end
            if isempty(Mins{id})
                start(id) =Data.start+Data.range;
            else
                start(id) = Mins{id}(end);
            end
            
            
            
            
            % end
        end
        %concat  mins give unique
        Minsort{cpt}=[Mins{searchfiles}];
        Minsort{cpt}= unique(Minsort{cpt},'sorted');
        
        %         if exportkind==2
        %             uiwait(triggersigs(Minsort{cpt},Data.file(Data.currentctrlaxe),Data.start,Data.trimspyke ,Data.rangespyke ));
        %             if exist('interguicom.mat', 'file')==2
        %                 load('interguicom.mat', 'begin','range');
        %                 Data.trimspyke=begin;
        %                 Data.rangespyke=range;
        %
        %                 delete('interguicom.mat');
        %             end
        %         end
        
        
        if exportkind==1
            for idfindform=searchfiles

                Data.file(idfindform)=Data.file(idfindform).setfiltertype('fir1');
                Data.file(idfindform)=Data.file(idfindform).setlowpass(9000,1);
                Data.file(idfindform)=Data.file(idfindform).sethighpass(300);
                
                Data.file(idfindform)=Data.file(idfindform).readdata();
            end
            switch filterindex
                case 1
                    nbf=4;
                case 3
                    nbf=2;
                otherwise
                    nbf=length(searchfiles);
            end
            spykes{cpt}=extractspyke( Minsort{cpt}-Data.start,Data.file(searchfiles), Data.trimspyke,Data.rangespyke,nbf);
            
        end
        
        
% display waveform and cluster        
%         if(Data.start==0) && exportkind==1
%             stepdisplay=ceil(length(spykes{cpt})/700);
%             figure;
%             
%             plot(spykes{cpt}(:,1:stepdisplay:end));
%             if filterindex==1
%                 figure;
%                 scatter3(spykes{cpt}(-Data.trimspyke,1:stepdisplay:end),spykes{cpt}(-Data.trimspyke+Data.rangespyke,1:stepdisplay:end),spykes{cpt}(-Data.trimspyke+Data.rangespyke*2,1:stepdisplay:end),'.');
%             end
%         end
        %         disp([ 'number of detection' num2str(length(spykes{cpt}))]);
        
    end
    
    spykes=[spykes{:}];
    Minsort= [Minsort{:}];
    
    
    prompt = {'Minimum samples numbers between 2 spike detection:','Probe number :'};
    dlg_title = 'Minimum detection';
    num_lines = 1;
    def = {'3','0'};
    if exportkind~=1
        
        prompt={prompt{1}};
        def={def{1}};
    end
    
    answer = inputdlg(prompt,dlg_title,num_lines,def);
    
    closersp=round(str2num( answer{1}));
    if closersp>0
        mask=[1 abs(diff(Minsort))>closersp/Data.file(id).currentSF ];
        msgbox([ num2str(length(find(mask==0))*100/length(Minsort)) '% detections removed']);
        if exportkind==1
            spykes=spykes(:,logical(mask));
        end
        Minsort =Minsort(logical(mask));
    end
    if exportkind==1
        probeNb=round(str2num( answer{2}));
    end
    if exportkind ~=2
        set(Data.statussearch,'string','Writing file...' );
        drawnow;
        %         pause(0.01);
    end
    Minsort=(Minsort*1E6)+Data.TSfirstpoint;
    switch exportkind
        case 1 %export units
            switch filterindex
                case 1
                    
                    write_ntt(filename,Minsort,spykes,-Data.trimspyke,probeNb,Data.file(searchfiles));
                case 2
                    write_se(filename,Minsort,spykes,-Data.trimspyke,probeNb,Data.file(searchfiles));
                case 3
                    write_nst(filename,Minsort,spykes,-Data.trimspyke,probeNb,Data.file(searchfiles));
                case 4
                    trim=-Data.trimspyke;
                    ADbitVolts = Data.file(searchfiles(1)).ADbitVolts;
                    %                 if(Data.start==0)
                    save(filename,'spykes','Minsort','probeNb','trim','ADbitVolts');
                    %                 else
                    %                    save(filename,'spykes','-append');
                    %                 end
            end
        case 2 %export spike after selection
            set(Data.statussearch,'string','');
            spikeSelecter(Minsort',Data.Path);
            
        case 3 %export TS spike
            
            switch filterindex
                case 1
                    xlswrite(filename,uint64(Minsort));
                case 2
                    dlmwrite(filename,uint64(Minsort),'delimiter',';','precision', 20);
                case 3
                    save(filename,'Minsort');
            end
            
            
            
    end
    
    
    
    
    cd(Data.Path);
    Data=old_data;
    if exportkind ~=2
        set(Data.statussearch,'string','Export done !' );
        pause(2);
        set(Data.statussearch,'string','' );
    end
end
guidata(hObject, Data);

% --- Executes on button press in bttrim.
function bttrim_Callback(hObject, eventdata, handles)
% hObject    handle to bttrim (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

Data=guidata(gcbf);
if isfield(Data,'trimspyke') &&isfield(Data,'rangespyke')
    uiwait(triggersigs(Data.Mins{Data.currentctrlaxe},Data.file(Data.currentctrlaxe),Data.start,Data.trimspyke ,Data.rangespyke ));
else
    uiwait(triggersigs(Data.Mins{Data.currentctrlaxe},Data.file(Data.currentctrlaxe),Data.start));
end

if exist('interguicom.mat', 'file')==2
    load('interguicom.mat', 'begin','range');
    Data.trimspyke=begin;
    Data.rangespyke=range;
    
    delete('interguicom.mat');
end



guidata(hObject, Data);


function spykes=extractspyke(mins,files,begin,range,nbfileneed)
% spykes=zeros(length(mins),range*length(files));
spykes=zeros(length(mins),range*nbfileneed);
for i=1:length(mins)
    filenum=1;
    for j=1:range:range*nbfileneed  %length(files)
        %         if (round(mins(i)*files(filenum).currentSF) + begin+1)<1 || round(mins(i)*files(filenum).currentSF) + begin +range> length(files(filenum).Samples)
        %             disp('hum');
        %         end
        if filenum<=length(files)
            try
                spykes(i,j:j+range-1)=files(filenum).Samples( round(mins(i)*files(filenum).currentSF) + begin+1 : round(mins(i)*files(filenum).currentSF) + begin +range)   ;
%                   spykes(i,j:j+range-1)= spykes(i,j:j+range-1)-mean(spykes(i,j:j+range-1));
%                 medsig= spykes(i,j:j+range-1)-median(spykes(i,j:j+range-1));
                
%                 spykes(i,j:j+range-1)= spykes(i,j:j+range-1)-median(spykes(i,j:j+range-1));
                %              spykes(i,j:j+range-1)=files(filenum).Samples( round(mins(i)*files(filenum).currentSF) + begin+1 : round(mins(i)*files(filenum).currentSF) + begin +range)   -files(filenum).Samples( 1+round(mins(i)*files(filenum).currentSF) );
                
                
                %             siglargefiles=files(filenum).Samples( round((mins(i)-3*1E-3)*files(filenum).currentSF) + begin+1 : round((mins(i)+3*1E-3)*files(filenum).currentSF) + begin +range);
                %                   ss=medfilt1(siglargefiles,files(filenum).currentSF*3*1E-3);
                %                         spykes(i,j:j+range-1)=spykes(i,j:j+range-1)-ss(round((3*1E-3)*files(filenum).currentSF)+1:end-round((3*1E-3)*files(filenum).currentSF))';
                
                
                %             spykes(i,j:j+range-1)=spykes(i,j:j+range-1)-  mean(spykes(i,j:j+range-1));
                %  spykes(i,j:j+range-1)=files(filenum).Samples( round(mins(i)*files(filenum).currentSF) + begin+1 : round(mins(i)*files(filenum).currentSF) + begin +range)     -files(filenum).Samples( round(mins(i)*files(filenum).currentSF) + begin+1 );
                
            catch
                disp(['Error  during extraction of the spyke num '  num2str(i) ' Time : ' num2str(round(mins(i)*files(filenum).currentSF) + begin+1)  ' to ' num2str(round(mins(i)*files(filenum).currentSF) + begin +range)   ' length of sample : '  num2str(length(files(filenum).Samples)) ' Start' num2str(files(filenum).start)]);
                4545454
            end
        else
            spykes(i,j:j+range-1)=zeros(1,range);
        end
        filenum=filenum+1;
        %     spykes(i,:)=files(:,1).Samples( round(mins(i)*files(1).currentSF) + begin+1 : round(mins(i)*files(1).currentSF) + begin +range) ;
    end
    
end
spykes=permute(spykes,[2 1]);


% --- Executes on button press in checkboxfmax.
function checkboxfmax_Callback(hObject, eventdata, handles)
% hObject    handle to checkboxfmax (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hint: get(hObject,'Value') returns toggle state of checkboxfmax
Data=guidata(gcbf);
Data.spkypesrch(Data.currentctrlaxe).max = get(hObject,'Value');

if Data.spkypesrch(Data.currentctrlaxe).activate
    Data = update_graph( Data,'true');
end
guidata(gcbf,Data);


% --- Executes on button press in checkboxfmin.
function checkboxfmin_Callback(hObject, eventdata, handles)
% hObject    handle to checkboxfmin (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hint: get(hObject,'Value') returns toggle state of checkboxfmin
Data=guidata(gcbf);
Data.spkypesrch(Data.currentctrlaxe).min = get(hObject,'Value');

if Data.spkypesrch(Data.currentctrlaxe).activate
    Data = update_graph( Data,'true');
end
guidata(gcbf,Data);


% --- Executes on button press in pushbtsavegraph.
function pushbtsavegraph_Callback(hObject, eventdata, handles)
% hObject    handle to pushbtsavegraph (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
% printfig = figure('visible','off');
printfig = figure();
cpax=[];
switch Data.xtraFileData(Data.currentctrlaxe).ftype
    case {'nvt','dat'}
        if get(Data.ctrlsig(Data.currentctrlaxe).viewpos,'Value') == 1 && Data.xtraFileData(Data.currentctrlaxe).viewgraph==1
         
            choice = questdlg('Which graph do you want save?', ...
                'Save graph', ...
                'Curve','Map','Both','Both');
        else
            if Data.xtraFileData(Data.currentctrlaxe).viewgraph==1
                choice='Curve';
            else
                choice='Map';
            end
        end
        % Handle response
        switch choice
            case 'Curve'
                cpax(1)=copyobj(Data.ax(Data.currentctrlaxe),printfig);
                set(cpax(1),'xaxislocation','bottom');
                xlabel(cpax(1),'Time (s)');
            case 'Map'
                cpax(1)=copyobj(Data.axpos(Data.currentctrlaxe),printfig);
                
            case 'Both'
                
                cpax(1)=copyobj(Data.ax(Data.currentctrlaxe),printfig);
                set(cpax(1),'xaxislocation','top');
                cpax(2)=copyobj(Data.axpos(Data.currentctrlaxe),printfig);
                xlabel(cpax(1),'Time (s)');;
        end
    case {'ntt','nse'}
        cpax(1)=copyobj(Data.ax(Data.currentctrlaxe),printfig);
        xlabel(cpax(1),'Time (s)');
        ylabel(cpax(1),'clusters');
    case {'nev','txt'}
        cpax(1)=copyobj(Data.ax(Data.currentctrlaxe),printfig);
        xlabel(cpax(1),'Time (s)');
        ylabel(cpax(1),'Events');
        
    case 'ncs'
        if Data.xtraFileData(Data.currentctrlaxe).viewfft==1 && Data.xtraFileData(Data.currentctrlaxe).viewgraph==1
            choice = questdlg('Witch graph do you want save?', ...
                'Save graph', ...
                'EEG','Analyze','Both','Both');
        else
            if Data.xtraFileData(Data.currentctrlaxe).viewfft==1
                choice='Analyze';
            else
                choice='EEG';
            end
        end
        % Handle response
        switch choice
            case 'EEG'
                cpax(1)=copyobj(Data.ax(Data.currentctrlaxe),printfig);
                set(cpax(1),'xaxislocation','bottom');
            case 'Analyze'
                cpax(1)=copyobj(Data.axftt(Data.currentctrlaxe),printfig);
            case 'Both'
                cpax(1)=copyobj(Data.ax(Data.currentctrlaxe),printfig);
                set(cpax(1),'xaxislocation','top');
                cpax(2)=copyobj(Data.axftt(Data.currentctrlaxe),printfig);
                set(cpax(2),'xaxislocation','bottom');
                
        end
        xlabel(cpax(1),'Time (s)');
        
end
if length(cpax)==1
    set(cpax(1),'position',[0.1 0.1 0.8 0.8]);
end
if length(cpax)==2
    set(cpax(1),'position',[0.1 0.5 0.8 0.35]);
    set(cpax(2),'position',[0.1 0.05 0.8 0.4]);
end
for i=1:length(cpax)
    set(cpax(i),'LineWidth',1);
    if isempty(get(cpax(i),'xticklabel'))
        set(cpax(i),'xticklabel',get(cpax(i),'xtick'));
    end
    if mod(i,2)
        set(cpax(i),'yaxislocation','left');
    else
        set(cpax(i),'yaxislocation','right');
    end
end
title(cpax(1),[Data.Path  Data.xtraFileData(Data.currentctrlaxe).name]);
% prt=printpreview(printfig);
% uiwait(prt);
[filename, pathname, filterindex] =uiputfile({'*.jpg;*.tif;*.png;*.gif';...
    '*.jpg';'*.tif';'*.png';'*.gif';...
    '*.*' },'Save Image',...
    'newfile.jpg');
if isequal(filename,0) || isequal(pathname,0)
    disp('User selected Cancel')
else
    cd(pathname);
    saveas(printfig,filename);
    cd(Data.Path);
end

% close(printfig);


% --- Executes on button press in btremovefile.
function btremovefile_Callback(hObject, eventdata, handles)
% hObject    handle to btremovefile (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
numfile = Data.currentctrlaxe;



if Data.xtraFileData(numfile).duplicate >0
    Data.xtraFileData(Data.xtraFileData(numfile).duplicate).duplicate=0;
    set(Data.ctrlsig(Data.xtraFileData(numfile).duplicate).duplicate,'Value',0);
end
if Data.xtraFileData(numfile).duplicate < 0
    if length(Data.xtraFileData) ==numfile+1
        newcurrentctrlaxe= numfile-1;
    else
        newcurrentctrlaxe= numfile+2;
    end
    AxeButtonDownFcn(hObject, eventdata, newcurrentctrlaxe);
    if length(Data.xtraFileData) ==numfile+1
        Data.currentctrlaxe=Data.currentctrlaxe-1;
    end
    
    
    Data = removefileo(Data,-1*Data.xtraFileData(numfile).duplicate);
else
    if length(Data.xtraFileData) ==numfile
        newcurrentctrlaxe= numfile-1;
    else
        newcurrentctrlaxe= numfile+1;
    end
    AxeButtonDownFcn(hObject, eventdata, newcurrentctrlaxe);
    if length(Data.xtraFileData) ==numfile
        Data.currentctrlaxe=Data.currentctrlaxe-1;
    end
end

Data = removefileo(Data,numfile);

Data = update_graph( Data,'true');
guidata(gcbf,Data);

% --- Executes on button press in btaddfile.
function btaddfile_Callback(hObject, eventdata, handles)
% hObject    handle to btaddfile (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)


% --- Executes on button press in btzoomYncs.
function btzoomYncs_Callback(hObject, eventdata, handles)
% hObject    handle to btzoomYncs (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
for numfile = 1:length(Data.file)
    if strcmp(Data.xtraFileData(numfile).ftype,'ncs')
        Data.xtraFileData(numfile).zoom=Data.xtraFileData(numfile).zoom*0.9;
        if ishandle(Data.ax(numfile))
            set(Data.ax(numfile),'Ylim',get(Data.ax(numfile),'Ylim')*0.9);
        end
    end
end
guidata(gcbf,Data);

% --- Executes on button press in btunzoomYncs.
function btunzoomYncs_Callback(hObject, eventdata, handles)
% hObject    handle to btunzoomYncs (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
for numfile = 1:length(Data.file)
    if strcmp(Data.xtraFileData(numfile).ftype,'ncs')
        Data.xtraFileData(numfile).zoom=Data.xtraFileData(numfile).zoom*1.1;
        if ishandle(Data.ax(numfile))
            set(Data.ax(numfile),'Ylim',get(Data.ax(numfile),'Ylim')*1.1);
        end
    end
end
guidata(gcbf,Data);


% --- Executes on selection change in popupfiltertype.
function popupfiltertype_Callback(hObject, eventdata, handles)
% hObject    handle to popupfiltertype (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: contents = cellstr(get(hObject,'String')) returns popupfiltertype contents as cell array
%        contents{get(hObject,'Value')} returns selected item from popupfiltertype
Data=handles;
contents = cellstr(get(hObject,'String')) ;
filtertype=contents{get(hObject,'Value')};
for numfile = 1:length(Data.file)
    if strcmp(Data.xtraFileData(numfile).ftype,'ncs')
        Data.file(numfile) = Data.file(numfile).setfiltertype(filtertype);
    end
end
Data = update_graph( Data);
guidata(gcbf,Data);

% --- Executes during object creation, after setting all properties.
function popupfiltertype_CreateFcn(hObject, eventdata, handles)
% hObject    handle to popupfiltertype (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: popupmenu controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc && isequal(get(hObject,'BackgroundColor'), get(0,'defaultUicontrolBackgroundColor'))
    set(hObject,'BackgroundColor','white');
end


% --- Executes on button press in btstd.
function btstd_Callback(hObject, eventdata, handles)
% hObject    handle to btstd (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

Data=handles;
i=Data.currentctrlaxe;
% old way do on first choosing range of EEG
tmpfile=Data.file(i).setstart(0); % change to set start point of std calculation
range=min([600,tmpfile.filerecordtotaltime]); % modify vale to change time of std calculation
if 0
    tmpfile=tmpfile.setrange(floor(range/(512*(1/Data.file(i).SF))));
else
    tmpfile=tmpfile.setrange(range);
end
tmpfile=tmpfile.readdata();
% msgbox(['Standar error of ' tmpfile.name ' = ' num2str(std(tmpfile.Samples))],'STD','help');

msgbox(['Standar error of windows ' Data.file(i).name ' = ' num2str(std(Data.file(i).Samples)) '.  STD of first ' num2str(range) 's = ' num2str(std(tmpfile.Samples))],'STD','help');

guidata(gcbf,Data);


function Csdview(Data,axecsd)
axes(axecsd);
ncsfilesid=strcmp('ncs',{Data.xtraFileData.ftype});
d=zeros(length(Data.file(find(ncsfilesid,1,'first')).Samples),length(ncsfilesid));
for i = find(ncsfilesid)
    d(:,i)=Data.file(i).Samples;
end
SF=Data.file(find(ncsfilesid,1,'first')).currentSF;
% FreqRange=[1, 60];
% [b,a]=cheby2 (2,20,FreqRange./(SF/2));
d=d./max(max(d));
% d=filtfilt(b,a,d);
% d=resample(d,1,100);
p=1/SF;
sizeS=length(Data.file(find(ncsfilesid,1,'first')).Samples);
% T=(Data.start :p: Data.start+sizeS*p - p);
% SF=SF/100;
% T=T(1:100:end);

% DATA=squeeze(mean(d,1));

[csd,newtrange,newchrange]=CSDPP2(d,'d',SF); % my version of CSD (no inversion)
h=pcolor(axecsd,Data.start+(newtrange*1E-6),newchrange,csd'); % csd is time (rows) vs chan(cols, 1 2 3 4 5) csd' becomes  1 to 16 (top to bottom)time (cols)... but pcolor starts from bottom...
set(gca, 'ytick',[1:1:max(newchrange)+1]);
set(gca, 'ytickLabel',{Data.file(ncsfilesid).name});
set(axecsd,'ylim',[1,max(newchrange)+1]);
cx =caxis;
cxmax = max(abs(cx));
caxis([-cxmax cxmax]);
shading interp

% 
% for ind =1:size(DATA,2)
%     newD(:,ind)=interp1(T,DATA(:,ind),newtrange); % putactual EEGs to a new interpolated time
% end;
% for ind =1:size(DATA,2)
%     newD(:,ind)=newD(:,ind)./max(max(DATA)); % normalize
% end;
% 
% 
% hold on
% multiplot2plot(-1*(newD), newtrange*1E-6, -max(max(newD))) % note the -1 here... that's because multiplo to plot plots from bottom to top, then I inverse the Y axis...
set(gca,'ydir','rev');
set(gca,'FontSize',5)


% --- Executes on button press in tg_notch.
function tg_notch_Callback(hObject, eventdata, handles)
% hObject    handle to tg_notch (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hint: get(hObject,'Value') returns toggle state of tg_notch
handles = update_graph( handles);
guidata(gcbf,handles);



function editbegintime_Callback(hObject, eventdata, handles)
% hObject    handle to editbegintime (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of editbegintime as text
%        str2double(get(hObject,'String')) returns contents of editbegintime as a double
handles.start=str2double(get(hObject,'String'));
handles = update_graph( handles);
guidata(gcbf,handles);

% --- Executes during object creation, after setting all properties.
function editbegintime_CreateFcn(hObject, eventdata, handles)
% hObject    handle to editbegintime (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc && isequal(get(hObject,'BackgroundColor'), get(0,'defaultUicontrolBackgroundColor'))
    set(hObject,'BackgroundColor','white');
end



function editrange_Callback(hObject, eventdata, handles)
% hObject    handle to editrange (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hints: get(hObject,'String') returns contents of editrange as text
%        str2double(get(hObject,'String')) returns contents of editrange as a double
handles.range=str2double(get(hObject,'String'));
handles = update_graph( handles);
guidata(gcbf,handles);

% --- Executes during object creation, after setting all properties.
function editrange_CreateFcn(hObject, eventdata, handles)
% hObject    handle to editrange (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    empty - handles not created until after all CreateFcns called

% Hint: edit controls usually have a white background on Windows.
%       See ISPC and COMPUTER.
if ispc && isequal(get(hObject,'BackgroundColor'), get(0,'defaultUicontrolBackgroundColor'))
    set(hObject,'BackgroundColor','white');
end


% --- Executes on button press in pushbuttonsaveall.
function pushbuttonsaveall_Callback(hObject, eventdata, handles)
% hObject    handle to pushbuttonsaveall (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)
Data=guidata(gcbf);
% printfig = figure('visible','off');
printfig = figure();
cpax=[];
 cpax=copyobj(Data.ax,printfig);
 if isfield(Data,'axftt')
     handmask=ishandle(Data.axftt);
     if sum(handmask)>0
        cpax2=copyobj(Data.axftt(handmask),printfig);
     end
 end


[filename, pathname, filterindex] =uiputfile({'*.jpg;*.tif;*.png;*.gif';...
    '*.jpg';'*.tif';'*.png';'*.gif';...
    '*.*' },'Save Image',...
    'newfile.jpg');
if isequal(filename,0) || isequal(pathname,0)
    disp('User selected Cancel')
else
    cd(pathname);
    saveas(printfig,filename);
    cd(Data.Path);
end


% --- Executes on button press in checkboxinvertEEG.
function checkboxinvertEEG_Callback(hObject, eventdata, handles)
% hObject    handle to checkboxinvertEEG (see GCBO)
% eventdata  reserved - to be defined in a future version of MATLAB
% handles    structure with handles and user data (see GUIDATA)

% Hint: get(hObject,'Value') returns toggle state of checkboxinvertEEG
Data=guidata(gcbf);
val=get(hObject,'Value');
for i=1:length( Data.file)
    Data.file(i).readmodeinvert=val;
end
Data = update_graph( Data);
guidata(gcbf,Data);
    
