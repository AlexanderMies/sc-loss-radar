# Loss Radar — South Carolina

Automated lead detection for commercial restoration work. Watches South
Carolina news, weather alerts, and public safety feeds for fire, water, smoke
and mold losses at commercial and institutional properties, scores them, and
puts the results on a triage board.

Replaces the manual Google News keyword routine.

---

## How it fits together

GitHub Pages is static hosting — it can't run anything on a schedule. So the
architecture is:

```
GitHub Actions (every 20 min)          <- this is the backend
   |
   +- fetch: Google News RSS, SC newsroom feeds, NWS alerts
   +- locate: drop anything not in South Carolina
   +- dedupe: collapse 8 outlets covering 1 fire into 1 event
   +- score: keyword rules, then an optional model pass
   +- commit docs/data/leads.json back to the repo
                    |
GitHub Pages serves docs/  <- static page that fetches that JSON
```

No server, no database, no hosting bill.

**`leads.json` lives inside `docs/`** because Pages only serves files from the
publish directory. A sibling `data/` folder 404s at runtime. The unserved
`data/archive/` holds the historical record for backtesting.

---

## Setup

1. **Push the repo** (commands at the bottom of this file).

2. **Turn on Pages.** Settings → Pages → Source: *Deploy from a branch* →
   Branch `main`, folder `/docs` → Save. The URL appears within a minute or two.

3. **Let Actions write to the repo.** Settings → Actions → General →
   Workflow permissions → *Read and write permissions* → Save. Without this the
   commit step fails with a 403.

4. **First run.** Actions tab → *Collect leads* → Run workflow. Scheduled runs
   on a new repo sometimes don't start until you've triggered one manually.

5. **Optional — the model pass.** Settings → Secrets and variables → Actions →
   New repository secret, named `ANTHROPIC_API_KEY`. Without it everything still
   works; you just get rule scores and no commercial/residential column. At your
   volume expect a few dollars a month.

### Running locally

```bash
pip install -r requirements.txt
python -m pipeline.run --no-llm     # rules only
python -m pipeline.run              # with the model pass, needs the key in env

cd docs && python -m http.server 8000    # board at localhost:8000
```

`python scripts/preview.py` loads fabricated sample leads so you can work on the
board's design without waiting for a collection run. `--clear` empties it again.

---

## The repo is public

Anyone can read your lead list, including competitors. Making it private costs
about $4/month (GitHub Pro) — Pages on private repos needs a paid plan. Worth it
once this is producing leads you actually chase.

---

## Tuning the scorer

**This is the part that determines whether the system is useful.** Everything in
`config/scoring.yaml` is a starting guess, not a tuned model.

The honest way to do it:

1. Let it run a couple of weeks. The archive in `data/archive/` accumulates
   everything it saw.
2. Go through 50–100 of those rows and mark each one: *would I have called this?*
3. Compare your answers to the tier the system assigned. Every disagreement
   points at a specific rule.
4. Adjust weights and terms in `config/scoring.yaml`. Committing to `config/`
   re-triggers the workflow automatically.

Without step 2 you're guessing, and you'll end up with either a board full of
noise or one that quietly misses the jobs worth having.

### Where to look first

- **Misses** usually mean a missing term. SC newsrooms have their own phrasing —
  add what they actually write.
- **False positives** usually mean a missing penalty. Add the term to
  `penalties.not_a_loss`.
- **Right story, wrong tier** means a weight is off, not a term.

### Files you'll edit

| File | What it controls |
|---|---|
| `config/queries.yaml` | Google News search terms |
| `config/outlets.yaml` | Which newsrooms and feeds get polled |
| `config/scoring.yaml` | Weights, penalties, tier thresholds, freshness decay |

---

## Known limits

**The dashboard is the wrong primary interface.** Restoration leads go stale in
hours and whoever calls first usually wins. A page you have to remember to open
is a weak fit for that. Add an alert path — the workflow can post to Slack,
email, or SMS when something crosses the priority threshold — and treat the
board as the review surface for everything below that bar. This is the highest-
value thing to build next.

**Actions scheduling is best-effort.** Cron entries can lag 5–20 minutes at peak
times, and GitHub disables schedules on repos with no activity for 60 days. If
you need dependable freshness, run the same pipeline on a cheap VPS cron and
keep Actions as the fallback.

**Feed URLs rot.** When an outlet redesigns its site, its RSS path changes and
the fetch starts failing silently. The collector logs per-feed item counts every
run — a feed sitting at zero for several days is a dead URL, not a quiet news
week. Check the Actions logs occasionally.

**Some outlets block automated requests.** A few of the feeds in
`outlets.yaml` return 403 to non-browser clients. Those are logged as warnings
and skipped; Google News usually picks up the same stories, just later. If a
market matters to you and its feed is blocked, that's a candidate for a
different approach.

**Geographic coverage is partial.** `pipeline/geo.py` has the SC cities I could
enumerate, not all of them. If leads from a town keep getting dropped, add it to
`SC_CITIES` with its county.

**Scoring is automated and imperfect.** It's a triage aid. Verify before
dispatching a crew.

---

## Push it to GitHub

Create an empty repo on github.com first — no README, no .gitignore, no license,
or the first push will conflict. Then:

```bash
cd sc-loss-radar
git init
git add .
git commit -m "Initial commit: SC commercial loss lead collector"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/sc-loss-radar.git
git push -u origin main
```

Then do steps 2–4 under Setup above.
