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

Pipeline_Main("C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1","C:\Users\Z390\Desktop\IED DATA\LL_input_M13s2aug1_2023-08-01_12-11-26_mex_disk_uV.mat")

 C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1\Pipeline Output\Master_Stats.csv
main
EventStacks_ampWidth_Avg_Pipeline: sfx=30000.0 Hz | display ±10.0 ms | metrics ±5.0 ms | anchorSearch ±5.0 ms | channels=32
Found 13 SOLID, 4 SPUTTER events (by filenames).
SOLID: used 13/13 events (any channel contributed).
Saved group stats: C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1\EventStacks AmpWidth Output\AvgStack_SOLID_stats.mat
SPUTTER: used 4/4 events (any channel contributed).
Saved group stats: C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1\EventStacks AmpWidth Output\AvgStack_SPUTTER_stats.mat
Global y-limit (both figs): ±3873.0 µV (auto)
Saved: C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1\EventStacks AmpWidth Output\AvgStack_SOLID_anchor-max_disp300s_met150s.png
Saved: C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1\EventStacks AmpWidth Output\AvgStack_SPUTTER_anchor-max_disp300s_met150s.png
Warning: Failed writing EventStacks per-channel stats CSV: Duplicate dimension and variable name:
'Row'. 
> In EventStacks_ampWidth_Avg_Pipeline (line 190)
In Pipeline_Main (line 13)
In main (line 21) 
EventStacks pipeline outputs:
  C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1\EventStacks AmpWidth Output\AvgStack_SOLID_anchor-max_disp300s_met150s.png
  C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1\EventStacks AmpWidth Output\AvgStack_SPUTTER_anchor-max_disp300s_met150s.png
  C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1\EventStacks AmpWidth Output\EventStacks_perChannel_Stats.csv
VoltageRaster_AvgGroups: sfx=30000.0 Hz | window ±20.0 ms | anchor: firstCh max (±5.0 ms)
Found 13 SOLID, 4 SPUTTER events (by filenames).
Global CLim (averages): ±1899.40 µV.
Saved SOLID average raster: C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1\Voltage Raster Output\Raster_Avg_SOLID.png
Saved SPUTTER average raster: C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1\Voltage Raster Output\Raster_Avg_SPUTTER.png
CSD AvgGroups: sfx=30000.0 Hz | window ±20.0 ms | anchor: firstCh max (±5.0 ms)
Found 13 SOLID, 4 SPUTTER events (by filenames).
Global CSD CLim (averages): ±859.46 (CSD units).
Saved SOLID average CSD raster: C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1\CSD Raster Output\CSD_Raster_Avg_SOLID.png
Saved SPUTTER average CSD raster: C:\Users\Z390\Desktop\IED DATA\Preped Data - M13s2aug1\CSD Raster Output\CSD_Raster_Avg_SPUTTER.png
CSD Center Slices: sfx=30000.0 Hz | window ±20.0 ms | anchor: firstCh max (±5.0 ms)
Found 13 SOLID, 4 SPUTTER events (by filenames).
Warning: CSD_CentersSlieces_Waveform_AvgGroups_Pipeline: generation failed: Unrecognized input or
invalid parameter/value pair arguments. 
> In CSD_CentersSlieces_Waveform_AvgGroups_Pipeline (line 52)
In Pipeline_Main (line 37)
In main (line 21) 
Warning: Failed to build SOLID montage: Undefined function 'makeMontageHiRes' for input arguments of
type 'string'. 
> In Pipeline_Main (line 86)
In main (line 21) 
Warning: Failed to build SPUTTER montage: Undefined function 'makeMontageHiRes' for input arguments
of type 'string'. 
> In Pipeline_Main (line 97)
In main (line 21) 
Warning: VoltageRaster CSV read failed: Undefined function 'vertcatSafe' for input arguments of type
'table'. 
> In Pipeline_Main (line 107)
In main (line 21) 
Warning: CSDRaster CSV read failed: Undefined function 'vertcatSafe' for input arguments of type
'table'. 
> In Pipeline_Main (line 110)
In main (line 21) 
Warning: CSD Center Slices CSV read failed: Undefined function 'vertcatSafe' for input arguments of
type 'table'. 
> In Pipeline_Main (line 113)
In main (line 21) 