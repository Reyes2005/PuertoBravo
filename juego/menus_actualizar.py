"""Menú de actualizaciones y aviso al arrancar."""
from .i18n import tr
import os
import sys
import threading

import pygame

from . import VERSION, actualizador as A, registro
from .menus import EntradaTexto, Menu, Opcion

TEXTO_FUENTE = {"servidor": tr("el servidor del juego"), "github": "GitHub", "ambas": tr("las dos, el servidor del juego y GitHub"), "personalizada": tr("una dirección personalizada")}


class Tarea:
    """Pantalla de espera: hace un trabajo largo sin congelar el juego. Escape lo cancela."""
    pausa_mundo = True

    def __init__(self, app, titulo, trabajo, al_terminar):
        self.app = app
        self.titulo = titulo
        self.trabajo = trabajo                # función(tarea) -> resultado
        self.al_terminar = al_terminar        # función(resultado, error)
        self.cancelada = False
        self.avisos = []                      # textos que el trabajo quiere que se digan
        self.resultado = None
        self.error = None
        self.hecho = False
        self.hilo = None
        self.t_eco = 0.0
        self.estado = ""                      # cuánto lleva, dicho en una frase: lo pone el trabajo y se oye al pulsar una tecla
        self.fondo = False                    # se puede dejar en segundo plano y seguir jugando
        self.en_fondo = False

    def al_entrar(self):
        self.app.decir(self.titulo + tr(". Espera. Cualquier tecla dice cuánto lleva. Escape cancela.")
                       + (tr(' Con {_tecla_fondo} se queda en segundo plano y sigues con lo que estabas.').format(_tecla_fondo=(self._tecla_fondo())) if self.fondo else ""), True)

    def _tecla_fondo(self):
        """Con qué se deja en segundo plano: la B o, con mando, X o Cuadrado (que aquí llega como Tabulador)."""
        md = getattr(self.app, "mando", None)
        return md.boton_pantalla(pygame.K_TAB, tr("la B")) if md is not None else tr("la B")

    def decir(self, texto):
        self.avisos.append(texto)

    def _correr(self):
        try:
            self.resultado = self.trabajo(self)
        except Exception as e:               # el error se cuenta al jugador en el hilo principal
            self.error = e
        self.hecho = True

    def tecla(self, ev):
        if ev.key == pygame.K_ESCAPE:
            if not self.cancelada:
                self.t_cancelar = 0.0
            self.cancelada = True
            self.app.decir(tr("Cancelando."), True)
        elif ev.key in (pygame.K_b, pygame.K_TAB) and self.fondo and not self.hecho and self.hilo is not None and not self.app.pruebas:
            self.en_fondo = True
            self.app.cerrar(self)
            if not hasattr(self.app, "tareas_fondo"):
                self.app.tareas_fondo = []
            self.app.tareas_fondo.append(self)
            self.app.son("notificacion")
            self.app.decir(self.titulo + tr(": sigue en segundo plano. Te aviso cuando termine."), True)
        else:
            self.app.decir(f"{self.titulo}. {self.estado or tr('Espera.')}", True)

    def paso_fondo(self):
        """Lo llama el juego en cada vuelta mientras la tarea sigue en segundo plano. True cuando ha terminado."""
        self.avisos.clear()                    # en segundo plano no se va cantando el avance: se pregunta, o se espera al final
        if not self.hecho:
            return False
        self.al_terminar(self.resultado, self.error)
        return True

    def actualizar(self, dt):
        if self.hilo is None:
            if self.app.pruebas:
                self.hilo = True
                self._correr()
            else:
                self.hilo = threading.Thread(target=self._correr, daemon=True)
                self.hilo.start()
        if self.cancelada and not self.hecho:
            self.avisos.clear()                # cancelada: ya no se canta cómo va
            self.t_cancelar = getattr(self, "t_cancelar", 0.0) + dt
            if self.t_cancelar >= 2.0:         # la red no contesta: no se espera a ella. El hilo lo deja al recibir el siguiente trozo
                self.hecho = True
                self.app.cerrar(self)
                self.al_terminar(None, A.Cancelado(tr("Cancelado.")))
            return
        while self.avisos:
            self.app.decir(self.avisos.pop(0))
        if not self.hecho:
            self.t_eco += dt
            if self.t_eco >= 4.0:             # un tictac suave: sigue trabajando
                self.t_eco = 0.0
                self.app.son("menu_mover", vol=0.3)
            return
        self.app.cerrar(self)
        self.al_terminar(self.resultado, self.error)


def _abrir(app):
    """Con qué se abre la red. En las pruebas automáticas nunca se sale a internet."""
    propio = getattr(app, "act_abrir", None)
    if propio is not None:
        return propio
    if app.pruebas:
        def sin_red(url, tiempo=0):
            raise OSError(tr("sin red en las pruebas"))
        return sin_red
    return None


def buscar(app, al_no_haber=None):
    cfg = app.cfg

    def trabajo(tarea):
        return A.comprobar(cfg["act_fuente"], cfg["act_url"], abrir=_abrir(app), claves=getattr(app, "act_claves", None))

    def fin(info, error):
        registro.info("actualizar", "Búsqueda de versión nueva", fuente=cfg["act_fuente"], encontrada=getattr(info, "version", "ninguna"),
                      error=f"{type(error).__name__}: {error}" if error is not None else "ninguno")
        if error is not None:
            app.son("error")
            app.decir(str(error) if isinstance(error, A.ErrorActualizacion) else tr("No se pudo comprobar si hay una versión nueva."), True)
        elif info is None:
            app.son("guardado")
            app.decir(tr('Tienes la última versión, la {VERSION}.').format(VERSION=(VERSION)), True)
        else:
            ofrecer(app, info)
    app.abrir(Tarea(app, tr('Buscando actualizaciones en {v}').format(v=(TEXTO_FUENTE[cfg['act_fuente']])), trabajo, fin))


def ofrecer(app, info):
    megas = max(1, round(info.tamano / (1024 * 1024)))

    def novedades():
        app.decir(info.novedades or tr("Esta versión no trae notas."), True)

    def instalar():
        if not A.puede_instalar():
            app.son("error")
            app.decir(tr("Estás jugando desde el código fuente: la versión nueva solo se instala sola en el juego compilado."), True)
            return
        falta = "" if app.pruebas and not hasattr(app, "act_libre") else A.problema_para_descargar(info, libre=getattr(app, "act_libre", None), escribible=getattr(app, "act_escribible", None))
        if falta:                                                # no va a caber, o no se va a poder escribir: mejor saberlo antes de descargar nada
            registro.aviso("actualizar", "No se puede descargar la versión nueva", version=info.version, motivo=falta[:60])
            app.son("error")
            app.decir(falta, True)
            return
        app.cerrar(m)
        descargar(app, info)
    m = Menu(app, tr('Hay una versión nueva, la {version}. Tienes la {VERSION}').format(version=(info.version), VERSION=(VERSION)), [
        Opcion(tr("Leer las novedades"), novedades, ayuda=tr("Te lee lo que trae la versión nueva antes de decidir si la instalas.")),
        Opcion(tr('Descargar e instalar ahora, {megas} megas').format(megas=(megas)), instalar,
               ayuda=tr("Descarga la versión nueva, comprueba que es auténtica, cierra el juego, lo actualiza y lo vuelve a abrir. Tus partidas, tus opciones, tu música y tus mods no se tocan.")),
        Opcion(tr("Ahora no"), lambda: app.cerrar(m)),
    ])
    app.son("evento")
    app.abrir(m)


def megas(n):
    return f"{n / 2 ** 20:.0f}".replace(".", ",")


def texto_progreso(hecho, total):
    """«42 por ciento: 180 de 430 megas.» Lo que se oye al pulsar una tecla durante una descarga."""
    if not total:
        return tr('{megas} megas descargados.').format(megas=(megas(hecho)))
    return tr('{int} por ciento: {megas} de {megas2} megas.').format(int=(int(100 * hecho / total)), megas=(megas(hecho)), megas2=(megas(total)))


def descargar(app, info):
    estado = {"cuarto": 0, "tarea": None}

    def trabajo(tarea):
        estado["tarea"] = tarea

        def progreso(hecho, total):
            tarea.estado = texto_progreso(hecho, total)
            cuarto = int(4 * hecho / max(1, total))
            if cuarto > estado["cuarto"] and cuarto < 4:
                estado["cuarto"] = cuarto
                tarea.decir(tr('{v} por ciento.').format(v=(cuarto * 25)))
        ruta = A.descargar(info, progreso=progreso, cancelado=lambda: tarea.cancelada, abrir=_abrir(app))
        tarea.estado = tr("Descarga comprobada. Preparando la instalación.")
        tarea.decir(tr("Descarga comprobada. Preparando la instalación."))
        nueva = A.extraer(ruta, os.path.join(A.carpeta_trabajo(), "nueva"))
        try:
            os.remove(ruta)
        except OSError:
            pass
        return A.escribir_instalador(nueva, version=info.version)

    def fin(bat, error):
        registro.info("actualizar", "Descarga de la versión nueva", version=info.version, megas=info.tamano // 2 ** 20,
                      error=f"{type(error).__name__}: {error}" if error is not None else "ninguno")
        if error is not None:
            if not isinstance(error, A.Cancelado):
                app.son("error")
            A.limpiar()
            app.decir(str(error) if isinstance(error, A.ErrorActualizacion) else str(A.error_de_disco(error, tr("preparar la actualización"))) if isinstance(error, OSError)
                      else tr("No se pudo preparar la actualización. ") + A.A_MANO, True)
            return
        if getattr(estado["tarea"], "en_fondo", False):          # se descargó mientras jugabas: se instala cuando tú digas
            app.act_lista = (bat, info.version)
            app.son("guardado")
            app.decir(tr('La versión {version} ya está descargada. Para instalarla, entra en Opciones, Actualizaciones, Instalar la versión descargada. El juego se cerrará, se actualizará y volverá a abrirse solo.').format(version=(info.version)))
            return
        _instalar(app, bat)
    app.act_version = info.version
    t = Tarea(app, tr('Descargando la versión {version}').format(version=(info.version)), trabajo, fin)
    t.fondo = True
    app.abrir(t)


def _servidores_abiertos(app):
    """Los servidores en línea de esta carpeta que están abiertos ahora y se pueden parar y volver a arrancar solos."""
    buscar_ = getattr(app, "act_servidores", None) or (None if app.pruebas else A.servidores_en_marcha)
    try:
        return list(buscar_()) if buscar_ else []
    except Exception:
        registro.excepcion("actualizar", "No se pudo mirar si hay un servidor en línea abierto")
        return []


def _confirmar_servidor(app, bat, fichas):
    """Hay un servidor en línea abierto: se explica lo que va a pasar y se pide permiso antes de tocarlo."""
    que = A.texto_servidores(fichas)
    servicio = any(f.get("servicio") for f in fichas)
    parado = A.sin_servidor_en_marcha(fichas)                    # solo el panel, con el servidor parado: no hay jugadores a los que avisar
    explica = (tr("El servidor está parado, así que no hay jugadores a los que avisar. El panel se cierra solo, el juego se actualiza y, al terminar, "
               "el panel vuelve a abrirse solo, minimizado y con el servidor parado, como estaba. Si la actualización fallara, el panel se vuelve a abrir igualmente, "
               "con la versión que tenías. Todo queda apuntado en el archivo actualizacion punto log de la carpeta de registros.")) if parado else (tr("Se avisa a los jugadores que haya dentro, con la cuenta atrás que tengas puesta en el servidor, que de serie son 20 segundos, y sus juegos se quedan esperando. "
               "El servidor lo guarda todo y se cierra, el juego se actualiza y, al terminar, el servidor vuelve a arrancar solo, igual que estaba, "
               "y los jugadores vuelven a entrar solos y siguen donde estaban. Si la actualización fallara, el servidor se vuelve a arrancar igualmente, con la versión que tenías. "
               "Todo queda apuntado en el archivo actualizacion punto log de la carpeta de registros.")
               + (tr(" Ojo: parece que este servidor lo arranca un servicio o una tarea programada de Windows. Se le puede pedir que se cierre, pero desde aquí no se puede "
                  "volver a arrancar igual: tendrás que arrancarlo como lo tengas montado, si no vuelve solo.") if servicio else ""))

    app.act_lista = (bat, getattr(app, "act_version", "") or "nueva")      # si sale con Escape, la descarga sigue ahí para luego

    def si():
        app.cerrar(m)
        app.act_lista = None
        _instalar(app, bat, confirmado=True)

    def no():
        app.cerrar(m)
        app.act_lista = (bat, getattr(app, "act_version", "") or "nueva")
        app.decir(tr("No se toca nada. La versión queda descargada: se instala cuando quieras desde Opciones, Actualizaciones, Instalar la versión descargada."), True)
    m = Menu(app, tr('Tienes abierto {que}. Para actualizar hay que ').format(que=(que)) + (tr("cerrarlo un momento") if parado else tr("pararlo un momento")), [
        Opcion(tr("Actualizar ahora: cerrar el panel y volver a abrirlo al terminar") if parado else
               tr("Actualizar ahora: avisar a los jugadores, parar el servidor y volver a arrancarlo al terminar"), si, ayuda=explica),
        Opcion(tr("Ahora no"), no, ayuda=(tr("No se cierra el panel") if parado else tr("No se para el servidor")) + tr(" ni se instala nada. La descarga no se pierde."))],
        intro=tr("F1 explica lo que va a pasar"))
    app.son("evento")
    app.abrir(m)


def _instalar(app, bat, confirmado=False):
    # Antes de cerrar: lo que haría fallar la instalación (el editor de mods abierto, poco sitio en el disco, una carpeta
    # en la que no se puede escribir). Si hay algo, se dice, la descarga se guarda y se instala cuando esté arreglado.
    # Un servidor en línea abierto no impide actualizar: se pide permiso, se para con orden y se vuelve a arrancar al terminar.
    fichas = _servidores_abiertos(app)
    comprobar = getattr(app, "act_comprobar", None) or (None if app.pruebas else (lambda nueva: A.problemas_para_instalar(nueva, servidores=fichas)))
    try:
        problemas = comprobar(os.path.join(os.path.dirname(bat), "nueva")) if comprobar else []
    except Exception:
        registro.excepcion("actualizar", "No se pudo comprobar si la actualización se puede instalar")
        problemas = []
    if problemas:
        app.act_lista = (bat, getattr(app, "act_version", "") or "nueva")
        registro.aviso("actualizar", "La actualización no se instala todavía", motivos=" | ".join(problemas))
        app.son("error")
        app.decir(tr("Todavía no se puede instalar. ") + " ".join(problemas) + tr(" Cuando esté arreglado, entra en Opciones, Actualizaciones, "
                  "Instalar la versión descargada. La descarga no se pierde."), True)
        return
    if fichas and not confirmado:
        return _confirmar_servidor(app, bat, fichas)
    if fichas:
        try:
            parar = getattr(app, "act_parar_servidores", None) or A.pedir_parada_servidores
            parar(fichas)
            registro.info("actualizar", "Se pide a los servidores en línea abiertos que se cierren para actualizar", cuantos=len(fichas),
                          tipos=",".join(f["tipo"] for f in fichas))
        except A.ErrorActualizacion as e:
            app.act_lista = (bat, getattr(app, "act_version", "") or "nueva")
            registro.aviso("actualizar", "No se pudo pedir al servidor en línea que se cierre", motivo=str(e))
            app.son("error")
            app.decir(str(e) + tr(" La descarga no se pierde."), True)
            return
    if True:
        parado = A.sin_servidor_en_marcha(fichas)
        p = app.partida
        if p is not None and not p.mision:
            try:
                from . import menus_juego
                menus_juego.guardar_por_si_acaso(p)      # a la ranura de la partida, con su copia anterior
            except Exception:
                pass
        amigos = False
        try:                                                     # con la partida abierta a los amigos: que sepan por qué se cierra
            if p is not None and p.es_anfitrion() and p.online_activo() and p.remotos:
                amigos = True
                p.red.enviar({"t": "chat", "texto": tr("Cierro la partida unos minutos para actualizar el juego. Cuando vuelva a abrirla, entrad otra vez.")})
        except Exception:
            pass
        app.son("guardado")
        app.decir(tr("Todo listo. ") + (tr("La partida que tienes abierta a tus amigos se cierra, y se lo he dicho: ábrela otra vez cuando vuelvas. ") if amigos else "")
                  + (tr("El panel del servidor en línea se cierra. ") if parado else tr("El servidor en línea avisa a los jugadores y se cierra. ") if fichas else "")
                  + tr("El juego se cierra, se actualiza y vuelve a abrirse solo en ") + (tr("un minuto más o menos") if fichas and not parado else tr("unos segundos"))
                  + (tr(", y el panel vuelve a abrirse con él.") if parado else tr(", y el servidor vuelve a arrancar con él.") if fichas else "."), True)
        try:
            from . import vozgen
            vozgen.parar_prueba()                                # el proceso que prueba el motor de voz es el propio programa: no puede quedarse abierto
        except Exception:
            pass
        if not app.pruebas:
            pygame.time.wait(4500)
            A.lanzar_instalador(bat)
        app.salir()


def opciones(app):
    cfg = app.cfg

    def fuente(d):
        i = A.FUENTES.index(cfg["act_fuente"]) if cfg["act_fuente"] in A.FUENTES else 0
        cfg["act_fuente"] = A.FUENTES[(i + d) % len(A.FUENTES)]

    def auto(d):
        cfg["act_auto"] = not cfg["act_auto"]

    def direccion():
        def hecho(t):
            t = t.strip()
            if t:
                try:
                    A.comprobar_url(t)
                except A.ErrorActualizacion as e:
                    app.son("error")
                    app.decir(str(e), True)
                    return
            cfg["act_url"] = t
            app.decir(tr("Dirección guardada.") if t else tr("Dirección borrada."), True)
        app.abrir(EntradaTexto(app, tr("Dirección personalizada del archivo version punto json"), hecho, inicial=cfg["act_url"], maximo=300,
                               ayuda=tr("La dirección completa, que empiece por https, del archivo version.json. Puedes pegarla con Control V. Sirva de donde sirva, la versión tiene que ir firmada por quien publica el juego.")))

    def instalar_lista():
        lista = getattr(app, "act_lista", None)
        if lista:
            app.act_lista = None
            _instalar(app, lista[0])

    def fallo():
        app.decir(app.act_fallo + tr(" El detalle está en la carpeta de registros, en el archivo actualizacion punto log: se llega desde Opciones, Registro para informar de fallos, Abrir la carpeta con todas las sesiones."), True)

    def sin_red():
        app.decir(tr('Al abrir el juego se buscó una versión nueva y no se pudo: {act_sin_red} Elige Buscar actualizaciones ahora para probar otra vez.').format(act_sin_red=(app.act_sin_red)), True)

    m = Menu(app, tr("Actualizaciones"), ([
        Opcion(tr('Instalar la versión descargada, la {v}').format(v=(app.act_lista[1])), instalar_lista,
               ayuda=tr("Ya está descargada y comprobada. El juego guarda la partida, se cierra, se actualiza y vuelve a abrirse solo en unos segundos."))] if getattr(app, "act_lista", None) else []) + ([
        Opcion(tr("Por qué falló la última actualización"), fallo,
               ayuda=tr("Lo que dejó apuntado el instalador: en qué paso falló, con qué archivo y qué hacer para que la próxima vez salga bien."))] if getattr(app, "act_fallo", None) else []) + ([
        Opcion(tr("Aviso: al abrir el juego no se pudo buscar una versión nueva"), sin_red,
               ayuda=tr("Al arrancar no se molesta con errores, pero aquí queda dicho: si no se puede buscar, el juego no puede avisarte de las versiones nuevas. Intro dice el motivo."))] if getattr(app, "act_sin_red", None) else []) + [
        Opcion(tr('Versión instalada: {VERSION}').format(VERSION=(VERSION)), lambda: app.decir(tr('Tienes la versión {VERSION}.').format(VERSION=(VERSION)), True),
               ayuda=tr("La versión del juego que tienes ahora. Tras actualizar, aquí tiene que salir la nueva.")),
        Opcion(tr("Buscar actualizaciones ahora"), lambda: buscar(app),
               ayuda=tr("Mira en la fuente elegida si hay una versión más nueva. Si la hay, te ofrece leer las novedades e instalarla; si no, te dice que tienes la última. Hace falta conexión.")),
        Opcion(lambda: tr('Buscar al arrancar el juego: {v}').format(v=(tr('sí') if cfg['act_auto'] else tr('no'))), ajuste=auto,
               ayuda=tr("Al abrir el juego mira si hay una versión nueva y te avisa. No descarga ni instala nada sin que tú lo pidas, salvo que actives la opción de abajo.")),
        Opcion(lambda: tr('Si hay una versión nueva al arrancar, instalarla sola: {v}').format(v=(tr('sí') if cfg['act_instalar_solo'] else tr('no'))),
               ajuste=lambda d: cfg.__setitem__("act_instalar_solo", not cfg["act_instalar_solo"]),
               ayuda=tr("Con sí, cuando al abrir el juego encuentra una versión nueva, la descarga, la comprueba y la instala sin preguntarte, en cuanto estás en el menú principal. "
                     "Te lo dice antes de empezar, y Escape lo cancela. Hace falta tener activado Buscar al arrancar. Con no, que es como viene, solo te avisa.")),
        Opcion(lambda: tr('Actualizar desde: {v}').format(v=(TEXTO_FUENTE[cfg['act_fuente']])), ajuste=fuente,
               ayuda=tr("Con las flechas izquierda y derecha eliges de dónde se buscan y se descargan las versiones: el servidor del juego, GitHub, las dos o una dirección que escribas tú. "
                     "Con las dos, se usa la versión más nueva y, si una falla, la otra. Venga de donde venga, solo se instala una versión firmada por quien publica el juego.")),
        Opcion(lambda: tr("Dirección personalizada: ") + (cfg["act_url"] or "ninguna"), direccion, ayuda=tr("Solo se usa si eliges actualizar desde una dirección personalizada. Intro para escribirla.")),
        Opcion(tr("Componentes: idiomas, voces, documentación, sonidos y mods"), lambda: __import__("juego.menus_componentes", fromlist=["x"]).buscar(app),
               ayuda=tr("Lo que se publica aparte del juego, sin esperar a una versión nueva: un idioma, sus voces, la documentación corregida, un pack de sonidos o un mod. "
                     "Se busca en la misma fuente que las versiones, y se instala sin cerrar el juego. Todo va firmado por quien publica el juego.")),
        Opcion(lambda: tr('Buscar componentes nuevos al arrancar: {v}').format(v=(tr('sí') if cfg['comp_auto'] else tr('no'))),
               ajuste=lambda d: cfg.__setitem__("comp_auto", not cfg["comp_auto"]),
               ayuda=tr("Al abrir el juego mira si hay componentes nuevos o con versión nueva y te avisa. No instala nada sin que tú lo pidas, salvo que actives la opción de abajo.")),
        Opcion(lambda: tr('Instalar solos los componentes nuevos de las categorías que te interesan: {v}').format(v=(tr('sí') if cfg['comp_instalar_solo'] else tr('no'))),
               ajuste=lambda d: cfg.__setitem__("comp_instalar_solo", not cfg["comp_instalar_solo"]),
               ayuda=tr("Con sí, al abrir el juego se instalan solos, sin preguntarte, los componentes nuevos o con versión nueva, pero solo de las categorías que marcaste en Componentes, "
                     "Categorías que te interesan. Si no quieres mods, no se instala ninguno. Hace falta tener activado Buscar componentes nuevos al arrancar. Con no, que es como viene, solo te avisa.")),
        Opcion(tr("Actualizar a mano, si desde aquí no hay manera"), lambda: a_mano(app),
               ayuda=tr("Los pasos para poner la versión nueva tú mismo, descargándola con el navegador y descomprimiéndola encima de la carpeta del juego. Tus partidas y tus opciones se conservan.")),
        Opcion(tr("Volver"), lambda: app.cerrar(m)),
    ], al_cerrar=cfg.guardar)
    app.abrir(m)


PASOS_A_MANO = (
    tr("Uno. Abre la página de descargas del juego con la opción de abajo, o desde otro ordenador o con el móvil si en este la red está bloqueada, "
    "y descarga el archivo ZIP de la última versión: su nombre empieza por PuertoBravo, todo junto, y sigue con el número de versión."),
    tr("Dos. Cierra el juego. Cierra también el editor de mods y el servidor en línea, si los tienes abiertos."),
    tr("Tres. Abre el ZIP y copia todo lo que trae dentro de la carpeta donde tienes el juego, encima de lo que hay. "
    "Cuando Windows pregunte, elige reemplazar los archivos. No borres antes la carpeta: dentro están tus partidas, tus opciones y tu música, y la versión nueva no trae nada de eso, así que no se pisa. Tus mods tampoco se borran."),
    tr("Cuatro. Abre el juego. En Opciones, Actualizaciones, la primera línea dice la versión instalada: tiene que ser la nueva."),
    tr("Si Windows no deja copiar, el juego está en una carpeta protegida: mueve la carpeta entera del juego a otro sitio, por ejemplo dentro de Documentos, y repite el paso tres."),
)


def a_mano(app):
    """Los pasos para actualizar sin el actualizador: para cuando un antivirus, un filtro de red o los permisos no dejan."""
    def abrir_pagina():
        try:
            os.startfile(A.PAGINA_DESCARGAS)
            app.decir(tr("Se abre la página de descargas en tu navegador. El juego sigue aquí."), True)
        except (OSError, AttributeError):
            app.son("error")
            app.decir(tr("No se pudo abrir el navegador. La dirección es github punto com, barra, ") + A.REPOSITORIO_GITHUB.replace("/", ", barra, ") + tr(", barra, releases."), True)

    def abrir_carpeta():
        try:
            os.startfile(A.carpeta_programa())
            app.decir(tr("Se abre la carpeta del juego en el explorador de Windows: ahí es donde hay que copiar lo que trae el ZIP."), True)
        except (OSError, AttributeError):
            app.son("error")
            app.decir(tr("No se pudo abrir la carpeta. Es la carpeta desde la que abres el juego."), True)
    ops = [Opcion(t.rstrip("."), ayuda=tr("Un paso para actualizar a mano. Con flecha abajo pasas al siguiente.")) for t in PASOS_A_MANO]         # el menú pone el punto
    ops += [Opcion(tr("Abrir la página de descargas en el navegador"), abrir_pagina,
                   ayuda=tr("Abre en tu navegador la página donde está el ZIP de cada versión. El juego sigue abierto.")),
            Opcion(tr("Abrir la carpeta del juego"), abrir_carpeta, ayuda=tr("La carpeta donde hay que copiar lo que trae el ZIP.")),
            Opcion(tr("Volver"), lambda: app.cerrar(m))]
    m = Menu(app, tr("Actualizar a mano. Son cuatro pasos: recórrelos con las flechas"), ops)
    app.abrir(m)


# ------------------------------------------------------------------ al arrancar
def al_arrancar(app):
    """Tras actualizar, lo dice y limpia. Si está activado, busca una versión nueva sin molestar."""
    if A.ARG_TRAS_ACTUALIZAR in sys.argv or "--actualizacion-fallida" in sys.argv:
        A.limpiar_registro_instalador()                          # el instalador apunta rutas completas: se dejan en el nombre del archivo,
        registro._sanear(A.ruta_registro_instalador())           # y lo demás se limpia como el resto del registro
    if A.ARG_TRAS_ACTUALIZAR in sys.argv:
        A.limpiar()
        registro.info("actualizar", "Primera sesión tras actualizar", version=VERSION)
        servidores = A.texto_relanzados(A.leer_registro_instalador())
        app.decir(tr('Juego actualizado a la versión {VERSION}. Las novedades están en el menú principal, en Acerca de, Novedades de esta versión.').format(VERSION=(VERSION)) + (" " + servidores if servidores else ""))
    elif "--actualizacion-fallida" in sys.argv:
        A.limpiar()
        motivo = A.motivo_del_fallo()
        registro.aviso("actualizar", "La actualización anterior falló y se restauró la versión que había", dicho=motivo, **{k: v for k, v in A.leer_registro_instalador().items() if v and k != "existe"})
        app.act_fallo = motivo
        app.son("error")
        servidores = A.texto_relanzados(A.leer_registro_instalador())
        app.decir(tr('La actualización no se pudo instalar y se ha dejado la versión que tenías, la {VERSION}. {motivo} Lo tienes otra vez en Opciones, Actualizaciones, y el detalle está en la carpeta de registros, en el archivo actualizacion punto log.').format(VERSION=(VERSION), motivo=(motivo))
                  + (" " + servidores if servidores else ""))
    app.act_aviso = None
    if not app.pruebas:
        # Si el juego se actualizó porque un servidor pedía una versión más nueva, se ofrece volver a ese servidor.
        from . import reconexion
        nota = reconexion.leer_vuelta()
        if nota and A.ARG_TRAS_ACTUALIZAR in sys.argv:
            reconexion.ofrecer_vuelta(app, nota)
    if app.pruebas or not (app.cfg["act_auto"] or app.cfg["comp_auto"]):
        return

    def mirar():
        from . import comunidad                                  # la lista de la Comunidad de jugadores, al día
        comunidad.poner_al_dia(app, en_segundo_plano=False)
        if app.cfg["comp_auto"]:
            from . import menus_componentes
            menus_componentes.mirar_al_arrancar(app)
        if not app.cfg["act_auto"]:
            return
        try:
            app.act_aviso = A.comprobar(app.cfg["act_fuente"], app.cfg["act_url"])
            registro.info("actualizar", "Comprobación al arrancar", fuente=app.cfg["act_fuente"], encontrada=getattr(app.act_aviso, "version", "ninguna"))
        except Exception as e:
            registro.info("actualizar", "Comprobación al arrancar sin resultado", fuente=app.cfg["act_fuente"], motivo=f"{type(e).__name__}: {e}")
            app.act_aviso = None             # sin conexión o sin fuente: al arrancar no se molesta con errores,
            app.act_sin_red = str(e) if isinstance(e, A.ErrorActualizacion) else tr("no se pudo conectar.")      # pero queda dicho en Opciones, Actualizaciones
    threading.Thread(target=mirar, daemon=True).start()


def paso(app):
    """Llamado en cada vuelta del bucle: da el aviso cuando la búsqueda del arranque encuentra algo."""
    info = getattr(app, "act_aviso", None)
    if info is None and getattr(app, "comp_aviso", 0):
        from . import menus_componentes
        menus_componentes.paso(app)
    if info is None or app.partida is not None or len(app.pila) != 1:
        return
    app.act_aviso = None
    app.son("evento")
    if app.cfg["act_instalar_solo"] and A.puede_instalar() and not A.problema_para_descargar(info, libre=getattr(app, "act_libre", None), escribible=getattr(app, "act_escribible", None)):
        registro.info("actualizar", "Instalación sola al arrancar", version=info.version)
        app.decir(tr('Hay una versión nueva del juego, la {version}, y la instalas sola, como pediste en Opciones, Actualizaciones. Escape la cancela.').format(version=(info.version)))
        descargar(app, info)
        return
    app.decir(tr('Hay una versión nueva del juego, la {version}. Para instalarla entra en Opciones, Actualizaciones.').format(version=(info.version)))
