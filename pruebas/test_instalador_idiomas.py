"""El instalador de las actualizaciones es el mismo en todos los idiomas (1.7.6).

En la 1.7.3, la 1.7.4 y la 1.7.5, las líneas del .bat que instala las actualizaciones iban en tr(), y el catálogo ruso las
traducía («@echo off» pasaba a ser «@эхо выключено», «goto fin» a «перейти к концу», «>nul» a «> ноль»). cmd.exe no
entendía nada, y en ruso el juego se cerraba sin actualizarse y sin volver a abrirse. Lo que se vigila aquí:

- con cualquier idioma del juego, el .bat sale idéntico, letra por letra, al que sale en español;
- ningún texto para traducir (traduccion/origen.json) es una orden de Windows;
- la herramienta que pone los tr() (herramientas/i18n/marcar.py) no envuelve nunca una línea de .bat.
"""
import json
import os
import sys

from juego import actualizador as A, i18n

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas", "i18n"))
import marcar  # noqa: E402


def _idiomas():
    carpeta = os.path.join(RAIZ, "data", "idiomas")
    return sorted(c for c in os.listdir(carpeta) if os.path.isfile(os.path.join(carpeta, c, "textos.json")))


def _bat(tmp_path, cod):
    prog = tmp_path / "prog"
    nueva = tmp_path / "actualizacion" / "nueva"
    prog.mkdir(parents=True, exist_ok=True)
    nueva.mkdir(parents=True, exist_ok=True)
    (nueva / "PuertoBravo.exe").write_bytes(b"exe")
    i18n.cargar(cod)
    ruta = A.escribir_instalador(str(nueva), str(prog), pid=4321, version="9.9.9")
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def test_el_bat_es_el_mismo_en_todos_los_idiomas(tmp_path):
    antes = i18n.actual()
    try:
        espanol = _bat(tmp_path, "es")
        assert espanol.startswith("@echo off") and "goto fin" in espanol and '(goto) 2>nul & del "%~f0"' in espanol
        for cod in _idiomas():
            assert _bat(tmp_path, cod) == espanol, f"El instalador sale distinto con el idioma {cod}: alguna orden de Windows va en tr()"
    finally:
        i18n.cargar(antes)


def test_ninguna_orden_de_windows_se_traduce():
    origen = json.load(open(os.path.join(RAIZ, "traduccion", "origen.json"), encoding="utf-8"))
    ordenes = sorted(k for k in origen if marcar.es_orden_windows(k))
    assert not ordenes, f"Órdenes de Windows en tr(): {ordenes[:10]}"


def test_marcar_no_envuelve_las_lineas_de_un_bat():
    for orden in ("@echo off", "setlocal", "set PASO={nombre}", "set /a N+=1", "if %RC% geq 8 goto fallo", "goto fin", ":espera",
                  '{ping} -n 2 127.0.0.1 >nul', '>>"%REG%" echo {texto}', 'rmdir /s /q "%NUEVA%"', '(goto) 2>nul & del "%~f0"',
                  'set "APP={programa}"', "if errorlevel 1 goto programas", "if not exist \"{si}\" goto {salto}"):
        assert marcar.es_orden_windows(orden) and not marcar.es_texto(orden), orden
    for texto in ("Del 1 al 9", "Set de herramientas", "Echo de menos", "El 50% de la gente", "Entra %s%s. Hay %d.", "Goto",
                  "Actualizando Puerto Bravo. No cierres esta ventana."):
        assert not marcar.es_orden_windows(texto), texto
