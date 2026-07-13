<#
    WR-0152 Phase 1 Discovery - Section 2 & part of Section 3: Power BI

    Covers:
      - Power BI workspaces
      - Capacity usage (shared vs Premium)
      - Workspace ownership model (personal vs enterprise)
      - Dataset locations (central vs siloed) + data sources (SQL, SharePoint, APIs, external)
      - Duplicate datasets (heuristic: same dataset name across multiple workspaces)

    Requires: MicrosoftPowerBIMgmt
    Permissions: Power BI Service Administrator (or Global Admin).
    Note: the workspace scan (datasources, dataset lineage) uses the Admin "metadata scanning" API
    (Get Info / scanStatus / scanResult). This must be enabled under
    Admin Portal > Tenant settings > Developer settings > "Enhanced admin API responses for
    PBI content metadata (Preview)". If it isn't enabled, dataset/datasource detail will be skipped.
#>

param(
    [string]$OutputFolder = (New-DiscoveryOutputFolder),
    [int]$ScanBatchSize = 100,
    [int]$ScanPollSeconds = 5,
    [int]$ScanTimeoutSeconds = 300
)

. "$PSScriptRoot/Common.ps1"
Connect-PBIAdmin

Write-Host "Collecting Power BI capacities..."
$capacities = Get-PowerBICapacity -Scope Organization
$capacityLookup = @{}
foreach ($c in $capacities) { $capacityLookup[$c.Id] = $c }

$capacityResults = foreach ($c in $capacities) {
    [PSCustomObject]@{
        CapacityId  = $c.Id
        DisplayName = $c.DisplayName
        Sku         = $c.Sku
        State       = $c.State
        Region      = $c.Region
        Admins      = ($c.Admins -join '; ')
    }
}
Export-Discovery -Data $capacityResults -OutputFolder $OutputFolder -Name "02-PowerBI-Capacities"

Write-Host "Collecting Power BI workspaces..."
$workspaces = Get-PowerBIWorkspace -Scope Organization -All | Where-Object { $_.State -eq 'Active' }

$workspaceResults = foreach ($ws in $workspaces) {
    $capacityName = if ($ws.CapacityId -and $capacityLookup.ContainsKey($ws.CapacityId)) {
        $capacityLookup[$ws.CapacityId].DisplayName
    } else { $null }

    [PSCustomObject]@{
        WorkspaceId      = $ws.Id
        Name             = $ws.Name
        Type             = $ws.Type                 # Workspace (enterprise) vs PersonalGroup
        OwnershipModel   = if ($ws.Type -eq 'PersonalGroup') { 'Personal' } else { 'Enterprise' }
        CapacityUsage    = if ($ws.CapacityId) { "Premium ($capacityName)" } else { "Shared" }
        IsOnDedicatedCapacity = [bool]$ws.CapacityId
        State            = $ws.State
    }
}
Export-Discovery -Data $workspaceResults -OutputFolder $OutputFolder -Name "02-PowerBI-Workspaces"

# --- Dataset / datasource lineage via the Admin metadata scanning API ---
Write-Host "Running metadata scan for datasets, reports and data sources (this can take a few minutes)..."

$workspaceIds = @($workspaces | Select-Object -ExpandProperty Id)
$allScanResults = @()

for ($i = 0; $i -lt $workspaceIds.Count; $i += $ScanBatchSize) {
    $batch = $workspaceIds[$i..([Math]::Min($i + $ScanBatchSize - 1, $workspaceIds.Count - 1))]
    $body = @{ workspaces = $batch } | ConvertTo-Json

    try {
        $scan = Invoke-PowerBIRestMethod -Url "admin/workspaces/getInfo?lineage=true&datasourceDetails=true&getArtifactUsers=false" -Method Post -Body $body | ConvertFrom-Json
    } catch {
        Write-Warning "Scanner API call failed for batch starting at index $i : $($_.Exception.Message)"
        continue
    }

    $elapsed = 0
    do {
        Start-Sleep -Seconds $ScanPollSeconds
        $elapsed += $ScanPollSeconds
        $status = Invoke-PowerBIRestMethod -Url "admin/workspaces/scanStatus/$($scan.id)" -Method Get | ConvertFrom-Json
    } while ($status.status -notin @('Succeeded', 'Failed') -and $elapsed -lt $ScanTimeoutSeconds)

    if ($status.status -ne 'Succeeded') {
        Write-Warning "Scan $($scan.id) did not complete successfully (status: $($status.status)) - skipping batch."
        continue
    }

    $result = Invoke-PowerBIRestMethod -Url "admin/workspaces/scanResult/$($scan.id)" -Method Get | ConvertFrom-Json
    $allScanResults += $result.workspaces
}

$datasetResults = foreach ($ws in $allScanResults) {
    foreach ($ds in $ws.datasets) {
        [PSCustomObject]@{
            WorkspaceId   = $ws.id
            WorkspaceName = $ws.name
            DatasetId     = $ds.id
            DatasetName   = $ds.name
            ConfiguredBy  = $ds.configuredBy
            DataSources   = ($ds.datasourceUsages | ForEach-Object { $_.datasourceInstance.datasourceType }) -join '; '
        }
    }
}
Export-Discovery -Data $datasetResults -OutputFolder $OutputFolder -Name "02-PowerBI-Datasets"

if ($datasetResults) {
    $duplicates = $datasetResults | Group-Object DatasetName | Where-Object { $_.Count -gt 1 } |
        ForEach-Object {
            [PSCustomObject]@{
                DatasetName = $_.Name
                Occurrences = $_.Count
                Workspaces  = ($_.Group.WorkspaceName -join '; ')
            }
        }
    Export-Discovery -Data $duplicates -OutputFolder $OutputFolder -Name "02-PowerBI-DuplicateDatasets-Heuristic"
    Write-Host "Note: duplicate-dataset detection is name-based only; verify true duplication (schema/source) manually." -ForegroundColor Yellow
}

$reportResults = foreach ($ws in $allScanResults) {
    foreach ($r in $ws.reports) {
        [PSCustomObject]@{
            WorkspaceId   = $ws.id
            WorkspaceName = $ws.name
            ReportId      = $r.id
            ReportName    = $r.name
            DatasetId     = $r.datasetId
        }
    }
}
Export-Discovery -Data $reportResults -OutputFolder $OutputFolder -Name "02-PowerBI-Reports"
