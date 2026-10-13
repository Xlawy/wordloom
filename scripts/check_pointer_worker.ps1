# Validate the production exporter without screen capture or WinRT dependencies.
$ErrorActionPreference = 'Stop'
$path = Join-Path $PSScriptRoot '../src/wordloom/resources/pointer_worker.ps1'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $path).Path, [ref]$tokens, [ref]$errors)
if ($errors.Count -gt 0) { throw 'Worker PowerShell syntax check failed' }
$function = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'ExportOcrLines' }, $true)
if ($null -eq $function) { throw 'Missing production exporter' }
. ([ScriptBlock]::Create($function.Extent.Text))
# An enumerable with no public Count or indexer models the required interface.
Add-Type -TypeDefinition @'
using System.Collections;
public class OnlyEnumerable : IEnumerable {
    private object[] items;
    public OnlyEnumerable(object[] values) { items=values; }
    public IEnumerator GetEnumerator() { return items.GetEnumerator(); }
}
'@
$rect = [PSCustomObject]@{X=10.5;Y=20.25;Width=80.0;Height=16.0}
$word = [PSCustomObject]@{Text='example';BoundingRect=$rect}
$line = [PSCustomObject]@{Text='an example';Words=[OnlyEnumerable]::new(@($word))}
$result = [PSCustomObject]@{Lines=[OnlyEnumerable]::new(@($line))}
$packet = ExportOcrLines $result -1900 -200
$json = $packet | ConvertTo-Json -Compress -Depth 8
$decoded = $json | ConvertFrom-Json
if ($decoded.code -ne 'ocr_lines' -or $decoded.left -ne -1900 -or $decoded.top -ne -200) { throw 'Envelope regression' }
if ($decoded.lines.Count -ne 1 -or $decoded.lines[0].words.Count -ne 1) { throw 'Singleton collection regression' }
if ($decoded.lines[0].words[0].box[0] -ne 10.5 -or $decoded.lines[0].words[0].text -ne 'example') { throw 'Primitive export regression' }
$empty = ExportOcrLines ([PSCustomObject]@{Lines=[OnlyEnumerable]::new(@())}) 0 0
if ($empty.lines.Count -ne 0) { throw 'Empty collection regression' }
Write-Output 'PASS: worker syntax and production OCR exporter (enumeration, JSON, singleton/empty collections)'
