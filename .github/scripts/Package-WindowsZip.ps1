# Build one self-contained ZIP after the functional and stress gates pass.
# The plugin payload comes from CMake's install tree; test DLLs have no install
# rules. No EXE installer or signing service is involved in this fork package.
[CmdletBinding()]
param([string] $Commit, [string] $Repository)
$ErrorActionPreference = 'Stop'
if (!$env:CI) { throw 'This packaging script is intended for CI.' }
$project = (Resolve-Path "$PSScriptRoot/../..").Path
$spec = Get-Content -LiteralPath (Join-Path $project 'buildspec.json') -Raw | ConvertFrom-Json
$bundle = Join-Path $project 'work/windows-zip'
if (Test-Path -LiteralPath $bundle) { throw 'The ZIP staging directory must be fresh.' }
New-Item -ItemType Directory -Path $bundle | Out-Null
Copy-Item -LiteralPath (Join-Path $project 'release/RelWithDebInfo/obs-ptz') -Destination (Join-Path $bundle 'obs-ptz') -Recurse
$dll = Join-Path $bundle 'obs-ptz/bin/64bit/obs-ptz.dll'
$hash = (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLower()
$bat = [IO.File]::ReadAllText((Join-Path $project 'installer/install.bat')).Replace('@OBS_PTZ_DLL_SHA256@', $hash)
# CMD needs an ASCII launcher without a BOM; normalize line endings explicitly
# rather than relying on the runner's Git autocrlf setting.
$bat = $bat.Replace("`r`n", "`n").Replace("`n", "`r`n")
[IO.File]::WriteAllText((Join-Path $bundle 'install.bat'), $bat, [Text.Encoding]::ASCII)
Copy-Item -LiteralPath (Join-Path $project 'installer/README-Windows.txt') -Destination $bundle
Copy-Item -LiteralPath (Join-Path $project 'LICENSE') -Destination $bundle
"Commit: $Commit`nRepository: $Repository`nOBS: 32.0.4 or later`nArchitecture: Windows x64`nUnsigned fork test build" | Set-Content -LiteralPath (Join-Path $bundle 'BUILD-INFO.txt') -Encoding utf8
# Hash every shipped file, including the installer, using relative portable
# paths. The manifest itself is excluded because it cannot hash itself.
Get-ChildItem -LiteralPath $bundle -Recurse -File | Sort-Object FullName | ForEach-Object {
    $relative = [IO.Path]::GetRelativePath($bundle, $_.FullName).Replace('\', '/')
    "$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower())  $relative"
} | Set-Content -LiteralPath (Join-Path $bundle 'SHA256SUMS.txt') -Encoding utf8
$name = "$($spec.name)-$($spec.version)-fixed-$($Commit.Substring(0,7))-windows-x64.zip"
Compress-Archive -Path (Join-Path $bundle '*') -DestinationPath (Join-Path $project "release/$name") -CompressionLevel Optimal
