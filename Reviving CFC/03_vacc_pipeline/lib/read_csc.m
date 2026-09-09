function [RecSz,SF,TS,Samples]=read_Csc (filename,Downsampling)
% reads Neuralynx Csc files
% [RecSz,SF,TS,Samples]=read_Csc (filename,Downsampling);
% Downsampling (optional) is if you want to extract only a fraction of the
% file
%
%  this one has all we need
if nargin==1;
Downsampling=1;
end;
format long g

%%%%% constants
header_sz=16384;
%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%% Formats %%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%
%  ts='uint64';%8bytes    %
%  chnum='uint32';%4      %
%  SF='uint32';%4         %
%  numsamples='uint32';%4 %
%  sample='int16';%512*2  %
% total=1044              %
%%%%%%%%%%%%%%%%%%%%%%%%%%%



fid=fopen(filename,'r');
if fid==-1
   fprintf('\n %s \n', 'issue with fopen')
fid=fopen('TT4a.ncs','r');

end;

headernum=fscanf(fid,'%c',header_sz);
returns=find(headernum==13);
header=cell(length(returns),1);

for i=2:length(returns)-1
header{i}=char(headernum(returns(i):returns(i+1)-1));
end
header{1}=char(headernum(1:returns(1)));
header{end}=(headernum(returns(end):end));

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

whereSF=strfind(header,'SamplingFrequency' );
for k=1:length(whereSF)
if ~isempty(whereSF{k}), myline=k; end;
end


SF=char(header(myline));
blancs=strfind(SF, 'y');
SF=str2double(SF(blancs(1)+1:end));

whereAD=strfind(header,'ADMaxValue' );
for k=1:length(whereAD)
if ~isempty(whereAD{k}), myline=k; end;
end



ADMaxVal=char(header(myline));
blancs=strfind(ADMaxVal,'e');
ADMaxVal=str2double(ADMaxVal(blancs+1:end));

whereAD2=strfind(header,'ADBitVolts' );
for k=1:length(whereAD2)
if ~isempty(whereAD2{k}), myline=k; end;
end



ADbitVolts=char(header(myline));
blancs=strfind(ADbitVolts,'s');
ADbitVolts=str2double(ADbitVolts(blancs+1:end));
found=0;
whereSubSpl=strfind(header,'-SubSamplingInterleave' );
for k=1:length(whereSubSpl)
if ~isempty(whereSubSpl{k}), myline=k; found=1;end;
end

if found ==1

Interleave=char(header(myline));
blancs=strfind(Interleave,'ve');
Interleave=str2double(Interleave(blancs+2:end));

    if SF>=30000

    SF=SF/Interleave;
    end
end;
%%%%%%%%%%%% read the file
TS=fread(fid,'uint64',1036);
fseek(fid,header_sz+20,'bof');
Samples=fread(fid,512*length(TS),'512*int16=>int16',20);
fclose (fid);
% Gain=char(header(32));
% blancs=find(Gain==32);
% Gain=str2double(Gain(blancs+1:end));
RecSz=512*length(TS);

 
 if Downsampling~=1
% TS=EEGTs(1:Downsampling:end);
SF=SF/(Downsampling);
Samples=Samples(1:Downsampling:end);
EEGTs=[0:(1/SF)*1E6: length(Samples)*(1/SF)*1E6];
 EEGTs=EEGTs+TS(1);
 
 EEGTs(end)=[];
 
 else
    
     EEGTs=[0:(1/SF)*1E6: length(Samples)*(1/SF)*1E6];
 EEGTs=EEGTs+TS(1);
 
 EEGTs(end)=[];
 end;
  TS=EEGTs;
clear EEGTs;


Samples=double(Samples).*(ADbitVolts*1E6); % in microvolts



