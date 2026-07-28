@echo off
REM =============================================================
REM CreateSonjaBlog - Windows .exe build szkript
REM =============================================================
REM Ezt a fajlt a projekt GYOKEREBEN kell futtatni (ugyanabban a
REM mappaban, ahol a main.py is van), Windows Parancssorbol vagy
REM dupla-kattintassal.
REM
REM MIT CSINAL:
REM   1. Telepiti a requirements.txt fuggosegeit (PySide6, requests)
REM   2. Telepiti a PyInstaller csomagot (ha meg nincs meg)
REM   3. Legyartja az onefile .exe-t a dist/ mappaba
REM =============================================================

echo.
echo === 1. lepes: fuggosegek telepitese ===
pip install -r requirements.txt

echo.
echo === 2. lepes: PyInstaller telepitese ===
pip install pyinstaller

echo.
echo === 3. lepes: EXE epitese ===
REM A "python -m PyInstaller" format hasznalata (NEM a sima
REM "pyinstaller" parancs) azert fontos, mert ha a Python
REM "felhasznaloi" modban lett telepitve (pl. Microsoft Store-os
REM Python eseten ez az alapertelmezett), a "pyinstaller" onallo
REM parancs nincs rajta a Windows PATH-jan - a "python -m" viszont
REM mindig mukodik, mert kozvetlenul a Python ertelmezon keresztul
REM hivja meg a modult.
REM --onefile: egyetlen .exe fajl jon letre (nem egy mappa tele fajlokkal)
REM --windowed: nem nyilik meg mellette egy fekete parancssor-ablak
REM --name: az elkeszult exe neve (CreateSonjaBlog.exe)
python -m PyInstaller --name CreateSonjaBlog --onefile --windowed main.py

echo.
echo =============================================================
echo KESZ! Az elkeszult program itt talalhato:
echo   dist\CreateSonjaBlog.exe
echo.
echo FONTOS - MASOLD AT MELLE (ugyanabba a mappaba, ahol az exe
echo van) a kovetkezo mappakat is, mert az exe ezeket a SAJAT
echo mappajahoz kepest keresi majd:
echo   - .env\secrets       (WordPress belepesi adatok)
echo   - config\sorozatok.json   (sorozat-navigacio adatai)
echo.
echo A "state" mappa NEM kell elore - a program magatol letrehozza,
echo amikor eloszor osszekapcsol ket nyelvi valtozatot.
echo =============================================================
echo.
pause
