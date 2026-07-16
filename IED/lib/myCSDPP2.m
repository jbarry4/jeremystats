%function [csd, newtrange, newchrange] = CurSrcDns(eeg,trange,type,chnum,chanrange,samplerate, step, ColorRange)
%function [csd, newtrange, newchrange] = CurSrcDns(eeg,varargin)

function [csd,newtrange,newchrange]=CSDPP2(eeg,type,samplerate);

samplerate=samplerate(1); %in case there is a mistake



step=1; %if you want to use a fancier method (but gives same results)
ColorRange=[];

method =2; %%if you want to use standard(1) or a fancier (2) method (but give same results) (1 ou 2)

if size(eeg,1)<size(eeg,2) % to make sure the matrix is organized as I expect it
    eeg  = eeg';
end
chnum=size(eeg,2);

si=(1/samplerate)*1E6;%% units will be in microseconds (1E-6 s)

trange=[0:si:(si)*length(eeg)]; % current time range

csd=eeg;
if (method == 1)
    csd=-diff(csd,2,2); % the easy one Could Have used diff(diff) WHY the "-" because of the diff
    ch=[2:chnum-1];
else %% use this one!
    ch=[step+1:chnum-step];
    csd = csd(:,ch+step) - 2*csd(:,ch) + csd(:,ch-step); % the complex one
    csd = -csd; %%% Marat I don't get this one
end
   


    csd=interp2(csd, 'linear'); %increase resolution%to make a nice graph I changed the size of the EEG like if I had a half channel and plenty of time

    newtrange=linspace(trange(1),trange(end),size(csd,1)); % get new time and channel resolutions
    % newchrange=linspace(ch(1), ch(end), size(csd,2)); %old version
    newchrange=linspace(ch(1)-0.5, ch(end)+0.5, size(csd,2));
    if (type=='c')
        pcolor(newtrange*1E-6,newchrange,csd'); %%% plotting inverts the channels, think about 

        set(gca,'YTick',[1:1:max(newchrange)+1]);
%         set(gca,'YTick', newchrange(1:2:end));
        shading interp
        axis tight
%         set(gca,'ydir','rev'); %%% MARAT why did you do that you drove me nuts for months!!!!
        %         colorbar
        if (isempty(ColorRange))
            cx =caxis;
            cxmax = max(abs(cx));
            caxis([-cxmax cxmax]);
        else
            caxis(ColorRange);
        end
    elseif (type=='l') % fuhgetaboutit
        spacing= mean(max(csd,[],1)-min(csd,[],1)) ;
        plot(newtrange,cpsd'-repmat(newchrange*spacing,length(newtrange),1)','k'); 
    end
end

