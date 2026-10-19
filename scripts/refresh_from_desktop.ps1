# Re-copy rules + UI from the desktop tree into this Pages build.
# Run from afwip-pages:  powershell -File scripts\refresh_from_desktop.ps1

$ErrorActionPreference = "Stop"
$pages = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$desktop = Join-Path (Split-Path -Parent $pages) "afwip-game-main"
if (-not (Test-Path $desktop)) {
  throw "Expected desktop repo at $desktop"
}

robocopy "$desktop\afwip" "$pages\python\afwip" /E /XD __pycache__ /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
# Drop learner-only / server-only pieces we do not ship in Pages.
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
  "$pages\python\afwip\rl\nets.py",
  "$pages\python\afwip\web\app.py",
  "$pages\python\afwip\web\__main__.py"

robocopy "$desktop\web\dist" "$pages\game" /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
robocopy "$desktop\models" "$pages\models" /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
robocopy "$pages\game\art" "$pages\art" /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
Copy-Item "$pages\game\afwipic.png" "$pages\afwipic.png" -Force

$files = Get-ChildItem "$pages\python" -Recurse -Filter *.py | ForEach-Object {
  $_.FullName.Substring("$pages\python\".Length) -replace '\\', '/'
}
$json = $files | ConvertTo-Json
[System.IO.File]::WriteAllText(
  "$pages\python\manifest.json",
  $json,
  [System.Text.UTF8Encoding]::new($false)
)
Write-Host "Refreshed from $desktop — $($files.Count) python files in manifest."
