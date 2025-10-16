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
Processing 59 events (±50.0 ms window)...
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch1 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch2 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch3 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch4 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch5 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch6 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch7 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch8 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch9 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch10 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch11 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch12 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch13 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch14 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch15 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch16 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch17 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch18 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch19 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch20 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch21 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch22 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch23 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch24 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch25 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch26 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch27 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch28 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch29 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch30 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch31 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch32 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch33 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch34 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch35 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch36 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch37 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch38 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch39 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch40 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch41 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch42 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch43 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch44 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch45 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch46 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch47 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch48 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch49 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch50 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch51 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch52 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch53 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch54 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch55 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch56 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch57 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch58 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch59 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch60 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch61 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch62 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch63 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
Ch64 failed: One or more output arguments not assigned during call to "Nlx2MatCSC".
Index exceeds the number of array elements. Index must not exceed 32.