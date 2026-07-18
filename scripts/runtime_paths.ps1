function Resolve-AixRuntimeRoot {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$ProjectRoot,
        [Parameter(Mandatory)]
        [string]$GitCommonDir
    )

    $resolvedProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
    $resolvedCommonDir = if ([IO.Path]::IsPathRooted($GitCommonDir)) {
        [IO.Path]::GetFullPath($GitCommonDir)
    } else {
        [IO.Path]::GetFullPath((Join-Path $resolvedProjectRoot $GitCommonDir))
    }
    return Split-Path -Parent $resolvedCommonDir
}
