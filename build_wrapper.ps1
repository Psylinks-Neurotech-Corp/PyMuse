Param(
  [string]$PythonExe = "python",
  [string]$VsGenerator = "Visual Studio 17 2022",
  [string]$MuseSdkRoot = "..\libmuse_windows_8.0.5\libmuse_windows_8.0.5"
)

function Resolve-Executable([string]$candidate) {
  try { return (Resolve-Path $candidate -ErrorAction Stop).Path }
  catch {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Could not locate executable: $candidate"
  }
}
function Resolve-SdkRoot([string]$candidate) {
  try { return (Resolve-Path $candidate -ErrorAction Stop).Path }
  catch { throw "Muse SDK root not found: $candidate" }
}

$resolvedPython = Resolve-Executable $PythonExe
$resolvedSdk = Resolve-SdkRoot $MuseSdkRoot

Write-Host "Using Python: $resolvedPython"
Write-Host "Using Muse SDK root: $resolvedSdk"

Write-Host "Configuring Muse wrapper..."
cmake -S . -B build -G "$VsGenerator" -A x64 -DMUSE_SDK_ROOT="$resolvedSdk" -DPython3_EXECUTABLE="$resolvedPython"
if ($LASTEXITCODE -ne 0) { throw "CMake configure failed" }

Write-Host "Building Muse wrapper (Release)..."
cmake --build build --config Release
if ($LASTEXITCODE -ne 0) { throw "CMake build failed" }

Write-Host "Built. Artifacts copied to $(Resolve-Path ./bin)" -ForegroundColor Green

