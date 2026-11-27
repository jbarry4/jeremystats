param([string]$Deck, [string]$Png, [int]$Width = 4800, [string]$Pdf = "")
# Opens a deck read-only in PowerPoint, exports slide 1 to PNG (and optionally the deck to PDF), then quits.
$app = New-Object -ComObject PowerPoint.Application
try {
    $pres = $app.Presentations.Open($Deck, $true, $false, $false)
    $w = $pres.PageSetup.SlideWidth; $h = $pres.PageSetup.SlideHeight
    $pres.Slides.Item(1).Export($Png, "PNG", $Width, [int]($Width * $h / $w))
    if ($Pdf) { $pres.SaveAs($Pdf, 32) }
    $pres.Close()
    "exported $Png" + $(if ($Pdf) { " and $Pdf" } else { "" })
} finally {
    $app.Quit()
}
