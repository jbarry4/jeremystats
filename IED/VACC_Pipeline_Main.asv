function VACC_Pipeline_Main(dataDir, varargin)
% VACC_Pipeline_Main — VACC version of your master pipeline.
% - INPUT: dataDir containing CSC*.ncs, ets.mat, ech.mat
% - Loads header ONCE (ADBitVolts, fs), loads raw samples per channel
%   (even-only by default), flips polarity, converts to µV (single).
% - Passes the converted data (struct V) into each VACC_* sub-pipeline.
%
% Example:
%   VACC_Pipeline_Main("D:\PTEN\PTEN\MouseX\IED DATA");

% ---------- Options ----------
p = inputParser;
p.addRequired('dataDir', @(s)ischar(s)||isstring(s));
p.addParameter('evenOnly', true, @(x)islogical(x));
p.addParameter('invertPolarity', true, @(x)islogical(x));
p.parse(dataDir, varargin{:});
dataDir        = string(p.Results.dataDir);
evenOnly       = p.Results.evenOnly;
invertPolarity = p.Results.invertPolarity;

fprintf('\n=== VACC_Pipeline_Main ===\n');

% ---------- Output hub ----------
masterOutDir     = fullfile(dataDir, 'Pipeline Output');
if ~exist(masterOutDir, 'dir'), mkdir(masterOutDir); end
triptychSOLID    = fullfile(masterOutDir, 'Master_Compact_SOLID.png');
triptychSPUTTER  = fullfile(masterOutDir, 'Master_Compact_SPUTTER.png');
masterCSV        = fullfile(masterOutDir, 'Master_Stats.csv');

% ---------- Load converted data once ----------
V = VACC_loadNeuralynxData(dataDir, 'evenOnly', evenOnly, 'invertPolarity', invertPolarity);
% V fields: V.D [nCh x nSamp] (µV, single), V.fs (Hz), V.nums (CSC numbers), V.ADBitVolts

% ---------- 1) EventStacks (CENTER) ----------
evtStacksRes = [];
try
    evtStacksRes = VACC_EventStacks_ampWidth_Avg(dataDir, V);
catch ME
    warning(ME.identifier, 'EventStacks failed: %s', ME.message);
end

% % ---------- 2) Voltage Raster (LEFT) ----------
% voltRasterRes = [];
% try
%     voltRasterRes = VACC_VoltageRaster_EventsAvg(dataDir, V);
% catch ME
%     warning(ME.identifier, 'VoltageRaster failed: %s', ME.message);
% end
% 
% % ---------- 3) CSD Raster (RIGHT) ----------
% csdRasterRes = [];
% try
%     csdRasterRes = VACC_CSDRaster_Avg(dataDir, V);
% catch ME
%     warning(ME.identifier, 'CSDRaster failed: %s', ME.message);
% end
% 
% % ---------- 4) CSD Center Slices + Vertical Waveforms (LEFT) ----------
% csdSlicesRes = [];
% try
%     csdSlicesRes = VACC_CSD_CenterSlices_Waveform_AvgGroups(dataDir, V);
% catch ME
%     warning(ME.identifier, 'CSD CenterSlices failed: %s', ME.message);
% end
% 
% % ---------- 5) CSD Time-Avg Slices + Vertical Waveforms (RIGHT) ----------
% csdTimeAvgRes = [];
% try
%     csdTimeAvgRes = VACC_CSD_TimeAvgSlices_Waveforms_AvgGroups(dataDir, V);
% catch ME
%     warning(ME.identifier, 'CSD TimeAvgSlices failed: %s', ME.message);
% end
% 
% % ---------- 6) Spectrogram + Waveform (LEFT, bottom) ----------
% spec3rdRes = [];
% try
%     spec3rdRes = VACC_Spectrogram_Waveform_ThirdEvent(dataDir, V);
% catch ME
%     warning(ME.identifier, 'Spectrogram ThirdEvent failed: %s', ME.message);
% end
% 
% % ---------- Build SOLID triptych ----------
% try
%     colLeft_SOL  = stackVerticalHiRes({ ...
%         getFileIfExists(getFieldSafe(voltRasterRes,'pngSolid')), ...
%         getFileIfExists(getFieldSafe(csdSlicesRes,'pngSolid')), ...
%         getFileIfExists(getFieldSafe(spec3rdRes,'pngSolid'))}, 6);
%     colCtr_SOL   = getFileIfExists(getFieldSafe(evtStacksRes,'pngSolid'));
%     colRight_SOL = stackVerticalHiRes({ ...
%         getFileIfExists(getFieldSafe(csdRasterRes,'pngSolid')), ...
%         getFileIfExists(getFieldSafe(csdTimeAvgRes,'pngSolid'))}, 6);
% 
%     cols_SOL = filterNonEmpty({colLeft_SOL, colCtr_SOL, colRight_SOL});
%     if ~isempty(cols_SOL)
%         composeColumnsHiRes(cols_SOL, triptychSOLID, 10);
%         fprintf('Master SOLID compact montage saved: %s\n', triptychSOLID);
%     else
%         warning('No SOLID images found; SOLID compact montage not created.');
%     end
% catch ME
%     warning(ME.identifier, 'Failed to build SOLID montage: %s', ME.message);
% end

% ---------- Build SPUTTER triptych ----------
try
    colLeft_SPU  = stackVerticalHiRes({ ...
        getFileIfExists(getFieldSafe(voltRasterRes,'pngSputter')), ...
        getFileIfExists(getFieldSafe(csdSlicesRes,'pngSputter')), ...
        getFileIfExists(getFieldSafe(spec3rdRes,'pngSputter'))}, 6);
    colCtr_SPU   = getFileIfExists(getFieldSafe(evtStacksRes,'pngSputter'));
    colRight_SPU = stackVerticalHiRes({ ...
        getFileIfExists(getFieldSafe(csdRasterRes,'pngSputter')), ...
        getFileIfExists(getFieldSafe(csdTimeAvgRes,'pngSputter'))}, 6);

    cols_SPU = filterNonEmpty({colLeft_SPU, colCtr_SPU, colRight_SPU});
    if ~isempty(cols_SPU)
        composeColumnsHiRes(cols_SPU, triptychSPUTTER, 10);
        fprintf('Master SPUTTER compact montage saved: %s\n', triptychSPUTTER);
    else
        warning('No SPUTTER images found; SPUTTER compact montage not created.');
    end
catch ME
    warning(ME.identifier, 'Failed to build SPUTTER montage: %s', ME.message);
end

% ---------- Merge available stats into a single CSV ----------
T = table();
T = tryAddCSV(T, evtStacksRes,  'EventStacks');
T = tryAddCSV(T, voltRasterRes, 'VoltageRaster');
T = tryAddCSV(T, csdRasterRes,  'CSDRaster');
T = tryAddCSV(T, csdSlicesRes,  'CSDCenterSlices');
T = tryAddCSV(T, csdTimeAvgRes, 'CSDTimeAvg');
% (Spectrogram block has no CSV)

try
    if isempty(T)
        T = table(string(datetime('now')), "EMPTY", 'VariableNames', {'GeneratedAt','Note'});
    end
    writetable(T, masterCSV);
    fprintf('Master stats CSV: %s\n', masterCSV);
catch ME
    warning(ME.identifier, 'Failed writing master stats CSV: %s', ME.message);
end
end
