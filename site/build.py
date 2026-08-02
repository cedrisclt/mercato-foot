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
from config.short_names import SHORT_NAMES

# Canonical production URL — used for <link rel="canonical">/og:url, which
# must stay correct regardless of SITE_BASE_PATH (empty for local previews).
SITE_URL = "https://cedrisclt.github.io/mercato-foot"


def dname(club_id, fallback):
    """Canonical short display name for a club id, else whatever name we
    were given (e.g. Transfermarkt's own wording for an untracked club)."""
    return SHORT_NAMES.get(club_id, fallback)


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


def fmt_match(m, clubs_by_id):
    """Enrich one raw fixture dict with display-ready fields. Matched by
    Transfermarkt club id, not by name text — Transfermarkt itself writes
    a given club's name differently from one page to the next (e.g.
    "R. Strasbourg" on a fixture list vs "RC Strasbourg Alsace" on its own
    competition table), so id is the only reliable join key."""
    opp_id = m.get("opponent_id")
    opp = clubs_by_id.get(opp_id)
    return {
        **m,
        "season_label": season_label(m["season"]),
        "opponent": dname(opp_id, m["opponent"]),
        "opponent_code": opp["code"] if opp else None,
        "opponent_logo_own": opp["logo_url"] if opp else None,
        "score_display": (f"{m['score']} {m['extra']}".strip() if m.get("extra") else m.get("score", "")),
    }


def enrich_standings(rows, clubs_by_id):
    out = []
    for r in rows:
        cid = r.get("club_id")
        c = clubs_by_id.get(cid)
        out.append({**r, "club_name": dname(cid, r.get("club_name")),
                    "code": c["code"] if c else None,
                    "logo_url": c["logo_url"] if c else r.get("logo_url", ""),
                    "accent": c["accent"] if c else None})
    return out


def build_matchday_view(clubs_raw, clubs_by_id, season):
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
        home_ctx = clubs_by_id.get(c["id"])
        for m in club_fixtures(c):
            if m["season"] != season or m["comp"] != league_comp_name or m["venue"] != "home":
                continue
            opp_id = m.get("opponent_id")
            away_ctx = clubs_by_id.get(opp_id)
            by_md[m["matchday"]].append({
                "date": m["date"], "date_iso": m["date_iso"], "time": m["time"],
                "home_name": dname(c["id"], c["name"]), "home_code": home_ctx["code"] if home_ctx else None,
                "home_logo": home_ctx["logo_url"] if home_ctx else "",
                "away_name": dname(opp_id, m["opponent"]), "away_code": away_ctx["code"] if away_ctx else None,
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
    shutil.copy(os.path.join(STATIC, "favicon.svg"), os.path.join(PUBLIC, "favicon.svg"))
    open(os.path.join(PUBLIC, "robots.txt"), "w", encoding="utf-8").write(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")

    sitemap_paths = []

    def write_page(rel_path, html):
        """rel_path is relative to PUBLIC, e.g. 'FR1/equipe/PSG.html'."""
        full = os.path.join(PUBLIC, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w", encoding="utf-8").write(html)
        sitemap_paths.append("/" + rel_path)

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
                "code": c["code"], "id": c["id"], "name": dname(c["id"], c["name"]),
                "full_name": c["name"], "logo_url": c["logo_url"],
                "accent": c["accent"], "arr": arr, "dep": dep,
                "arr_total_fmt": fmt_money(arr_total), "dep_total_fmt": fmt_money(dep_total),
                "solde": solde, "solde_fmt": fmt_money(solde, signed=True),
            })

        clubs_by_id = {c["id"]: c for c in clubs_ctx}

        # Full standings history: {season(str): [rows]}, most recent season
        # first, each row linked back to our own club page when possible.
        standings_raw = d.get("standings", {})
        standings_seasons = sorted((int(s) for s in standings_raw.keys()), reverse=True)
        by_season = {}
        for s in standings_seasons:
            rows = enrich_standings(standings_raw.get(str(s), []), clubs_by_id)
            if not any(r.get("played", 0) for r in rows):
                # Nobody's played yet this season (preseason) — a "1st place"
                # zone-colour stripe on an 18-way tie at 0 pts would just be
                # misleading, so strip it for this season's table only.
                rows = [{**r, "zone_color": ""} for r in rows]
            by_season[s] = rows

        # Default the UI to the current season only once it has real matches;
        # otherwise show the last *completed* season so "classement" means
        # something on day one of a fresh mercato window.
        default_season = d["season"]
        if not any(r.get("played", 0) for r in by_season.get(d["season"], [])):
            for s in standings_seasons:
                if s != d["season"] and any(r.get("played", 0) for r in by_season.get(s, [])):
                    default_season = s
                    break

        standings_ctx = {
            "seasons": standings_seasons,
            "season_labels": {s: season_label(s) for s in standings_seasons},
            "current_season": d["season"],
            "default_season": default_season,
            "season_not_started": default_season != d["season"],
            "by_season": by_season,
        }

        matchday_ctx = build_matchday_view(d["clubs"], clubs_by_id, d["season"])

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

        season_lbl = season_label(d["season"])
        comp_code = comp["code"]

        tpl = env.get_template("mercato.html")
        html = tpl.render(competition=comp_ctx, all_competitions=all_comps_meta, page_kind="mercato",
                          clubs=clubs_ctx, latest=latest_ctx, standings=standings_ctx,
                          meta_description=f"Mercato {d['name']} {season_lbl} : arrivées, départs et indemnités de transfert, club par club.",
                          og_image=comp_ctx["logo_url"], canonical_url=f"{SITE_URL}/{comp_code}/index.html")
        write_page(f"{comp_code}/index.html", html)

        tpl_cl = env.get_template("classement.html")
        html_cl = tpl_cl.render(competition=comp_ctx, all_competitions=all_comps_meta, page_kind="classement",
                                standings=standings_ctx,
                                meta_description=f"Classement {d['name']} : tableau complet, 10 dernières saisons (2017/18 à {season_lbl}).",
                                og_image=comp_ctx["logo_url"], canonical_url=f"{SITE_URL}/{comp_code}/classement.html")
        write_page(f"{comp_code}/classement.html", html_cl)

        tpl_cal = env.get_template("calendrier.html")
        html_cal = tpl_cal.render(competition=comp_ctx, all_competitions=all_comps_meta, page_kind="calendrier",
                                  matchday=matchday_ctx,
                                  standings=standings_ctx.get("by_season", {}).get(standings_ctx["default_season"], []),
                                  standings_meta=standings_ctx,
                                  meta_description=f"Calendrier {d['name']} {season_lbl} : tous les matchs, journée par journée.",
                                  og_image=comp_ctx["logo_url"], canonical_url=f"{SITE_URL}/{comp_code}/calendrier.html")
        write_page(f"{comp_code}/calendrier.html", html_cal)

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
                (fmt_match(m, clubs_by_id) for m in raw_fixtures),
                key=lambda m: (m["date_iso"], m["time"]), reverse=True)
            fixtures_seasons = sorted({m["season"] for m in fixtures_ctx}, reverse=True)
            fixtures_comps = sorted({m["comp"] for m in fixtures_ctx})

            # Full history (up to 10 seasons) is written out as a small
            # per-club JSON file and only fetched on demand (season/comp
            # filter picks a season outside the inlined window) — most
            # visits only ever look at the current season, so there's no
            # reason to ship a growing multi-year archive on every load.
            recent_seasons = set(fixtures_seasons[:2])
            fixtures_recent = [m for m in fixtures_ctx if m["season"] in recent_seasons]
            fixtures_json_path = f"{comp_code}/fixtures/{c['code']}.json"
            os.makedirs(os.path.join(PUBLIC, comp_code, "fixtures"), exist_ok=True)
            json.dump(fixtures_ctx, open(os.path.join(PUBLIC, fixtures_json_path), "w", encoding="utf-8"),
                      ensure_ascii=False, separators=(",", ":"))

            own_history = []
            for s in standings_ctx["seasons"]:
                row = next((r for r in standings_ctx["by_season"][s] if r.get("club_id") == c["id"]), None)
                if row:
                    own_history.append({**row, "season": s, "season_label": season_label(s)})

            club_ctx = {"code": c["code"], "name": dname(c["id"], c["name"]),
                       "full_name": c["name"], "logo_url": c["logo_url"],
                       "accent": c["accent"], "info": c.get("info", {}),
                       "honours": honours, "fixtures": fixtures_recent,
                       "fixtures_full_url": fixtures_json_path,
                       "fixtures_seasons": fixtures_seasons, "fixtures_comps": fixtures_comps,
                       "current_season": d["season"], "standings_history": own_history}
            html_eq = tpl_eq.render(competition=comp_ctx, all_competitions=all_comps_meta, page_kind="equipe",
                                    club=club_ctx, squad_by_group=squad_by_group,
                                    meta_description=f"{club_ctx['full_name']} : effectif, palmarès, stade, calendrier et résultats — {d['name']} {season_lbl}.",
                                    og_image=club_ctx["logo_url"],
                                    canonical_url=f"{SITE_URL}/{comp_code}/equipe/{c['code']}.html")
            write_page(f"{comp_code}/equipe/{c['code']}.html", html_eq)

        print(f"✓ {comp['code']} : {len(d['clubs'])} pages effectif + mercato + classement + calendrier")

    tpl_home = env.get_template("home.html")
    home_comps = []
    for comp in COMPETITIONS:
        d = loaded.get(comp["code"])
        home_comps.append({"code": comp["code"], "name": comp["name"],
                           "logo_url": comp.get("logo_url", ""),
                           "color": comp.get("color", "#3b4252"),
                           "n_clubs": len(d["clubs"]) if d else 0})
    from config.competitions import SEASON
    write_page("index.html", tpl_home.render(
        competitions=home_comps, season=SEASON,
        meta_description="Suivi du mercato, du calendrier et du classement de Ligue 1, Ligue 2 et National — données Transfermarkt.fr.",
        canonical_url=f"{SITE_URL}/index.html"))
    print(f"✓ index.html (accueil) généré")

    sitemap_xml = ['<?xml version="1.0" encoding="UTF-8"?>',
                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path in sitemap_paths:
        sitemap_xml.append(f"  <url><loc>{SITE_URL}{path}</loc></url>")
    sitemap_xml.append("</urlset>")
    open(os.path.join(PUBLIC, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(sitemap_xml) + "\n")
    print(f"✓ sitemap.xml ({len(sitemap_paths)} pages) + robots.txt")


if __name__ == "__main__":
    build()
