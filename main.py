"""
main.py

A program belépési pontja — ezt kell futtatni a program
elindításához:

    python main.py

FONTOS: a programot a projekt GYÖKERÉBŐL kell futtatni (abból a
mappából, ahol ez a main.py fájl is van), mert:
  1. a wordpress/config.py a ".env/secrets" relatív útvonalon
     keresi a bejelentkezési adatokat (lásd ott a részletes
     magyarázatot),
  2. az "from ui.main_window import MainWindow" és hasonló
     importok is a projekt gyökeréhez képest működnek.
"""

import os
import sys


# ============================================================
# KRITIKUS JAVÍTÁS (2026.07.28) — EZ MUSZÁJ A FÁJL LEGELEJÉN,
# MINDEN EGYÉB IMPORT ELŐTT MARADJON!
# ============================================================
#
# Amikor a programot a build_exe.bat "--windowed" kapcsolóval
# csomagolja .exe-vé, Windows-on a program NEM kap saját konzol-
# ablakot — emiatt a sys.stdout és sys.stderr egyszerűen None
# lesz (nem egy "csendes" stream, hanem TÉNYLEGESEN None).
#
# Ha EZUTÁN bármelyik könyvtár (akár a mi kódunk, akár egy
# függőség, pl. a "requests"/"urllib3" egy figyelmeztetése)
# megpróbál akár csak egyetlen sort is kiírni ide (print(), egy
# figyelmeztetés, stb.), az egy "AttributeError: 'NoneType'
# object has no attribute 'write'" hibát dob — ÉS EZ A HIBA NEM
# a "windowed" mód hiánya miatt LÁTHATATLAN, hanem egy TELJESEN
# ÚJ, el nem kapott kivétel, ami bárhol a programban
# megszakíthatja a futást, csendben, nyom nélkül.
#
# (Pontosan ez okozta azt a jelenséget, hogy a validáció közben,
# egy hálózati hívás során a program "csendben" leállt a
# becsomagolt .exe-ben, miközben "python main.py"-jal és a
# konzolos debug-buildben minden rendben működött — ott ugyanis
# LÉTEZIK egy valódi konzol, tehát sys.stdout/sys.stderr nem
# None.)
#
# A MEGOLDÁS: ha stdout/stderr None (vagyis nincs konzol), egy
# "semmit nem csináló" (null-eszközre irányított) stream-mel
# helyettesítjük őket — így bármi, ami megpróbál ide írni,
# egyszerűen nem csinál semmit, ahelyett hogy hibát dobna.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")

if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


# minden PySide6-os (Qt-alapú) alkalmazásnak pontosan EGY
# QApplication példányra van szüksége, ez fogja össze az egész
# grafikus felület eseménykezelését (gombnyomások, ablak
# újrarajzolása, stb.)
app = QApplication(sys.argv)

# létrehozzuk és megjelenítjük a fő ablakot (lásd
# ui/main_window.py — itt történik a tényleges munka: ODT
# betöltése, metaadat-előnézet, validáció, poszt létrehozása)
window = MainWindow()
window.show()

# elindítjuk a Qt "eseményhurkot" — a program innentől a
# felhasználói interakciókra (gombnyomások, stb.) reagál, egészen
# az ablak bezárásáig
app.exec()
