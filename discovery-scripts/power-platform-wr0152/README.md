# WR-0152 Power Platform Discovery Scripts

PowerShell scripts to automate the Phase 1 discovery items from DHSC Work Request **WR-0152 (Power Platform Discovery)**. They pull tenant-wide inventory data so the qualitative/ownership follow-up work (interviews, business-criticality classification) can focus on what can't be queried automatically.

## Mapping to WR-0152 Phase 1

| Script | WR-0152 section |
|---|---|
| `01-Environments.ps1` | 1. Environments |
| `02-PowerBI.ps1` | 2. Power BI |
| `03-Assets.ps1` | 3. Asset Discovery (Power Apps, Power Automate, cross-workload dependencies) |
| `04-AccessSecurity.ps1` | 4. Access Model & Security Controls (DLP, Conditional Access, maker/admin roles) |

Run all four with `Run-AllDiscovery.ps1`, or run any script individually.

## Prerequisites

- PowerShell 7+
- Modules (install once):
  ```powershell
  Install-Module Microsoft.PowerApps.Administration.PowerShell -Scope CurrentUser
  Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser
  Install-Module Microsoft.Graph -Scope CurrentUser
  Install-Module Az.Accounts -Scope CurrentUser   # only needed for model-driven app lookup in 03-Assets.ps1
  ```
- Permissions:
  - **Power Platform Administrator** (or Global Admin) — environments, DLP policies, role assignments, apps/flows across the tenant.
  - **Power BI Service Administrator** — workspace/capacity inventory and the metadata scanner API.
  - **Conditional Access Administrator** or **Global Reader** (`Policy.Read.All`) — reading Conditional Access policies.
- Power BI tenant setting **"Enhanced admin API responses for PBI content metadata (Preview)"** must be enabled for `02-PowerBI.ps1` to return dataset/data-source detail via the scanner API.

Each script prompts for interactive sign-in on first use (`Add-PowerAppsAccount`, `Connect-PowerBIServiceAccount`, `Connect-MgGraph`). Use an account with the roles above.

## Usage

```powershell
cd discovery-scripts/power-platform-wr0152
./Run-AllDiscovery.ps1 -OutputPath ./output
```

Output is written per-run to a timestamped folder (`output/yyyyMMdd-HHmmss/`) as both CSV and JSON per data set, so results can be dropped straight into a findings report or spreadsheet.

## What these scripts can't tell you

The WR asks for some judgement calls that no API exposes directly. Each script flags these in its output with a warning; they're called out here so they aren't missed when compiling the discovery findings:

- **Environment purpose** (business system vs end-user vs legacy) — `01-Environments.ps1` gives a naming/default-environment heuristic only; confirm with environment owners.
- **App/flow business-criticality vs personal productivity** — inferred loosely from Dataverse/Power BI/flow linkage in `03-Assets.ps1`; needs owner confirmation.
- **Approval process maturity** — not queryable; interview the Business Engagement team.
- **External sharing limits** — not exposed by the PowerShell modules used here; check Power Platform Admin Center > Policies > Sharing limits.
- **Desktop flows (RPA)** — `Get-AdminFlow` only returns cloud flows; pull desktop flow inventory from the Power Automate admin center.

## Recommendation for Phase 2/3

Microsoft's [Center of Excellence (CoE) Starter Kit](https://learn.microsoft.com/power-platform/guidance/coe/starter-kit) automates ongoing inventory of exactly these assets (environments, apps, flows, connectors) into Dataverse and is the standard basis for the tiered support model and MI/usage-insights work described in Phase 2 and Phase 3 of WR-0152. These one-off discovery scripts are a fast path for the Phase 1 snapshot; the CoE kit is worth evaluating as the ongoing mechanism once Phase 2 governance work starts, rather than maintaining bespoke scripts long-term.
