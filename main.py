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

import sys

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
