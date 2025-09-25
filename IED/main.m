%LLSpikeViewer("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.mat")

%SpikePerEventCrossChannelAvg("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.mat")
%SpikeAvgPerChannelCompare("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.mat")
%SpikeAvgByChannel("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.mat")
%TheVision("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.mat")
%TheVisionOverlay("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.mat")
%TheVisionOverlayByPolarity("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.mat")

%SolidSputterAvgStack("C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat")
%SpikeAmpWidthScatter("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.xlsx","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat")
%EventStacks_AmpWidth("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.xlsx","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_uV.mat")
%EventStacks_AmpWidth_Avg("C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_uV.mat")
%VoltageRaster_EventsAvg("C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_uV.mat")
%CSDRaster_Events("C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_uV.mat")

%CSDRaster_AvgGroups("C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_uV.mat")
%CSD_CenterSlices_Waveforms_AvgGroups("C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_uV.mat")
%CSD_TimeAvgSlices_Waveforms_AvgGroups("C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_uV.mat")

%Pipeline_Main("C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_uV.mat")




%% Other workspace
%SpectrogramRaster_Events_Stitched("C:\Users\Barry Lab\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Barry Lab\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat")
SpectrogramRaster_RepSample("C:\Users\Barry Lab\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Barry Lab\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat")



RepSample: found 13 SOLID, 4 SPUTTER (by filenames).
Spectrogram params: win=8 samp (0.267 ms) | overlap=4 samp (50%) | nfft=32 | fMax=2000 Hz | anchor search ±5.0 ms
Warning: SOLID Evt 10: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SOLID Evt 15: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SOLID Evt 16: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SOLID Evt 20: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SOLID Evt 26: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SOLID Evt 27: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SOLID Evt 35: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SOLID Evt 40: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SOLID Evt 51: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SOLID Evt 65: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SOLID Evt 76: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SOLID Evt 158: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SOLID Evt 417: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 181)
In main (line 28) 
Warning: SPUTTER Evt 13: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 182)
In main (line 28) 
Warning: SPUTTER Evt 49: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 182)
In main (line 28) 
Warning: SPUTTER Evt 98: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 182)
In main (line 28) 
Warning: SPUTTER Evt 193: Unrecognized input or invalid parameter/value pair arguments. 
> In SpectrogramRaster_RepSample>renderGroup (line 198)
In SpectrogramRaster_RepSample (line 182)
In main (line 28) 
Done.