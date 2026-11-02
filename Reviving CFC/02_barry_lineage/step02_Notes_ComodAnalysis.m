load '/Volumes/Backup Plus/Michelle/FSEGrp3/FSE30s9/Comod/Comodulogram_24.mat'
Comodulogram=Comodulogram'
%Renaame with CSC filename once transposed?

%Orientation is by number (i.e., 2.75 Hz on x axis and 40 Hz on y axis is
%(4,4)

%Unfortunatly, in workspace it's just named 'Comodulagram', so need to be
%careful with filehandling

Delta = Comodulogram(1:end,1:3);
Mean_Delta=mean(Delta,2);
figure1=figure
plot (y1,Mean_Delta)

DelTheta = Comodulogram(1:end,3:9);
Mean_DelTheta=mean(DelTheta,2);
figure2=figure
plot (y1,Mean_DelTheta)

Theta = Comodulogram(1:end,7:23);
Mean_Theta=mean(Theta,2);
figure3=figure
plot (y1,Mean_Theta)

Beta = Comodulogram(1:end,23:40);
Mean_Beta=mean(Beta,2);
figure4=figure
plot (y1,Mean_Beta)


save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE36s4/Mean_Delta.mat', 'Mean_Delta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE36s4/Mean_DelTheta.mat', 'Mean_DelTheta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE36s4/Mean_Theta.mat', 'Mean_Theta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE36s4/Mean_Beta.mat', 'Mean_Beta')

save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE35s4/Mean_Delta.mat', 'Mean_Delta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE35s4/Mean_DelTheta.mat', 'Mean_DelTheta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE35s4/Mean_Theta.mat', 'Mean_Theta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE35s4/Mean_Beta.mat', 'Mean_Beta')

save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE-FSE33s4/Mean_Delta.mat', 'Mean_Delta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE-FSE33s4/Mean_DelTheta.mat', 'Mean_DelTheta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE-FSE33s4/Mean_Theta.mat', 'Mean_Theta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE-FSE33s4/Mean_Beta.mat', 'Mean_Beta')

save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE34s4/Mean_Delta.mat', 'Mean_Delta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE34s4/Mean_DelTheta.mat', 'Mean_DelTheta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE34s4/Mean_Theta.mat', 'Mean_Theta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE34s4/Mean_Beta.mat', 'Mean_Beta')

save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE27s4/Mean_Delta.mat', 'Mean_Delta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE27s4/Mean_DelTheta.mat', 'Mean_DelTheta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE27s4/Mean_Theta.mat', 'Mean_Theta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE27s4/Mean_Beta.mat', 'Mean_Beta')

save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE28s/Mean_Delta.mat', 'Mean_Delta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE28s/Mean_DelTheta.mat', 'Mean_DelTheta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE28s/Mean_Theta.mat', 'Mean_Theta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/FSE_FSE28s/Mean_Beta.mat', 'Mean_Beta')


save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE26s9/Mean_Delta.mat', 'Mean_Delta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE26s9/Mean_DelTheta.mat', 'Mean_DelTheta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE26s9/Mean_Theta.mat', 'Mean_Theta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE26s9/Mean_Beta.mat', 'Mean_Beta')

save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE25s2/Mean_Delta.mat', 'Mean_Delta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE25s2/Mean_DelTheta.mat', 'Mean_DelTheta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE25s2/Mean_Theta.mat', 'Mean_Theta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE25s2/Mean_Beta.mat', 'Mean_Beta')

save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE31s4/Mean_Delta.mat', 'Mean_Delta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE31s4/Mean_DelTheta.mat', 'Mean_DelTheta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE31s4/Mean_Theta.mat', 'Mean_Theta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE31s4/Mean_Beta.mat', 'Mean_Beta')


save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE30s9/Mean_Delta.mat', 'Mean_Delta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE30s9/Mean_DelTheta.mat', 'Mean_DelTheta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE30s9/Mean_Theta.mat', 'Mean_Theta')
save('/Users/jeremybarry/Documents/UVM/projects/FSE/Michelle/FSE project/CoModulation/CTL_FSE30s9/Mean_Beta.mat', 'Mean_Beta')


