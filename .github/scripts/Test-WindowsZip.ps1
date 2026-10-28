# Exercise the actual ZIP's installer only on a disposable CI runner. The user's
# installed OBS is never modified by the local development or stress harness.
$ErrorActionPreference = 'Stop'
if (!$env:CI) { throw 'Installer smoke tests require a disposable CI runner.' }
$project = (Resolve-Path "$PSScriptRoot/../..").Path
$archive = Get-ChildItem -LiteralPath (Join-Path $project 'release') -Filter '*-windows-x64.zip' | Select-Object -First 1
$smoke = Join-Path $project 'work/installer-smoke'
Expand-Archive -LiteralPath $archive.FullName -DestinationPath $smoke
$script = Join-Path $smoke 'install.bat'
$sourceDll = Join-Path $smoke 'obs-ptz/bin/64bit/obs-ptz.dll'
$expected = (Get-FileHash -LiteralPath $sourceDll -Algorithm SHA256).Hash
$commonData = [Environment]::GetFolderPath([Environment+SpecialFolder]::CommonApplicationData)
$targetDll = Join-Path $commonData 'obs-studio/plugins/obs-ptz/bin/64bit/obs-ptz.dll'
$env:OBS_PTZ_INSTALL_QUIET = '1'
foreach ($attempt in 1..2) {
    # First installation and then upgrade: the second run must leave an old
    # plugin backup outside the scan directory while installing the same bytes.
    & $script
    if ($LASTEXITCODE -ne 0) { throw "Installer attempt $attempt failed." }
    if ((Get-FileHash -LiteralPath $targetDll -Algorithm SHA256).Hash -ne $expected) { throw 'Installed DLL differs from the package.' }
}
$backups = Get-ChildItem -LiteralPath (Join-Path $commonData 'obs-studio/plugin-backups') -Directory -Filter 'obs-ptz-*'
if (!($backups | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin/64bit/obs-ptz.dll') })) { throw 'Upgrade did not preserve a plugin backup.' }
# A damaged package must fail before touching the working installation. Corrupt
# only the extracted test copy; the uploaded ZIP stays unchanged.
$stream = [IO.File]::OpenWrite($sourceDll)
try { $stream.Position = $stream.Length; $stream.WriteByte(0) } finally { $stream.Dispose() }
& $script
if ($LASTEXITCODE -eq 0) { throw 'The installer accepted a damaged plugin.' }
if ((Get-FileHash -LiteralPath $targetDll -Algorithm SHA256).Hash -ne $expected) { throw 'A failed installation changed the installed plugin.' }
Write-Host 'ZIP installer checks passed: fresh install, upgrade backup, corrupt-package rejection.'
# The last native command intentionally failed. Return success only after all
# assertions above verified that this was the expected, harmless rejection.
exit 0
