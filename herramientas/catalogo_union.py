"""El catálogo de un idioma que vale a la vez para varias versiones publicadas del juego, para su componente.

    .venv\\Scripts\\python.exe herramientas\\catalogo_union.py ru 1.7.3            lo escribe en dist\\PuertoBravo
    .venv\\Scripts\\python.exe herramientas\\catalogo_union.py ru 1.7.3 --probar   solo dice lo que haría

Para qué: un componente de idioma solo se publica en una versión (la más alta), y el juego no lo ve si es más moderno que
él. Cuando hay que arreglar un idioma en versiones ya repartidas (en noviembre de 2026, el ruso de la 1.7.3 a la 1.7.5,
que traducía las órdenes del instalador de las actualizaciones y no dejaba actualizar), el componente tiene que llevar un
catálogo que sirva en todas ellas. Este junta:

1. los catálogos de ese idioma de cada versión desde la indicada (las etiquetas v<versión> del repositorio) y de cada
   componente ya publicado (dist\\componentes\\idioma-<código>_<n>.zip): así ninguna versión se queda sin sus textos;
2. el de la compilación (dist\\PuertoBravo), y encima el del repositorio, que es el más corregido: manda el más nuevo;
3. y quita lo que no se traduce nunca: las órdenes de Windows (las líneas de un .bat) y los textos del actualizador que
   dejaron de ir en tr() porque eran parte del instalador. Sin ellos, cada versión usa el texto en español, que es el
   que cmd.exe entiende.

Las claves de más no molestan: el juego busca cada texto por su frase exacta, y desde la 1.7.3 la carga de datos no
traduce los valores con forma de identificador. También copia el palabras.json del repositorio, que es el más completo.
"""
import glob
import json
import os
import re
import subprocess
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas", "i18n"))

from marcar import es_orden_windows  # noqa: E402

DIST = os.path.join(RAIZ, "dist", "PuertoBravo")


def _git(*args):
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True)
    return r.stdout.decode("utf-8") if r.returncode == 0 else None


def _clave_version(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def _etiquetas(desde):
    tags = [t.strip() for t in (_git("tag") or "").splitlines() if re.fullmatch(r"v\d+(\.\d+)+", t.strip())]
    return sorted((t for t in tags if _clave_version(t) >= _clave_version(desde)), key=_clave_version)


def _textos(texto):
    d = json.loads(texto)
    return {k: v for k, v in (d.get("textos", d) or {}).items() if isinstance(v, str) and v}


def fuentes(cod, desde):
    """[(nombre, {texto: traducción})], de la más vieja a la más nueva."""
    r = []
    for z in sorted(glob.glob(os.path.join(RAIZ, "dist", "componentes", f"idioma-{cod}_*.zip")),
                    key=lambda p: int(re.search(r"_(\d+)\.zip$", p).group(1))):
        with zipfile.ZipFile(z) as f:
            try:
                r.append((os.path.basename(z), _textos(f.read(f"data/idiomas/{cod}/textos.json").decode("utf-8"))))
            except KeyError:
                pass
    for t in _etiquetas(desde):
        texto = _git("show", f"{t}:data/idiomas/{cod}/textos.json")
        if texto:
            r.append((t, _textos(texto)))
    for nombre, ruta in (("compilación", os.path.join(DIST, "data", "idiomas", cod, "textos.json")),
                         ("repositorio", os.path.join(RAIZ, "data", "idiomas", cod, "textos.json"))):
        if os.path.isfile(ruta):
            r.append((nombre, _textos(open(ruta, encoding="utf-8").read())))
    return r


def del_instalador(desde):
    """Los textos que el actualizador de alguna versión publicada pasaba por tr() y ya no: eran del instalador (.bat)."""
    ahora = set(json.load(open(os.path.join(RAIZ, "traduccion", "origen.json"), encoding="utf-8")))
    r = set()
    for t in _etiquetas(desde):
        origen, codigo = _git("show", f"{t}:traduccion/origen.json"), _git("show", f"{t}:juego/actualizador.py")
        if not origen or not codigo:
            continue
        for k in set(json.loads(origen)) - ahora:
            if any(lit in codigo for lit in (json.dumps(k, ensure_ascii=False), repr(k))):
                r.add(k)
    return r


def unir(cod, desde):
    union, de_donde = {}, []
    for nombre, textos in fuentes(cod, desde):
        union.update(textos)
        de_donde.append(f"{nombre} ({len(textos)})")
    quitar = del_instalador(desde)
    fuera = sorted(k for k in union if k in quitar or es_orden_windows(k))
    for k in fuera:
        del union[k]
    return dict(sorted(union.items())), de_donde, fuera


def main(args):
    if len(args) < 2:
        print(__doc__)
        return 1
    cod, desde = args[0], args[1]
    union, de_donde, fuera = unir(cod, desde)
    print(f"Catálogo {cod} para la {desde} y siguientes: {len(union)} textos, de {', '.join(de_donde)}.")
    print(f"Fuera, por ser del instalador o una orden de Windows: {len(fuera)}.")
    if "--probar" in args:
        return 0
    destino = os.path.join(DIST, "data", "idiomas", cod)
    if not os.path.isdir(destino):
        raise SystemExit(f"No hay {destino}: compila primero.")
    with open(os.path.join(destino, "textos.json"), "w", encoding="utf-8") as f:
        json.dump({"textos": union}, f, ensure_ascii=False, indent=0)
    palabras = os.path.join(RAIZ, "data", "idiomas", cod, "palabras.json")
    if os.path.isfile(palabras):
        with open(palabras, encoding="utf-8") as f, open(os.path.join(destino, "palabras.json"), "w", encoding="utf-8") as g:
            g.write(f.read())
    print(f"Escrito en {destino}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
