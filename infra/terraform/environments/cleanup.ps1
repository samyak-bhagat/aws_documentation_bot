# Cleanup old dev folder after state backup
# Run this script after closing all terraform.tfstate files in your editor

$devFolder = "d:\aws_documentation_bot\infra\terraform\environments\dev"

if (Test-Path $devFolder) {
    Write-Host "Removing old dev folder: $devFolder"
    Remove-Item -Path $devFolder -Recurse -Force
    Write-Host "✓ Cleanup complete"
} else {
    Write-Host "✓ dev folder already removed"
}

Write-Host "`nCurrent environments structure:"
Get-ChildItem d:\aws_documentation_bot\infra\terraform\environments -Force | Select-Object Name, Mode
