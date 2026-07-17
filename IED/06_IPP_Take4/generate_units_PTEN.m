function generate_units_PTEN(varargin)
%% generate_units_PTEN  Multiunit (300-6000 Hz) laminar view per PTEN session
%
% Windows/.mat port of generate_units (originally raw-Neuralynx / KCNT1 cluster).
% For each PTEN session folder under 'InputParent', loads the 32 even-channel
% (CSC 2..64) traces from that session's data .mat over a 60 s window,
% band-passes 300-6000 Hz, and renders a stacked multi-channel trace image into
% the session folder -- for unit / laminar labelling.
%
% DIFFERENCES vs the original:
%   - Reads from the pre-converted data .mat (matfile 'd', 'sfx', 'kept_channels')
%     instead of CSC*.n* via Nlx2MatCSC. 'd' rows are already even channels
%     2:2:64 in microvolts (kept_channels), so no ADBitVolts step.
%   - Data is used as-is (invertPolarity default FALSE; the .mat is already the
%     processed uV signal that IPP_Combined_Pipeline_v2 consumes). Set
%     'invertPolarity',true to flip if you want the raw-CSC display convention.
%
% Long broadband traces are drawn as a per-pixel min/max ENVELOPE.
%
% USAGE:
%   generate_units_PTEN                                   % all sessions in Take 3
%   generate_units_PTEN('Sessions', {'PTEN_M13_pten_m13s2aug1'})
%   generate_units_PTEN('OutputParent', "...\Take 4\units")   % redirect output

P = inputParser;
P.addParameter('InputParent', 'C:\Users\Z390\Desktop\IED DATA\Take 3', @(s)ischar(s)||isstring(s));
P.addParameter('OutputParent', '', @(s)ischar(s)||isstring(s));  % '' = write into each session folder
P.addParameter('Sessions', {}, @iscell);
P.addParameter('Channels', 2:2:64, @(v)isnumeric(v)&&~isempty(v));  % physical channels
P.addParameter('highPassHz', 300,  @(x)isfinite(x)&&x>0);
P.addParameter('lowPassHz',  6000, @(x)isfinite(x)&&x>0);
P.addParameter('windowSec',  60,   @(x)isfinite(x)&&x>0);
P.addParameter('startSec',   [],   @(x)isempty(x)||(isscalar(x)&&x>=0));  % [] = centre of recording
P.addParameter('invertPolarity', false, @(x)islogical(x)||ismember(x,[0 1]));
P.addParameter('scaleToMicroV', 1, @(x)isfinite(x)&&x>0);
P.addParameter('yLimUV', 200, @(x)isfinite(x)&&x>0);   % +/- per-channel display scale
P.addParameter('dispBins', 3000, @(x)isscalar(x)&&x>=200);
P.addParameter('dpi', 200, @(x)isfinite(x)&&x>=72);
P.parse(varargin{:});
A = P.Results;

inParent = char(A.InputParent);
if ~isfolder(inParent), error('InputParent not found: %s', inParent); end
outParent = char(string(A.OutputParent));

% ---- discover sessions (subfolders with a non-ets data .mat) ----
if isempty(A.Sessions)
    dd = dir(inParent); dd = dd([dd.isdir] & ~ismember({dd.name},{'.','..'}));
    sessions = {};
    for k = 1:numel(dd)
        nm = dd(k).name;
        if isempty(regexpi(nm, 'm\d+s\d+', 'once')), continue; end  % looks like a session
        mats = dir(fullfile(inParent, nm, '*.mat'));
        mats = mats(~startsWith({mats.name}, 'ets.mat', 'IgnoreCase', true));
        if ~isempty(mats), sessions{end+1} = nm; end %#ok<AGROW>
    end
    sessions = sort(sessions);
else
    sessions = cellfun(@char, A.Sessions, 'UniformOutput', false);
end

fprintf('\n===== generate_units_PTEN =====\nSessions: %d | band %g-%g Hz | %g s window\n', ...
    numel(sessions), A.highPassHz, A.lowPassHz, A.windowSec);

for si = 1:numel(sessions)
    s = sessions{si};
    fprintf('\n[%d/%d] %s\n', si, numel(sessions), s);
    try
        one(s);
    catch ME
        fprintf('  [ERROR] %s: %s\n', s, ME.message);
        if ~isempty(ME.stack), fprintf('     at %s (line %d)\n', ME.stack(1).name, ME.stack(1).line); end
    end
end
fprintf('\n===== generate_units_PTEN DONE =====\n');

    function one(sess)
        inDir = fullfile(inParent, sess);
        if ~isfolder(inDir), fprintf('  [SKIP] no session folder.\n'); return; end
        mats = dir(fullfile(inDir, '*.mat'));
        mats = mats(~startsWith({mats.name}, 'ets.mat', 'IgnoreCase', true));
        if isempty(mats), fprintf('  [SKIP] no data .mat.\n'); return; end
        dataMat = fullfile(mats(1).folder, mats(1).name);

        if isempty(outParent), outDir = inDir; else, outDir = fullfile(outParent, sess); end
        if ~exist(outDir,'dir'), mkdir(outDir); end

        mf = matfile(dataMat);
        try sfx = mf.sfx; catch, sfx = 30000; end
        sfx = double(sfx); if ~(isfinite(sfx)&&sfx>0), sfx = 30000; end
        nRowsAll = size(mf,'d',1);
        nSampAll = size(mf,'d',2);
        try kc = double(mf.kept_channels); kc = kc(:).'; catch, kc = []; end
        if isempty(kc), kc = 1:nRowsAll; end   % fall back: row == channel

        % map requested physical channels -> data rows
        [tf, rowIdx] = ismember(A.Channels, kc);
        chs = A.Channels(tf); rowIdx = rowIdx(tf);
        if isempty(chs), error('none of the requested channels present in kept_channels'); end
        nCh = numel(chs);

        durSec = nSampAll / sfx;
        if isempty(A.startSec), startSec = max(0, (durSec - A.windowSec)/2); else, startSec = A.startSec; end
        startSec = min(startSec, max(0, durSec - A.windowSec));
        s0 = max(1, round(startSec*sfx) + 1);
        nWin = min(round(A.windowSec*sfx) + 1, nSampAll - s0 + 1);
        s1 = s0 + nWin - 1;
        tsec = (0:nWin-1)/sfx;
        fprintf('  %d ch | Fs=%g | window %.0f-%.0f s of %.0f s\n', nCh, sfx, startSec, startSec+nWin/sfx, durSec);

        % read the window block once (columns contiguous in column-major matfile)
        D = double(mf.d(:, s0:s1));
        if logical(A.invertPolarity), D = -D; end
        D = D * A.scaleToMicroV;

        % band-pass 300-6000 Hz (zero-phase), built as SOS
        fhi = A.highPassHz/(sfx/2); flo = min(A.lowPassHz,(sfx/2)*0.99)/(sfx/2);
        [z,p,kk] = butter(4, [fhi flo], 'bandpass'); [sos,g] = zp2sos(z,p,kk);

        % figure sized in INCHES (DPI-independent); thin stacked rows
        rowIn = 0.32; figH_in = min(40, 1.0 + rowIn*nCh); figW_in = 16;
        f = figure('Color','w','Visible','off','Units','inches', ...
            'Position',[1 1 figW_in figH_in], 'InvertHardcopy','off');
        set(f,'PaperUnits','inches','PaperSize',[figW_in figH_in],'PaperPosition',[0 0 figW_in figH_in]);
        tl = tiledlayout(f, nCh, 1, 'TileSpacing','none', 'Padding','compact');

        for i = 1:nCh
            c  = chs(i);
            y  = D(rowIdx(i), :);
            yz = y; yz(~isfinite(yz)) = 0;
            yz = filtfilt(sos, g, yz);                         % 300-6000 Hz
            [xb, yb] = envMinMax(tsec, yz, A.dispBins);

            ax = nexttile(tl);
            plot(ax, xb, yb, '-', 'Color',[0 0.2 0.85], 'LineWidth',0.2);
            xlim(ax,[0 tsec(end)]); ylim(ax,[-A.yLimUV A.yLimUV]);
            set(ax,'YTick',[],'TickDir','out','FontSize',7,'Box','on','Layer','top');
            if mod(i,2)==1, ax.YAxisLocation = 'left'; else, ax.YAxisLocation = 'right'; end
            ylabel(ax, sprintf('CSC%d', c), 'Rotation',0, 'FontSize',7, ...
                'HorizontalAlignment', tern(mod(i,2)==1,'right','left'), 'VerticalAlignment','middle');
            if i < nCh, ax.XTickLabel = []; else, xlabel(ax,'Time (s)','FontSize',9,'FontWeight','bold'); end
        end
        title(tl, sprintf('%s   |   Units %g-%g Hz   |   %g s  (t = %.0f-%.0f s)   |   \\pm%g \\muV/ch', ...
            strrep(sess,'_','\_'), A.highPassHz, A.lowPassHz, A.windowSec, ...
            startSec, startSec+nWin/sfx, A.yLimUV), 'FontSize',12, 'FontWeight','bold');

        outPng = fullfile(outDir, sprintf('%s_units_%g_%gHz_%gs.png', sess, A.highPassHz, A.lowPassHz, A.windowSec));
        exportgraphics(f, outPng, 'Resolution', A.dpi);
        close(f);
        fprintf('  Saved %s\n', outPng);
    end
end

% ----------------------------------------------------------------------
function [xb, yb] = envMinMax(t, y, nbins)
% per-bin min/max envelope rendered as a zigzag line (downsampled waveform view)
N = numel(y); bs = max(1, floor(N/nbins)); m = floor(N/bs);
Y = reshape(y(1:m*bs), bs, m);
mn = min(Y,[],1); mx = max(Y,[],1);
tb = t(round(((1:m)-0.5)*bs));
xb = repelem(tb, 2);
yb = reshape([mn; mx], 1, []);
end

function s = tern(c,a,b), if c, s=a; else, s=b; end, end
