param([ValidateSet('uia','ocr')][string]$Mode = 'uia')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$nativeReady = $false
$uiaReady = $false
$ocrReady = $false
$ocrInitStage = 'init'
try {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class WordLoomPointNative {
 [StructLayout(LayoutKind.Sequential)] public struct Point { public int X,Y; }
 [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left,Top,Right,Bottom; }
 [StructLayout(LayoutKind.Sequential)] public struct MonitorInfo { public int Size; public Rect Monitor,Work; public uint Flags; }
 [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr context);
 [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(Point point);
 [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr window, uint flag);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern IntPtr MonitorFromPoint(Point point, uint flag);
 [DllImport("user32.dll")] public static extern bool GetMonitorInfo(IntPtr monitor, ref MonitorInfo info);
}
'@
    try { [void][WordLoomPointNative]::SetProcessDpiAwarenessContext([IntPtr](-4)) } catch {}
    $nativeReady = $true
} catch {}
if ($Mode -eq 'uia') {
    try {
        Add-Type -AssemblyName UIAutomationClient
        Add-Type -AssemblyName UIAutomationTypes
        Add-Type -AssemblyName WindowsBase
        $uiaReady = $true
    } catch {}
} else {
    try {
        Add-Type -AssemblyName System.Drawing
        Add-Type -AssemblyName System.Runtime.WindowsRuntime
        [void][Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
        [void][Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
        [void][Windows.Globalization.Language, Windows.Foundation, ContentType=WindowsRuntime]
        [void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
        [void][Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType=WindowsRuntime]
        [void][Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Foundation, ContentType=WindowsRuntime]
        [void][Windows.Storage.Streams.DataWriter, Windows.Foundation, ContentType=WindowsRuntime]
        $ocrInitStage = 'bridge'
        $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
            $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Length -eq 1 -and
            $_.GetParameters().Length -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
        } | Select-Object -First 1
        $ocrInitStage = 'language'
        $language = [Windows.Globalization.Language]::new('en-US')
        $engine = $null
        if ([Windows.Media.Ocr.OcrEngine]::IsLanguageSupported($language)) {
            $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
        }
        if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
        $ocrReady = $null -ne $engine -and $null -ne $asTask
    } catch {}
}
function AwaitResult($operation, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($operation))
    $task.GetAwaiter().GetResult()
}
function PointInside($box, $x, $y) {
    return ($x -ge $box[0]-2 -and $x -le $box[0]+$box[2]+2 -and $y -ge $box[1]-2 -and $y -le $box[1]+$box[3]+2)
}
function GetScreenBox($left, $top, $rect) {
    # Comma binds more tightly than + in PowerShell. Group each coordinate.
    return @(($left + $rect.X), ($top + $rect.Y), $rect.Width, $rect.Height)
}
function GetUia($request) {
    if (-not $uiaReady) { return @{code='helper'} }
    $point = [System.Windows.Point]::new([double]$request.x, [double]$request.y)
    $node = [System.Windows.Automation.AutomationElement]::FromPoint($point)
    for ($i=0; $i -lt 10 -and $null -ne $node; $i++) {
        if ($node.Current.IsPassword) { return @{code='protected'} }
        $pattern = $null
        if ($node.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) {
            $range = $pattern.RangeFromPoint($point)
            $range.ExpandToEnclosingUnit([System.Windows.Automation.Text.TextUnit]::Word)
            $word = $range.GetText(129).Trim()
            # Some providers expand Word to Paragraph; never call that a single word.
            if ($word.Length -gt 0 -and $word.Length -le 128 -and $word -notmatch '\s') {
                $bounds = $range.GetBoundingRectangles()
                foreach ($rect in $bounds) {
                    $box = @($rect.X, $rect.Y, $rect.Width, $rect.Height)
                    if (PointInside $box $request.x $request.y) {
                        $contextRange = $range.Clone()
                        $contextRange.ExpandToEnclosingUnit([System.Windows.Automation.Text.TextUnit]::Paragraph)
                        $context = $contextRange.GetText(4000)
                        if (-not $context.Contains($word)) {
                            # A long paragraph can truncate before the hovered word.
                            $contextRange = $range.Clone()
                            [void]$contextRange.MoveEndpointByUnit([System.Windows.Automation.Text.TextPatternRangeEndpoint]::Start, [System.Windows.Automation.Text.TextUnit]::Word, -20)
                            [void]$contextRange.MoveEndpointByUnit([System.Windows.Automation.Text.TextPatternRangeEndpoint]::End, [System.Windows.Automation.Text.TextUnit]::Word, 20)
                            $context = $contextRange.GetText(4000)
                        }
                        return @{code='ok'; word=$word; context=$context; source='uia'; box=$box}
                    }
                }
            }
        }
        # Stop at target top-level window, do not inspect unrelated UI ancestors.
        if (([Int64]$node.Current.NativeWindowHandle -band 4294967295) -eq ([Int64]$request.window -band 4294967295)) { break }
        $node = [System.Windows.Automation.TreeWalker]::RawViewWalker.GetParent($node)
    }
    return @{code='unsupported'}
}
function GetOcr($request, $point) {
    if (-not $ocrReady) { return @{code='ocr_missing';stage=$ocrInitStage} }
    $info = [WordLoomPointNative+MonitorInfo]::new()
    $info.Size = [System.Runtime.InteropServices.Marshal]::SizeOf($info)
    $monitor = [WordLoomPointNative]::MonitorFromPoint($point, 2)
    if (-not [WordLoomPointNative]::GetMonitorInfo($monitor, [ref]$info)) { return @{code='ocr_error'} }
    $width = [Math]::Min(700, $info.Monitor.Right - $info.Monitor.Left)
    $height = [Math]::Min(260, $info.Monitor.Bottom - $info.Monitor.Top)
    $left = [int][Math]::Max($info.Monitor.Left, [Math]::Min([int]$request.x - $width/2, $info.Monitor.Right-$width))
    $top = [int][Math]::Max($info.Monitor.Top, [Math]::Min([int]$request.y - $height/2, $info.Monitor.Bottom-$height))
    $bitmap=$null; $graphics=$null; $memory=$null; $random=$null; $writer=$null; $software=$null
    $stage = 'capture'
    try {
        $bitmap = [System.Drawing.Bitmap]::new($width, $height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($left, $top, 0, 0, [System.Drawing.Size]::new($width,$height))
        $stage = 'decode'
        $memory = [System.IO.MemoryStream]::new()
        $bitmap.Save($memory, [System.Drawing.Imaging.ImageFormat]::Png)
        $random = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
        $writer = [Windows.Storage.Streams.DataWriter]::new($random)
        $writer.WriteBytes($memory.ToArray())
        [void](AwaitResult ($writer.StoreAsync()) ([uint32]))
        $writer.DetachStream() | Out-Null
        $random.Seek(0)
        $decoder = AwaitResult ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($random)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $software = AwaitResult ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $stage = 'recognize'
        $result = AwaitResult ($engine.RecognizeAsync($software)) ([Windows.Media.Ocr.OcrResult])
        $stage = 'hitbox'
        if ($result.Lines.Count -eq 0) { return @{code='ocr_no_text';stage=$stage} }
        $index = -1; $found=$null; $foundBox=$null
        for ($j=0; $j -lt $result.Lines.Count; $j++) {
            foreach ($word in $result.Lines[$j].Words) {
                $r = $word.BoundingRect
                $box = GetScreenBox $left $top $r
                if (PointInside $box $request.x $request.y) { $index=$j; $found=$word.Text; $foundBox=$box; break }
            }
            if ($null -ne $found) { break }
        }
        if ([string]::IsNullOrWhiteSpace($found)) { return @{code='ocr_no_hit';stage=$stage} }
        $lines = @()
        for ($j=[Math]::Max(0,$index-1); $j -le [Math]::Min($result.Lines.Count-1,$index+1); $j++) {
            $lines += $result.Lines[$j].Text
        }
        $context = [string]::Join("`n", $lines)
        if ($context.Length -gt 4000) { $context=$context.Substring(0,4000) }
        return @{code='ok';word=$found;context=$context;source='ocr';box=$foundBox}
    } catch { return @{code='ocr_error';stage=$stage} }
    finally {
        foreach ($item in @($software,$writer,$random,$memory,$graphics,$bitmap)) {
            if ($null -ne $item) { try { $item.Dispose() } catch {} }
        }
    }
}
while ($null -ne ($line = [Console]::ReadLine())) {
    try {
        $request = $line | ConvertFrom-Json
        $result = @{code='helper'}
        if ($nativeReady) {
            $point = [WordLoomPointNative+Point]::new()
            $point.X = [int]$request.x; $point.Y = [int]$request.y
            $window = [WordLoomPointNative]::WindowFromPoint($point)
            $root = [WordLoomPointNative]::GetAncestor($window,2)
            if ($root.ToInt64() -ne [Int64]$request.window -or [WordLoomPointNative]::GetForegroundWindow().ToInt64() -ne [Int64]$request.foreground) {
                $result = @{code='changed'}
            } elseif ($Mode -eq 'uia') { $result = GetUia $request }
            else { $result = GetOcr $request $point }
        }
        $result['id'] = $request.id
        [Console]::WriteLine(($result | ConvertTo-Json -Compress -Depth 5))
    } catch {
        [Console]::WriteLine((@{code='helper';id=$request.id} | ConvertTo-Json -Compress))
    }
}
