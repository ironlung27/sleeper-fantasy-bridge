# Sleeper Fantasy Data Bridge

Automatically refreshes public Sleeper league data for two fantasy leagues and writes analysis-ready JSON files.

## Included leagues

- `1389130395563327488` → `data/full_ppr_10_team.json`
- `1389736155972390912` → `data/half_ppr_12_team.json`

## What it collects

- NFL state/current week
- League settings and scoring
- All managers and rosters
- Starters, bench/reserve, taxi
- Current-week matchups and opponents
- Current-week transactions
- Waiver position / FAAB fields supplied by Sleeper
- Trending adds and drops that are actually unrostered
- Fantasy-relevant unrostered players
- Sleeper injury/status/depth-chart metadata

## Setup

1. Create a new GitHub repository. A public repo is simplest if ChatGPT needs to read the generated JSON without authentication.
2. Upload the contents of this project to the repository root.
3. In GitHub, open **Settings → Actions → General → Workflow permissions** and enable **Read and write permissions**.
4. Open **Actions → Refresh Sleeper fantasy data → Run workflow** once.
5. Confirm these files appear:
   - `data/index.json`
   - `data/full_ppr_10_team.json`
   - `data/half_ppr_12_team.json`
6. The workflow then refreshes every six hours automatically.

No Sleeper API key or login is required. Sleeper's API is read-only.

## Stable raw-data URLs

After publishing the repo, the raw files can be read at URLs shaped like:

`https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/YOUR_REPO/main/data/index.json`

`https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/YOUR_REPO/main/data/full_ppr_10_team.json`

`https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/YOUR_REPO/main/data/half_ppr_12_team.json`

Replace `YOUR_GITHUB_USERNAME` and `YOUR_REPO`.

## Refresh frequency

The workflow runs every six hours at minute 17. You can change the cron in `.github/workflows/refresh.yml`.

## Notes

The `free_agents` array is derived by subtracting every rostered player ID from Sleeper's NFL player database. Availability is therefore league-specific. Current NFL news should still be checked separately because Sleeper's player injury metadata may lag breaking reports.
