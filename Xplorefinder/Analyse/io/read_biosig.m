function [FramNum, TS, X, Y, Shocks, Sectors,  MotorState, CurrentLevel, Flags, Finfo, header]=read_biosig (FileName, draw);
 %This version is modified for the biosig .dat files generated during place
 %accuracy experiments.
% this read files for the rotating arena with extension ".dat"
% ind id is for whether you want a figure or not.


fid = fopen(FileName,'r');
 
fseek(fid,1,'bof');
headernum=fscanf(fid,'%c');
returns=find(headernum==13); % find the returns in the text (13 designates a return))

% startup the string search for the text %sample that always indicates the
% number of columns in the header

startup=strfind(headernum,'%Sample.0');

ri=find(returns>startup,1);
%the return index (ri) finds the number of carriage returns to sample,
%indicating the line number

Sample=headernum(returns(ri-1):returns(ri)); 
%this takes the sample line by taking everything from the previous carriage
%return to the position before the return index

blancs=find(Sample==32); % find the spaces in the text (13 designates a space))
%the number of blank spaces indicates the number of columns or "numebr of
%elements"

numberElements=length(blancs)-2;
% number of elements = number of columns and -2 is to get rid of the two
% spaces between sample and the first column
fseek(fid,1,'bof');

%this will start to read the data by doing the same thing as earlier but
%finding the string "end header" instead of 'sample'.

startdata=strfind(headernum,'%%END_HEADER');
%instead of return index we make a data index

di=find(returns>startdata,1);
% everthing after the return following 'end header' is sweet delicious
% data, the 1 in this case means the first position after the return

if numberElements==9
      data = textscan(fid,'%f%f%f%f%d%d%d%s%d', 'delimiter', '\t',  'headerLines', di);  
        FramNum=data{:,1};
        TS=data{:,2};
        X=data{:,3};
        Y=data{:,4};
        Sectors=data{:,5};
        Shocks=data{:,6};
        CurrentLevel=data{:,7};
        
        Flags=data{:,8};
        Finfo=data{:,9};
        MotorState=[];
elseif numberElements==10


%%%% read the data 

data = textscan(fid,'%f%f%f%f%d%d%d%d%s%d', 'delimiter', '\t',  'headerLines', di);
%%( FrameCount 1msTimeStamp RoomX RoomY Angle Sectors State CurrentLevel  MotorState Flags FrameInfo )
FramNum=data{:,1};
TS=data{:,2};
X=data{:,3};
Y=data{:,4};
Sectors=data{:,5};
Shocks=data{:,6};
CurrentLevel=data{:,7};
MotorState=data{:,8}; 
Flags=data{:,9};
Finfo=data{:,10};

end;
DatfileName=FileName;
[FramNum, PosTS, X, Y, Shocks, Sectors,  State, CurrentLevel, Flags, Finfo, header]=read_biosig (DatfileName, 0);
 
FrameCount 1msTimeStamp RoomX RoomY Sectors State CurrentLevel Flags FrameInfo )
 
 % get back to the header

headernum(returns(22):end)=[];
returns(22:end)=[];
 
header=cell(21,1);
 
for i=2:length(returns)-1
header{i,1}=char(headernum(returns(i):returns(i+1)-1));
end
header{1}=char(headernum(1:returns(1)));
header{end}=(headernum(returns(end):end));
 
 
fclose(fid);
midtime = (round(length(TS)/2));
 
 %%%%% get the reszolution in pix/cm
 line=0;
k=strfind(header,'%TrackerResolution');
for ind=1:length(k)
if ~isempty(cell2mat(k(ind)))
    line=ind;
end;
end

if line~=0
    TrackerRes=char(header(line));
    blancs=find(TrackerRes==32);
end;
 
PixPerCm=str2double(TrackerRes(blancs(2):blancs(3)));
Diameter=82*PixPerCm;

Radius=Diameter/2;
 
% get angle properties


%RoomTrackReinforcedSector.0
 line=0;
k=strfind(header,'%RoomTrackReinforcedSector.0');
for ind=1:length(k)
if ~isempty(cell2mat(k(ind)))
    line=ind;
end;
end

if line~=0
    shockZone=char(header(line));
    blancs=find(shockZone==32);
end;

ctrang=str2double(shockZone(blancs(2):blancs(3)));
wid=str2double(shockZone(blancs(3):blancs(4)));
inrad=str2double(shockZone(blancs(4):blancs(5)));
outrad=str2double(shockZone(blancs(5):end));


[b,a]=cheby2(8,20, 2/30);
 
[X,Y]=FixPosData0 (TS,X,Y);
 
 [X]=filtfilt(b,a,X);
[Y]=filtfilt(b,a,Y);
 
X1=X(1:midtime);
Y1=Y(1:midtime);
X2=X(midtime:end);
Y2=Y(midtime:end);
Sectors=diff(Sectors);
Sectors(Sectors<=0)=0;
 
Sectors1=Sectors(1:midtime);
Sectors2=Sectors(midtime:end);
Shocks(Shocks~=2)=0;
Shocks = [diff(Shocks);0];
Shocks(Shocks<=0)=0;
 
Shocks1=Shocks(1:midtime);
Shocks2=Shocks(midtime:end);
 
 
t = linspace(0,2*pi,1000);

 
 
y=Radius*sin(t)+127.5; %carefull of center coords, normaly take them from the header
x=Radius*cos(t)+127.5;
 
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%% 
tshk= linspace(ang2rad(ctrang)-ang2rad(wid/2),ang2rad(ctrang)+ang2rad(wid/2),1000)+(pi);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%% 
% r=75;
 
yshk=Radius*sin(tshk)+127.5; %carefull of center coords, normaly take them from the header
xshk=Radius*cos(tshk)+127.5;
 
 
 
 if draw~=0
     figure
     
subplot(3,2,1)
plot(X1,Y1,'Color',[0.5 0.5 0.5])
 
 
 
hold on
plot(x,y,'k', 'linewidth',2)
plot(xshk,yshk,'b', 'linewidth',3)
 
 
axis ij
hold on
plot(X1(Shocks1 ==2), Y1(Shocks1==2),'o','MarkerEdgeColor','k',...
                'MarkerFaceColor','r',...
                'MarkerSize',8)
 plot([127.5 xshk(1)], [127.5 yshk(1)], 'b','linewidth',3)    
  plot([127.5 xshk(end)], [127.5 yshk(end)], 'b','linewidth',3) 
  
  
  
axis square
title('First half')
% axis ([40 220 40 220])
text((127+Radius), 10,num2str(sum(double(Sectors1)),'%d')) 
text(127-Radius, 10,num2str(length(find(Shocks1==2)),'%d')) 
plot(127.5, 127.5, '+k')
 
subplot(3,2,2)
 
plot(X2,Y2,'Color',[0.5 0.5 0.5])
 
 
axis ij
hold on
plot(x,y,'k', 'linewidth',2)
plot(xshk,yshk,'b', 'linewidth',3)
 
plot(X2(Shocks2 ==2), Y2(Shocks2==2),'o','MarkerEdgeColor','k',...
                'MarkerFaceColor','r',...
                'MarkerSize',8)
  plot([127.5 xshk(1)], [127.5 yshk(1)], 'b','linewidth',3)    
  plot([127.5 xshk(end)], [127.5 yshk(end)], 'b','linewidth',3) 
             
axis square
title('Second half')
% axis ([40 220 40 220])
text((127+Radius), 10,num2str(sum(double(Sectors2)),'%d')) 
text((127-Radius), 10,num2str(length(find(Shocks2==2)),'%d')) 
plot(127.5, 127.5, '+k')
 end;