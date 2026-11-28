param([string]$V4, [string]$Png, [string]$Out, [string]$Seed = "")
# Builds the deck until every text box is sized to its own text: build -> PowerPoint measures every text box -> build again
# with those measures, repeated until no text height changes (at most 4 rounds). Leaves $Out and $Out.measure.json.
$here = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
$meas = $Seed
for ($k = 1; $k -le 4; $k++) {
    if ($meas) { python "$here\build_v11.py" $V4 $Png $Out $meas | Out-Null } else { python "$here\build_v11.py" $V4 $Png $Out | Out-Null }
    $new = "$Out.measure$k.json"
    & "$PSScriptRoot\measure_text.ps1" -Deck $Out -Out $new | Out-Null
    if ($meas) {
        $same = python -c "import json,sys; a={r['id']:r['text_height'] for r in json.load(open(sys.argv[1],encoding='utf-8-sig'))}; b={r['id']:r['text_height'] for r in json.load(open(sys.argv[2],encoding='utf-8-sig'))}; print(all(abs(a[i]-b[i])<0.005 for i in b if i in a and i<85))" $meas $new
        if ($same -eq "True") { Copy-Item $new "$Out.measure.json" -Force; "converged after $k rounds"; python "$here\build_v11.py" $V4 $Png $Out $new; break }
    }
    $meas = $new
}
