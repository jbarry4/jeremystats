function R = xf_analyse(mode, Samples, SF, varargin)
%XF_ANALYSE  Run one xplorefinder "Analyse" mode and return the result.
%
%   R = xf_analyse(MODE, SAMPLES, SF)
%   R = xf_analyse(MODE, SAMPLES, SF, 'Name', Value, ...)
%
%   MODE is the popup index (1..8) or its name, matching the GUI's
%   "Analyse" dropdown exactly:
%
%     1  'Spectogram'             STFT spectrogram                 xf_spectrogram
%     2  'Spectrum'               Welch PSD                        xf_spectrum
%     3  'Diff Spectrum'          Welch PSD of diff(signal)        xf_spectrum
%     4  'Correlation...'         multitaper specgram difference   xf_specgramDiff
%     5  'chronus spectogram'     multitaper spectrogram           xf_chronuxSpecgram
%     6  'max freq in time'       dominant-frequency ridge         xf_maxFreqInTime
%     7  'Correlation classic...' STFT specgram difference         xf_specgramDiff
%     8  'coherency...'           segmented multitaper coherency   xf_coherency
%
%   (The dropdown labels are reproduced verbatim, typos included, so they
%   can be matched against the GUI. 'chronus' is 'chronux'; 'Spectogram' is
%   'Spectrogram'.)
%
%   Options
%     'MinF'          lower edge of the displayed band, Hz      (default 0)
%     'MaxF'          upper edge of the displayed band, Hz      (default 200)
%     'FrameLength'   STFT frame length, ms; 0 = auto           (default 0)
%     'FrameOverlap'  STFT frame overlap, ms; 0 = auto          (default 0)
%     'Samples2'      second channel, required for modes 4, 7, 8
%     'SegLength'     coherency segment length, s (mode 8)      (default 2)
%     'Start'         recording time of SAMPLES(1), s           (default 0)
%
%   The MinF/MaxF/FrameLength/FrameOverlap defaults are the GUI's own
%   initial values from Data.xtraFileData (nlyzminf=0, nlyzmaxf=200,
%   frame_length=0, frame_overlap=0).
%
%   R is a struct describing the result.  R.kind tells you which shape it
%   is, so XF_PLOTANALYSE can render it without re-deciding:
%
%     R.kind = 'image'   spectrogram-like.  R.Z (freq x time), R.F, R.T
%     R.kind = 'curve'   spectrum-like.     R.X, R.Y
%     R.kind = 'ridge'   mode 6.            R.T, R.P, R.Fraw, R.Mag
%     R.kind = 'cohere'  mode 8.            R.F, R.C, R.Phi, R.PhiStd
%
%   Every R also carries: R.mode, R.name, R.minf, R.maxf, R.start, and for
%   the difference modes R.corrCoef.
%
%   R.T is in seconds relative to the start of SAMPLES.  Add R.start to put
%   it on the recording clock -- that is exactly what the GUI does when it
%   plots T + Data.start.  XF_PLOTANALYSE does it for you.
%
%   Example
%     f  = Cscfile2_PP('CSC1.ncs');
%     f  = f.setstart(120); f = f.setrange(10); f = f.readdata();
%     R  = xf_analyse('Spectogram', f.Samples, f.currentSF, ...
%                     'MaxF', 100, 'Start', 120);
%     xf_plotAnalyse(R);
%
%   See also XF_PLOTANALYSE, XF_SPECTROGRAM, XF_SPECTRUM, XF_COHERENCY.

names = {'Spectogram','Spectrum','Diff Spectrum','Correlation...', ...
         'chronus spectogram','max freq in time','Correlation classic...', ...
         'coherency...'};

if ischar(mode)
    idx = find(strcmpi(names, mode));
    if isempty(idx)
        error('xf_analyse:badMode', ...
              'Unknown mode ''%s''. Use 1..8 or one of: %s.', ...
              mode, strjoin(names, ', '));
    end
    mode = idx;
end
if ~isscalar(mode) || mode < 1 || mode > 8 || mode ~= fix(mode)
    error('xf_analyse:badMode', 'MODE must be an integer 1..8 or a mode name.');
end

opt = struct('MinF', 0, 'MaxF', 200, 'FrameLength', 0, 'FrameOverlap', 0, ...
             'Samples2', [], 'SegLength', 2, 'Start', 0);
if mod(numel(varargin), 2)
    error('xf_analyse:badArgs', 'Options must be Name/Value pairs.');
end
for k = 1:2:numel(varargin)
    nm = varargin{k};
    if ~isfield(opt, nm)
        error('xf_analyse:badOption', 'Unknown option ''%s''.', nm);
    end
    opt.(nm) = varargin{k+1};
end

needsTwo = ismember(mode, [4 7 8]);
if needsTwo && isempty(opt.Samples2)
    error('xf_analyse:needSamples2', ...
          'Mode %d (%s) compares two channels -- pass ''Samples2''.', ...
          mode, names{mode});
end

R = struct('mode', mode, 'name', names{mode}, ...
           'minf', opt.MinF, 'maxf', opt.MaxF, 'start', opt.Start);

switch mode
    case 1
        [Z, F, T] = xf_spectrogram(Samples, SF, opt.MinF, opt.MaxF, ...
                                   opt.FrameLength, opt.FrameOverlap);
        R.kind = 'image'; R.Z = Z; R.F = F; R.T = T;
        R.zlabel = 'Power (dB, 30log10)';

    case {2, 3}
        [Y, f] = xf_spectrum(Samples, SF, opt.MinF, opt.MaxF, mode == 3);
        R.kind = 'curve'; R.X = f; R.Y = Y;
        R.xlabel = 'Frequency (Hz)'; R.ylabel = '|Y(f)|';

    case 5
        [Z, F, T] = xf_chronuxSpecgram(Samples, SF, opt.MinF, opt.MaxF, ...
                                       opt.FrameLength, opt.FrameOverlap);
        R.kind = 'image'; R.Z = Z.'; R.F = F; R.T = T;   % -> freq x time
        R.zlabel = 'Power (dB, 30log10)';

    case 6
        [p, t, fRaw, maxs] = xf_maxFreqInTime(Samples, SF, opt.MinF, opt.MaxF, ...
                                              opt.FrameLength, opt.FrameOverlap);
        R.kind = 'ridge'; R.T = t; R.P = p; R.Fraw = fRaw; R.Mag = maxs;

    case {4, 7}
        if mode == 4, meth = 'chronux'; else, meth = 'stft'; end
        [Z, cc, F, T] = xf_specgramDiff(Samples, opt.Samples2, SF, ...
                                        opt.MinF, opt.MaxF, meth, ...
                                        opt.FrameLength, opt.FrameOverlap);
        R.kind = 'image'; R.Z = Z; R.F = F; R.T = T; R.corrCoef = cc;
        R.zlabel = sprintf('|dB diff|  (corr2 = %.4f)', cc);

    case 8
        [C, phi, f, phistd, confC, Cerr] = ...
            xf_coherency(Samples, opt.Samples2, SF, opt.MinF, opt.MaxF, opt.SegLength);
        R.kind = 'cohere'; R.F = f; R.C = C; R.Phi = phi; R.PhiStd = phistd;
        R.ConfC = confC; R.Cerr = Cerr;
end
