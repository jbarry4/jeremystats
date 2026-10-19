library(tidyverse)
setwd("D://PupProbePilot//Matlab Code for amplitude and frequency and feeder sheet//CFC//ReadFiles")
Check <- read.csv("CFCMerged.csv")
Check$region <-factor(Check$region, levels = c("CA1","Pyr","Rad","SLM","OML","MML","GCL","HIL"))

#CTL AD Check ---------
CheckCTAD <-Check %>% filter (group == "CTL ADULT")
CheckCTAD %>%
  ggplot(aes(x = frequency, y = MeanDeltaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

CheckCTAD %>%
  ggplot(aes(x = frequency, y = MeanDelThetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

Color<- CheckCTAD %>% filter(ratid != "AES8R4")
Color %>% 
  ggplot(aes(x = frequency, y = MeanThetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

CheckCTAD %>%
  ggplot(aes(x = frequency, y = MeanThetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

CheckCTAD %>%
  ggplot(aes(x = frequency, y = MeanBetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)


#CTLJUV Check ----
CheckCTJUV <-Check %>% filter (group == "CTL JUV")

CheckCTJUV %>%
  ggplot(aes(x = frequency, y = MeanDeltaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

CheckCTJUV %>%
  ggplot(aes(x = frequency, y = MeanDelThetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

CheckCTJUV %>%
  ggplot(aes(x = frequency, y = MeanThetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

CheckCTJUV %>%
  ggplot(aes(x = frequency, y = MeanBetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)






#ELAD Check----
CheckELSAD <- Check %>% filter(group == "ELS ADULT")

CheckELSAD %>%
  ggplot(aes(x = frequency, y = MeanDeltaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

CheckELSAD %>%
  ggplot(aes(x = frequency, y = MeanDelThetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

CheckELSAD %>%
  ggplot(aes(x = frequency, y = MeanThetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

CheckELSAD %>%
  ggplot(aes(x = frequency, y = MeanBetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)


#ELJUV Check----
CheckELJUV <-Check%>% filter(group == "ELS JUV")



CheckELJUV %>%
  ggplot(aes(x = frequency, y = MeanDeltaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

CheckELJUV %>%
  ggplot(aes(x = frequency, y = MeanDelThetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

CheckELJUV %>%
  ggplot(aes(x = frequency, y = MeanThetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)

CheckELJUV %>%
  ggplot(aes(x = frequency, y = MeanBetaHeight, color = ratid))+
  geom_point()+
  facet_wrap(~region)
