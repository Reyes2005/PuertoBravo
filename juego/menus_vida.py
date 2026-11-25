"""Menús de la elección de personaje y de la vida honrada: oficina de empleo, academias y voluntariado."""
from .i18n import tr
from . import genero
from .menus import EntradaTexto, Menu, Opcion
from .trabajos import NOMBRE_TRABAJO
from .vida import HAB_NOMBRE, MAX_NIVEL, MAX_NOMBRE, PUNTOS, RANGOS, VENTAJAS, limpiar_nombre, personaje_propio

DONDE = {"taxi": tr("un taxi"), "ambulancia": tr("una ambulancia"), "autobus": tr("un autobús"), "vigilante": tr("un coche patrulla"), "camion": tr("un camión"),
         "helados": tr("una furgoneta de helados"), "bomberos": tr("un camión de bomberos"), "grua": tr("una grúa"), "paqueteria": tr("una bicicleta, un scooter o una moto"),
         "mensajeria": tr("cualquier barco, ya en el mar")}


TRATO = {"h": tr("en masculino"), "m": tr("en femenino")}
AYUDA_TRATO = (tr("Cambia cómo te hablan los demás y cómo te habla el juego: bienvenido o bienvenida, el sobrino o la sobrina de Encarna. "
               "La historia y todo lo demás son iguales."))


def elegir_genero(app, al_elegir, quien=""):
    """Pregunta cómo hay que tratar al protagonista y llama a al_elegir con "h" o "m"."""
    def con(g):
        def f():
            app.cerrar(m)
            al_elegir(g)
        return f
    ops = [Opcion(tr("En masculino"), con("h"), ayuda=tr("Te hablan como a un hombre: bienvenido, el sobrino de Encarna, hijo.")),
           Opcion(tr("En femenino"), con("m"), ayuda=tr("Te hablan como a una mujer: bienvenida, la sobrina de Encarna, hija.")),
           Opcion(tr("Volver"), lambda: app.cerrar(m))]
    m = Menu(app, tr('¿Cómo quieres que te hablen{v}?').format(v=(tr(' con ') + quien if quien else '')), ops, intro=AYUDA_TRATO)
    app.abrir(m)


def elegir_personaje(app):
    datos = app.datos.get("personajes", [])

    def con(pj):
        def f():
            if pj.get("genero") in genero.GENEROS:           # los personajes de algunos mods ya dicen si son él o ella
                app.empezar_partida(None, personaje=pj["id"])
            else:
                elegir_genero(app, lambda g: app.empezar_partida(None, personaje={"id": pj["id"], "genero": g}), pj["nombre"])
        return f
    ops = [Opcion(f"{pj['nombre']} {pj.get('apellido', '')}".strip() + f". {pj.get('desc', '')}", con(pj),
                  ayuda=tr("Empiezas la partida con este personaje y sus ventajas.") if pj.get("genero") in genero.GENEROS else tr("Después eliges si te hablan en masculino o en femenino.")) for pj in datos]
    ops.append(Opcion(tr("Crear tu propio personaje"), lambda: crear_personaje(app),
                      ayuda=tr("Le pones nombre y apellido, eliges si te hablan en masculino o en femenino, repartes ocho niveles entre las cuatro habilidades y escoges con qué empiezas.")))
    ops.append(Opcion(tr("Volver"), lambda: app.cerrar(m)))
    m = Menu(app, tr("Elige tu personaje"), ops, intro=tr("La historia es la misma para todos; cambian las ventajas con las que empiezas. La última opción te deja crear el tuyo"))
    app.abrir(m)


AYUDA_HAB = {"conduccion": tr("Con más nivel el vehículo corre algo más y se daña menos en los golpes."),
             "punteria": tr("Con más nivel aciertas más a menudo."),
             "resistencia": tr("Con más nivel corres más deprisa y te hacen algo menos de daño."),
             "pesca": tr("Con más nivel pican antes y el pescado vale más.")}


def crear_personaje(app):
    """El jugador se hace su protagonista: nombre, apellido, cómo le hablan, las habilidades y con qué empieza."""
    from . import vozgen
    e = {"nombre": "", "apellido": "", "genero": "h", "niveles": {h: 0 for h in HAB_NOMBRE}, "ventaja": 0, "voz": 0, "dicho": ""}

    def voz(d):
        e["voz"] = (e["voz"] + d) % len(vozgen.VOCES_PROTA)

    def oir_nombre():
        if not e["nombre"]:
            app.son("error")
            return app.decir(tr("Primero pon el nombre."), True)
        quien = vozgen.reparto()["personajes"].get("Encarna")
        pj = vozgen.Personaje(e["nombre"], e["apellido"], e["genero"], vozgen.VOCES_PROTA[e["voz"]], e["dicho"])
        vozgen.probar(app, quien, pj.texto(tr("¡Dani! ¡Pero mírate! Te lo dije: Dani Roca siempre vuelve.")))

    def oir_voz():
        pj = vozgen.Personaje(e["nombre"] or tr("Dani"), e["apellido"], e["genero"], vozgen.VOCES_PROTA[e["voz"]], e["dicho"])
        archivo = vozgen.reparto()["protagonista"].get(f"{pj.voz}_{pj.genero}")
        vozgen.probar(app, archivo, pj.texto(tr("Me llamo Dani Roca. He salido esta mañana y no tengo ni para un café.")))

    def quedan():
        return PUNTOS - sum(e["niveles"].values())

    def pedir(campo, titulo):
        def hecho(t):
            limpio = limpiar_nombre(t)
            if t.strip() and not limpio:
                app.son("error")
                app.decir(tr("Ahí solo valen letras, espacios y guiones."), True)
                return
            e[campo] = limpio
            m.refrescar(False)
            app.decir(f"{titulo}: {limpio or tr('sin poner')}.", True)
        return lambda: app.abrir(EntradaTexto(app, titulo, hecho, inicial=e[campo], maximo=MAX_NOMBRE,
                                              ayuda=tr('Hasta {MAX_NOMBRE} letras. Lo que escribas aquí no se anota en el registro del juego.').format(MAX_NOMBRE=(MAX_NOMBRE))))

    def trato(d):
        e["genero"] = "m" if e["genero"] == "h" else "h"

    def nivel(h):
        def f(d):
            n = e["niveles"][h] + d
            if n < 0 or n > MAX_NIVEL or (d > 0 and quedan() <= 0):
                app.son("menu_borde")
                return
            e["niveles"][h] = n
        return f

    def ventaja(d):
        e["ventaja"] = (e["ventaja"] + d) % len(VENTAJAS)

    def empezar():
        if not e["nombre"]:
            app.son("error")
            app.decir(tr("Falta el nombre. Es la primera opción."), True)
            return
        aviso = quedan()
        pj = personaje_propio(e["nombre"], e["apellido"], e["genero"], e["niveles"], VENTAJAS[e["ventaja"]][0], vozgen.VOCES_PROTA[e["voz"]], e["dicho"])
        if aviso > 0 and not e.get("avisado"):
            e["avisado"] = True
            app.son("menu_borde")
            app.decir(tr('Te quedan {aviso} niveles de habilidad sin repartir. Pulsa Intro otra vez para empezar así, o repártelos antes.').format(aviso=(aviso)), True)
            return
        if app.cfg["voces_grabadas"] and app.cfg["voces_propias"] and not app.pruebas and vozgen.disponible():
            quien = vozgen.Personaje(pj["nombre"], pj["apellido"], pj["genero"], pj["voz"], pj["dicho"])
            app.abrir(vozgen.Preparando(app, quien, app.datos.get("misiones", []), lambda: app.empezar_partida(None, personaje=pj)))
            return
        app.empezar_partida(None, personaje=pj)

    def ops():
        # los textos son funciones: cambian al tocar las flechas, sin rehacer el menú
        lista = [Opcion(lambda: tr('Nombre: {v}').format(v=(e['nombre'] or tr('sin poner'))), pedir("nombre", tr("Nombre")), ayuda=tr("Intro para escribirlo. Así te llamarán en la historia.")),
                 Opcion(lambda: tr('Apellido: {v}').format(v=(e['apellido'] or tr('sin poner'))), pedir("apellido", tr("Apellido")), ayuda=tr("Intro para escribirlo. Puedes dejarlo vacío.")),
                 Opcion(lambda: tr('Te hablan {v}').format(v=(TRATO[e['genero']])), ajuste=trato, ayuda=AYUDA_TRATO + tr(" Izquierda, derecha o Intro para cambiar.")),
                 Opcion(lambda: tr('Tu voz en las escenas: {v}, {v2}').format(v=(vozgen.NOMBRE_VOZ[vozgen.VOCES_PROTA[e['voz']]]), v2=(TRATO[e['genero']])), ajuste=voz,
                        ayuda=tr("La voz con la que hablas tú en las escenas de la historia. Hay cuatro de hombre y cuatro de mujer; suena la que corresponde a cómo te hablan. Izquierda y derecha para cambiar."))]
        if vozgen.disponible() or vozgen.probando():      # mientras el motor se comprueba, las opciones ya están: si se pulsan, lo dicen
            lista += [Opcion(lambda: tr('Cómo se pronuncia tu nombre: {v}').format(v=(e['dicho'] or tr('igual que se escribe'))), pedir("dicho", tr("Cómo se pronuncia tu nombre")),
                             ayuda=tr("Si al escuchar tu nombre no suena bien, escríbelo aquí como se pronuncia, por ejemplo Yónatan en vez de Jonathan. En pantalla y en braille sigue saliendo como lo escribiste arriba. Puedes dejarlo vacío.")),
                      Opcion(tr("Escuchar cómo te llamarán"), oir_nombre, ayuda=tr("Genera una frase con tu nombre, dicha por un personaje de la historia. Tarda un momento.")),
                      Opcion(tr("Escuchar tu voz"), oir_voz, ayuda=tr("Genera una frase dicha por ti, con la voz elegida. Tarda un momento."))]
        for h, nombre in HAB_NOMBRE.items():
            lista.append(Opcion((lambda h=h, nombre=nombre: tr('{capitalize}: nivel {v}. Quedan {quedan} por repartir').format(capitalize=(nombre.capitalize()), v=(e['niveles'][h]), quedan=(quedan()))), ajuste=nivel(h),
                                ayuda=tr('{get} Derecha sube e izquierda baja. Tienes {PUNTOS} niveles para repartir y como mucho {MAX_NIVEL} en cada habilidad. Después se sigue subiendo con la práctica y en las academias, hasta el diez.').format(get=(AYUDA_HAB.get(h, '')), PUNTOS=(PUNTOS), MAX_NIVEL=(MAX_NIVEL))))
        lista.append(Opcion(lambda: tr('Ventaja de salida: {v}. {v2}').format(v=(VENTAJAS[e['ventaja']][1]), v2=(VENTAJAS[e['ventaja']][2])), ajuste=ventaja, ayuda=tr("Izquierda y derecha para ver las demás. Solo puedes llevarte una.")))
        lista.append(Opcion(tr("Empezar la partida"), empezar, ayuda=tr("Empieza la historia con el personaje tal como está.")))
        lista.append(Opcion(tr("Volver"), lambda: app.cerrar(m)))
        return lista
    m = Menu(app, tr("Crea tu personaje"), ops, intro=tr("Arriba y abajo para recorrer los datos. Intro para escribir el nombre; izquierda y derecha para cambiar lo demás"))
    app.abrir(m)


def _menu(p, l, ops, intro=None):
    m = Menu(p.app, lambda: tr('{nombre}. Tienes {dinero} euros').format(nombre=(l.nombre), dinero=(p.j.dinero)), ops + [Opcion(tr("Volver"), lambda: p.app.cerrar(m))], intro=intro)
    p.app.abrir(m)
    return m


def empleo(p, l):
    app = p.app

    def buscar(tipo):
        def f():
            if tipo == "mensajeria":
                app.decir(tr("Para la mensajería del mar, zarpa en cualquier barco desde un embarcadero y pulsa J."), True)
                return
            donde = p.vehiculo_de_trabajo_cercano(tipo)
            if donde is None:
                app.decir(tr('En esta localidad no hay ningún sitio fijo donde encontrar {v}. Tendrás que comprarlo, o tomarlo prestado.').format(v=(DONDE[tipo])), True)
                return
            while len(app.pila) > 1 and app.pila[-1] is not p:
                app.pila.pop()
            app.teclas.clear()
            p.salir_interior()
            p.gps_a_lugar(donde)
            p.decir(tr('Hay {v} aparcado junto a {nombre}. Sube con F y pulsa J para empezar a trabajar.').format(v=(DONDE[tipo]), nombre=(donde.nombre)))
        return f
    ops = [Opcion(tr('{nombre}: ocho horas, unos {int} euros').format(nombre=(nombre), int=(int(paga * p.mult_trabajo('jornada')))), (lambda c=clave, n=nombre, pg=paga, s=salud: p.jornada(c, n, pg, s)),
                  ayuda=tr("Trabajo sin vehículo: pasan ocho horas y cobras. Una jornada al día. Sube tu prestigio entre los vecinos.")) for clave, nombre, paga, salud in ((x["id"], x["nombre"], int(x.get("paga", 0)), float(x.get("salud", 0))) for x in p.datos.get("jornadas", []))]
    for tipo, nombre in NOMBRE_TRABAJO.items():
        ops.append(Opcion(tr('Oficio de {nombre}: eres {v}, con {servicios_de} servicios. Se hace con {get}').format(nombre=(nombre), v=(RANGOS[p.rango(tipo)]), servicios_de=(p.servicios_de(tipo)), get=(DONDE.get(tipo, tr('su vehículo')))), buscar(tipo),
                          ayuda=tr("Intro marca en el GPS dónde hay un vehículo de ese oficio. Cada ocho servicios asciendes y cobras un doce por ciento más.")))
    ops.append(Opcion(lambda: tr('En el barrio, {ciudadania_txt}').format(ciudadania_txt=(p.ciudadania_txt())), ayuda=tr("El prestigio sube con el trabajo honrado, los cursos, los donativos y ayudando en los sucesos. Baja con los delitos. Con buen prestigio cobras más y la policía es más comprensiva.")))
    from . import menus_honrado as mh
    ops.append(Opcion(lambda: tr("Contratos fijos: carrera con jefe, nómina y ascensos. ") + p.hon_contrato_txt(), lambda: mh.menu_empleos(p, l),
                      ayuda=tr("Opcional. Firmas con una empresa: te pide unos turnos cada periodo, te evalúa, te paga una nómina además de cada turno y te asciende si cumples. "
                            "Si faltas o lo haces mal, avisos y despido. Sin contrato, todo sigue como siempre.")))
    _menu(p, l, ops, tr("Aquí están todos los trabajos honrados del juego"))


def academia(p, l):
    cursos = [h for h in (l.get("cursos") or list(HAB_NOMBRE)) if h in HAB_NOMBRE]
    ops = [Opcion((lambda h=h: tr('Curso de {v}: {precio} euros y cuatro horas. Tu nivel es {nivel} de 10').format(v=(HAB_NOMBRE[h]), precio=(p.precio('curso', 250)), nivel=(p.nivel(h)))), (lambda h=h: p.curso(h)),
                  ayuda=tr("Sube la habilidad mucho más deprisa que la práctica. Un curso al día.")) for h in cursos]
    if p.normas_activas():
        from . import realismo as R
        ops.append(Opcion(lambda: tr('Curso de recuperación de puntos del carné: {int} euros y cuatro horas.').format(int=(int(R.aj('precio_carne')))) + p.carne_txt(), p.recuperar_carne,
                          ayuda=tr('Devuelve {int} puntos, hasta el tope de {int2}. Si te lo han retirado, con el curso vuelves a tenerlo.').format(int=(int(R.aj('puntos_curso'))), int2=(int(R.aj('puntos_carne'))))))
    if p.datos.get("titulos"):
        from . import menus_honrado as mh
        ops.append(Opcion(lambda: tr("Estudios con título. ") + mh.estudios_txt(p), lambda: mh.menu_estudios(p, l),
                          ayuda=tr("Títulos que llevan varias sesiones, una al día, y dinero. Abren puestos mejores en los contratos fijos y mejoras para tus negocios. Se puede estudiar y trabajar el mismo día.")))
    _menu(p, l, ops)


def ong(p, l):
    ops = [Opcion(tr("Donar 50 euros"), lambda: p.donar(50), ayuda=tr("Sube un poco tu prestigio entre los vecinos y tu ánimo. Se puede repetir las veces que quieras.")),
           Opcion(tr("Donar 500 euros"), lambda: p.donar(500), ayuda=tr("Tu prestigio entre los vecinos sube diez veces más que donando cincuenta, y tu ánimo también mejora. Se puede repetir.")),
           Opcion(tr("Hacer voluntariado cuatro horas"), p.voluntariado, ayuda=tr("No cobras nada, pero sube mucho tu ánimo y tu prestigio entre los vecinos. Una vez al día.")),
           Opcion(lambda: tr('En el barrio, {ciudadania_txt}').format(ciudadania_txt=(p.ciudadania_txt())),
                  ayuda=tr("El prestigio sube con el trabajo honrado, los cursos, los donativos y ayudando en los sucesos. Baja con los delitos. Con buen prestigio cobras más y la policía es más comprensiva."))]
    from .honrado import AJ as HON
    if p.hon_antecedentes():
        ops.insert(3, Opcion(tr('Hacer servicios a la comunidad: {entero} horas').format(entero=(HON.entero('servicio_horas'))), p.hon_servicio_comunidad,
                             ayuda=tr('Sin cobrar. Le quita {entero} días a tu antecedente penal más grave. Una vez al día.').format(entero=(HON.entero('servicio_quita')))))
    if p.j.reputacion > 0:
        ops.insert(3, Opcion(lambda: tr('Pasar {horas} horas con los chavales del barrio. Tu fama en la calle: {fama}').format(horas=HON.entero("chavales_horas"), fama=p.reputacion_txt()),
                             p.hon_chavales,
                             ayuda=tr('Sin cobrar, para que no acaben en la calle. Baja tu fama en la calle unos {fama} puntos sin tocar tu prestigio ni tu empleo, y los vecinos lo ven con buenos ojos. '
                                      'Una vez al día. Sirve si la fama te ha subido sin buscarla: con mucho prestigio y algo de fama, el barrio empieza a sospechar que llevas una doble vida.').format(fama=HON.entero("chavales_fama"))))
    _menu(p, l, ops)


def carrera(p):
    """Resumen de tu vida: la honrada y la otra."""
    app = p.app
    j = p.j
    s = j.stats
    lineas = [f"{j.nombre} {j.apellido}".strip() + tr('. Día {dia}').format(dia=(p.dia)),
              tr('Entre los vecinos, {ciudadania_txt}. En la calle, {reputacion_txt}. Tu ánimo es {animo_txt}').format(ciudadania_txt=(p.ciudadania_txt()), reputacion_txt=(p.reputacion_txt()), animo_txt=(p.animo_txt())),
              tr('Misiones completadas: {len}. Dinero: {dinero} euros en mano y {banco} en el banco').format(len=(len(p.completadas)), dinero=(j.dinero), banco=(j.banco))]
    hechos = [(t, n) for t, n in NOMBRE_TRABAJO.items() if p.servicios_de(t)]
    for t, n in hechos:
        lineas.append(tr('Vida honrada. {capitalize} {v}: {servicios_de} servicios').format(capitalize=(n.capitalize()), v=(RANGOS[p.rango(t)]), servicios_de=(p.servicios_de(t))))
    if j.policia.get("alta") or s.get("serv_policia"):
        pol = j.policia
        lineas.append((tr("Vida honrada. Policía: eres ") + p.rango_policia_txt() if pol.get("alta") else tr("Vida honrada. Fuiste policía"))
                      + tr('. Avisos resueltos: {get}. Detenciones hechas: {get2}').format(get=(s.get('serv_policia', 0)), get2=(s.get('detenidos', 0))) + (tr('. Te quitaron la placa {expulsiones_policia} veces').format(expulsiones_policia=(s['expulsiones_policia'])) if s.get("expulsiones_policia") else ""))
    lineas.append(tr('Vida honrada. Jornadas trabajadas: {servicios_de}. Voluntariado: {get} veces. Donado: {get2} euros. Sucesos resueltos: {get3}').format(servicios_de=(p.servicios_de('jornada')), get=(s.get('voluntariado', 0)), get2=(s.get('donado', 0)), get3=(s.get('eventos', 0))))
    if not p.en_servidor:
        lineas.append(tr("Vida honrada. ") + p.hon_contrato_txt().rstrip(".") + tr('. Títulos: {len}. Evaluaciones buenas: {get} de {get2}. Ascensos: {get3}. Buenas acciones: {get4}').format(len=(len(p.hon_titulos())), get=(s.get('evaluaciones_buenas', 0)), get2=(s.get('evaluaciones', 0)), get3=(s.get('ascensos', 0)), get4=(s.get('buenas_acciones', 0))))
        lineas.append(tr("Tu ficha. ") + p.hon_antecedentes_txt() + tr(' Condenas en total: {get}').format(get=(s.get('antecedentes', 0))))
    lineas.append(tr('Vida delictiva. Vehículos robados: {vehiculos_robados}. Contratos: {get}. Atracos a bancos: {get2}. Territorios: {len}. Detenciones: {detenciones}').format(vehiculos_robados=(s['vehiculos_robados']), get=(s.get('contratos', 0)), get2=(s.get('atracos', 0)), len=(len(j.territorios)), detenciones=(s['detenciones'])))
    if p.modo_adulto():
        lineas.append(tr('Vida delictiva. Mercancía vendida por valor de {get} euros').format(get=(s.get('vendido', 0))))
    app.abrir(Menu(app, tr("Tu carrera"), [Opcion(t, ayuda=tr("Una línea del resumen de tu vida en la partida. Con flecha abajo pasas a la siguiente.")) for t in lineas] + [Opcion(tr("Volver"), lambda: app.cerrar())]))
