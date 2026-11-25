"""Trabajo 1.7.1, tanda 4: defensa propia, la gente que reacciona y que habla entre sí, la munición y las armas de los
caídos, las patrullas de ronda, las ambulancias, rendirse, el helicóptero de la policía, la guerra de barrios en la
calle y los garajes al reintentar una misión."""
import os

import pygame
import pytest

from juego import calle as C, charla, config, guerra as GU, gente as G, mundo as M, respuestas, rutas, sintesis
from juego.entidades import Persona
from juego.menus import Dialogo, Menu


@pytest.fixture
def datos_de_serie():
    """Deja los números y las frases de la calle como vienen en los datos, por si una prueba los ha cambiado."""
    yield
    M.cargar_datos()


def _empezar(robot, **opciones):
    """Una partida nueva con la calle vacía y sin nada que estorbe: ni sucesos, ni patrullas, ni ambulancias, salvo que la prueba los pida."""
    p = robot.nueva_partida()
    p.cfg["sucesos"] = False
    p.cfg["patrullas_calle"] = False
    p.cfg["ambulancias"] = False
    p.cfg["charla_peatones"] = "nada"
    for k, v in opciones.items():
        p.cfg[k] = v
    p.t_evento = 1e9
    _vaciar(p)
    return p


def _vaciar(p):
    for v in [v for v in p.vehiculos if v is not p.j.veh]:
        p.quitar_vehiculo(v)
    p.personas = []
    p.t_poblar = 1e9                                     # y que no salga nadie más


def _oir(p):
    """Apunta los sonidos que suenan desde ahora."""
    sonados = []
    original = p.son

    def son(nombre, xy=None, **kw):
        sonados.append(nombre)
        return original(nombre, xy=xy, **kw)
    p.son = son
    return sonados


def _persona(p, tipo="civil", dx=6.0, dy=0.0, nombre=None, tono=None, **attrs):
    q = Persona(tipo, *p.mundo.punto_libre(p.pos()[0] + dx, p.pos()[1] + dy), nombre)
    if tono is not None:
        q.tono = tono
    for k, v in attrs.items():
        setattr(q, k, v)
    p.personas.append(q)
    return q


def _enemigo(p, dx=8.0, arma="pistola", **attrs):
    e = _persona(p, "enemigo", dx, nombre="Atracador", arma=arma, hostil=True, estado="ataca", t_disparo=0.05)
    for k, v in attrs.items():
        setattr(e, k, v)
    return e


def _hasta(robot, condicion, segundos=60.0):
    """Deja correr el juego hasta que se cumpla algo. Devuelve si se ha cumplido."""
    for _ in range(int(segundos * 30)):
        if condicion():
            return True
        robot.frames(1)
    return bool(condicion())


def _todo(robot):
    return " | ".join(robot.app.voz.registro)


def _al_descubierto(p):
    """Lleva al jugador al centro de una calle, lejos de las fachadas."""
    m = p.mundo
    i, jj = m._idx(p.j.x, m.NX), m._idx(p.j.y, m.NY)
    p.j.x, p.j.y = i * M.B + 40.0, jj * M.B + 0.5
    assert not p.oculto_del_cielo()


def _a_la_fachada(p):
    """Y lo pega a una pared, bajo el alero."""
    m = p.mundo
    y = p.j.y
    for k in range(60, 95):
        yy = m._idx(y, m.NY) * M.B + k / 10.0
        if m.transitable(p.j.x, yy) and m.superficie(p.j.x, yy + 1.2) == "pared":
            p.j.y = yy
            break
    assert p.oculto_del_cielo(), (p.j.x, p.j.y)


# ------------------------------------------------------------------ 1. defensa propia
def test_defenderte_de_quien_te_ataca_primero_no_es_delito(robot, datos_de_serie):
    p = _empezar(robot, invulnerable=True)
    C.AJUSTES["auxilio_prob"] = 0
    _persona(p, "civil", -8, estado="quieto")                    # un testigo
    e = _enemigo(p)
    robot.frames(30)
    assert e.agresor and "defenderte de quien te ataca no cuenta como delito" in robot.dicho()
    p._ruido_disparo(*p.pos())                                   # disparas para defenderte
    p.danar_persona(e, 999)                                      # y lo tumbas
    assert p.j.puntos_busqueda == 0 and p.j.stats["enemigos"] == 1
    assert robot.dicho().count("no cuenta como delito") == 1     # el aviso, una sola vez por partida
    # a quien has pegado tú primero, no: si luego te ataca, lo suyo no es una agresión
    e2 = _enemigo(p, t_disparo=99.0)
    p.danar_persona(e2, 5)
    e2.t_disparo = 0.05
    robot.frames(30)
    assert not getattr(e2, "agresor", False)
    p.danar_persona(e2, 999)
    assert p.j.puntos_busqueda > 0
    # los enemigos de una misión tampoco: ahí vas tú a por ellos
    e3 = _enemigo(p, tag="mision")
    robot.frames(30)
    assert not getattr(e3, "agresor", False)


def test_sin_la_opcion_todo_es_como_antes(robot, datos_de_serie):
    p = _empezar(robot, invulnerable=True, defensa_propia=False)
    _persona(p, "civil", -8, estado="quieto")
    e = _enemigo(p)
    robot.frames(30)
    assert not getattr(e, "agresor", False)
    p._ruido_disparo(*p.pos())
    assert p.j.puntos_busqueda > 0                               # disparar es delito aunque te estén atacando
    antes = p.j.puntos_busqueda
    p.danar_persona(e, 999)
    assert p.j.puntos_busqueda > antes
    assert config.POR_DEFECTO["defensa_propia"] is True


def test_los_agentes_van_tambien_a_por_el_agresor(robot, datos_de_serie):
    p = _empezar(robot, invulnerable=True)
    C.AJUSTES["auxilio_prob"] = 0
    e = _enemigo(p, 10, salud=30.0)
    a = _persona(p, "policia", 4, nombre="Policía", arma="pistola", hostil=False, estado="quieto", t_disparo=0.2)
    assert _hasta(robot, lambda: e.muerto, 40)
    assert "Policía abate a Atracador" in _todo(robot)
    assert any(f"Policía: {f}" in _todo(robot) for f in C.LISTAS["frases_auxilio"])          # y antes le ha dado el alto
    assert p.j.stats["enemigos"] == 0 and p.j.estrellas == 0 and p.j.puntos_busqueda == 0      # no lo has matado tú, ni es delito tuyo
    assert not p.agente_auxilia(a, 0.03)                         # ya no hay a por quién ir
    # si además te buscan a ti, el agente va a por quien tenga más cerca
    lejos = _enemigo(p, 30, agresor=True, t_disparo=99.0)
    p.j.estrellas = 2
    assert not p.agente_auxilia(a, 0.03)                         # tú estás a 4 metros y el otro a más de 20
    lejos.x, lejos.y = a.x + 1.0, a.y
    assert p.agente_auxilia(a, 0.03)


def test_una_patrulla_acude_a_la_pelea_y_luego_se_va(robot, datos_de_serie):
    p = _empezar(robot, invulnerable=True)
    C.AJUSTES["auxilio_prob"] = 100
    e = _enemigo(p, salud=120.0)
    robot.frames(30)
    patrullas = [v for v in p.vehiculos if v.ia == "policia"]
    assert len(patrullas) == 1 and patrullas[0].auxilio and "una patrulla viene hacia la pelea" in _todo(robot)
    v = patrullas[0]
    assert v.dist(*p.pos()) > 100 and not v.hostil
    assert _hasta(robot, lambda: v.desplegado, 70), v.dist(*p.pos())
    assert v.sirena is not None and "Van a por quien te ha atacado, no a por ti" in _todo(robot)
    agentes = [q for q in p.personas if q.tipo == "policia"]
    assert agentes and all(not q.hostil for q in agentes)
    assert _hasta(robot, lambda: e.muerto, 60)
    assert p.j.estrellas == 0
    assert _hasta(robot, lambda: not v.desplegado, 15)           # sin nadie a quien perseguir, vuelven al coche
    assert not [q for q in p.personas if q.tipo == "policia"] and v.ronda and v.sirena is None


# ------------------------------------------------------------------ 2. la gente reacciona
def test_la_gente_grita_y_se_queja_con_voz_de_hombre_o_de_mujer(robot, datos_de_serie):
    p = _empezar(robot)
    ella, el = _persona(p, tono=1.3), _persona(p, dx=-6, tono=0.85)
    assert C.genero_de(ella) == "m" and C.genero_de(el) == "h"
    son = _oir(p)
    p.asustar(ella, 10, grito=1.0)
    p.asustar(el, 10, grito=1.0)
    assert [s for s in son if s.startswith("grito")] == ["grito_mujer", "grito_hombre"] and ella.estado == el.estado == "huye"
    n = len(robot.app.voz.registro)
    robot.frames(2)
    dicho = robot.app.voz.registro[n:]
    assert len(dicho) == 1 and dicho[0].startswith(tuple(f.format(n=2).rstrip(".") for f in C.LISTAS["frases_huyen"])), dicho      # varios a la vez, una sola frase
    assert dicho[0].rstrip(".").endswith(("norte", "sur", "este", "oeste", "noreste", "noroeste", "sureste", "suroeste"))             # y hacia dónde
    # límite de frecuencia: otro que huye enseguida se oye, pero no se dice
    otro = _persona(p, dy=5, tono=0.9)
    p.asustar(otro, 10, grito=1.0)
    robot.frames(2)
    assert len(robot.app.voz.registro) == n + 1 and son.count("grito_hombre") == 2
    p.asustar(otro, 10, grito=1.0)                               # quien ya huye no vuelve a gritar
    assert son.count("grito_hombre") == 2
    # pasado el tiempo, uno solo: «Una mujer...» o «Un hombre...»
    p.t_reaccion = -99.0
    sola = _persona(p, dy=-5, tono=1.35)
    p.asustar(sola, 10)
    robot.frames(2)
    assert robot.app.voz.registro[-1].startswith("Una mujer")
    # el claxon aparta: frase propia
    p.t_reaccion = -99.0
    uno = _persona(p, dx=3, dy=3, tono=0.9)
    p.asustar(uno, 4, "aparta", grito=0.0)
    robot.frames(2)
    assert robot.app.voz.registro[-1].startswith(tuple(f.format(quien="Un hombre").rstrip(".") for f in C.LISTAS["frases_aparta"]))
    # un golpe: se queja con su voz
    del son[:]
    p.danar_persona(_persona(p, dx=2, tono=1.3), 1)
    p.danar_persona(_persona(p, dx=-2, tono=0.85), 1)
    assert son[0] == "dolor_mujer" and "dolor_npc" in son
    p.j.puntos_busqueda = 0.0                                    # que la agresión no traiga a la policía a esta prueba
    # al presentarse, el nombre va con la voz que ya se le ha oído
    assert charla.ficha(ella)["genero"] == "m" and charla.ficha(el)["genero"] == "h"
    assert charla.ficha(ella)["nombre"] in G.nombres("m") and charla.ficha(el)["nombre"] in G.nombres("h")
    # con la opción apagada se oye, pero no se dice
    p.cfg["frases_reacciones"] = False
    p.t_reaccion = -99.0
    n = len(robot.app.voz.registro)
    del son[:]
    p.asustar(_persona(p, dx=4, tono=1.3), 10, grito=1.0)
    robot.frames(2)
    assert len(robot.app.voz.registro) == n and "grito_mujer" in son


def test_los_disparos_y_el_grito_asustan_con_las_voces_nuevas(robot, datos_de_serie):
    p = _empezar(robot)
    C.AJUSTES["grito_prob"] = 100
    gente = [_persona(p, dx=d, tono=t, estado="pasea") for d, t in ((10, 1.3), (-10, 0.85), (14, 1.25))]
    son = _oir(p)
    p._ruido_disparo(*p.pos())
    assert all(q.estado == "huye" for q in gente) and son.count("grito_mujer") == 2 and son.count("grito_hombre") == 1
    robot.frames(2)
    assert "3 personas" in robot.app.voz.registro[-1]


# ------------------------------------------------------------------ 3. peatones que hablan
def test_al_pasar_junto_a_dos_personas_se_les_oye_hablar(robot, datos_de_serie):
    p = _empezar(robot, charla_peatones="muchas")
    a, b = _persona(p, dx=4, tono=1.3, estado="pasea"), _persona(p, dx=6, tono=0.85, estado="pasea")
    son = _oir(p)
    p.t_charla = 0.0
    n = len(robot.app.voz.registro)
    robot.frames(2)
    dicho = robot.app.voz.registro[n:]
    assert len(dicho) == 1 and "murmullo" in son, dicho
    entradas = tuple(f.split("{")[0] for f in C.LISTAS["frases_charla"] if not f.startswith("{")) + ("Una mujer", "Un hombre")
    assert dicho[0].startswith(entradas) and "{" not in dicho[0] and len(dicho[0]) > 25
    # límite de frecuencia: no vuelve a sonar hasta pasado un rato, y la misma pareja no repite enseguida
    assert p.t_charla >= C.aj("charla_mucho") * 0.7
    p.t_charla = 0.0
    robot.frames(3)
    assert len(robot.app.voz.registro) == n + 1
    # cuánto: «pocas veces» espera bastante más que «a menudo»
    assert C.aj("charla_poco") > C.aj("charla_normal") > C.aj("charla_mucho")
    # en una persecución, o con la opción en «nunca», nadie charla
    c, d = _persona(p, dx=-4, estado="pasea"), _persona(p, dx=-6, estado="pasea")
    p.poner_busqueda(1)
    p.t_policia = 1e9
    robot.frames(2)
    n = len(robot.app.voz.registro)
    p.t_charla = 0.0
    robot.frames(2)
    assert len(robot.app.voz.registro) == n and p.j.estrellas == 1
    p.limpiar_busqueda(False)
    p.cfg["charla_peatones"] = "nada"
    p.t_charla = 0.0
    robot.frames(2)
    assert len(robot.app.voz.registro) == n
    p.cfg["charla_peatones"] = "pocas"
    p.t_charla = 0.0
    robot.frames(2)
    assert len(robot.app.voz.registro) == n + 1 and p.t_charla >= C.aj("charla_poco") * 0.7
    assert c.t_charla == d.t_charla > 0                           # hablaron estos dos: los primeros aún no pueden repetir
    assert config.POR_DEFECTO["charla_peatones"] == "pocas" and set(config.OPCIONES["charla_peatones"]) == set(C.CHARLA)


def test_las_frases_sueltas_salen_de_la_base_de_conversacion(datos_de_serie):
    import random
    respuestas._cargar()
    assert all(t in respuestas._POR_ID for t in C.LISTAS["charla_temas"])          # los temas de los datos existen
    vistas = set()
    for s in range(200):
        rng = random.Random(s)

        class Q:
            pass
        f = charla.ficha(Q(), rng)
        frase = respuestas.suelta(f, {"barrio": "El Puerto", "ciudad": "Puerto Bravo", "hora": "las 9", "tu": ""}, C.LISTAS["charla_temas"], rng)
        assert frase and "{" not in frase and frase[0] == frase[0].upper(), frase
        vistas.add(frase)
        assert "{" not in respuestas.comentario(f, rng)
    assert len(vistas) > 120                                     # mucha variedad: no se oye siempre lo mismo


def test_hay_gente_que_pasea_de_dos_en_dos(robot, datos_de_serie):
    p = _empezar(robot)
    C.AJUSTES["parejas"] = 100
    uno = _persona(p, estado="pasea", bloque=p.mundo.bloque(*p.pos()), u=40.0)
    otro = p.pareja_de_paseo(uno)
    assert otro in p.personas and otro.bloque == uno.bloque and otro.sentido == uno.sentido and otro.vel == uno.vel
    p._pos_perimetro(uno)
    assert otro.dist(uno.x, uno.y) < 3
    C.AJUSTES["parejas"] = 0
    assert p.pareja_de_paseo(uno) is None


# ------------------------------------------------------------------ 4. munición y armas de los caídos
def test_los_enemigos_caidos_sueltan_municion_de_su_arma(robot, datos_de_serie):
    p = _empezar(robot)
    C.AJUSTES["municion_prob"] = 100
    j = p.j
    p.dar_arma("pistola", 10)
    e = _enemigo(p, t_disparo=99.0)
    p.danar_persona(e, 999)
    o = next(o for o in p.objetos if o.tipo == "municion")
    cap = p.armas_d["pistola"]["cargador"]
    assert o.arma == "pistola" and o.nombre == "Munición de " + p.armas_d["pistola"]["nombre"]
    assert max(1, int(cap * 0.4)) <= o.valor <= int(cap * 1.2)
    antes = j.armas["pistola"]["reserva"]
    son = _oir(p)
    j.x, j.y = o.x, o.y
    p._lugares_cercanos(j.x, j.y)                                # se recoge sola al pasar por encima
    assert o not in p.objetos and j.armas["pistola"]["reserva"] == antes + o.valor
    assert "recoger_municion" in son and f"Recoges {o.valor} bala" in robot.dicho()
    # un arma que tú no llevas: no deja nada (la opción de soltar armas viene apagada)
    assert config.POR_DEFECTO["soltar_armas"] is False and config.POR_DEFECTO["soltar_municion"] is True
    p.danar_persona(_enemigo(p, arma="subfusil", t_disparo=99.0), 999)
    assert not [o for o in p.objetos if o.tipo in ("municion", "arma")] and "subfusil" not in j.armas
    # un arma de cuerpo a cuerpo no tiene munición; un rival deportivo o un peatón no sueltan nada
    p.dar_arma("bate")
    p.danar_persona(_enemigo(p, arma="bate", t_disparo=99.0), 999)
    p.danar_persona(_enemigo(p, deportivo=True, t_disparo=99.0), 999)
    p.danar_persona(_persona(p, "civil", arma="pistola"), 999)
    assert not [o for o in p.objetos if o.tipo in ("municion", "arma")]
    # con la munición apagada, nada
    p.cfg["soltar_municion"] = False
    p.danar_persona(_enemigo(p, t_disparo=99.0), 999)
    assert not [o for o in p.objetos if o.tipo in ("municion", "arma")]


def test_con_la_opcion_de_dificultad_sueltan_el_arma_entera(robot, datos_de_serie):
    p = _empezar(robot, soltar_armas=True)
    C.AJUSTES["arma_prob"] = 100
    j = p.j
    p.danar_persona(_enemigo(p, arma="subfusil", t_disparo=99.0), 999)
    o = next(o for o in p.objetos if o.tipo == "arma")
    assert o.arma == "subfusil" and "en el suelo" in o.nombre
    son = _oir(p)
    arma_antes = j.arma
    p.recoger(o)
    cap = p.armas_d["subfusil"]["cargador"]
    assert "subfusil" in j.armas and j.armas["subfusil"]["cargador"] + j.armas["subfusil"]["reserva"] == o.valor and j.armas["subfusil"]["cargador"] <= cap
    assert j.arma == arma_antes and son == ["recoger_municion"] and "Recoges del suelo: " + p.armas_d["subfusil"]["nombre"] in robot.dicho()
    # ya la llevas: del siguiente, solo la munición
    C.AJUSTES["municion_prob"] = 100
    p.danar_persona(_enemigo(p, arma="subfusil", t_disparo=99.0), 999)
    assert [o.tipo for o in p.objetos if o.tipo in ("municion", "arma")] == ["municion"]
    # un arma de cuerpo a cuerpo también se suelta
    p.danar_persona(_enemigo(p, arma="bate", t_disparo=99.0), 999)
    b = next(o for o in p.objetos if o.tipo == "arma")
    p.recoger(b)
    assert "bate" in j.armas and b.valor == 0
    # en un servidor en línea no cuenta
    p.en_servidor = True
    try:
        assert p.soltar_botin(_enemigo(p, arma="rifle", t_disparo=99.0)) is None
    finally:
        p.en_servidor = False


# ------------------------------------------------------------------ 5. patrullas de ronda
def test_hay_patrullas_que_circulan_sin_buscarte(robot, datos_de_serie):
    p = _empezar(robot, patrullas_calle=True)
    assert config.POR_DEFECTO["patrullas_calle"] is True and p.datos["calle"][0]["patrullas"] == 2
    for _ in range(12):
        p._poner_patrullas()
    rondas = [v for v in p.vehiculos if getattr(v, "ronda", False)]
    assert len(rondas) == 2 and all(v.ia == "policia" and v.ocupado and not v.hostil and v.sirena is None for v in rondas)
    assert all(v.dist(*p.pos()) > 100 for v in rondas)           # no aparecen encima
    donde = [(v.x, v.y) for v in rondas]
    p.t_poblar = 0.0
    robot.frames(240)
    p.t_poblar = 1e9
    _ = [p.quitar_vehiculo(v) for v in list(p.vehiculos) if v not in rondas and v is not p.j.veh]
    p.personas = []
    assert all(v in p.vehiculos and v.sirena is None for v in rondas) and p.j.estrellas == 0       # siguen ahí, sin sirena, y nadie te busca
    assert any(abs(v.x - x) + abs(v.y - y) > 20 for v, (x, y) in zip(rondas, donde))              # y se mueven
    # ven los delitos que cometes cerca, y dan pie a las multas de tráfico
    p.delito(2, "prueba")
    lejos = p.j.puntos_busqueda
    v = rondas[0]
    v.x, v.y = p.pos()[0] + 30, p.pos()[1]
    p.cfg["normas_trafico"] = True
    assert p._policia_mirando()
    p.delito(2, "prueba")
    assert lejos == 0 and p.j.puntos_busqueda > 0
    # cuando te buscan, se suman a la persecución
    p.poner_busqueda(2)
    robot.frames(20)
    assert v.hostil and v.sirena is not None
    # de noche hay menos; con cero en los datos, ninguna
    p.limpiar_busqueda(False)
    for u in rondas:
        p.quitar_vehiculo(u)
    C.AJUSTES["patrullas"] = 0
    p.reloj = 12 * 60.0
    for _ in range(6):
        p._poner_patrullas()
    assert not [v for v in p.vehiculos if v.ia == "policia"]
    # con la opción apagada, sin policía, o en un servidor que lleva su propia policía, tampoco
    C.AJUSTES["patrullas"] = 2
    assert p.patrullas_activas()
    p.cfg["patrullas_calle"] = False
    assert not p.patrullas_activas()
    p.cfg["patrullas_calle"], p.cfg["sin_policia"] = True, True
    assert not p.patrullas_activas()
    p.cfg["sin_policia"] = False
    p.en_servidor, p.sv = True, dict(p.sv, info={"policia": True})
    try:
        assert not p.patrullas_activas() and not p.heli_activo() and not p.rendirse()
        assert "la policía la lleva el servidor" in robot.dicho()
    finally:
        p.en_servidor = False


# ------------------------------------------------------------------ 6. ambulancias
def test_tras_un_atropello_acude_una_ambulancia_atiende_y_se_va(robot, datos_de_serie):
    p = _empezar(robot, ambulancias=True)
    C.AJUSTES.update(ambulancia_prob=100, ambulancia_espera_min=1, ambulancia_espera_max=1, ambulancia_atiende=3)
    victima = _persona(p, dx=12)
    p.danar_persona(victima, 999, atropello=True)
    assert p.ambulancia and p.ambulancia["estado"] == "espera"
    salud = p.j.salud
    assert _hasta(robot, lambda: p.ambulancia["estado"] == "viene", 5)
    v = p.ambulancia["veh"]
    assert v.modelo["id"] == "ambulancia" and v.sirena is not None and v.dist(*p.pos()) > 100 and "Se oye una ambulancia" in _todo(robot)
    assert _hasta(robot, lambda: p.ambulancia["estado"] == "atiende", 70), (v.x, v.y, p.ambulancia)
    assert v.sirena is None and v.vel < 1 and "los sanitarios atienden a los heridos" in _todo(robot)
    assert v.dist(victima.x, victima.y) < 60
    # no deja subir
    p.j.x, p.j.y = p.mundo.punto_libre(v.x + 3, v.y + 3)
    if v.dist(p.j.x, p.j.y) <= 5.5:
        p._entrar_salir()
        assert p.j.veh is None and "sanitarios" in robot.dicho()
    assert _hasta(robot, lambda: p.ambulancia["estado"] == "se_va", 10)
    assert victima not in p.personas                             # se llevan a los heridos
    assert _hasta(robot, lambda: p.ambulancia is None, 60)
    assert v not in p.vehiculos and p.j.salud == salud           # y en todo el rato no te ha tocado
    # una cada vez, y con la opción apagada, ninguna
    p.t_ambulancia = 0.0
    p.aviso_ambulancia(*p.pos())
    primera = p.ambulancia
    p.aviso_ambulancia(*p.pos())
    assert primera is not None and p.ambulancia is primera
    p.ambulancia = None
    p.cfg["ambulancias"] = False
    p.aviso_ambulancia(*p.pos())
    assert p.ambulancia is None and config.POR_DEFECTO["ambulancias"] is True


def test_la_ambulancia_espera_a_que_acabe_el_tiroteo(robot, datos_de_serie):
    p = _empezar(robot, ambulancias=True, invulnerable=True)
    C.AJUSTES.update(ambulancia_prob=100, ambulancia_espera_min=1, ambulancia_espera_max=1, auxilio_prob=0)
    malo = _enemigo(p, 12, salud=500.0)
    p.danar_persona(_enemigo(p, 10, t_disparo=99.0), 999)
    robot.frames(120)
    assert p.ambulancia["estado"] == "espera"                    # sigue habiendo tiros: no entran
    malo.muerto = True
    assert _hasta(robot, lambda: p.ambulancia["estado"] == "viene", 5)


# ------------------------------------------------------------------ 7. rendirse
def test_rendirse_con_mucha_busqueda(robot, datos_de_serie):
    p = _empezar(robot)
    j = p.j
    j.dinero = 5000
    p.dar_arma("pistola", 20)
    p.dar_arma("bate")
    assert not p.rendirse() and "Nadie te busca" in robot.dicho()
    p.poner_busqueda(4)
    robot.frames(2)
    assert j.estrellas == 4
    p.t_policia = 1e9                                            # sin patrullas nuevas: solo el agente que ponemos
    assert not p.rendirse() and "No hay ningún agente cerca" in robot.dicho()
    agente = _persona(p, "policia", 16, nombre="Policía", arma="subfusil", hostil=True, estado="ataca", t_disparo=0.05)
    salud, dia, reloj = j.salud, p.dia, p.reloj
    robot.tecla(pygame.K_h, pygame.KMOD_SHIFT)
    assert p.rendido and "Levantas las manos" in robot.dicho() and "Con nivel 4" in robot.dicho()
    multa, horas, todas = p._pena_rendicion(4)
    assert multa == 300 * 4 + 5000 * 5 * 4 // 100 and horas == 8 + 8 * 2 and not todas
    assert _hasta(robot, lambda: isinstance(robot.app.pila[-1], Dialogo), 30)
    assert j.salud == salud                                      # el agente no ha disparado ni una vez
    assert "Policía: " in _todo(robot)
    texto = robot.dicho()
    assert "Te entregas con las manos arriba" in texto and f"sales {horas} horas después, con {multa} euros menos" in texto
    assert j.dinero == 5000 - multa and "pistola" not in j.armas and "bate" in j.armas and j.estrellas == 0
    assert (p.dia - dia) * 1440 + p.reloj - reloj >= horas * 60 - 1 and j.stats["rendiciones"] == 1 and j.stats["detenciones"] == 1
    assert agente not in p.personas and p.rendido is None
    robot.saltar_dialogos()
    # con el nivel más alto se pierde todo
    j.dinero = 1000
    multa5, horas5, todas5 = p._pena_rendicion(5)
    assert todas5 and horas5 == 32 and multa5 == 1000 and "sin las demás armas ni el chaleco" in p.rendicion_txt(5)
    assert "detención corriente" in p.rendicion_txt(1)


def test_rendirse_se_rompe_si_atacas_o_te_mueves_y_con_poca_busqueda_es_una_detencion_normal(robot, datos_de_serie):
    p = _empezar(robot, invulnerable=True)
    j = p.j
    j.dinero = 3000
    p.poner_busqueda(3)
    robot.frames(2)
    p.t_policia = 1e9
    _persona(p, "policia", 40, nombre="Policía", arma="pistola", hostil=True, estado="ataca", t_disparo=5.0)
    assert p.rendirse()
    p.atacar()
    assert p.rendido is None and "vuelven a disparar" in robot.dicho()
    assert not p.rendirse() and "no se fían" in robot.dicho()     # no vale rendirse y romperlo una y otra vez
    p.t_rendicion_rota = -99.0
    assert p.rendirse()
    j.x, j.y = p.mundo.punto_libre(j.x + 3, j.y)
    robot.frames(2)
    assert p.rendido is None and "Te has movido" in robot.dicho()
    p.t_rendicion_rota = -99.0
    assert p.rendirse()
    assert not p.rendirse() and p.rendido is None and "Bajas las manos" in robot.dicho()       # otra pulsación baja las manos
    # con poca búsqueda: lo de siempre, con su multa o su soborno
    p.limpiar_busqueda(False)
    p.personas = []
    p.poner_busqueda(1)
    robot.frames(2)
    p.t_policia = 1e9
    p.t_rendicion_rota = -99.0
    _persona(p, "policia", 8, nombre="Policía", arma="pistola", hostil=True, estado="ataca")
    assert p.rendirse()
    assert _hasta(robot, lambda: isinstance(robot.app.pila[-1], Menu) and robot.app.pila[-1] is not robot.app.pila[0] and "Un agente te ha cogido" in str(robot.app.pila[-1].titulo), 20)


def test_rendirse_tiene_tecla_y_boton(app):
    from juego import ayuda, mando
    teclas = dict(ayuda.TECLAS["general"])
    assert "rendirte" in teclas["Mayúsculas H"]
    assert mando.ACCIONES["rendirse"][1:3] == (pygame.K_h, pygame.KMOD_SHIFT)
    assert mando.POR_DEFECTO["pie_combo"]["lt"] == mando.POR_DEFECTO["coche_combo"]["lt"] == "rendirse"
    assert any("rendirte ante la policía" in linea for linea in app.mando.lineas_ayuda())
    manual = open(os.path.join(rutas.base(), "data", "docs", "manual_es.html"), encoding="utf-8").read()
    assert "Mayúsculas H" in manual and "Rendirse" in manual


# ------------------------------------------------------------------ 8. helicóptero de la policía
def _con_helicoptero(robot, **ajustes):
    p = _empezar(robot, helicoptero_policia=True, invulnerable=True)
    C.AJUSTES.update(helicoptero_llega=1, **ajustes)
    _al_descubierto(p)
    p.poner_busqueda(5)
    robot.frames(3)
    assert p.j.estrellas == 5
    return p


def _sin_policia_de_tierra(p):
    for v in [v for v in p.vehiculos if v.ia == "policia"]:
        p.quitar_vehiculo(v)
    p.personas = [q for q in p.personas if q.tipo != "policia"]
    p.t_policia = 1e9
    p.patrulla_enviada = True


def test_el_helicoptero_viene_apagado_de_serie(robot, datos_de_serie):
    assert config.POR_DEFECTO["helicoptero_policia"] is False
    p = _empezar(robot, invulnerable=True)
    C.AJUSTES["helicoptero_llega"] = 1
    p.poner_busqueda(5)
    robot.frames(150)
    assert p.heli is None and not [v for v in p.vehiculos if getattr(v, "volando", False)]


def test_el_helicoptero_llega_te_localiza_y_no_deja_despistar_a_nadie(robot, datos_de_serie):
    p = _con_helicoptero(robot)
    son = _oir(p)
    assert _hasta(robot, lambda: p.heli is not None, 4)
    v = p.heli["veh"]
    assert p.heli["estado"] == "llega" and v.dist(*p.pos()) > 250 and "Se oye un helicóptero" in _todo(robot)
    assert "helicoptero_policia" in son and v.canal is not None and v.canal.alto == C.aj("helicoptero_altura")      # se le oye, y por encima
    assert v.nombre == "Helicóptero de la policía"
    lejos = v.dist(*p.pos())
    robot.frames(30)
    assert v.dist(*p.pos()) < lejos - 20                         # se acerca
    assert _hasta(robot, lambda: p.heli["estado"] == "vigila", 15)
    assert "megafono" in son and "Por el altavoz: " in _todo(robot) and p.heli_te_tiene()
    assert v in p._objetivos()                                   # se le puede fijar con la Q
    # da vueltas: no se queda quieto, y no se aleja
    _sin_policia_de_tierra(p)
    puntos = []
    for _ in range(8):
        robot.frames(20)
        _sin_policia_de_tierra(p)
        puntos.append((v.x, v.y))
        assert C.aj("helicoptero_radio") - 15 < v.dist(*p.pos()) < C.aj("helicoptero_radio") + 15
    assert max(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a in puntos for b in puntos) > 40
    # sin un solo agente en tierra, con él encima no hay manera de despistar
    for _ in range(30):
        robot.frames(30)
        _sin_policia_de_tierra(p)
    assert p.j.estrellas == 5 and p.t_evasion == 0.0
    # no choca con nada ni nadie se sube a él
    p.j.x, p.j.y = v.x, v.y
    p._entrar_salir()
    assert p.j.veh is None


def test_al_helicoptero_se_le_despista_bajo_techo_y_cambiando_de_vehiculo(robot, datos_de_serie):
    p = _con_helicoptero(robot, helicoptero_pierde=3, helicoptero_reconoce=2, helicoptero_busca=20)
    assert _hasta(robot, lambda: p.heli and p.heli["estado"] == "vigila", 20)
    h = p.heli
    _sin_policia_de_tierra(p)
    # pegado a una fachada: a los pocos segundos te pierde
    _a_la_fachada(p)
    robot.frames(45)
    assert "el helicóptero no te ve" in _todo(robot) and h["estado"] == "vigila"
    assert _hasta(robot, lambda: h["estado"] == "busca", 4)
    assert "te ha perdido de vista" in _todo(robot) and not p.heli_te_tiene()
    # si sales al descubierto tal como te vio, te encuentra
    _al_descubierto(p)
    _sin_policia_de_tierra(p)
    assert _hasta(robot, lambda: h["estado"] == "vigila", 4)
    assert "te ha vuelto a localizar" in _todo(robot)
    # entrar en un edificio te quita de su vista en el acto; un monumento al aire libre, no
    monumento = next(l for l in p.mundo.lugares.values() if l.tipo == "monumento")
    p.entrar_bajo_techo(monumento)
    assert h["estado"] == "vigila"
    p.entrar_bajo_techo(next(l for l in p.mundo.lugares.values() if l.tipo == "tienda"))
    assert h["estado"] == "busca" and "Al entrar bajo techo" in robot.dicho()
    # y si sales con otro vehículo, no te reconoce
    _al_descubierto(p)
    coche = p.crear_vehiculo("sedan", p.j.x, p.j.y, 1, None)
    p._subir(coche, False, callar=True)
    _sin_policia_de_tierra(p)
    for _ in range(5):
        robot.frames(30)
        _sin_policia_de_tierra(p)
        coche.vel = 0.0
    assert p.heli is h and h["estado"] == "busca"
    # pero si un agente de tierra te tiene delante, le canta dónde estás
    _persona(p, "policia", 10, nombre="Policía", arma="pistola", hostil=True, estado="ataca", t_disparo=99.0)
    assert _hasta(robot, lambda: h["estado"] == "vigila", 4)
    # perdido otra vez y sin encontrarte, se retira; y entonces sí se despista a la policía
    p.salir_vehiculo(forzado=True)
    _sin_policia_de_tierra(p)
    _a_la_fachada(p)
    assert _hasta(robot, lambda: h["estado"] == "busca", 6)
    C.AJUSTES["helicoptero_vuelve"] = 600
    assert _hasta(robot, lambda: p.heli is None, 25)
    assert "se retira" in _todo(robot) and h["veh"] not in p.vehiculos
    _sin_policia_de_tierra(p)
    assert _hasta(robot, lambda: p.j.estrellas == 0, 40)
    assert p.heli is None


def test_al_helicoptero_se_le_derriba_con_armas_pesadas_y_tiene_consecuencias(robot, datos_de_serie):
    p = _con_helicoptero(robot)
    j = p.j
    j.dinero = 6000
    assert _hasta(robot, lambda: p.heli and p.heli["estado"] == "vigila", 20)
    v = p.heli["veh"]
    salud = v.salud
    assert salud == C.aj("helicoptero_salud")
    p.danar_vehiculo(v, p.armas_d["pistola"]["dano"] * 0.55)     # con una pistola, nada
    p.danar_vehiculo(v, p.armas_d["subfusil"]["dano"] * 0.55)
    assert v.salud == salud and "hace falta un arma pesada" in robot.dicho()
    p.danar_vehiculo(v, p.armas_d["rifle"]["dano"] * 0.55)       # con un rifle, sí
    assert v.salud < salud
    # un cohete lanzado contra él estalla arriba, donde esté cuando llegue
    antes = v.salud
    p.explosiones.append({"t": 0.1, "x": v.x, "y": v.y, "radio": 10, "dano": 100, "arma": "lanzacohetes", "sigue": v})
    robot.frames(10)
    assert v.salud < antes or p.heli["estado"] == "cae"
    rep, ciu = j.reputacion, j.ciudadania
    while p.heli and p.heli["estado"] != "cae":
        p.danar_vehiculo(v, p.armas_d["rifle"]["dano"] * 0.55)
    assert v not in p.vehiculos and "Has derribado el helicóptero de la policía" in robot.dicho()
    assert j.cargos_helicoptero == 1 and j.stats["helicopteros"] == 1 and j.reputacion > rep and j.ciudadania < ciu
    assert p.t_represalia > p.t + 100                            # la policía tarda el doble en olvidarte
    son = _oir(p)
    assert _hasta(robot, lambda: p.heli is None, 4)
    assert "explosion" in son and p.t_heli > p.t                 # se estrella, y otro tardará en venir
    # el helicóptero se paga al ser detenido
    robot.frames(5)
    dinero = j.dinero
    p.detener(sin_trato=True)
    assert j.dinero <= dinero - C.aj("helicoptero_multa") and j.cargos_helicoptero == 0 and "el helicóptero que derribaste" in robot.dicho()


# ------------------------------------------------------------------ 9. guerra de barrios en la calle
def _menu_territorios(robot, p):
    from juego import menus_extra
    menus_extra.territorios(p)
    m = robot.app.pila[-1]
    assert isinstance(m, Menu)
    return m


def _texto(o):
    return o.texto() if callable(o.texto) else o.texto


def test_con_el_modo_apagado_todo_sigue_desde_el_movil(robot, datos_de_serie):
    assert config.POR_DEFECTO["guerra_calle"] is False
    p = _empezar(robot)
    b = p.mundo.barrio(*p.pos())
    assert not p.guerra_activa() and p.banda_guerra(b) == ""
    sin_banda = next(x for x in p.mundo.barrios if not x.get("banda"))
    assert p.banda_de_barrio(sin_banda) == "" and p.miembro_de_barrio(sin_banda) is None
    m = _menu_territorios(robot, p)
    m.i = next(k for k, o in enumerate(m.opciones) if _texto(o).startswith("Conquistar"))
    robot.tecla(pygame.K_RETURN)
    assert p.mision and p.mision["def"]["id"] == "conquista" and p.guerra is None
    # y matar a pandilleros por la calle no empieza ninguna guerra
    for _ in range(3):
        p.danar_persona(_persona(p, "banda", nombre="Calavera", banda="Los Calaveras", hostil=True), 999)
    assert p.guerra is None


def test_con_el_modo_encendido_cada_barrio_tiene_banda_y_los_suyos_andan_por_la_calle(robot, datos_de_serie):
    import random
    p = _empezar(robot, guerra_calle=True)
    GU.AJUSTES["miembros_prob"] = 100
    bandas = {x["id"]: p.banda_de_barrio(x) for x in p.mundo.barrios}
    assert all(b in G.nombres_bandas() for b in bandas.values()) and len(set(bandas.values())) > 1
    assert bandas == {x["id"]: p.banda_de_barrio(x) for x in p.mundo.barrios}       # siempre la misma en esta partida
    pueblo = next(m for m in p.mapas.values() if m.tipo not in ("ciudad", "mar"))
    assert all(p.banda_guerra(x) == "" for x in pueblo.barrios)                    # fuera de las ciudades no hay guerras
    assert "Territorio de la banda de" in p.barrio_dueno_txt(p.mundo.barrio(*p.pos()))
    random.seed(5)
    p.personas = []
    for _ in range(60):
        p._poblar()
    miembros = [q for q in p.personas if q.tipo == "banda"]
    assert miembros and all(q.hostil and q.banda == p.banda_de_barrio(p.mundo.barrio(q.x, q.y)) for q in miembros)
    assert all(q.arma for q in miembros) and all(q.banda in q.nombre or q.nombre == "Calavera" for q in miembros)
    # en un barrio tuyo no hay nadie de otra banda
    p.j.territorios = [x["id"] for x in p.mundo.barrios]
    p.personas = []
    for _ in range(40):
        p._poblar()
    assert not [q for q in p.personas if q.tipo == "banda"]
    # en un servidor el modo no cuenta
    p.en_servidor = True
    try:
        assert not p.guerra_activa()
    finally:
        p.en_servidor = False


def _ganar_oleadas(robot, p):
    """Juega la guerra entera: espera cada oleada y tumba a todos. Devuelve cuántas oleadas han venido."""
    oleadas = 0
    while p.guerra:
        g = p.guerra
        k = g["oleada"]
        assert _hasta(robot, lambda: p.guerra is None or p.guerra["oleada"] > k, 40), g
        if p.guerra is None:
            break
        oleadas += 1
        assert len(g["vivos"]) == GU.aj("oleada_base") + g["oleada"] - 1 and all(e.tag == "guerra" and e.hostil for e in g["vivos"])
        for e in list(g["vivos"]):
            p.danar_persona(e, 9999)
        robot.frames(3)
    return oleadas


def test_un_barrio_se_conquista_en_la_calle_por_oleadas_con_tu_banda(robot, datos_de_serie):
    p = _empezar(robot, guerra_calle=True, invulnerable=True)
    GU.AJUSTES.update(pausa_min=1, pausa_max=1)
    j = p.j
    j.banda, j.banda_nombre, j.territorios = 2, "Los Mirlos", ["otro_barrio"]
    b = p.mundo.barrio(*p.pos())
    banda = p.banda_de_barrio(b)
    # la primera baja avisa; la segunda empieza la guerra
    p.danar_persona(_persona(p, "banda", nombre=f"Pandillero de {banda}", banda=banda, hostil=True), 999)
    assert p.guerra is None and "una baja más" in robot.dicho()
    p.danar_persona(_persona(p, "banda", nombre=f"Pandillero de {banda}", banda=banda, hostil=True), 999)
    g = p.guerra
    assert g and g["tipo"] == "conquista" and g["barrio"] == b["id"] and g["banda"] == banda and g["total"] == 3
    assert "Son 3 oleadas" in robot.dicho() and len([q for q in p.personas if q.tipo == "aliado"]) == 2       # los tuyos acuden
    assert "Guerra por " + b["nombre"] in p.objetivo_txt()
    dinero = j.dinero
    assert _ganar_oleadas(robot, p) == 3
    assert p.guerra is None and b["id"] in j.territorios and j.stats["conquistas"] == 1
    assert f"{b['nombre']} es tuyo" in _todo(robot) and "Oleada 3 de 3" in _todo(robot) and "Oleada 1 superada" in _todo(robot)
    assert j.dinero >= dinero + GU.aj("premio_conquista")
    assert p.banda_de_barrio(b) == "" and "Territorio tuyo" in p.barrio_dueno_txt(b)


def test_si_sales_del_barrio_o_caes_la_guerra_se_pierde(robot, datos_de_serie):
    p = _empezar(robot, guerra_calle=True, invulnerable=True)
    GU.AJUSTES.update(pausa_min=1, pausa_max=1, fuera_max=4)
    b = p.mundo.barrio(*p.pos())
    assert p.empezar_guerra(b)
    assert _hasta(robot, lambda: p.guerra["oleada"] == 1, 10)
    enemigos = list(p.guerra["vivos"])
    otro = next(l for l in p.mundo.lugares.values() if p.mundo.barrio(l.x, l.y)["id"] != b["id"])
    p.teletransportar(otro.x, otro.y)
    robot.frames(120)
    assert "Has salido de " + b["nombre"] in _todo(robot)
    assert _hasta(robot, lambda: p.guerra is None, 5)
    assert b["id"] not in p.j.territorios and "sigue siendo de" in robot.dicho()
    assert not [e for e in enemigos if e in p.personas]          # y los que venían se retiran
    # caer en mitad de la pelea también la acaba; y empezar una misión
    p.t_guerra_enfria = -99.0
    b2 = p.mundo.barrio(*p.pos())
    assert p.empezar_guerra(b2)
    p.cfg["invulnerable"] = False
    p.morir()
    assert p.guerra is None and b2["id"] not in p.j.territorios


def test_un_barrio_tuyo_se_defiende_entrando_en_el(robot, datos_de_serie):
    p = _empezar(robot, guerra_calle=True, invulnerable=True)
    GU.AJUSTES.update(pausa_min=1, pausa_max=1)
    j = p.j
    b = p.mundo.barrio(*p.pos())
    otro = next(l for l in p.mundo.lugares.values() if p.mundo.barrio(l.x, l.y)["id"] != b["id"] and l.tipo not in ("salida", "embarcadero"))
    j.territorios = [b["id"]]
    aqui = p.pos()
    p.teletransportar(otro.x, otro.y)
    j.amenaza = {"territorio": b["id"], "banda": "Los Cuervos", "dia": p.dia}
    robot.frames(5)
    assert p.guerra is None                                      # mientras no vayas, no pasa nada
    # el móvil ya no defiende: marca el camino
    from juego import sistemas
    ops = sistemas.opciones_sucesos(p, Menu, __import__("juego.menus", fromlist=["Opcion"]).Opcion)
    defender = next(o for o in ops if _texto(o).startswith("Defender"))
    defender.accion()
    assert p.mision is None and p.gps is not None and "la defensa empieza en cuanto entres en el barrio" in robot.dicho()
    p.teletransportar(*aqui)
    robot.frames(3)
    g = p.guerra
    assert g and g["tipo"] == "defensa" and g["banda"] == "Los Cuervos" and g["total"] == 2
    dinero = j.dinero
    assert _ganar_oleadas(robot, p) == 2
    assert j.amenaza is None and b["id"] in j.territorios and j.stats["defensas"] == 1 and j.dinero >= dinero + GU.aj("premio_defensa")
    assert "sigue siendo tuyo" in _todo(robot)


def test_con_el_modo_encendido_el_movil_no_conquista_te_manda_alli(robot, datos_de_serie):
    p = _empezar(robot, guerra_calle=True, invulnerable=True)
    b = p.mundo.barrio(*p.pos())
    m = _menu_territorios(robot, p)
    textos = [_texto(o) for o in m.opciones]
    assert not [t for t in textos if t.startswith("Conquistar")]
    lejos = next(k for k, o in enumerate(m.opciones) if "Se conquista en la calle" in _texto(o))
    m.i = lejos
    robot.tecla(pygame.K_RETURN)
    assert p.guerra is None and p.mision is None and p.gps is not None and "Ve allí" in robot.dicho()
    aqui = next(k for k, o in enumerate(m.opciones) if _texto(o).startswith(b["nombre"] + ":"))
    assert "plantarles cara" in _texto(m.opciones[aqui])
    m.i = aqui
    robot.tecla(pygame.K_RETURN)
    assert p.guerra and p.guerra["barrio"] == b["id"] and robot.app.pila[-1] is p


# ------------------------------------------------------------------ 10. los garajes al reintentar una misión
def _mision_de_prueba(p):
    l = min(p.mundo.lugares.values(), key=lambda l: (l.x - p.j.x) ** 2 + (l.y - p.j.y) ** 2)
    p.teletransportar(l.x, l.y)
    p._empezar_repetible({"id": "prueba_garajes", "titulo": "Prueba", "lugar": l.id,
                          "pasos": [{"tipo": "ir", "lugar": l.id, "texto": "Ve."}, {"tipo": "eliminar", "lugar": l.id, "texto": "A por ellos.", "enemigos": [{"n": 1, "tipo": "Matón", "arma": "pistola", "salud": 60}]}],
                          "recompensa": {"dinero": 1}})
    return p.mision


def _reintentar(robot, p, opcion="Reintentar desde el principio"):
    p.fallar_mision("Prueba.")
    m = robot.app.pila[-1]
    assert isinstance(m, Menu)
    m.i = next(k for k, o in enumerate(m.opciones) if _texto(o).startswith(opcion))
    robot.tecla(pygame.K_RETURN)


@pytest.mark.parametrize("opcion", ["Reintentar desde el principio", "Reintentar desde el último punto de control"])
def test_reintentar_una_mision_no_duplica_el_vehiculo_sacado_del_garaje(robot, datos_de_serie, opcion):
    p = _empezar(robot)
    j = p.j
    casa = next(l for l in p.mundo.lugares.values() if l.tipo == "casa" and int(l.get("garaje", 0)) > 0)
    if casa.id not in j.propiedades:
        j.propiedades.append(casa.id)
    j.garajes[casa.id] = [{"modelo": "sedan", "salud": 100.0, "nombre": "Rayo", "mejoras": {}}]
    j.dinero = 900
    ms = _mision_de_prueba(p)
    robot.frames(3)
    assert ms["paso"] == 1 and ms.get("control")                 # ya has llegado: hay punto de control
    j.dinero = 900
    ms["control"]["copia"]["dinero"] = 900
    en_la_calle = p.crear_vehiculo("utilitario", j.x + 8, j.y, 1, None, "Trueno")
    assert p.hacer_mio(en_la_calle)
    # durante la misión: sacas a Rayo del garaje y guardas a Trueno
    ficha = j.garajes[casa.id].pop(0)
    rayo = p._veh_de_dict(ficha, j.x - 8, j.y)
    assert p.hacer_mio(rayo, callar=True)
    j.garajes[casa.id].append(p._ficha_garaje(en_la_calle))
    p.quitar_vehiculo(en_la_calle)
    j.dinero = 100
    _reintentar(robot, p, opcion)
    assert p.mision and j.dinero == 900                          # lo demás sí vuelve a como estaba
    assert [f["nombre"] for f in j.garajes[casa.id]] == ["Trueno"]                              # Rayo no vuelve al garaje, y Trueno no se pierde
    assert [v.nombre for v in p.vehiculos if p.es_mio(v) and not v.muerto] == ["Rayo"]          # y en la calle hay un solo Rayo
    assert p.mis_en_calle() + p.mis_en_garajes() == 2


# ------------------------------------------------------------------ datos, opciones, editor y sonidos
def test_todo_sale_de_los_datos_y_un_mod_lo_cambia(datos_de_serie):
    d = M.cargar_datos(con_mods=False)
    assert set(d["calle"][0]) == set(C._AJUSTES) | set(C._LISTAS) | {"id"}
    assert set(d["guerra_barrios"][0]) == set(GU._AJUSTES) | set(GU._LISTAS) | {"id"}
    for k, v in C._AJUSTES.items():
        assert C.aj(k) == d["calle"][0][k] == v, k               # lo de serie del código y lo de los datos dicen lo mismo
    for k, v in GU._AJUSTES.items():
        assert GU.aj(k) == d["guerra_barrios"][0][k] == v, k
    C.configurar({"calle": [{"id": "general", "patrullas": 0, "helicoptero_nivel": 4, "megafono": ["Alto."], "reaccion_cada": "mal", "frases_huye": []}]})
    assert C.aj("patrullas") == 0 and C.aj("helicoptero_nivel") == 4 and C.LISTAS["megafono"] == ["Alto."]
    assert C.aj("reaccion_cada") == 8 and C.LISTAS["frases_huye"] == C._LISTAS["frases_huye"]      # lo que viene mal o vacío, lo de serie
    GU.configurar({"guerra_barrios": [{"id": "general", "oleadas": 5, "frases_gana": ["Fuera."]}]})
    assert GU.aj("oleadas") == 5 and GU.LISTAS["frases_gana"] == ["Fuera."]
    C.configurar({})
    GU.configurar({})
    assert C.AJUSTES == C._AJUSTES and GU.AJUSTES == GU._AJUSTES


def test_las_opciones_estan_en_el_menu_con_su_ayuda(robot):
    from juego import menus_juego
    serie = {"defensa_propia": True, "frases_reacciones": True, "charla_peatones": "pocas", "soltar_municion": True, "soltar_armas": False,
             "patrullas_calle": True, "ambulancias": True, "helicoptero_policia": False, "guerra_calle": False,
             "gente_actua": True, "oficio_policia": False,               # las dos últimas, de la tanda 5
             "reconquista": "normal",                                    # y esta, de la tanda 9
             "recoger_al_pasar": True}                                   # y esta, de la 1.7.4 (issue 28)
    for k, v in serie.items():
        assert config.POR_DEFECTO[k] == v, k
    menus_juego.opciones(robot.app)
    m = robot.app.pila[-1]
    m.i = next(k for k, o in enumerate(m.opciones) if _texto(o).startswith("La calle"))
    robot.tecla(pygame.K_RETURN)
    calle = robot.app.pila[-1]
    assert calle is not m and len(calle.opciones) == len(serie) + 1
    for o in calle.opciones[:-1]:
        assert o.ayuda and len(o.ayuda) > 80, _texto(o)
    textos = " | ".join(_texto(o) for o in calle.opciones)
    assert "Gente que habla al pasar: pocas veces" in textos and "Helicóptero de la policía con el nivel de búsqueda más alto: no" in textos
    assert "Modo: guerra de barrios en la calle: no" in textos
    cfg = robot.app.cfg
    calle.i = next(k for k, o in enumerate(calle.opciones) if _texto(o).startswith("Gente que habla"))
    robot.tecla(pygame.K_RIGHT)
    assert cfg["charla_peatones"] == "algunas" and "de vez en cuando" in _texto(calle.opciones[calle.i])
    robot.tecla(pygame.K_LEFT)
    assert cfg["charla_peatones"] == "pocas"


def test_los_sonidos_nuevos_estan_en_todos_los_packs_y_en_la_guia(app):
    from juego import catalogo_sonidos
    nuevos = ["grito_hombre", "grito_mujer", "dolor_mujer", "recoger_municion", "helicoptero_policia", "megafono"]
    for n in nuevos:
        assert n in app.mez.sonidos and catalogo_sonidos.describir(n) != "Sonido del juego.", n
    carpetas = [c for c in os.listdir(rutas.PACKS) if os.path.isdir(os.path.join(rutas.PACKS, c))]
    assert len(carpetas) == 5
    for c in carpetas:
        archivos = sintesis.archivos_de(os.path.join(rutas.PACKS, c))
        for n in nuevos:
            assert n in archivos, (c, n)
            d = sintesis.leer_audio(archivos[n])
            assert len(d) > sintesis.SR * 0.15 and float(abs(d).max()) > 0.05, (c, n)
    assert sintesis.es_bucle("helicoptero_policia") and not sintesis.es_bucle("megafono")
    guia = open(os.path.join(rutas.base(), "data", "docs", "cambiar_sonidos_es.html"), encoding="utf-8").read()
    assert all(n in guia for n in nuevos)


def test_el_editor_edita_la_calle_y_la_guerra_con_formularios_accesibles(datos_de_serie):
    wx = pytest.importorskip("wx")
    from editor import modelo
    from editor.accesibilidad.revision_teclado import informe, revisar_teclado
    from editor.esquema import ESQUEMAS, SECCIONES
    from editor.formulario import DialogoFormulario
    secciones = {s: e for s, _t, e in SECCIONES}
    assert secciones["calle"] == "ajuste_calle" and secciones["guerra_barrios"] == "ajuste_guerra"
    d = M.cargar_datos(con_mods=False)
    for clave in ("calle", "guerra_barrios"):
        campos = {cp["k"]: cp for cp in ESQUEMAS[secciones[clave]]["campos"]}
        assert set(d[clave][0]) == set(campos), set(d[clave][0]) ^ set(campos)
        for k, cp in campos.items():                              # y lo de serie del editor es lo de serie del juego
            if "defecto" in cp and k != "id":
                assert cp["defecto"] == d[clave][0][k], k
    app = wx.GetApp() or wx.App(False)
    wx.HelpProvider.Set(wx.SimpleHelpProvider())
    cat = modelo.Catalogo()
    m = modelo.Mod()
    marco = wx.Frame(None)
    for clave in ("calle", "guerra_barrios"):
        dlg = DialogoFormulario(marco, secciones[clave], dict(d[clave][0]), cat, m)
        problemas = [x for x in revisar_teclado(dlg) if not x.aviso]
        assert not problemas, (clave, informe(problemas))
        dlg.Destroy()
    marco.Destroy()
    assert app is not None
