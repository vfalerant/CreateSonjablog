"""
wordpress/config.py

Ez a modul olvassa be a WordPress bejelentkezési adatokat és egyéb
beállításokat egy egyszerű, saját "secrets" fájlból — SZÁNDÉKOSAN
NEM a python-dotenv csomagot használjuk (nem is szerepel a
requirements.txt-ben), mert:
  - a te .env/secrets elrendezésed nem a python-dotenv által
    alapból elvárt fájlnevet/helyet használja,
  - ez egy ilyen egyszerű "KULCS=érték" formátum saját kézzel is
    percek alatt megírható és könnyen átlátható, nem kell hozzá
    külső függőség.

A SECRETS FÁJL ELVÁRT FORMÁTUMA (.env/secrets, a projekt
gyökerében, tehát ugyanabban a mappában, ahol a main.py is van):

    WP_URL=https://sonjablog.com
    WP_USER=a_te_wp_felhasznalonev
    WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
    WP_ELEMENTOR_VERSION=3.28.0

Magyarázat soronként:
  WP_URL               — a WordPress oldal címe, VÉGZŐDŐ PER JEL
                          NÉLKÜL (tehát "https://sonjablog.com", NEM
                          "https://sonjablog.com/")
  WP_USER               — az a WordPress felhasználónév, akihez az
                          Application Password tartozik
  WP_APP_PASSWORD       — a WP admin → Felhasználók → Profil →
                          Application Passwords alatt generált
                          jelszó, PONTOSAN úgy (a szóközökkel
                          együtt), ahogy a WordPress megadta
  WP_ELEMENTOR_VERSION  — az Elementor plugin verziószáma
                          (WP admin → Bővítmények oldalon látható),
                          mert ezt bele kell írnunk minden generált
                          poszt _elementor_version meta mezőjébe.
                          HA FRISSÍTED AZ ELEMENTORT, EZT AZ ÉRTÉKET
                          IS FRISSÍTSD A SECRETS FÁJLBAN.

2026.09.01-i bővítés — OPCIONÁLIS kulcsok (NINCSENEK a
REQUIRED_KEYS-ben, tehát a hiányuk nem hiba):

    CTA_SHORTCODE_ID_HU=11589
    CTA_SHORTCODE_ID_EN=11612
    CTA_SHORTCODE_ID_ES=...

  Ezek a szerzői CTA-doboz Elementor Saját sablonjainak ID-ja,
  nyelvenként — a Dynific Addons for Elementor (AnyWhere Elementor)
  plugin "[INSERT_ELEMENTOR id=xxx]" rövidkódjához használja őket a
  wordpress/wp_client.py (lásd ott build_elementor_data és
  WordPressClient._build_cta_shortcode). Ha egy nyelv hiányzik
  innen, az adott nyelvű posztokba egyszerűen nem kerül bele a
  CTA-doboz widget, minden más változatlanul működik.

- Az üres sorokat és a "#"-tal kezdődő sorokat (megjegyzés) a
  betöltő figyelmen kívül hagyja, hogy a fájlba lehessen írni
  saját emlékeztetőt is.
- A sorrend nem számít, csak a "KULCS=érték" formátum.
"""

import os

from paths import get_project_root


# A secrets fájl elvárt helye — a projekt gyökeréhez (lásd
# paths.get_project_root()) képest, NEM a jelenlegi
# munkakönyvtárhoz képest. Ez biztosítja, hogy akár szkriptként,
# akár becsomagolt .exe-ként fut a program, mindig ugyanott keresse
# a fájlt. Ha a fájl máshol van, ezt az egy sort kell módosítani —
# vagy a load_secrets() hívásakor át lehet adni egy másik
# útvonalat is.
DEFAULT_SECRETS_PATH = os.path.join(
    get_project_root(),
    ".env",
    "secrets"
)

# Ezeknek a kulcsoknak KÖTELEZŐEN szerepelniük kell a secrets
# fájlban — ha valamelyik hiányzik, a load_secrets() hibát dob,
# hogy MINÉL HAMARABB, már induláskor kiderüljön a hiányos
# konfiguráció (ne csak akkor, amikor már a WordPress API hívna
# éppen elszállna emiatt egy poszt-létrehozás közepén).
REQUIRED_KEYS = [
    "WP_URL",
    "WP_USER",
    "WP_APP_PASSWORD",
    "WP_ELEMENTOR_VERSION",
]


def load_secrets(path=None):
    """
    Beolvassa és feldolgozza a secrets fájlt, dict-et ad vissza,
    pl.:
        {
            "WP_URL": "https://sonjablog.com",
            "WP_USER": "...",
            "WP_APP_PASSWORD": "...",
            "WP_ELEMENTOR_VERSION": "3.28.0",
        }

    Ha a path paramétert nem adjuk meg, a DEFAULT_SECRETS_PATH-ot
    használja (".env/secrets", a jelenlegi munkakönyvtárhoz
    képest — FONTOS: ez azt jelenti, hogy a programot a projekt
    GYÖKERÉBŐL kell futtatni, pl. "python main.py" a
    CreateSonjaBlog mappában állva, különben nem találja meg a
    ".env/secrets" fájlt).

    Hibát dob (FileNotFoundError vagy ValueError), ha a fájl nem
    létezik, vagy hiányzik belőle valamelyik kötelező kulcs — ezt a
    GUI-nak (main.py/ui) érdemes elkapnia és emberi hibaüzenetként
    megjelenítenie induláskor.
    """

    if path is None:
        path = DEFAULT_SECRETS_PATH

    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Nem található a secrets fájl itt: '{path}'. "
            f"Hozz létre egy '.env/secrets' fájlt a projekt "
            f"gyökerében, lásd a config.py fájl elején lévő "
            f"leírást a pontos formátumról."
        )

    secrets = {}

    with open(path, "r", encoding="utf-8") as f:

        for line_number, raw_line in enumerate(f, start=1):

            line = raw_line.strip()

            # üres sor vagy megjegyzés -> kihagyjuk
            if not line or line.startswith("#"):
                continue

            if "=" not in line:
                raise ValueError(
                    f"Hibás sor a secrets fájlban "
                    f"({path}:{line_number}): '{raw_line.rstrip()}' "
                    f"— a várt formátum KULCS=érték."
                )

            # a split("=", 1) azért fontos (nem sima split("=")),
            # mert pl. az Application Password vagy egy URL-ben
            # elméletileg szerepelhet "=" karakter is az értékben —
            # csak az ELSŐ "=" jelnél vágjuk ketté a sort
            key, value = line.split("=", 1)

            secrets[key.strip()] = value.strip()

    # ellenőrizzük, hogy minden kötelező kulcs megvan-e
    missing_keys = [
        key
        for key in REQUIRED_KEYS
        if key not in secrets or not secrets[key]
    ]

    if missing_keys:
        raise ValueError(
            f"Hiányzó vagy üres kulcs(ok) a secrets fájlban "
            f"({path}): {', '.join(missing_keys)}."
        )

    # a WP_URL-ről levágjuk a záró "/" jelet, ha véletlenül ott
    # maradt volna — így a wp_client.py mindig biztonságosan
    # tud hozzáfűzni egy "/wp-json/wp/v2/..." útvonalat, dupla
    # perjel nélkül
    secrets["WP_URL"] = secrets["WP_URL"].rstrip("/")

    return secrets
