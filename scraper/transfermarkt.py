#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generic Transfermarkt scraping helpers.

Everything here is parameterised by *competition* (a Transfermarkt
"wettbewerb" code such as FR1/FR2/FR3) or by *club* (id + slug), so the
same module works for any competition without code changes — only
config/competitions.py needs a new entry.
"""
import os
import re
import time
import colorsys
from io import BytesIO

import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "scraper", ".cache")
os.makedirs(CACHE, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# ---------------------------------------------------------------- fetch ----
def fetch_url(cache_key, url, offline=False, label=""):
    fn = os.path.join(CACHE, cache_key)
    if offline and os.path.exists(fn):
        return open(fn, "rb").read()
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.status_code == 200 and len(r.content) > 2000:
                open(fn, "wb").write(r.content)
                return r.content
            print(f"  ! HTTP {r.status_code} pour {label or url} (essai {attempt + 1})")
        except Exception as e:
            print(f"  ! {label or url} : {e} (essai {attempt + 1})")
        time.sleep(1.5 + attempt * 2)
    if os.path.exists(fn):
        print(f"  -> cache utilisé pour {label or url}")
        return open(fn, "rb").read()
    return None


# --------------------------------------------------------- club roster ----
def get_clubs(competition, season, offline=False):
    """Scrape the competition's 'startseite' table -> list of club dicts.

    Returns [{id, name, slug, code, logo_url}] ordered as on Transfermarkt.
    `code` is a short auto-generated abbreviation (e.g. "PSG", "ASM").
    """
    url = (f"https://www.transfermarkt.fr/{competition['slug']}/startseite/"
           f"wettbewerb/{competition['code']}?saison_id={season}")
    raw = fetch_url(f"clubs_{competition['code']}.html", url, offline,
                     f"clubs {competition['name']}")
    if not raw:
        return []
    soup = BeautifulSoup(raw, "lxml")
    t = soup.select_one("table.items")
    clubs, used_codes = [], set()
    for tr in (t.select("tbody > tr") if t else []):
        a = tr.select_one("td.hauptlink a[href*='/verein/']") or tr.find("a", href=re.compile(r"/verein/\d+"))
        if not a:
            continue
        m = re.search(r"/([\w-]+)/startseite/verein/(\d+)", a["href"])
        if not m:
            continue
        slug, cid = m.group(1), int(m.group(2))
        name = (a.get("title") or a.get_text(strip=True)).strip()
        # "head" size crest (~139x181) — much crisper than the 15x15 "tiny"
        # icon used in the competition table, which looks blurry once scaled up.
        logo_url = f"https://tmssl.akamaized.net/images/wappen/head/{cid}.png"
        code = _make_code(name, used_codes)
        used_codes.add(code)
        clubs.append({"id": cid, "name": name, "slug": slug, "code": code,
                      "logo_url": logo_url})
    return clubs


_STOPWORDS = {"de", "du", "le", "la", "les", "et", "d"}


def _make_code(name, used):
    tokens = re.split(r"[\s-]+", name.strip())
    parts = []
    for tok in tokens:
        low = tok.lower().strip(".")
        if low in _STOPWORDS:
            continue
        if tok.isupper() and len(tok) <= 5:
            parts.append(tok)
        elif tok[:1].isdigit():
            parts.append(tok)
        else:
            parts.append(tok[0].upper())
    code = "".join(parts)[:6] or name[:3].upper()
    base, i = code, 2
    while code in used:
        code = f"{base}{i}"
        i += 1
    return code


def accent_color(logo_url, offline=False):
    """Average non-white/transparent colour of a club crest -> '#rrggbb'."""
    if not logo_url:
        return "#3b4252"
    try:
        from PIL import Image
        key = "logo_" + re.sub(r"\W+", "_", logo_url)[-60:] + ".png"
        fn = os.path.join(CACHE, key)
        if offline and os.path.exists(fn):
            raw = open(fn, "rb").read()
        else:
            r = requests.get(logo_url, headers=HEADERS, timeout=15)
            raw = r.content
            open(fn, "wb").write(raw)
        img = Image.open(BytesIO(raw)).convert("RGBA").resize((24, 24))
        pixels = [p for p in img.getdata() if p[3] > 80]
        pixels = [p for p in pixels if not (p[0] > 235 and p[1] > 235 and p[2] > 235)
                  and not (p[0] < 20 and p[1] < 20 and p[2] < 20)]
        if not pixels:
            return "#3b4252"
        r = sum(p[0] for p in pixels) / len(pixels)
        g = sum(p[1] for p in pixels) / len(pixels)
        b = sum(p[2] for p in pixels) / len(pixels)
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        s = min(1.0, s * 1.15)
        v = max(0.28, min(0.55, v))
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))
    except Exception:
        return "#3b4252"


# -------------------------------------------------------------- posts -----
POS = {
    "Gardien de but": "GdB", "Arrière droit": "ArD", "Arrière gauche": "ArG",
    "Défenseur central": "DC", "Milieu défensif": "MDC", "Milieu central": "MC",
    "Milieu offensif": "MO", "Milieu droit": "MD", "Milieu gauche": "MG",
    "Ailier droit": "AiD", "Ailier gauche": "AiG", "Avant-centre": "AC",
    "Second attaquant": "SA", "Attaquant": "AC", "Défenseur": "DC", "Milieu": "MC",
}
GRP = {
    "Gardien de but": "GK",
    "Arrière droit": "DEF", "Arrière gauche": "DEF", "Défenseur central": "DEF", "Défenseur": "DEF",
    "Milieu défensif": "MID", "Milieu central": "MID", "Milieu offensif": "MID",
    "Milieu droit": "MID", "Milieu gauche": "MID", "Milieu": "MID",
    "Ailier droit": "ATT", "Ailier gauche": "ATT", "Avant-centre": "ATT",
    "Second attaquant": "ATT", "Attaquant": "ATT",
}


def pos_short(full):
    full = (full or "").strip()
    if full in POS:
        return POS[full]
    return "".join(w[0] for w in full.split()[:3]).upper()[:4] or "?"


def pos_group(full):
    return GRP.get((full or "").strip(), "MID")


RESERVE_RE = re.compile(
    r"(\bB\b|\bII\b|\bU-?1\d\b|\bU-?2\d\b|Futuro|R[ée]serve|Youth|Juniores|Primavera|Akademi)",
    re.I)


def is_reserve(club):
    return bool(RESERVE_RE.search(club or ""))


def parse_fee(raw):
    """-> (type, val_millions, is_loan_return); type in {paid, loan, free, none}"""
    t = (raw or "").strip()
    low = t.lower()
    if "fin du prêt" in low or "fin de prêt" in low or "fin du pret" in low:
        return ("none", 0.0, True)
    val = 0.0
    m = re.search(r"([\d.,]+)\s*(mio|th|k)\b", low)
    if m:
        num = (float(m.group(1).replace(".", "").replace(",", "."))
               if m.group(1).count(",") else float(m.group(1).replace(",", ".")))
        unit = m.group(2)
        val = num if unit == "mio" else num / 1000.0
    if "prêt" in low or "pret" in low or "loan" in low:
        return ("loan", val, False)
    if m:
        return ("paid", val, False)
    if "libre" in low or "free" in low:
        return ("free", 0.0, False)
    return ("none", 0.0, False)


def _club_name_from_cell(td):
    for a in td.find_all("a"):
        txt = a.get_text(strip=True)
        if txt:
            return txt
    return td.get_text(" ", strip=True) or "Sans club"


def _parse_side(rt):
    out = []
    table = rt.find("table")
    tbody = table.find("tbody") if table else None
    if not tbody:
        return out
    for tr in tbody.find_all("tr", recursive=False):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 6:
            continue
        namea = tds[1].select_one(".hauptlink a") or tds[1].find("a")
        if not namea:
            continue
        name = (namea.get("title") or namea.get_text(strip=True)).strip()
        inner_rows = tds[1].find_all("tr")
        pos_full = inner_rows[-1].get_text(" ", strip=True) if inner_rows else ""
        age = re.sub(r"\D", "", tds[2].get_text(strip=True))[:2]
        club = _club_name_from_cell(tds[4])
        fee_raw = tds[5].get_text(" ", strip=True)
        out.append({"p": name, "age": int(age) if age else 0, "pos": pos_short(pos_full),
                    "club": club, "feeRaw": fee_raw})
    return out


def _clean(rows):
    res = []
    for t in rows:
        typ, val, loan_ret = parse_fee(t["feeRaw"])
        if loan_ret:
            continue
        if is_reserve(t["club"]) and typ in ("free", "none", "loan"):
            continue
        res.append({"p": t["p"], "age": t["age"], "pos": t["pos"], "club": t["club"],
                    "type": typ, "val": round(val, 3)})
    return res


def get_transfers(club, season, offline=False):
    """-> (arrivals, departures) for one club this season."""
    url = (f"https://www.transfermarkt.fr/{club['slug']}/transfers/verein/"
           f"{club['id']}/saison_id/{season}")
    raw = fetch_url(f"transfers_{club['id']}.html", url, offline, club["name"])
    if not raw:
        return [], []
    soup = BeautifulSoup(raw, "lxml")
    rts = soup.select("div.responsive-table")
    arr = _clean(_parse_side(rts[0])) if len(rts) > 0 else []
    dep = _clean(_parse_side(rts[1])) if len(rts) > 1 else []
    return arr, dep


def get_squad(club, season, offline=False):
    url = (f"https://www.transfermarkt.fr/{club['slug']}/kader/verein/"
           f"{club['id']}/saison_id/{season}/plus/1")
    raw = fetch_url(f"kader_{club['id']}.html", url, offline, club["name"] + " kader")
    if not raw:
        return []
    soup = BeautifulSoup(raw, "lxml")
    t = soup.select_one("table.items")
    players = []
    for tr in (t.select("tbody > tr.odd, tbody > tr.even") if t else []):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 3:
            continue
        nm = tds[1].select_one(".hauptlink a")
        if not nm:
            continue
        name = (nm.get("title") or nm.get_text(strip=True)).strip()
        inner = tds[1].select("tr")
        pos_full = inner[-1].get_text(" ", strip=True) if inner else ""
        num = tds[0].get_text(strip=True)
        num = "" if num in ("-", "") else num
        m = re.search(r"\((\d+)\)", tds[2].get_text())
        age = int(m.group(1)) if m else 0
        _, val, _ = parse_fee(tds[-1].get_text(" ", strip=True))
        players.append({"n": num, "p": name, "pos": pos_short(pos_full),
                        "grp": pos_group(pos_full), "age": age, "val": round(val, 2)})
    return players


def get_club_info(club, offline=False):
    """-> {"stadium": str, "capacity": str} from the club's profile page."""
    url = f"https://www.transfermarkt.fr/{club['slug']}/startseite/verein/{club['id']}"
    raw = fetch_url(f"profile_{club['id']}.html", url, offline, club["name"] + " profil")
    if not raw:
        return {"stadium": "", "capacity": ""}
    soup = BeautifulSoup(raw, "lxml")
    info = {"stadium": "", "capacity": ""}
    for li in soup.select("ul.data-header__items > li.data-header__label"):
        if li.get_text(" ", strip=True).startswith("Stade:"):
            a = li.select_one("span.data-header__content a")
            cap = li.select_one("span.tabellenplatz")
            info["stadium"] = a.get_text(strip=True) if a else ""
            cap_txt = cap.get_text(strip=True) if cap else ""
            info["capacity"] = cap_txt.replace(".", " ").replace("Places", "places")
            break
    return info


def get_honours(club, offline=False):
    """-> [{"title","count","seasons":[...],"logo_url"}], most recent first."""
    url = f"https://www.transfermarkt.fr/{club['slug']}/erfolge/verein/{club['id']}"
    raw = fetch_url(f"erfolge_{club['id']}.html", url, offline, club["name"] + " palmarès")
    if not raw:
        return []
    soup = BeautifulSoup(raw, "lxml")
    honours = []
    for box in soup.select("div.erfolg_infotext_box"):
        container = box.parent
        outer = container.parent if container else None
        h2 = outer.select_one("div.header h2") if outer else None
        if not h2:
            continue
        title_full = h2.get_text(strip=True)
        m = re.match(r"(\d+)x\s*(.+)", title_full)
        if not m:
            continue  # occasional upstream data glitch: trophy image without a name
        count, title = int(m.group(1)), m.group(2).strip()
        seasons = [s.strip() for s in box.get_text(" ", strip=True).split(",") if s.strip()]
        img = container.select_one("div.erfolg_bild_box img")
        honours.append({"title": title, "count": count, "seasons": seasons,
                        "logo_url": img["src"] if img else ""})
    return honours


def get_fixtures(club, season, offline=False):
    """-> {"results": [...], "upcoming": [...]} for the full season schedule
       (all competitions), each match: comp/matchday/date/time/venue/
       opponent/opponent_logo/score/played."""
    url = (f"https://www.transfermarkt.fr/{club['slug']}/spielplandatum/verein/"
           f"{club['id']}/saison_id/{season}")
    raw = fetch_url(f"spielplan_{club['id']}.html", url, offline, club["name"] + " calendrier")
    if not raw:
        return {"results": [], "upcoming": []}
    soup = BeautifulSoup(raw, "lxml")
    table = None
    for t in soup.find_all("table"):
        hdr = t.find("tr")
        if hdr and "Résultat" in hdr.get_text():
            table = t
            break
    if not table:
        return {"results": [], "upcoming": []}

    current_comp = ""
    matches = []
    for r in table.select("tr")[1:]:
        tds = r.find_all("td", recursive=False)
        if len(tds) == 1 and "extrarow" in (tds[0].get("class") or []):
            a = tds[0].find("a")
            current_comp = a.get_text(strip=True) if a else tds[0].get_text(strip=True)
            continue
        if len(tds) < 10:
            continue
        venue_raw = tds[3].get_text(strip=True)
        opp_a = tds[6].find("a")
        opp_img = tds[5].find("img")
        score = tds[9].get_text(strip=True)
        played = bool(score) and score not in ("-:-", "?:?", "")
        matches.append({
            "comp": current_comp, "matchday": tds[0].get_text(strip=True),
            "date": tds[1].get_text(strip=True), "time": tds[2].get_text(strip=True),
            "venue": {"D": "home", "E": "away"}.get(venue_raw, venue_raw),
            "opponent": opp_a.get_text(strip=True) if opp_a else tds[6].get_text(strip=True),
            "opponent_logo": opp_img["src"] if opp_img else "",
            "score": score if played else "", "played": played,
        })
    results = [m for m in matches if m["played"]]
    upcoming = [m for m in matches if not m["played"]]
    return {"results": list(reversed(results))[:8], "upcoming": upcoming[:8]}


def get_latest_transfers(competition, club_ids, offline=False):
    """Most recent arrivals into any club of `competition` (id -> code map)."""
    url = ("https://www.transfermarkt.fr/transfers/neuestetransfers/statistik"
           f"?land_id=0&wettbewerb_id={competition['code']}&minMarktwert=0&maxMarktwert=500000000")
    raw = fetch_url(f"latest_{competition['code']}.html", url, offline,
                     f"derniers transferts {competition['name']}")
    if not raw:
        return []
    soup = BeautifulSoup(raw, "lxml")
    t = soup.select_one("table.items")
    out = []
    for tr in (t.select("tbody > tr") if t else []):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 6:
            continue
        dst_a = tds[4].find("a", href=re.compile(r"/verein/\d+"))
        dst = int(re.search(r"/verein/(\d+)", dst_a["href"]).group(1)) if dst_a else None
        if dst not in club_ids:
            continue
        namea = tds[0].select_one(".hauptlink a") or tds[0].find("a")
        if not namea:
            continue
        name = (namea.get("title") or namea.get_text(strip=True)).strip()
        inner = tds[0].find_all("tr")
        pos_full = inner[-1].get_text(" ", strip=True) if inner else ""
        age = re.sub(r"\D", "", tds[1].get_text(strip=True))[:2]
        frm_full = tds[3].get_text(" ", strip=True)
        frm = _club_name_from_cell(tds[3])
        typ, val, loan_ret = parse_fee(tds[5].get_text(" ", strip=True))
        if loan_ret:
            continue
        if is_reserve(frm_full) and typ in ("free", "none", "loan"):
            continue
        out.append({"p": name, "age": int(age) if age else 0, "pos": pos_short(pos_full),
                    "club": frm, "type": typ, "val": round(val, 3),
                    "club_code": club_ids[dst]})
    return out
