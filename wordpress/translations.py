"""
wordpress/translations.py

Ez a modul tartja nyilván, hogy egy adott TÖRTÉNET (fordítás-
csoport, lásd converter/metadata_parser.build_csoport_azonosito)
melyik nyelvi verziója melyik WordPress poszt-ID-hoz tartozik —
majd amikor legalább 2 nyelvi verzió már ismert, összeköti őket
Polylang-fordításként a wp_client.WordPressClient segítségével.

MIÉRT KELL EZ, HELYI FÁJLBAN TÁROLVA?

A feleséged a magyar/angol/spanyol verziót NEM egyszerre, hanem
EGYMÁS UTÁN, külön ODT-fájlokból, akár külön napokon hozza létre
(lásd a specifikáció Polylang-integrációról szóló részét). Amikor
az ELSŐ nyelvi verzió elkészül, a másik kettő poszt-ID-je még nem
is létezik — nincs mit összekötni. A programnak emlékeznie kell
arra, hogy "a 'A szalon-77' történet magyar verziója a 11234-es
poszt", hogy amikor később elkészül az angol verzió is, tudja,
melyik két posztot kell összekötnie. Mivel a program bezárása
UTÁN is emlékeznie kell erre, ezt egy FÁJLBAN tároljuk, nem csak a
memóriában.
"""

import json
import os

from paths import get_project_root


# Alapértelmezett hely az állapot-fájlnak — a projekt gyökeréhez
# (lásd paths.get_project_root()) képest, NEM a jelenlegi
# munkakönyvtárhoz képest (ugyanaz a mintakövetés, mint a
# ".env/secrets" és a "config/sorozatok.json" esetében).
DEFAULT_STATE_PATH = os.path.join(
    get_project_root(),
    "state",
    "forditasi_csoportok.json"
)


def load_state(path=None):
    """
    Beolvassa az állapot-fájlt. A formátuma:

        {
          "A szalon-77": {"hu": 11234, "en": 11267},
          "A szalon-78": {"hu": 11290}
        }

    Ha a fájl még nem létezik (pl. ez az ELSŐ valaha létrehozott
    poszt), üres dict-et ad vissza — ez NEM hiba, egyszerűen még
    nincs semmilyen korábbi állapot.
    """

    if path is None:
        path = DEFAULT_STATE_PATH

    if not os.path.isfile(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state, path=None):
    """
    Elmenti az állapot-fájlt. Ha a "state/" mappa még nem létezik
    (pl. a legelső futáskor), létrehozza — a felhasználónak NEM
    kell ezt előre elkészítenie, ellentétben a ".env/" és
    "config/" mappákkal (azok érzékeny/kézzel szerkesztendő
    adatokat tartalmaznak, ezt a fájlt viszont KIZÁRÓLAG a program
    maga írja és olvassa).
    """

    if path is None:
        path = DEFAULT_STATE_PATH

    directory = os.path.dirname(path)

    if directory and not os.path.isdir(directory):
        os.makedirs(directory)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def register_post_and_link(
    wp_client,
    csoport_azonosito,
    nyelv,
    post_id,
    state_path=None
):
    """
    A modul FŐ belépési pontja — ezt hívja meg a GUI (lásd
    ui/main_window.py) MINDEN sikeres poszt-létrehozás UTÁN.

    MEGJEGYZÉS (2026.07.27-i változás): a poszt NYELVÉNEK
    beállítása mostantól MÁR a wp_client.create_post() belsejében
    megtörténik (a poszt létrehozása UTÁN, de a kategóriák
    hozzárendelése ELŐTT — lásd ott a részletes magyarázatot, miért
    fontos ez a sorrend a Polylang miatt). Ez a függvény tehát MÁR
    NEM állítja be újra a nyelvet, csak a fordítás-csoport
    nyilvántartását és összekapcsolását végzi:

    Elvégzi, ebben a sorrendben:

      1. Betölti a helyi állapot-fájlt, és hozzáadja/frissíti benne
         ennek a történetnek ("csoport_azonosito") ezt a nyelvi
         bejegyzését (nyelv -> poszt ID).

      2. HA a történethez már 2 VAGY TÖBB nyelvi verzió ismert
         (akár most, akár korábbi futásokból), összeköti ŐKET
         Polylang-fordításként (wp_client.link_translations) — a
         MINDENKORI teljes, addig ismert csoporttal. Ez azt
         jelenti, hogy ha pl. a magyar és angol már össze volt
         kötve, és most elkészül a spanyol is, ÚJRA meghívjuk a
         összekötést mind a HÁROM poszttal — ez ártalmatlan
         (a Polylang egyszerűen frissíti/megerősíti a csoportot),
         és biztosítja, hogy a végén tényleg mind a három
         összekötve legyen.

      3. Elmenti a frissített állapot-fájlt.

    Visszatérési érték: a történet TELJES, mostanra ismert
    nyelv -> poszt ID leképezése (dict) — ezt a hívó (GUI)
    megjelenítheti a felhasználónak (pl. "eddig elkészült
    nyelvek: hu, en").

    HIBAKEZELÉS: ha a link_translations hívás elszáll (pl. mert a
    mu-plugin még nincs telepítve a WordPress oldalon), ez a
    függvény NEM nyeli el a hibát — a requests HTTPError feljut a
    hívóig (a GUI-ig), ahol a meglévő try/except már úgyis kezeli
    és megjeleníti. FONTOS VISZONT, hogy eddigre a POSZT MÁR
    LÉTREJÖTT ÉS A NYELVE MÁR BE VAN ÁLLÍTVA a WordPress-en (hiszen
    ezt a függvényt csak SIKERES create_post() UTÁN hívjuk) — tehát
    egy itteni hiba esetén a poszt megvan, helyes nyelvvel, csak az
    ÖSSZEKAPCSOLÁS maradt el, ezt a felhasználónak KÉZZEL kell
    pótolnia a WP adminban, amíg a mu-plugin hibáját ki nem
    javítjátok.
    """

    state = load_state(state_path)

    csoport = state.get(csoport_azonosito, {})
    csoport[nyelv] = post_id
    state[csoport_azonosito] = csoport

    if len(csoport) >= 2:
        wp_client.link_translations(csoport)

    save_state(state, state_path)

    return csoport
