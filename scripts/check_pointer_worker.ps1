# Execute the production geometry functions without starting UIA or screen capture.
$ErrorActionPreference = 'Stop'
$path = Join-Path $PSScriptRoot '../src/wordloom/resources/pointer_worker.ps1'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $path).Path, [ref]$tokens, [ref]$errors)
if ($errors.Count -gt 0) { throw 'Worker PowerShell syntax check failed' }
foreach ($name in @('GetScreenBox', 'PointInside')) {
    $function = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }, $true)
    if ($null -eq $function) { throw "Missing production function: $name" }
    . ([ScriptBlock]::Create($function.Extent.Text))
}
foreach ($offset in @(120, -1900)) {
    $rect = [PSCustomObject]@{X=10.5;Y=20.25;Width=80.0;Height=16.0}
    $box = @(GetScreenBox $offset -200 $rect)
    if ($box.Count -ne 4 -or $box[0] -ne ($offset+10.5) -or $box[1] -ne -179.75 -or $box[2] -ne 80 -or $box[3] -ne 16) {
        throw 'OCR screen-coordinate regression'
    }
    if (-not (PointInside $box ($offset+20) -175)) { throw 'Expected pointer hit' }
    if (PointInside $box ($offset+200) -175) { throw 'Unexpected pointer hit' }
}
Write-Output 'PASS: worker syntax and production OCR geometry (positive/negative coordinates, hit/miss)'
