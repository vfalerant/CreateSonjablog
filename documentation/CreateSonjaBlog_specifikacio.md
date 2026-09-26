# CreateSonjaBlog — Specifikáció (v1)

## 1. Cél

Egyetlen LibreOffice (.odt) dokumentumból, ami tartalmazza a bejegyzés
metaadatait és a törzsszövegét, automatikusan létrehozni (vagy ütemezni)
egy bejegyzést a sonjablog.com WordPress oldalon, a WordPress REST API-n
keresztül — Elementor-szerkesztés és kézi copy-paste nélkül.

A projekt a meglévő `odt_to_html` kódra épül (ODT-beolvasás és
HTML-generálás), de önálló, új projektként (`CreateSonjaBlog`) készül,
mert a feldolgozási logika és a GUI is jelentősen bővül.

---

## 2. Bemeneti dokumentum formátuma

Egyetlen `.odt` fájl, amit a feleséged a megszokott módon ír LibreOffice
Writerben. A dokumentum két részből áll:

### 2.1 Metaadat-táblázat (a dokumentum tetején)

Egy 2 oszlopos táblázat, fix bal oszloppal (mező neve) és kitöltendő
jobb oszloppal (érték). A program a **dokumentum első táblázatát**
tekinti metaadatnak — minden, ami utána következik, a bejegyzés
törzsszövege.

| Mező | Érték (példa) |
|---|---|
| Történet azonosító | *(opcionális — lásd lentebb)* |
| Nyelv | hu |
| Cím | A szalon – 7. rész |
| Publikálás dátuma | 2026.08.03 09:00 |
| Kategóriák | novella, karácsonyi |
| Beleolvasó szövege | Egy kis faluban, ahol a hó sosem olvad el... |
| SEO snippet | Novella a hegyi csendről és az emberi kapcsolatokról. |
| SEO kulcsszavak | novella, hegyi csend, karácsony |
| Kiemelt kép ID | 482 |
| Sorozat neve | A szalon *(opcionális, csak sorozat esetén)* |
| Rész sorszáma | 7 *(opcionális, csak sorozat esetén)* |

Több kategória/kulcsszó esetén vesszővel elválasztva. A "Kiemelt kép
ID" a WordPress médiatárban már feltöltött kép azonosítója (lásd 8.5).
A "Sorozat neve" és "Rész sorszáma" mezők csak akkor kerülnek
kitöltésre, ha a bejegyzés egy sorozat része (lásd 9. pont). A "Cím"
mező a WordPress **posztcíme** (nem a történet saját alcíme — azt a
törzsszöveg első bekezdése adja, lásd 2.2 pont).

**"Nyelv"** (KÖTELEZŐ): `hu`, `en` vagy `es` — a blog Polylang által
kezelt három nyelve (lásd a 10. pontot).

**"Történet azonosító"** (opcionális): csak akkor KÖTELEZŐ kitölteni,
ha a bejegyzés NEM sorozat része. Sorozat-résznél a program a
"Sorozat neve" + "Rész sorszáma" párosból automatikusan előállítja —
ILYENKOR ÜRESEN HAGYHATÓ. Ez az azonosító köti össze ugyanannak a
történetnek a magyar/angol/spanyol nyelvű posztjait — FONTOS, hogy a
"Sorozat neve" mezőt MINDHÁROM nyelvi táblázatban UGYANAZZAL a
(magyar) névvel add meg, különben a program nem fogja tudni
összekötni a nyelvi verziókat.

### 2.2 Törzsszöveg (a táblázat után)

A táblázat utáni teljes tartalom a bejegyzés szövege. Ezt a meglévő
`odt_reader.py` + `html_generator.py` logika dolgozza fel.

**A törzsszöveg ELSŐ bekezdése mindig `<h2>` címsorrá alakul** — ez
a történet saját, hangulatos, az adott részre jellemző
alcíme/címe (pl. "A hegyek csendje"), és **NEM ugyanaz**, mint a
metaadat-táblázat "Cím" mezője. A "Cím" mező a WordPress **posztcíme**
lesz (ez jelenik meg a téma saját `<h1>`-jeként, és ebből generálódik
az URL is) — ezt a feleséged jellemzően a sorozat/rész-számozás
szerint tölti ki (pl. "A szalon – 7. rész"). A törzsszöveg első
bekezdése (a `<h2>`) ettől függetlenül, a szöveg tartalmán belül
jelenik meg, közvetlenül a posztcím alatt:

```
<h1> A szalon – 7. rész        <- WordPress posztcím (metaadat "Cím" mező)
<h2> A hegyek csendje          <- a törzsszöveg első bekezdése (automatikusan h2-vé alakítva)
(a történet szövege...)
```

*(Korábban, a fejlesztés közben egy pillanatra eltávolítottuk ezt a
logikát, mert azt hittük, feleslegessé vált a metaadat-táblázat
bevezetésével — kiderült azonban, hogy továbbra is szükség van rá,
csak más okból: nem a poszt egyetlen címeként, hanem egy, a
posztcím ALATT megjelenő, a történetre jellemző alcímként.)*

**HIBAKERESÉS — üres, de félkövér-jelölt bekezdés az elején (2026.08.23,
"Emily_24_20260824_ENG.odt"):** a magyar ODT-ből helyesen generálódott
a `<h2>`, de az angol fordításból üres `<h2></h2>` jött ki, a valódi
cím pedig egy sima, félkövér `<p>`-ként jelent meg. Az ok: a törzsszöveg
ELSŐ bekezdése a LibreOffice-ban technikailag NEM volt üres — egy
`<text:span text:style-name="Strong_20_Emphasis" />` (egy tartalom
nélküli, de félkövérre állított formázási jelölő) volt benne,
feltehetően azért, mert a szerző bekapcsolta a félkövér stílust,
mielőtt beírta volna a címet, de az adott sorba végül nem gépelt be
semmit. Az `odt_reader.py` a span szövegét ELŐBB csomagolta
`<strong>`/`<i>` tagbe (lásd `process_inline`), és csak UTÁNA
ellenőrizte, hogy a bekezdés "üres-e" — így egy tartalmilag üres span
"<strong></strong>"-vé vált, ami mint STRING már nem üres, tehát sem
az "üres sor" jelölőt előállító logika, sem a felesleges
(stílus nélküli) bekezdéseket kiszűrő `is_layout_artifact` nem kapta
el. A JAVÍTÁS: a `process_inline` most már csak akkor csomagolja egy
span szövegét formázó tagbe, ha a span-nek TÉNYLEGESEN van szövege
(lásd a kódban lévő magyarázatot) — így egy ilyen, tartalom nélküli
formázási jelölő újra helyesen üres bekezdésként viselkedik, és a
dokumentum elejéről/végéről levágó logika (lásd `odt_reader.read_odt_document`)
megfelelően eltünteti.

---

## 3. Projektstruktúra

```
CreateSonjaBlog/
├── main.py                      # GUI indítása
├── converter/
│   ├── odt_reader.py            # táblázat-felismerés metaadatokhoz
│   ├── html_generator.py        # az első bekezdés automatikusan <h2> alcím lesz
│   ├── metadata_parser.py       # metaadat-táblázat → strukturált dict
│   ├── validators.py            # az összes validációs szabály
│   └── navigation.py            # sorozat-navigáció (gombok, jelölő), nyelvenként
├── wordpress/
│   ├── wp_client.py             # REST API hívások (poszt létrehozás, kategória, nyelv, stb.)
│   ├── config.py                # .env/secrets beolvasása
│   └── translations.py          # fordítás-csoportok állapotának kezelése
├── ui/
│   └── main_window.py           # metaadat-előnézet, hibalista, "Poszt létrehozása" gomb
├── config/
│   └── sorozatok.json           # sorozatonkénti, nyelvenkénti navigációs adatok (KÉZZEL karbantartott)
├── state/
│   └── forditasi_csoportok.json # a program automatikusan írja/olvassa, NEM kézi szerkesztésre
├── .env/
│   └── secrets                  # WordPress bejelentkezési adatok (KÉZZEL karbantartott, TITKOS)
├── wordpress_functions_php_kiegeszites.php  # a WordPress oldalra másolandó mu-plugin
└── requirements.txt             # odfpy és defusedxml törölve, requests hozzáadva
```

---

## 4. WordPress oldali előfeltételek (egyszeri beállítás)

1. **Application Password létrehozása**: WP admin → Felhasználók →
   Profil → Application Passwords → generálás. Ezt a jelszót a
   `config.py`-ban (vagy egy külön, nem verziókezelt `.env`/`secrets`
   fájlban) tároljuk, **nem** kerül fel GitHub-ra.

2. **RankMath meta mezők + Polylang REST-integráció**: lásd a
   `wordpress_functions_php_kiegeszites.php` fájlt — ezt kell
   elhelyezni `wp-content/mu-plugins/createsonjablog.php` néven
   (vagy beilleszteni a téma `functions.php`-jába). Ez a fájl EGYBEN
   tartalmazza a RankMath mezők REST-re nyitását (`rank_math_title`,
   `rank_math_description`, `rank_math_focus_keyword`,
   `rank_math_primary_category`) ÉS a Polylang integrációhoz
   szükséges HÁROM egyéni REST végpontot (`set-language`,
   `link-translations`, `category-id` — lásd 10. pont).

   **Fontos tudnivaló a RankMath "SEO pontszámról" (pl. 63/100):**
   ez a szám KIZÁRÓLAG a RankMath böngészőben futó JavaScript-
   elemzőjének terméke — csak akkor számolódik ki, ha a posztot
   ténylegesen MEGNYITJÁTOK a WordPress szerkesztőben (Elementor
   vagy Gutenberg). Az API-val létrehozott posztoknál ez "N/A"
   lesz, amíg meg nem nyitjátok egyszer szerkesztőben. EZ NEM HIBA
   és NEM BEFOLYÁSOLJA a tényleges, élesben látható SEO-adatokat
   (a `<title>` tag, meta description, séma-jelölés) — azok már a
   poszt létrehozásakor helyesen beállításra kerülnek a fenti meta
   mezőkön keresztül. A pontszám csupán egy opcionális, írási
   segédeszköz — a program SZÁNDÉKOSAN nem próbálja ezt
   automatizálni (a RankMath elemzési logikája nem dokumentált és
   gyakran változik, ezért ennek Python-beli újraépítése törékeny
   és felesleges lenne).

3. **Kategóriák előre léteznek** a WordPress oldalon — a program nem
   hoz létre új kategóriát, csak a meglévők ID-ját kérdezi le névből.

4. **(Opcionális) Dynific Addons for Elementor plugin a szerzői
   CTA-dobozhoz** (2026.09.01-i bővítés — lásd a 9. pont végén): ha
   szeretnétek, hogy minden poszt alá automatikusan bekerüljön egy
   Elementor Saját sablonként elmentett CTA-doboz, telepítsétek a
   "Dynific Addons for Elementor" (korábbi nevén "AnyWhere
   Elementor") pluginot, mentsétek el a CTA-dobozt Elementor Saját
   sablonként, és a sablon ID-ját írjátok be a `.env/secrets` fájlba
   (`CTA_SHORTCODE_ID_HU`/`_EN`/`_ES`, nyelvenként külön-külön). Ha
   ezt a plugint nem telepítitek, vagy egy nyelvhez nem adtok meg
   ID-t, a program egyszerűen nem tesz CTA-dobozt az adott nyelvű
   posztokba — ez NEM hiba, minden más változatlanul működik.

---

## 5. Feldolgozási folyamat (lépésről lépésre)

1. Felhasználó (a férj) betölti az `.odt` fájlt a GUI-ban.
2. `odt_reader.py` beolvassa a dokumentumot, elkülöníti az első
   táblázatot (metaadatok) a maradék tartalomtól.
3. `metadata_parser.py` a táblázat celláiból dict-et épít
   (`cim`, `datum`, `kategoriak`, `beleolvaso`, `seo_snippet`,
   `seo_kulcsszavak`, `nyelv`, `csoport_azonosito`, stb.).
4. Validáció fut le (lásd 6. pont) — ha hiba van, a GUI megjeleníti,
   és a "Poszt létrehozása" gomb nem aktív.
5. Ha minden rendben: `html_generator.py` legenerálja a törzsszöveg
   HTML-jét (a törzsszöveg első bekezdése automatikusan `<h2>`
   alcím lesz, lásd 2.2 pont); ha a bejegyzés sorozat része,
   `navigation.py` a törzsszöveg alá fűzi a navigációs HTML-t is.
6. A GUI megjeleníti az előnézetet: metaadatok szövegesen + a
   generált HTML renderelt előnézete — mielőtt bármi elküldésre
   kerülne a WordPress-nek.
7. Felhasználó rákattint a "Poszt létrehozása" gombra.
8. `wp_client.py` (a specifikáció 10. pontjában részletezett,
   KRITIKUS sorrendben, lásd ott miért):
   - létrehozza a posztot (cím, tartalom, excerpt, dátum, SEO
     mezők, `status: "future"`) — MÉG nyelv és kategóriák nélkül,
   - beállítja a poszt nyelvét (mu-plugin `set-language` végpont),
   - lekérdezi (és cache-eli) a megadott kategórianevek ID-jait, a
     poszt nyelvén (mu-plugin `category-id` végpont),
   - egy frissítő kéréssel hozzárendeli a kategóriákat és az
     elsődleges kategóriát.
9. `wordpress/translations.py` rögzíti a poszt nyelvét/ID-ját a
   helyi `state/forditasi_csoportok.json` fájlban, és ha ehhez a
   történethez már 2+ nyelvi verzió ismert, összekapcsolja őket
   Polylang-fordításként (mu-plugin `link-translations` végpont).
10. A GUI visszajelzi az eredményt: siker esetén a poszt szerkesztői
    linkjét és az eddig elkészült nyelveket, hiba esetén a
    hibaüzenetet (pl. "nincs ilyen kategória: ...").

---

## 6. Validáció (feldolgozás előtti ellenőrzések)

A "Poszt létrehozása" gomb csak akkor aktív, ha az alábbiak mind
teljesülnek:

- van metaadat-táblázat a dokumentumban,
- a **Cím** mező nem üres,
- a **Publikálás dátuma** mező érvényes dátum/idő formátumban van,
- a **Kategóriák** mező nem üres, és minden felsorolt kategórianév
  (előzetes, cache-elt lekérdezés alapján) létezik a WordPress
  oldalon,
- a törzsszöveg (táblázat utáni rész) nem üres.

Minden hiba egy jól olvasható lista formájában jelenik meg a GUI-ban,
konkrétan megnevezve, melyik mezővel/résszel van gond.

---

## 7. GUI (bővített felület)

A meglévő `main_window.py` felépítésére építve:

- **"ODT fájl betöltése"** gomb — változatlan.
- **Metaadat-előnézet panel** (ÚJ) — a beolvasott metaadatokat
  szövegesen listázza (Cím, Dátum, Kategóriák, stb.), hogy
  ellenőrizhető legyen betöltés után rögtön.
- **Hibalista panel** (ÚJ) — validációs hibák, ha vannak; ez esetben
  a "Poszt létrehozása" gomb inaktív.
- **HTML szerkesztő + élő előnézet** — változatlan (megmarad a
  kézi finomítás lehetősége közvetlenül elküldés előtt).
- **"Poszt létrehozása" gomb** (ÚJ, a meglévő "HTML másolása" gomb
  mellett) — csak validáció után aktív; kattintásra elindítja az 5.
  pontban leírt WordPress API hívást.
- Sikeres létrehozás után egy rövid visszajelzés (pl. "Poszt
  létrehozva, ütemezve: 2026.08.03 09:00" + link a szerkesztőhöz).

---

## 8. Eldöntött kérdések (v1 lezárva)

**8.1 Dátumformátum a táblázatban — ELDÖNTVE**
`ÉÉÉÉ.HH.NN ÓÓ:PP` (pl. `2026.08.03 09:00`), szigorú ellenőrzéssel;
hibás formátum esetén validációs hiba, nincs "kitalálás".

**8.2 Nem létező kategória — ELDÖNTVE**
Validációs hiba, konkrét hibaüzenettel (megnevezve, melyik
kategórianév nem található). A poszt nem hozható létre, amíg nincs
javítva (kézzel a WP adminban, vagy a dokumentumban).

**8.3 Publikálási állapot (status) logika — ELDÖNTVE, MÓDOSÍTVA**
A biztonság kedvéért **csak jövőbeli dátum engedélyezett**:
- validáció: a "Publikálás dátuma" mezőnek a jelen pillanatnál
  **későbbinek** kell lennie — ha nem az, validációs hiba
  ("A dátum nem lehet jelenlegi vagy múltbeli — adj meg jövőbeli
  időpontot."),
- a `status` mindig `"future"` — a program **soha nem** publikál
  azonnal, mindig ütemezi a WordPress-re, hogy ellenőrizhető legyen
  ütemezett állapotban a publikálás előtt.

**8.4 "Beleolvasó szövege" (Excerpt) — ELDÖNTVE, ÉS JÖVŐBELI BŐVÍTÉS**
V1: a WordPress `excerpt` mezőjébe kerül, egyszerű szövegként.

V2 (későbbi bővítés, most rögzítve, hogy tudjuk mire tervezzünk):
a "Beleolvasó szövege" mező akár több bekezdésből is állhat, ezeket a
program automatikusan HTML bekezdésekké alakítja. Az **első**
bekezdés sima szövegként/egyszerű `<p>`-ként megy be, minden
**további** bekezdés a következő formázással:

```html
<p style="margin-top:-1.1em; text-align:justify;">– Ó, jaj, ne! Szegény Nico!</p>
```

(A negatív felső margó a bekezdések közti térköz szűkítésére szolgál
az excerpt megjelenésekor.) Ez egy elkülönült, egyszerűbb
bekezdés→HTML logika lesz, nem a fő `html_generator.py` bővítése.

**8.5 Képek kezelése — ELDÖNTVE (kiemelt kép)**
Új metaadat mező: **"Kiemelt kép ID"** — a WordPress médiatárban már
feltöltött kép numerikus azonosítója (attachment ID). A program a
poszt létrehozásakor beállítja a `featured_media` mezőt erre az
ID-ra. Validáció: a program lekérdezi (`GET
/wp-json/wp/v2/media/{id}`), és ha nem található ilyen ID-jű média,
validációs hiba ("Nincs ilyen ID-jű kép a médiatárban: ..."). Ez csak
a **kiemelt képet** fedi le, nem a törzsszövegbe ágyazott képeket
(ilyenre jelenleg nincs igény).

**8.6 RankMath Title és Description összeállítása — ELDÖNTVE
(2026.09.12-i bővítés, "Sonja Blonde SEO strategy" dokumentum, "Meta
Description Optimization" feladat)**

A program mostantól automatikusan felépíti a RankMath **Title**
mezőjét (`rank_math_title`), a következő formában:

```
{ELSŐ SEO kulcsszó}: {epizód cím} %sep% %sitename%
```

Ahol az "epizód cím" a törzsszöveg első bekezdéséből automatikusan
képzett `<h2>` szövege (lásd 2.2 pont), formázó tagek nélkül. A
`%sep%` és `%sitename%` a RankMath SAJÁT, beépített template-
szintaxisa (elválasztó karakter, ill. az oldal neve) — ezt
SZÁNDÉKOSAN szó szerint, változatlanul írjuk a mezőbe, a RankMath
saját maga helyettesíti be őket megjelenítéskor. Ha nincs SEO
kulcsszó VAGY nincs `<h2>` a törzsszövegben, a mező egyszerűen
kimarad a payloadból, és RankMath a saját, globális title-sablonjára
esik vissza (ez NEM hiba).

A RankMath **Description** mezőjéhez (`rank_math_description`) a "SEO
snippet" szöveg VÉGÉRE, szóközzel elválasztva, opcionálisan bekerül
egy **sorozat- és nyelv-specifikus** figyelemfelhívó mondat, amiben
`{n}` helyére a "Rész sorszáma" kerül. Ez a mondat a
`config/sorozatok.json` adott sorozat+nyelv blokkjában, az opcionális
`meta_description_sablon` kulcsban adható meg (lásd
`converter/navigation.py` `build_meta_description_suffix()`) —
UGYANAZZAL az elvvel, mint a navigációs gombok szövegfelülírásai
(lásd a 9. pont "Sorozatonkénti szövegfelülírás" alpontját): ha egy
sorozathoz (vagy egy adott nyelvéhez) nincs megadva ilyen sablon, a
leírás egyszerűen a sima SEO snippet marad, kiegészítés nélkül — ez
NEM hiba, csak hiányzó, opcionális konfiguráció. Nem sorozat-részhez
tartozó (önálló) posztoknál ez a kiegészítés értelemszerűen sosem
kerül bele.

Jelenleg (2026.09.12) az "A szalon" sorozathoz van beállítva
mindhárom nyelven:

```json
"meta_description_sablon": "Olvasd el A szalon {n}. részét a humoros szépségszalon-sorozatban!"   // hu
"meta_description_sablon": "Read Part {n} of The Salon, a humorous beauty salon series!"            // en
"meta_description_sablon": "¡Lee la Parte {n} de El salón, una serie humorística de salón de belleza!"  // es
```

Más sorozatokhoz (pl. "Emily naplója") egyelőre NINCS beállítva —
ott a leírás a sablon-kiegészítés nélkül, változatlanul kerül ki.

---

## 9. Elementor-struktúra — ELDÖNTVE (egyszerűsített, egy-két widgetes megoldás)

A jelenlegi kézi munkafolyamatban minden poszt Elementor-felépítése két
szekcióból, több oszlopból és kétféle widgetből (Text Editor + HTML)
állt. Ehelyett az új projektben egy jelentősen egyszerűbb, de továbbra
is Elementorban maradó struktúrát használunk:

```
Section
└── Column
    ├── HTML widget (Elementor widgetType: "html")
    │   └── tartalma: a bejegyzés törzsszövegének HTML-je
    │       + alatta egy CSS-alapú (pl. flexbox) kétoszlopos <div>
    │         a navigációs linkeknek (sorozat eleje / következő rész)
    └── Shortcode widget (Elementor widgetType: "shortcode") — CSAK
        HA az adott nyelvhez be van állítva CTA-sablon ID (lásd a
        pont végén, "Szerzői CTA-doboz")
```

**Miért ez mellett döntöttünk:**
- Az Elementor "widget" fogalma **nem** azonos a klasszikus WordPress
  sidebar-widgetekkel — ez a builder saját tartalmi blokkja, ami a
  poszt `_elementor_data` meta mezőjében tárolódik.
- Egyetlen szekció/oszlop/widget → sokkal egyszerűbb és kisebb
  kockázatú `_elementor_data` JSON-t kell a programnak felépítenie és
  beírnia, mint egy több szekciós/oszlopos/widget-típusos struktúránál.
- Megmarad az Elementorban való utólagos, kézi szerkeszthetőség
  lehetősége (ez fontos szempont volt).
- A navigációs linkek kétoszlopos elrendezését egyszerű CSS-sel (a
  HTML kódon belül) oldjuk meg, nem Elementor-oszlopokkal.

A poszt létrehozásakor a programnak az alábbi meta mezőket kell
beírnia (a sima `content` mező mellett/helyett):
- `_elementor_data` — a fenti egy-widgetes struktúra JSON-ja, benne a
  teljes generált HTML-lel,
- `_elementor_edit_mode` = `"builder"`,
- `_elementor_template_type` = `"wp-post"`,
- `_elementor_version` — az adott oldalon futó Elementor verziószáma
  (ezt egyszer le kell kérdezni/rögzíteni).

**A "sorozat navigáció" tartalma — VÉGLEGESÍTVE:** a
`config/sorozatok.json` fájl sorozatonként, **nyelvenként** tárolja
az adatokat (mert a Polylang-integráció miatt a blog három nyelvű —
lásd 10. pont): a nyelvspecifikus megjelenő sorozatnevet
(`megjelenitett_nev`), az első rész URL-jét és címét
(`elso_resz_url`, `elso_resz_cim`), valamint egy URL-**sablont**
(`resz_url_sablon`, pl. `/a-szalon-{resz}-resz/`) tetszőleges
későbbi rész linkjének felépítéséhez. A gomb körüli FIX szövegek
("Új vagy?", "Folytatás", stb.) nyelvenkénti fordítása magában a
`converter/navigation.py`-ban van (`NAV_TEXT_TEMPLATES`), nem a
JSON-configban, mert ezek nem sorozat-specifikusak.

**Sorozatonkénti szövegfelülírás (2026.08.23-i bővítés):** a fenti
generikus, minden sorozatra érvényes szövegsablonok egyes
sorozatoknál nyelvtanilag esetlenek lehetnek (pl. "Olvasd el Emily
naplója sorozat részeit..." — a "sorozat" szó nem illik a "napló"
utótaghoz). Emiatt a `config/sorozatok.json` egy adott sorozat egy
adott nyelvi blokkjában az alábbi, MINDHÁROM mezőnél opcionális
kulcsokkal felülírható a generikus szöveg:

- `elso_resz_intro` — a "sorozat eleje" gomb bevezető mondatát
  írja felül TELJES egészében (nem sablon, nincs benne
  behelyettesítés — a szerző már a végleges, a sorozat nevéhez
  illeszkedő mondatot adja meg).
- `kovetkezo_resz_cimke_sablon` — a "következő rész" gomb
  rész-számot tartalmazó feliratát (alapból pl. `"{n}. rész"`)
  írja felül; a `{n}` helyére a program a rész sorszámát
  helyettesíti be.
- `kovetkezo_resz_szoveg` — a "következő rész" gomb alatti,
  "Folytatás →" jellegű sort írja felül TELJES egészében (nem
  sablon).

Ha egy sorozat+nyelv blokkban ezek a kulcsok hiányoznak, a program
az általános `NAV_TEXT_TEMPLATES`-beli szöveget használja
változatlanul (ez marad pl. "A szalon" sorozat viselkedése).
Példa (az "Emily naplója" sorozat magyar bejegyzése,
`config/sorozatok.json`):

```json
"elso_resz_intro": "Olvasd Emily naplóját az elejétől, és ismerd meg, hogyan kezdődött minden →",
"kovetkezo_resz_cimke_sablon": "{n}. bejegyzés →",
"kovetkezo_resz_szoveg": "Folytasd Emily történetét a következő epizódban."
```

Az angol/spanyol nyelvű felülírásokat (ha a férj kéri őket) ugyanígy,
a sorozat `en`/`es` blokkjába kell felvenni — a mechanizmus
nyelvenként FÜGGETLENÜL működik, tehát egy sorozatnak lehet pl. csak
magyar felülírása, és angol/spanyol nyelven a generikus szöveg
marad érvényben, amíg valaki fel nem veszi azokat is.

A metaadat-táblázatba két új, opcionális mező került: **"Sorozat
neve"** és **"Rész sorszáma"** — ha ki vannak töltve, a program ez
alapján generálja a navigációs HTML-t a sablonból, nem kell minden
alkalommal kézzel újraírni.

**A gombstílus eredete — TISZTÁZVA:** a `blog-button` (és
`blog-button-emoji`) egy **globális, site-szintű CSS class**, a
WordPress Testreszabó "Additional CSS" mezőjében definiálva (nem
egy adott Elementor-widget saját stílusa). Ez azt jelenti, hogy a
programunk által generált, sima `<a class="blog-button" href="...">`
linkek **változtatás nélkül**, automatikusan felveszik a megfelelő
kinézetet (lekerekített sarkok, színek, mobil-reszponzív viselkedés) —
nem kell semmit Elementor-widgetté alakítani vagy a HTML-generátorban
külön kezelni ezt a stílust.

**KIEGÉSZÍTÉS a gombstílushoz:** a kézzel készített referencia-gomb
Elementor "Advanced" fülén widget-szintű beállítások is voltak
(háttérszín `#8C6239`, hover-szín `#B07A43`, box-shadow,
lekerekítettebb sarok, eltérő padding) — ezek NEM részei a globális
`.blog-button` class-nak, ezért a program a saját, generált HTML-je
elé egy **szűken célzott** (`.sonjablog-nav-item .blog-button`),
beágyazott `<style>` blokkot ír, ami csak a MI navigációs gombjainkra
hat, a `.blog-button` class más előfordulásait (pl. régebbi, kézzel
készített posztokon) nem érinti. Ugyanez a `<style>` blokk oldja meg
azt is, hogy a gomb NE nyúljon szét a teljes sorszélességre, amikor
csak egyetlen gomb látható (lásd `.sorozat-eleje`/`.sonjablog-nav-item`
csomagoló elem, `max-width` korlátozással, a mobil nézet
érintetlenül hagyásával).

**"Következő rész" gomb — HTML-generálás ELKÉSZÜLT, automatikus
beillesztés MÉG NEM:** a `converter/navigation.py` tartalmaz egy
`build_next_part_button_html()` függvényt, ami TETSZŐLEGES
rész-számhoz felépíti a megfelelő nyelvű "következő rész" gomb
HTML-jét (a `resz_url_sablon` és a nyelvi szöveg-sablonok alapján).
EZ MÉG NINCS BEKÖTVE semmilyen automatikus poszt-frissítő
folyamatba — lásd alább.

**"Következő rész" link és poszt-frissítés — ELDÖNTVE:** mivel ez a
link csak azután jelenik meg egy résznél, hogy a *következő* rész már
megjelent, a korábbi rész posztját utólag frissíteni kellene. V1-ben
ebből **csak a láthatatlan jelölő** (HTML comment) kerül bele a
generált HTML-be, pontosan azon a helyen, ahova a leendő "következő
rész" link majd bekerül — ez biztosítja, hogy a program **csak** az
általa generált posztokat tudja majd biztonságosan azonosítani és
frissíteni. Maga a poszt-frissítő funkció (ami visszamenőleg beszúrja
a linket egy korábbi részbe, a már kész `build_next_part_button_html()`
felhasználásával) egy **későbbi lépésben** készül el, miután az alap
poszt-generálás megbízhatóan működik éles használatban (2026.07.27:
ez a feltétel gyakorlatilag teljesült — a poszt-frissítő funkció a
következő tervezett fejlesztési lépés).

**A jelölő tartalma — BŐVÍTVE (2026.08.23), amíg a poszt-frissítő
funkció nincs kész:** a jelölő MOST MÁR nem csak a puszta, gépi
azonosításra szolgáló komment (`series="..." part="..."`), hanem
UGYANAZON a HTML-kommenten belül a KÖVETKEZŐ rész gombjának TELJES,
kikommentezett kódját is tartalmazza (a jelenlegi rész sorszáma + 1
alapján, `build_next_part_button_html()`-lel felépítve — lásd
`converter/navigation.py` `build_next_part_marker()`). Így amíg a
poszt-frissítő funkció el nem készül, a férj a WordPress
szerkesztőben a korábbi rész posztjának HTML widgetjében megkeresi
a jelölőt, és egyszerűen eltávolítja a `<!--`/`-->` komment-jeleket
— nem kell a gomb HTML-jét kézzel begépelnie. A jelölő NYITÓ sora
(a `series`/`part` azonosító) továbbra is a JELENLEGI poszt saját
rész-számát tartalmazza (ez marad a jövőbeli automatikus
frissítő funkció kulcsa); csak a komment BELSEJE (az előnézeti gomb)
vonatkozik a következő részre. Ha a config/sorozatok.json-ból (még)
nem építhető fel a következő rész gombja, a jelölő a régi, puszta
azonosító formájában marad — ez csak egy kényelmi előnézet, hiánya
nem hiba.

**Nyelvi URL-előtag a navigációs linkekben (2026.09.26-i javítás):** a
Polylang URL-szerkezete: HU előtag nélkül (`/emily-naploja-27-bejegyzes/`),
EN `/en/` (`/en/emilys-diary-entry-27/`), ES `/es/`
(`/es/el-diario-de-emily-entrada-27/`). A `config/sorozatok.json`
előtag NÉLKÜLI útvonalakat tárol (`elso_resz_url`, `resz_url_sablon`), a
generátor viszont korábban ezeket változtatás nélkül írta a gombok
href-jébe — EN/ES posztokban ez felesleges 301-es átirányítást okozott
(SEO szempontból kerülendő). A javítás: a `converter/navigation.py`
KÖZPONTI `build_post_path(nyelv, útvonal)` függvénye (a
`LANGUAGE_URL_PREFIXES` táblával) adja hozzá az előtagot; MINDEN
navigációs link (sorozat eleje gomb, következő rész gomb, és a
jelölőbe ágyazott kikommentezett előnézeti gomb) ezen keresztül épül.
A kimenet mindig RELATÍV (`/en/...`), nincs dupla előtag (`/en/en/...`;
az már előtagos bemenetet nem toldja meg), a HU kimenet változatlan,
abszolút URL-t nem érint, ismeretlen nyelvre `ValueError`. Új nyelv
esetén a `LANGUAGE_URL_PREFIXES`-t is bővíteni kell. Tesztek:
`python -m unittest discover -s tests -t . -v`. Éles ellenőrzés: az Emily naplója 30. részének
(mindhárom nyelv) generálása hibátlan, előtagos linkekkel.

*Nyitott pont:* a "placeholder → éles gomb" automatikus csere (a korábbi
rész posztjában) továbbra sincs megvalósítva — amikor elkészül, a
linket a `build_next_part_button_html()`-lel (vagyis `build_post_path`-tal)
kell építenie, és a jelölő keresésekor a már előtagos href-et is
ismernie kell.

**Szerzői CTA-doboz (2026.09.01-i bővítés) — ELDÖNTVE:** minden poszt
törzsszövege (és a sorozat-navigáció) alá opcionálisan bekerülhet egy,
a WordPress oldalon Elementor Saját sablonként elmentett CTA-doboz
(pl. "iratkozz fel", "kövess a Facebookon", stb.). Ezt NEM a
törzsszöveg HTML-jébe ágyazzuk bele, hanem egy MÁSODIK, önálló
Elementor widgetként ugyanabba az oszlopba — mert gyakorlati teszttel
igazolt tapasztalat, hogy az Elementor HTML widgetje SZÁNDÉKOSAN nem
futtatja le a WordPress-shortcode-okat (sem a natív Elementor
"[elementor-template]", sem a "Dynific Addons for Elementor" (korábbi
nevén "AnyWhere Elementor") plugin "[INSERT_ELEMENTOR id=xxx]"
rövidkódja nem dolgozódik fel benne) — ehhez az Elementor saját,
dedikált **Shortcode widgetje** kell (`widgetType: "shortcode"`,
`settings.shortcode`).

A CTA-sablon ID-ja **nyelvenként** külön adható meg a `.env/secrets`
fájlban (`CTA_SHORTCODE_ID_HU`, `CTA_SHORTCODE_ID_EN`,
`CTA_SHORTCODE_ID_ES`) — ezek OPCIONÁLIS kulcsok (NEM szerepelnek a
`wordpress/config.py` `REQUIRED_KEYS` listájában). Ha egy nyelvhez
nincs megadva ID (vagy a Dynific plugin egyáltalán nincs telepítve),
a `wordpress/wp_client.py` `WordPressClient._build_cta_shortcode()`
egyszerűen `None`-t ad vissza, és a `build_elementor_data()` ilyenkor
KIHAGYJA a Shortcode widgetet — a poszt a régi, egy-widgetes
szerkezetével jön létre, ez NEM hiba. Ugyanaz a defenzív elv, mint a
sorozat-navigációnál: egy hiányzó/opcionális konfiguráció miatt nem
szabadna, hogy elszálljon a teljes poszt-létrehozás.

**FONTOS KORLÁTOZÁS:** a CTA-doboz KIZÁRÓLAG a WordPress oldalon,
publikálás/előnézet után válik láthatóvá — a GUI saját, helyi HTML
előnézete (lásd 7. pont) ezt NEM jeleníti meg, mert a Shortcode widget
csak a `wp_client.create_post()` hívásban, a WordPress-nek küldött
`_elementor_data`-ban jön létre, a helyi `body_html`-nek (amit a GUI
előnézete mutat) nem része.

---

## 10. Polylang (többnyelvűség) integráció

A blog **három nyelvű** (magyar `hu`, angol `en`, spanyol `es`),
Polylang **ingyenes** verzióval. A munkafolyamat: a feleséged
elkészíti a magyar ODT-t, majd lefordítja angolra és spanyolra
(3 önálló ODT-fájl), és mindhárom nyelvi verziót **külön-külön**
hozod létre a programmal — nagyjából egy időben ütemezve, hogy a
posztok egyszerre váljanak olvashatóvá mindhárom nyelven.

**Technikai háttér:** a Polylang ingyenes verziója NEM támogatja a
nyelv beállítását/a fordítások összekapcsolását a szabványos
WordPress REST API-n keresztül (ez csak a Pro verzióban elérhető).
Emiatt a `wordpress_functions_php_kiegeszites.php` mu-plugin három
egyéni REST végpontot regisztrál:

- `POST sonjablog/v1/set-language` — a Polylang saját
  `pll_set_post_language()` PHP-függvényét hívja meg
- `POST sonjablog/v1/link-translations` — a Polylang saját
  `pll_save_post_translations()` PHP-függvényét hívja meg
- `GET sonjablog/v1/category-id?name=...&lang=...` — lásd lentebb,
  ÉLES HIBAKERESÉS UTÁN véglegesített megoldás a kategória-keresésre

**A kategória-keresés története (élesben felmerült, megoldott
probléma):** első nekifutásra a szabványos `/wp/v2/categories`
végpontot próbáltuk a `lang` query-paraméterrel megcélozni — kiderült,
hogy ez a paraméter a hivatalos Polylang dokumentáció szerint CSAK
Pro verzióban működik natívan, Free verzióban a WordPress egyszerűen
figyelmen kívül hagyja. Egy második próbálkozás a Polylang belső,
nem hivatalos "curlang" állapotának kézi beállítására épült — ez
ELMÉLETBEN dokumentált trükk, de a gyakorlatban NEM bizonyult
megbízhatónak (feltehetően Polylang-verziófüggő). A VÉGLEGES,
működő megoldás: egy SAJÁT REST végpont (`category-id`), ami
PHP-szinten közvetlenül a `get_terms(['lang' => ...])` hívást
használja — ez a Polylang legalapvetőbb, Free verzióban is stabil,
régóta bevált funkciója (nem REST-specifikus, nem Pro-only), mert a
Polylang saját maga is ezt használja mindenhol belül.

**KRITIKUS SORREND (élesben felmerült, megoldott probléma):** a
poszt létrehozásakor **ELŐSZÖR** kell beállítani a poszt NYELVÉT, és
**CSAK UTÁNA** szabad hozzárendelni a kategóriákat — fordított
sorrendben (ahogy elsőre implementáltuk) a Polylang CSENDBEN
figyelmen kívül hagyja az idegen nyelvű kategória hozzárendelését
egy még nyelv nélküli (ilyenkor alapértelmezett nyelvűnek számító)
poszthoz, hibaüzenet nélkül. Emiatt a `wp_client.create_post()` HÁROM
lépésben dolgozik: (1) poszt létrehozása kategóriák nélkül, (2) nyelv
beállítása, (3) egy külön, frissítő kéréssel a kategóriák (és az
elsődleges kategória) hozzárendelése.

**A "fordítás-csoport azonosító"**: mivel a három nyelvi verzió
külön-külön, akár más napon készül el, a programnak emlékeznie kell,
melyik poszt melyik történet melyik nyelvi verziója. Ezt egy helyi
állapot-fájl (`state/forditasi_csoportok.json`) tartja nyilván — ezt
a fájlt KIZÁRÓLAG a program kezeli, nem kell kézzel szerkeszteni.
Amint egy adott történetnek legalább 2 nyelvi verziója elkészült, a
program automatikusan összeköti őket Polylang-fordításként; a
harmadik nyelv elkészültekor mindhárom véglegesen összekapcsolódik.

**Elsődleges kategória**: ha egy posztnak több kategóriája van, a
megadott lista **első** eleme lesz a RankMath "Primary Term"
beállítása (`rank_math_primary_category` meta mező) — ez befolyásolja
pl. az URL-ben használt kategória-szeletet.

**FONTOS, amit a Polylang oldalán is ellenőrizni kell:** a Languages
→ Settings → "Taxonomies" szekcióban a "Categories" opciónak
BEKAPCSOLVA kell lennie ("Activate languages and translations"),
különben a kategóriák nem kapnak nyelvet, és a fenti mechanizmus nem
tud értelmesen működni.

---

## 11. Windows .exe csomagolás

A program `python main.py`-jal futtatható szkriptként, DE a
feleséged számára kényelmesebb egy önálló, Python telepítése
nélkül futtatható `.exe` — ezt a `build_exe.bat` szkript állítja
elő (PyInstaller segítségével), a projekt gyökeréből futtatva.

**Fontos technikai előfeltétel:** mivel egy becsomagolt `.exe`
futtatásakor a "jelenlegi munkakönyvtár" a helyzettől függően
változhat (Intéző dupla-kattintás, parancsikon, stb.), a program
a `paths.py` modul segítségével MINDIG a saját (az `.exe`
fájlt tartalmazó) mappájához képest keresi a `.env/secrets`,
`config/sorozatok.json` és `state/forditasi_csoportok.json`
fájlokat — NEM a munkakönyvtárhoz képest. Ezt a `.env/` és
`config/` mappákat az elkészült `.exe` MELLÉ kell másolni (a
`state/` mappát a program magától létrehozza).

**A build folyamata**: `build_exe.bat` (1) telepíti a
`requirements.txt` függőségeit, (2) telepíti a PyInstaller
csomagot, (3) legyártja az `.exe`-t `--onefile --windowed`
móddal a `dist/` mappába. Ezt Windows gépen kell futtatni — a
PyInstaller nem tud "keresztfordítani" más operációs rendszerről.

---

## 12. Amit a projekt NEM csinál (kezdetben)

- Nem hoz létre automatikusan új WordPress kategóriát.
- Nem tölt fel új képet a médiatárba — a kiemelt képnek már fel kell
  lennie töltve, a dokumentum csak annak ID-jét adja meg.
- Nem kezel a törzsszövegbe ágyazott képeket, csak a kiemelt képet.
- Nem ad lehetőséget meglévő poszt szerkesztésére/frissítésére, csak
  új poszt létrehozására (kivéve, ha a 9. pontban tárgyalt "következő
  rész" link automatizálása mellett döntötök).
- Nem épül webes (böngészőben futó) felület — a jelenlegi terv PySide6
  asztali GUI-t céloz. Mivel a feldolgozó logika (`converter/`,
  `wordpress/`) el van választva a felülettől (`ui/`), egy esetleges
  jövőbeli webes verzió (pl. Streamlit/NiceGUI, hogy iPadről/távolról
  is lehessen posztot közzétenni) később, a meglévő logika
  újraírása nélkül is megvalósítható — ez most nem befolyásolja a
  tervezést, csak egy nyitva hagyott lehetőség.
- Nem kezeli a `.venv` vagy egyéb fejlesztői környezeti fájlokat —
  ezekre a meglévő `.gitignore` vonatkozik változatlanul.
