#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render data/<CODE>.json -> public/ static HTML site.

Pure presentation layer: reads only the JSON snapshots, never touches the
network, so the site can be rebuilt anytime without rescraping.
"""
import os
import sys
import json
import shutil
import hashlib
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
TEMPLATES = os.path.join(ROOT, "site", "templates")
STATIC = os.path.join(ROOT, "site", "static")
PUBLIC = os.path.join(ROOT, "public")

sys.path.insert(0, ROOT)
from config.competitions import COMPETITIONS


def fmt_money(value, signed=False):
    v = round(value or 0, 3)
    if v == 0:
        return ("+0 K€" if signed else "0 K€")
    sign = ""
    if signed:
        sign = "+" if v > 0 else "−"
    av = abs(v)
    if av < 1:
        txt = f"{round(av * 1000)} K€"
    else:
        v1 = round(av, 1)
        if v1 == int(v1):
            txt = f"{int(v1)} M€"
        else:
            txt = f"{v1}".replace(".", ",") + " M€"
    return sign + txt


def fmt_fee(t):
    typ, val = t.get("type"), t.get("val", 0)
    if typ == "paid":
        return fmt_money(val)
    if typ == "loan":
        return (fmt_money(val) + " · prêt") if val else "Prêt"
    if typ == "free":
        return "Libre"
    return "—"


def fmt_val(val):
    return fmt_money(val) if val and val > 0 else "—"


def season_label(season):
    return f"{season}/{(int(season) + 1) % 100:02d}"


def fmt_match(m, club_lookup_by_name):
    """Enrich one raw fixture dict with display-ready fields."""
    opp = club_lookup_by_name.get(m["opponent"])
    return {
        **m,
        "season_label": season_label(m["season"]),
        "opponent_code": opp["code"] if opp else None,
        "opponent_logo_own": opp["logo_url"] if opp else None,
        "score_display": (f"{m['score']} {m['extra']}".strip() if m.get("extra") else m.get("score", "")),
    }


def enrich_standings(rows, clubs_by_id):
    out = []
    for r in rows:
        c = clubs_by_id.get(r.get("club_id"))
        out.append({**r, "code": c["code"] if c else None,
                    "logo_url": c["logo_url"] if c else r.get("logo_url", ""),
                    "accent": c["accent"] if c else None})
    return out


def build_matchday_view(clubs_raw, name_to_club, season):
    """Reconstruct a round-by-round (journée) view of the league phase for
    one season, purely from the per-club fixture lists already scraped —
    no extra requests. The "league" competition is whichever one accounts
    for the most matches in a club's calendar that season (cups are far
    fewer games), which avoids hardcoding Transfermarkt's exact label for
    it (it isn't always the competition's own name, e.g. National shows
    up as "Ligue 3" in fixture lists)."""
    from collections import Counter, defaultdict

    def club_fixtures(c):
        fx = c.get("fixtures", [])
        return fx if isinstance(fx, list) else []

    counter = Counter()
    for c in clubs_raw:
        for m in club_fixtures(c):
            if m["season"] == season:
                counter[m["comp"]] += 1
    if not counter:
        return {"league_comp_name": None, "matchday_order": [], "matchdays": {}}
    league_comp_name = counter.most_common(1)[0][0]

    by_md = defaultdict(list)
    for c in clubs_raw:
        home_ctx = name_to_club.get(c["name"])
        for m in club_fixtures(c):
            if m["season"] != season or m["comp"] != league_comp_name or m["venue"] != "home":
                continue
            away_ctx = name_to_club.get(m["opponent"])
            by_md[m["matchday"]].append({
                "date": m["date"], "date_iso": m["date_iso"], "time": m["time"],
                "home_name": c["name"], "home_code": home_ctx["code"] if home_ctx else None,
                "home_logo": home_ctx["logo_url"] if home_ctx else "",
                "away_name": m["opponent"], "away_code": away_ctx["code"] if away_ctx else None,
                "away_logo": away_ctx["logo_url"] if away_ctx else m.get("opponent_logo", ""),
                "score": m.get("score", ""), "extra": m.get("extra", ""), "played": m.get("played", False),
            })
    for md in by_md:
        by_md[md].sort(key=lambda x: (x["date_iso"], x["time"]))

    def md_key(k):
        try:
            return (0, int(k))
        except ValueError:
            return (1, k)
    matchday_order = sorted(by_md.keys(), key=md_key)
    return {"league_comp_name": league_comp_name, "matchday_order": matchday_order,
            "matchdays": dict(by_md)}


def load_competition(code):
    p = os.path.join(DATA, f"{code}.json")
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def build():
    if os.path.exists(PUBLIC):
        shutil.rmtree(PUBLIC)
    os.makedirs(PUBLIC)
    os.makedirs(os.path.join(PUBLIC, "assets"), exist_ok=True)
    shutil.copy(os.path.join(STATIC, "style.css"), os.path.join(PUBLIC, "assets", "style.css"))
    shutil.copy(os.path.join(STATIC, "app.js"), os.path.join(PUBLIC, "assets", "app.js"))
    shutil.copytree(os.path.join(STATIC, "fonts"), os.path.join(PUBLIC, "assets", "fonts"))

    def content_hash(fn):
        return hashlib.sha256(open(fn, "rb").read()).hexdigest()[:10]

    env = Environment(loader=FileSystemLoader(TEMPLATES),
                      autoescape=select_autoescape(["html"]))
    # GitHub Pages project sites are served from /<repo>/, not the domain
    # root, so every root-relative link/asset needs this prefix. Empty for
    # local previews (served from the origin's root by `python -m http.server`).
    env.globals["base"] = os.environ.get("SITE_BASE_PATH", "").rstrip("/")
    # Cache-busting: assets are always served from the same /assets/*.css|js
    # path across deploys, and GitHub Pages' CDN can keep serving a stale
    # cached copy for a while after a push. Appending a content hash changes
    # the URL whenever the file actually changes, forcing a fresh fetch.
    env.globals["css_v"] = content_hash(os.path.join(STATIC, "style.css"))
    env.globals["js_v"] = content_hash(os.path.join(STATIC, "app.js"))

    all_comps_meta = []
    loaded = {}
    for comp in COMPETITIONS:
        d = load_competition(comp["code"])
        if d:
            loaded[comp["code"]] = d
            all_comps_meta.append({"code": comp["code"], "name": comp["name"],
                                   "logo_url": comp.get("logo_url", ""),
                                   "color": comp.get("color", "#3b4252")})

    for comp in COMPETITIONS:
        d = loaded.get(comp["code"])
        if not d:
            print(f"! pas de données pour {comp['code']}, page ignorée")
            continue

        updated_dt = datetime.fromisoformat(d["updated"])
        comp_ctx = {
            "code": d["code"], "name": d["name"], "season": d["season"],
            "logo_url": comp.get("logo_url", ""),
            "color": comp.get("color", "#3b4252"),
            "updated_fmt": updated_dt.strftime("%d/%m/%Y à %Hh%M"),
        }

        clubs_ctx = []
        for c in d["clubs"]:
            arr = [{**t, "fee_fmt": fmt_fee(t)} for t in c.get("arr", [])]
            dep = [{**t, "fee_fmt": fmt_fee(t)} for t in c.get("dep", [])]
            arr_total = sum(t.get("val", 0) for t in arr)
            dep_total = sum(t.get("val", 0) for t in dep)
            solde = dep_total - arr_total
            clubs_ctx.append({
                "code": c["code"], "id": c["id"], "name": c["name"], "logo_url": c["logo_url"],
                "accent": c["accent"], "arr": arr, "dep": dep,
                "arr_total_fmt": fmt_money(arr_total), "dep_total_fmt": fmt_money(dep_total),
                "solde": solde, "solde_fmt": fmt_money(solde, signed=True),
            })

        name_to_club = {c["name"]: c for c in clubs_ctx}
        clubs_by_id = {c["id"]: c for c in clubs_ctx}

        # Full standings history: {season(str): [rows]}, most recent season
        # first, each row linked back to our own club page when possible.
        standings_raw = d.get("standings", {})
        standings_seasons = sorted((int(s) for s in standings_raw.keys()), reverse=True)
        standings_ctx = {
            "seasons": standings_seasons,
            "season_labels": {s: season_label(s) for s in standings_seasons},
            "current_season": d["season"],
            "by_season": {s: enrich_standings(standings_raw.get(str(s), []), clubs_by_id)
                         for s in standings_seasons},
        }

        matchday_ctx = build_matchday_view(d["clubs"], name_to_club, d["season"])

        # Enrich the "latest arrivals" strip with the destination club's
        # crest/accent so each entry can carry that club's visual identity.
        club_lookup = {c["code"]: c for c in clubs_ctx}
        latest_ctx = []
        for t in d.get("latest", []):
            item = {**t, "fee_fmt": fmt_fee(t)}
            dest = club_lookup.get(t.get("club_code"))
            if dest:
                item["dest_logo_url"] = dest["logo_url"]
                item["dest_accent"] = dest["accent"]
                item["dest_name"] = dest["name"]
            latest_ctx.append(item)

        out_dir = os.path.join(PUBLIC, comp["code"])
        os.makedirs(out_dir, exist_ok=True)
        tpl = env.get_template("mercato.html")
        html = tpl.render(competition=comp_ctx, all_competitions=all_comps_meta,
                          clubs=clubs_ctx, latest=latest_ctx, standings=standings_ctx)
        open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(html)

        tpl_cl = env.get_template("classement.html")
        html_cl = tpl_cl.render(competition=comp_ctx, all_competitions=all_comps_meta,
                                standings=standings_ctx)
        open(os.path.join(out_dir, "classement.html"), "w", encoding="utf-8").write(html_cl)

        tpl_cal = env.get_template("calendrier.html")
        html_cal = tpl_cal.render(competition=comp_ctx, all_competitions=all_comps_meta,
                                  matchday=matchday_ctx,
                                  standings=standings_ctx.get("by_season", {}).get(d["season"], []))
        open(os.path.join(out_dir, "calendrier.html"), "w", encoding="utf-8").write(html_cal)

        team_dir = os.path.join(out_dir, "equipe")
        os.makedirs(team_dir, exist_ok=True)
        tpl_eq = env.get_template("equipe.html")
        for c in d["clubs"]:
            squad_by_group = {"GK": [], "DEF": [], "MID": [], "ATT": []}
            for p in c.get("squad", []):
                p_ctx = {**p, "val_fmt": fmt_val(p.get("val", 0))}
                squad_by_group.setdefault(p.get("grp", "MID"), []).append(p_ctx)
            honours = sorted(c.get("honours", []), key=lambda h: h["count"], reverse=True)

            raw_fixtures = c.get("fixtures", [])
            if not isinstance(raw_fixtures, list):
                raw_fixtures = []  # pre-migration shape, ignore
            fixtures_ctx = sorted(
                (fmt_match(m, name_to_club) for m in raw_fixtures),
                key=lambda m: (m["date_iso"], m["time"]), reverse=True)
            fixtures_seasons = sorted({m["season"] for m in fixtures_ctx}, reverse=True)
            fixtures_comps = sorted({m["comp"] for m in fixtures_ctx})

            own_history = []
            for s in standings_ctx["seasons"]:
                row = next((r for r in standings_ctx["by_season"][s] if r.get("club_id") == c["id"]), None)
                if row:
                    own_history.append({**row, "season": s, "season_label": season_label(s)})

            club_ctx = {"code": c["code"], "name": c["name"], "logo_url": c["logo_url"],
                       "accent": c["accent"], "info": c.get("info", {}),
                       "honours": honours, "fixtures": fixtures_ctx,
                       "fixtures_seasons": fixtures_seasons, "fixtures_comps": fixtures_comps,
                       "current_season": d["season"], "standings_history": own_history}
            html_eq = tpl_eq.render(competition=comp_ctx, all_competitions=all_comps_meta,
                                    club=club_ctx, squad_by_group=squad_by_group)
            open(os.path.join(team_dir, f"{c['code']}.html"), "w", encoding="utf-8").write(html_eq)

        print(f"✓ {comp['code']} : {len(d['clubs'])} pages effectif + mercato + classement + calendrier")

    tpl_home = env.get_template("home.html")
    home_comps = []
    for comp in COMPETITIONS:
        d = loaded.get(comp["code"])
        home_comps.append({"code": comp["code"], "name": comp["name"],
                           "logo_url": comp.get("logo_url", ""),
                           "color": comp.get("color", "#3b4252"),
                           "n_clubs": len(d["clubs"]) if d else 0})
    season = COMPETITIONS[0].get("season") if COMPETITIONS else 2026
    from config.competitions import SEASON
    open(os.path.join(PUBLIC, "index.html"), "w", encoding="utf-8").write(
        tpl_home.render(competitions=home_comps, season=SEASON))
    print(f"✓ index.html (accueil) généré")


if __name__ == "__main__":
    build()
