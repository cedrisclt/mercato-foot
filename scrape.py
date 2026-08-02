#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scrape every competition in config/competitions.py and write one
normalized JSON snapshot per competition into data/<CODE>.json.

Usage:
    python scrape.py             # scrape online
    python scrape.py --offline   # reuse scraper/.cache
    python scrape.py --squads-only
"""
import os
import sys
import json
import time
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.competitions import COMPETITIONS, SEASON
from scraper import transfermarkt as tm

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

HISTORY_SEASONS = 10  # backfilled once, then only SEASON itself is re-scraped
SEASON_RANGE = list(range(SEASON - HISTORY_SEASONS + 1, SEASON + 1))


def state_path(code):
    return os.path.join(DATA, f"{code}.json")


def load_state(code):
    p = state_path(code)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {}


def key(club_code, direction, t):
    return f"{club_code}|{direction}|{t['p']}|{t['club']}"


def get_club_fixtures(club, old_fixtures, offline):
    """Backfill whichever of the last HISTORY_SEASONS aren't already stored
    (the first time a club is seen, that's all of them), and always
    re-scrape the current SEASON since it's the only one still changing.
    Seasons older than the window are left untouched once fetched, so the
    archive only grows over time instead of being re-fetched or pruned."""
    if not isinstance(old_fixtures, list):
        old_fixtures = []  # migrate from the old {"results","upcoming"} shape
    old_seasons = {m["season"] for m in old_fixtures}
    missing = [s for s in SEASON_RANGE if s not in old_seasons or s == SEASON]
    if len(missing) > 1:
        print(f"    ↻ backfill {len(missing)} saisons ({missing[0]}-{missing[-1]})")
    kept = [m for m in old_fixtures if m["season"] not in missing]
    fetched = []
    for s in missing:
        fetched.extend(tm.get_fixtures(club, s, offline))
        if not offline:
            time.sleep(1.0)
    return kept + fetched


def get_competition_standings(comp, old_standings, offline):
    """Same incremental-backfill strategy as get_club_fixtures, but per
    competition (one table per season, not per club) — far cheaper."""
    old_seasons = {int(s) for s in old_standings.keys()}
    missing = [s for s in SEASON_RANGE if s not in old_seasons or s == SEASON]
    if len(missing) > 1:
        print(f"  ↻ backfill classements {len(missing)} saisons ({missing[0]}-{missing[-1]})")
    out = {str(s): v for s, v in old_standings.items() if int(s) not in missing}
    for s in missing:
        out[str(s)] = tm.get_standings(comp, s, offline)
        if not offline:
            time.sleep(1.0)
    return out


def scrape_competition(comp, offline=False, squads_only=False):
    print(f"\n=== {comp['name']} ({comp['code']}) ===")
    old = load_state(comp["code"])
    old_seen = old.get("seen", {})
    old_clubs_by_code = {c["code"]: c for c in old.get("clubs", [])}

    print("· liste des clubs …")
    clubs = tm.get_clubs(comp, SEASON, offline)
    if not clubs:
        print("  !! échec récupération des clubs, on garde l'ancien état")
        return old

    clubs_out = []
    for c in clubs:
        print(f"· {c['name']} ({c['code']}) …")
        accent = tm.accent_color(c["logo_url"], offline)
        squad = tm.get_squad(c, SEASON, offline)
        info = tm.get_club_info(c, offline)
        honours = tm.get_honours(c, offline)
        old_fixtures = old_clubs_by_code.get(c["code"], {}).get("fixtures", [])
        fixtures = get_club_fixtures(c, old_fixtures, offline)
        entry = {"code": c["code"], "name": c["name"], "slug": c["slug"],
                 "id": c["id"], "logo_url": c["logo_url"], "accent": accent,
                 "squad": squad, "info": info, "honours": honours,
                 "fixtures": fixtures}
        if not squads_only:
            arr, dep = tm.get_transfers(c, SEASON, offline)
            entry["arr"], entry["dep"] = arr, dep
        else:
            old_c = old_clubs_by_code.get(c["code"], {})
            entry["arr"], entry["dep"] = old_c.get("arr", []), old_c.get("dep", [])
        clubs_out.append(entry)
        if not offline:
            time.sleep(1.0)

    latest = []
    if not squads_only:
        print("· derniers transferts …")
        club_ids = {c["id"]: c["code"] for c in clubs}
        latest = tm.get_latest_transfers(comp, club_ids, offline)

    print("· classements …")
    standings = get_competition_standings(comp, old.get("standings", {}), offline)

    today = date.today().isoformat()
    seen = {}
    for c in clubs_out:
        for direction, lst in (("in", c["arr"]), ("out", c["dep"])):
            for t in lst:
                k = key(c["code"], direction, t)
                fs = old_seen.get(k, today)
                seen[k] = fs
                t["fs"] = fs
    for t in latest:
        k = key(t["club_code"], "in", t)
        t["fs"] = seen.get(k, today)

    out = {
        "code": comp["code"], "name": comp["name"], "season": SEASON,
        "updated": datetime.now().isoformat(timespec="seconds"),
        "clubs": clubs_out, "latest": latest[:10], "seen": seen,
        "standings": standings,
    }
    json.dump(out, open(state_path(comp["code"]), "w", encoding="utf-8"),
               ensure_ascii=False, indent=1)
    na = sum(len(c["arr"]) for c in clubs_out)
    nd = sum(len(c["dep"]) for c in clubs_out)
    print(f"✓ {comp['code']} : {len(clubs_out)} clubs, {na} arrivées, {nd} départs")
    return out


def main():
    offline = "--offline" in sys.argv
    squads_only = "--squads-only" in sys.argv
    for comp in COMPETITIONS:
        scrape_competition(comp, offline, squads_only)


if __name__ == "__main__":
    main()
