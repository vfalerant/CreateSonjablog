@echo off
REM =============================================================
REM CreateSonjaBlog - DEBUG build (konzolos mod)
REM =============================================================
REM Ugyanaz, mint a build_exe.bat, DE a "--windowed" kapcsolo
REM NELKUL - igy amikor futtatod az elkeszult exe-t, egy fekete
REM konzol-ablak IS megnyilik mellette, es abban lathato barmilyen
REM Python hibauzenet/traceback, amit a "csendes" (--windowed)
REM verzio elnyelne.
REM
REM CSAK HIBAKERESESRE hasznald - ha megvan a hiba oka, allj vissza
REM a rendes build_exe.bat-ra (windowed mod), hogy a feleseged ne
REM lasson feleslegesen egy fekete ablakot a program mellett.
REM =============================================================

echo.
echo === EXE epitese DEBUG (konzolos) modban ===
python -m PyInstaller --name CreateSonjaBlogDebug --onefile main.py

echo.
echo =============================================================
echo KESZ! Futtasd a dist\CreateSonjaBlogDebug.exe -t.
echo A megnyilo fekete konzol-ablakban lathatod majd a pontos
echo hibauzenetet, ha valami elszall.
echo =============================================================
echo.
pause
