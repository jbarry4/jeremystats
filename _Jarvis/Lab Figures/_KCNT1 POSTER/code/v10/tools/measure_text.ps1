param([string]$Deck, [string]$Out)
# Opens a deck read-only in PowerPoint (no window) and writes, for every shape with text on slide 1, where its box is and
# where its text really ends (inches): the build uses this to size every text box to its text and to space the poster.
# Quits PowerPoint only if no other presentation was open, so a running session of the user's is never closed.
$wasRunning = $null -ne (Get-Process POWERPNT -ErrorAction SilentlyContinue)
$app = New-Object -ComObject PowerPoint.Application
$pres = $null
$rows = @()
try {
    $pres = $app.Presentations.Open($Deck, $true, $false, $false)
    foreach ($s in $pres.Slides.Item(1).Shapes) {
        if ($s.HasTextFrame -and $s.TextFrame2.HasText) {
            $tr = $s.TextFrame2.TextRange
            $n = $tr.Lines().Count
            $rows += [pscustomobject]@{
                id = $s.Id; name = $s.Name
                left = $s.Left / 72; top = $s.Top / 72; width = $s.Width / 72; height = $s.Height / 72
                text_top = $tr.BoundTop / 72; text_height = $tr.BoundHeight / 72; text_width = $tr.BoundWidth / 72
                lines = $n; last_line = $tr.Lines($n, 1).Text
            }
        }
    }
    $rows | ConvertTo-Json -Depth 3 | Out-File -FilePath $Out -Encoding utf8
    "measured $($rows.Count) text shapes -> $Out"
} finally {
    if ($pres) { $pres.Close() }
    if (-not $wasRunning -and $app.Presentations.Count -eq 0) { $app.Quit() }
}
