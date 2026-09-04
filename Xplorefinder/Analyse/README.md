# Xplorefinder — Analyse code

Everything behind the **Analyse** checkbox in Xplorefinder, pulled out of the GUI
callbacks and made callable on its own, plus the dependencies it needs to run.

In `xplorefinder.m` this code lives inside `update_graph` and `eegcorrelation`,
reads its inputs out of `Data.xtraFileData(i)` / `get(Data.ctrlsig(i).nlyztype,'value')`,
and writes straight to a subplot. None of it can be called without a live figure.
The `core/` functions here are the same math with the GUI plumbing removed.

## Run it

```matlab
cd Xplorefinder/Analyse
xf_setpath                              % once per session

f = Cscfile2_PP('CSC1.ncs');            % Neuralynx CSC reader
f = f.setstart(120);                    % seconds
f = f.setrange(10);                     % seconds
f = f.readdata();

R = xf_analyse('Spectogram', f.Samples, f.currentSF, 'MaxF', 100, 'Start', 120);
xf_plotAnalyse(R);
```

`xf_demo('CSC1.ncs', 120, 5)` runs all eight modes on one file.

`xf_selftest` needs no data at all — it synthesises an 8 Hz theta / 45 Hz gamma
LFP, runs every function against it, and prints results with the expected values
annotated. Run it after moving this folder or after a MATLAB upgrade.

## The eight modes

The dropdown next to the Analyse checkbox. Labels are reproduced verbatim,
typos included, so they match the GUI on screen.

| # | Dropdown label | Engine | Function |
|---|---|---|---|
| 1 | `Spectogram` | hamming STFT | `xf_spectrogram` |
| 2 | `Spectrum` | Welch PSD | `xf_spectrum` |
| 3 | `Diff Spectrum` | Welch PSD of `diff(x)` | `xf_spectrum(...,true)` |
| 4 | `Correlation...` | multitaper specgram difference | `xf_specgramDiff(...,'chronux')` |
| 5 | `chronus spectogram` | multitaper spectrogram | `xf_chronuxSpecgram` |
| 6 | `max freq in time` | STFT dominant-frequency ridge | `xf_maxFreqInTime` |
| 7 | `Correlation classic...` | STFT specgram difference | `xf_specgramDiff(...,'stft')` |
| 8 | `coherency...` | segmented multitaper coherency | `xf_coherency` |

Modes 4, 7 and 8 need a second channel. In the GUI, picking one of them pops a
`listdlg` and stores the choice in `Data.xtraFileData(i).correlationeeg`; here you
pass `'Samples2'`.

Modes 1, 5 and 6 also read the frame length/overlap that mode 1's setup dialog
writes into `frame_length` / `frame_overlap`. Zero means "auto" — see
`xf_frameDefaults`.

## Layout

```
xf_setpath.m              add core/ io/ vendor/ to the path
xf_demo.m                 run all eight modes on one .ncs file
xf_selftest.m             run everything on synthetic data, no files needed

core/
  xf_analyse.m            dispatcher, modes 1-8 -> result struct
  xf_plotAnalyse.m        draw a result struct the way the GUI draws it
  xf_spectrogram.m        mode 1
  xf_spectrum.m           modes 2, 3
  xf_chronuxSpecgram.m    mode 5
  xf_maxFreqInTime.m      mode 6
  xf_specgramDiff.m       modes 4, 7
  xf_coherency.m          mode 8
  xf_frameDefaults.m      frame length/overlap resolution (the 0 = auto rule)
  xf_pwelchWindow.m       Welch window sizing heuristic for modes 2, 3
  xf_chronuxParams.m      the params struct the chronux modes use
  xf_band.m               frequency-band mask
  xf_csd.m                current source density (the live CSD window)
  xf_findEvents.m         LocalMinima threshold/peak detector
  xf_extractWaveforms.m   cut fixed-length waveforms around event times

io/
  Cscfile2_PP.m           Neuralynx .ncs reader class, current version
  Cscfile2.m              previous version, kept for reference
  read_ntt.m read_Se.m read_nev.m read_biosig.m Read_nvt_Automatic.m

vendor/
  misc/     spStft.m subaxis.m parseArgs.m LocalMinima.m CSDPP2.m
  chronux_spectral/   the 14 chronux files the Analyse modes reach

gui/
  xplorefinder.m          reference copy of the source (newest version)
  xplorefinder.fig        the GUIDE layout, which the newest copy lacks
```

`gui/` is **not** added to the path by `xf_setpath` — it would shadow whichever
`xplorefinder` you actually run. It is there so you can diff against the original.

## Things that will surprise you

These are all faithful to the GUI. They are reproduced, not fixed, so output
matches what Xplorefinder puts on screen. Each is also noted in the relevant
function's help text.

- **dB is `30*log10`**, not `20*log10` (amplitude) or `10*log10` (power). Every
  spectrogram mode uses it. Absolute dB values are not comparable to any other
  tool — only relative structure within one plot means anything.
- **The frame-overlap default is `frame_length/1.02`**, but mode 1's setup dialog
  tells you it is `frame_length/1.2`. The drawing code wins; the prompt is stale.
  Both defaults are ~98% overlap, which is very slow on long windows.
- **The "Correlation" modes are not correlations over time or frequency.** They
  draw `abs(SdB1-SdB2)` as an image and print a single global `corr2` scalar in
  the y-label. Mode 4 and mode 7 differ *only* in which spectrogram engine feeds
  that subtraction.
- **`corr2` needs the Image Processing Toolbox.** `corrcoef(A(:),B(:))` element
  (1,2) is the same number if you don't have it.
- **Mode 8 sets `params.err=[2 3]`.** chronux reads `err(2)` as a p-value, so 3 is
  out of range — treat the returned `confC` / `Cerr` as unreliable.
- **Mode 6's ridge is an argmax over the band**, so with the default band of
  0–200 Hz it pins to the 1/f low edge. Raise `MinF` above the DC roll-off for it
  to track anything real.
- **The min+max event detector runs a dead pass.** With both polarities selected
  the GUI searches directions `[-1 0]`; the `0` pass multiplies the signal by zero
  and searches a flat line. `xf_findEvents` skips it when it provably cannot
  match — same results, less work.
- **The CSD view feeds flat channels to the derivative.** It sizes its matrix by
  the total number of open files and indexes by global file index, so any open
  `.ntt`/`.nvt`/`.nev` leaves an all-zero column in the middle of the channel
  stack. `xf_csd` takes the matrix directly so you can pass only real channels.
- **CSD sign is inverted** relative to most published CSD figures — `CSDPP2` is
  "my version of CSD (no inversion)".
- **Mode 5 is drawn here with `imagesc`, not `pcolor`+`shading interp`.** Same
  data, slightly different picture. `xf_plotAnalyse` says how to get the GUI look.

## Where the originals are

| Piece | Original location |
|---|---|
| Modes 1, 2, 3, 5, 6 | `xplorefinder.m` `update_graph`, ~line 1279–1590 |
| Modes 4, 7, 8 | `xplorefinder.m` `eegcorrelation`, ~line 1876–1978 |
| Frame setup dialog | `popmenunlyztypecallback`, ~line 1151 |
| Band edit boxes | `txtminfcallback` / `txtmaxfcallback`, ~line 1132 |
| Analyse checkbox + dropdown | `createfilemenu`, ~line 557–570 |
| Spectrum over a selection | `popupmenurangeaction_Callback` case {3,4}, ~line 2553 |
| Event detector | `showsearchmin`, ~line 2799 |
| Waveform cutting | `extractspyke`, ~line 3338 |
| CSD view | `Csdview`, ~line 3665 |
| Saving the Analyse axes | `pushbtsavegraph_Callback`, ~line 3413 |

`popupmenurangeaction_Callback` case {3,4} is the same Welch spectrum as modes 2
and 3, applied to the dragged time selection instead of the whole window and
drawn into a new figure with one subplot per channel. It is not duplicated in
`core/` — call `xf_spectrum` on the sample range you want.
