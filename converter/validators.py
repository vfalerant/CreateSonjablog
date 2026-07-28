"""
validators.py

Ez a modul dönti el, hogy egy beolvasott és feldolgozott dokumentum
"posztolható-e" — vagyis minden kötelező szabálynak megfelel-e,
mielőtt bármit elküldenénk a WordPress felé.

Lásd a specifikáció 6. pontját (validációs szabályok listája) és a
8.3 pontot (a dátumnak jövőbelinek kell lennie).

FONTOS TERVEZÉSI DÖNTÉS: a kategória- és a kiemelt kép-létezés
ellenőrzéséhez hálózati hívás kell (meg kell kérdezni a WordPress
API-t, hogy létezik-e az adott nevű kategória / ID-jű kép). Mivel ez
a modul (validators.py) az 1. lépésben, a WordPress-integráció
(wp_client.py, 2. lépés) NÉLKÜL készült el, ezeket az
ellenőrzéseket "callback" függvényeken keresztül vesszük át:

    category_exists_fn(name: str) -> bool
    media_exists_fn(media_id: int) -> bool

Ha ezeket a hívó kód NEM adja meg (None marad, mint most, az 1.
lépésben), az adott konkrét ellenőrzés egyszerűen kimarad — a
struktúra és formátum szintű ellenőrzések (üres mező, hibás
dátumformátum, stb.) viszont MINDIG lefutnak, hálózat nélkül is.

Amikor elkészül a wp_client.py (2. lépés), oda kell majd írni két
kis függvényt, ami a WordPress API-t hívja meg, és ÉPPEN ILYEN
szignatúrával (name -> bool, illetve id -> bool) átadni ennek a
validate() függvénynek.
"""

import datetime


def validate(
    metadata,
    unrecognized_labels,
    body_blocks,
    table_found,
    category_exists_fn=None,
    media_exists_fn=None,
    series_config=None,
):
    """
    A FŐ validációs függvény. Az összes szabályt lefuttatja, és egy
    LISTÁVAL tér vissza — minden elem egy-egy emberi nyelvű
    hibaüzenet (magyarul, hogy a GUI-ban közvetlenül kiírható
    legyen a szerzőnek/férjnek).

    Ha a lista ÜRES, a dokumentum hibamentes, a "Poszt létrehozása"
    gomb aktiválható.

    Paraméterek:
      metadata — a metadata_parser.parse_metadata() kimenete
                 (strukturált dict)
      unrecognized_labels — szintén a parse_metadata() kimenete
                 (jelenleg nem dob hibát emiatt, de a jövőben
                 idekerülhetne egy figyelmeztetés, ha szeretnénk)
      body_blocks — a odt_reader.read_odt_document() második eleme
                 (a törzsszöveg blokkjai)
      table_found — bool: volt-e egyáltalán táblázat a dokumentumban
                 (ha nem, a metadata dict üres/érvénytelen lenne,
                 ezért ezt külön, elsőként ellenőrizzük)
      category_exists_fn, media_exists_fn — lásd a modul tetején
                 lévő magyarázatot; opcionálisak, hálózati
                 ellenőrzéshez
      series_config — a converter.navigation.load_series_config()
                 kimenete (dict), a sorozat neve -> URL/cím
                 adatokkal. Ha a "Sorozat neve" mező ki van töltve,
                 ez alapján ellenőrizzük, hogy a sorozat szerepel-e
                 a config/sorozatok.json fájlban (lásd
                 _validate_sorozat).
    """

    errors = []

    if not table_found:

        # ha nincs táblázat, a mező-szintű ellenőrzéseknek nincs
        # sok értelme (üres lenne minden), de a törzsszöveg
        # meglétét azért még megnézzük, hogy minél TÖBB hibát
        # lássunk egyszerre (ne kelljen egyesével, "hiba -> javít
        # -> újra próbál -> következő hiba" körben haladni)
        errors.append(
            "Nem található metaadat-táblázat a dokumentum elején."
        )
        errors.extend(
            _validate_body(body_blocks)
        )
        return errors

    errors.extend(_validate_cim(metadata))
    errors.extend(_validate_datum(metadata))
    errors.extend(
        _validate_kategoriak(metadata, category_exists_fn)
    )
    errors.extend(
        _validate_kiemelt_kep(metadata, media_exists_fn)
    )
    errors.extend(
        _validate_sorozat(metadata, series_config)
    )
    errors.extend(_validate_nyelv(metadata))
    errors.extend(_validate_csoport_azonosito(metadata))
    errors.extend(_validate_body(body_blocks))

    return errors


def _validate_cim(metadata):
    """A 'Cím' mező egyszerű kötelező-mező ellenőrzése."""

    if not metadata.get("cim"):
        return ["A 'Cím' mező nem lehet üres."]

    return []


def _validate_datum(metadata):
    """
    Háromféle hiba lehet a dátummal kapcsolatban, ezért három
    külön hibaüzenet:
      1. teljesen üres a mező
      2. ki van töltve, de nem a várt ÉÉÉÉ.HH.NN ÓÓ:PP formátumban
      3. helyes formátumú, DE nem jövőbeli időpont (lásd 8.3 —
         szándékosan tiltjuk az azonnali/múltbeli publikálást,
         hogy mindig legyen esély ütemezve ellenőrizni a posztot)
    """

    raw = metadata.get("datum", "")

    if not raw:
        return ["A 'Publikálás dátuma' mező nem lehet üres."]

    # a metadata_parser már megpróbálta értelmezni a dátumot;
    # ha az eredmény None, az azt jelenti, hogy a formátum hibás
    parsed = metadata.get("datum_parsed")

    if parsed is None:
        return [
            "A 'Publikálás dátuma' mező formátuma hibás. "
            "Elvárt formátum: ÉÉÉÉ.HH.NN ÓÓ:PP "
            "(pl. 2026.08.03 09:00)."
        ]

    # datetime.datetime.now() minden validate() híváskor újra
    # lekérdezi az "aktuális" időt, tehát ha a program éppen a
    # határidő pillanatában fut, elképzelhető, hogy egy korábban
    # még érvényes dátum "lejár" — ez szándékos, mert a cél az,
    # hogy TÉNYLEG mindig jövőbeli időpontra ütemezzünk
    if parsed <= datetime.datetime.now():
        return [
            "A dátum nem lehet jelenlegi vagy múltbeli — "
            "adj meg jövőbeli időpontot."
        ]

    return []


def _validate_kategoriak(metadata, category_exists_fn):
    """
    Először azt nézzük, hogy egyáltalán van-e megadva kategória
    (ez hálózat nélkül is ellenőrizhető). Utána, HA van
    category_exists_fn (vagyis a 2. lépés, a WordPress-kliens már
    be van kötve), minden egyes megadott kategórianevet külön-külön
    leellenőrzünk — így ha pl. három kategóriából kettő létezik, de
    egy elgépelt, PONTOSAN azt az egyet nevezzük meg a hibaüzenetben,
    nem csak azt, hogy "valami baj van a kategóriákkal".
    """

    kategoriak = metadata.get("kategoriak", [])

    if not kategoriak:
        return ["A 'Kategóriák' mező nem lehet üres."]

    if category_exists_fn is None:
        # az 1. lépésben (WordPress-kliens nélkül) itt nincs mit
        # tovább ellenőrizni
        return []

    errors = []

    for name in kategoriak:

        if not category_exists_fn(name):
            errors.append(
                f"Nincs ilyen kategória a WordPress oldalon: "
                f"'{name}'."
            )

    return errors


def _validate_kiemelt_kep(metadata, media_exists_fn):
    """
    A 'Kiemelt kép ID' mező OPCIONÁLIS — ha a szerző üresen hagyja,
    az rendben van (nem lesz kiemelt kép a poszton). DE ha ki van
    töltve, akkor:
      1. érvényes egész számnak kell lennie (különben elgépelés)
      2. (ha van media_exists_fn) tényleg léteznie kell ilyen ID-jű
         képnek a WordPress médiatárában
    """

    # a "_raw" mezőt nézzük (a nyers szöveget), nem a már int-té
    # alakított "kiemelt_kep_id"-t — mert épp azt akarjuk
    # megkülönböztetni, hogy a mező tényleg ÜRES volt-e, vagy csak
    # érvénytelen tartalommal lett kitöltve (a parse_optional_int
    # mindkét esetben None-t adna vissza, ha csak arra
    # támaszkodnánk)
    raw = metadata.get("kiemelt_kep_id_raw", "")

    if not raw:
        # opcionális mező, üresen hagyható -> nincs hiba
        return []

    kep_id = metadata.get("kiemelt_kep_id")

    if kep_id is None:
        # ki VAN töltve, de nem sikerült számmá alakítani
        return [
            f"A 'Kiemelt kép ID' mező érvénytelen: '{raw}' "
            f"(egész számnak kell lennie)."
        ]

    if media_exists_fn is None:
        # az 1. lépésben (WordPress-kliens nélkül) csak a
        # formátumot tudjuk ellenőrizni, a tényleges létezést nem
        return []

    if not media_exists_fn(kep_id):
        return [
            f"Nincs ilyen ID-jű kép a médiatárban: {kep_id}."
        ]

    return []


def _validate_sorozat(metadata, series_config):
    """
    A "Sorozat neve" és "Rész sorszáma" mezők EGYÜTT opcionálisak
    (egy önálló, nem sorozat-bejegyzésnél mindkettő üresen marad),
    DE ha az egyik ki van töltve, a MÁSIKNAK is ki kell töltve
    lennie — értelmetlen lenne pl. sorozatnevet megadni rész-szám
    nélkül, vagy fordítva.

    Ha mindkettő ki van töltve, ÉS ez NEM az 1. rész (annak nincs
    "sorozat eleje" gombja, lásd converter/navigation.py), akkor
    azt is ellenőrizzük, hogy a sorozat szerepel-e a
    config/sorozatok.json fájlban — enélkül a navigation.py nem
    tudná felépíteni a "sorozat eleje" gombot (nem tudná, hova
    kellene mutatnia a linknek).

    series_config: a converter.navigation.load_series_config()
    kimenete. Ha None (pl. mert a hívó még nem töltötte be), a
    config-alapú ellenőrzés kimarad — hasonlóan a
    category_exists_fn / media_exists_fn opcionális
    callback-ekhez máshol ebben a modulban.
    """

    sorozat_nev = metadata.get("sorozat_nev", "")
    resz_szam_raw = metadata.get("resz_szam_raw", "")

    # egyik mező sincs kitöltve -> nem sorozat része, rendben van
    if not sorozat_nev and not resz_szam_raw:
        return []

    errors = []

    if sorozat_nev and not resz_szam_raw:
        errors.append(
            "A 'Sorozat neve' mező ki van töltve, de a 'Rész "
            "sorszáma' nincs — vagy mindkettőt töltsd ki, vagy "
            "egyiket se."
        )

    if resz_szam_raw and not sorozat_nev:
        errors.append(
            "A 'Rész sorszáma' mező ki van töltve, de a 'Sorozat "
            "neve' nincs — vagy mindkettőt töltsd ki, vagy "
            "egyiket se."
        )

    # ha bármelyik hiányzik a kettő közül, a további (config-alapú)
    # ellenőrzésnek már nincs értelme
    if errors:
        return errors

    resz_szam = metadata.get("resz_szam")

    if resz_szam is None:
        errors.append(
            f"A 'Rész sorszáma' mező érvénytelen: "
            f"'{resz_szam_raw}' (egész számnak kell lennie)."
        )
        return errors

    if resz_szam < 1:
        errors.append(
            "A 'Rész sorszáma' mezőnek 1-nél nagyobb vagy "
            "egyenlő egész számnak kell lennie."
        )
        return errors

    # az 1. résznek nincs szüksége a sorozat-configban szereplő
    # bejegyzésre (nincs "sorozat eleje" gombja, lásd
    # converter/navigation.py build_navigation_html) — a
    # config-ellenőrzés csak a 2. résztől releváns
    if resz_szam == 1:
        return errors

    if series_config is None:
        # a hívó (pl. az 1-3. lépésben, mielőtt a navigation.py
        # bekötésre került) még nem adta át a configot — ezt az
        # ellenőrzést egyszerűen kihagyjuk, hasonlóan a hálózatot
        # igénylő ellenőrzésekhez
        return errors

    sorozat_nyelvek = series_config.get(sorozat_nev)

    if sorozat_nyelvek is None:
        errors.append(
            f"Nincs ilyen sorozat a config/sorozatok.json "
            f"fájlban: '{sorozat_nev}'. Add hozzá a sorozatot a "
            f"konfigurációs fájlhoz, vagy ellenőrizd, nincs-e "
            f"elgépelés a sorozat nevében."
        )
        return errors

    # a sorozat ISMERT, de lehet, hogy ehhez a KONKRÉT nyelvhez
    # (lásd metadata["nyelv"]) még nincs feltöltve adat a
    # config/sorozatok.json-ban — pl. ha valaki csak a magyar
    # verziót vette fel eddig, az angol/spanyol posztnál ez hiba
    nyelv = metadata.get("nyelv", "")

    if nyelv and nyelv not in sorozat_nyelvek:
        errors.append(
            f"A(z) '{sorozat_nev}' sorozathoz nincs '{nyelv}' "
            f"nyelvű bejegyzés a config/sorozatok.json fájlban. "
            f"Egészítsd ki a fájlban ezt a sorozatot a hiányzó "
            f"nyelvvel (megjelenitett_nev, elso_resz_url, "
            f"elso_resz_cim)."
        )

    return errors


def _validate_nyelv(metadata):
    """
    A "Nyelv" mező kötelező, és az értékének a blog három nyelvének
    egyikének kell lennie ("hu", "en", "es" — lásd
    metadata_parser.VALID_NYELVEK). Ez a mező dönti el, hogy a
    Polylang-integráció (wordpress/wp_client.py) melyik nyelvre
    állítja majd be a posztot.
    """

    # a metadata_parser modult itt importáljuk (nem a fájl tetején),
    # hogy elkerüljük a két modul közötti körkörös importot, ha
    # valaha a metadata_parser is importálná a validators-t
    from converter.metadata_parser import VALID_NYELVEK

    nyelv = metadata.get("nyelv", "").strip()

    if not nyelv:
        return ["A 'Nyelv' mező nem lehet üres."]

    if nyelv not in VALID_NYELVEK:
        return [
            f"A 'Nyelv' mező érvénytelen: '{nyelv}'. Elvárt "
            f"érték: {', '.join(VALID_NYELVEK)}."
        ]

    return []


def _validate_csoport_azonosito(metadata):
    """
    Minden posztnak kell legyen egy fordítás-csoport azonosítója
    (lásd metadata_parser.build_csoport_azonosito) — ez köti össze
    ugyanannak a történetnek a magyar/angol/spanyol verzióját a
    Polylang-integrációban. Ha ez None, azt jelenti, hogy SEM a
    "Történet azonosító" mező, SEM a "Sorozat neve" + "Rész
    sorszáma" páros nincs kitöltve — a programnak nincs mivel
    összekötnie a nyelvi verziókat.
    """

    if metadata.get("csoport_azonosito") is None:
        return [
            "Nem sikerült megállapítani a fordítás-csoport "
            "azonosítóját — vagy töltsd ki a 'Történet azonosító' "
            "mezőt, vagy add meg EGYÜTT a 'Sorozat neve' és 'Rész "
            "sorszáma' mezőket."
        ]

    return []


def _validate_body(body_blocks):
    """
    Megnézi, hogy a törzsszöveg (a metaadat-táblázat UTÁNI rész)
    tartalmaz-e legalább egy nem-üres blokkot. Ha a szerző
    véletlenül csak a táblázatot töltötte ki, de a történet
    szövegét elfelejtette megírni (vagy rossz helyre másolta), ez a
    szabály elkapja.
    """

    has_content = any(
        block["type"] != "empty" and block["text"].strip()
        for block in body_blocks
    )

    if not has_content:
        return [
            "A bejegyzés törzsszövege üres "
            "(a metaadat-táblázat utáni rész)."
        ]

    return []
