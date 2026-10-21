# Сборка Orthofill для Windows.
# Запуск:  powershell -ExecutionPolicy Bypass -File build.ps1
# Нужен только интернет: uv сам скачает Python и библиотеки.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what — ошибка (код $LASTEXITCODE)" } }
function SelfTest($exe) {
    # окно с темой создаётся и закрывается — значит tkinter и тема попали в сборку
    $p = Start-Process $exe -ArgumentList '--selftest-ui' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Самопроверка $exe не прошла (код $($p.ExitCode))" }
    Write-Host "Самопроверка $exe — OK" -ForegroundColor Green
}

Step 'uv'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
uv --version; Check 'uv'

Step 'Python и библиотеки'
uv sync --group dev; Check 'uv sync'

Step 'Тесты'
uv run pytest -q; Check 'Тесты не прошли — сборка остановлена'

Step 'Версия и код сборки'
# имя файлов — из версии программы: «0.1 beta 2» → 0.1beta2
$Version = (uv run python -c "import orthofill; print(orthofill.VERSION_LABEL.replace(' ', ''))").Trim()
Check 'Чтение версии'
$sha = 'nogit'
if (Get-Command git -ErrorAction SilentlyContinue) {
    $sha = (git rev-parse --short HEAD).Trim()
    if (git status --porcelain --untracked-files=no) { $sha = "$sha+изм" }
}
$build = "$sha · $(Get-Date -Format 'yyyy-MM-dd')"
# код сборки зашивается в exe — виден в заголовке окна
[IO.File]::WriteAllText("$PSScriptRoot\orthofill\_build.py", "BUILD = '$build'`n", (New-Object Text.UTF8Encoding $false))
Write-Host "Версия $Version, сборка $build"

$common = @('--noconfirm', '--clean', '--windowed', '--paths', '.',
            '--icon', 'assets\orthofill.ico',
            '--add-data', 'assets\orthofill.ico;assets',
            '--collect-data', 'sv_ttk')

try {
    Step 'Портативная версия (папка)'
    Remove-Item -Recurse -Force dist\Orthofill, "dist\Orthofill-$Version-portable.zip" -ErrorAction SilentlyContinue
    uv run pyinstaller @common --name Orthofill --workpath build\portable orthofill\__main__.py
    Check 'PyInstaller (папка)'
    SelfTest dist\Orthofill\Orthofill.exe
    Copy-Item order.xlsx dist\Orthofill\order.xlsx      # пример классификатора с эталоном
    Copy-Item README.md dist\Orthofill\README.md
    Compress-Archive -Path dist\Orthofill -DestinationPath "dist\Orthofill-$Version-portable.zip" -Force

    Step 'Exe одним файлом'
    uv run pyinstaller @common --onefile --name "Orthofill-$Version" --workpath build\onefile orthofill\__main__.py
    Check 'PyInstaller (один файл)'
    SelfTest "dist\Orthofill-$Version.exe"
} finally {
    # иначе запуск из папки проекта показывал бы код этой сборки, а не текущий
    Remove-Item orthofill\_build.py -ErrorAction SilentlyContinue
}

Step 'Готово'
Get-Item "dist\Orthofill-$Version-portable.zip", "dist\Orthofill-$Version.exe" |
    Format-Table Name, @{n='МБ'; e={[math]::Round($_.Length / 1MB, 1)}}
