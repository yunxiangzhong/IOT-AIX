[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$sourceCommit = "41736238f5bced4debf3f2a12375d2466874866d"
$modelRepo = "depth-anything/DA3-SMALL"
$modelRevision = "e08cab65ca0ec38e7826075418411ab90cab4da3"
$conda = "D:\APP\Anaconda\install_place\Scripts\conda.exe"

$commonGitDir = (& git -C $PSScriptRoot rev-parse --git-common-dir).Trim()
$projectRoot = Split-Path -Parent $commonGitDir
$root = Join-Path $projectRoot "Models\DepthAnything3"
$source = Join-Path $root "source"
$environment = Join-Path $root "env"
$weights = Join-Path $root "weights\DA3-SMALL"
$detectorWeights = Join-Path $root "weights\SSDLite320-MobileNetV3"
$cache = Join-Path $root "cache"
$logs = Join-Path $root "logs"

foreach ($path in @($root, $cache, $logs, $weights, $detectorWeights)) {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
}

if (-not (Test-Path -LiteralPath $conda)) {
    throw "Conda was not found: $conda"
}

if (-not (Test-Path -LiteralPath (Join-Path $source ".git"))) {
    & git clone --depth 1 https://github.com/ByteDance-Seed/depth-anything-3.git $source
    if ($LASTEXITCODE -ne 0) { throw "Depth Anything 3 clone failed" }
}

& git -C $source fetch --depth 1 origin $sourceCommit
if ($LASTEXITCODE -ne 0) { throw "Depth Anything 3 fetch failed" }
& git -C $source checkout --detach $sourceCommit
if ($LASTEXITCODE -ne 0) { throw "Depth Anything 3 checkout failed" }

if (-not (Test-Path -LiteralPath (Join-Path $environment "python.exe"))) {
    & $conda create --prefix $environment python=3.10 pip -y
    if ($LASTEXITCODE -ne 0) { throw "DA3 environment creation failed" }
}

$python = Join-Path $environment "python.exe"
$env:HF_HOME = Join-Path $cache "huggingface"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TORCH_HOME = Join-Path $cache "torch"

& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $python -m pip install torch==2.12.1 torchvision==0.27.1 --index-url https://download.pytorch.org/whl/cu126
if ($LASTEXITCODE -ne 0) { throw "CUDA PyTorch installation failed" }
& $python -m pip install xformers==0.0.35
if ($LASTEXITCODE -ne 0) { throw "xformers installation failed" }
& $python -m pip install -e $source
if ($LASTEXITCODE -ne 0) { throw "Depth Anything 3 installation failed" }
& $python -m pip install addict
if ($LASTEXITCODE -ne 0) { throw "Depth Anything 3 missing runtime dependency installation failed" }
& $python -m pip install fastapi uvicorn
if ($LASTEXITCODE -ne 0) { throw "inference service dependency installation failed" }

& $python (Join-Path $PSScriptRoot "download_weights.py") --repo $modelRepo --revision $modelRevision --output $weights
if ($LASTEXITCODE -ne 0) { throw "DA3-SMALL weight download failed" }

$detectorUrl = "https://download.pytorch.org/models/ssdlite320_mobilenet_v3_large_coco-a79551df.pth"
$detectorFile = Join-Path $detectorWeights "ssdlite320_mobilenet_v3_large_coco-a79551df.pth"
if (-not (Test-Path -LiteralPath $detectorFile)) {
    & $python (Join-Path $PSScriptRoot "download_weights.py") --url $detectorUrl --output-file $detectorFile --sha256-prefix "a79551df"
    if ($LASTEXITCODE -ne 0) { throw "SSDLite weight download failed" }
}

$manifest = [ordered]@{
    source_commit = $sourceCommit
    model_repo = $modelRepo
    model_revision = $modelRevision
    source = $source
    environment = $environment
    weights = $weights
    detector_weights = $detectorFile
    cache = $cache
    installed_at = (Get-Date).ToString("o")
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root "install_manifest.json") -Encoding UTF8

Write-Output "DA3 installation complete: $root"
