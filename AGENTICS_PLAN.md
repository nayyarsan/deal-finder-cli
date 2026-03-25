# Agentics Plan — deal-finder-cli

Add [GitHub Agentic Workflows](https://github.com/githubnext/agentics) to maintain this deal intelligence engine.

## Prerequisites

```bash
gh extension install github/gh-aw
```

## Workflows to Add

- [ ] **Repo Assist** — triages issues, investigates bugs, proposes improvements on a schedule
  ```bash
  gh aw add-wizard githubnext/agentics/repo-assist
  ```

- [ ] **CI Doctor** — monitors CI failures; critical since this feeds the live WhatsApp pipeline
  ```bash
  gh aw add-wizard githubnext/agentics/ci-doctor
  ```

- [ ] **Daily Perf Improver** — identifies latency in deal-fetching and price-ranking pipelines
  ```bash
  gh aw add-wizard githubnext/agentics/daily-perf-improver
  ```

- [ ] **Daily Test Improver** — grows test coverage for price tracking and buy/hold verdict logic
  ```bash
  gh aw add-wizard githubnext/agentics/daily-test-improver
  ```

- [ ] **Daily Malicious Code Scan** — scans Python deps for supply-chain risks
  ```bash
  gh aw add-wizard githubnext/agentics/daily-malicious-code-scan
  ```

- [ ] **Issue Triage** — auto-labels incoming issues and PRs
  ```bash
  gh aw add-wizard githubnext/agentics/issue-triage
  ```

- [ ] **Repo Ask** (`/repo-ask` command) — on-demand research into codebase behaviour
  ```bash
  gh aw add-wizard githubnext/agentics/repo-ask
  ```

- [ ] **Plan** (`/plan` command) — breaks big issues into tracked sub-tasks
  ```bash
  gh aw add-wizard githubnext/agentics/plan
  ```

## Keep Workflows Updated

```bash
gh aw upgrade
gh aw update
```
