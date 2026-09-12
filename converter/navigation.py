"""
converter/navigation.py

Ez a modul építi fel a sorozat-bejegyzésekhez tartozó navigációs
HTML-t, amit a törzsszöveg (html_generator.generate_html kimenete)
ALÁ fűzünk be, mielőtt elküldenénk a WordPress-nek — lásd a
specifikáció 9. pontját.

Két dolgot generálhat:

  1. "Sorozat eleje" gomb — csak akkor, ha ez NEM az adott sorozat
     1. része (annak nincs értelme saját magára mutatnia). A gomb
     célja (URL, megjelenő cím) a config/sorozatok.json fájlból jön.

  2. Láthatatlan JELÖLŐ (HTML comment) — MINDEN sorozat-résznél
     bekerül, azon a helyen, ahova majd a "következő rész" gomb
     kerülne, HA/AMIKOR a következő rész megjelenik. Ez a jelölő
     teszi lehetővé, hogy egy KÉSŐBBI (még nem elkészült)
     poszt-frissítő funkció BIZTONSÁGOSAN, tévedés nélkül
     megtalálja, hova kell beszúrnia a linket — és garantálja, hogy
     a frissítő funkció CSAK ezt a programot generálta posztokat
     tudja módosítani (lásd a specifikáció 9. pontjának végét).

     2026.08.23-i bővítés: amíg a poszt-frissítő funkció nem
     készül el, a jelölő MOST MÁR nem csak a puszta azonosító
     komment, hanem a jelenlegi rész-szám alapján előre kiszámítható
     KÖVETKEZŐ rész gombjának TELJES, kikommentezett HTML-kódját is
     tartalmazza (lásd build_next_part_marker) — így a férj kézzel,
     a WordPress szerkesztőben egyszerű kikommentezéssel be tudja
     illeszteni a gombot a korábbi rész posztjába, anélkül, hogy
     neki kellene begépelnie a HTML-t.

HA A BEJEGYZÉS NEM RÉSZE SEMMILYEN SOROZATNAK (a "Sorozat neve" mező
üresen maradt az ODT táblázatban), ez a modul semmit nem csinál —
build_navigation_html() ekkor üres stringet ad vissza, és a
törzsszöveg változatlan marad.
"""

import json
import os

from paths import get_project_root


# Alapértelmezett hely a sorozat-konfigurációs fájlnak — a projekt
# gyökeréhez (lásd paths.get_project_root()) képest, NEM a
# jelenlegi munkakönyvtárhoz képest (ugyanaz a mintakövetés, mint a
# wordpress/config.py ".env/secrets"-nél — lásd ott a részletes
# magyarázatot, miért fontos ez becsomagolt .exe esetén).
DEFAULT_SERIES_CONFIG_PATH = os.path.join(
    get_project_root(),
    "config",
    "sorozatok.json"
)

# A láthatatlan jelölő NYITÓ sorának SABLONJA. A {series} és {part}
# helyekre a JELENLEGI poszt sorozatneve és rész-sorszáma kerül — ez
# teszi "önazonosítóvá" a jelölőt: a jövőbeli frissítő funkció ebből
# tudja majd megkeresni, hogy MELYIK sorozat MELYIK részéhez
# tartozik ez a placeholder, hálózati/adatbázis-lekérdezés nélkül,
# pusztán a poszt tartalmát átvizsgálva.
#
# SZÁNDÉKOSAN nincs benne a záró "-->" — a build_next_part_marker()
# a nyitó sor UTÁN, MÉG a lezárás ELŐTT szúrja be a kikommentezett
# előnézeti gomb HTML-jét (lásd ott), hogy az egész (azonosító +
# gomb-előnézet) EGYETLEN HTML-kommentben maradjon.
#
# HA EZT A SABLONT VALAHA MÓDOSÍTOD, a már korábban legenerált (és
# a WordPress-en már élő) posztokban lévő RÉGI jelölők nem fognak
# egyezni az új mintával — a poszt-frissítő funkciónak (amikor
# elkészül) ezzel számolnia kell, vagy egy migrációt kell futtatni
# a régi posztokon.
MARKER_OPEN_TEMPLATE = (
    '<!-- SONJABLOG:NEXT_PART_PLACEHOLDER '
    'series="{series}" part="{part}"'
)

# A "sorozat eleje" gomb KÖRÜLI, FIX szövegek nyelvenkénti
# fordítása (2026.07.27-i bővítés — a blog háromnyelvű, Polylang-
# gal, lásd a specifikáció 10. pontját). A gomb SZÖVEGE nem lehet
# vegyes nyelvű: egy angol poszt alatt nem jelenhet meg magyar
# mondat, még akkor sem, ha a linkelt cím (elso_resz_cim) már eleve
# a megfelelő nyelven van a config/sorozatok.json-ban.
#
# EZEK CSAK az ÁLTALÁNOS, minden sorozatra érvényes ALAPÉRTELMEZÉST
# adják (2026.08.23-i bővítés). Ha egy adott sorozathoz (pl. mert a
# generikus "sorozat részeit"/"rész" megfogalmazás nyelvtanilag nem
# illik rá, mint "Emily naplója" esetén) egyedi szöveg kell, a
# config/sorozatok.json adott sorozat+nyelv blokkjában az alábbi
# opcionális kulcsokkal FELÜLÍRHATÓ (lásd build_series_start_html és
# build_next_part_button_html):
#   - "elso_resz_intro"             -> felülírja a teljes "intro" sort
#   - "kovetkezo_resz_cimke_sablon" -> felülírja a "resz_cimke" sablont
#   - "kovetkezo_resz_szoveg"       -> felülírja a "folytatas" sort
#
# (2026.09.12-i bővítés: egy TOVÁBBI, hasonló elvű, de NEM a
# navigációs gombokhoz, hanem a RankMath SEO leírás mezőjéhez
# tartozó opcionális kulcs is idekerülhet ugyanezekbe a sorozat+
# nyelv blokkokba — lásd build_meta_description_suffix() lentebb és
# a specifikáció 8.6 pontját:
#   - "meta_description_sablon"     -> a SEO snippet VÉGÉRE fűzendő,
#                                       sorozat-specifikus mondat,
#                                       {n} helyére a rész sorszáma
#                                       kerül)
#
# HA ÚJ NYELV KERÜL A BLOGRA, ITT kell felvenni egy új bejegyzést —
# ÉS bővíteni a metadata_parser.VALID_NYELVEK listát is.
NAV_TEXT_TEMPLATES = {
    "hu": {
        "new_here": "Új vagy?",
        # {series} helyére a config/sorozatok.json adott nyelvű
        # "megjelenitett_nev" mezője kerül (NEM a belső, magyar
        # azonosító!)
        "intro": (
            "Olvasd el {series} sorozat részeit az elejétől, és "
            "ismerd meg, minden szereplő történetét \u2192"
        ),
        # a "következő rész" gombhoz (2026.07.27-i bővítés):
        # "{n}. rész" -> pl. "14. rész"
        "resz_cimke": "{n}. rész",
        # 2026.08.23-tól a nyíl MÁR ITT, a szöveg részeként szerepel
        # (korábban a kódban volt automatikusan hozzáfűzve) — azért
        # került ide, hogy egy sorozat-specifikus felülírás (lásd
        # fent) szabadon eldönthesse, kell-e egyáltalán nyíl a sor
        # végére, a kódnak ne kelljen ezt automatikusan
        # hozzáragasztania minden esetben.
        "folytatas": "Folytatás →",
    },
    "en": {
        "new_here": "New here?",
        # SZÁNDÉKOSAN nincs "the" a sablonban a {series} elé írva —
        # a megjelenitett_nev mezőben te adod meg pontosan úgy,
        # ahogy szerepelnie kell (pl. "The Salon"), hogy elkerüljük
        # a dupla névelőt ("Read the The Salon series").
        "intro": (
            "Start from the beginning and discover every "
            "character\u2019s story \u2192"
        ),
        "resz_cimke": "Part {n}",
        "folytatas": "Continue →",
    },
    "es": {
        "new_here": "¿Eres nuevo?",
        "intro": (
            "Empieza desde el principio y descubre la historia de "
            "cada personaje \u2192"
        ),
        "resz_cimke": "Parte {n}",
        "folytatas": "Continuar →",
    },
}


def load_series_config(path=None):
    """
    Beolvassa a sorozatok.json fájlt, és egy dict-et ad vissza:
    sorozat BELSŐ (magyar) azonosítója -> {nyelvkód -> {
        "megjelenitett_nev": ..., "elso_resz_url": ...,
        "elso_resz_cim": ...
    }}

    (2026.07.27-i bővítés: a config immár NYELVENKÉNT tárolja az
    adatokat, mert a gomb szövege és a linkelt URL is nyelvenként
    eltérő — lásd a NAV_TEXT_TEMPLATES és build_series_start_html
    magyarázatát.)

    Az "_"-vel kezdődő kulcsokat (pl. "_megjegyzes") kihagyja — ezt
    a JSON formátum nem támogatja natívan a kommenteket, ezért egy
    ilyen "álkulcsot" használunk dokumentációs célra a fájlban, amit
    itt szűrünk ki, hogy ne próbáljon meg "sorozatként" értelmezni.

    Ha a fájl nem létezik, ÜRES dict-et ad vissza (nem hibát dob) —
    ez azért ésszerű alapértelmezés, mert ha valakinek egyáltalán
    nincs sorozat-bejegyzése, nem kellene emiatt hibáznia a
    programnak; a validators.py úgyis csak akkor néz bele ebbe a
    configba, ha a metaadat-táblázatban ki van töltve a "Sorozat
    neve" mező.
    """

    if path is None:
        path = DEFAULT_SERIES_CONFIG_PATH

    if not os.path.isfile(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        raw_config = json.load(f)

    return {
        key: value
        for key, value in raw_config.items()
        if not key.startswith("_")
    }


def build_series_start_html(series_name, nyelv, series_config):
    """
    Felépíti a "sorozat eleje" gomb HTML-jét, a
    config/sorozatok.json-ban tárolt, AZ ADOTT NYELVHEZ tartozó URL,
    cím és megjelenített sorozat-név alapján, a gomb körüli fix
    szövegeket pedig a NAV_TEXT_TEMPLATES megfelelő nyelvi
    változatából véve — így sem az URL, sem a cím, sem a gomb
    szövege NEM keveredhet a poszt nyelvétől eltérő nyelvvel.

    Hibát dob (ValueError), ha:
      - a megadott sorozatnév TELJESEN hiányzik a configból, VAGY
      - a sorozat ISMERT, de ehhez a KONKRÉT nyelvhez nincs
        beállítva benne adat (pl. valaki elfelejtette hozzáadni az
        angol változatot egy már létező sorozathoz)

    Ezt a validators.py-ban ELŐRE ellenőrizzük (lásd
    _validate_sorozat), úgyhogy ide már csak validált adattal
    szabadna eljutni — de ha mégis idáig jutna egy hiányos eset,
    inkább egy egyértelmű hibaüzenettel álljon le, mint hogy egy
    hibás/üres/vegyes nyelvű linket generáljon.
    """

    sorozat_nyelvek = series_config.get(series_name)

    if sorozat_nyelvek is None:
        raise ValueError(
            f"Nincs ilyen sorozat a config/sorozatok.json "
            f"fájlban: '{series_name}'. Add hozzá a sorozatot a "
            f"konfigurációs fájlhoz, mielőtt posztot hoznál létre "
            f"hozzá."
        )

    info = sorozat_nyelvek.get(nyelv)

    if info is None:
        raise ValueError(
            f"A(z) '{series_name}' sorozathoz nincs '{nyelv}' "
            f"nyelvű bejegyzés a config/sorozatok.json fájlban "
            f"(pedig a sorozat MÁS nyelven ismert). Egészítsd ki "
            f"a fájlban ezt a sorozatot a hiányzó nyelvvel "
            f"(megjelenitett_nev, elso_resz_url, elso_resz_cim)."
        )

    url = info["elso_resz_url"]
    cim = info["elso_resz_cim"]
    megjelenitett_nev = info["megjelenitett_nev"]

    szoveg = NAV_TEXT_TEMPLATES[nyelv]

    # 2026.08.23-i bővítés: ha a config/sorozatok.json-ban ehhez a
    # sorozat+nyelv archoz meg van adva egyedi "elso_resz_intro", azt
    # HASZNÁLJUK VÁLTOZTATÁS NÉLKÜL (a szerző már a végleges, a
    # sorozat nevéhez nyelvtanilag illeszkedő mondatot írta meg —
    # nincs mit .format()-olni rajta). Ha nincs megadva, marad a
    # generikus sablon, a megjelenitett_nev behelyettesítésével.
    # Erre azért volt szükség (lásd "Emily naplója"), mert a
    # generikus "Olvasd el {series} sorozat részeit..." forma egyes
    # sorozatneveknél nyelvtanilag esetlen ("Olvasd el Emily naplója
    # sorozat részeit...").
    intro_override = info.get("elso_resz_intro")

    if intro_override:
        intro = intro_override
    else:
        intro = szoveg["intro"].format(series=megjelenitett_nev)

    # ez a HTML-sablon a te eredeti, kézzel írt gombod alapján
    # készült (lásd a specifikáció 9. pontját) — a "blog-button"
    # class-t VÁLTOZTATÁS NÉLKÜL használjuk, mert az a WordPress
    # oldal Testreszabó "Additional CSS" mezőjében GLOBÁLISAN van
    # definiálva (border-radius, színek, stb.), tehát ez a sima,
    # program által generált <a> tag is automatikusan felveszi a
    # megfelelő kinézetet
    return (
        f'<a class="blog-button" href="{url}">\n'
        f'<strong>{szoveg["new_here"]}</strong>\n'
        f'<br>\n'
        f'{intro}  \n'
        f'<span style="white-space: nowrap;">\n'
        f'    {cim}\n'
        f'</span>\n'
        f'</a>'
    )


def build_next_part_button_html(series_name, nyelv, resz_szam, series_config):
    """
    Felépíti a "következő rész" gomb HTML-jét EGY ADOTT rész-
    számhoz (resz_szam = a KÖVETKEZŐ rész sorszáma, amire a gomb
    mutat — NEM a jelenlegi poszté).

    FONTOS, MI EZ ÉS MI NEM: ez a függvény CSAK a gomb HTML-jét
    állítja elő. Azt, hogy ez a HTML mikor/hogyan kerül be egy
    KORÁBBAN már létrehozott poszt tartalmába (a
    build_next_part_marker() által elhelyezett láthatatlan jelölő
    helyére) — vagyis maga a poszt-FRISSÍTŐ funkció — egy KÉSŐBBI
    fejlesztési lépés (lásd a specifikáció 9. pontjának végét). Ez
    a függvény csak előkészíti ehhez a szükséges HTML-generálást.

    A "sorozat eleje" gombtól (build_series_start_html) ELTÉRŐEN
    ennek a gombnak:
      - az URL-je NEM egy fix, egyszeri config-érték, hanem a
        config/sorozatok.json-ban tárolt "resz_url_sablon"
        mintából, a rész-szám behelyettesítésével épül fel (pl.
        "/a-szalon-{resz}-resz/" -> "/a-szalon-14-resz/"),
      - a szövege rövidebb, nincs alcím-span, csak a sorozat
        (nyelvspecifikus) neve + a rész-szám + egy "Folytatás"/
        "Continue"/"Continuar" felirat.

    2026.08.23-i bővítés: mind a rész-számot tartalmazó felirat
    ("resz_cimke", pl. "14. rész"), mind az alatta lévő "folytatas"
    sor ("Folytatás →") FELÜLÍRHATÓ sorozatonként, a
    config/sorozatok.json adott sorozat+nyelv blokkjában a
    "kovetkezo_resz_cimke_sablon" (a {n} helyre a rész-szám kerül,
    pl. "{n}. bejegyzés →") és a "kovetkezo_resz_szoveg" (VÉGLEGES,
    nem sablon jellegű szöveg, semmi nem kerül behelyettesítésre
    bele) kulcsokkal. Ha ezek hiányoznak, marad az általános
    NAV_TEXT_TEMPLATES-beli alapértelmezés. Erre azért volt szükség
    (lásd "Emily naplója"), mert ott a rész-szám mellett nem "rész",
    hanem "bejegyzés" szerepel, és a nyíl (→) is máshova kerül (a
    felirat végére, nem a "folytatas" sor végére) — ezt a generikus
    sablon szerkezete nem tudja lefedni.

    Hibát dob (ValueError) ugyanazon esetekben, mint
    build_series_start_html (ismeretlen sorozat, vagy ismert
    sorozat de a nyelv hiányzik belőle).
    """

    sorozat_nyelvek = series_config.get(series_name)

    if sorozat_nyelvek is None:
        raise ValueError(
            f"Nincs ilyen sorozat a config/sorozatok.json "
            f"fájlban: '{series_name}'."
        )

    info = sorozat_nyelvek.get(nyelv)

    if info is None:
        raise ValueError(
            f"A(z) '{series_name}' sorozathoz nincs '{nyelv}' "
            f"nyelvű bejegyzés a config/sorozatok.json fájlban."
        )

    megjelenitett_nev = info["megjelenitett_nev"]
    url = info["resz_url_sablon"].format(resz=resz_szam)

    szoveg = NAV_TEXT_TEMPLATES[nyelv]

    # sorozat-specifikus felulirasok, lasd a docstringet fent es a
    # NAV_TEXT_TEMPLATES tetejen levo magyarazatot -- ha nincsenek
    # megadva a config/sorozatok.json-ban, az altalanos sablonra
    # esunk vissza
    cimke_sablon = info.get("kovetkezo_resz_cimke_sablon", szoveg["resz_cimke"])
    resz_cimke = cimke_sablon.format(n=resz_szam)

    folytatas_szoveg = info.get("kovetkezo_resz_szoveg", szoveg["folytatas"])

    return (
        f'<a class="blog-button" href="{url}">\n'
        f'<strong>{megjelenitett_nev}<br>{resz_cimke}</strong>\n'
        f'<br>\n'
        f'{folytatas_szoveg}\n'
        f'</a>'
    )


def build_next_part_marker(series_name, part_number, nyelv, series_config):
    """
    Felépíti a láthatatlan jelölőt (HTML comment) — lásd a modul
    tetején lévő MARKER_OPEN_TEMPLATE magyarázatát.

    2026.08.23-i bővítés: a jelölő MÁR NEM CSAK a puszta, gépi
    azonosításra szolgáló nyitó sort tartalmazza, hanem — amennyiben
    a config/sorozatok.json-ból ki tudjuk számítani — a KÖVETKEZŐ
    rész (part_number + 1) gombjának TELJES, kikommentezett HTML-
    kódját is, UGYANAZON a kommenten belül. Ez azért hasznos MÁR
    MOST, a poszt-frissítő funkció elkészülte ELŐTT is: amikor a
    következő rész ténylegesen megjelenik, a korábbi rész posztjában
    (a WordPress szerkesztőben) elég a jelölőt megkeresni és a
    komment jeleit (<!-- / -->) eltávolítani — nem kell a gomb
    HTML-jét kézzel begépelni.

    A jelölő NYITÓ sora (series="..." part="...") TOVÁBBRA IS a
    JELENLEGI poszt saját rész-számát azonosítja (nem a következőét)
    — ez marad a jövőbeli automatikus frissítő funkció "kulcsa"
    (lásd a modul tetején lévő magyarázatot); csak a KOMMENT
    TARTALMA (az előnézeti gomb) vonatkozik a következő részre.

    Ha a config/sorozatok.json-ból (még) nem lehet felépíteni a
    következő rész gombját (pl. mert a sorozat vagy a nyelv hiányzik
    belőle — ezt a validators.py rendesen csak az AKTUÁLIS részre
    ellenőrzi, a KÖVETKEZŐre nem tudja, hiszen az még nem létezik),
    egyszerűen a régi, puszta azonosító jelölőt adjuk vissza —
    ez csak egy kényelmi előnézet, a hiánya nem hiba.
    """

    marker_open = MARKER_OPEN_TEMPLATE.format(
        series=series_name,
        part=part_number
    )

    try:
        preview_button_html = build_next_part_button_html(
            series_name,
            nyelv,
            part_number + 1,
            series_config
        )
    except ValueError:
        return f'{marker_open} -->'

    return f'{marker_open}\n{preview_button_html}\n-->'


def build_navigation_html(metadata, series_config):
    """
    A modul FŐ belépési pontja. A metaadatok alapján eldönti, kell-e
    egyáltalán navigációs blokk, és ha igen, felépíti azt.

    Visszatérési érték: egy HTML string, amit a HÍVÓ (a GUI, lásd
    ui/main_window.py) a törzsszöveg generált HTML-je UTÁN fűz be.
    Ha a bejegyzés nem sorozat része, ÜRES stringet ad vissza — a
    hívónak ezt nem kell külön kezelnie, egyszerűen semmi nem
    kerül hozzáfűzésre.

    A generált blokk felépítése:

        <style> ... .sonjablog-nav-item { ... } ... </style>
        <div style="display:flex; ...">
            <div class="sonjablog-nav-item">
                [sorozat eleje gomb — CSAK ha resz_szam > 1]
            </div>
            <div class="sonjablog-nav-item">
                [láthatatlan jelölő — MINDIG, ha van sorozat neve]
            </div>
        </div>

    A "sorozat eleje" gomb az 1. résznél SZÁNDÉKOSAN hiányzik —
    annak nincs értelme saját magára visszamutatnia. A jelölő
    viszont MINDEN résznél bekerül (az 1. résznél is!), mert
    bármelyik résznek lehet később "következő része".

    MIÉRT KELL A ".sonjablog-nav-item" CSOMAGOLÓ ELEM (2026.07.26-i
    javítás): amikor csak EGYETLEN gomb van ténylegesen látható (a
    jelölő maga egy láthatatlan HTML comment, nem foglal helyet), a
    ".blog-button" class önmagában NEM ad meg szélességet asztali
    nézetben (csak a mobil médialekérdezésben, 768px alatt) — emiatt
    a gomb az oldal valamelyik globális stílusa miatt a TELJES
    sorszélességre nyúlhat szét, ahelyett hogy oszlopszerűen,
    korlátozott szélességben jelenne meg. A ".sonjablog-nav-item"
    egy KÜLÖN, saját class, ami a gombot körbevevő elemre ad meg
    szélesség-korlátot — ez SZÁNDÉKOSAN NEM nyúl hozzá a
    ".blog-button" saját stílusához (lásd a modul tetején és a
    build_series_start_html()-nél is), hogy a mobil nézeten már
    bevált, working viselkedés (width:100% 768px alatt) TOVÁBBRA IS
    érvényben maradjon — csak asztali nézetben korlátozzuk a
    szélességet egy ÚJ, ehhez a célhoz tartozó, szűken (scoped)
    beágyazott <style> blokkal.
    """

    series_name = metadata.get("sorozat_nev", "")

    if not series_name:
        # nem sorozat része -> nincs navigációs blokk
        return ""

    nyelv = metadata.get("nyelv", "")
    part_number = metadata.get("resz_szam")

    pieces = []

    if part_number is not None and part_number > 1:

        pieces.append(
            build_series_start_html(
                series_name,
                nyelv,
                series_config
            )
        )

    pieces.append(
        build_next_part_marker(
            series_name,
            part_number,
            nyelv,
            series_config
        )
    )

    # minden darabot (gomb VAGY jelölő) egyformán, saját
    # ".sonjablog-nav-item" csomagolóba teszünk — így ha majd a
    # jövőbeli poszt-frissítő funkció a jelölőt egy valódi
    # "következő rész" gombra cseréli, nem kell új csomagolót
    # hozzáadnia, elég a MEGLÉVŐ div TARTALMÁT lecserélnie
    wrapped_pieces = [
        f'<div class="sonjablog-nav-item">\n{piece}\n</div>'
        for piece in pieces
    ]

    inner_html = "\n".join(wrapped_pieces)

    # a <style> blokkot MINDEN navigációs blokk elé beírjuk — ez
    # apró redundancia (ha egy posztban több navigációs blokk is
    # lenne, ami jelenleg nem fordul elő), de cserébe a HTML widget
    # tartalma önmagában, KÜLSŐ függőség nélkül helyesen jelenik
    # meg, még akkor is, ha valaki csak ezt a részt másolná ki
    # valahova külön
    #
    # A ".sonjablog-nav-item .blog-button" szabályok (2026.07.26-i
    # kiegészítés) a kézzel készített Elementor "HTML nyomógomb"
    # widget saját, widget-szintű "Advanced" beállításait pótolják
    # (háttérszín, box-shadow, illetve a globális ".blog-button"
    # class-tól ELTÉRŐ padding/border-radius érték) — ezek NEM
    # részei a globális ".blog-button" class-nak (lásd a modul
    # elején és build_series_start_html()-nél a magyarázatot), mert
    # az Elementor ezeket külön, az adott widget-példányhoz kötve
    # generálja, amit egy sima <a> taggel nem tudunk "örökölni".
    #
    # SZÁNDÉKOSAN SZŰKEN CÉLZUNK (".sonjablog-nav-item .blog-button",
    # NEM csak ".blog-button" önmagában) — így ha a blogon MÁSHOL is
    # van/lesz ".blog-button" class-t használó elem (pl. egy régebbi,
    # kézzel készített poszt), azt ez a szabály NEM érinti, csak a MI
    # saját navigációs gombjainkat.
    #
    # A padding/border-radius felülírást KIFEJEZETTEN csak asztali
    # nézetre (min-width: 769px) korlátozzuk — ugyanaz az elv, mint
    # a szélesség-korlátozásnál fentebb: a mobil nézet globális,
    # már bevált viselkedését (padding: 2em 1.2em 768px alatt) nem
    # akarjuk felülírni.
    # A ":hover" szabály (2026.07.26-i kiegészítés) a widget
    # Advanced beállításainak "Hover" állapotát pótolja — ez SEM
    # része a globális ".blog-button" class-nak (az csak a
    # szövegszínt tartja fehéren hover esetén, lásd a modul elején
    # dokumentált globális CSS-t), a háttérszín-váltást a widget
    # saját beállítása adta hozzá, amit itt is "bedrótozunk". Ezt
    # SEM korlátozzuk médialekérdezéssel, mert a globális CSS
    # sehol nem állít be háttérszínt hover esetén — nincs mivel
    # ütköznie.
    style_block = (
        "<style>\n"
        ".sonjablog-nav-item {\n"
        "    flex: 1 1 320px;\n"
        "    max-width: 480px;\n"
        "}\n"
        ".sonjablog-nav-item .blog-button {\n"
        "    background-color: #8C6239;\n"
        "    box-shadow: 6px 12px 12px #8C62394D;\n"
        "}\n"
        ".sonjablog-nav-item .blog-button:hover {\n"
        "    background-color: #B07A43;\n"
        "}\n"
        "@media (min-width: 769px) {\n"
        "    .sonjablog-nav-item .blog-button {\n"
        "        border-radius: 1em;\n"
        "        padding-left: 1em;\n"
        "        padding-right: 1em;\n"
        "    }\n"
        "}\n"
        "@media (max-width: 768px) {\n"
        "    .sonjablog-nav-item {\n"
        "        max-width: 100%;\n"
        "    }\n"
        "}\n"
        "</style>"
    )

    return (
        f'{style_block}\n'
        f'<div style="display:flex; flex-wrap:wrap; '
        f'gap:1rem; margin-top:2rem;">\n'
        f'{inner_html}\n'
        f'</div>'
    )


def build_meta_description_suffix(metadata, series_config):
    """
    Felépíti a RankMath SEO leírás (rank_math_description) mező
    VÉGÉRE fűzendő, sorozat- és nyelv-specifikus, figyelemfelhívó
    mondatot (2026.09.12-i bővítés — lásd a specifikáció 8.6
    pontját, "Sonja Blonde SEO strategy" dokumentum, "Meta
    Description Optimization" feladat).

    Bár ez NEM a navigációs gombokhoz tartozik, IDE, ebbe a modulba
    került, mert UGYANAZT a config/sorozatok.json-t, UGYANAZZAL a
    "sorozat neve + nyelv -> adatok" felépítéssel használja, mint a
    build_series_start_html()/build_next_part_button_html() — nem
    indokolt emiatt egy külön modult nyitni.

    CSAK akkor ad vissza NEM ÜRES szöveget, ha MINDHÁROM feltétel
    teljesül:
      1. a bejegyzés sorozat része (a "Sorozat neve" ÉS a "Rész
         sorszáma" mező is ki van töltve — validators.py ezt már
         garantálja, ha egyáltalán eljutottunk idáig, DE ide
         validáció NÉLKÜL is hívható, ezért itt is megnézzük),
      2. a sorozat ISMERT a config/sorozatok.json-ban, az ADOTT
         nyelven,
      3. ehhez a sorozat+nyelv archoz meg van adva a "meta_description_sablon"
         opcionális kulcs (lásd a NAV_TEXT_TEMPLATES feletti
         magyarázatot).

    Ha BÁRMELYIK feltétel hiányzik, ÜRES stringet ad vissza — ez NEM
    hiba (nem dob ValueError-t, ELLENTÉTBEN a navigációs gombok
    build_*_html() függvényeivel), mert ez a mező csak egy OPCIONÁLIS
    SEO-kiegészítés: egy sorozat pontosan úgy publikálható enélkül
    is, mint eddig, csak a SEO leírás nem kap sorozat-specifikus
    záró mondatot. A hívó (wordpress/wp_client.py create_post())
    ilyenkor egyszerűen a sima "SEO snippet" szöveget küldi tovább,
    kiegészítés nélkül.
    """

    series_name = metadata.get("sorozat_nev", "")
    part_number = metadata.get("resz_szam")

    if not series_name or part_number is None:
        return ""

    sorozat_nyelvek = series_config.get(series_name)

    if sorozat_nyelvek is None:
        return ""

    nyelv = metadata.get("nyelv", "")
    info = sorozat_nyelvek.get(nyelv)

    if info is None:
        return ""

    sablon = info.get("meta_description_sablon")

    if not sablon:
        return ""

    return sablon.format(n=part_number)
