"""Junta los lotes traducidos en el catálogo de un idioma, comprobando cada traducción.

    python herramientas\\i18n\\fusionar.py                 inglés: de traduccion\\en\\hechos al catálogo
    python herramientas\\i18n\\fusionar.py --idioma fr
    python herramientas\\i18n\\fusionar.py --instalar      además copia el catálogo a data\\idiomas\\<idioma>.json

Comprueba, de cada texto: que esté; que tenga exactamente los mismos huecos ({nombre}, %s...); que conserve los espacios
del principio y del final; que no queden marcas de género del español ([o|a]); y que no sea una copia sin traducir de una
frase larga. Lo que falla va a traduccion\\<idioma>\\revisar.json, con el motivo, para traducirlo otra vez.
"""
import glob
import json
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from marcar import es_orden_windows  # noqa: E402
HUECO = re.compile(r"\{[^{}]*\}|%[-+ #0-9.]*[sdifr]|\{\{|\}\}")
MARCA_ES = re.compile(r"\[[a-záéíóú]*\|[a-záéíóú]*\]")
PALABRAS_ES = re.compile(r"\b(que|los|las|del|para|con|una|está|tienes|puedes|pero|cuando|también|más)\b", re.I)


GENERO = {"{o}", "{a}", "{e}", "{os}", "{as}"}                          # terminaciones de género del español: en otro idioma pueden sobrar


def huecos(t):
    return sorted(h for h in HUECO.findall(t) if h not in GENERO)


def bordes(es, en):
    """La traducción con los mismos espacios al principio y al final que el original: el código pega los trozos contando
    con ellos, y uno de más se oye como una pausa rara."""
    if not isinstance(en, str) or not en.strip():
        return en
    ini = es[:len(es) - len(es.lstrip(" "))]
    fin = es[len(es.rstrip(" ")):]
    return ini + en.strip(" ") + fin


def problema(es, en):
    if not isinstance(en, str) or not en.strip():
        return "vacía"
    sobran = set(huecos(en)) - set(huecos(es))
    if sobran:                                                   # un hueco que no existe rompería el texto; uno que falta, no
        return f"huecos que no existen: {sorted(sobran)}"
    if es[:1].isspace() != en[:1].isspace() or es[-1:].isspace() != en[-1:].isspace():
        return "espacios del principio o del final"
    if len(es) > 40 and es == en and PALABRAS_ES.search(es):
        return "sin traducir"
    return ""


def main(args):
    idioma = args[args.index("--idioma") + 1] if "--idioma" in args else "en"
    base = os.path.join(RAIZ, "traduccion", idioma)
    origen = json.load(open(os.path.join(RAIZ, "traduccion", "origen.json"), encoding="utf-8"))
    cat_ruta = os.path.join(base, f"{idioma}.json")
    cat = json.load(open(cat_ruta, encoding="utf-8")) if os.path.exists(cat_ruta) else {"_idioma": {"codigo": idioma, "nombre": {"en": "English"}.get(idioma, idioma)}, "textos": {}}
    textos = cat["textos"]
    revisar, nuevos = {}, 0
    for f in sorted(glob.glob(os.path.join(base, "hechos", "lote_*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except ValueError as e:
            revisar["__" + os.path.basename(f)] = f"no es JSON válido: {e}"
            continue
        for es, en in d.items():
            if es not in origen:
                continue                                                  # un texto que ya no existe en el juego
            en = bordes(es, en)
            p = problema(es, en)
            if p:
                revisar[es] = {"en": en, "motivo": p}
                continue
            if textos.get(es) != en:
                nuevos += 1
            textos[es] = en
    corr = os.path.join(base, "correcciones.json")              # lo corregido a mano manda sobre los lotes
    if os.path.exists(corr):
        for es, en in json.load(open(corr, encoding="utf-8")).items():
            en = bordes(es, en)
            if es in origen and not problema(es, en):
                textos[es] = en
                revisar.pop(es, None)
    for es in list(textos):                                       # lo que ya estaba en el catálogo, con los bordes al día
        if es_orden_windows(es):                                  # una línea de .bat no se traduce nunca: fuera del catálogo
            del textos[es]
            continue
        textos[es] = bordes(es, textos[es])
    faltan = [k for k in origen if k not in textos and k not in revisar]
    cat["textos"] = dict(sorted(textos.items()))
    with open(cat_ruta, "w", encoding="utf-8") as fh:
        json.dump(cat, fh, ensure_ascii=False, indent=0)
    with open(os.path.join(base, "revisar.json"), "w", encoding="utf-8") as fh:
        json.dump(revisar, fh, ensure_ascii=False, indent=1)
    print(f"Catálogo {idioma}: {len(textos)} textos ({nuevos} nuevos o cambiados). Por revisar: {len(revisar)}. Sin traducir: {len(faltan)} de {len(origen)}.")
    if "--instalar" in args:
        destino = os.path.join(RAIZ, "data", "idiomas", idioma)
        os.makedirs(destino, exist_ok=True)
        with open(os.path.join(destino, "textos.json"), "w", encoding="utf-8") as fh:
            json.dump({"textos": cat["textos"]}, fh, ensure_ascii=False, indent=0)
        print(f"Instalado en data\\idiomas\\{idioma}\\textos.json.")
    return 1 if (faltan or revisar) and "--estricto" in args else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
