"""Verificador e instalador idempotente de los ganchos mínimos en juego/app.py y setup_cx.py.

Pensado para sobrevivir a futuras actualizaciones de Puerto Bravo:
    .venv\\Scripts\\python.exe -m trampas.instalar_gancho --verificar
    .venv\\Scripts\\python.exe -m trampas.instalar_gancho --instalar
"""
from __future__ import annotations

import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_APP = os.path.join(RAIZ, "juego", "app.py")
RUTA_SETUP = os.path.join(RAIZ, "setup_cx.py")

MARCA_INICIO = "_puente_trampas.iniciar(self)"
MARCA_PASO = "_puente_trampas.atender()"
MARCA_CERRAR = "_puente_trampas.detener()"


def verificar(raiz: str | None = None) -> list[str]:
    """Devuelve una lista de ganchos faltantes (vacía si todo está instalado)."""
    base = raiz or RAIZ
    app_path = os.path.join(base, "juego", "app.py")
    setup_path = os.path.join(base, "setup_cx.py")
    faltan: list[str] = []

    with open(app_path, encoding="utf-8") as f:
        app_src = f.read()
    if MARCA_INICIO not in app_src:
        faltan.append("juego/app.py: falta el gancho de inicio en App.__init__")
    if MARCA_PASO not in app_src:
        faltan.append("juego/app.py: falta el gancho de atención en App.paso")
    if MARCA_CERRAR not in app_src:
        faltan.append("juego/app.py: falta el gancho de cierre en App.cerrar_todo")

    with open(setup_path, encoding="utf-8") as f:
        setup_src = f.read()
    if '"trampas"' not in setup_src and "'trampas'" not in setup_src:
        faltan.append("setup_cx.py: falta el paquete 'trampas' en opciones['packages']")
    if "MenuTrampas.exe" not in setup_src:
        faltan.append("setup_cx.py: falta Executable('trampas_gui.py', ..., target_name='MenuTrampas.exe')")
    return faltan


def instalar(raiz: str | None = None) -> list[str]:
    """Inserta de forma idempotente los ganchos que falten. Devuelve los cambios aplicados."""
    base = raiz or RAIZ
    app_path = os.path.join(base, "juego", "app.py")
    setup_path = os.path.join(base, "setup_cx.py")
    cambios: list[str] = []

    with open(app_path, encoding="utf-8") as f:
        app_src = f.read()
    original_app = app_src

    if MARCA_INICIO not in app_src:
        patron_init = re.compile(r"(def __init__\(self.*?\n)(.*?)(\n    # -+\s*audio)", re.DOTALL)
        m = patron_init.search(app_src)
        if not m:
            raise RuntimeError("No se encontró el final de App.__init__ en juego/app.py")
        bloque = (
            "\n        try:\n"
            "            from trampas import puente as _puente_trampas\n"
            "            _puente_trampas.iniciar(self)\n"
            "        except Exception:\n"
            "            pass"
        )
        app_src = app_src[:m.end(2)] + bloque + app_src[m.end(2):]
        cambios.append("juego/app.py: añadido gancho en App.__init__")

    if MARCA_PASO not in app_src:
        patron_paso = re.compile(r"(def paso\(self,\s*dt\):.*?\n\s*self\.mez\.actualizar\(\))", re.DOTALL)
        m = patron_paso.search(app_src)
        if not m:
            raise RuntimeError("No se encontró self.mez.actualizar() en App.paso")
        bloque = (
            "\n        if getattr(self, \"_puente_trampas\", None) is not None:\n"
            "            self._puente_trampas.atender()"
        )
        app_src = app_src[:m.end(1)] + bloque + app_src[m.end(1):]
        cambios.append("juego/app.py: añadido gancho en App.paso")

    if MARCA_CERRAR not in app_src:
        patron_cerrar = re.compile(r"(    def cerrar_todo\(self\):\n)")
        m = patron_cerrar.search(app_src)
        if not m:
            raise RuntimeError("No se encontró App.cerrar_todo en juego/app.py")
        bloque = (
            "        try:\n"
            "            if getattr(self, \"_puente_trampas\", None) is not None:\n"
            "                self._puente_trampas.detener()\n"
            "                self._puente_trampas = None\n"
            "        except Exception:\n"
            "            pass\n"
        )
        app_src = app_src[:m.end(1)] + bloque + app_src[m.end(1):]
        cambios.append("juego/app.py: añadido gancho en App.cerrar_todo")

    if app_src != original_app:
        with open(app_path, "w", encoding="utf-8") as f:
            f.write(app_src)

    with open(setup_path, encoding="utf-8") as f:
        setup_src = f.read()
    original_setup = setup_src

    if '"trampas"' not in setup_src and "'trampas'" not in setup_src:
        setup_src, n = re.subn(
            r'("panel_servidor"\s*,)',
            r'\1 "trampas",',
            setup_src,
            count=1,
        )
        if n:
            cambios.append("setup_cx.py: añadido paquete 'trampas'")

    if "MenuTrampas.exe" not in setup_src:
        setup_src, n = re.subn(
            r'(Executable\("servidor_main\.py"[^)]*\))',
            r'\1,\n                 Executable("trampas_gui.py", base="gui", target_name="MenuTrampas.exe")',
            setup_src,
            count=1,
        )
        if n:
            cambios.append("setup_cx.py: añadido Executable MenuTrampas.exe")

    if setup_src != original_setup:
        with open(setup_path, "w", encoding="utf-8") as f:
            f.write(setup_src)

    return cambios


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--instalar" in args:
        cambios = instalar()
        if cambios:
            print("Cambios aplicados:")
            for c in cambios:
                print(" -", c)
        else:
            print("Todos los ganchos ya estaban instalados.")
        faltan = verificar()
        if faltan:
            for f in faltan:
                print("ERROR:", f)
            return 1
        return 0

    faltan = verificar()
    if faltan:
        print("Faltan ganchos:")
        for f in faltan:
            print(" -", f)
        return 1
    print("Todos los ganchos están correctamente instalados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
