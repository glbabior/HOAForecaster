# Open a workbook in Microsoft Excel (Windows only) and report whether Excel had to repair it.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\excel_check.ps1 -Path book.xlsx [-ChartDir dir]
#
# Excel writes an error*.xml log to %TEMP% whenever it repairs a file on open; any new log
# means the workbook would show the user a repair prompt. Prints "opened", then "no repair log"
# or "REPAIR LOG" with its contents. With -ChartDir, also renders every chart to PNG there.
param([Parameter(Mandatory)][string]$Path, [string]$ChartDir)

$before = @(Get-ChildItem $env:TEMP -Filter "error*.xml" -ErrorAction SilentlyContinue | ForEach-Object FullName)
$xl = New-Object -ComObject Excel.Application
$xl.DisplayAlerts = $false
$xl.AutomationSecurity = 3  # msoAutomationSecurityForceDisable – never run a file's macros
$xl.Visible = $false
try {
    $wb = $xl.Workbooks.Open((Resolve-Path $Path).Path, 0, $true)
    $xl.CalculateFull()
    "opened"
    if ($ChartDir) {
        $i = 0
        foreach ($ws in $wb.Worksheets) {
            foreach ($co in $ws.ChartObjects()) {
                $i++
                [void]$co.Chart.Export((Join-Path $ChartDir ("chart_{0:d2}.png" -f $i)))
            }
        }
        "rendered $i charts"
    }
    $wb.Close($false)
}
finally {
    $xl.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
}
$new = @(Get-ChildItem $env:TEMP -Filter "error*.xml" -ErrorAction SilentlyContinue |
    ForEach-Object FullName | Where-Object { $before -notcontains $_ })
if ($new.Count) { "REPAIR LOG"; Get-Content $new } else { "no repair log" }
