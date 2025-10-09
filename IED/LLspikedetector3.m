function [ets,ech]=LLspikedetector3(d,sfx,llw,prc,badch)
% Same as original detector; supports a fixed global threshold if prc is {'<number>'}

if ~exist('llw','var')||isempty(llw); llw=.04; end
if ~exist('prc','var')||isempty(prc); prc=99.5; end
if ndims(d)>2, error('d must be vector or 2-D matrix'); end
if size(d,1)>size(d,2), d=d'; end
if ~exist('badch','var')||isempty(badch); badch=false(1,size(d,1)); end

% 1) Line-length transform
numsamples=round(llw*sfx);
if isvector(d)
  L=nan(1,length(d),'single');
  for i=1:length(d)-numsamples
    L(i)=sum(abs(diff(d(i:i+numsamples-1))));
  end
else
  L=nan(size(d),'single');
  for i=1:size(d,2)-numsamples
    L(:,i)=sum(abs(diff(d(:,i:i+numsamples-1),1,2)),2);
  end
end

% 2) Threshold and event build
Lvec=reshape(L,1,numel(L)); Lvec(isnan(Lvec))=[];
if ~iscell(prc); threshold=prctile(Lvec,prc);
else; threshold=str2double(prc{1}); end
Li=L>threshold;

a=nansum(Li,1)>0;
a=diff(a);
eON=find(a==1)+1; eOFF=find(a==-1);
if ~isempty(eOFF) && ~isempty(eON)
  if eOFF(1)<eON(1); eON=[1 eON]; end
  if numel(eOFF)<numel(eON); eOFF=[eOFF length(a)]; end
end
if numel(eOFF)~=numel(eON); ets=[]; ech=[]; return; end
ets=[eON(:) eOFF(:)];

ech=false(size(ets,1),size(Li,1));
for i=1:size(ets,1)
  ech(i,:)=logical(nansum(Li(:,ets(i,1):ets(i,2)),2));
end

% 3) Center, drop bad-only, merge <300 ms, min dur 25 ms
ets=round(ets+(sfx*llw)/2);
ech(:,badch)=0; idx=sum(ech,2)<1; ets(idx,:)=[]; ech(idx,:)=[];
s=size(ets,1); kill=false(s,1);
for i=1:s-1
  if (ets(i+1,1)-ets(i,2))<round(0.3*sfx)
    ets(i+1,1)=ets(i,1);
    ech(i+1,:)=logical(ech(i+1,:) | ech(i,:));
    kill(i)=true;
  end
end
ets(kill,:)=[]; ech(kill,:)=[];
minL=.025;
tooShort=diff(ets,1,2)<round(sfx*minL);
ets(tooShort,:)=[]; ech(tooShort,:)=[];
end
