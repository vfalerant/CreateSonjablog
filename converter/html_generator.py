"""
html_generator.py

Az odt_reader.py által visszaadott "blocks" listából (lásd ott a
formátumot: {"type": ..., "text": ...} dict-ek) épít egy darab
összefűzött HTML stringet — ez kerül majd az Elementor HTML
widgetbe (lásd a specifikáció 9. pontját).

A TÖRZSSZÖVEG ELSŐ BEKEZDÉSE MINDIG <h2> CÍMSOR LESZ — EZ SZÁNDÉKOS,
ÚJRA VISSZAÁLLÍTOTT VISELKEDÉS. (Az 1. lépésben ezt a logikát még
eltávolítottuk, mert akkor még úgy gondoltuk, felesleges — kiderült
azonban, hogy TOVÁBBRA IS kell, csak MÁS okból, mint a projekt
korábbi, odt_to_html verziójában. Ha valaha megint elgondolkoznál
ennek eltávolításán, ELŐSZÖR OLVASD EL EZT:)

  A metaadat-táblázat "Cím" mezője a WordPress POSZT CÍME lesz — ez
  jelenik meg a téma saját <h1>-jeként, és ez alapján generálódik az
  URL is. A feleséged ezt jellemzően a sorozat/rész-számozás szerint
  tölti ki, pl. "A szalon – 7. rész".

  A törzsszöveg ELSŐ bekezdése viszont a TÖRTÉNET SAJÁT, hangulatos,
  az adott részre jellemző címe/alcíme, pl. "A hegyek csendje" — ezt
  a szerző (ahogy korábban is) a szöveg elejére írja, NEM a
  metaadat-táblázatba. Ez a poszt TARTALMÁN belül jelenik meg <h2>
  formában, közvetlenül a poszt <h1> címe (a WordPress saját
  posztcíme) alatt.

  Tehát a kettő EGYÜTT, EGYMÁS MELLETT működik:
    <h1> A szalon – 7. rész          <- WordPress posztcím (metaadat "Cím" mező)
    <h2> A hegyek csendje            <- a törzsszöveg első bekezdése (ITT alakítjuk át)
    (a történet szövege...)
"""

import re


def strip_formatting_tags(text):
    """
    Címsorokból (h1, h2, ...) eltávolítja az esetleges <i>/<strong>
    formázást — egy címsorban nem szeretnénk félkövér/dőlt
    részleteket, ott a formázás a HTML tag (pl. h2) szintjén már
    eleve megvan.
    """

    text = re.sub(r"</?i>", "", text)
    text = re.sub(r"</?strong>", "", text)

    return text


def map_block(text, element_type, is_first):
    """
    Egyetlen blokkot alakít át a megfelelő HTML-lé.

    is_first: True, ha ez a törzsszöveg ELSŐ, nem-üres blokkja —
              ekkor FÜGGETLENÜL az eredeti típusától (még akkor is,
              ha ODT-ben simán csak bekezdésként írták), <h2>
              címsorrá alakítjuk (lásd a modul tetején lévő
              magyarázatot, MIÉRT).

    A típusok szerinti logika (is_first=False esetén):

      "empty" -> egy középre igazított "*" — ezt használja a
                 szerző jelenetváltás/időugrás jelzésére a
                 történetben (egy szándékosan hagyott üres sor)

      "h1", "h2", "h3", ... -> valódi címsor a törzsszövegen belül
                 (pl. ha a szerző egy hosszabb novellát több
                 "fejezetre" tagol). A h1-et szándékosan h2-vé
                 fokozzuk le, hogy sose ütközzön/keveredjen a
                 WordPress saját posztcímével.

      "list" -> egy listaelem, kézzel rakott "•" karakterrel (NEM
                valódi <ul>/<li> HTML lista — ez szándékos
                egyszerűsítés, mert az Elementor HTML widgetben
                így könnyebb egységesen kezelni a bekezdés-szerű
                sorstílust, mint egy beágyazott <ul>-t)

      minden más ("p") -> sima, sorkizárt bekezdés
    """

    # üres sor -> "*" elválasztó
    # FONTOS: ez FÜGGETLEN az is_first-től — egy üres sor sosem
    # lehet az "első" tartalmi blokk, mert az odt_reader.py már a
    # dokumentum elejéről/végéről levágja a felesleges üres
    # blokkokat (lásd read_odt_document), tehát a blocks lista
    # első eleme mindig egy TÉNYLEGES tartalommal bíró blokk lesz
    if element_type == "empty":
        return '<p style="text-align:center;">*</p>'

    # a törzsszöveg első tartalmi blokkja -> mindig <h2>,
    # a story saját alcíme (lásd a modul tetején lévő magyarázatot)
    if is_first:

        clean_text = strip_formatting_tags(text)

        return f"<h2>{clean_text}</h2>"

    # címsor (h1, h2, h3, ...) — ha a szerző a történeten BELÜL,
    # nem az elején használt címsor-stílust (pl. fejezetcímekhez)
    if element_type.startswith("h"):

        try:
            level = int(element_type[1])
        except:
            # ha valamiért nem sikerül számot kiolvasni a típusból
            # (nem várt eset), biztonságosan h2-nek vesszük
            level = 2

        clean_text = strip_formatting_tags(text)

        if level == 1:
            # h1 -> h2, hogy ne ütközzön a poszt saját címével
            return f"<h2>{clean_text}</h2>"

        return f"<h{level}>{clean_text}</h{level}>"

    # lista-elem
    if element_type == "list":
        return f'<p style="text-align:justify;">• {text}</p>'

    # normál bekezdés (ez az alapértelmezett ág is, tehát ha valaha
    # egy új, itt nem kezelt "type" kerülne be a blocks listába,
    # egyszerű bekezdésként fog megjelenni, nem fog hibát dobni)
    return f'<p style="text-align:justify;">{text}</p>'


def generate_html(blocks):
    """
    Végigmegy az összes blokkon, mindegyiket átalakítja
    (map_block), majd üres sorral elválasztva összefűzi őket egy
    darab HTML stringgé.

    Nyomon követi, hogy melyik az ELSŐ nem-üres blokk (lásd
    map_block "is_first" paramétere) — CSAK az kerül <h2>-ként
    kiírásra, minden további, akár azonos típusú blokk (pl. egy
    fejezetcím később a szövegben) a normál szabályok szerint
    alakul HTML-lé.

    A blokkok közötti "\\n\\n" (üres sor) csak a HTML FORRÁSKÓD
    olvashatóságát szolgálja (hogy ha valaki megnézi a nyers HTML-t,
    átlátható legyen) — a böngésző/Elementor szempontjából nincs
    jelentősége, mert a <p> tagek maguktól új sorba kerülnek.
    """

    html_parts = []

    first_content_found = False

    for block in blocks:

        is_first = (
            not first_content_found
            and block["type"] != "empty"
        )

        html_parts.append(
            map_block(
                text=block["text"],
                element_type=block["type"],
                is_first=is_first
            )
        )

        if block["type"] != "empty":
            first_content_found = True

    return "\n\n".join(html_parts)
