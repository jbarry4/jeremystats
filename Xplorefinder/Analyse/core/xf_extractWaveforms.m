function spykes = xf_extractWaveforms(TS, files, begin, range, nbfileneed)
%XF_EXTRACTWAVEFORMS  Cut fixed-length waveforms around event times.
%
%   SPYKES = xf_extractWaveforms(TS, FILES, BEGIN, RANGE, NBFILENEED)
%
%   TS          event times in SECONDS relative to the start of the samples
%               currently loaded in FILES (i.e. XF_FINDEVENTS output minus
%               Data.start -- inside the GUI both are on the same clock
%               because the files hold exactly the displayed window)
%   FILES       array of Cscfile2_PP objects with .Samples and .currentSF
%               already read
%   BEGIN       offset of the cut start relative to the event, in SAMPLES.
%               Negative means "start before the event".  The GUI passes
%               Data.trimspyke here and -Data.trimspyke to write_ntt.
%   RANGE       number of samples per channel per waveform
%   NBFILENEED  number of channels to emit.  If greater than numel(FILES),
%               the extra channels are filled with zeros -- this is how the
%               GUI pads a 1- or 2-channel detection up to the 4 channels
%               that Neuralynx .ntt requires ("Add flat signals").
%
%   SPYKES is (RANGE*NBFILENEED) x numel(TS): each COLUMN is one event, with
%   the channels concatenated end to end down the column.  That is the
%   layout write_ntt / write_se / write_nst expect.
%
%   Events whose window falls off either end of the loaded samples are
%   skipped with a message on the command window and left as zeros -- they
%   still occupy a column, so SPYKES stays aligned with TS.
%
%   Extracted from xplorefinder.m extractspyke.  The original body carries
%   several commented-out baseline-correction variants (subtract mean,
%   subtract median, running median subtraction); none is active, so the
%   waveforms come out with their DC offset intact.  See
%   gui/xplorefinder.m (~line 3338) if you want one of them.
%
%   See also XF_FINDEVENTS, WRITE_NTT, WRITE_SE, WRITE_NST.

if nargin < 5 || isempty(nbfileneed)
    nbfileneed = numel(files);
end

nEvent = numel(TS);
spykes = zeros(nEvent, range * nbfileneed);

for i = 1:nEvent
    filenum = 1;
    for j = 1:range:range*nbfileneed
        if filenum <= numel(files)
            SF   = files(filenum).currentSF;
            from = round(TS(i) * SF) + begin + 1;
            to   = round(TS(i) * SF) + begin + range;
            try
                spykes(i, j:j+range-1) = files(filenum).Samples(from:to);
            catch
                disp(['Error during extraction of the spyke num ' num2str(i) ...
                      ' Time : ' num2str(from) ' to ' num2str(to) ...
                      ' length of sample : ' num2str(numel(files(filenum).Samples)) ...
                      ' Start' num2str(files(filenum).start)]);
            end
        else
            spykes(i, j:j+range-1) = zeros(1, range);
        end
        filenum = filenum + 1;
    end
end

spykes = permute(spykes, [2 1]);        % -> samples x events
