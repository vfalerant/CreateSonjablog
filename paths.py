"""
paths.py

Ez a modul EGYETLEN felelősséggel bír: megbízhatóan megállapítani a
projekt GYÖKÉRKÖNYVTÁRÁT — akár `python main.py`-jal, szkriptként
fut a program, akár egy PyInstaller által becsomagolt önálló `.exe`-
ként.

MIÉRT KELL EZ (2026.07.27-i kiegészítés, a Windows .exe csomagolás
előkészítéseként)? A wordpress/config.py (`.env/secrets`), a
converter/navigation.py (`config/sorozatok.json`) és a
wordpress/translations.py (`state/forditasi_csoportok.json`) eddig
egy RELATÍV útvonalat használt (pl. ".env/secrets"), ami a program
JELENLEGI MUNKAKÖNYVTÁRÁHOZ képest értelmeződik. Ez `python main.py`-
jal, a projekt gyökeréből futtatva jól működik — DE egy becsomagolt
`.exe` esetén a munkakönyvtár attól függően változhat, hogyan
indítják el a programot (Intéző dupla-kattintás, parancsikon, más
mappából indított parancssor, stb.), ami azt eredményezhetné, hogy a
program nem találja meg a saját fájljait.

Ehelyett MOSTANTÓL mindhárom modul EZT a get_project_root()
függvényt használja, ami MINDIG a program TÉNYLEGES helyéhez (nem a
munkakönyvtárhoz) képest számol — ez konzisztens, kiszámítható
viselkedést ad mindkét futtatási módban.
"""

import os
import sys


def get_project_root():
    """
    Visszaadja a projekt gyökérkönyvtárának ABSZOLÚT útvonalát.

    KÉT ESET:

    1. Ha a program egy PyInstaller által becsomagolt .exe-ként fut
       (ezt a `sys.frozen` attribútum jelzi, amit a PyInstaller
       futásidőben automatikusan beállít) — ekkor a gyökér az .exe
       fájlt TARTALMAZÓ mappa. FONTOS: emiatt a `.env/`, `config/`
       és `state/` mappáknak UGYANABBAN a mappában kell lenniük,
       ahova az .exe-t kiteszed, NEM az .exe "belsejében" (a
       PyInstaller ugyanis a Python-kódot magát csomagolja be, a
       mellette lévő adatfájlokat NEM).

    2. Ha a program sima `.py` szkriptként fut (`python main.py`) —
       ekkor a gyökér ennek a paths.py fájlnak a saját mappája
       (ami maga a projekt gyökere, hiszen ide tettük a paths.py-t).
    """

    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)

    return os.path.dirname(os.path.abspath(__file__))
