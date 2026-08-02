"""Canonical short display names, keyed by Transfermarkt club id (globally
unique — our own auto-generated `code` can collide across competitions,
e.g. "PFC" for both Paris FC and Pau FC).

Used everywhere a club name is rendered so the same club shows the same
name on every page (mercato cards, calendrier, classement, équipe header,
fixture rows) instead of whatever wording Transfermarkt happened to use
on a given page. Ligue 1 names match ligue1.com's own short names; the
rest follow the same convention (drop redundant legal-entity words like
"FC"/"AS"/"Olympique" once the remaining name is still unambiguous).

A club with no entry here just keeps its scraped full name.
"""

SHORT_NAMES = {
    # --- Ligue 1 (verbatim from ligue1.com) ---
    583: "PSG",
    162: "AS Monaco",
    667: "Strasbourg",
    1082: "LOSC",
    1041: "OL",
    273: "Rennes",
    244: "OM",
    10004: "Paris FC",
    826: "RC Lens",
    415: "Toulouse FC",
    417: "OGC Nice",
    290: "AJ Auxerre",
    1158: "FC Lorient",
    1420: "Angers SCO",
    3911: "Brest",
    738: "Havre AC",
    1095: "Troyes",
    1164: "Le Mans FC",

    # --- Ligue 2 ---
    618: "Saint-Étienne",
    995: "Nantes",
    1421: "Reims",
    347: "Metz",
    969: "Montpellier",
    3524: "Clermont",
    11273: "Rodez",
    3166: "Pau FC",
    1154: "Red Star",
    1290: "Grenoble",
    855: "Guingamp",
    1159: "Nancy",
    30204: "Annecy",
    1080: "Laval",
    9202: "Dunkerque",
    7042: "Boulogne",
    750: "Sochaux",
    2969: "Dijon",

    # --- National ---
    595: "Bastia",
    1416: "Amiens",
    13466: "Versailles",
    1162: "Caen",
    1423: "Valenciennes",
    10868: "Orléans",
    17442: "Fleury",
    18633: "Villefranche",
    62382: "Paris 13 Atletico",
    21688: "Concarneau",
    1564: "Rouen",
    26863: "Le Puy",
    7124: "Quevilly-Rouen",
    2972: "Bourg-Péronnas",
    895: "Cannes",
    42609: "Aubagne",
    94385: "Thionville",
    3541: "La Roche-sur-Yon",
}
