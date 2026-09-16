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
  #colnames(cfc) <-c((1:51),"ratid","group",'region','frequency')
  rbind(Merged,cfc)}

Merged <-do.call(rbind,Merged)
for (i in 1:ncol(Merged)){
  Merged[,i] <-unlist(Merged[,i])} #For each column, unlist column. 
MergedDelta <-data.frame(rowMeans(Merged[c(1:3)]), 
                        Merged$ratid,Merged$group,Merged$region)
colnames(MergedDelta) <-c("MeanDeltaHeight","ratid","group","region")

MergedDelTheta <-data.frame(rowMeans(Merged[c(3:9)]), 
                           Merged$ratid,Merged$group,Merged$region)
colnames(MergedDelTheta) <-c("MeanDelThetaHeight","ratid","group","region")

MergedTheta <-data.frame(rowMeans(Merged[c(7:23)]), 
                        Merged$ratid,Merged$group,Merged$region) 
colnames(MergedTheta) <-c("MeanThetaHeight","ratid","group","region")

MergedBeta <-data.frame(rowMeans(Merged[c(23:40)]), 
                       Merged$ratid,Merged$group,Merged$region,Merged$frequency) 
colnames(MergedBeta) <-c("MeanBetaHeight","ratid","group","region","frequency")

Merged <-cbind(MergedBeta,MergedDelTheta,MergedDelta,MergedTheta)
Dupes <- duplicated(as.list(Merged))
Merged <-Merged[!Dupes] #I could probably not use this bit by not taking the other cols but it's fine.
Merged <-Merged[,c("MeanDeltaHeight","MeanDelThetaHeight","MeanThetaHeight","MeanBetaHeight"
                   ,"ratid","group","region","frequency")]

#Cleanup

#Merged[Merged == 'CTL'] <- 'CTL ADULT'
#Merged[Merged == 'ELSJUV'] <- 'ELS JUV'
#Merged[Merged == 'ELS Adult'] <- 'ELS ADULT'
#Merged[Merged =="ADULT ELS"] <-'ELS ADULT'
#Merged[Merged == 'CTLJUV'] <-'CTL JUV'
#Merged[Merged == "CA1 SLM"] <-"SLM"
#Merged[Merged == "CA1 PYR"] <-"Pyr"
#Merged[Merged == "CA1 Pyr"] <-"Pyr"
#Merged[Merged == "Ca1"] <-"CA1"
#Merged[Merged == "AES5R5S3"] <-"AES5R5"
#Merged[Merged == "P23ELS7"] <-"23ELS7"
#Merged[Merged == "ELS12"] <-"12"
#Merged[Merged == "ELS15"] <-"15"
#Merged[Merged == "ELS3S3"] <-"34ELS3"
#Merged[Merged == "ELS4S2"] <- "33ELS4"
#Merged[Merged == "ELS5S3"] <-"32ELS5"
#Merged[Merged == "ELS6S3"] <-"30ELS6"
#Merged[Merged == "ELS9S3"] <- "ELSJUV9"
#Merged[Merged == "ELS11S2"] <-"ELSJUV11"
#Merged[Merged== "ELS16"] <- "ELSJUV16"



write_csv(Merged, "CFCMerged.csv")

