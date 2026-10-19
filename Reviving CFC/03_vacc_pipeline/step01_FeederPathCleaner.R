#We have a simple process here. We are to take feeder.xlsx, and read them.
#We will either use escape characters and regex to remove the offending title
#Or we will simply mash it together and export, to do this in excel.
library("tidyverse")
library("data.table")
library("readxl")
library("openxlsx")
#Read
setwd('D://PupProbePilot//Matlab Code for amplitude and frequency and feeder sheet')
Files <-list.files(pattern='Feeder.xlsx') 
Compiled <-lapply(Files, read_xlsx, sheet = "Torun", 
                  col_names = c("Filler", "RatID", "eegnum",
                                "Session", "path", "cond",
                                "grp", "file", "side",
                                "region","more"))
Compiled<-as.data.frame(rbindlist(Compiled,fill=FALSE, use.names = TRUE, idcol = NULL))
setwd("D://PupProbePilot//Matlab Code for amplitude and frequency and feeder sheet//FeedersUpload")
write.xlsx(Compiled,"CompiledFeeders.xlsx")
#ENSURE YOU CLEAN THE FEEDERS HERE.
ToSplit<-read.xlsx("CompiledFeeders.xlsx")
SplitData <-split(ToSplit, ToSplit$RatID)
lapply(1:length(SplitData), function (i) write.xlsx(SplitData[[i]],
       file = paste0(names(SplitData[i]), "VACCFeeder.xlsx"), row.names = FALSE))


#lapply(1:length(SplitData), function (i) write.csv(SplitData[[i]],
                                                    #file = paste0(names(SplitData[i]), "VACCFeeder.csv"), row.names = FALSE))

#This was taken from StackOverflow. We are saying, for a length of 1 to
#Data length of split data, we perform the write.xslx function, for each piece of data.
#And the file name is "paste0(the names(SplitData[Part of index]).xlsx)


#Getting foldernames for VACC
Feedernames <-list.files(pattern='VACCFeeder.xlsx') 
cat(Feedernames, file = "feeder_sheets.txt")
