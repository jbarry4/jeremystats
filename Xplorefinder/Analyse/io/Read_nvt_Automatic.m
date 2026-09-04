function [RecSz,PosTS,newX,newY] = Read_nvt_Automatic (filename,fix)
%use .mex or .m to read Neuralynx video file then clean video by choosing
%the bigest target each time ( and not the mean like usual)
%[RecSz,PosTS,newX,newY] = Read_nvt_Automatic (filename,fix)
% fix == 1 will choose better point as X,Y
% fix == 0 will make mean of all detection as X,Y (default)
%
if nargin==1
    fix=0;
end
A = exist('Nlx2MatVT');
if A==3 %mean it's a mex file         %strfind(lower(computer),'win')
    try
        if fix
            [PosTS,targets] = Nlx2MatVT(filename, [1 0 0 0 1 0], 0, 1, [] );
        else
            [PosTS,newX,newY] = Nlx2MatVT(filename, [1 1 1 0 0 0], 0, 1, [] );
            newX=newX';
            newY=newY';
            RecSz=length(newX);
            return;
        end
        RecSz=length(PosTS);
        PosTS=PosTS';
    catch
        [RecSz,PosTS,~,~,targets]= read_NVT(filename );
    end
    
else
    if fix==1
        [RecSz,PosTS,~,~,targets]=read_NVT (filename);
    else
        [RecSz,PosTS,newX,newY]=read_NVT (filename);
        return;
    end
end
newX=zeros(RecSz,1);
newY=newX;

for ind=1:size(targets,2)
    %     tmptargets=tmptargets(find(tmptargets~=0,'last'));
    tmptargets=dec2bin(targets(1,ind),32);
    newX(ind)=bin2dec(tmptargets(1,21:32));
    newY(ind)=bin2dec(tmptargets(1,5:16));
    
end
% [newX,newY]=FixPosData (PosTS,newX,newY);