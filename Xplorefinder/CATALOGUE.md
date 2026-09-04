# Xplorefinder — catalogue

MATLAB/GUIDE application for browsing and analysing Neuralynx electrophysiology
recordings: multi-channel EEG/LFP (`.ncs`), spike files (`.ntt`, `.nse`), video
tracking (`.nvt`), events (`.nev`), and MPEG video, all on one shared time axis
with a scrolling window.

Catalogued 2026-09-03 from `C:\Users\Z390\Documents\matlab`.

---

## 1. Where the code actually is

There is no `Xplorefinder` source folder. The application is split across two
directories, and **neither one is self-contained**.

| Path | Holds |
|---|---|
| `OurMfiles\commonGUIs\` | the newest `xplorefinder.m` (+ two older variants), and ~14 sibling GUIs |
| `matlab\xplorer\` | `xplorefinder.fig`, the `.ncs` reader class, and most helper code |

`xplorer\` is a sibling of `OurMfiles\`, not inside it.

### Three copies of xplorefinder.m

| File | Modified | Lines | Reads `.ncs` via | Video |
|---|---|---|---|---|
| `commonGUIs\xplorefinder.m` | 2022-02-10 | 3817 | `Cscfile2_PP` | yes (`.mpg`) |
| `commonGUIs\xplorefinder_tryfix.m` | 2020-04-16 | 3817 | `Cscfile2` | yes |
| `commonGUIs\xplorefinder_old.m` | 2020-10-13 | 3644 | `Cscfile2` | yes |
| `xplorer\xplorefinder.m` | 2015-03-20 | 3809 | `Cscfile2` | no |

`commonGUIs\xplorefinder.m` is the current version. Against `_tryfix` it differs
in exactly two lines: the reader class, and one regression (§6).

The 2015 `xplorer` copy is the last one that shipped with its own `.fig`. The
`.mpg` support and the `Cscfile2_PP` reader arrived after it.

### The copy you want to run cannot start on its own

`commonGUIs\xplorefinder.m` has **no `.fig` file** — every other GUI in that
folder does. GUIDE resolves the layout by name off the MATLAB path, so it
silently picks up `xplorer\xplorefinder.fig` (2015). Same for
`xplorcursorarrow.mat`, loaded by name in `xplorefinder_OpeningFcn`.

So the newest `.m` runs against a seven-year-older layout. Every uicontrol the
`.m` reaches by tag must still exist in that 2015 `.fig`. It evidently does — but
it means the two halves are versioned independently, and adding a control to the
`.fig` is the one change that cannot be made from `commonGUIs` alone.

**To run it:**

```matlab
addpath('C:\Users\Z390\Documents\matlab\OurMfiles\commonGUIs')
addpath('C:\Users\Z390\Documents\matlab\xplorer')
addpath('C:\Users\Z390\Documents\matlab\OurMfiles\FileHandling')
addpath(genpath('C:\Users\Z390\Documents\matlab\OurMfiles\chronux'))
addpath('C:\Users\Z390\Documents\matlab\OurMfiles\Rustem')       % CSDPP2
xplorefinder
```

Order matters: `commonGUIs` must precede `xplorer` so the 2022 `.m` wins over the
2015 one, while the 2015 `.fig` is still found.

---

## 2. How it is built

One GUIDE figure, one state struct, one redraw function.

**State** — a single struct stored with `guidata(gcbf, Data)`, fetched at the top
of nearly every callback. GUIDE's `handles` *is* `Data`; the opening function
seeds it and from then on the two names are used interchangeably.

| Field | Meaning |
|---|---|
| `Data.start`, `Data.range` | displayed window: start time and width, seconds |
| `Data.file(i)` | per-channel data. For `.ncs`, a `Cscfile2_PP` object |
| `Data.xtraFileData(i)` | per-channel view settings — see below |
| `Data.ctrlsig(i)` | per-channel uicontrol handles, built at load time |
| `Data.ax(i)`, `Data.axftt(i)` | signal axes and Analyse axes for channel `i` |
| `Data.filentt(i)` | spike/event times and cluster ids |
| `Data.filenvt(i)` | position tracking (TS, X, Y) |
| `Data.filevideo(i)` | `.mpg` filename and sync offset |
| `Data.lineTS`, `Data.winTS` | draggable time markers and range selection |
| `Data.spkypesrch(i)` | event-detector settings per channel |
| `Data.currentctrlaxe` | which channel the shared control panel is editing |

`Data.xtraFileData(i)` is the per-channel view state, initialised at load
(`pushbutton1_Callback`, ~line 240):

```matlab
struct('name','','height',5,'viewfft',0,'viewgraph',1,'ftype',ftype, ...
       'lowpass',0,'highpass',0,'frame_length',0,'frame_overlap',0, ...
       'zoom',1,'nlyzminf',0,'nlyzmaxf',200,'duplicate',0,'correlationeeg',[])
```

`viewfft` is the **Analyse** checkbox. `nlyzminf`/`nlyzmaxf` are the frequency
band. `frame_length`/`frame_overlap` are the STFT parameters (0 = auto).
`height` is the channel's relative row height in the stack; `duplicate` links a
channel to another shown twice with different filtering.

**Redraw** — `update_graph(Data, notmodifydata)` (~line 1279, ~600 lines) is the
whole renderer. It lays the visible channels out with `subaxis`, re-reads samples
from disk unless `notmodifydata` is set, draws each signal, then draws each
channel's Analyse panel. `eegcorrelation(Data)` runs right after it for the
two-channel Analyse modes, because those need every channel loaded first.

Anything that changes the view calls `update_graph` and then `guidata`. Passing
`'true'` as `notmodifydata` means "redraw, don't re-read from disk" — note it is
the *string* `'true'`, tested with `nargin < 2`, not a logical.

**Reading** — `Cscfile2_PP` (`xplorer\Cscfile2_PP.m`) is a value class that reads
a `.ncs` window at a time rather than the whole file: `setstart`, `setrange`,
`sethighpass`, `setlowpass`, `setfiltertype`, then `readdata()` populates
`.Samples` and `.currentSF`. Being a value class, every setter returns a new
object and must be reassigned (`f = f.setstart(10)`). Filtering is Chebyshev
type II via `filtfilt`, with an optional `iirnotch`; a low-pass may also trigger
downsampling, which is why `currentSF` exists alongside `SF`.

---

## 3. Input formats

Dispatched by extension in `pushbutton1_Callback` (~line 219).

| Ext | Content | Reader |
|---|---|---|
| `.ncs` | continuous EEG/LFP | `Cscfile2_PP` |
| `.ntt` | tetrode spikes + clusters | `read_ntt` |
| `.nse` | single-electrode spikes | `read_Se` |
| `.nev` | event strings + TTL | `read_nev` |
| `.nvt` | video position tracking | `Read_nvt_Automatic` |
| `.dat` | Biosig position + `.nev` for sync | `read_biosig` + `read_nev` |
| `.txt` `.csv` `.xls` | timestamps, optional cluster column | `load` |
| `.mpg` | video, synced via a sibling `.smi` | `mmread` |

Two ordering rules run before loading: `.ncs` files are moved to the front of the
selection, and `CSC<n>.ncs` names are sorted numerically rather than
lexically — so `CSC2` precedes `CSC10`.

All channels are aligned by subtracting `Data.TSfirstpoint`, the first timestamp
of the first file loaded. Files whose first timestamp disagrees are forced onto
that reference and a warning goes to the command window.

**`.mpg` needs `mmread`, which is not present anywhere in the tree.** The video
path (`playvideocallback`, ~line 1194) will error until it is installed.

---

## 4. The Analyse code → `Analyse\`

The **Analyse** checkbox plus its dropdown is the analysis half of the
application: spectrogram, spectrum, dominant-frequency tracking, spectrogram
differencing, and coherency. Eight modes, all reached through
`get(Data.ctrlsig(i).nlyztype,'value')`.

In the source this code has no existence outside the GUI — it reads
`Data.xtraFileData` and writes to a subplot inside `update_graph` and
`eegcorrelation`. **[`Analyse\`](Analyse/) is that code extracted into callable
functions**, with the dependencies it needs vendored alongside.

| # | Dropdown label | What it does |
|---|---|---|
| 1 | `Spectogram` | hamming STFT via `spStft`, dB image |
| 2 | `Spectrum` | Welch PSD, window scaled to the displayed band |
| 3 | `Diff Spectrum` | same on `diff(x)` — pre-whitens the 1/f slope |
| 4 | `Correlation...` | multitaper spectrogram difference + one global `corr2` |
| 5 | `chronus spectogram` | multitaper spectrogram via `mtspecgramc` |
| 6 | `max freq in time` | argmax-over-band ridge, Chebyshev-smoothed |
| 7 | `Correlation classic...` | as 4, but STFT instead of multitaper |
| 8 | `coherency...` | segmented multitaper coherency via `coherencysegc` |

See **[`Analyse\README.md`](Analyse/README.md)** for the API, and for the
behavioural quirks the extraction preserves — the non-standard `30*log10` dB
scale, the frame-overlap default that disagrees with its own dialog, and the fact
that the two "Correlation" modes draw a difference image rather than a
correlation.

Related analysis code, also extracted: `xf_csd` (the live CSD window),
`xf_findEvents` (the `LocalMinima` peak detector behind the spike finder), and
`xf_extractWaveforms` (waveform cutting for export).

---

## 5. Function inventory

93 top-level functions in `commonGUIs\xplorefinder.m`. Grouped by job.

**Lifecycle** — `xplorefinder`, `xplorefinder_OpeningFcn`, `xplorefinder_OutputFcn`

**Loading and per-channel UI**
`pushbutton1_Callback` (~97) — the file-open path, ~375 lines: extension
dispatch, timestamp alignment, per-channel control construction.
`createfilemenu` (~472) builds one channel's control strip.
`insertnewfile`, `removefileo`, `btaddfile_Callback`, `btremovefile_Callback`,
`duplicatecallback`.

**Rendering** — `update_graph` (~1279), `eegcorrelation` (~1876),
`Csdview` (~3665), `updatesliderstep`

**Analyse controls** — `tboutonfftcallback` (checkbox),
`popmenunlyztypecallback` (mode + setup dialogs), `txtminfcallback`,
`txtmaxfcallback`

**Navigation and zoom** — `SlidTime_Callback`, `pushbutton_uprange_Callback`,
`pushbutton_downrange_Callback`, `editbegintime_Callback`, `editrange_Callback`,
`zoomaxecallback`, `unzoomaxecallback`, `reducaxecallback`, `biggeraxecallback`,
`btzoomYncs_Callback`, `btunzoomYncs_Callback`, `pushbtprevgraphctrl_Callback`,
`pushbtnextgraphctrl_Callback`, `AxeButtonDownFcn`

**Filtering** — `editHighPass_Callback`, `editlow_Callback`,
`popupfiltertype_Callback`, `tg_notch_Callback`, `individualfiltercallback`,
`checkboxinvertEEG_Callback`, `btstd_Callback`

**Time markers and range selection**
`pushbuttonAddmark_Callback`, `updatelineTS`, `clicklinecallback`,
`pushbuttondelline_Callback`, `pushbuttonimportts_Callback`,
`pushbuttonexportts_Callback`, `pushbtcreatewindow_Callback`,
`startwindowdrag`/`draggingwin`/`updatewinTS`/`stopdragwin`,
`startwindowdragrange`/`draggingwinrange`/`updatewinTSrange`/`stopdragwinrange`,
`updaterange`, `updatetxtrangeinfo`, `popupmenurangeaction_Callback`,
`pushbuttondelrange_Callback`

**Event detection and export**
`localminact_Callback`, `showsearchmin` (~2799), `updateminimafinder`,
`notcloserth_Callback`, `morethan_Callback`, `checkboxfmin_Callback`,
`checkboxfmax_Callback`, `bttrim_Callback`, `extractspyke` (~3338),
`exportspyke_Callback` (~2913, ~400 lines — writes `.ntt`/`.nse`/`.nst`/`.mat`/`.xls`,
or hands off to `spikeSelecter`)

**Spike clusters** — `changeclustcallback`, `changeclustnamecallback`,
`tboxmarkclustcallback`, `nttplotTranversalmark`, `drawclustmark`,
`prevmarkcallback`, `nextmarkcallback`

**Video** — `tboutonstreamvideoallback`, `playvideocallback`

**Saving** — `pushbtsavegraph_Callback` (~3413), `pushbuttonsaveall_Callback`

`*_CreateFcn` callbacks are GUIDE boilerplate and are not listed.

---

## 6. Findings

Ordered by how likely they are to bite. All verified against the source.

**A regression in the current version — a lost return value.**
`pushbuttonAddmark_Callback` line 2168:

```matlab
spikeData = updatelineTS(Data,id);      % should be: Data = ...
guidata(gcbf,Data)                      % saves the pre-call Data
```

`spikeData` is assigned nowhere else in the file. `updatelineTS` fills
`Data.lineTS(id).line(i)` with the handles of the marker lines it draws; those
handles are discarded, and the `Data` written back still has `line` empty.

The line is still drawn and still clickable — `updatelineTS` sets its
`ButtonDownFcn` — so clicking a just-added marker enters `clicklinecallback`,
which does `set(Data.lineTS(id).line(i),'selected','on')` on an empty array and
errors on the index. The next full `update_graph` re-runs `updatelineTS` through
a path that *does* keep its result, so the marker heals on the next redraw.
Reproduce: add a mark, click it before touching anything else.

All three older copies have `Data = updatelineTS(Data,id)`. This line and the
reader-class swap are the *only* differences between the current version and
`_tryfix`, which suggests it was a slip during that edit. Fix: restore `Data =`.

**`mmread` is missing.** `.mpg` loading stores a sync offset fine, but
`playvideocallback` calls `mmread`, which is nowhere in the tree. Video playback
errors out. The `.mpg` path is the newest feature and the least reachable.

**`EraseMode` was removed from MATLAB in R2014b.** Set in `updatelineTS`,
`showsearchmin`, and the window-drag helpers. Harmless on the 2015-era MATLAB
this was written for; on a modern release `set(...,'EraseMode','xor')` throws.
This is the first thing to hit if the code is moved to a current MATLAB.

**Toolbox dependencies are unguarded.** `corr2` (modes 4 and 7) needs the Image
Processing Toolbox; `pwelch`, `cheby2`, `filtfilt`, `iirnotch`, `spectrogram`
need Signal Processing. There is no `license`/`exist` check, so a missing
toolbox surfaces as an undefined-function error mid-redraw.

**`Data.file(i)` is a value-class array assigned per element.** `Cscfile2_PP` is
a value class, so `Data.file(i) = Data.file(i).setstart(t)` copies the whole
object each time — including `.Samples`. With many channels at a wide window
this is the main cost in `update_graph`, alongside the ~98% STFT frame overlap
the Analyse defaults ask for.

**`removefileo` and `duplicatecallback` renumber `Data.file` in place** while
`Data.ctrlsig(i)` callbacks capture `i` by value at construction time
(`{@zoomaxecallback,i}`). Adding and removing channels in the wrong order can
therefore point a control at the wrong channel. Worth knowing before editing
that code.

**Dead code carried forward.** `xplorefinder.m` contains substantial
commented-out work — Hilbert phase of the mode-6 ridge, a NaN-and-reinterp pass
for weak frames, `plotyy` variants, several waveform baseline-correction schemes,
an unsegmented `coherencyc` call. Preserved in `Analyse\gui\xplorefinder.m`, and
each `core/` function's help points at the block it came from.

---

## 7. Dependencies

**Runtime, outside the two main folders**

| Function | Location | Used for |
|---|---|---|
| `spStft` | `xplorer\` | STFT engine (modes 1, 6, 7) |
| `subaxis` | `xplorer\` | channel-stack layout |
| `parseArgs` | `xplorer\` | `subaxis` argument parsing |
| `LocalMinima` | `xplorer\` | event detection |
| `Cscfile2_PP` | `xplorer\` | `.ncs` reader |
| `Read_nvt_Automatic` | `xplorer\` | `.nvt` tracking |
| `spikeSelecter`, `triggersigs` | `xplorer\` | export GUIs (`.fig` + `.m`) |
| `write_ntt`, `write_se`, `write_nst` | `xplorer\` | Neuralynx spike export |
| `read_ntt`, `read_Se`, `read_nev`, `read_biosig` | `OurMfiles\FileHandling\` | spike/event/Biosig readers |
| `mtspecgramc`, `coherencysegc` | `OurMfiles\chronux\` | multitaper modes 4, 5, 8 |
| `CSDPP2` | `OurMfiles\Rustem\` | CSD |
| `CSD` | `OurMfiles\Jeremy\New_CSD\` | CSD (alternate) |
| `FixPosData0` | `OurMfiles\PlaceCellAnal\` | tracking cleanup |
| `Speed_MtxEZ` | `OurMfiles\VideoProcessing\` | speed from tracking |
| `mmread` | **missing** | `.mpg` playback |

Only 14 of chronux's 374 files are actually reachable from Xplorefinder:
`mtspecgramc`, `mtspectrumc`, `mtfftc`, `coherencyc`, `coherencysegc`,
`cohgramc`, `coherr`, `specerr`, `createdatamatc`, `dpsschk`, `getfgrid`,
`getparams`, `change_row_to_column`, `check_consistency`. All 14 are vendored
into `Analyse\vendor\chronux_spectral\`, so the Analyse code needs no chronux
install.

**Duplicate copies.** `chronux` exists four times over
(`OurMfiles\chronux`, `OurMfiles\Jeremy\Leutgeb_Autocorr`, `matlabProgs\chronux`,
`matlabProgs\Mitraold`), `LocalMinima` four times, and most `FileHandling`
readers twice (`OurMfiles\` and `matlabProgs\`). Which one loads depends on path
order. `matlabProgs\` looks like an older snapshot of `OurMfiles\`; prefer
`OurMfiles\`.

---

## 8. The surrounding `xplorer\` toolbox

`xplorer\` is a working directory, not a packaged application: Xplorefinder's
helpers sit next to several independent GUIs and analysis scripts.

**GUIs** — `spikeSelecter` (manual spike/cluster curation, called from
Xplorefinder's export), `triggersigs` (waveform trim/align, called from the
Trim button), `RasterCellsonline` (live raster), `abfxplorer\abfspikedetect`
(Axon `.abf` spike detection), `analyzeGui\PlaceCellsNlyz` (place-field
analysis), `brainwavecompare` (see below).

**`brainwavecompare\`** is the other spectral application, and the closest
relative of the Analyse code — batch two-channel comparison over behavioural
zones. `compareEEG` builds the same `params.tapers=[3 5]` chronux struct and
calls `cohgramc` for a time-resolved coherogram, with artefact rejection
(`removeartefact_spectrum`, `removeartefac_satandshockjeremy_spectrum`), band
extraction (`extractBand_corrmap`, `diff_corrmap`), and theta/gamma segment
selection (`theta_gammaselector`, `theta_gammaselector_harmonics`,
`bestthetaeeg`). If you need coherency *over time* rather than the single
spectrum mode 8 gives, this is where it already exists.

**File surgery** — `merge_csc`, `merge_ntt`, `mergefilecsc`, `mergefilentt`,
`unmergentt`, `write_csc`, `write_ntt`, `write_se`, `write_nst`

**Spike analysis** — `spikenlyz\` (per-cluster raster and waveform plots driven
from Excel exports, `RMSnormalized`), `symmetryunitsfeature\` (waveform
asymmetry metrics for cell-type classification: `calcsymvalue`,
`unitsymmetryvalue`, `getsymvaluesophie`)

**Also** — `netcom_soft\` (live Neuralynx NetCom acquisition, online place fields,
closed-loop opto stimulation), `models\` (CA3/CA1 network simulation and result
plotting), `spykeclusteringkohonet` (Kohonen-net spike clustering)

---

## 9. Sibling GUIs in `commonGUIs\`

Xplorefinder's neighbours — earlier and per-person variants of the same
browse-EEG-and-spikes idea, all GUIDE-built with a `.fig`. Xplorefinder is the
most developed and the only one still being modified (2022; the rest are frozen
at 2015).

`ExploreEEG` · `AbfEEG` (Axon `.abf`) · `GregEEG` / `ShpsEEG` / `SharpsEEG`
(sharp-wave detection) · `SeanGUI` (85 KB, the largest) · `SoniaGUI` ·
`ClusterSharps` / `ClusterSharpsNLX` · `AlignSharps` / `AlignSharpsNLX` ·
`CSD2Spik` / `CSDNLX` · `PlaceCells` / `PlaceCellsUFF`

`NLX` suffixes are Neuralynx ports of a version that read another format.
`AbfEEG.asv`, `ExploreEEG.asv`, `ShpsEEG.asv` are MATLAB editor autosaves, not
source. `._*` files are macOS resource forks and can be deleted.

---

## 10. This folder

```
CATALOGUE.md          this document
Analyse/              the extracted Analyse code — see Analyse/README.md
  xf_setpath.m        add core/ io/ vendor/ to the path
  xf_demo.m           run all eight modes on one .ncs file
  xf_selftest.m       run everything on synthetic data, no files needed
  core/               15 functions: the Analyse math, GUI-free
  io/                 Cscfile2_PP + the Neuralynx readers
  vendor/misc/        spStft, subaxis, parseArgs, LocalMinima, CSDPP2
  vendor/chronux_spectral/   the 14 chronux files actually reached
  gui/                reference copy of xplorefinder.m + .fig + cursor .mat
```

Nothing in `C:\Users\Z390\Documents\matlab` was modified — everything here is a
copy or an extraction.

Verified on MATLAB R2023b: `checkcode` clean across `core/`, and `xf_selftest`
exercises all eight modes plus the detector, waveform cutter, CSD and plotting.
