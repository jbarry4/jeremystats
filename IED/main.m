%% After breakthrough
%VACC_TheVision("D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26")
%VACC_Pipeline_Main("D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26")
%vacc_summarize_master("compiled_master.mat")
%VACC_Pipeline_Main("D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26\VACC_TheVision_out","D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26")


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

Pipeline_Main("C:\Users\Z390\Desktop\IED DATA\Take 2\PTEN_M13_pten_HF4s1aug1\group_05-10 (1)","C:\Users\Z390\Desktop\IED DATA\Take 2\PTEN_M13_pten_HF4s1aug1\LL_input_2023-08-01_11-37-10_mex_disk_uV.mat")
%convert_fig_to_svg_robust("C:\Users\info\Desktop\Barry\jeremystats\IED\Theta Graph Data\theta.fig")
%ThetaRaster("C:\Users\Z390\Desktop\jeremystats\IED\Theta Graph Data")
%ThetaRaster_Pipeline("C:\Users\Z390\Desktop\jeremystats\IED\Theta Graph Data")

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
