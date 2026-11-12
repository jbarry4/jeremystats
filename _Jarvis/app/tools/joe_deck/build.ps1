param([string]$Plan)
# Builds a deck from plan.json through PowerPoint itself, so every Morph
# transition is PowerPoint's own. Every shape is named; a "!!" name is what
# Morph matches from one slide to the next. Reports any text that does not
# fit its box, then saves the deck and a PNG of every slide.
$ErrorActionPreference = 'Stop'
$P = Get-Content -Raw -Encoding UTF8 $Plan | ConvertFrom-Json

# ConvertFrom-Json gives a Decimal for 14.0, and PowerPoint cannot take one.
function F($x) { return [single][double]$x }
function RGB($c) { if ($null -eq $c) { return $null }; return [int]$c[0] + 256 * [int]$c[1] + 65536 * [int]$c[2] }

# PowerPoint's automation object IS the running PowerPoint when one is open
# (2026-10-23: a build quit it, with whatever the person had open). So a
# PowerPoint that was already running is left running; only ours is closed.
$wasRunning = [bool](Get-Process POWERPNT -ErrorAction SilentlyContinue)
$app = New-Object -ComObject PowerPoint.Application
$overflow = New-Object System.Collections.ArrayList
$pres = $null
try {
    $pres = $app.Presentations.Add(0)
    $pres.PageSetup.SlideWidth = (F $P.width)
    $pres.PageSetup.SlideHeight = (F $P.height)
    $i = 0
    foreach ($sd in $P.slides) {
        $i++
        $s = $pres.Slides.Add($i, 12)
        foreach ($sp in $sd.shapes) {
            switch ($sp.kind) {
                'picture' { $sh = $s.Shapes.AddPicture($sp.file, 0, -1, (F $sp.left), (F $sp.top), (F $sp.width), (F $sp.height)) }
                'text'    { $sh = $s.Shapes.AddTextbox(1, (F $sp.left), (F $sp.top), (F $sp.width), (F $sp.height)) }
                'snip'    { $sh = $s.Shapes.AddShape(157, (F $sp.left), (F $sp.top), (F $sp.width), (F $sp.height)) }
                default   { $sh = $s.Shapes.AddShape(1, (F $sp.left), (F $sp.top), (F $sp.width), (F $sp.height)) }
            }
            $sh.Name = $sp.name
            if ($sp.kind -eq 'snip') {
                $adj = $sh.Adjustments
                $adj.Item(1) = 0.0
                if ($null -ne $sp.snip) { $adj.Item(2) = (F $sp.snip) }
            }
            if ($sp.kind -ne 'picture' -and $sp.kind -ne 'text') {
                if ($null -ne $sp.fill) { $sh.Fill.Visible = -1; $sh.Fill.Solid(); $sh.Fill.ForeColor.RGB = (RGB $sp.fill); $sh.Fill.Transparency = (F $sp.fill_t) }
                else { $sh.Fill.Visible = 0 }
                $sh.Shadow.Visible = 0
            }
            if ($null -ne $sp.line) { $sh.Line.Visible = -1; $sh.Line.ForeColor.RGB = (RGB $sp.line); $sh.Line.Weight = (F $sp.line_w) }
            elseif ($sp.kind -ne 'picture') { $sh.Line.Visible = 0 }
            if ($null -ne $sp.text) {
                $tf = $sh.TextFrame
                $tf.WordWrap = -1
                $tf.AutoSize = 0
                # A new text box shrinks itself to one line the moment it is made;
                # with auto-fit now off, put back the size the plan asked for.
                $sh.Top = (F $sp.top); $sh.Height = (F $sp.height)
                $tf.MarginLeft = (F $sp.margin[0]); $tf.MarginTop = (F $sp.margin[1]); $tf.MarginRight = (F $sp.margin[2]); $tf.MarginBottom = (F $sp.margin[3])
                $tf.VerticalAnchor = @{ t = 1; m = 3; b = 4 }[$sp.anchor]
                $tr = $tf.TextRange
                $tr.Text = ($sp.text -replace "`n", "`r")
                $tr.Font.Name = $sp.font
                $tr.Font.Size = (F $sp.size)
                $tr.Font.Bold = $(if ($sp.bold) { -1 } else { 0 })
                $tr.Font.Underline = $(if ($sp.underline) { -1 } else { 0 })
                $tr.Font.Color.RGB = (RGB $sp.color)
                $tr.ParagraphFormat.Alignment = @{ l = 1; c = 2; r = 3 }[$sp.align]
                $tr.ParagraphFormat.SpaceWithin = 0.95
                foreach ($run in $sp.runs) {
                    $ch = $tr.Characters($run.start + 1, $run.len)
                    if ($null -ne $run.color) { $ch.Font.Color.RGB = (RGB $run.color) }
                    if ($null -ne $run.bold) { $ch.Font.Bold = $(if ($run.bold) { -1 } else { 0 }) }
                    if ($null -ne $run.size) { $ch.Font.Size = (F $run.size) }
                }
                # Measured, not guessed: the text's own height against the box.
                $need = $sh.TextFrame2.TextRange.BoundHeight + $sp.margin[1] + $sp.margin[3]
                if ($sp.left -lt $P.width -and $sp.left + $sp.width -gt 0 -and $need -gt $sh.Height + 1) {
                    [void]$overflow.Add(('slide {0} {1}: needs {2:N0} pt, has {3:N0}: {4}' -f $i, $sp.name, $need, $sh.Height, $sp.text.Substring(0, [math]::Min(60, $sp.text.Length))))
                }
            }
        }
        $t = $s.SlideShowTransition
        if ($i -gt 1) { $t.EntryEffect = 3954; $t.Duration = (F $P.duration) }
        if ($sd.notes) { $s.NotesPage.Shapes.Placeholders.Item(2).TextFrame.TextRange.Text = $sd.notes }
    }
    $pres.SaveAs($P.out, 24)
    if ($P.png_dir) {
        New-Item -ItemType Directory -Force -Path $P.png_dir | Out-Null
        Get-ChildItem $P.png_dir -Filter *.png | Remove-Item
        foreach ($s in $pres.Slides) { $s.Export((Join-Path $P.png_dir ('s{0:000}.png' -f $s.SlideIndex)), 'PNG', 1280, 720) }
    }
    $pres.Close()
    $pres = $null
} finally {
    if ($null -ne $pres) { try { $pres.Close() } catch {} }
    if (-not $wasRunning) { $app.Quit() }
}
'slides: ' + $i
'overflow: ' + $overflow.Count
$overflow | ForEach-Object { $_ }
