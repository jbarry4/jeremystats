function [ets,ech]=LLspikedetector2(d,sfx,llw,prc,badch)
% Per-channel–aware LL spike detector.
% prc can be:
%  - scalar numeric: percentile used per channel
%  - vector numeric (nChanx1): fixed per-channel LL thresholds
%  - cellstr {'<scalar>'}: single fixed global LL threshold

if ~exist('llw','var')||isempty(llw); llw=.04; end
if ~exist('prc','var')||isempty(prc); prc=99.5; end
if ndims(d)>2, error('d must be vector or 2-D matrix'); end
if size(d,1)>size(d,2), d=d'; end                 % rows=channels
if ~exist('badch','var')||isempty(badch), badch=false(1,size(d,1)); end

% 1) Line-length transform (channels x time), tail NaN-padded
numsamples = round(llw*sfx);
if isvector(d)
  L = nan(1,length(d),'single');
  for i=1:length(d)-numsamples
    L(i)=sum(abs(diff(d(i:i+numsamples-1))));
  end
else
  L = nan(size(d),'single');
  for i=1:size(d,2)-numsamples
    L(:,i)=sum(abs(diff(d(:,i:i+numsamples-1),1,2)),2);
  end
end

% 2) Threshold mask Li (channels x time)
nChan = size(L,1);
if isnumeric(prc) && isscalar(prc)
  % per-channel percentile
  thr = prctile(L, prc, 2);              % nChan x 1
  Li  = L > thr;
elseif isnumeric(prc) && isvector(prc)
  if numel(prc)~=nChan, error('length(prc) must match channels'); end
  thr = prc(:);
  Li  = L > thr;
elseif iscell(prc) && numel(prc)==1
  thr = str2double(prc{1});
  Li  = L > thr;
else
  error('Unsupported prc format');
end

% Global event mask (any channel active)
a = nansum(Li,1)>0;
a = diff(a);
eON  = find(a==1)+1;
eOFF = find(a==-1);
if isempty(eON) && ~isempty(eOFF), eON = 1; end
if ~isempty(eOFF) && ~isempty(eON)
  if eOFF(1)<eON(1), eON=[1 eON]; end
  if numel(eOFF)<numel(eON), eOFF=[eOFF length(a)]; end
end
if numel(eOFF)~=numel(eON), ets=[]; ech=[]; return; end
ets = [eON(:) eOFF(:)];

% Channel membership per event
ech = false(size(ets,1), nChan);
for i=1:size(ets,1)
  ech(i,:) = logical(nansum(Li(:, ets(i,1):ets(i,2)), 2));
end

% 3) Post-processing: center, badch, merge, min duration
ets = round(ets + (sfx*llw)/2);
ech(:,badch)=0;
idx = sum(ech,2)<1;  ets(idx,:)=[]; ech(idx,:)=[];

% Merge events <300 ms apart
s = size(ets,1); kill=false(s,1);
for i=1:s-1
  if (ets(i+1,1)-ets(i,2)) < round(0.3*sfx)
    ets(i+1,1) = ets(i,1);
    ech(i+1,:) = logical(ech(i+1,:) | ech(i,:));
    kill(i)=true;
  end
end
ets(kill,:)=[]; ech(kill,:)=[];

% Minimum duration 25 ms
minL = .025;
tooShort = (diff(ets,1,2) < round(sfx*minL));
ets(tooShort,:)=[]; ech(tooShort,:)=[];
end
