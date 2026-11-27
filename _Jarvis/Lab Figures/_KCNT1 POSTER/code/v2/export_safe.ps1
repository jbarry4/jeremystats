param([string]$Deck, [string]$Png, [int]$Width = 4800, [string]$Pdf = "")
# Opens a deck read-only in PowerPoint (no window), exports slide 1 to PNG (and optionally the deck to PDF).
# Quits PowerPoint only if no other presentation was open, so a running session of the user's is never closed.
$wasRunning = $null -ne (Get-Process POWERPNT -ErrorAction SilentlyContinue)
$app = New-Object -ComObject PowerPoint.Application
$pres = $null
try {
    $pres = $app.Presentations.Open($Deck, $true, $false, $false)
    $w = $pres.PageSetup.SlideWidth; $h = $pres.PageSetup.SlideHeight
    $pres.Slides.Item(1).Export($Png, "PNG", $Width, [int]($Width * $h / $w))
    if ($Pdf) { $pres.SaveCopyAs($Pdf, 32) }
    "exported $Png" + $(if ($Pdf) { " and $Pdf" } else { "" })
} finally {
    if ($pres) { $pres.Close() }
    if (-not $wasRunning -and $app.Presentations.Count -eq 0) { $app.Quit() }
}
