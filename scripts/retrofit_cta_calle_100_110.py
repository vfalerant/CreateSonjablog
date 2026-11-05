"""
scripts/retrofit_cta_calle_100_110.py

PROBAKOR: a "Calle la Rosa 22" sorozat 100-110. reszeire (mindharom
nyelven, osszesen 33 poszt) utolagosan ratolja a szerzoi CTA-dobozt,
egy KULON Elementor Shortcode-tipusu widgetkent a poszt meglevo
oszlopaba - ugyanaz a technika, amit a wordpress/wp_client.py
build_elementor_data() fuggvenye hasznal uj posztoknal (lasd ott a
"cta_shortcode" parameter dokumentaciojat).

FONTOS - EZT A GEPEDEN, NORMAL PARANCSSORBOL FUTTASD (nem a Claude
sandbox-jabol), mert a WordPress API-hoz teljes internet-eleres
kell:

    cd Development\CreateSonjablog
    python scripts\retrofit_cta_calle_100_110.py

Ez a script:
  1. Beolvassa a .env/secrets fajlt (ugyanugy, mint a fo program).
  2. A LENTEBBI, mar kikeresett post ID-k alapjan (nem kell hozza uj
     WordPress-lekerdezes) lekeri mindegyik poszt jelenlegi
     _elementor_data-jat.
  3. Ha a posztban MAR van egy "[INSERT_ELEMENTOR" rovidkodot
     tartalmazo Shortcode widget, VAGY egy regi, nyers HTML-es
     "sb-author-cta" class-t tartalmazo blokk -- KIHAGYJA (nem tesz
     bele meg egyet), es ezt kiirja.
  4. Kulonben hozzafuz egy uj "shortcode" tipusu widgetet a poszt
     MEGLEVO oszlopahoz (a tobbi tartalmat NEM bantja), a nyelvnek
     megfelelo CTA-sablon ID-val (lasd CTA_SHORTCODE_IDS lent - ezek
     meg kell, hogy egyezzenek a .env/secrets CTA_SHORTCODE_ID_*
     ertekeivel).
  5. Minden poszthoz kiirja: FRISSITVE / KIHAGYVA / HIBA + a
     poszt linkjet, hogy konnyen at tudd nezni oket a bongeszoben.

EZ CSAK EGY PROBASZKRIPT egy konkret, kezzel osszeallitott
poszt-listahoz (100-110. resz) - ha bevalik, egy KOVETKEZO lepesben
erdemes altalanositani (pl. WP REST kereses alapjan automatikusan
megtalalni egy egesz sorozat OSSZES reszet, nem csak egy kezzel
megadott ID-listat).
"""

import json
import sys

import requests
from requests.auth import HTTPBasicAuth

sys.path.insert(0, ".")
from wordpress.config import load_secrets


# A nyelvenkenti CTA-sablon ID-k -- EZEKNEK EGYEZNIUK KELL a
# .env/secrets fajlban levo CTA_SHORTCODE_ID_HU/EN/ES ertekekkel.
CTA_SHORTCODE_IDS = {
    "hu": "11589",
    "en": "11612",
    "es": "11622",
}

# Kezzel osszeallitott lista: resz-szam -> {nyelv: poszt ID}.
# Ezeket egy WP REST keresessel (search=Calle la Rosa 22) es
# slug-egyeztetessel derítettük ki elore, lasd a beszelgetest.
TARGET_POSTS = [
    {"n": 100, "hu": 8973, "en": 8988, "es": 8982},
    {"n": 101, "hu": 9277, "en": 9289, "es": 9283},
    {"n": 102, "hu": 9322, "en": 9340, "es": 9334},
    {"n": 103, "hu": 9348, "en": 9378, "es": 9360},
    {"n": 104, "hu": 9430, "en": 9457, "es": 9450},
    {"n": 105, "hu": 9495, "en": 9507, "es": 9501},
    {"n": 106, "hu": 9525, "en": 9559, "es": 9553},
    {"n": 107, "hu": 9630, "en": 9645, "es": 9639},
    {"n": 108, "hu": 9651, "en": 9664, "es": 9657},
    {"n": 109, "hu": 9681, "en": 9693, "es": 9687},
    {"n": 110, "hu": 9698, "en": 9713, "es": 9707},
]


def _new_element_id():
    import uuid
    return uuid.uuid4().hex[:7]


def has_cta_already(node):
    """
    Rekurzivan vegigjarja az _elementor_data fat, es megnezi, van-e
    benne MAR egy CTA-dobozra utalo elem:
      - egy "shortcode" tipusu widget, aminek a beallitasa
        tartalmazza az "INSERT_ELEMENTOR" szot, VAGY
      - egy "html" tipusu widget, aminek a tartalma tartalmazza a
        "sb-author-cta" class-t (ez a regi, nyers HTML-es
        probaverziokat fogja meg, amiket kezzel illesztettel be).
    """

    if isinstance(node, list):
        return any(has_cta_already(item) for item in node)

    if not isinstance(node, dict):
        return False

    if node.get("widgetType") == "shortcode":
        shortcode_text = node.get("settings", {}).get("shortcode", "")
        if "INSERT_ELEMENTOR" in shortcode_text:
            return True

    if node.get("widgetType") == "html":
        html_text = node.get("settings", {}).get("html", "")
        if "sb-author-cta" in html_text:
            return True

    return has_cta_already(node.get("elements", []))


def find_first_column(node):
    """
    Megkeresi az ELSO "column" tipusu elemet a faban -- ide fogjuk
    hozzafuzni az uj CTA-widgetet, MELLE a mar meglevo (tipikusan
    "html" tipusu) widgetnek.
    """

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


def process_post(session, base_url, post_id, lang, cta_shortcode_ids):
    """
    Egy adott posztot dolgoz fel: lekeri, ellenorzi, sziksegeseten
    modositja es visszairja. Visszaad egy (action, detail, link)
    harmast, action erteke "FRISSITVE" / "KIHAGYVA" / "HIBA".
    """

    resp = session.get(
        f"{base_url}/posts/{post_id}",
        params={"context": "edit", "_fields": "id,link,meta"}
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

    shortcode_widget = {
        "id": _new_element_id(),
        "elType": "widget",
        "widgetType": "shortcode",
        "settings": {
            "shortcode": f"[INSERT_ELEMENTOR id={cta_shortcode_ids[lang]}]"
        },
        "elements": []
    }

    column.setdefault("elements", []).append(shortcode_widget)

    patch_resp = session.post(
        f"{base_url}/posts/{post_id}",
        json={
            "meta": {
                "_elementor_data": json.dumps(elementor_data, ensure_ascii=False)
            }
        }
    )

    if patch_resp.status_code not in (200, 201):
        return "HIBA", f"POST {patch_resp.status_code}: {patch_resp.text[:200]}", link

    return "FRISSITVE", f"uj widget id={shortcode_widget['id']}", link


def main():
    secrets = load_secrets()

    base_url = f"{secrets['WP_URL']}/wp-json/wp/v2"

    session = requests.Session()
    session.auth = HTTPBasicAuth(secrets["WP_USER"], secrets["WP_APP_PASSWORD"])

    summary = {"FRISSITVE": 0, "KIHAGYVA": 0, "HIBA": 0}

    for target in TARGET_POSTS:
        for lang in ("hu", "en", "es"):
            post_id = target[lang]

            action, detail, link = process_post(
                session, base_url, post_id, lang, CTA_SHORTCODE_IDS
            )

            summary[action] += 1

            print(f"[{action}] {target['n']}. resz ({lang}) - poszt {post_id} - {detail}")
            if link:
                print(f"          {link}")

    print()
    print("Osszesites:", summary)


if __name__ == "__main__":
    main()
