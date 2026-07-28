"""
ui/main_window.py

A program grafikus felülete (PySide6). A korábbi (odt_to_html)
verzióhoz képest itt jelentősen bővült a funkcionalitás — lásd a
specifikáció 7. pontját:

  ÚJ elemek:
    - metaadat-előnézet panel (mit olvasott ki a program a
      táblázatból)
    - hibalista panel (mi akadályozza a poszt létrehozását, ha
      van ilyen)
    - "Poszt létrehozása" gomb (csak akkor aktív, ha nincs hiba
      ÉS sikerült kapcsolódni a WordPress oldalhoz)

  VÁLTOZATLAN elemek (a korábbi kódból):
    - "ODT fájl betöltése" gomb
    - bal oldali "debug" nézet (nyers blokkok listája)
    - jobb oldali HTML szerkesztő + élő előnézet
    - "HTML másolása" gomb (a kézi finomítás lehetősége megmarad —
      a "Poszt létrehozása" gomb a SZERKESZTETT HTML-t küldi el,
      nem az eredeti, automatikusan generáltat, lásd
      create_post() lentebb)
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QTextEdit,
    QFileDialog,
    QHBoxLayout,
    QApplication,
    QLabel,
    QMessageBox
)

from converter.odt_reader import read_odt_document
from converter.metadata_parser import parse_metadata
from converter.validators import validate
from converter.html_generator import generate_html
from converter.navigation import (
    load_series_config,
    build_navigation_html
)

from wordpress.config import load_secrets
from wordpress.wp_client import WordPressClient
from wordpress import translations


# Azok a metaadat-mezők, amiket az előnézet panelen megjelenítünk,
# a kulcs (metadata dict-beli név) és a kijelzett magyar címke
# párjaként. Ez CSAK a megjelenítést szabályozza — a tényleges
# validációt a converter/validators.py végzi, ettől függetlenül.
METADATA_DISPLAY_FIELDS = [
    ("nyelv", "Nyelv"),
    ("cim", "Cím"),
    ("datum", "Publikálás dátuma"),
    ("kategoriak", "Kategóriák"),
    ("beleolvaso", "Beleolvasó szövege"),
    ("seo_snippet", "SEO snippet"),
    ("seo_kulcsszavak", "SEO kulcsszavak"),
    ("kiemelt_kep_id", "Kiemelt kép ID"),
    ("sorozat_nev", "Sorozat neve"),
    ("resz_szam", "Rész sorszáma"),
    ("csoport_azonosito", "Fordítás-csoport azonosítója (számított)"),
]


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("CreateSonjaBlog")
        self.resize(1500, 850)

        # Ide tesszük el a legutóbb betöltött dokumentum adatait,
        # hogy a create_post() (amit a "Poszt létrehozása" gomb
        # hív) hozzáférjen — enélkül minden gombnyomáskor újra be
        # kellene tölteni/feldolgozni az ODT-t.
        self.current_metadata = None
        self.current_blocks = None
        self.current_errors = []

        # A WordPress-kapcsolatot MÁR AZ INDULÁSKOR megpróbáljuk
        # felépíteni (nem csak a "Poszt létrehozása" gomb
        # megnyomásakor), mert:
        #   1. a kategória/kép-létezés VALIDÁCIÓHOZ is kell
        #      (lásd load_odt lentebb — a category_exists /
        #      media_exists callback-eket adjuk át a validate()
        #      hívásnak),
        #   2. így ha hibás a secrets fájl, azt MÁR ODT betöltés
        #      előtt, induláskor jelezni tudjuk, nem csak a "Poszt
        #      létrehozása" gomb megnyomásakor derülne ki.
        self.wp_client, self.wp_init_error = self._init_wp_client()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()

        # ------------------------------------------------------
        # FELSŐ GOMBSOR
        # ------------------------------------------------------

        top_button_layout = QHBoxLayout()

        self.load_button = QPushButton(
            "ODT fájl betöltése"
        )

        self.load_button.clicked.connect(
            self.load_odt
        )

        top_button_layout.addWidget(
            self.load_button
        )

        if self.wp_client is None:

            # ha nem sikerült a WordPress-kapcsolat, ezt egy
            # állandóan látható címkével jelezzük a gombsor
            # mellett, hogy ne csak akkor derüljön ki, amikor már
            # a "Poszt létrehozása" gombra kattintanánk
            wp_status_label = QLabel(
                f"⚠ WordPress kapcsolat hiba: {self.wp_init_error}"
            )
            wp_status_label.setStyleSheet("color: darkred;")

            top_button_layout.addWidget(wp_status_label)

        main_layout.addLayout(
            top_button_layout
        )

        # ------------------------------------------------------
        # FŐ TARTALOM: bal oldal (metaadat + hibák + debug),
        # jobb oldal (HTML szerkesztő + előnézet)
        # ------------------------------------------------------

        content_layout = QHBoxLayout()

        # --- BAL OLDAL ---

        left_layout = QVBoxLayout()

        left_layout.addWidget(
            QLabel("Beolvasott metaadatok:")
        )

        self.metadata_preview = QTextEdit()
        self.metadata_preview.setReadOnly(True)
        self.metadata_preview.setMaximumHeight(220)

        left_layout.addWidget(
            self.metadata_preview
        )

        left_layout.addWidget(
            QLabel("Validációs hibák:")
        )

        self.error_list = QTextEdit()
        self.error_list.setReadOnly(True)
        self.error_list.setMaximumHeight(160)

        left_layout.addWidget(
            self.error_list
        )

        left_layout.addWidget(
            QLabel("Nyers törzsszöveg-blokkok (debug):")
        )

        self.source_edit = QTextEdit()
        self.source_edit.setReadOnly(True)

        left_layout.addWidget(
            self.source_edit
        )

        content_layout.addLayout(
            left_layout
        )

        # --- JOBB OLDAL (változatlan a korábbi kódhoz képest) ---

        right_layout = QVBoxLayout()

        self.html_edit = QTextEdit()

        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)

        right_layout.addWidget(
            self.html_edit
        )

        right_layout.addWidget(
            self.preview_edit
        )

        content_layout.addLayout(
            right_layout
        )

        main_layout.addLayout(
            content_layout
        )

        # ------------------------------------------------------
        # ALSÓ GOMBSOR
        # ------------------------------------------------------

        bottom_button_layout = QHBoxLayout()

        self.copy_button = QPushButton(
            "HTML másolása"
        )

        self.copy_button.clicked.connect(
            self.copy_html
        )

        self.create_post_button = QPushButton(
            "Poszt létrehozása"
        )

        # a gomb ALAPÉRTELMEZETTEN inaktív — csak sikeres,
        # hibamentes betöltés után aktiválódik (lásd load_odt),
        # hogy véletlenül se lehessen hiányos/hibás adatokkal
        # posztot indítani
        self.create_post_button.setEnabled(False)

        self.create_post_button.clicked.connect(
            self.create_post
        )

        bottom_button_layout.addStretch()

        bottom_button_layout.addWidget(
            self.copy_button
        )

        bottom_button_layout.addWidget(
            self.create_post_button
        )

        main_layout.addLayout(
            bottom_button_layout
        )

        central_widget.setLayout(
            main_layout
        )

        # ÉLŐ HTML ELŐNÉZET: valahányszor a szerkesztőben (jobb
        # felül) módosul a szöveg, azonnal frissül az alatta lévő
        # renderelt előnézet is
        self.html_edit.textChanged.connect(
            self.update_preview
        )

    def _init_wp_client(self):
        """
        Megpróbálja betölteni a secrets fájlt és felépíteni a
        WordPressClient-et. Ha bármi hiba történik (hiányzó fájl,
        hiányzó kulcs a secrets-ben, stb.), NEM omlik össze a teljes
        program — ehelyett (None, hibaüzenet) tuple-t ad vissza, és
        a GUI ezt egy figyelmeztető felirattal jelzi, a "Poszt
        létrehozása" gomb pedig inaktív marad, amíg ez nincs
        megoldva.
        """

        try:
            secrets = load_secrets()
            client = WordPressClient(secrets)
            return client, None

        except Exception as e:
            return None, str(e)

    def load_odt(self):
        """
        A fájlválasztó megnyitása, majd a KOMPLETT feldolgozási
        lánc lefuttatása egy betöltött dokumentumon:

          1. odt_reader.read_odt_document — táblázat + törzsszöveg
             szétválasztása
          2. metadata_parser.parse_metadata — strukturált metaadat
          3. validators.validate — hibalista (ide adjuk át a
             wp_client kategória/kép-ellenőrző függvényeit is, HA
             sikerült kapcsolódni a WordPress-hez)
          4. html_generator.generate_html — a törzsszöveg HTML-je

        A végén frissül mind a négy panel (metaadat-előnézet,
        hibalista, debug blokkok, HTML szerkesztő+előnézet), és
        eldől, hogy a "Poszt létrehozása" gomb aktiválható-e.
        """

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "ODT fájl kiválasztása",
            "",
            "ODT Files (*.odt)"
        )

        if not filepath:
            return

        metadata_rows, blocks = read_odt_document(filepath)

        table_found = len(metadata_rows) > 0

        metadata, unrecognized_labels = parse_metadata(
            metadata_rows
        )

        # eltároljuk a jelenlegi állapotot, hogy a create_post()
        # (a gomb megnyomásakor) elérje ugyanezeket az adatokat
        self.current_metadata = metadata
        self.current_blocks = blocks

        # --- METAADAT-ELŐNÉZET PANEL FRISSÍTÉSE ---

        self.metadata_preview.clear()

        for key, label in METADATA_DISPLAY_FIELDS:

            value = metadata.get(key, "")

            # a listás mezőket (kategóriák, kulcsszavak) olvashatóan
            # vesszővel elválasztva jelenítjük meg, nem Python-lista
            # formájában (pl. ne "['novella', 'karácsonyi']", hanem
            # "novella, karácsonyi" jelenjen meg)
            if isinstance(value, list):
                value = ", ".join(value)

            self.metadata_preview.append(
                f"{label}: {value if value else '(üres)'}"
            )

        if unrecognized_labels:

            self.metadata_preview.append("")
            self.metadata_preview.append(
                "⚠ Fel nem ismert táblázat-sorok (elgépelés "
                "gyanús): " + ", ".join(unrecognized_labels)
            )

        # --- VALIDÁCIÓ ---

        # a kategória- és kép-létezés ellenőrzéséhez a wp_client
        # megfelelő metódusait adjuk át callback-ként — HA sikerült
        # kapcsolódni hozzá induláskor. Ha nem (self.wp_client is
        # None), ezeket a konkrét ellenőrzéseket egyszerűen kihagyja
        # a validate() függvény (lásd converter/validators.py).
        category_exists_fn = None
        media_exists_fn = None

        if self.wp_client is not None:

            # a category_exists()-nek szüksége van a poszt
            # NYELVÉRE is (lásd wp_client.get_category_id
            # magyarázatát: a Polylang nyelvenként külön
            # kategória-objektumokat kezel, és a REST API-lekérdezést
            # explicit "lang" paraméterrel kell megcéloznunk) — a
            # validate() viszont a category_exists_fn-t EGYETLEN
            # argumentummal (a kategórianévvel) hívja meg, ezért itt,
            # egy lambdával "befagyasztjuk" a nyelvet a JELENLEG
            # betöltött dokumentum "nyelv" metaadatára
            category_exists_fn = (
                lambda name, _nyelv=metadata["nyelv"]:
                    self.wp_client.category_exists(name, _nyelv)
            )

            media_exists_fn = self.wp_client.media_exists

        # a sorozat-configot minden betöltéskor ÚJRA beolvassuk
        # (nem tesszük el __init__-ben egyszer s mindenkorra), hogy
        # ha időközben hozzáadsz egy új sorozatot a
        # config/sorozatok.json fájlhoz, a programot ne kelljen
        # emiatt újraindítani
        series_config = load_series_config()

        errors = validate(
            metadata,
            unrecognized_labels,
            blocks,
            table_found,
            category_exists_fn=category_exists_fn,
            media_exists_fn=media_exists_fn,
            series_config=series_config
        )

        # ha a WordPress-kapcsolat maga hibás, azt is hozzávesszük
        # a hibalistához — enélkül a felhasználó azt hihetné, hogy
        # minden rendben van, miközben csak a kategória/kép
        # ellenőrzés maradt ki hálózati hiba miatt
        if self.wp_client is None:
            errors = [
                f"WordPress kapcsolat nem elérhető, a kategória- "
                f"és kép-ellenőrzés kimaradt ({self.wp_init_error})."
            ] + errors

        self.current_errors = errors

        self._render_errors(errors)

        # a "Poszt létrehozása" gomb CSAK akkor aktív, ha nincs
        # egyetlen hiba SEM, és van érvényes WordPress-kapcsolat
        self.create_post_button.setEnabled(
            len(errors) == 0 and self.wp_client is not None
        )

        # --- DEBUG NÉZET (nyers blokkok) ---

        self.source_edit.clear()

        for b in blocks:

            self.source_edit.append(
                f"[{b['type']}] {b['text']}"
            )

        # --- HTML GENERÁLÁS + NAVIGÁCIÓ HOZZÁFŰZÉSE + ELŐNÉZET ---

        html = generate_html(blocks)

        # ha a bejegyzés egy sorozat része, a navigációs blokkot
        # (sorozat eleje gomb + láthatatlan jelölő, lásd
        # converter/navigation.py) a törzsszöveg ALÁ fűzzük.
        #
        # A build_navigation_html ELMÉLETBEN hibát (ValueError)
        # dobhat, ha a sorozat nincs benne a config/sorozatok.json
        # fájlban — ezt a validators.py MÁR külön jelezte a
        # hibalistában (lásd fent), úgyhogy itt nem akarunk emiatt
        # ÖSSZEOMLANI, csak egyszerűen kihagyjuk a navigációs
        # blokkot, amíg a szerző nem javítja a hibát és tölti be
        # újra a fájlt
        navigation_html = ""

        try:
            navigation_html = build_navigation_html(
                metadata,
                series_config
            )
        except ValueError:
            # a konkrét hibaüzenet már ott van a hibalistában
            # (validators._validate_sorozat), itt nincs mit
            # tovább tenni
            pass

        if navigation_html:
            html = html + "\n\n" + navigation_html

        self.html_edit.setPlainText(html)

        self.preview_edit.setHtml(html)

    def _render_errors(self, errors):
        """
        A hibalista panel frissítése. Ha nincs hiba, egy zöld,
        megnyugtató üzenetet mutatunk; ha van, piros színnel,
        soronként felsoroljuk őket — mindegyik előtt egy "✗"
        jellel, hogy vizuálisan is egyértelműen elkülönüljenek.
        """

        self.error_list.clear()

        if not errors:

            self.error_list.setStyleSheet("color: darkgreen;")
            self.error_list.setPlainText(
                "Nincs hiba — a poszt létrehozható."
            )
            return

        self.error_list.setStyleSheet("color: darkred;")

        for error in errors:
            self.error_list.append(f"✗ {error}")

    def update_preview(self):
        """
        Valahányszor a HTML szerkesztő tartalma módosul (akár a
        program generálta, akár a felhasználó kézzel javította),
        az alatta lévő élő előnézet ezt azonnal megjeleníti.
        """

        html = self.html_edit.toPlainText()

        self.preview_edit.setHtml(html)

    def copy_html(self):
        """A HTML szerkesztő TELJES tartalmát a vágólapra másolja."""

        clipboard = QApplication.clipboard()

        clipboard.setText(
            self.html_edit.toPlainText()
        )

    def create_post(self):
        """
        A "Poszt létrehozása" gomb eseménykezelője.

        FONTOS: a HTML szerkesztő JELENLEGI (esetleg a felhasználó
        által kézzel módosított) tartalmát küldjük el, NEM az
        eredeti, automatikusan generált verziót — ez biztosítja,
        hogy ha valaki elküldés előtt még finomított valamin a
        szövegen, az a változtatás ténylegesen bekerüljön a
        posztba.

        Ez a gomb csak akkor aktív (lásd load_odt), ha korábban
        nem volt validációs hiba ÉS van érvényes WordPress-
        kapcsolat — de a hálózati hívás közben ELVILEG még mindig
        történhet hiba (pl. időközbeni kapcsolati probléma, vagy ha
        valaki a validáció és a kattintás között törölt egy
        kategóriát a WordPress oldalon) — ezt a try/except kapja el,
        és egy hibaüzenet-ablakban jelzi, ahelyett hogy a program
        összeomlana.
        """

        if self.current_metadata is None:
            return

        body_html = self.html_edit.toPlainText()

        try:
            result = self.wp_client.create_post(
                self.current_metadata,
                body_html
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Hiba a poszt létrehozásakor",
                f"Nem sikerült létrehozni a posztot:\n\n{e}"
            )
            return

        link = result.get("link", "(nincs link a válaszban)")
        publish_date = self.current_metadata.get("datum", "")
        post_id = result.get("id")

        # --- POLYLANG: nyelv beállítása + fordítások összekötése ---
        #
        # ITT MÁR A POSZT LÉTREJÖTT — ha ez a rész hibázik (pl. mert
        # a mu-plugin még nincs telepítve a WordPress oldalon), NEM
        # veszítjük el a posztot, csak a nyelv/összekapcsolás marad
        # el. Emiatt ezt KÜLÖN try/except blokkban kezeljük, saját,
        # a helyzetet pontosan leíró hibaüzenettel — nem ugyanazzal
        # az általános "Hiba a poszt létrehozásakor" üzenettel, mert
        # ez egy MÁSODIK, a poszt létrejötte UTÁNI lépés hibája.
        forditasi_allapot = None
        forditasi_hiba = None

        try:
            forditasi_allapot = translations.register_post_and_link(
                self.wp_client,
                self.current_metadata["csoport_azonosito"],
                self.current_metadata["nyelv"],
                post_id
            )

        except Exception as e:
            forditasi_hiba = str(e)

        uzenet = (
            f"A poszt sikeresen létrejött, ütemezve erre az "
            f"időpontra: {publish_date}\n\nSzerkesztői link:\n{link}"
        )

        if forditasi_hiba is not None:

            uzenet += (
                f"\n\n⚠ A poszt létrejött, DE a nyelv beállítása "
                f"vagy a fordítások összekapcsolása nem sikerült:\n"
                f"{forditasi_hiba}\n\nEzt kézzel kell pótolnod a "
                f"WordPress adminban (Languages panel a poszt "
                f"szerkesztőjében)."
            )

        elif forditasi_allapot is not None:

            ismert_nyelvek = ", ".join(sorted(forditasi_allapot.keys()))

            uzenet += (
                f"\n\nEbből a történetből eddig elkészült nyelvek: "
                f"{ismert_nyelvek}."
            )

        QMessageBox.information(
            self,
            "Poszt létrehozva",
            uzenet
        )
