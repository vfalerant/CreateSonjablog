"""
metadata_parser.py

A odt_reader.read_odt_document() által visszaadott NYERS
(label, érték) táblázat-sorokból épít egy STRUKTURÁLT dict-et,
amit aztán a validators.py ellenőriz, a wordpress/wp_client.py
(2. lépés) pedig felhasznál a poszt létrehozásához.

Miért van szükség erre a köztes lépésre (miért nem elég a nyers
táblázat)?
  - a táblázatban minden cella egyszerű szöveg (string), de nekünk
    listákra (kategóriák, kulcsszavak) és számokra (kép ID, rész
    sorszám) és dátumra van szükségünk
  - a szerző (a feleség) magyar mezőneveket lát a táblázatban, a
    program viszont belső, angolos kulcsnevekkel dolgozik tovább
    (ez a FIELD_MAP feladata)
"""

import datetime


# A táblázatban elvárt dátumformátum, a specifikáció 8.1 pontja
# szerint rögzítve: ÉÉÉÉ.HH.NN ÓÓ:PP, pl. "2026.08.03 09:00"
# Ha ez valaha megváltozik, EZT az egy sort kell módosítani —
# a strptime/strftime ugyanezt a mintát használja mindenhol.
DATE_FORMAT = "%Y.%m.%d %H:%M"


# A táblázat bal oszlopában szereplő (magyar) mezőnév -> belső
# kulcsnév megfeleltetés. FONTOS: a kulcsok itt már kisbetűsek,
# mert a parse_metadata() a bejövő label-t is kisbetűsíti
# összehasonlítás előtt (lásd lentebb) — így ha a szerző véletlenül
# "Cím" helyett "cím"-et vagy "CÍM"-et ír, azt is felismeri.
#
# HA ÚJ METAADAT MEZŐT VESZÜNK FEL a sablonba, ITT kell hozzáadni
# egy új sort, ÉS a specifikáció 2.1 pontjában is dokumentálni.
FIELD_MAP = {
    "cím": "cim",
    "publikálás dátuma": "datum",
    "kategóriák": "kategoriak_raw",
    "beleolvasó szövege": "beleolvaso",
    "seo snippet": "seo_snippet",
    "seo kulcsszavak": "seo_kulcsszavak_raw",
    "kiemelt kép id": "kiemelt_kep_id_raw",
    "sorozat neve": "sorozat_nev",
    "rész sorszáma": "resz_szam_raw",
    "nyelv": "nyelv",
    "történet azonosító": "tortenet_azonosito_raw",
}

# Ezeknek a mezőknek KÖTELEZŐEN ki kell tölteni a táblázatban —
# ha üresek, a validators.py hibát fog jelezni rájuk.
# (Ez a lista jelenleg dokumentációs célú / referencia a
# validators.py-hoz; a tényleges kötelezőség-ellenőrzést a
# validators.py végzi mezőnként, külön-külön hibaüzenettel.)
REQUIRED_FIELDS = [
    "cim",
    "datum",
    "kategoriak_raw",
    "nyelv",
]

# Ezek a mezők opcionálisak — üresen hagyhatók a táblázatban
# (pl. ha a bejegyzés nem egy sorozat része, a "Sorozat neve" és
# "Rész sorszáma" mezők üresek maradnak). A "Történet azonosító"
# IS ide tartozik — lásd a build_csoport_azonosito() magyarázatát:
# sorozat-résznél NEM kell kitölteni, mert a program a "Sorozat
# neve" + "Rész sorszáma" párosból automatikusan képez egy
# egyedi azonosítót; egyedi (nem sorozat) bejegyzésnél viszont
# KÖTELEZŐ — ezt a validators.py ellenőrzi.
OPTIONAL_FIELDS = [
    "beleolvaso",
    "seo_snippet",
    "seo_kulcsszavak_raw",
    "kiemelt_kep_id_raw",
    "sorozat_nev",
    "resz_szam_raw",
    "tortenet_azonosito_raw",
]

# A blog oldal 3 nyelve, ahogy a Polylang-ban be vannak állítva
# (WP admin → Languages → Language Code). Ha valaha új nyelv
# kerülne a blogra, ITT kell bővíteni a listát.
VALID_NYELVEK = ["hu", "en", "es"]


def split_csv_field(raw_value):
    """
    Egy vesszővel elválasztott mezőt (pl. kategóriák vagy SEO
    kulcsszavak) listává alakít, a felesleges szóközöket levágva,
    és az üres darabokat (pl. ha valaki véletlenül dupla vesszőt
    írt: "novella,, karácsonyi") kiszűrve.

    Példa: 'novella, karácsonyi' -> ['novella', 'karácsonyi']
    Üres bemenet ('' vagy None) esetén üres listát ad vissza.
    """

    if not raw_value:
        return []

    return [
        part.strip()
        for part in raw_value.split(",")
        if part.strip()
    ]


def parse_metadata(rows):
    """
    A modul FŐ belépési pontja.

    Bemenet:
      rows — a odt_reader.read_odt_document() második eleme:
             lista (label, érték) tuple-ökből, közvetlenül a
             táblázat celláiból, még "nyersen" (semmi
             feldolgozás, csak a szöveg).

    Kimenet: (metadata, unrecognized_labels) tuple
      metadata — dict, a FIELD_MAP összes belső kulcsával
                 feltöltve. A hiányzó mezők üres string ("") vagy
                 None értéket kapnak (lásd lentebb melyik mikor).
      unrecognized_labels — azon táblázat-sorok bal oszlopának
                 szövege, amit NEM sikerült egyeztetni egyik ismert
                 mezőnévvel sem. Ez önmagában NEM feltétlenül hiba
                 (lehet, hogy a szerző csak egy extra megjegyzés-
                 sort tett a táblázatba), de jó jelzés lehet
                 elgépelés gyanúja esetén — a GUI-ban érdemes
                 kiírni figyelmeztetésként.
    """

    # előre feltöltjük az összes ismert kulcsot üres stringgel,
    # hogy a hívó kód (validators.py, wp_client.py) mindig
    # biztonságosan hivatkozhasson rájuk .get() nélkül is —
    # nem lesz KeyError, ha egy mező hiányzik a táblázatból
    metadata = {
        key: ""
        for key in FIELD_MAP.values()
    }

    unrecognized_labels = []

    for label, value in rows:

        # kis- és nagybetű-érzéketlen összehasonlítás — a szerzőnek
        # nem kell pontosan úgy írnia a mezőnevet, ahogy a
        # FIELD_MAP-ben szerepel (bár az ékezeteknek egyezniük kell)
        key = FIELD_MAP.get(
            label.strip().lower()
        )

        if key is None:
            # ismeretlen mezőnév -> gyanús sor, de nem dobunk hibát
            # itt, csak jelezzük a hívónak
            unrecognized_labels.append(label)
            continue

        metadata[key] = value.strip()

    # a vesszővel elválasztott mezőket listává alakítjuk
    metadata["kategoriak"] = split_csv_field(
        metadata.get("kategoriak_raw", "")
    )

    metadata["seo_kulcsszavak"] = split_csv_field(
        metadata.get("seo_kulcsszavak_raw", "")
    )

    # a numerikus mezőket (opcionálisak) int-té próbáljuk alakítani;
    # ha üres vagy nem szám, None lesz belőle — a validators.py
    # dönti el, hogy ez hiba-e (pl. kiemelt kép ID esetén igen, ha
    # ki VAN töltve, de nem szám)
    metadata["kiemelt_kep_id"] = parse_optional_int(
        metadata.get("kiemelt_kep_id_raw", "")
    )

    metadata["resz_szam"] = parse_optional_int(
        metadata.get("resz_szam_raw", "")
    )

    # a dátumot is megpróbáljuk értelmezni már itt (nem csak a
    # validators.py-ban), hogy a wp_client.py (2. lépés) egyből
    # egy kész datetime objektumot kapjon, ne kelljen neki is
    # újra parse-olnia a szöveget
    metadata["datum_parsed"] = parse_publish_date(
        metadata.get("datum", "")
    )

    # a Polylang-fordítások összekapcsolásához szükséges "csoport-
    # azonosítót" számoljuk ki itt — lásd build_csoport_azonosito()
    metadata["csoport_azonosito"] = build_csoport_azonosito(
        metadata
    )

    return metadata, unrecognized_labels


def build_csoport_azonosito(metadata):
    """
    Kiszámolja a nyelvi-fordítás CSOPORT-AZONOSÍTÓJÁT — ez köti
    össze ugyanannak a történetnek a magyar/angol/spanyol nyelvű
    posztjait, hogy a wordpress/wp_client.py tudja, melyik posztok
    tartoznak egymáshoz Polylang-fordításként (lásd a specifikáció
    Polylang-integrációról szóló részét).

    KÉT FORRÁSBÓL képezhető, ELSŐBBSÉGI SORRENDBEN:

      1. Ha a "Történet azonosító" mező ki van töltve, EGYSZERŰEN
         AZT használjuk változatlanul — ez ad teljes szabadságot
         egyedi (nem sorozat) bejegyzéseknél.

      2. Ha a "Történet azonosító" ÜRES, de a "Sorozat neve" ÉS a
         "Rész sorszáma" mindkettő ki van töltve, ebből a kettőből
         AUTOMATIKUSAN képezünk egy azonosítót (pl. "A szalon-77")
         — FONTOS, hogy a "Sorozat neve" mezőt MINDHÁROM nyelvi
         táblázatban UGYANÚGY (a magyar nevén) kell megadni, hogy
         a három nyelvi verzió azonosítója egyezzen! Ez már eddig
         is elvárás volt a sorozat-navigációhoz (lásd
         converter/navigation.py), tehát nem jelent új terhet.

      3. Ha EGYIK forrás sem elérhető (nincs se "Történet
         azonosító", se teljes "Sorozat neve" + "Rész sorszáma"
         páros), None-t ad vissza — a validators.py ezt hibaként
         jelzi ("nem lehet megállapítani a fordítás-csoportot").

    A visszaadott érték NEM kerül a WordPress-be semmilyen látható
    mezőként — ez KIZÁRÓLAG a program saját, helyi
    state/forditasi_csoportok.json állapot-fájljának kulcsa (lásd
    wordpress/wp_client.py), hogy a külön-külön létrehozott nyelvi
    verziókat utólag össze tudja párosítani.
    """

    tortenet_azonosito = metadata.get(
        "tortenet_azonosito_raw", ""
    ).strip()

    if tortenet_azonosito:
        return tortenet_azonosito

    sorozat_nev = metadata.get("sorozat_nev", "").strip()
    resz_szam = metadata.get("resz_szam")

    if sorozat_nev and resz_szam is not None:
        return f"{sorozat_nev}-{resz_szam}"

    return None


def parse_optional_int(raw_value):
    """
    Egy opcionális, egész számot váró mezőt (Kiemelt kép ID, Rész
    sorszáma) alakít int-té. Üres string esetén None-t ad vissza
    (ez a "nincs kitöltve" jelzés). Ha a szöveg NEM üres, de nem is
    érvényes szám (pl. elgépelés), szintén None-t ad vissza — EBBEN
    az esetben viszont a validators.py hibát fog jelezni, mert
    különbséget kell tudnunk tenni "üresen hagyva" és "hibásan
    kitöltve" között (ezért van két külön "_raw" és feldolgozott
    mező, lásd metadata["kiemelt_kep_id_raw"] vs.
    metadata["kiemelt_kep_id"]).
    """

    raw_value = (raw_value or "").strip()

    if not raw_value:
        return None

    try:
        return int(raw_value)
    except ValueError:
        return None


def parse_publish_date(raw_value):
    """
    A "Publikálás dátuma" mezőt próbálja meg értelmezni a szigorúan
    elvárt 'ÉÉÉÉ.HH.NN ÓÓ:PP' formátum szerint (pl. '2026.08.03
    09:00' — lásd DATE_FORMAT fent).

    SZÁNDÉKOSAN nem próbálkozunk alternatív formátumok
    "kitalálásával" (pl. 2026-08-03 vagy 08/03/2026) — a
    specifikáció 8.1 pontja szerint ez egy szigorú, egyértelmű
    szabály, hogy elkerüljük a félreértelmezést (pl. hónap/nap
    felcserélését).

    Hibás formátum vagy üres mező esetén None-t ad vissza — ezt a
    validators.py alakítja emberi hibaüzenetté.
    """

    raw_value = (raw_value or "").strip()

    if not raw_value:
        return None

    try:
        return datetime.datetime.strptime(
            raw_value,
            DATE_FORMAT
        )
    except ValueError:
        return None
