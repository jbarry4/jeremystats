function [ets,ech]=LLspikedetector_fixedthr(d,sfx,llw,thr,badch)
% LLspikedetector_fixedthr — same detector, but uses a FIXED global threshold.
% Inputs:
%   d    : [channels x time] or vector
%   sfx  : Hz
%   llw  : sec (e.g., 0.04)
%   thr  : numeric LL threshold (global)
%   badch: optional logical row marking bad channels

if ~exist('llw','var')||isempty(llw); llw=.04; end
if ~exist('thr','var')||isempty(thr); error('Pass numeric thr'); end
if length(size(d))>2; error('Accepts only vector or 2-D matrix for data'); end
if size(d,1)>size(d,2); d=d'; end                   % channels x time
if ~exist('badch','var')||isempty(badch); badch=false(1,size(d,1)); end

% 1) Line-length transform
numsamples=round(llw*sfx);
if any(size(d)==1)   % vector
  L=nan(1,length(d));
  for i=1:length(d)-numsamples
    L(i)=sum(abs(diff(d(i:i+numsamples-1))));
  end
else                 % matrix
  L=nan(size(d));
  for i=1:size(d,2)-numsamples
    L(:,i)=sum(abs(diff(d(:,i:i+numsamples-1),1,2)),2);
  end
end

% 2) Thresholding & event finding (no percentile; use fixed thr)
Li = L > thr;

a = nansum(Li,1)>0;            % any channel over threshold at each time
a = diff(a);                    % edges: +1 on, -1 off
eON  = find(a==1)+1;
eOFF = find(a==-1);
if ~isempty(eOFF) && ~isempty(eON)
  if eOFF(1)<eON(1), eON=[1 eON]; end
  if length(eOFF)<length(eON), eOFF=[eOFF length(a)]; end
end
if isempty(eON) || isempty(eOFF)
  ets = zeros(0,2); ech = false(0,size(Li,1)); return
end
if length(eOFF)~=length(eON)
  error('start and end of events is not matching up, check your code');
end
ets = [eON(:) eOFF(:)];

% Channel participation
ech=false(size(ets,1),size(Li,1));
for i=1:size(ets,1)
  ech(i,:)=logical(nansum(Li(:,ets(i,1):ets(i,2)),2));
end

% 3) Post-processing (same as original)
ets = round(ets + (sfx*llw)/2);     % center by half LL window
ech(:,badch)=0;
idx = sum(ech,2)<1;    ech(idx,:)=[];    ets(idx,:)=[];

% merge events <300 ms apart
s=size(ets,1); indx=false(s,1);
for i=1:s-1
  if (ets(i+1,1)-ets(i,2)) < sfx*.3
    ets(i+1,1)=ets(i,1);
    ech(i+1,:)=logical(sum(ech(i:i+1,:),1));
    indx(i)=true;
  end
end
ets(indx,:)=[];  ech(indx,:)=[];

% drop too-short (<25 ms)
minL=.025;
tooshort = diff(ets,1,2) < (sfx*minL);
ets(tooshort,:)=[];  ech(tooshort,:)=[];

end
