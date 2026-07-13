<#
    WR-0152 Phase 1 Discovery - Section 4: Access Model & Security Controls

    Covers:
      - Who can create: Apps / Flows / Workspaces (environment-level maker/admin role assignments)
      - Approval process maturity (flagged as manual/interview item - see notes below)
      - DLP Policies
      - Conditional Access (policies scoped to Power Apps / Power Automate / Dataverse)
      - External Sharing (flagged as manual/portal item - see notes below)

    Requires: Microsoft.PowerApps.Administration.PowerShell, Microsoft.Graph.Identity.SignIns
    Permissions: Power Platform Administrator for DLP/roles; Conditional Access Administrator or
                 Global Reader (Policy.Read.All) for reading Conditional Access policies.
#>

param(
    [string]$OutputFolder = (New-DiscoveryOutputFolder)
)

. "$PSScriptRoot/Common.ps1"
Connect-PPAdmin

Write-Host "Collecting environment role assignments (who can create apps/flows)..."
$environments = Get-AdminPowerAppEnvironment
$roleResults = foreach ($env in $environments) {
    Get-AdminPowerAppEnvironmentRoleAssignment -EnvironmentName $env.EnvironmentName -ErrorAction SilentlyContinue |
        ForEach-Object {
            [PSCustomObject]@{
                EnvironmentName = $env.DisplayName
                RoleName        = $_.RoleName          # e.g. Environment Admin, Environment Maker
                PrincipalType   = $_.PrincipalType      # User / Group / Tenant (everyone)
                PrincipalName   = $_.PrincipalDisplayName
            }
        }
}
Export-Discovery -Data $roleResults -OutputFolder $OutputFolder -Name "04-EnvironmentRoleAssignments"

Write-Host "Collecting DLP policies..."
$dlpPolicies = Get-AdminDlpPolicy
$dlpResults = foreach ($policy in $dlpPolicies) {
    [PSCustomObject]@{
        PolicyName        = $policy.DisplayName
        PolicyId          = $policy.PolicyName
        CreatedBy         = $policy.CreatedBy.displayName
        LastModifiedTime  = $policy.LastModifiedTime
        EnvironmentScope  = $policy.EnvironmentType   # AllEnvironments / ExceptEnvironments / OnlyEnvironments
        Environments      = ($policy.Environments.Name -join '; ')
        BusinessConnectors    = ($policy.ConnectorGroups | Where-Object { $_.classification -eq 'Confidential' } | Select-Object -ExpandProperty connectors | Select-Object -ExpandProperty name) -join '; '
        NonBusinessConnectors = ($policy.ConnectorGroups | Where-Object { $_.classification -eq 'General' } | Select-Object -ExpandProperty connectors | Select-Object -ExpandProperty name) -join '; '
        BlockedConnectors     = ($policy.ConnectorGroups | Where-Object { $_.classification -eq 'Blocked' } | Select-Object -ExpandProperty connectors | Select-Object -ExpandProperty name) -join '; '
    }
}
Export-Discovery -Data $dlpResults -OutputFolder $OutputFolder -Name "04-DlpPolicies"

Write-Host "Collecting Conditional Access policies scoped to Power Platform workloads..."
try {
    Connect-GraphAdmin -Scopes @("Policy.Read.All")
    $caPolicies = Get-MgIdentityConditionalAccessPolicy -All

    $caResults = foreach ($policy in $caPolicies) {
        $includedApps = $policy.Conditions.Applications.IncludeApplications
        $matched = $Script:PowerPlatformAppIds.GetEnumerator() | Where-Object { $includedApps -contains $_.Value -or $includedApps -contains 'All' }

        if ($matched) {
            [PSCustomObject]@{
                PolicyName     = $policy.DisplayName
                State          = $policy.State              # enabled / disabled / enabledForReportingButNotEnforced
                MatchedWorkload = ($matched.Key -join '; ')
                GrantControls  = ($policy.GrantControls.BuiltInControls -join '; ')
                IncludedUsers  = ($policy.Conditions.Users.IncludeUsers -join '; ')
                IncludedGroups = ($policy.Conditions.Users.IncludeGroups -join '; ')
            }
        }
    }
    Export-Discovery -Data $caResults -OutputFolder $OutputFolder -Name "04-ConditionalAccess-PowerPlatform"
} catch {
    Write-Warning "Could not read Conditional Access policies: $($_.Exception.Message). Requires Conditional Access Administrator or Global Reader role."
}

Write-Host ""
Write-Host "Items in this section that require manual follow-up (not reliably queryable via API):" -ForegroundColor Yellow
Write-Host " - Approval process maturity: interview Business Engagement team on how the app/flow access business case process actually operates day-to-day." -ForegroundColor Yellow
Write-Host " - External sharing limits: Admin Center > Power Platform > Policies > Sharing limits (tenant-wide and per-environment 'share with security groups' settings are not exposed via this module)." -ForegroundColor Yellow
