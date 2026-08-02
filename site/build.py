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
                "code": c["code"], "name": c["name"], "logo_url": c["logo_url"],
                "accent": c["accent"], "arr": arr, "dep": dep,
                "arr_total_fmt": fmt_money(arr_total), "dep_total_fmt": fmt_money(dep_total),
                "solde": solde, "solde_fmt": fmt_money(solde, signed=True),
            })

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
                          clubs=clubs_ctx, latest=latest_ctx)
        open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(html)

        team_dir = os.path.join(out_dir, "equipe")
        os.makedirs(team_dir, exist_ok=True)
        tpl_eq = env.get_template("equipe.html")
        for c in d["clubs"]:
            squad_by_group = {"GK": [], "DEF": [], "MID": [], "ATT": []}
            for p in c.get("squad", []):
                p_ctx = {**p, "val_fmt": fmt_val(p.get("val", 0))}
                squad_by_group.setdefault(p.get("grp", "MID"), []).append(p_ctx)
            honours = sorted(c.get("honours", []), key=lambda h: h["count"], reverse=True)
            club_ctx = {"code": c["code"], "name": c["name"], "logo_url": c["logo_url"],
                       "accent": c["accent"], "info": c.get("info", {}),
                       "honours": honours, "fixtures": c.get("fixtures", {})}
            html_eq = tpl_eq.render(competition=comp_ctx, all_competitions=all_comps_meta,
                                    club=club_ctx, squad_by_group=squad_by_group)
            open(os.path.join(team_dir, f"{c['code']}.html"), "w", encoding="utf-8").write(html_eq)

        print(f"✓ {comp['code']} : {len(d['clubs'])} pages effectif + 1 page mercato")

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
