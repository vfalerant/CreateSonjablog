"""
wordpress/wp_client.py

Ez a modul felelős azért, hogy a feldolgozott adatokból (metaadatok
+ a törzsszöveg HTML-je) TÉNYLEGESEN létrehozzon egy posztot a
WordPress oldalon, a REST API-n keresztül.

Amit ez a modul csinál:
  1. Kategórianevek -> kategória ID lekérdezése (és cache-elése,
     hogy egy futás alatt ne kérdezzük le ugyanazt a kategóriát
     többször).
  2. Kép-létezés ellenőrzése ID alapján (a kiemelt képhez).
  3. Az Elementor "egy szekció / egy oszlop / egy HTML widget"
     struktúrájának felépítése (lásd a specifikáció 9. pontját) —
     ez egy JSON, amit a WordPress a poszt `_elementor_data` meta
     mezőjébe ment el.
  4. A teljes poszt létrehozása egyetlen POST kéréssel a
     /wp-json/wp/v2/posts végpontra.

FONTOS ELŐFELTÉTELEK a WordPress oldalon (lásd a specifikáció 4.
pontját is):
  - Application Password létrehozva (WP admin → Felhasználók →
    Profil → Application Passwords)
  - a RankMath SEO meta mezők (rank_math_description,
    rank_math_focus_keyword, rank_math_primary_category)
    regisztrálva vannak show_in_rest=true kapcsolóval
    (functions.php / mu-plugin) — enélkül a WordPress egyszerűen
    KIHAGYJA ezeket az adatokat (nem hibázik, csak nem menti el
    őket!), ami megtévesztő lehet hibakeresésnél.
  - a Polylang-integrációhoz (nyelv beállítása, fordítások
    összekapcsolása) a mu-pluginban regisztrálva van a
    "sonjablog/v1/set-language" és "sonjablog/v1/link-translations"
    egyéni REST végpont — lásd set_post_language() és
    link_translations() lentebb, és a wordpress/translations.py
    modult, ami ezeket a MEGFELELŐ időzítéssel hívja.

Ez a modul NEM dönti el, hogy egy poszt "postolható-e" — az a
converter/validators.py feladata. Ide már csak a validáción átment,
tiszta adatok érkeznek.
"""

import json
import uuid

import requests
from requests.auth import HTTPBasicAuth


def _new_element_id():
    """
    Az Elementor minden egyes "elemhez" (szekció, oszlop, widget)
    egy rövid, egyedi azonosítót vár el (a saját szerkesztőjében ezt
    automatikusan generálja). Ha ide ütköző/duplikált ID-kat írnánk,
    az Elementor szerkesztőben később furcsa, nehezen debuggolható
    hibákhoz vezethetne (pl. két elem "összeragad").

    Egy uuid4-ből vágunk le 7 karaktert hexadecimális formában —
    ez gyakorlatilag sosem fog ütközni, és pont annyi karakter,
    amennyit az Elementor a saját generált ID-jaihoz szokott
    használni.
    """

    return uuid.uuid4().hex[:7]


def build_elementor_data(html_content):
    """
    Felépíti az Elementor "_elementor_data" meta mezőjének
    TARTALMÁT (egy Python listát/dict-eket, amit a hívó fog
    JSON-stringgé alakítani, lásd create_post()).

    A struktúra (lásd a specifikáció 9. pontját is):

        Section
        └── Column
            └── HTML widget (widgetType: "html")
                └── settings.html = html_content

    Ez a JELENLEGI, SZÁNDÉKOSAN EGYSZERŰ megoldás — NINCS benne
    külön szekció/oszlop a sorozat-navigációs linkeknek (az egy
    KÉSŐBBI lépésben, a "sorozat navigáció" fázisban kerül bele,
    ugyanebbe a HTML-be, CSS-alapú elrendezéssel, NEM külön
    Elementor-elemként).

    FIGYELEM, HA VALAHA HIBÁT KELL KERESNI ITT: az Elementor a saját
    JSON-sémáját NEM dokumentálja hivatalosan, ez a struktúra
    "reverse engineering" (egy ténylegesen Elementorban létrehozott
    poszt _elementor_data mezőjének megfigyeléséből) alapján készült.
    Ha egy Elementor-frissítés után a posztok furcsán jelennének meg,
    érdemes összehasonlítani egy KÉZZEL, a legújabb Elementor
    verzióval létrehozott poszt _elementor_data tartalmával (ezt pl.
    egy adatbázis-lekérdezéssel vagy a WP admin "Egyéni mezők"
    nézetével lehet megnézni).
    """

    widget = {
        "id": _new_element_id(),
        "elType": "widget",
        "widgetType": "html",
        "settings": {
            "html": html_content
        },
        "elements": []
    }

    column = {
        "id": _new_element_id(),
        "elType": "column",
        # a "_column_size": 100 azt jelenti, hogy ez az EGYETLEN
        # oszlop a szekcióban a teljes szélességet foglalja el
        "settings": {
            "_column_size": 100
        },
        "elements": [widget]
    }

    section = {
        "id": _new_element_id(),
        "elType": "section",
        "settings": {},
        "elements": [column],
        "isInner": False
    }

    # az Elementor egy TÖMBÖT vár a legfelső szinten (elméletileg
    # egy poszt több szekcióból is állhatna, itt most csak egy van)
    return [section]


class WordPressClient:
    """
    Egyetlen WordPress oldalhoz tartozó kapcsolatot és a hozzá
    tartozó, session-szintű cache-eket (pl. kategória ID-k) fogja
    össze. Egy futás (egy GUI-munkamenet) alatt érdemes EGYETLEN
    WordPressClient példányt létrehozni és azt újrahasználni, hogy a
    kategória-cache tényleg segítsen (ne kérdezzünk le mindig
    mindent újra a WordPress-től).
    """

    def __init__(self, secrets):
        """
        secrets: a config.load_secrets() kimenete (dict), a
        WP_URL / WP_USER / WP_APP_PASSWORD / WP_ELEMENTOR_VERSION
        kulcsokkal.
        """

        # a /wp-json/wp/v2 utótagot itt fűzzük hozzá EGYSZER, hogy a
        # többi függvényben már ne kelljen ezt mindig megismételni
        self.base_url = f"{secrets['WP_URL']}/wp-json/wp/v2"

        # a mi SAJÁT, mu-plugin által regisztrált REST végpontjaink
        # (nyelv beállítása, fordítások összekapcsolása) — lásd a
        # modul elején és a set_post_language()/link_translations()
        # magyarázatát
        self.custom_api_base = f"{secrets['WP_URL']}/wp-json/sonjablog/v1"

        # HTTP Basic Auth az Application Password-del — a WordPress
        # ezt automatikusan felismeri Application Password-ként,
        # NEM a felhasználó "sima" bejelentkezési jelszavaként
        self.auth = HTTPBasicAuth(
            secrets["WP_USER"],
            secrets["WP_APP_PASSWORD"]
        )

        self.elementor_version = secrets["WP_ELEMENTOR_VERSION"]

        # (nyelv, kategórianév kisbetűsítve) -> kategória ID cache,
        # hogy egy futás alatt ne kérdezzük le ugyanazt többször.
        # FONTOS: a cache-kulcsban a NYELV is szerepel — a Polylang-
        # ban ugyanaz a kategórianév-szöveg (elméletileg) más-más
        # kategória-objektumot jelenthet nyelvenként, lásd
        # get_category_id() magyarázatát.
        self._category_cache = {}

    def get_category_id(self, name, lang):
        """
        Lekérdezi egy kategórianév WordPress-beli ID-ját, EGY ADOTT
        NYELVEN. Ha már korábban lekérdeztük (ugyanerre a nyelvre,
        ugyanebben a futásban), a cache-ből adja vissza, hálózati
        hívás nélkül.

        Visszaadja a kategória ID-ját (int), vagy None-t, ha nincs
        ilyen nevű kategória az adott nyelven a WordPress oldalon.

        MIÉRT A SAJÁT "category-id" VÉGPONTUNKAT HÍVJUK, NEM A
        SZABVÁNYOS /wp/v2/categories-t (2026.07.27-i javítás,
        MÁSODIK kör)? Az ELSŐ próbálkozásunk (a szabványos végpont
        + "lang" query-paraméter, illetve a Polylang belső
        "curlang" állapotának kézi átállítása) a gyakorlatban NEM
        bizonyult megbízhatónak — feltehetően Polylang-verziófüggő,
        nem hivatalos belső API-ra próbált támaszkodni. Ehelyett a
        mu-plugin (wordpress_functions_php_kiegeszites.php) egy
        SAJÁT REST végpontot ad, ami PHP-szinten, közvetlenül a
        Polylang hivatalosan dokumentált, Free verzióban is stabil
        get_terms(['lang' => ...]) lekérdezését használja — ez
        megbízhatóbb, mert nem REST-rétegbeli, Pro-only
        viselkedésre épül.
        """

        key = (lang, name.strip().lower())

        if key in self._category_cache:
            return self._category_cache[key]

        response = requests.get(
            f"{self.custom_api_base}/category-id",
            params={
                "name": name,
                "lang": lang
            },
            auth=self.auth
        )

        if response.status_code == 404:
            # a mu-plugin ezt adja vissza, ha nincs ilyen nevű
            # kategória az adott nyelven — ez NEM hiba, csak azt
            # jelenti, hogy nincs találat
            return None

        response.raise_for_status()

        category_id = response.json()["id"]

        # eltároljuk a cache-ben, hogy legközelebb ne kelljen
        # újra lekérdezni
        self._category_cache[key] = category_id

        return category_id

    def category_exists(self, name, lang):
        """
        Ez a függvény pontosan az a "category_exists_fn" callback,
        amit a converter/validators.py validate() függvénye elvár
        (lásd ott a részletes magyarázatot) — DE mivel a validate()
        egyetlen argumentummal (name) hívja meg ezt a callback-et,
        a "lang"-ot a HÍVÓ oldalon (ui/main_window.py) kell egy
        lambda/closure segítségével "befagyasztani" a poszt aktuális
        nyelvére, MIELŐTT átadjuk a validate()-nek — lásd ott a
        magyarázatot.
        """

        return self.get_category_id(name, lang) is not None

    def media_exists(self, media_id):
        """
        Ez pedig a "media_exists_fn" callback a validators.py
        számára — leellenőrzi, hogy a megadott ID-jú kép valóban
        létezik-e a WordPress médiatárában.

        Egy sikeres (200-as) válasz azt jelenti, létezik a kép;
        egy 404-es választ (vagy bármilyen hibát) "nem létezik"-ként
        értelmezünk.

        MEGJEGYZÉS: itt NEM kell "lang" paraméter, mert egy
        egyetlen ID alapján történő lekérdezés (nem lista/keresés)
        nem esik a Polylang nyelvi szűrése alá, és a kiemelt kép
        egyébként is ugyanaz a médiatár-elem mindhárom nyelvi
        posztnál (nem külön-külön feltöltött kép nyelvenként).
        """

        response = requests.get(
            f"{self.base_url}/media/{media_id}",
            auth=self.auth
        )

        return response.status_code == 200

    def _resolve_category_ids(self, category_names, lang):
        """
        A validáció (converter/validators.py) UTÁN hívjuk ezt — azaz
        ekkorra már biztosan tudjuk, hogy minden megadott
        kategórianév létezik EZEN a nyelven. Ha mégis hiányozna
        valamelyik (pl. közben törölte valaki a WordPress oldalon,
        a validáció és a tényleges létrehozás közötti pillanatban),
        itt egy explicit hibát dobunk, ahelyett hogy csendben
        kihagynánk a kategóriát — jobb egy egyértelmű hibaüzenet,
        mint egy posztot rossz/hiányos kategorizálással közzétenni.
        """

        category_ids = []

        for name in category_names:

            category_id = self.get_category_id(name, lang)

            if category_id is None:
                raise ValueError(
                    f"A(z) '{name}' kategória ('{lang}' nyelven) "
                    f"időközben eltűnt a WordPress oldalról — "
                    f"ellenőrizd újra a posztot létrehozás előtt."
                )

            category_ids.append(category_id)

        return category_ids

    def create_post(self, metadata, body_html):
        """
        Létrehozza (ütemezi) a posztot a WordPress oldalon.

        Bemenet:
          metadata — a converter.metadata_parser.parse_metadata()
                     kimenete (MÁR validált, lásd
                     converter/validators.py) — innen jön a cím, a
                     dátum, a kategóriák, a kiemelt kép ID, a SEO
                     mezők, stb.
          body_html — a converter.html_generator.generate_html()
                     kimenete: a törzsszöveg HTML-je, amit az
                     Elementor HTML widgetbe (és tartalék jelleggel
                     a sima "content" mezőbe is) teszünk.

        Visszaadja a WordPress API válaszát (dict), amiben többek
        közt benne van a létrehozott poszt ID-ja és szerkesztői
        linkje — ezt a GUI-nak érdemes megjelenítenie sikeres
        létrehozás után.

        Hiba esetén requests.exceptions.HTTPError-t dob (a
        raise_for_status() miatt) — a hívónak (a GUI-nak) ezt el
        kell kapnia, és a válasz szövegét (response.text)
        megjelenítenie, mert a WordPress általában pontos okot ad a
        hibára (pl. "invalid_username", "rest_cannot_create", stb.)

        FONTOS SORREND (2026.07.27-i javítás): a posztot ELŐSZÖR
        NYELV ÉS KATEGÓRIÁK NÉLKÜL hozzuk létre, utána ÁLLÍTJUK BE A
        NYELVÉT, és csak EZUTÁN, egy KÜLÖN kéréssel rendeljük hozzá a
        kategóriákat. Korábban egyetlen kérésben próbáltuk mindent
        beállítani (kategóriák + nyelv is ugyanabban a POST
        kérésben) — ez azért volt hibás, mert a poszt LÉTREHOZÁSAKOR
        még nem volt neki nyelve (a Polylang ilyenkor az
        alapértelmezett, magyar nyelvet feltételezi), és a Polylang
        emiatt CSENDBEN FIGYELMEN KÍVÜL HAGYTA az angol/spanyol
        kategóriák hozzárendelését, hiszen azok nyelve nem egyezett
        a poszt (akkor még beállítatlan/alapértelmezett) nyelvével.
        A helyes sorrend: poszt létrehozása -> nyelv beállítása ->
        kategóriák hozzárendelése.
        """

        elementor_data = build_elementor_data(body_html)

        payload = {
            "title": metadata["cim"],

            # a "content" mezőt is kitöltjük, NEM csak az
            # _elementor_data-t — ez egyfajta "tartalék", mert pl.
            # RSS feedek, keresőmotorok, vagy egy esetleges
            # Elementor nélküli nézet is ebből a mezőből dolgozik.
            # Az Elementor, amíg "builder" módban van a poszt
            # (_elementor_edit_mode = builder), a saját
            # _elementor_data-ját jeleníti meg a látogatóknak, NEM
            # ezt a mezőt — de a mezőnek akkor is érdemes
            # tartalmaznia valamit.
            "content": body_html,

            "excerpt": metadata.get("beleolvaso", ""),

            # SZÁNDÉKOSAN mindig "future" (soha nem azonnali
            # publikálás) — lásd a specifikáció 8.3 pontját. A
            # validators.py már garantálta, hogy a dátum jövőbeli.
            "status": "future",

            # a datetime objektumot ISO 8601 formátumú stringgé
            # alakítjuk, mert a WordPress REST API ezt várja a
            # "date" mezőben (pl. "2026-08-03T09:00:00")
            "date": metadata["datum_parsed"].isoformat(),

            # SZÁNDÉKOSAN NINCS "categories" kulcs itt — lásd a
            # fenti "FONTOS SORREND" magyarázatot, ezeket csak a
            # nyelv beállítása UTÁN, egy külön hívással rendeljük
            # hozzá lentebb.
            "meta": {
                # az Elementor JSON-t stringgé kell alakítani —
                # a WordPress meta mezők egyszerű string/szám
                # értékeket tárolnak, nem beágyazott objektumokat
                "_elementor_data": json.dumps(
                    elementor_data,
                    ensure_ascii=False
                ),
                "_elementor_edit_mode": "builder",
                "_elementor_template_type": "wp-post",
                "_elementor_version": self.elementor_version,

                # RankMath SEO mezők — CSAK AKKOR kerülnek ténylegesen
                # elmentésre, ha a WordPress oldalon regisztrálva
                # vannak show_in_rest=true-val (lásd a modul elején
                # lévő magyarázatot és a specifikáció 4. pontját)
                "rank_math_description": metadata.get(
                    "seo_snippet", ""
                ),
                "rank_math_focus_keyword": ", ".join(
                    metadata.get("seo_kulcsszavak", [])
                ),
                # a rank_math_primary_category-t is a kategóriákkal
                # EGYÜTT, a lentebbi PATCH hívásban állítjuk be,
                # mert az is a kategória-feloldás eredményétől függ
            }
        }

        # a kiemelt kép OPCIONÁLIS — csak akkor tesszük bele a
        # payloadba, ha a szerző valóban megadott egy ID-t (ha a
        # "featured_media" kulcsot 0-ra vagy None-ra állítanánk,
        # az egyes WordPress verziókban hibát vagy nem várt
        # viselkedést okozhat, ezért inkább teljesen kihagyjuk a
        # kulcsot, ha nincs kép)
        if metadata.get("kiemelt_kep_id"):
            payload["featured_media"] = metadata["kiemelt_kep_id"]

        response = requests.post(
            f"{self.base_url}/posts",
            json=payload,
            auth=self.auth
        )
        response.raise_for_status()

        result = response.json()
        post_id = result["id"]

        # 1. LÉPÉS a poszt létrehozása UTÁN: nyelv beállítása —
        # ennek MEG KELL előznie a kategóriák hozzárendelését
        self.set_post_language(post_id, metadata["nyelv"])

        # 2. LÉPÉS: a kategóriák feloldása MOST már a helyes
        # sorrendben történik (a poszt nyelve már be van állítva a
        # WordPress-en, amikor ez a get_category_id hívás lefut)
        category_ids = self._resolve_category_ids(
            metadata["kategoriak"],
            metadata["nyelv"]
        )

        # 3. LÉPÉS: a kategóriák (és az elsődleges kategória)
        # hozzárendelése egy KÜLÖN, frissítő (PATCH-jellegű) kéréssel
        update_response = requests.post(
            f"{self.base_url}/posts/{post_id}",
            json={
                "categories": category_ids,
                "meta": {
                    "rank_math_primary_category": str(
                        category_ids[0]
                    ),
                }
            },
            auth=self.auth
        )
        update_response.raise_for_status()

        return update_response.json()

    def set_post_language(self, post_id, lang):
        """
        Beállítja egy poszt Polylang-nyelvét — a mu-plugin egyéni
        REST végpontján keresztül (lásd a specifikáció Polylang-
        integrációról szóló részét), mert a Polylang INGYENES
        verziója ezt nem támogatja a szabványos WordPress REST
        API-n keresztül.

        A mu-plugin belül a Polylang saját, hivatalos PHP
        függvényét hívja meg (pll_set_post_language), tehát ez
        ugyanolyan megbízható, mintha a WordPress adminban
        állítanád be kézzel.

        lang: "hu", "en" vagy "es" (lásd
              metadata_parser.VALID_NYELVEK) — a validators.py már
              ellenőrizte, hogy csak ez a három érték fordulhat elő.
        """

        response = requests.post(
            f"{self.custom_api_base}/set-language",
            json={
                "post_id": post_id,
                "lang": lang
            },
            auth=self.auth
        )
        response.raise_for_status()

        return response.json()

    def link_translations(self, translations):
        """
        Összeköti a megadott posztokat egymás Polylang-
        fordításaként — szintén a mu-plugin egyéni REST
        végpontján keresztül, ami belül a Polylang
        pll_save_post_translations() függvényét hívja meg.

        translations: dict, nyelvkód -> poszt ID, pl.:
            {"hu": 11234, "en": 11267, "es": 11268}

        NEM KELL mind a három nyelvnek szerepelnie egyszerre —
        Polylang-nál egy 2 vagy akár 1 elemű "fordítás-csoport" is
        érvényes (pl. ha egyelőre csak a magyar és az angol verzió
        készült el, a spanyol még nem). A wordpress/translations.py
        modul hívja ezt meg a MINDENKORI ismert, teljes csoporttal —
        lásd ott a részletes magyarázatot.
        """

        response = requests.post(
            f"{self.custom_api_base}/link-translations",
            json={
                "translations": translations
            },
            auth=self.auth
        )
        response.raise_for_status()

        return response.json()
