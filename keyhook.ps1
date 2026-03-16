# Wispr Transcription - Windows keyboard hook
# Polls key state via GetAsyncKeyState and sends events over TCP to the WSL daemon.
# Must run on the Windows interactive desktop (launched via wscript.exe from WSL).
param(
    [int]$VKCode = 0xA5,  # Default: Right Alt (VK_RMENU)
    [int]$Port = 19475
)

Add-Type -MemberDefinition @"
[DllImport("user32.dll")]
public static extern short GetAsyncKeyState(int vKey);
"@ -Name Win32Api -Namespace Wispr

# Connect to the WSL daemon over TCP localhost
try {
    $client = New-Object System.Net.Sockets.TcpClient
    $client.Connect("127.0.0.1", $Port)
    $stream = $client.GetStream()
    $writer = New-Object System.IO.StreamWriter($stream)
    $writer.AutoFlush = $true
    $reader = New-Object System.IO.StreamReader($stream)
    $writer.WriteLine("HOOK_READY")
} catch {
    Write-Error "Cannot connect to wispr daemon on port ${Port}: $_"
    exit 1
}

# Poll key state and send events
$keyDown = $false
try {
    while ($true) {
        # Check if daemon sent a quit signal (non-blocking)
        if ($stream.DataAvailable) {
            $line = $reader.ReadLine()
            if ($null -eq $line -or $line -eq "QUIT") { break }
        }

        $state = [Wispr.Win32Api]::GetAsyncKeyState($VKCode)
        if ($state -band 0x8000) {
            if (-not $keyDown) {
                $writer.WriteLine("KEY_DOWN")
                $keyDown = $true
            }
        } else {
            if ($keyDown) {
                $writer.WriteLine("KEY_UP")
                $keyDown = $false
            }
        }
        Start-Sleep -Milliseconds 15
    }
} catch {
    # Connection closed or broken — exit cleanly
} finally {
    try { $writer.Close() } catch {}
    try { $reader.Close() } catch {}
    try { $client.Close() } catch {}
}
