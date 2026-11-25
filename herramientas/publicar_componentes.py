"""Publica los componentes: idiomas, voces, documentación, packs de sonidos y mods, aparte de las versiones del juego.

    .venv\\Scripts\\python.exe herramientas\\publicar_componentes.py              a la carpeta del servidor (publicar_destino.txt)
    .venv\\Scripts\\python.exe herramientas\\publicar_componentes.py prueba       a su subcarpeta de pruebas
    .venv\\Scripts\\python.exe herramientas\\publicar_componentes.py github       además, sube los ZIP y el manifiesto a la
                                                                               publicación «componentes» de GitHub (con gh)
    .venv\\Scripts\\python.exe herramientas\\publicar_componentes.py lista        solo dice qué componentes hay y cuáles han cambiado
    .venv\\Scripts\\python.exe herramientas\\publicar_componentes.py de-serie     apunta en la compilación (data\\componentes_de_serie.json)
                                                                               qué versión de cada componente trae el juego: así
                                                                               no avisa de componentes nuevos que ya tiene. Lo
                                                                               hace compilar.bat

Los componentes salen de la compilación (dist\\PuertoBravo), que es lo que el juego lee de verdad:
- idioma-<código>: data\\idiomas\\<código> y los documentos data\\docs\\*_<código>.html. El español no: viene con el juego.
- voces-<código>: las voces de las escenas de ese idioma, data\\voces\\<historia>_<código> (en la compilación viajan en
  data\\datos\\voces_puente; en el componente van ya a data\\voces), y las del generador del personaje propio,
  data\\phonon\\voces_<código> con su reparto_<código>.json.
- docs-es: los documentos en español, por si se corrigen sin sacar versión.
- sonidos-<pack>: cada pack de data\\sonidos, menos el de serie.
- mod-<nombre>: cada mod de data\\mods.
- Los de componentes_extra\\<carpeta>\\componente.json: lo que no viene con el juego y solo llega como componente (un mod
  con su traducción y sus voces, por ejemplo). Cada uno dice sus archivos y adónde van; un mod se protege como los del
  juego. No entran en data\\componentes_de_serie.json, porque el juego no los trae. Si la compilación ya trae un mod con
  el mismo identificador (El Diablo, que llegó como componente para la 1.7.3 y viene de serie desde la 1.7.4), vale
  el de la compilación y el de componentes_extra no se publica.
Cada uno lleva su versión, que solo sube si su contenido ha cambiado desde la última publicación. El manifiesto,
componentes.json, va firmado con la misma clave que las versiones del juego.

Cada componente pide la versión del juego compilada (requiere_juego). Para arreglar un componente en versiones ya
repartidas, herramientas\\componentes_requiere.json puede pedir una más antigua, solo mientras la compilación sea la
que dice (con_la_version): al compilar la siguiente ya no vale y hay que decidirlo otra vez. Lo que vaya así tiene
que servir en todas esas versiones (para un idioma, el catálogo de herramientas\\catalogo_union.py).
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))

from juego import VERSION, actualizador as A, componentes as C, ed25519   # noqa: E402
import publicar as P                                                      # noqa: E402

DIST = os.path.join(RAIZ, "dist", "PuertoBravo")
EXTRA = os.path.join(RAIZ, "componentes_extra")
ORIGEN = {}          # de los componentes extra: ruta en el componente -> archivo de donde sale
META = {}            # de los componentes extra: nombre y descripción en cada idioma
EXTRAS = set()       # sus identificadores: el juego no los trae de serie
SALIDA = os.path.join(RAIZ, "dist", "componentes")
ESTADO = os.path.join(RAIZ, "herramientas", "componentes_publicados.json")      # versión y huella de cada uno
REQUIERE = os.path.join(RAIZ, "herramientas", "componentes_requiere.json")       # los que valen desde una versión anterior


def requiere(cid):
    """La versión del juego que pide un componente: la compilada, salvo que componentes_requiere.json diga otra para ella."""
    try:
        d = json.load(open(REQUIERE, encoding="utf-8")).get(cid) or {}
    except (OSError, ValueError, AttributeError):
        d = {}
    if isinstance(d, dict) and d.get("con_la_version") == VERSION and d.get("requiere_juego"):
        return str(d["requiere_juego"])
    return VERSION


def _archivos(base, *prefijos, excluir=()):
    r = []
    for pre in prefijos:
        carpeta = os.path.join(base, *pre.split("/"))
        if os.path.isfile(carpeta):
            r.append(pre)
            continue
        for raiz, dirs, archivos in os.walk(carpeta):
            dirs[:] = sorted(d for d in dirs if d not in excluir and d != "__pycache__")
            for a in sorted(archivos):
                rel = os.path.relpath(os.path.join(raiz, a), base).replace("\\", "/")
                r.append(rel)
    return r


def definir(base=DIST):
    """Los componentes que hay en la compilación: [(id, tipo, nombre, [rutas relativas])]."""
    from juego import i18n
    r = []
    idiomas = os.path.join(base, "data", "idiomas")
    docs = os.path.join(base, "data", "docs")
    if os.path.isdir(idiomas):
        for cod in sorted(os.listdir(idiomas)):
            if not os.path.isdir(os.path.join(idiomas, cod)):
                continue
            nombre = i18n.NOMBRES.get(cod, cod)
            arch = _archivos(base, f"data/idiomas/{cod}")
            arch += [f"data/docs/{a}" for a in sorted(os.listdir(docs)) if a.endswith(f"_{cod}.html")] if os.path.isdir(docs) else []
            r.append((f"idioma-{cod}", "idioma", nombre, arch))
    for cod in sorted({"es"} | (set(os.listdir(idiomas)) if os.path.isdir(idiomas) else set())):
        voces = []
        for raiz_voces in ("data/datos/voces_puente", "data/voces"):
            carpeta = os.path.join(base, *raiz_voces.split("/"))
            if os.path.isdir(carpeta):
                for h in sorted(os.listdir(carpeta)):
                    if h.endswith("_" + cod) and os.path.isdir(os.path.join(carpeta, h)):
                        voces += _archivos(base, f"{raiz_voces}/{h}")
        if cod != "es":
            voces += [a for a in _archivos(base, f"data/phonon/voces_{cod}", f"data/phonon/reparto_{cod}.json") if os.path.exists(os.path.join(base, *a.split("/")))]
        if voces:
            r.append((f"voces-{cod}", "voces", f"{i18n.NOMBRES.get(cod, cod)}: voces", voces))
    if os.path.isdir(docs):
        r.append(("docs-es", "documentacion", "Documentación en español", [f"data/docs/{a}" for a in sorted(os.listdir(docs)) if a.endswith("_es.html")]))
    sonidos = os.path.join(base, "data", "sonidos")
    if os.path.isdir(sonidos):
        for pack in sorted(os.listdir(sonidos)):
            if pack != "por_defecto" and os.path.isdir(os.path.join(sonidos, pack)):
                r.append((f"sonidos-{pack}", "sonidos", f"Pack de sonidos {pack}", _archivos(base, f"data/sonidos/{pack}")))
    mods = os.path.join(base, "data", "mods")
    if os.path.isdir(mods):
        for a in sorted(os.listdir(mods)):
            if a.endswith((".pbm", ".json")):
                r.append((f"mod-{os.path.splitext(a)[0]}", "mod", f"Mod {os.path.splitext(a)[0]}", [f"data/mods/{a}"]))
    return [x for x in r if x[3]]


def destino_de(rel):
    """Dónde va un archivo de la compilación al instalar el componente: las voces que en la compilación viajan en el
    puente van a data/voces; lo demás, al mismo sitio."""
    return "data/voces/" + rel[len("data/datos/voces_puente/"):] if rel.startswith("data/datos/voces_puente/") else rel


def _fuente(base, rel):
    return ORIGEN.get(rel) or os.path.join(base, *rel.split("/"))


def _proteger(origen, carpeta):
    """El mod protegido, como lo deja el editor. Solo se rehace si cambia el original: así su versión no sube sin motivo."""
    from juego import cifrado
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, os.path.splitext(os.path.basename(origen))[0] + ".pbm")
    sello = destino + ".origen"
    h = hashlib.sha256(open(origen, "rb").read()).hexdigest()
    if not os.path.exists(destino) or not os.path.exists(sello) or open(sello, encoding="utf-8").read().strip() != h:
        cifrado.escribir_json(destino, json.load(open(origen, encoding="utf-8")), cifrado=True)
        open(sello, "w", encoding="utf-8").write(h)
    return destino


def definir_extra():
    """Los componentes de componentes_extra: [(id, tipo, nombre, [rutas en el componente])]."""
    r = []
    if not os.path.isdir(EXTRA):
        return r
    for carpeta in sorted(os.listdir(EXTRA)):
        spec_ruta = os.path.join(EXTRA, carpeta, "componente.json")
        if not os.path.exists(spec_ruta):
            continue
        base = os.path.join(EXTRA, carpeta)
        spec = json.load(open(spec_ruta, encoding="utf-8"))
        arch = []
        for a in spec["archivos"]:
            if "carpeta" in a:
                origen = os.path.normpath(os.path.join(base, a["carpeta"]))
                if not os.path.isdir(origen):
                    raise SystemExit(f"{spec['id']}: falta la carpeta {origen}")
                for n in sorted(os.listdir(origen)):
                    rel = a["destino"].rstrip("/") + "/" + n
                    ORIGEN[rel] = os.path.join(origen, n)
                    arch.append(rel)
                continue
            origen = os.path.normpath(os.path.join(base, a["origen"]))
            if not os.path.exists(origen):
                raise SystemExit(f"{spec['id']}: falta {origen}")
            if a.get("proteger"):
                origen = _proteger(origen, os.path.join(base, "_paquete"))
            ORIGEN[a["destino"]] = origen
            arch.append(a["destino"])
        META[spec["id"]] = {k: spec[k] for k in ("nombres", "descripcion", "descripciones") if k in spec}
        EXTRAS.add(spec["id"])
        r.append((spec["id"], spec["tipo"], spec.get("nombre", spec["id"]), arch))
    return r


def idiomas_del_menu(base=DIST):
    """Los idiomas en los que se escriben el nombre y la descripción de cada componente: el español y los que tienen catálogo."""
    carpeta = os.path.join(base, "data", "idiomas")
    otros = sorted(c for c in os.listdir(carpeta) if os.path.isfile(os.path.join(carpeta, c, "textos.json"))) if os.path.isdir(carpeta) else []
    return ["es"] + [c for c in otros if c != "es"]


def _info_mod(ident):
    """El nombre y la descripción de un mod del juego, de su archivo legible del proyecto (en la compilación va protegido)."""
    for ruta in (os.path.join(RAIZ, "data", "mods", ident + ".json"), os.path.join(DIST, "data", "mods", ident + ".json")):
        try:
            info = json.load(open(ruta, encoding="utf-8")).get("info") or {}
            return str(info.get("nombre") or ""), str(info.get("descripcion") or "")
        except (OSError, ValueError, AttributeError):
            continue
    return "", ""


def presentar(cid, tipo, base=DIST):
    """Nombre y descripción de un componente del juego en cada idioma, para el manifiesto: {"nombre", "nombres",
    "descripcion", "descripciones"}. Un juego anterior los dice tal como llegan, en su idioma, sin saber nada más."""
    from juego import componentes as C2, i18n
    cod = cid.split("-", 1)[1]
    nombres, descripciones = {}, {}
    for lengua in idiomas_del_menu(base):
        plantilla = i18n.en_idioma(C2.DESCRIPCIONES.get(tipo, ""), lengua)
        if tipo in ("idioma", "voces", "documentacion"):
            idioma = "es" if cid == "docs-es" else cod
            nombre = i18n.nombre_en(idioma, lengua)
            desc = plantilla.format(idioma=i18n.idioma_en(idioma, lengua))
        elif tipo == "sonidos":
            pack = {}
            for raiz in (base, RAIZ):                    # la compilación protege los .json: si no, el del proyecto
                try:
                    pack = json.load(open(os.path.join(raiz, "data", "sonidos", cod, "pack.json"), encoding="utf-8"))
                    break
                except (OSError, ValueError):
                    continue
            nombre = i18n.en_idioma(str(pack.get("nombre") or cod), lengua)
            desc = plantilla.format(descripcion=i18n.en_idioma(str(pack.get("descripcion") or ""), lengua)).strip()
        elif tipo == "mod":
            n, d = _info_mod(cod)
            nombre = i18n.en_idioma(n or cod.replace("_", " "), lengua)
            desc = plantilla.format(descripcion=i18n.en_idioma(d, lengua)).strip()
        else:
            continue
        nombres[lengua], descripciones[lengua] = nombre, desc
    if not nombres:
        return {}
    return {"nombre": nombres["es"], "nombres": nombres, "descripcion": descripciones["es"], "descripciones": descripciones}


def huella(base, archivos):
    h = hashlib.sha256()
    for a in archivos:
        h.update(a.encode("utf-8"))
        with open(_fuente(base, a), "rb") as f:
            for b in iter(lambda: f.read(1024 * 1024), b""):
                h.update(b)
    return h.hexdigest()


def main(args):
    if not os.path.isdir(DIST):
        raise SystemExit("No hay compilación en dist\\PuertoBravo. Compila primero.")
    estado = json.load(open(ESTADO, encoding="utf-8")) if os.path.exists(ESTADO) else {}
    comps = definir()
    de_serie = {c[0] for c in comps}
    for extra in definir_extra():
        if extra[0] in de_serie:                     # la compilación ya lo trae (El Diablo desde la 1.7.4): vale el de serie
            EXTRAS.discard(extra[0])
            print(f"{extra[0]}: viene con el juego; se publica el de la compilación, con sus voces y sus textos en los de cada idioma.")
            continue
        comps.append(extra)
    cambios = []
    for cid, tipo, nombre, arch in comps:
        hu = huella(DIST, arch)
        antes = estado.get(cid, {})
        version = int(antes.get("version", 0)) + (0 if antes.get("huella") == hu else 1)
        cambios.append((cid, tipo, nombre, arch, hu, version, antes.get("huella") != hu, antes.get("archivos", [])))
    if "de-serie" in args:                                            # la misma versión que tendrá cada uno al publicarlo
        with open(os.path.join(DIST, "data", C.ARCHIVO_SERIE), "w", encoding="utf-8") as f:
            json.dump({"de_serie": {cid: v for cid, _t, _n, _a, _h, v, _x, _y in cambios if cid not in EXTRAS}}, f, ensure_ascii=False, indent=1)
        print(f"Componentes que trae el juego apuntados: {sum(1 for c in cambios if c[0] not in EXTRAS)}.")
        return 0
    if "lista" in args:
        for cid, tipo, nombre, arch, hu, v, nuevo, _ in cambios:
            print(f"{cid}: {tipo}, {len(arch)} archivos, versión {v}{' (cambia)' if nuevo else ''}, pide la {requiere(cid)}")
        return 0
    prueba = "prueba" in args
    destino = None
    with open(os.path.join(RAIZ, "publicar_destino.txt"), encoding="utf-8-sig") as f:
        destino = f.read().strip()
    carpeta = os.path.join(destino, *( [P.SUB_PRUEBAS] if prueba else []), C.CARPETA_WEB)
    os.makedirs(carpeta, exist_ok=True)
    os.makedirs(SALIDA, exist_ok=True)
    base_web = A.URL_SERVIDOR.rsplit("/", 1)[0] + "/" + (P.SUB_PRUEBAS + "/" if prueba else "") + C.CARPETA_WEB + "/"
    lista = []
    for cid, tipo, nombre, arch, hu, version, nuevo, viejos in cambios:
        archivo = f"{cid}_{version}.zip"
        zruta = os.path.join(SALIDA, archivo)
        if not os.path.exists(zruta) or nuevo:
            with zipfile.ZipFile(zruta, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
                for a in arch:
                    z.write(_fuente(DIST, a), destino_de(a))
        sha = A.sha256_de(zruta)
        tam = os.path.getsize(zruta)
        destino_zip = os.path.join(carpeta, archivo)
        if not os.path.exists(destino_zip) or os.path.getsize(destino_zip) != tam:
            import shutil
            shutil.copy2(zruta, destino_zip)
        lista.append({"id": cid, "tipo": tipo, "nombre": nombre, "version": version, "file": archivo, "sha256": sha, "size": tam,
                      "url": base_web + archivo, "espejos": {"github": f"https://github.com/{A.REPOSITORIO_GITHUB}/releases/download/{C.TAG_GITHUB}/{archivo}"},
                      "requiere_juego": requiere(cid), "borra": sorted({destino_de(a) for a in set(viejos) - set(arch)}), **(META.get(cid) or presentar(cid, tipo))})
        estado[cid] = {"version": version, "huella": hu, "archivos": arch}
    semilla = P.leer_privada()
    manifiesto = P.firmar({"formato": 1, "componentes": lista}, semilla)
    A.verificar_firma(dict(manifiesto))
    ruta_m = os.path.join(carpeta, C.ARCHIVO)
    with open(ruta_m, "w", encoding="utf-8") as f:
        json.dump(manifiesto, f, ensure_ascii=False, indent=1)
    with open(os.path.join(SALIDA, C.ARCHIVO), "w", encoding="utf-8") as f:
        json.dump(manifiesto, f, ensure_ascii=False, indent=1)
    if not prueba:
        with open(ESTADO, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=1)
    print(f"{len(lista)} componentes publicados en {carpeta}. Cambian: {sum(1 for x in cambios if x[6])}.")
    if "github" in args:
        subprocess.run(["gh", "release", "view", C.TAG_GITHUB, "--repo", A.REPOSITORIO_GITHUB], check=False, capture_output=True)
        subprocess.run(["gh", "release", "create", C.TAG_GITHUB, "--repo", A.REPOSITORIO_GITHUB, "--title", "Componentes", "--notes",
                        "Idiomas, voces, documentación, packs de sonidos y mods que el juego actualiza por su cuenta.", "--latest=false"], check=False, capture_output=True)
        archivos = [os.path.join(SALIDA, x["file"]) for x in lista] + [os.path.join(SALIDA, C.ARCHIVO)]
        subprocess.run(["gh", "release", "upload", C.TAG_GITHUB, "--repo", A.REPOSITORIO_GITHUB, "--clobber"] + archivos, check=True)
        print("Subidos a GitHub, a la publicación «componentes».")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
