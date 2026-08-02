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
        fixtures = tm.get_fixtures(c, SEASON, offline)
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
