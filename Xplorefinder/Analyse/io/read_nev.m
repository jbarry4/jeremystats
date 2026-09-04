function [RecSz,TS,ID,TTL,EventString,header]=read_nev (filename)
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
%nstx 2
%npkt_id 2
%ntpkt_data_size 2
%
%  TS=  uint64                            8 bytes
% ID uint16                     2 bytes
% TTL: uint16:                    2 bytes
% ncrc 1
%dummy 2
%dummy 2
%dnextra 4*8 = 32
%String  128*uchar?   128*1 byte

%
% total size = 184
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


%%%%%%%%%%%% read the file
 fseek(fid,header_sz+6,'bof'); %skip the first 3 int16
TS=fread(fid,'uint64',176); % read time stpams = each dataset is 184 bytes, remove 8 bytes for TS = 176 

fseek(fid,header_sz+6+8,'bof');
ID=fread(fid,'int16',182);

fseek(fid,header_sz+6+8+2,'bof');
TTL=fread(fid,'int16',182);

fseek(fid,header_sz+6+8+42,'bof');
str=fread(fid,[128,length(TS)],'128*uint8=>128*char',184-128);
EventString=cell(length(TS),1);
for i=1:length(TS)
EventString{i}=char(str(:,i));
end;

fclose (fid);

RecSz=length(TS);
