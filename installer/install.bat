@echo off
setlocal
rem This is a single-file BAT/PowerShell installer. Pass paths through the
rem environment so spaces and non-ASCII extraction directories remain literal.
set "OBS_PTZ_INSTALL_SCRIPT=%~f0"
set "OBS_PTZ_INSTALL_PACKAGE=%~dp0"
powershell.exe -NoLogo -NoProfile -Command "$t=[IO.File]::ReadAllText($env:OBS_PTZ_INSTALL_SCRIPT); & ([scriptblock]::Create($t.Substring($t.LastIndexOf('#--OBS-PTZ-POWERSHELL--'))))"
set "OBS_PTZ_INSTALL_RESULT=%ERRORLEVEL%"
rem An elevated child already displayed its result. Avoid a second pause.
if "%OBS_PTZ_INSTALL_RESULT%"=="200" exit /b 0
if not defined OBS_PTZ_INSTALL_QUIET pause
exit /b %OBS_PTZ_INSTALL_RESULT%
#--OBS-PTZ-POWERSHELL--
$ErrorActionPreference = 'Stop'
try {
    if (![Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }
    $source = Join-Path $env:OBS_PTZ_INSTALL_PACKAGE 'obs-ptz'
    $dll = Join-Path $source 'bin\64bit\obs-ptz.dll'
    # The packaging job substitutes the hash of the exact tested DLL. Check it
    # before requesting elevation or changing an existing installation.
    $expectedHash = '@OBS_PTZ_DLL_SHA256@'
    if (!(Test-Path -LiteralPath $dll -PathType Leaf)) { throw 'Extract the complete ZIP before running install.bat.' }
    if ((Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash -ne $expectedHash) { throw 'The plugin checksum is invalid. Extract the ZIP again.' }
    if (@(Get-Process -Name obs64,obs32 -ErrorAction SilentlyContinue).Count) { throw 'Exit OBS Studio completely, including the system tray, before installing.' }

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        # ShellExecute handles the BAT path directly, without interpolating a
        # package path into a shell command. The new process repeats validation.
        $child = Start-Process -FilePath $env:OBS_PTZ_INSTALL_SCRIPT -Verb RunAs -WorkingDirectory $env:OBS_PTZ_INSTALL_PACKAGE -WindowStyle Normal -Wait -PassThru
        if ($child.ExitCode -ne 0) { exit $child.ExitCode }
        exit 200
    }

    $commonData = [Environment]::GetFolderPath([Environment+SpecialFolder]::CommonApplicationData)
    $obsRoot = [IO.Path]::GetFullPath((Join-Path $commonData 'obs-studio'))
    $plugins = [IO.Path]::GetFullPath((Join-Path $obsRoot 'plugins'))
    $target = [IO.Path]::GetFullPath((Join-Path $plugins 'obs-ptz'))
    # Backups and staging stay outside the plugin search directory, so OBS
    # cannot accidentally load an old or partially copied plugin as a second one.
    $backups = [IO.Path]::GetFullPath((Join-Path $obsRoot 'plugin-backups'))
    $id = [Guid]::NewGuid().ToString('N')
    $stage = [IO.Path]::GetFullPath((Join-Path $backups ('obs-ptz-stage-' + $id)))
    $previous = [IO.Path]::GetFullPath((Join-Path $backups ('obs-ptz-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + $id)))
    # Validate absolute move destinations and reject junctions before any
    # directory move. Only this plugin's fixed installation folder is replaced.
    if ([IO.Path]::GetDirectoryName($target) -ne $plugins -or
        !$stage.StartsWith($backups + '\', [StringComparison]::OrdinalIgnoreCase) -or
        !$previous.StartsWith($backups + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid installation path.' }
    foreach ($path in @($obsRoot, $plugins, $target, $backups)) {
        if ((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw ('Installation path contains a junction: ' + $path) }
    }
    [IO.Directory]::CreateDirectory($plugins) | Out-Null
    [IO.Directory]::CreateDirectory($backups) | Out-Null
    Copy-Item -LiteralPath $source -Destination $stage -Recurse
    if ((Get-FileHash -LiteralPath (Join-Path $stage 'bin\64bit\obs-ptz.dll') -Algorithm SHA256).Hash -ne $expectedHash) { throw 'The staged plugin checksum is invalid.' }
    $backupMade = $false
    if (Test-Path -LiteralPath $target) {
        [IO.Directory]::Move($target, $previous)
        $backupMade = $true
    }
    try {
        # These sibling folders share a volume. Directory.Move is an atomic
        # rename and refuses to merge into a destination created concurrently.
        [IO.Directory]::Move($stage, $target)
    } catch {
        if ($backupMade -and !(Test-Path -LiteralPath $target)) { [IO.Directory]::Move($previous, $target) }
        throw
    }
    Write-Host ('Installed obs-ptz to ' + $target) -ForegroundColor Green
    if ($backupMade) { Write-Host ('Previous plugin backup: ' + $previous) }
    Write-Host 'Installation complete. Start OBS Studio 32.0.4 or later (x64).'
    exit 0
} catch {
    Write-Host ('Installation failed: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
