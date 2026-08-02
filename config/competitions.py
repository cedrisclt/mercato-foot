"""Config-driven list of competitions to track.

Adding a new competition to the site = adding one entry here.
No club lists to maintain by hand: the club roster for each competition
is scraped dynamically from its Transfermarkt "startseite" page every run,
so promotions/relegations are picked up automatically each season.
"""

SEASON = 2026

COMPETITIONS = [
    {"code": "FR1", "name": "Ligue 1", "slug": "ligue-1",
     "logo_url": "https://tmssl.akamaized.net/images/logo/header/fr1.png",
     "color": "#ff7fde"},
    {"code": "FR2", "name": "Ligue 2", "slug": "ligue-2",
     "logo_url": "https://tmssl.akamaized.net/images/logo/header/fr2.png",
     "color": "#0072ce"},
    {"code": "FR3", "name": "National", "slug": "championnat-national",
     "logo_url": "https://tmssl.akamaized.net/images/logo/header/fr3.png",
     "color": "#00a656"},
]
