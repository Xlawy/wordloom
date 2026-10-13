# Read-only UI Automation helper. ExpectedWindow is prepended by the Python adapter.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
function Reply($code, $text = '') {
    [Console]::WriteLine((@{ code = $code; text = $text } | ConvertTo-Json -Compress))
    exit 0
}
try {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
} catch { Reply 'unavailable' }
try {
    $element = [System.Windows.Automation.AutomationElement]::FocusedElement
    if ($null -eq $element) { Reply 'empty' }
    if ($element.Current.IsPassword) { Reply 'protected' }
    # Ensure the focused element belongs to the window captured at hotkey time.
    $node = $element
    $belongs = $false
    for ($i = 0; $i -lt 64 -and $null -ne $node; $i++) {
        $handle = [Int64]$node.Current.NativeWindowHandle -band 4294967295
        if ($handle -eq ($ExpectedWindow -band 4294967295)) { $belongs = $true; break }
        $node = [System.Windows.Automation.TreeWalker]::RawViewWalker.GetParent($node)
    }
    if (-not $belongs) { Reply 'focus_changed' }
    $pattern = $null
    if (-not $element.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) {
        Reply 'unsupported'
    }
    $ranges = $pattern.GetSelection()
    $parts = New-Object 'System.Collections.Generic.List[string]'
    $length = 0
    foreach ($range in $ranges) {
        $part = $range.GetText(20001)
        if ($part.Length -eq 0) { continue }
        $length += $part.Length + 1
        if ($length -gt 20001) { Reply 'too_long' }
        $parts.Add($part)
    }
    $text = [String]::Join("`n", $parts)
    if ([String]::IsNullOrWhiteSpace($text)) { Reply 'empty' }
    Reply 'ok' $text
} catch {
    # Never emit exception details containing window titles or selected content.
    Reply 'unavailable'
}
