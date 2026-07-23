[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$sourceCommit = "41736238f5bced4debf3f2a12375d2466874866d"
$modelRepo = "depth-anything/DA3-SMALL"
$modelRevision = "e08cab65ca0ec38e7826075418411ab90cab4da3"
$fallbackConda = "D:\APP\Anaconda\install_place\Scripts\conda.exe"
$conda = if ($env:AIX_CONDA_EXE) {
    $env:AIX_CONDA_EXE
} else {
    $condaCommand = Get-Command conda -ErrorAction SilentlyContinue
    if ($condaCommand) { $condaCommand.Source } else { $fallbackConda }
}

$projectRoot = (& git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
. (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "scripts\runtime_paths.ps1")
$commonGitDir = (& git -C $projectRoot rev-parse --git-common-dir).Trim()
$runtimeRoot = Resolve-AixRuntimeRoot -ProjectRoot $projectRoot -GitCommonDir $commonGitDir
$root = Join-Path $runtimeRoot "Models\DepthAnything3"
$source = Join-Path $root "source"
$environment = Join-Path $root "env"
$weights = Join-Path $root "weights\DA3-SMALL"
$detectorWeights = Join-Path $root "weights\YOLO26m"
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
    & $conda create --prefix $environment python=3.10 pip -y --override-channels --channel conda-forge
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
& $python -m pip install fastapi uvicorn "openai==2.47.0" "ultralytics==8.4.96" "onnx==1.22.0" "onnxslim==0.1.94"
if ($LASTEXITCODE -ne 0) { throw "inference service dependency installation failed" }

& $python (Join-Path $PSScriptRoot "download_weights.py") --repo $modelRepo --revision $modelRevision --output $weights
if ($LASTEXITCODE -ne 0) { throw "DA3-SMALL weight download failed" }

$env:YOLO_CONFIG_DIR = Join-Path $cache "ultralytics"
$env:MPLCONFIGDIR = Join-Path $cache "matplotlib"
$detectorFile = Join-Path $detectorWeights "yolo26m.pt"
$detectorEngine = Join-Path $detectorWeights "yolo26m.engine"
& $python (Join-Path $PSScriptRoot "setup_yolo.py") --weights-dir $detectorWeights
$engineExported = $LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $detectorEngine)
if (-not (Test-Path -LiteralPath $detectorFile)) {
    throw "YOLO26m weight download failed"
}
if (-not $engineExported) {
    Write-Warning "TensorRT FP16 export was unavailable; service will use CUDA FP16 yolo26m.pt."
}

& $python (Join-Path $PSScriptRoot "write_install_manifest.py") `
    --runtime-root $root --source-commit $sourceCommit --model-repo $modelRepo --model-revision $modelRevision
if ($LASTEXITCODE -ne 0) { throw "installation manifest generation failed" }

Write-Output "DA3 installation complete: $root"
