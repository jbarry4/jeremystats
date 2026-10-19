figpath = 'C:\Users\Z390\Desktop\PTEN_CFCs\VACC\CFC\CNO_Data\IED+\2\m13\transposed'
figslist = dir(fullfile(figpath,'*.fig'));
for i = 1:length(figslist)
currentFig = fullfile(figpath, figslist(i).name);
saveName = erase(currentFig, '.fig');
openfig(currentFig)
fig = gcf;

dataObjs = findobj(fig,'-property','XData');
x1 = dataObjs(1).XData;
dataObjs = findobj(fig,'-property','YData');
y1 = dataObjs(1).YData;
dataObjs = findobj(fig,'-property','ZData');
z1 = dataObjs(1).ZData;

save(strcat(saveName,'_CFCRipx1.mat'),'x1')
save(strcat(saveName,'_CFCRipy1.mat'),'y1')
save(strcat(saveName,'_CFCRipz1.mat'),'z1')
close
end