# Devpost submission checklist

Re-read the Rules and Resources tabs on the hackathon page before submitting. Items marked (verify) are my reading of the rules, not confirmed.

## Code and repo
- [ ] Repo is public on GitHub (verify the repo name and visibility)
- [ ] `LICENSE` is MIT and `[YOUR NAME]` is replaced
- [ ] `.env` is NOT committed (only `.env.example`)
- [ ] No API keys in the git history (`git log -p | grep -i nebius_api_key`)
- [ ] `pytest` passes on a clean clone
- [ ] `paperwork models` run with a real key; `NEBIUS_MODEL` set to a listed NVIDIA Nemotron id
- [ ] One real `paperwork explain demo/sample_letter.txt` run against Nebius works end to end
- [ ] README "Verified vs not verified" updated after the live run

## Hackathon requirements (verify each on the Rules tab)
- [ ] Runs on Nebius Token Factory or AI Cloud
- [ ] Uses at least one NVIDIA open source model (Nemotron)
- [ ] Track chosen: Personal AI
- [ ] Any sponsor tools the Rules make mandatory are included

## Demo video
- [ ] Under 3 minutes (check the exported file length, not just the timeline)
- [ ] Shows the real product running, not slides only
- [ ] Mentions Nebius Token Factory and NVIDIA Nemotron
- [ ] States the privacy limits honestly (data minimisation, not anonymisation)
- [ ] Uploaded as public or unlisted and the link opens when logged out

## Devpost page
- [ ] Project name, tagline and description filled in
- [ ] Repo link and video link added
- [ ] "Built with" lists Nebius Token Factory, NVIDIA Nemotron, Python, SQLite
- [ ] Only synthetic data appears in screenshots and video
- [ ] Submitted before the deadline (verify the time zone)
