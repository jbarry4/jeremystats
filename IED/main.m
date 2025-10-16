%% After breakthrough
VACC_TheVision("D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26")




%LLSpikeViewer("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.mat")

%SpikePerEventCrossChannelAvg("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.mat")
%SpikeAvgPerChannelCompare("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.mat")
%SpikeAvgByChannel("C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_LLspikes_20250909_134703.mat")
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
%vacc_global_threshold_v5("D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26")
%BatchConvert_CSC_fromSheet("D:\PTEN\Mouse Recording Sessions.xlsx","D:\PTEN","C:\Users\Z390\Desktop\IED DATA\Converted Data")
%RunLLspikedetector_Folder("C:\Users\Barry Lab\Desktop\IED DATA\Batch raw Data")
%BuildBatchInputCSV_fromSheet("D:\PTEN\Mouse Recording Sessions.xlsx","D:\PTEN")
%% Other workspace
%SpectrogramRaster_Events_Stitched("C:\Users\Barry Lab\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Barry Lab\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat")
%SpectrogramRaster_RepSample("C:\Users\Barry Lab\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Barry Lab\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat")
%Spectrogram_Waveform_Stacked_FirstEvent("C:\Users\Barry Lab\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Barry Lab\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat")
%Pipeline_Main("C:\Users\Barry Lab\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Barry Lab\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk.mat")
%vacc_ied_detect_chunked_thr(186565)
Loaded 423 events × 32 channels from ets/ech
Using 32 even-numbered channels
	An error has occurred. Based on the field selection vector, 1 output arguments are expected, but 6 arguments were provided.
One or more output arguments not assigned during call to "Nlx2MatCSC".

Error in VACC_TheVision (line 48)
[~,~,~,~,~,hdr] = Nlx2MatCSC(fullfile(files(1).folder, files(1).name), [0 0 0 0 0], 1, 1, []);

Error in main (line 2)
VACC_TheVision("D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26")
 
