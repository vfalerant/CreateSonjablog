"""
odt_reader.py

Ez a modul olvassa be a nyers .odt fájlt, és két részre bontja:

  1. metadata_rows: a dokumentum ELSŐ táblázatának sorai, nyers
     (label, érték) párokként — ebből építi fel a
     metadata_parser.py a strukturált metaadatokat (cím, dátum,
     kategóriák, stb.)

  2. blocks: a törzsszöveg (a táblázat UTÁNI rész), egy listányi
     "blokk" dict formájában, pl.:
       {"type": "p", "text": "Valami bekezdés szövege"}
       {"type": "h2", "text": "Egy címsor"}
       {"type": "list", "text": "Egy listaelem"}
       {"type": "empty", "text": ""}
     Ezt a html_generator.py alakítja majd HTML-lé.

Az .odt fájl technikailag egy ZIP archívum, amiben a szöveges
tartalom a content.xml-ben van, XML formátumban (ODF szabvány).
Ez a modul közvetlenül ezt az XML-t olvassa (nem használ külső
odfpy-szerű könyvtárat), úgyhogy ha valaha "furcsa" a kimenet,
érdemes megnézni magát a content.xml tartalmát is (egy .odt fájlt
átnevezve .zip-re, majd kicsomagolva hozzáférhető).
"""

import zipfile
import xml.etree.ElementTree as ET


# Az ODF (OpenDocument Format) szabvány "névterei" (namespace-ei).
# Az XML-ben minden elem/attribútum egy ilyen névtérhez tartozik,
# pl. a bekezdés valójában "{urn:oasis:...:text:1.0}p", nem csak "p".
# Ezekre a rövidítésekre (office, text, style, fo, table) hivatkozunk
# a kód többi részében findall()/find() hívásokban.
NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
}


def normalize_block_text(text):
    """
    Egy bekezdés/szövegdarab "megtisztítása":
    - sortörés és tabulátor karakterek szóközre cserélése
      (LibreOffice-ban ritkán, de előfordulhatnak a szövegben)
    - több egymás utáni szóköz összevonása egyre
    - a szöveg elejéről/végéről a felesleges szóköz levágása

    Ez azért fontos, mert a HTML kimenetben nem szeretnénk, hogy
    véletlen dupla szóközök vagy vezető/záró whitespace-ek
    csúfítsák a bejegyzést.
    """

    if text is None:
        return ""

    text = text.replace("\n", " ")
    text = text.replace("\t", " ")

    while "  " in text:
        text = text.replace("  ", " ")

    return text.strip()


def load_style_map(content_root, styles_root):
    """
    Összegyűjti a dokumentumban (és a styles.xml-ben) definiált
    összes szövegstílust, és eldönti mindegyikről, hogy félkövér
    és/vagy dőlt-e.

    Visszatérési érték: dict, ahol a kulcs a stílus neve
    (pl. "T1"), az érték pedig {"bold": True/False, "italic": True/False}.

    Ezt a dict-et használjuk később (get_element_style), amikor egy
    adott bekezdés/span stílusát kell lekérdezni, hogy eldöntsük,
    kell-e köré <strong>/<i> tag a HTML-ben.
    """

    style_map = {}

    # a stílusdefiníciók elszórva lehetnek a content.xml
    # (automatic-styles) ÉS a styles.xml-ben is, ezért mindkettőt
    # végignézzük
    all_styles = []

    all_styles.extend(
        content_root.findall(".//style:style", NS)
    )

    all_styles.extend(
        styles_root.findall(".//style:style", NS)
    )

    for style in all_styles:

        style_name = style.attrib.get(
            f"{{{NS['style']}}}name"
        )

        if not style_name:
            continue

        text_props = style.find(
            "style:text-properties",
            NS
        )

        is_bold = False
        is_italic = False

        if text_props is not None:

            # az ODF-ben a félkövér/dőlt nem "bool" attribútum,
            # hanem fo:font-weight="bold" / fo:font-style="italic"
            # (CSS-hez hasonló elnevezéssel)
            font_weight = text_props.attrib.get(
                f"{{{NS['fo']}}}font-weight",
                ""
            ).lower()

            font_style = text_props.attrib.get(
                f"{{{NS['fo']}}}font-style",
                ""
            ).lower()

            if font_weight == "bold":
                is_bold = True

            if font_style == "italic":
                is_italic = True

        style_map[style_name] = {
            "bold": is_bold,
            "italic": is_italic
        }

    return style_map


def apply_style(text, is_bold, is_italic):
    """Bekeretezi a szöveget <strong>/<i> taggel, ha szükséges."""

    if is_bold and is_italic:
        return f"<strong><i>{text}</i></strong>"

    if is_bold:
        return f"<strong>{text}</strong>"

    if is_italic:
        return f"<i>{text}</i>"

    return text


def get_element_style(element, style_map):
    """
    Lekérdezi egy adott XML elem (pl. egy <text:p> vagy <text:span>)
    stílusnevét (text:style-name attribútum), majd ez alapján
    visszaadja a style_map-ből a bold/italic infót.

    Ha az elemnek nincs stílusa megadva, egyszerű (nem félkövér,
    nem dőlt) szövegnek tekintjük.
    """

    style_name = element.attrib.get(
        f"{{{NS['text']}}}style-name"
    )

    if not style_name:
        return {
            "bold": False,
            "italic": False
        }

    return style_map.get(
        style_name,
        {
            "bold": False,
            "italic": False
        }
    )


def process_inline(element, style_map):
    """
    Egy bekezdésen (vagy más szöveges elemen) BELÜLI tartalmat
    dolgozza fel rekurzívan: a sima szöveget összefűzi, a <text:span>
    elemeket (pl. egy bekezdésen belüli félkövér rész) a megfelelő
    <strong>/<i> taggel látja el, a sortöréseket pedig "\n"
    karakterré alakítja (ezt később split_paragraph_by_linebreak
    bontja szét külön bekezdésekké).

    Ez a függvény hívja saját magát rekurzívan, mert egy span-en
    belül is lehet további span (pl. félkövér ÉS dőlt egyszerre).
    """

    result = ""

    if element.text:
        result += element.text

    for child in element:

        if child.tag == f"{{{NS['text']}}}span":

            span_text = process_inline(
                child,
                style_map
            )

            style_info = get_element_style(
                child,
                style_map
            )

            span_text = apply_style(
                span_text,
                style_info["bold"],
                style_info["italic"]
            )

            result += span_text

        elif child.tag == f"{{{NS['text']}}}line-break":

            # a LibreOffice-ban Shift+Enter-rel beszúrt sortörés
            # (nem új bekezdés, csak új sor UGYANAZON bekezdésen
            # belül) — ezt jelöljük "\n"-nel, amit lentebb külön
            # blokká bontunk szét
            result += "\n"

        else:

            result += process_inline(
                child,
                style_map
            )

        if child.tail:
            result += child.tail

    return result


def split_paragraph_by_linebreak(
    element,
    style_map
):
    """
    Egy <text:p> (bekezdés) tartalmát feldolgozza, majd a benne
    lévő kézi sortörések (Shift+Enter) mentén KÜLÖN darabokra
    bontja. Ez azért kell, mert az ODF-ben egy Shift+Enter NEM hoz
    létre új <text:p> elemet, csak egy <text:line-break>-et — mi
    viszont mindegyik ilyen sort külön blokként szeretnénk kezelni.
    """

    full_text = process_inline(
        element,
        style_map
    )

    return full_text.split("\n")


def is_layout_artifact(element, text):
    """
    Néha a LibreOffice ment egy teljesen üres, stílus nélküli
    <text:p>-t pusztán elrendezési okokból (pl. a szerkesztő belső
    működése miatt, nem a szerző szándékos üres sora). Ezt
    igyekszünk megkülönböztetni egy TÉNYLEGESEN szándékos üres
    sortól (aminek van rá alkalmazott stílusa, pl. "üres bekezdés"
    stílus, és amit a szerző direkt hagyott ott elválasztónak,
    lásd html_generator.py "*" szeparátora).

    Ha a szövegtörzsben ez túl agresszívan szűr, itt érdemes
    keresni a hibát.
    """

    if text:
        return False

    if len(list(element)) > 0:
        return False

    style_name = element.attrib.get(
        f"{{{NS['text']}}}style-name"
    )

    if style_name is None:
        return True

    return False


def process_paragraph(
    element,
    blocks,
    style_map
):
    """
    Egy <text:p> elemet dolgoz fel, és 0, 1 vagy több blokkot ad
    hozzá a blocks listához (több akkor lesz, ha a bekezdésen belül
    kézi sortörés van, lásd split_paragraph_by_linebreak).
    """

    parts = split_paragraph_by_linebreak(
        element,
        style_map
    )

    for part in parts:

        text = normalize_block_text(part)

        if is_layout_artifact(element, text):
            continue

        if not text:

            # szándékos üres sor -> "empty" blokk, amiből a
            # html_generator egy "*" elválasztót csinál
            blocks.append({
                "type": "empty",
                "text": ""
            })

            continue

        style_info = get_element_style(
            element,
            style_map
        )

        text = apply_style(
            text,
            style_info["bold"],
            style_info["italic"]
        )

        blocks.append({
            "type": "p",
            "text": text
        })


def process_heading(
    element,
    blocks,
    style_map
):
    """
    Egy <text:h> (címsor) elemet dolgoz fel. A címsor "szintje"
    (h1, h2, h3...) az ODF-ben a text:outline-level attribútumban
    van megadva — ezt vesszük át típusként ("h1", "h2", stb.), a
    html_generator dönti majd el, hogyan jelenítse meg (pl. h1-et
    is h2-vé alakítja, hogy ne ütközzön a WordPress saját
  oldalcímével).
    """

    text = normalize_block_text(
        process_inline(element, style_map)
    )

    if not text:
        return

    style_info = get_element_style(
        element,
        style_map
    )

    text = apply_style(
        text,
        style_info["bold"],
        style_info["italic"]
    )

    level = element.attrib.get(
        f"{{{NS['text']}}}outline-level",
        "1"
    )

    blocks.append({
        "type": f"h{level}",
        "text": text
    })


def process_list(
    element,
    blocks,
    style_map
):
    """
    Egy <text:list> (felsorolás) elemet dolgoz fel: minden
    <text:list-item> belsejében lévő <text:p> egy külön "list"
    típusú blokk lesz.

    FONTOS: ezt a függvényt a walk_content úgy hívja meg, hogy utána
    NEM megy bele még egyszer rekurzívan ugyanebbe az elembe — ha ezt
    valaki visszaállítaná, a lista-elemek DUPLIKÁLÓDNÁNAK (ez már
    egyszer előfordult, lásd a walk_content kommentjét lentebb).
    """

    for item in element.findall(
        "text:list-item",
        NS
    ):

        for p in item.findall(
            "text:p",
            NS
        ):

            parts = split_paragraph_by_linebreak(
                p,
                style_map
            )

            for part in parts:

                text = normalize_block_text(part)

                if not text:
                    continue

                style_info = get_element_style(
                    p,
                    style_map
                )

                text = apply_style(
                    text,
                    style_info["bold"],
                    style_info["italic"]
                )

                blocks.append({
                    "type": "list",
                    "text": text
                })


def strip_inline_tags(text):
    """
    Eltávolítja a <strong>/<i> formázó tageket egy szövegből.

    ERRE AZÉRT VAN SZÜKSÉG, mert a process_inline() (amit a
    split_paragraph_by_linebreak hív) MINDEN szövegre alkalmazza a
    félkövér/dőlt formázást, ha az ODT-ben egy <text:span> ilyen
    stílussal van megjelölve — FÜGGETLENÜL attól, hogy az egy
    törzsszöveg-bekezdésben van-e (ahol ez helyénvaló és szándékos),
    vagy egy metaadat-táblázat cellájában (ahol NEM — a metaadat-
    mezőknek, pl. a "Cím"-nek, MINDIG sima szövegnek kell lenniük).

    HIBA, AMIT EZ JAVÍT: ha a szerző véletlenül félkövérre állította
    a táblázat "Cím" cellájának szövegét (pl. mert korábban egy
    másik, félkövér cellából másolta be), a program enélkül a
    javítás nélkül szó szerint beleírta volna a
    "<strong>...</strong>" HTML tageket a WordPress poszt CÍMÉBE —
    ez történt a "A szalon – 77. rész" posztnál is.
    """

    return (
        text
        .replace("<strong>", "")
        .replace("</strong>", "")
        .replace("<i>", "")
        .replace("</i>", "")
    )


def extract_cell_text(cell, style_map):
    """
    Egy táblázat-cella (<table:table-cell>) szöveges tartalmát adja
    vissza EGYETLEN stringként (a cellában lévő összes <text:p>-t
    összefűzve, szóközzel elválasztva).

    A metaadat-táblázat celláihoz használjuk — ott minden cella
    általában csak egy rövid szöveg (pl. a cím, vagy egy dátum),
    de biztonság kedvéért több bekezdést is kezel, ha valaki
    véletlenül Entert üt egy cellán belül.

    FONTOS: a metaadat-mezők (Cím, SEO snippet, stb.) MINDIG sima
    szövegként kerülnek ki innen, MÉG AKKOR IS, ha a szerző
    véletlenül félkövérre/dőltre formázta a cella tartalmát az
    ODT-ben — lásd a strip_inline_tags() függvény magyarázatát.
    A törzsszöveg (a táblázat UTÁNI rész) formázása ETTŐL
    FÜGGETLEN, ott a process_paragraph/process_list VÁLTOZATLANUL
    megtartja a bold/dőlt formázást, ahogy kell.
    """

    texts = []

    for p in cell.findall("text:p", NS):

        parts = split_paragraph_by_linebreak(
            p,
            style_map
        )

        for part in parts:

            text = normalize_block_text(part)
            text = strip_inline_tags(text)

            if text:
                texts.append(text)

    return " ".join(texts)


def find_metadata_table(office_text):
    """
    Megkeresi a dokumentum ELSŐ táblázatát (a szabály szerint ez
    tartalmazza a metaadatokat: cím, dátum, kategóriák, stb. — lásd
    a specifikáció 2.1 pontját).

    Csak a KÖZVETLEN gyermekei között keres (nem megy bele mélyebbre
    rekurzívan), mert a metaadat-táblázatnak a dokumentum tetején,
    nem egy másik elem belsejében kell lennie.

    Ha nincs táblázat a dokumentumban, None-t ad vissza — ezt a
    validators.py hibaként jelzi majd ("nincs metaadat-táblázat").
    """

    for child in office_text:

        if child.tag == f"{{{NS['table']}}}table":
            return child

    return None


def extract_metadata_rows(table_element, style_map):
    """
    A metaadat-táblázat minden sorából kiolvassa az első két cella
    szövegét, (label, érték) tuple-ként. Ha egy sorban 2-nél
    kevesebb cella van, azt a sort figyelmen kívül hagyja (hibásan
    szerkesztett táblázat esetén ez véd az IndexError ellen).
    """

    rows = []

    for row in table_element.findall(
        "table:table-row",
        NS
    ):

        cells = row.findall(
            "table:table-cell",
            NS
        )

        cell_texts = [
            extract_cell_text(cell, style_map)
            for cell in cells
        ]

        if len(cell_texts) >= 2:
            rows.append(
                (cell_texts[0], cell_texts[1])
            )

    return rows


def walk_content(
    node,
    blocks,
    style_map,
    skip_element=None
):
    """
    Rekurzívan bejárja a dokumentum XML-fáját, és a felismert
    elemtípusokat (bekezdés, címsor, lista) hozzáadja a blocks
    listához a megfelelő process_* függvénnyel.

    FONTOS, KORÁBBAN JAVÍTOTT HIBA: ha egy gyermek elemet MÁR
    feldolgoztunk process_paragraph/process_heading/process_list
    segítségével, utána NEM szabad még egyszer belemenni
    rekurzívan ugyanabba az elembe — mert pl. egy <text:list> belső
    <text:p>-jei a generikus "if tag == text:p" ághoz is illeszkednek,
    és így DUPLIKÁLÓDNÁNAK a lista-elemek. Emiatt minden felismert
    ágban van egy "continue", ami átugorja a függvény végén lévő
    rekurzív hívást. Csak az EGYÉB (nem külön kezelt) elemekbe megyünk
    bele mélyebbre — pl. egy <office:text> vagy más "wrapper" elembe.

    skip_element: a metaadat-táblázat elem referenciája (identitás
    szerint, "is" összehasonlítással) — ezt szándékosan kihagyjuk,
    hogy a metaadatok NE keveredjenek bele a törzsszöveg blokkjaiba.
    """

    for child in node:

        if child is skip_element:
            continue

        tag = child.tag

        if tag == f"{{{NS['text']}}}p":

            process_paragraph(
                child,
                blocks,
                style_map
            )

            continue

        if tag == f"{{{NS['text']}}}h":

            process_heading(
                child,
                blocks,
                style_map
            )

            continue

        if tag == f"{{{NS['text']}}}list":

            process_list(
                child,
                blocks,
                style_map
            )

            continue

        # ismeretlen/nem külön kezelt elem (pl. egy csoportosító
        # wrapper) -> nézzünk bele mélyebbre, hátha van benne
        # feldolgozandó tartalom
        walk_content(
            child,
            blocks,
            style_map,
            skip_element
        )


def read_odt_document(filepath):
    """
    A modul FŐ belépési pontja. Beolvassa a megadott .odt fájlt,
    és visszaad egy (metadata_rows, blocks) tuple-t:

      metadata_rows: a dokumentum első táblázatának nyers
                     (label, érték) sorai — lásd
                     metadata_parser.parse_metadata, ami ebből
                     épít strukturált adatot.

      blocks: a törzsszöveg blokkjai (a táblázat NÉLKÜL) — lásd
              html_generator.generate_html, ami ebből épít HTML-t.

    Ha a dokumentumban nincs táblázat, metadata_rows üres lista
    lesz — ezt a hívó kódnak (validators.py) kell hibaként
    kezelnie.
    """

    with zipfile.ZipFile(filepath) as z:

        # az .odt egy ZIP archívum; a szöveges tartalom a
        # content.xml-ben, a stílusdefiníciók egy része pedig a
        # styles.xml-ben van
        content_xml = z.read("content.xml")
        styles_xml = z.read("styles.xml")

    content_root = ET.fromstring(content_xml)
    styles_root = ET.fromstring(styles_xml)

    style_map = load_style_map(
        content_root,
        styles_root
    )

    office_text = content_root.find(
        "office:body/office:text",
        NS
    )

    # 1. lépés: keressük meg és olvassuk ki a metaadat-táblázatot
    metadata_table = find_metadata_table(office_text)

    metadata_rows = []

    if metadata_table is not None:
        metadata_rows = extract_metadata_rows(
            metadata_table,
            style_map
        )

    # 2. lépés: járjuk be a törzsszöveget, de a metaadat-táblázatot
    # kifejezetten kihagyva (skip_element), hogy ne keveredjen bele
    blocks = []

    walk_content(
        office_text,
        blocks,
        style_map,
        skip_element=metadata_table
    )

    # a törzsszöveg elejéről/végéről levágjuk a felesleges üres
    # blokkokat (pl. a táblázat utáni "elválasztó" üres bekezdést,
    # amit a sablon szerint a szerző a táblázat és a szöveg közé
    # tesz — ez nem szándékos "*" elválasztó, csak formai elem)
    while (
        blocks
        and blocks[-1]["type"] == "empty"
    ):
        blocks.pop()

    while (
        blocks
        and blocks[0]["type"] == "empty"
    ):
        blocks.pop(0)

    return metadata_rows, blocks
