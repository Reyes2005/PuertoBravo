"""Publica la lista de la Comunidad de jugadores, para que el juego la ponga al día sin esperar a una versión nueva.

    .venv\\Scripts\\python.exe herramientas\\publicar_comunidad.py            a la carpeta del servidor (publicar_destino.txt)
    .venv\\Scripts\\python.exe herramientas\\publicar_comunidad.py prueba     a su subcarpeta de pruebas
    .venv\\Scripts\\python.exe herramientas\\publicar_comunidad.py github     además, a la publicación «componentes» de GitHub
    .venv\\Scripts\\python.exe herramientas\\publicar_comunidad.py ver        solo dice lo que publicaría

Sale de data\\datos\\comunidad.json, el mismo que trae el juego. Para que el juego la use, «revision» tiene que ser más
alta que la de la lista que ya tiene: súbela en cada cambio. Va en comunidad.json, junto a componentes.json en cada
fuente, firmada con la misma clave que las versiones del juego, y lleva la traducción de sus textos a cada idioma
sacada de los catálogos (data\\idiomas\\<código>\\textos.json): un texto nuevo sale traducido aunque el catálogo del
juego todavía no lo tenga. Si un texto aún no está en los catálogos, sale en español hasta que se traduzca y se publique
otra vez. Lo lee juego/comunidad.py, desde la 1.7.6.
"""
import json
import os
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))

from juego import actualizador as A, componentes as C, i18n  # noqa: E402
import publicar as P  # noqa: E402

ORIGEN = os.path.join(RAIZ, "data", "datos", "comunidad.json")
SALIDA = os.path.join(RAIZ, "dist", "componentes")


def _textos(obj, clave=None):
    """Los textos de la lista que se traducen: todos menos los identificadores y las claves que empiezan por _."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("_"):
                continue
            if isinstance(v, str):
                if not i18n.es_identificador(v, k):
                    yield v
            else:
                yield from _textos(v, k)
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, str):
                if not i18n.es_identificador(v, clave):
                    yield v
            else:
                yield from _textos(v, clave)


def construir():
    """La lista para publicar, sin firmar: {formato, revision, datos, textos: {código: {español: traducción}}}."""
    with open(ORIGEN, encoding="utf-8") as f:
        datos = json.load(f)
    datos = {k: v for k, v in datos.items() if not k.startswith("_")}
    propios = sorted(set(_textos(datos)))
    textos = {}
    carpeta = os.path.join(RAIZ, "data", "idiomas")
    for cod in sorted(os.listdir(carpeta)):
        ruta = os.path.join(carpeta, cod, "textos.json")
        if not os.path.isfile(ruta):
            continue
        with open(ruta, encoding="utf-8") as f:
            cat = json.load(f).get("textos", {})
        textos[cod] = {t: cat[t] for t in propios if isinstance(cat.get(t), str) and cat[t]}
    return {"formato": 1, "revision": int(datos.get("revision", 0)), "datos": datos, "textos": textos}


def main(args):
    doc = construir()
    frases = {t for t in _textos(doc["datos"]) if " " in t and "://" not in t and t != t.title()}       # no las direcciones ni los nombres
    faltan = {cod: sorted(t for t in frases if t not in tr) for cod, tr in doc["textos"].items()}
    print(f"Lista de la comunidad, revisión {doc['revision']}: {sum(len(s.get('enlaces', [])) for s in doc['datos'].get('secciones', []))} sitios. "
          f"Textos sin traducir por idioma: {faltan}.")
    if "ver" in args:
        return 0
    doc = P.firmar(doc, P.leer_privada())
    A.verificar_firma(dict(doc))
    os.makedirs(SALIDA, exist_ok=True)
    local = os.path.join(SALIDA, "comunidad.json")                 # el nombre que busca juego/comunidad.py (ARCHIVO)
    with open(local, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    with open(os.path.join(RAIZ, "publicar_destino.txt"), encoding="utf-8-sig") as f:
        destino = f.read().strip().strip('"')
    carpeta = os.path.join(destino, *([P.SUB_PRUEBAS] if "prueba" in args else []), C.CARPETA_WEB)
    os.makedirs(carpeta, exist_ok=True)
    shutil.copy2(local, os.path.join(carpeta, os.path.basename(local)))
    print(f"Publicada en {carpeta}.")
    if "github" in args and "prueba" not in args:
        subprocess.run(["gh", "release", "upload", C.TAG_GITHUB, "--repo", A.REPOSITORIO_GITHUB, "--clobber", local], check=True)
        print("Subida a GitHub, a la publicación «componentes».")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
