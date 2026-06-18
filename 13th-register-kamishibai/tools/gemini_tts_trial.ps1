param(
  [string]$Text = "",
  [string]$Speaker = "ナレーション",
  [string]$Csv = "13th-register-kamishibai/assets/ep01_dialogue_edit.csv",
  [int]$Limit = 1,
  [string]$Voice = "Kore",
  [string]$VoiceMap = "13th-register-kamishibai/assets/gemini_voice_cast_v1.json",
  [string]$Model = "gemini-3.1-flash-tts-preview",
  [string]$OutDir = "outputs/gemini_tts_trial",
  [int]$DelaySeconds = 0
)

$ErrorActionPreference = "Stop"

function Get-GeminiApiKey {
  foreach ($envFile in @(".env.local", ".env")) {
    if (-not (Test-Path -LiteralPath $envFile)) {
      continue
    }
    $raw = Get-Content -LiteralPath $envFile -Raw -Encoding UTF8
    foreach ($line in ($raw -split "`r?`n")) {
      if ($line -match '^\s*(GEMINI_API_KEY|GOOGLE_API_KEY)\s*=(.+)\s*$') {
        return (($Matches[2]).Trim().Trim('"').Trim("'") -replace '[^\x21-\x7E]', '')
      }
    }
  }

  if ($env:GEMINI_API_KEY) { return $env:GEMINI_API_KEY }
  if ($env:GOOGLE_API_KEY) { return $env:GOOGLE_API_KEY }
  throw "GEMINI_API_KEY or GOOGLE_API_KEY is not set."
}

function Get-SpeakerStyle([string]$Name) {
  switch ($Name) {
    "ミナ" { "落ち着いた若い女性。淡々として無表情、低めのテンションで、コンビニ夜勤の先輩らしく自然に読む。" }
    "タクミ" { "若い男性。驚きとツッコミが多いが、叫びすぎず、深夜コンビニの小声感を少し残して読む。" }
    "ナレーション" { "静かな語り。深夜のコンビニSFコメディとして、落ち着いて少し不思議に読む。" }
    "第十三レジ" { "無機質なレジ端末。感情を抑え、機械的で淡々と読む。" }
    "未来の会社員" { "疲れた若い男性会社員。恐縮していて、少し弱った声で読む。" }
    "座木山辰哉" { "55歳の常連客。眠そうで飄々としていて、普通のことのように変な内容を読む。" }
    default { "自然な日本語の会話として読む。" }
  }
}

function Get-VoiceMap {
  if (-not (Test-Path -LiteralPath $VoiceMap)) {
    return $null
  }
  return Get-Content -LiteralPath $VoiceMap -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-VoiceForSpeaker([string]$Name, $Map) {
  if (-not $Map -or -not $Map.cast) {
    return $Voice
  }
  if ($Map.cast.PSObject.Properties.Name -contains $Name) {
    return [string]$Map.cast.$Name
  }
  if ($Map.defaultVoice) {
    return [string]$Map.defaultVoice
  }
  return $Voice
}

function Convert-Pcm16ToWav([byte[]]$PcmBytes, [string]$OutPath, [int]$SampleRate, [int]$Channels) {
  $dataSize = $PcmBytes.Length
  $byteRate = $SampleRate * $Channels * 2
  $blockAlign = $Channels * 2

  $stream = [System.IO.MemoryStream]::new()
  $writer = [System.IO.BinaryWriter]::new($stream)
  $writer.Write([Text.Encoding]::ASCII.GetBytes("RIFF"))
  $writer.Write([int](36 + $dataSize))
  $writer.Write([Text.Encoding]::ASCII.GetBytes("WAVE"))
  $writer.Write([Text.Encoding]::ASCII.GetBytes("fmt "))
  $writer.Write([int]16)
  $writer.Write([int16]1)
  $writer.Write([int16]$Channels)
  $writer.Write([int]$SampleRate)
  $writer.Write([int]$byteRate)
  $writer.Write([int16]$blockAlign)
  $writer.Write([int16]16)
  $writer.Write([Text.Encoding]::ASCII.GetBytes("data"))
  $writer.Write([int]$dataSize)
  $writer.Write($PcmBytes)
  $writer.Flush()

  [IO.File]::WriteAllBytes((Resolve-Path -LiteralPath (Split-Path -Parent $OutPath)).Path + "\" + (Split-Path -Leaf $OutPath), $stream.ToArray())
  $writer.Dispose()
  $stream.Dispose()
}

function Invoke-GeminiTts([string]$LineId, [string]$LineSpeaker, [string]$LineText, [string]$LineVoice) {
  $key = Get-GeminiApiKey
  $uri = "https://generativelanguage.googleapis.com/v1beta/models/$($Model):generateContent"
  $style = Get-SpeakerStyle $LineSpeaker
  $prompt = "$style`n次のセリフだけを日本語で読み上げる。説明や前置きは読まない。`nセリフ: $LineText"
  $bodyObj = @{
    contents = @(@{ parts = @(@{ text = $prompt }) })
    generationConfig = @{
      responseModalities = @("AUDIO")
      speechConfig = @{
        voiceConfig = @{
          prebuiltVoiceConfig = @{
            voiceName = $LineVoice
          }
        }
      }
    }
  }
  $body = $bodyObj | ConvertTo-Json -Depth 20
  $res = Invoke-RestMethod -Uri $uri -Method Post -Headers @{ "x-goog-api-key" = $key } -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec 120
  if (-not $res.candidates -or $res.candidates.Count -lt 1) {
    $json = $res | ConvertTo-Json -Depth 20
    throw "No candidates returned for $LineId. Response: $json"
  }
  $part = $res.candidates[0].content.parts[0].inlineData
  if (-not $part.data) {
    $json = $res | ConvertTo-Json -Depth 20
    throw "No audio data returned for $LineId. Response: $json"
  }

  $mime = [string]$part.mimeType
  $rate = 24000
  $channels = 1
  if ($mime -match 'rate=(\d+)') { $rate = [int]$Matches[1] }
  if ($mime -match 'channels=(\d+)') { $channels = [int]$Matches[1] }

  New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
  $safeSpeaker = $LineSpeaker -replace '[\\/:*?"<>|]', "_"
  $outPath = Join-Path $OutDir "$($LineId)_$($safeSpeaker)_$($LineVoice).wav"
  $bytes = [Convert]::FromBase64String($part.data)
  Convert-Pcm16ToWav -PcmBytes $bytes -OutPath $outPath -SampleRate $rate -Channels $channels

  [pscustomobject]@{
    id = $LineId
    speaker = $LineSpeaker
    voice = $LineVoice
    model = $Model
    mimeType = $mime
    out = $outPath
    text = $LineText
  }
}

$jobs = @()
if ($Text.Trim()) {
  $jobs += [pscustomobject]@{ id = "sample"; speaker = $Speaker; text = $Text }
} else {
  $rows = Import-Csv -LiteralPath $Csv -Encoding UTF8
  foreach ($row in $rows) {
    $lineText = ""
    foreach ($field in @("reading_hiragana", "reading", "dialogue")) {
      if ($row.PSObject.Properties.Name -contains $field -and [string]$row.$field) {
        $lineText = ([string]$row.$field).Trim()
        break
      }
    }
    if (-not $lineText) { continue }
    $jobs += [pscustomobject]@{
      id = if ($row.id) { $row.id } else { "line_$($jobs.Count + 1)" }
      speaker = if ($row.speaker) { $row.speaker } else { "" }
      text = $lineText
    }
    if ($jobs.Count -ge $Limit) { break }
  }
}

$manifest = @()
$voiceMapData = Get-VoiceMap
foreach ($job in $jobs) {
  $lineVoice = Get-VoiceForSpeaker -Name $job.speaker -Map $voiceMapData
  $result = Invoke-GeminiTts -LineId $job.id -LineSpeaker $job.speaker -LineText $job.text -LineVoice $lineVoice
  $manifest += $result
  Write-Output $result.out
  if ($DelaySeconds -gt 0) {
    Start-Sleep -Seconds $DelaySeconds
  }
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$manifestPath = Join-Path $OutDir "manifest.json"
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Output $manifestPath
