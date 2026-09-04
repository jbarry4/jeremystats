function [window, res] = xf_pwelchWindow(nSamples, SF, minf, maxf)
%XF_PWELCHWINDOW  Window length and frequency resolution for the spectrum modes.
%
%   [WINDOW, RES] = xf_pwelchWindow(NSAMPLES, SF, MINF, MAXF)
%
%   Reproduces the window-sizing heuristic used by xplorefinder for
%   'Spectrum' and 'Diff Spectrum' (update_graph, case {2,3}; the same block
%   is duplicated in popupmenurangeaction_Callback, case {3,4}).
%
%   The idea: scale the Welch window to the requested top frequency so the
%   spectrum stays smooth when you zoom the frequency axis, but never let the
%   window grow past 1/20 of the displayed segment.
%
%   RES is the target bin width in Hz -- (MAXF-MINF)/400, i.e. always ~400
%   points across the displayed band -- and is turned into NFFT by the
%   caller as round(SF/RES).
%
%   See also XF_SPECTRUM, PWELCH.

ratiomaxf = SF / maxf;

if ratiomaxf*100 > round(nSamples/20)
    a = floor(nSamples / ratiomaxf);
    if a == 0
        window = nSamples;
    elseif a > 100
        window = ratiomaxf * 100;
    else
        window = ratiomaxf * a;
    end
else
    window = nSamples / 20;
end
window = round(window);

res = (maxf - minf) / 400;
