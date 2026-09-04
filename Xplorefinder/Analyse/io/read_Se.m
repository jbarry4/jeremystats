function [RecSz,TS,probe,clust,params,Data,header]=read_Se (filename)
% reads Neuralynx video files
% [RecSz,TS,probe,clust,params,Samples]=read_NTT (filename);
%
%

format long g

%%%%% constants
 header_sz=16384;
% header_sz=16554;
%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%% Formats %%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%
%  TS=  uint64                            8 bytes
% probe: uint32                     4 bytes
% clust: uint32:                    4 bytes
% params: uint32 *8            8*4 =32 bytes
% Samples:  int16*[32]                 32*2 = 64 bytes
%
% total size = 112
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

ADbitVolts=char(header(14));
blancs=find(ADbitVolts==32);



ADBV=str2double(ADbitVolts(blancs:end));


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


%%%%%%%%%%%% read the file
TS=fread(fid,'uint64',112-8);
fseek(fid,header_sz+8,'bof');
probe=fread(fid,length(TS),'uint32',112-4);
fseek(fid,header_sz+12,'bof');
clust=fread(fid,length(TS),'uint32',112-4);
fseek(fid,header_sz+16,'bof');
params=fread(fid,[8,length(TS)],'8*int32',112-32);
fseek(fid,header_sz+48,'bof');
Data=fread(fid,[32,length(TS)],'32*int16',112-64);

Data=Data*ADBV*1E6;

fclose (fid);

RecSz=length(TS);
