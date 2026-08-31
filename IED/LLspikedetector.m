function [ets,ech]=LLspikedetector(d,sfx,llw,prc,badch)                     % ENTRY POINT: RETURNS ETS (EVENT TIMES) AND ECH (CHANNEL PARTICIPATION)
%jon.kleen@ucsf.edu 2016-2023                                                % AUTHOR / VERSION INFO
% Transforms data into linelength then detects events (spikes) surpassing    % OVERVIEW OF METHOD: LINE-LENGTH TRANSFORM + THRESHOLD
% the designated percentile threshold. Note that this function assumes any   % NOTE: ASSUMES SIMULTANEOUS DETECTIONS ARE SAME EVENT
% detections in any channel occurring simultaneously are involved in the     % REITERATES SIMULTANEOUS-CHANNEL ASSUMPTION
% same spike event.                                                          % CONTINUATION OF DESCRIPTION
% Based on Estellar et al 2001, DOI 10.1109/IEMBS.2001.1020545               % CITATION FOR METHOD
%INPUTS                                                                      % INPUT SPEC START
  % d: vector or matrix of ICEEG data and                                    % d: DATA (VECTOR OR CHANNELS×TIME MATRIX)
  % sfx: sampling frequency                                                   % sfx: SAMPLING RATE (HZ)
  % llw: linelength window (in seconds) over which to calculate transform     % llw: WINDOW LENGTH (SEC) FOR LINE-LENGTH
  % prc: percentile to use as a threshold for detections                      % prc: PERCENTILE (OR STRING OF NUMERIC THRESHOLD)
  % badch: logical index of bad channels (1=bad, 0=ok)                        % badch: LOGICAL VECTOR MARKING BAD CHANNELS
% OUTPUTS                                                                     % OUTPUT SPEC START
  % ets: matrix of events (rows) and their on/off times (2 columns) in samples% ets: [ON OFF] SAMPLE INDICES PER EVENT
  % ech: logical index of which channels are involved in each detection,      % ech: EVENT×CHANNEL LOGICAL PARTICIPATION
%        thus having the same number of rows (spikes) as ets                 % ech ROWS MATCH ets ROWS
  
%Example: [ets,ech]=LLspikedetector(d,512,.04,99.99)                         % USAGE EXAMPLE

if ~exist('llw','var')||isempty(llw); llw=.04; end                           % DEFAULT LL WINDOW TO 40 MS IF MISSING
if ~exist('prc','var')||isempty(prc); prc=99.5; end                           % DEFAULT PERCENTILE TO 99.5 IF MISSING
if length(size(d))>2; error('Accepts only vector or 2-D matrix for data'); end% VALIDATE d IS VECTOR OR 2-D MATRIX
if size(d,1)>size(d,2); d=d'; end                                            % ENSURE ORIENTATION: ROWS=CHANNELS, COLS=TIME
if ~exist('badch','var')||isempty(badch); badch=false(1,size(d,1)); end       % DEFAULT: NO BAD CHANNELS

%%  1. LINE-LENGTH TRANSFORM                                                      % SECTION HEADER: COMPUTE LINE-LENGTH
numsamples=round(llw*sfx); % number of samples in the transform window       % CONVERT LL WINDOW SECONDS → SAMPLES
if any(size(d)==1)   %if d is a vector                                       % BRANCH: 1-D VECTOR INPUT
  L=nan(1,length(d)); % will fill this with transformed data in loop below   % PREALLOCATE LL VECTOR WITH NaNs
  for i=1:length(d)-numsamples                                               % SLIDE WINDOW OVER TIME INDICES
    L(i)=sum(abs(diff(d(i:i+numsamples-1))));                                % LINE-LENGTH: SUM OF ABSOLUTE FIRST DIFFS IN WINDOW
  end                                                                        % END LOOP FOR VECTOR CASE
else                 %if d is a matrix                                       % BRANCH: 2-D MATRIX INPUT
  L=nan(size(d));                                                            % PREALLOCATE LL MATRIX (CHANNELS×TIME)
  for i=1:size(d,2)-numsamples                                               % LOOP OVER TIME (COLUMN) INDICES
  L(:,i)=sum(abs(diff(d(:,i:i+numsamples-1),1,2)),2);                        % CHANNEL-WISE LINE-LENGTH OVER WINDOW
  end                                                                        % END LOOP FOR MATRIX CASE
end                                                                          % END IF VECTOR/MATRIX BRANCH

%%  2. DETECT EVENTS                                                            % SECTION HEADER: THRESHOLDING AND EVENT FINDING
Lvec=reshape(L,1,numel(L)); Lvec(isnan(Lvec))=[];                            % FLATTEN LL TO 1×N AND DROP NaNs FOR THRESHOLD ESTIMATION
if ~iscell(prc); threshold=prctile(Lvec,prc);                                % IF prc IS NUMERIC: USE PERCENTILE OF LL DISTRIBUTION
else; threshold=str2double(prc{1});                                          % IF prc IS CELL STRING: TREAT AS RAW NUMERIC THRESHOLD
end                                                                          % END THRESHOLD SELECTION
Li=L>threshold;                                                              % LOGICAL MASK: ABOVE-THRESHOLD SAMPLES (CHANNELS×TIME)

% >>> CROSS-CHANNEL LOGIC STARTS HERE <<<                                     % NOTE: BEGIN CROSS-CHANNEL OPERATIONS
% THIS LINE SUMS ACROSS CHANNELS TO FIND ANY TIME POINT WHERE AT LEAST ONE CHANNEL IS ABOVE THRESHOLD
a=nansum(Li,1)>0;                                                            % GLOBAL TIME MASK: TRUE WHEN ANY CHANNEL IS ABOVE THRESHOLD
a=diff(a);                                                                    % EDGE DETECTION ON GLOBAL MASK: +1 ONSET, -1 OFFSET
eON=find(a==1)+1;                                                             % EVENT ONSETS: ADJUST +1 DUE TO diff() SHIFT
eOFF=find(a==-1);                                                             % EVENT OFFSETS: LOCATIONS OF FALLING EDGES
  if eOFF(1)<eON(1); eON=[1 eON]; end                                         % FIX: IF FIRST OFFSET PRECEDES ONSET, CLAMP START TO 1
  if length(eOFF)<length(eON); eOFF=[eOFF length(a)]; end                     % FIX: IF TRAILING EVENT UNTERMINATED, END AT LAST SAMPLE
  if length(eOFF)~=length(eON); error('start and end of events is not matching up, check your code'); end % SANITY: ON/OFF COUNTS MUST MATCH
ets(:,[1 2])=[eON(:) eOFF(:)];                                                % BUILD ets MATRIX: EACH ROW = [ON OFF] (SAMPLES)
% <<< CROSS-CHANNEL LOGIC ABOVE CREATES GLOBAL EVENT ON/OFF TIMES BASED ON ANY CHANNEL >>>

%Channel indexing for each event                                               % COMMENT: NOW MAP EVENTS TO CHANNELS
ech=false(size(ets,1),size(Li,1));                                            % PREALLOCATE ech (EVENTS×CHANNELS) AS FALSE
for i=1:size(ets,1)                                                           % LOOP OVER EVENTS
  % >>> CROSS-CHANNEL LOGIC: THIS SUM ACROSS CHANNELS DETERMINES WHICH CHANNELS WERE ACTIVE FOR EACH EVENT
  ech(i,:)=logical(nansum(Li(:,ets(i,1):ets(i,2)),2));                        % MARK CHANNELS ACTIVE AT ANY POINT WITHIN EVENT WINDOW
end                                                                           % END EVENT LOOP
% <<< CROSS-CHANNEL LOGIC ABOVE BUILDS THE CHANNEL PARTICIPATION MATRIX (ECH) >>>

%%  3. Additional checks/corrections                                            % SECTION HEADER: POST-PROCESSING
ets=round(ets+(sfx*llw)/2);                                                   % CENTER EVENTS BY ADDING HALF LL WINDOW (SAMPLES)

ech(:,badch)=0;                                                               % ZERO-OUT CONTRIBUTIONS FROM BAD CHANNELS
idx=sum(ech,2)<1;    ech(idx,:)=[];    ets(idx,:)=[]; clear idx              % DROP EVENTS WITH NO GOOD-CHANNEL PARTICIPATION

% >>> CROSS-CHANNEL LOGIC: MERGES EVENTS THAT OCCUR CLOSE IN TIME ACROSS CHANNELS AND COMBINES THEIR ECH FLAGS
s=size(ets,1); indx=false(s,1);                                               % PREP FOR MERGE: EVENT COUNT AND DELETION FLAG VECTOR
for i=1:s-1                                                                   % ITERATE OVER CONSECUTIVE EVENT PAIRS
  if (ets(i+1,1)-ets(i,2))<sfx*.3                                            % IF GAP BETWEEN EVENTS < 300 MS (IN SAMPLES)
    ets(i+1,1)=ets(i,1);                                                      % MERGE: SHIFT NEXT EVENT START BACK TO CURRENT START
    ech(i+1,:)=logical(sum(ech(i:i+1,:),1));                                  % MERGE CHANNEL FLAGS: CHANNEL-WISE OR ACROSS EVENTS
    indx(i)=true;                                                             % MARK CURRENT ROW FOR REMOVAL (MERGED INTO i+1)
  end                                                                         % END IF GAP CHECK
end                                                                           % END MERGE LOOP
ets(indx,:)=[];  ech(indx,:)=[];                                              % REMOVE ROWS THAT WERE MERGED INTO SUCCESSORS
% <<< CROSS-CHANNEL LOGIC ABOVE ENSURES OVERLAPPING OR NEARBY MULTI-CHANNEL EVENTS ARE MERGED TOGETHER >>>

minL=.025;                                                                    % MINIMUM EVENT DURATION (SEC)
tooshort=diff(ets,1,2)<(sfx*minL);                                           % FLAG EVENTS SHORTER THAN MIN DURATION
ets(tooshort,:)=[];  ech(tooshort,:)=[]; clear tooshort                       % DROP TOO-SHORT EVENTS FROM ets AND ech
%save d;                                                                       % (OPTIONAL DEBUG) SAVE RAW d
%save L;                                                                       % (OPTIONAL DEBUG) SAVE LL MATRIX
%save Lvec;                                                                    % (OPTIONAL DEBUG) SAVE FLATTENED LL VECTOR
%save eON;                                                                     % (OPTIONAL DEBUG) SAVE EVENT ONSETS
%save eOFF;                                                                    % (OPTIONAL DEBUG) SAVE EVENT OFFSETS
% Tada                                                                         % DONE
