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
main

=== VACC_TheVision ===
Loaded 423 events × 32 channels from ets/ech
Using 32 even-numbered channels
Loading CSC data (may take a while)...
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC2.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC4.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC6.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC8.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC10.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC12.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC14.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC16.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC18.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC20.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC22.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC24.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC26.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC28.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC30.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC32.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC34.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC36.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC38.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC40.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC42.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC44.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC46.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC48.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC50.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC52.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC54.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC56.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC58.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC60.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC62.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
	There was an error attempting to retrieve a string from index 0. Numeric data was found at that location.
  !! Failed to load CSC64.ncs: One or more output arguments not assigned during call to "Nlx2MatCSC".
Longest channel length: 0.00 sec
Selected 59 events (between 6–8 channels)
Evt 10 skipped (window [3043531 3046531] out of bounds)
Evt 13 skipped (window [3670713 3673713] out of bounds)
Evt 15 skipped (window [4126589 4129589] out of bounds)
Evt 16 skipped (window [4287862 4290862] out of bounds)
Evt 17 skipped (window [4340407 4343407] out of bounds)
Evt 20 skipped (window [10285120 10288120] out of bounds)
Evt 35 skipped (window [16791615 16794615] out of bounds)
Evt 40 skipped (window [17992409 17995409] out of bounds)
Evt 46 skipped (window [19304216 19307216] out of bounds)
Evt 51 skipped (window [20182646 20185646] out of bounds)
Evt 60 skipped (window [21250831 21253831] out of bounds)
Evt 65 skipped (window [21639182 21642182] out of bounds)
Evt 76 skipped (window [23074567 23077567] out of bounds)
Evt 78 skipped (window [23593886 23596886] out of bounds)
Evt 86 skipped (window [24094602 24097602] out of bounds)
Evt 98 skipped (window [25703971 25706971] out of bounds)
Evt 127 skipped (window [28767084 28770084] out of bounds)
Evt 128 skipped (window [28834147 28837147] out of bounds)
Evt 137 skipped (window [29947905 29950905] out of bounds)
Evt 148 skipped (window [31212013 31215013] out of bounds)
Evt 157 skipped (window [31972716 31975716] out of bounds)
Evt 193 skipped (window [36362868 36365868] out of bounds)
Evt 222 skipped (window [39003352 39006352] out of bounds)
Evt 236 skipped (window [40006299 40009299] out of bounds)
Evt 249 skipped (window [41340752 41343752] out of bounds)
Evt 252 skipped (window [41498413 41501413] out of bounds)
Evt 256 skipped (window [41771121 41774121] out of bounds)
Evt 266 skipped (window [44074606 44077606] out of bounds)
Evt 267 skipped (window [44154954 44157954] out of bounds)
Evt 271 skipped (window [44839504 44842504] out of bounds)
Evt 272 skipped (window [45161627 45164627] out of bounds)
Evt 273 skipped (window [45241488 45244488] out of bounds)
Evt 281 skipped (window [46599964 46602964] out of bounds)
Evt 282 skipped (window [46676819 46679819] out of bounds)
Evt 285 skipped (window [46913490 46916490] out of bounds)
Evt 288 skipped (window [47130590 47133590] out of bounds)
Evt 294 skipped (window [47503760 47506760] out of bounds)
Evt 308 skipped (window [48474582 48477582] out of bounds)
Evt 312 skipped (window [48816663 48819663] out of bounds)
Evt 318 skipped (window [49167196 49170196] out of bounds)
Evt 323 skipped (window [49437712 49440712] out of bounds)
Evt 326 skipped (window [49619228 49622228] out of bounds)
Evt 328 skipped (window [49700725 49703725] out of bounds)
Evt 336 skipped (window [50192149 50195149] out of bounds)
Evt 339 skipped (window [50456261 50459261] out of bounds)
Evt 347 skipped (window [50994684 50997684] out of bounds)
Evt 350 skipped (window [51187050 51190050] out of bounds)
Evt 364 skipped (window [52232021 52235021] out of bounds)
Evt 371 skipped (window [52680602 52683602] out of bounds)
Evt 374 skipped (window [52844915 52847915] out of bounds)
Evt 377 skipped (window [52940156 52943156] out of bounds)
Evt 378 skipped (window [53064174 53067174] out of bounds)
Evt 391 skipped (window [53858361 53861361] out of bounds)
Evt 395 skipped (window [54058445 54061445] out of bounds)
Evt 402 skipped (window [54468388 54471388] out of bounds)
Evt 405 skipped (window [54650245 54653245] out of bounds)
Evt 407 skipped (window [54799370 54802370] out of bounds)
Evt 419 skipped (window [55619262 55622262] out of bounds)
Evt 421 skipped (window [55793866 55796866] out of bounds)

All done! Output in: D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26\VACC_TheVision_out
