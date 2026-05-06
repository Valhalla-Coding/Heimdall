# ── DNS UDP Forwarder: Windows port 53 → WSL port 5353 ───────────────────────
# Run once as Administrator. Listens on all interfaces port 53,
# forwards every query to 127.0.0.1:5353 (your WSL DNS server).

$listenPort  = 53
$forwardHost = "127.0.0.1"
$forwardPort = 5353

Write-Host "  DNS Forwarder starting..." -ForegroundColor Cyan
Write-Host "  Listening on 0.0.0.0:$listenPort → ${forwardHost}:${forwardPort}" -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop.`n" -ForegroundColor Cyan

$listener = [System.Net.Sockets.UdpClient]::new($listenPort)
$listener.Client.ReceiveTimeout = 0

while ($true) {
    try {
        # Wait for a DNS query from any client
        $remote   = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0)
        $data     = $listener.Receive([ref]$remote)

        # Forward to WSL DNS server
        $fwd      = [System.Net.Sockets.UdpClient]::new()
        $fwd.Connect($forwardHost, $forwardPort)
        $fwd.Send($data, $data.Length) | Out-Null

        # Wait for reply from WSL (timeout 3s)
        $fwd.Client.ReceiveTimeout = 3000
        $wslRemote = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0)
        try {
            $reply = $fwd.Receive([ref]$wslRemote)
            # Send reply back to original client
            $listener.Send($reply, $reply.Length, $remote) | Out-Null
            Write-Host "  $(Get-Date -Format 'HH:mm:ss')  $($remote.Address) → forwarded ${reply.Length}b reply" -ForegroundColor DarkGray
        } catch {
            Write-Host "  $(Get-Date -Format 'HH:mm:ss')  Timeout waiting for WSL reply" -ForegroundColor Yellow
        }
        $fwd.Close()
    } catch {
        Write-Host "  Error: $_" -ForegroundColor Red
    }
}
