#This reads .mat files and clusters them together into column chunks for SPSS analysis.
#Library & Data----
library(tidyverse)
library(R.matlab)
library(stringr)
library(doParallel)
library(foreach)
matdf <- function(df)
{as.data.frame(readMat(df))}
setwd("C:/Users/Z390/Desktop/PTEN_CFCs/VACC/VACC_CFC_Input/VACCQuickstart")
YTemplate <-t(matdf("M13_HeadFixed -post CNO_ComodFig_1_transposed_CFCRipy1.mat"))

#Get the data
setwd("C:/Users/Z390/Desktop/PTEN_CFCs/VACC/CFC/CNO_Data/IED+/2/m13/transposed")
Mats <-list.files(pattern ="*.mat")
Matlength <- length(Mats)
Merged <- data.frame()

#Register parallel loop----
#Establish cores
n.cores <- parallel::detectCores() - 2
my.cluster <- parallel::makeCluster(n.cores, type = "PSOCK")
#Register cores
doParallel::registerDoParallel(cl = my.cluster)
#Ensure registry
foreach::getDoParRegistered()

#Parfor
Merged<-data.frame()
Merged <-foreach(ii = 1:Matlength) %do% {
  cfc<-matdf(Mats[ii]) #Make a df and assemble it by reading these files
  #print('1')
  cfc <-cbind (cfc,YTemplate) #Add the Y template for each read .mat
  #print('2')
  colnames(cfc) <-c((1:51),"eeg")
  rbind(Merged,cfc)}

Merged <-do.call(rbind,Merged)
for (i in 1:ncol(Merged)){
  Merged[,i] <-unlist(Merged[,i])} #For each column, unlist column. 
MergedDelta <-data.frame(rowMeans(Merged[c(1:3)]), 
                         Merged$eeg)
colnames(MergedDelta) <-c("MeanDeltaHeight","eeg")

MergedDelTheta <-data.frame(rowMeans(Merged[c(3:9)]), 
                            Merged$eeg)
colnames(MergedDelTheta) <-c("MeanDelThetaHeight","eeg")

MergedTheta <-data.frame(rowMeans(Merged[c(7:23)]), 
                         Merged$eeg) 
colnames(MergedTheta) <-c("MeanThetaHeight","eeg")

MergedBeta <-data.frame(rowMeans(Merged[c(23:40)]), 
                        Merged$eeg) 
colnames(MergedBeta) <-c("MeanBetaHeight","eeg")

Merged <-cbind(MergedBeta,MergedDelTheta,MergedDelta,MergedTheta)
Dupes <- duplicated(as.list(Merged))
Merged <-Merged[!Dupes] #I could probably not use this bit by not taking the other cols but it's fine.
Merged <-Merged[,c("MeanDeltaHeight","MeanDelThetaHeight","MeanThetaHeight","MeanBetaHeight"
                   ,"eeg")]

write_csv(Merged, "CFCMerged.csv")