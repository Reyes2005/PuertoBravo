"""Los mods de data/mods: cuáles hay, cuáles están activos y activarlos o desactivarlos. Lo usan el juego (Opciones, Mods)
y el editor de mods (Control M). Un mod desactivado lleva «.desactivado» al final del nombre y el juego no lo carga.
Los cambios se notan al volver a abrir el juego: los datos se leen al arrancar."""
from .i18n import tr
import os

from . import rutas

EXT_MODS = (".json", rutas.EXT_MOD)
DESACTIVADO = ".desactivado"


def listar():
    """[(nombre de archivo, activo)] de la carpeta de mods, por orden alfabético."""
    out = []
    try:
        for f in sorted(os.listdir(rutas.MODS)):
            if f.lower().endswith(EXT_MODS):
                out.append((f, True))
            elif f.lower().endswith(tuple(e + DESACTIVADO for e in EXT_MODS)):
                out.append((f, False))
    except OSError:
        pass
    return out


def activar(nombre, activo):
    """Activa o desactiva un mod. Devuelve su nombre de archivo nuevo (el mismo si ya estaba así)."""
    origen = os.path.join(rutas.MODS, nombre)
    if activo and nombre.lower().endswith(DESACTIVADO):
        destino = origen[:-len(DESACTIVADO)]
    elif not activo and nombre.lower().endswith(EXT_MODS):
        destino = origen + DESACTIVADO
    else:
        return nombre
    os.replace(origen, destino)
    return os.path.basename(destino)


def ficha(nombre):
    """(nombre para decir, descripción) de un mod, de su apartado info, en el idioma del juego si está traducido. Si no
    se puede leer, el nombre del archivo sin extensión y una descripción vacía."""
    from . import i18n, mundo
    base = nombre[:-len(DESACTIVADO)] if nombre.lower().endswith(DESACTIVADO) else nombre
    simple = os.path.splitext(base)[0]
    try:
        info = mundo._leer_json(os.path.join(rutas.MODS, nombre)).get("info") or {}
    except Exception:
        info = {}
    titulo = str(info.get("nombre") or "").strip()
    desc = str(info.get("descripcion") or "").strip()
    # tr(), no en_idioma(): el catálogo del idioma del juego lleva también la traducción de los mods que llegan como
    # componente (data/idiomas/<código>/mods), que en_idioma() no mira.
    titulo, desc = i18n.tr(titulo), i18n.tr(desc)
    return (titulo or simple.replace("_", " ")), desc


def menu(app):
    """Opciones, Mods: la lista de mods con una casilla cada uno. Intro o las flechas izquierda y derecha lo activan o
    lo desactivan; se nota al volver a abrir el juego."""
    from .menus import Menu, Opcion
    cambiados = set()

    def alternar(nombre_actual):
        estado = {"nombre": nombre_actual}

        def f(d=None):
            activo = not estado["nombre"].lower().endswith(DESACTIVADO)
            try:
                estado["nombre"] = activar(estado["nombre"], not activo)
            except OSError:
                app.son("error")
                app.decir(tr("No se ha podido cambiar: el archivo está en uso o la carpeta es de solo lectura."), True)
                return
            cambiados.add(estado["nombre"])
            app.son("menu_ok")
            titulo = ficha(estado["nombre"])[0]
            app.decir((tr('{nombre}: activado.') if activo is False else tr('{nombre}: desactivado.')).format(nombre=titulo)
                      + " " + tr("Se nota al volver a abrir el juego."), True)
            m.refrescar(False)

        def texto():
            titulo = ficha(estado["nombre"])[0]
            activo = not estado["nombre"].lower().endswith(DESACTIVADO)
            return tr('{nombre}: {estado}').format(nombre=titulo, estado=tr("activado") if activo else tr("desactivado"))

        desc = ficha(nombre_actual)[1]
        ayuda = (desc + " " if desc else "") + tr("Intro, o las flechas izquierda y derecha, lo activan o lo desactivan. El cambio se nota al volver a abrir el juego.")
        return Opcion(texto, f, ajuste=lambda d: f(), ayuda=ayuda)

    def al_cerrar():
        if cambiados:
            app.decir(tr("Para que se noten los cambios en los mods, sal del juego y vuelve a abrirlo."), False)

    lista = listar()
    ops = [alternar(n) for n, _ in lista] if lista else [Opcion(tr("No hay ningún mod en la carpeta de mods"),
                                                                ayuda=tr("Los mods se instalan en Opciones, Actualizaciones, Componentes, o se hacen con el editor de mods."))]
    m = Menu(app, tr("Mods: activar o desactivar"), ops + [Opcion(tr("Volver"), lambda: app.cerrar(m))], al_cerrar=al_cerrar,
             intro=tr("Cada mod dice si está activado. Intro lo cambia. Los cambios se notan al volver a abrir el juego"))
    app.abrir(m)
