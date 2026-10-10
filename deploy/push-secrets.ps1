<#
  Copies Glas Intelligence secrets from YOUR PC to the server's deploy/app-secrets.conf.
  Run it yourself, in your own PowerShell window (not through an AI agent):

    powershell -NoProfile -ExecutionPolicy Bypass -File deploy\push-secrets.ps1 -Server <server-ip>

  For each setting it uses your user environment variable when one exists (LLM_API_KEY,
  SUPABASE_URL, ...); otherwise it asks you, with hidden typing for secret values.
  Values are never printed. They travel over SSH in a temporary file that is deleted at
  both ends. Settings you leave empty keep their current value on the server.
#>
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [string]$KeyFile = "$env:USERPROFILE\.ssh\glas_hetzner",
    [string]$User = 'root'
)
$ErrorActionPreference = 'Stop'

# name, secret?, required?, hint
$settings = @(
    @('ACME_EMAIL', $false, $true, 'email for Lets Encrypt expiry warnings'),
    @('LLM_API_KEY', $true, $true, 'DeepSeek API key'),
    @('LLM_BASE_URL', $false, $false, 'default https://api.deepseek.com'),
    @('LLM_MODEL_NAME', $false, $false, 'default deepseek-flash'),
    @('SUPABASE_URL', $false, $true, 'https://<project>.supabase.co'),
    @('SUPABASE_SERVICE_KEY', $true, $true, 'Supabase service_role key'),
    @('SUPABASE_JWT_SECRET', $true, $true, 'Supabase JWT secret'),
    @('SUPABASE_ANON_KEY', $true, $true, 'Supabase anon (public) key'),
    @('STRIPE_SECRET_KEY', $true, $false, 'optional'),
    @('STRIPE_WEBHOOK_SECRET', $true, $false, 'optional'),
    @('RESEND_API_KEY', $true, $false, 'optional'),
    @('SENTRY_DSN', $true, $false, 'optional')
)

function Read-Value([string]$name, [bool]$secret, [string]$hint) {
    $fromEnv = [Environment]::GetEnvironmentVariable($name, 'User')
    if ($fromEnv) { Write-Host "  $name  <- your user environment variable"; return $fromEnv }
    if ($secret) {
        $ss = Read-Host "  $name ($hint; Enter to skip)" -AsSecureString
        $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($ss)
        try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
    }
    return (Read-Host "  $name ($hint; Enter to skip)")
}

Write-Host "Settings for $Server :"
$values = [ordered]@{}
foreach ($s in $settings) {
    $v = Read-Value $s[0] $s[1] $s[3]
    if ($v) {
        if ($v -match "[\r\n]") { throw "$($s[0]) contains a line break" }
        $values[$s[0]] = $v.Trim()
    } elseif ($s[2]) {
        Write-Host "    (left empty: $($s[0]) is required, so deploy.sh will refuse to start until it is set)" -ForegroundColor Yellow
    }
}
# The frontend build needs the public Supabase values under VITE_ names.
if ($values.Contains('SUPABASE_URL')) { $values['VITE_SUPABASE_URL'] = $values['SUPABASE_URL'] }
if ($values.Contains('SUPABASE_ANON_KEY')) { $values['VITE_SUPABASE_ANON_KEY'] = $values['SUPABASE_ANON_KEY'] }
if ($values.Count -eq 0) { Write-Host 'Nothing to send.'; exit 0 }

$tmp = Join-Path $env:TEMP ("glas-secrets-" + [guid]::NewGuid().ToString('N') + '.in')
try {
    $lines = ($values.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "`n"
    [IO.File]::WriteAllText($tmp, $lines + "`n", (New-Object Text.UTF8Encoding($false)))
    $remoteIn = '/root/glas-secrets.in'
    & scp -q -i $KeyFile $tmp "${User}@${Server}:$remoteIn"
    if ($LASTEXITCODE -ne 0) { throw 'scp failed' }
    # Merge on the server: replace KEY= lines, append new keys, keep everything else.
    $merge = @'
set -e
f=/opt/glas/deploy/app-secrets.conf
in=/root/glas-secrets.in
test -f "$f" || { echo "missing $f: run bootstrap-server.sh first"; rm -f "$in"; exit 1; }
awk 'NR==FNR { i=index($0,"="); if (i) v[substr($0,1,i-1)]=substr($0,i+1); next }
     { i=index($0,"="); if (i) { k=substr($0,1,i-1); if (k in v) { print k "=" v[k]; delete v[k]; next } } print }
     END { for (k in v) print k "=" v[k] }' "$in" "$f" > "$f.new"
chmod 600 "$f.new" && mv "$f.new" "$f"
shred -u "$in" 2>/dev/null || rm -f "$in"
rm -f /root/glas-merge.sh
echo "Server secrets updated. Still empty:"
grep -E '^[A-Z_]+=$' "$f" | cut -d= -f1 | sed 's/^/  /' || true
'@
    # Send the merge script as an LF-only file: piping it would carry Windows CRLFs into bash.
    $tmpMerge = Join-Path $env:TEMP ("glas-merge-" + [guid]::NewGuid().ToString('N') + '.sh')
    [IO.File]::WriteAllText($tmpMerge, ($merge -replace "`r", ''), (New-Object Text.UTF8Encoding($false)))
    & scp -q -i $KeyFile $tmpMerge "${User}@${Server}:/root/glas-merge.sh"
    if ($LASTEXITCODE -ne 0) { throw 'scp of the merge script failed' }
    & ssh -i $KeyFile "${User}@${Server}" 'bash /root/glas-merge.sh'
    if ($LASTEXITCODE -ne 0) { throw 'ssh merge failed' }
} finally {
    if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Force }
    if ($tmpMerge -and (Test-Path $tmpMerge)) { Remove-Item -LiteralPath $tmpMerge -Force }
}
Write-Host "Done. Next: ssh -i $KeyFile ${User}@${Server} /opt/glas/deploy/deploy.sh"
