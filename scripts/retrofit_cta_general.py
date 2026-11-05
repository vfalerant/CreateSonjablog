"""
scripts/retrofit_cta_general.py

ALTALANOS, sorozat-alapu script a szerzoi CTA-doboz visszamenoleges
beillesztesere a mar publikalt posztokra.

FONTOS (2026.09.02-i javitas): a sorozat reszeinek felderitese
KATEGORIA-ID alapjan tortenik (WP REST ?categories=<id>), NEM
cim-keresessel (?search=<cim>). A cim-kereses (search=) a
"Calle la Rosa 22" es "Nadia" sorozatoknal veletlenul jol mukodott,
de "A szalon" es "Emily naploja" sorozatoknal SULYOSAN alulszamolt
volna az angol/spanyol reszeknel (a WP relevancia-kereses nem
mindig talalja meg a forditott posztokat egy magyar/egyeb nyelvu
cimre keresve) -- ezt elo lehetett elozetesen olvasztani egy elo
WP REST kategoria-listazassal: minden sorozatnak es minden
nyelvnek KULON kategoria-ID-ja van a Polylang miatt (pl. "A szalon"
HU=361, EN "The Salon"=365, ES "El salon"=363), es a
?categories=<id> lekerdezes ezekre TELJES es PONTOS listat ad,
nyelvi keresesi kvirkektol fuggetlenul. Lasd SERIES_CONFIGS lent.

FUTTATAS SAJAT GEPEDROL (nem a Claude sandbox-jabol -- ahhoz teljes
internet-eleres kell a WordPress API-hoz):

    cd Development\\CreateSonjablog

    # Eloszor MINDIG dry-run-nal nezd at, mit tenne a script:
    python scripts\\retrofit_cta_general.py --sorozat a_szalon --dry-run
    python scripts\\retrofit_cta_general.py --sorozat emily_naploja --dry-run

    # Ha a dry-run kimenete rendben van, ugyanaz a parancs
    # --dry-run nelkul VEGREHAJTJA a frissitest:
    python scripts\\retrofit_cta_general.py --sorozat a_szalon
    python scripts\\retrofit_cta_general.py --sorozat emily_naploja

STATUSZ (2026.09.02):
  1. calle_la_rosa -- KESZ (297 poszt frissitve)
  2. nadia -- KESZ (27 poszt frissitve)
  3. a_szalon -- KESZ (59 poszt frissitve, 1 mar korabban kezzel
     beillesztett teszt-CTA-t a script automatikusan KIHAGYVA-kent
     ismerte fel a 19. magyar reszen)
  4. emily_naploja -- KESZ (75 poszt frissitve)
  5. rovid_tortenetek -- KESZ, az osszes poszt frissitve.

--resztol / --reszig: opcionalis szures egy sorozaton BELUL, ha
tovabb akarod darabolni (pl. csak az elso 10 reszt egy futtatasban):

    python scripts\\retrofit_cta_general.py --sorozat a_szalon --resztol 1 --reszig 10

A duplikacio-ellenorzes miatt biztonsagos ujra lefuttatni egy mar
lefutott (vagy attfedo tartomanyu) parancsot -- a mar ellatott
posztokat egyszeruen KIHAGYVA-kent jelzi, nem tesz be dupla dobozt.

Minden futtatas vegen a script hozzafuz egy osszefoglalo sort a
scripts/retrofit_log.txt fajlhoz, hogy tobb, kulon napon vegzett
futtatas eredmenye is visszakereshetp legyen egy helyen.
"""

import argparse
import json
import re
import sys
import uuid
from datetime import datetime

import requests
from requests.auth import HTTPBasicAuth

sys.path.insert(0, ".")
from wordpress.config import load_secrets


# ---------------------------------------------------------------
# Sorozatonkenti konfiguracio.
#
# category_ids: nyelvenkenti WP kategoria-ID (Polylang miatt minden
# nyelvnek SAJAT kategoria-term-je van, lasd a fejlecben leirt
# felfedezest 2026.09.02-en: /wp-json/wp/v2/categories?lang=<nyelv>).
# Ez a MEGBIZHATO forras arra, hogy egy poszt a sorozathoz
# tartozik-e -- nem a cim-kereses.
#
# patterns: nyelvenkenti regex a slug-bol a resz-szam kinyeresehez
# (csak rendezesre/naplozasra es --resztol/--reszig szuresre kell,
# a sorozathoz tartozast MAR a kategoria eldontotte).
# ---------------------------------------------------------------
SERIES_CONFIGS = {
    "calle_la_rosa": {
        "label": "Calle la Rosa 22",
        "category_ids": {"hu": 76, "en": 173, "es": 176},
        "patterns": {
            "hu": r"^calle-la-rosa-22-(\d+)-resz$",
            "en": r"^22-calle-la-rosa-part-(\d+)$",
            "es": r"^calle-la-rosa-22-parte-(\d+)$",
        },
        # A probakorben (2026.09.01) mar megkapta a CTA-dobozt --
        # a duplikacio-ellenorzes ugyis KIHAGYVA-kent kezelne, de
        # itt is jelezzuk a naplo attekinthetosege kedveert.
        "already_done": set(range(100, 111)),
    },
    "nadia": {
        "label": "Nadia",
        "category_ids": {"hu": 66},
        "patterns": {
            "hu": r"^nadia-(\d+)-resz$",
            # Nincs EN/ES: a Nadia sorozat csak magyarul futott.
        },
        "already_done": set(),
    },
    "a_szalon": {
        "label": "A szalon",
        "category_ids": {"hu": 361, "en": 365, "es": 363},
        "patterns": {
            "hu": r"^a-szalon-(\d+)-resz$",
            "en": r"^the-salon-part-(\d+)$",
            "es": r"^el-salon-parte-(\d+)$",
        },
        "already_done": set(),
    },
    "emily_naploja": {
        "label": "Emily naplója",
        "category_ids": {"hu": 345, "en": 349, "es": 347},
        "patterns": {
            "hu": r"^emily-naploja-(\d+)-bejegyzes$",
            "en": r"^emilys-diary-entry-(\d+)$",
            "es": r"^el-diario-de-emily-entrada-(\d+)$",
        },
        "already_done": set(),
    },
    "rovid_tortenetek": {
        "label": "Rövid történetek",
        # NEM szamozott resz-sorozat -- onallo cimu novellak.
        # TORTENETI MEGJEGYZES: 2026.09.02-ig ezeknek a posztoknak
        # nem volt sajat kategoriajuk, csak a kozos "Blog"-ba (hu=68,
        # en=88, es=70) voltak besorolva. A visszamenoleges retrofit
        # (2026.09.02) a "Blog minusz Emily/Szalon kategoriak" trukkel
        # derítette fel oket -- ez sikeresen lefutott, MINDEN akkor
        # letezo Rovid tortenetek poszt megkapta a CTA-dobozt.
        # Meg aznap letrejott az onallo "Rövid történetek" kategoria,
        # es a posztok at lettek cimkezve ra (Blog kategoria levéve
        # roluk) -- lasd SEO audit dokumentacio. EZ A KONFIG MOSTANTOL
        # AZ UJ, JOVOBENI ROVID TORTENET POSZTOKHOZ KELL, a regi
        # Blog-alapu kivonasos logika mar nem talalna meg oket.
        "category_ids": {"hu": 419, "en": 423, "es": 421},
        "patterns": {},  # nincs resz-szam -- minden poszt az "egyeb" agon megy
        "already_done": set(),
    },
}

CTA_SHORTCODE_IDS = {
    "hu": "11589",
    "en": "11612",
    "es": "11622",
}


def _new_element_id():
    return uuid.uuid4().hex[:7]


def has_cta_already(node):
    """Rekurzivan megnezi, van-e MAR CTA-doboz a posztban (Shortcode
    widget INSERT_ELEMENTOR tartalommal, vagy regi, kezzel beillesztett
    nyers HTML 'sb-author-cta' class-szal)."""

    if isinstance(node, list):
        return any(has_cta_already(item) for item in node)
    if not isinstance(node, dict):
        return False
    if node.get("widgetType") == "shortcode":
        if "INSERT_ELEMENTOR" in node.get("settings", {}).get("shortcode", ""):
            return True
    if node.get("widgetType") == "html":
        if "sb-author-cta" in node.get("settings", {}).get("html", ""):
            return True
    return has_cta_already(node.get("elements", []))


def find_first_column(node):
    """Megkeresi az elso 'column' tipusu elemet a faban."""

    if isinstance(node, list):
        for item in node:
            found = find_first_column(item)
            if found is not None:
                return found
        return None
    if not isinstance(node, dict):
        return None
    if node.get("elType") == "column":
        return node
    return find_first_column(node.get("elements", []))


def discover_posts(session, base_url, category_ids, patterns, category_exclude_ids=None):
    """Nyelvenkent lekeri a MEGADOTT KATEGORIA-ID osszes posztjat
    (lapozva) -- ez a sorozathoz-tartozas megbizhato forrasa, nem a
    cim-kereses. A slug-bol a resz-szamot a nyelvhez tartozo regex-szel
    probalja kinyerni (csak rendezesre/naplozasra kell).

    Visszaad: (by_part, egyeb), ahol
      by_part = {resz_szam: {nyelv: post_id}}
      egyeb   = {nyelv: [(post_id, slug), ...]}  -- olyan posztok,
                amik a kategoriaban vannak, de a slug NEM illik a
                vart mintara (ezeket is fel kell dolgozni, csak nem
                sorolhatok resz-szam ala).
    """

    category_exclude_ids = category_exclude_ids or {}
    by_part = {}
    egyeb = {}
    for lang, cat_id in category_ids.items():
        if cat_id is None:
            continue
        pattern = patterns.get(lang)
        exclude_ids = category_exclude_ids.get(lang)
        page = 1
        total_pages = 1
        while page <= total_pages:
            params = {
                "categories": cat_id,
                "per_page": 100,
                "page": page,
                "_fields": "id,slug,link",
            }
            if exclude_ids:
                params["categories_exclude"] = ",".join(str(x) for x in exclude_ids)
            resp = session.get(
                f"{base_url}/posts",
                params=params,
            )
            if page == 1:
                total_pages = int(resp.headers.get("X-WP-TotalPages", "1"))
            resp.raise_for_status()
            posts = resp.json()
            for post in posts:
                n = None
                if pattern:
                    m = re.match(pattern, post["slug"])
                    if m:
                        n = int(m.group(1))
                if n is not None:
                    by_part.setdefault(n, {})[lang] = post["id"]
                else:
                    egyeb.setdefault(lang, []).append((post["id"], post["slug"]))
            page += 1
    return by_part, egyeb


def process_post(session, base_url, post_id, lang, cta_shortcode_ids, dry_run):
    """Egy adott posztot dolgoz fel. Visszaad egy (action, detail, link)
    harmast, action erteke FRISSITVE / VOLNA_FRISSITVE (dry-run) /
    KIHAGYVA / HIBA."""

    resp = session.get(
        f"{base_url}/posts/{post_id}",
        params={"context": "edit", "_fields": "id,link,meta"},
    )
    if resp.status_code != 200:
        return "HIBA", f"GET {resp.status_code}: {resp.text[:200]}", None

    post = resp.json()
    link = post.get("link")
    raw_data = (post.get("meta") or {}).get("_elementor_data")

    if not raw_data:
        return "HIBA", "nincs _elementor_data meta", link

    try:
        elementor_data = json.loads(raw_data)
    except json.JSONDecodeError:
        return "HIBA", "nem parse-olhato _elementor_data JSON", link

    if has_cta_already(elementor_data):
        return "KIHAGYVA", "mar van CTA-doboz", link

    column = find_first_column(elementor_data)
    if column is None:
        return "HIBA", "nem talalhato column elem", link

    if dry_run:
        return "VOLNA_FRISSITVE", f"sablon id={cta_shortcode_ids[lang]}", link

    shortcode_widget = {
        "id": _new_element_id(),
        "elType": "widget",
        "widgetType": "shortcode",
        "settings": {"shortcode": f"[INSERT_ELEMENTOR id={cta_shortcode_ids[lang]}]"},
        "elements": [],
    }
    column.setdefault("elements", []).append(shortcode_widget)

    patch_resp = session.post(
        f"{base_url}/posts/{post_id}",
        json={"meta": {"_elementor_data": json.dumps(elementor_data, ensure_ascii=False)}},
    )
    if patch_resp.status_code not in (200, 201):
        return "HIBA", f"POST {patch_resp.status_code}: {patch_resp.text[:200]}", link

    return "FRISSITVE", f"uj widget id={shortcode_widget['id']}", link


def main():
    parser = argparse.ArgumentParser(description="Szerzoi CTA-doboz visszamenoleges beillesztese sorozatonkent.")
    parser.add_argument("--sorozat", required=True, choices=sorted(SERIES_CONFIGS.keys()), help="Melyik sorozatot dolgozza fel.")
    parser.add_argument("--dry-run", action="store_true", help="Csak kiirja, mit tenne, POST nelkul.")
    parser.add_argument("--resztol", type=int, default=None, help="Csak ettol a resz-szamtol (bezarolag).")
    parser.add_argument("--reszig", type=int, default=None, help="Csak eddig a resz-szamig (bezarolag).")
    args = parser.parse_args()

    config = SERIES_CONFIGS[args.sorozat]
    secrets = load_secrets()
    base_url = f"{secrets['WP_URL']}/wp-json/wp/v2"

    session = requests.Session()
    session.auth = HTTPBasicAuth(secrets["WP_USER"], secrets["WP_APP_PASSWORD"])

    print(f"Sorozat: {config['label']} ({args.sorozat})")
    print("Reszek felderitese WP REST kategoria-listazassal...")
    by_part, egyeb = discover_posts(
        session, base_url, config["category_ids"], config["patterns"],
        category_exclude_ids=config.get("category_exclude_ids"),
    )
    print(f"  {len(by_part)} resz-szam talalva.")
    for lang, items in egyeb.items():
        if items:
            print(f"  FIGYELEM: {len(items)} poszt a(z) {lang} kategoriaban NEM illeszkedik a vart slug-mintara, kulon lesz feldolgozva: {[s for _, s in items]}")

    already_done = config.get("already_done", set())
    parts = sorted(by_part.keys())
    if args.resztol is not None:
        parts = [n for n in parts if n >= args.resztol]
    if args.reszig is not None:
        parts = [n for n in parts if n <= args.reszig]

    to_process = [n for n in parts if n not in already_done]
    skipped_already_done = [n for n in parts if n in already_done]
    if skipped_already_done:
        print(f"  {len(skipped_already_done)} resz mar korabban feldolgozva, most at lesz ugorva: {skipped_already_done}")

    if args.dry_run:
        print("*** DRY RUN -- nem tortenik valos iras, csak szimulacio. ***")

    summary = {"FRISSITVE": 0, "VOLNA_FRISSITVE": 0, "KIHAGYVA": 0, "HIBA": 0}
    langs_in_config = list(config["category_ids"].keys())

    for n in to_process:
        posts_for_part = by_part[n]
        for lang in langs_in_config:
            post_id = posts_for_part.get(lang)
            if post_id is None:
                print(f"[HIANYZIK] {n}. resz ({lang}) -- nem talalhato poszt ehhez a nyelvhez")
                summary["HIBA"] += 1
                continue

            action, detail, link = process_post(session, base_url, post_id, lang, CTA_SHORTCODE_IDS, args.dry_run)
            summary[action] += 1
            print(f"[{action}] {n}. resz ({lang}) - poszt {post_id} - {detail}")
            if link:
                print(f"          {link}")

    # A vart mintara nem illeszkedo, de a kategoriaban ennek ellenere
    # megtalalt posztok -- ezeket is feldolgozzuk, resz-szam- (es igy
    # --resztol/--reszig-) szures nelkul.
    for lang, items in egyeb.items():
        for post_id, slug in items:
            action, detail, link = process_post(session, base_url, post_id, lang, CTA_SHORTCODE_IDS, args.dry_run)
            summary[action] += 1
            print(f"[{action}] EGYEDI slug={slug} ({lang}) - poszt {post_id} - {detail}")
            if link:
                print(f"          {link}")

    print()
    print("Osszesites:", summary)

    log_line = (
        f"{datetime.now().isoformat(timespec='seconds')} | sorozat={args.sorozat} "
        f"dry_run={args.dry_run} resztol={args.resztol} reszig={args.reszig} "
        f"osszesites={summary}\n"
    )
    with open("scripts/retrofit_log.txt", "a", encoding="utf-8") as f:
        f.write(log_line)


if __name__ == "__main__":
    main()
