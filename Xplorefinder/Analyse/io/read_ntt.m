function [RecSz,TS,probe,clust,params,Data,header]=read_ntt (filename)
% reads Neuralynx video files
% [RecSz,TS,probe,clust,params,Samples]=read_NTT (filename);
%
%

format long g

%%%%% constants
header_sz=16384;
%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%% Formats %%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%
%  TS=  uint64                            8 bytes
% probe: uint32                     4 bytes
% clust: uint32:                    4 bytes
% params: uint32 *8            8*4 32 bytes
% Samples:  int32*[32,4]                 32*4*4 256 bytes
%
% total size = 304
%%%%%%%%%%%%%%%%%%%%%%%%%%%



fid=fopen(filename,'r');
headernum=fscanf(fid,'%c',header_sz);
returns=find(headernum==13);
header=cell(length(returns),1);

for i=2:length(returns)-1
header{i}=char(headernum(returns(i):returns(i+1)-1));
end
header{1}=char(headernum(1:returns(1)));
header{end}=(headernum(returns(end):end));

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
Delay=0;
whereDelayA=strfind(header,'DspDelayCompensation' );
for k=1:length(whereDelayA)
    if ~isempty(whereDelayA{k})
        myline=k;
        DelayA=char(header(myline));
        if(strfind(DelayA, 'Disabled'))
            whereDELAY=strfind(header,'DspFilterDelay' );
            for l=1:length(whereDELAY)
                if ~isempty(whereDELAY{l})
                    mylined=l;
                    Delay=char(header(mylined));
                    blancs=strfind(Delay, ' ');
                    Delay=str2double(Delay(blancs(1):end));
                    k=length(whereDelayA);
                end
            end           
        end        
    end
end






line=0;
k=strfind(header,'-ADBitVolts');
for ind=1:length(k)
if ~isempty(cell2mat(k(ind))), line=ind; end;
end
if line~=0
ADbitVolts=char(header(line));
blancs=find(ADbitVolts==' ');
if isempty(blancs)
blancs=find(ADbitVolts==9);    
end
% get rid of eventual double spaces 
if min(diff(blancs))==1, blancs(diff(blancs)~=1)=[];end

ADbitVolts1=str2double(ADbitVolts(blancs(1):blancs(2)));
ADbitVolts2=str2double(ADbitVolts(blancs(2):blancs(3)));
ADbitVolts3=str2double(ADbitVolts(blancs(3):blancs(4)));
ADbitVolts4=str2double(ADbitVolts(blancs(4):end));
else
    ADbitVolts1=1;
ADbitVolts2=1;
ADbitVolts3=1;
ADbitVolts4=1;
    
end;

%%%%%%%%%%%% read the file

TS=fread(fid,'uint64',296);
fseek(fid,header_sz+8,'bof');
probe=fread(fid,length(TS),'uint32',300);
fseek(fid,header_sz+12,'bof');
clust=fread(fid,length(TS),'uint32',300);
fseek(fid,header_sz+16,'bof');
params=fread(fid,[8,length(TS)],'8*int32',304-32);
fseek(fid,header_sz+48,'bof');

Data=fread(fid,[128,length(TS)],'128*int16',304-256);
T1=Data(1:4:end,:).*ADbitVolts1;
T2=Data(2:4:end,:).*ADbitVolts2;
T3=Data(3:4:end,:).*ADbitVolts3;
T4=Data(4:4:end,:).*ADbitVolts4;
Data=cat(3,T1,T2,T3,T4);
Data=permute(Data,[2,3,1]);

fclose (fid);
if Delay ~=0
    TS=TS-Delay;
end


RecSz=length(TS);
