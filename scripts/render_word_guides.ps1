param(
    [Parameter(Mandatory=$true)][string]$InputDirectory,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
# File conversion only: a private invisible Word instance; existing Word windows are untouched.
$ErrorActionPreference = 'Stop'
$wordConverter = $null
try {
    $wordConverter = New-Object -ComObject Word.Application
    $wordConverter.Visible = $false
    $wordConverter.DisplayAlerts = 0
    $wordConverter.AutomationSecurity = 3
    $resolvedInput = (Resolve-Path -LiteralPath $InputDirectory).Path
    $absoluteOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
    [System.IO.Directory]::CreateDirectory($absoluteOutput) | Out-Null
    foreach ($sourceFile in Get-ChildItem -LiteralPath $resolvedInput -Filter '*.docx' -Recurse -File) {
        $destinationDirectory = Join-Path $absoluteOutput $sourceFile.BaseName
        [System.IO.Directory]::CreateDirectory($destinationDirectory) | Out-Null
        $pdfPath = Join-Path $destinationDirectory ($sourceFile.BaseName + '.pdf')
        $wordDocument = $null
        try {
            $wordDocument = $wordConverter.Documents.Open($sourceFile.FullName, $false, $true, $false)
            $wordDocument.Fields.Update() | Out-Null
            $wordDocument.Repaginate()
            $pages = $wordDocument.ComputeStatistics(2)
            $wordDocument.ExportAsFixedFormat($pdfPath, 17)
            Write-Output ($sourceFile.BaseName + ' | pages=' + $pages + ' | ' + $pdfPath)
        } finally {
            if ($null -ne $wordDocument) {
                $wordDocument.Close(0)
                [System.Runtime.InteropServices.Marshal]::ReleaseComObject($wordDocument) | Out-Null
            }
        }
    }
} finally {
    if ($null -ne $wordConverter) {
        $wordConverter.Quit()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($wordConverter) | Out-Null
    }
}
