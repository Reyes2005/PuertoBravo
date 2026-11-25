"""Pruebas del Menú de Trampas y su puente IPC en tiempo real."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import time

import pytest

from trampas import descubrir_instancias, instalar_gancho
from trampas.protocolo import ClienteTrampas, ErrorPuente
from trampas import puente


def _llamar_vivo(app, cliente: ClienteTrampas, cmd: str, **args):
    """Ejecuta una llamada TCP real contra el puente mientras App.paso drena la cola."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(cliente.llamar, cmd, **args)
        limite = time.monotonic() + 4.0
        while not fut.done() and time.monotonic() < limite:
            app.paso(1 / 60)
            time.sleep(0.002)
        return fut.result(timeout=1.0)


def _conectar_vivo(app, carpeta: str):
    """Ejecuta conectar_auto en segundo plano mientras App.paso atiende el saludo 'hola'."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(ClienteTrampas.conectar_auto, carpeta=carpeta)
        limite = time.monotonic() + 4.0
        while not fut.done() and time.monotonic() < limite:
            app.paso(1 / 60)
            time.sleep(0.002)
        return fut.result(timeout=1.0)


@pytest.fixture
def puente_activo(robot, tmp_path, monkeypatch):
    monkeypatch.setenv("PUERTOBRAVO_TRAMPAS_DIR", str(tmp_path))
    p = robot.nueva_partida()
    srv = puente.iniciar(robot.app, forzar=True, carpeta=str(tmp_path))
    assert srv is not None
    cli, info = _conectar_vivo(robot.app, str(tmp_path))
    yield robot, p, srv, cli, info, tmp_path
    puente.detener(robot.app)


def test_puente_descubrimiento_auth_y_cierre(robot, tmp_path, monkeypatch):
    monkeypatch.setenv("PUERTOBRAVO_TRAMPAS_DIR", str(tmp_path))
    assert getattr(robot.app, "_puente_trampas", None) is None  # apagado por defecto en pruebas

    srv = puente.iniciar(robot.app, forzar=True, carpeta=str(tmp_path))
    instancias = descubrir_instancias(str(tmp_path))
    assert len(instancias) == 1
    assert instancias[0]["pid"] == os.getpid()

    cli_malo = ClienteTrampas(srv.puerto, "token-invalido")
    with pytest.raises(ErrorPuente, match="Token"):
        cli_malo.llamar("hola")

    cli_ok, info = _conectar_vivo(robot.app, str(tmp_path))
    assert info["info"]["pid"] == os.getpid()
    assert info["info"]["en_partida"] is False

    puente.detener(robot.app)
    assert getattr(robot.app, "_puente_trampas", None) is None
    assert descubrir_instancias(str(tmp_path)) == []


def test_catalogos_dinamicos(puente_activo):
    robot, p, _, cli, _, _ = puente_activo
    cat = _llamar_vivo(robot.app, cli, "catalogos")
    assert len(cat["vehiculos"]) >= 39
    assert len(cat["armas"]) >= 28
    assert len(cat["tipos_enemigo"]) >= 10
    assert len(cat["bandas"]) >= 5
    assert len(cat["mapas"]) >= 8
    assert "motor" in cat["mejoras"]
    assert len(cat["objetos"]) >= 5
    assert len(cat["objetos_valor"]) >= 20
    assert len(cat["dias_azar"]) >= 5


def test_jugador_habilidades_y_teletransporte(puente_activo):
    robot, p, _, cli, _, _ = puente_activo
    res = _llamar_vivo(
        robot.app, cli, "jugador.set",
        dinero_delta=5000, banco=12000, salud_max=150, salud=140, blindaje=90,
        hambre=80, sed=70, sueno=60, suciedad=50, carne_puntos=7,
    )
    assert res["jugador"]["dinero"] == 5050
    assert res["jugador"]["banco"] == 12000
    assert res["jugador"]["salud"] == 140.0
    assert p.j.carne_puntos == 7

    _llamar_vivo(robot.app, cli, "jugador.set", accion="llenar_necesidades")
    assert p.j.hambre == 0.0 and p.j.sed == 0.0 and p.j.sueno == 0.0 and p.j.suciedad == 0.0

    hab = _llamar_vivo(robot.app, cli, "jugador.habilidad", habilidad="conduccion", nivel=8)
    assert hab["nivel"] == 8 and p.nivel("conduccion") == 8

    # Teletransporte a otra localidad
    san_lugar = next(l for l in p.lugares.values() if l.mapa == "san_lucero")
    tp = _llamar_vivo(robot.app, cli, "jugador.teletransportar", lugar_id=san_lugar.id)
    assert tp["mapa"] == "san_lucero"
    assert p.mundo.id == "san_lucero"


def test_inventario_completo(puente_activo):
    robot, p, _, cli, _, _ = puente_activo
    _llamar_vivo(robot.app, cli, "inventario.arma", accion="dar", arma_id="fusil", balas=400, silenciador=True, ampliado=True)
    assert "fusil" in p.j.armas
    assert p.j.armas["fusil"]["silenciador"] is True
    assert p.j.armas["fusil"]["ampliado"] is True
    assert p.j.arma == "fusil"

    _llamar_vivo(robot.app, cli, "inventario.arma", accion="quitar", arma_id="fusil")
    assert "fusil" not in p.j.armas
    assert p.j.arma == "punos"

    _llamar_vivo(robot.app, cli, "inventario.objeto", tipo="objeto", id="botiquin", cantidad=5)
    assert p.j.objetos["botiquin"] >= 6

    _llamar_vivo(robot.app, cli, "inventario.objeto", tipo="mochila_grande", valor=True)
    assert p.j.mochila_grande is True

    _llamar_vivo(robot.app, cli, "inventario.objeto", tipo="valor", id="dron", cantidad=1, robado=True)
    assert any(x["id"] == "dron" and x["robado"] for x in p.j.mochila)

    _llamar_vivo(robot.app, cli, "inventario.objeto", tipo="vaciar_robados")
    assert all(not x["robado"] for x in p.j.mochila)


def test_vehiculos_crear_y_editar_aislado(puente_activo):
    robot, p, _, cli, _, _ = puente_activo
    vel_proto_original = p.modelos["sedan"]["vel_max"]

    c1 = _llamar_vivo(
        robot.app, cli, "vehiculos.crear",
        modelo_id="sedan", nombre="Mi Rayo", hacer_mio=True, subir_ahora=True, mejoras_max=True,
    )["vehiculo"]
    assert p.j.veh is not None and p.j.veh.id == c1["id"]
    assert p.j.veh.mio is True

    # Crear un segundo sedan distinto para verificar aislamiento al editar solo este ejemplar
    c2 = _llamar_vivo(
        robot.app, cli, "vehiculos.crear",
        modelo_id="sedan", hacer_mio=False, subir_ahora=False,
    )["vehiculo"]

    edit = _llamar_vivo(
        robot.app, cli, "vehiculos.editar",
        id=c1["id"], solo_este=True, reparar=True, llenar_combustible=True,
        specs={"vel_max": 95.0, "acel": 30.0, "freno": 40.0},
    )["vehiculo"]
    assert edit["vel_max"] == 95.0
    assert p.modelos["sedan"]["vel_max"] == vel_proto_original
    v2 = next(v for v in p.vehiculos if v.id == c2["id"])
    assert v2.modelo["vel_max"] == vel_proto_original

    _llamar_vivo(robot.app, cli, "vehiculos.accion", id=c2["id"], accion="eliminar")
    assert all(v.id != c2["id"] for v in p.vehiculos)


def test_npcs_y_bandas(puente_activo):
    robot, p, _, cli, _, _ = puente_activo
    cre = _llamar_vivo(
        robot.app, cli, "npcs.crear",
        modo="pandillero", clase="pandillero_duro", banda="Los Calaveras",
        arma="escopeta", cantidad=2, salud=120, hostil=True, en_vehiculo=False,
    )
    ids = [x["id"] for x in cre["creados"]]
    assert len(ids) == 2

    ed = _llamar_vivo(robot.app, cli, "npcs.editar", id=ids[0], salud=250, punteria=0.85, hostil=False)["persona"]
    assert ed["salud"] == 250.0 and ed["punteria"] == 0.85 and ed["hostil"] is False

    _llamar_vivo(robot.app, cli, "npcs.accion", id=ids[0], accion="matar")
    assert next(x for x in p.personas if x.id == ids[0]).muerto is True

    _llamar_vivo(robot.app, cli, "npcs.accion", id=ids[0], accion="eliminar")
    assert all(x.id != ids[0] for x in p.personas)

    rep = _llamar_vivo(robot.app, cli, "policia.set", rep_banda={"banda": "Los Calaveras", "valor": 75})
    assert rep["rep_bandas"]["Los Calaveras"] == 75.0


def test_policia_y_eventos(puente_activo):
    robot, p, _, cli, _, _ = puente_activo
    pol = _llamar_vivo(robot.app, cli, "policia.set", estrellas=4)
    assert pol["estrellas"] == 4 and p.j.estrellas == 4

    pol2 = _llamar_vivo(robot.app, cli, "policia.set", estrellas=2)
    assert pol2["estrellas"] == 2 and p.j.estrellas == 2

    _llamar_vivo(robot.app, cli, "policia.set", estrellas=0)
    assert p.j.estrellas == 0

    ev = _llamar_vivo(robot.app, cli, "eventos.lanzar", tipo="suceso_atraco")
    assert ev["evento"] == "atraco" and p.evento is not None

    pers = _llamar_vivo(robot.app, cli, "eventos.lanzar", tipo="persecucion_vehiculo", modelo_id="deportivo", vel_obj=30)
    assert pers["vehiculo"]["ia"] == "huida" and p.gps is not None

    _llamar_vivo(robot.app, cli, "eventos.lanzar", tipo="buscar_pelea", banda="Los Calaveras")
    assert p.guerra is not None and p.guerra["tipo"] == "pelea"
    _llamar_vivo(robot.app, cli, "eventos.lanzar", tipo="terminar_guerra")
    assert p.guerra is None

    tiempo = _llamar_vivo(robot.app, cli, "mundo.set", hora=22, dia=5, lluvia=True, dia_azar="fiesta")
    assert tiempo["dia"] == 5 and tiempo["lluvia"] is True and tiempo["dia_azar"]["id"] == "fiesta"


def test_inspector_generico(puente_activo):
    robot, p, _, cli, _, _ = puente_activo
    _llamar_vivo(robot.app, cli, "inspector.escribir", objetivo="jugador", clave="alias", valor="El Jefe")
    assert p.j.alias == "El Jefe"
    campos = _llamar_vivo(robot.app, cli, "inspector.leer", objetivo="jugador")["campos"]
    assert campos["alias"] == "El Jefe"


def test_anulacion_total_multijugador(puente_activo, tmp_path):
    """En servidor o partida con amigos, el puente cierra socket, borra ficha y anula toda comunicación."""
    robot, p, srv, cli, _, _ = puente_activo

    # 1. Modo servidor (en_servidor = True)
    p.en_servidor = True
    robot.app.paso(1 / 60)
    assert srv._activo is False
    assert srv._sock is None
    assert descubrir_instancias(str(tmp_path)) == []
    with pytest.raises(ErrorPuente):
        cli.llamar("hola")
    with pytest.raises(ErrorPuente):
        cli.llamar("estado")
    with pytest.raises(ValueError, match="multijugador"):
        puente.despachar(robot.app, "hola", {})

    # Vuelve a un jugador: se reanuda automáticamente con nuevo puerto/ficha
    p.en_servidor = False
    robot.app.paso(1 / 60)
    assert srv._activo is True
    assert len(descubrir_instancias(str(tmp_path))) == 1
    cli2, _ = _conectar_vivo(robot.app, str(tmp_path))

    # 2. Modo amigos (anfitrión: p.servidor / invitado: p.red)
    class _FalsoRed:
        conectado = True

    p.red = _FalsoRed()
    robot.app.paso(1 / 60)
    assert srv._activo is False
    assert descubrir_instancias(str(tmp_path)) == []
    with pytest.raises(ErrorPuente):
        cli2.llamar("estado")

    p.red = None
    p.servidor = object()
    robot.app.paso(1 / 60)
    assert srv._activo is False
    assert descubrir_instancias(str(tmp_path)) == []

    p.servidor = None
    robot.app.paso(1 / 60)
    assert srv._activo is True
    assert len(descubrir_instancias(str(tmp_path))) == 1


def test_ganchos_y_gui_wx_sincronizada(puente_activo):
    import threading
    assert instalar_gancho.verificar() == []
    robot, p, srv, _, _, tmp_path = puente_activo

    p.j.dinero = 7777
    p.j.banco = 12345
    p.j.salud = 82.0
    p.j.blindaje = 45.0
    p.j.estrellas = 3
    p.j.hab["conduccion"] = 6000.0
    p.reloj = 15 * 60.0
    p.dia = 9
    p.lluvia = True

    wx = pytest.importorskip("wx")
    try:
        app_wx = wx.App(False)
    except Exception as exc:
        pytest.skip(f"Sin entorno gráfico wx disponible: {exc}")
    from trampas.ventana import VentanaTrampas

    wx.HelpProvider.Set(wx.SimpleHelpProvider())
    v = VentanaTrampas(auto_conectar=False, intervalo_ms=0)
    parar = threading.Event()

    def bombear_puente():
        while not parar.is_set():
            srv.atender()
            time.sleep(0.002)

    hilo = threading.Thread(target=bombear_puente, daemon=True)
    hilo.start()
    try:
        assert v.libro.GetPageCount() == 8
        assert v.conectar(False) is True
        assert v.sp_dinero.GetValue() == 7777
        assert v.sp_banco.GetValue() == 12345
        assert v.sp_salud.GetValue() == 82
        assert v.sp_blindaje.GetValue() == 45
        assert v.sp_estrellas.GetValue() == 3
        assert v.sp_hora.GetValue() == 15
        assert v.sp_dia.GetValue() == 9
        assert v.chk_lluvia.GetValue() is True
    finally:
        parar.set()
        hilo.join(timeout=1.0)
        v.Close()
        v.Destroy()
        app_wx.ProcessPendingEvents()
        app_wx.Destroy()


def test_inspector_blindado_contra_errores_y_sintaxis(puente_activo, monkeypatch):
    import threading
    robot, p, srv, cli, _, _ = puente_activo
    p.j.dinero = 500
    p.j.salud = 90.0
    p.j.objetos["botiquin"] = 2

    dinero_orig = p.j.dinero
    salud_orig = p.j.salud
    objetos_orig = dict(p.j.objetos)
    armas_orig = dict(p.j.armas)
    stats_orig = dict(p.j.stats)
    cfg_orig = dict(robot.app.cfg.v)
    per = p.personas[0]
    per_salud_orig = per.salud
    veh = p.vehiculos[0]
    modelo_orig_ref = veh.modelo

    casos_invalidos = [
        ("jugador", "objetos", '{"botiquin": 5,'),
        ("jugador", "objetos", "{'botiquin': 5}"),
        ("jugador", "objetos", '{"botiquin": "muchos"}'),
        ("jugador", "armas", '{"pistola": 123}'),
        ("jugador", "salud", "NaN"),
        ("jugador", "salud", "inf"),
        ("jugador", "salud", "0"),
        ("jugador", "dinero", "12.5"),
        ("jugador", "dinero", "-10"),
        ("jugador", "atributo_inventado", "123"),
        ("jugador", "_oculto", "1"),
        ("stats", "nueva_stat", "[1, 2,"),
        ("stats", "nueva_stat", "texto sin comillas"),
        ("stats", "nueva_stat", ""),
        ("stats", "nueva_stat", "NaN"),
        ("vehiculo_actual", "vel_max", "abc"),
        ("vehiculo_actual", "vel_max", "-5"),
        ("vehiculo_actual", "campo_inexistente", "42"),
        ("persona", "campo_inexistente", "99"),
        ("cfg", "opcion_inexistente", "true"),
    ]
    for objetivo, clave, valor in casos_invalidos:
        extra = {"id": per.id} if objetivo == "persona" else ({"id": veh.id} if objetivo == "vehiculo_actual" else {})
        with pytest.raises(ErrorPuente) as exc_info:
            _llamar_vivo(robot.app, cli, "inspector.escribir", objetivo=objetivo, clave=clave, valor=valor, **extra)
        assert exc_info.value

    # Verificación estricta: ningún error de sintaxis o validación modificó ni añadió nada
    assert p.j.dinero == dinero_orig
    assert p.j.salud == salud_orig
    assert p.j.objetos == objetos_orig
    assert p.j.armas == armas_orig
    assert {k: v for k, v in p.j.stats.items() if k != "tiempo"} == {k: v for k, v in stats_orig.items() if k != "tiempo"}
    assert "nueva_stat" not in p.j.stats
    assert not hasattr(p.j, "atributo_inventado")
    assert not hasattr(p.j, "_oculto")
    assert not hasattr(veh, "campo_inexistente")
    assert veh.modelo is modelo_orig_ref
    assert per.salud == per_salud_orig
    assert not hasattr(per, "campo_inexistente")
    assert robot.app.cfg.v == cfg_orig

    # Una escritura válida en stats y en objetos sí funciona
    res_stat = _llamar_vivo(robot.app, cli, "inspector.escribir", objetivo="stats", clave="nueva_stat", valor="42")
    assert res_stat["ok"] is True and p.j.stats["nueva_stat"] == 42
    res_obj = _llamar_vivo(robot.app, cli, "inspector.escribir", objetivo="jugador", clave="objetos", valor='{"botiquin": 4}')
    assert res_obj["ok"] is True and p.j.objetos == {"botiquin": 4}

    # También desde la GUI wx: bloquea localmente errores de sintaxis, informa al usuario y no altera el juego
    wx = pytest.importorskip("wx")
    try:
        app_wx = wx.App(False)
    except Exception as exc:
        pytest.skip(f"Sin entorno gráfico wx disponible: {exc}")
    import trampas.ventana as V
    errores_gui = []
    monkeypatch.setattr(V, "mostrar_error", lambda padre, msg, tit="Error": errores_gui.append((tit, msg)))

    wx.HelpProvider.Set(wx.SimpleHelpProvider())
    v = V.VentanaTrampas(auto_conectar=False, intervalo_ms=0)
    parar = threading.Event()

    def bombear():
        while not parar.is_set():
            srv.atender()
            time.sleep(0.002)

    hilo = threading.Thread(target=bombear, daemon=True)
    hilo.start()
    try:
        assert v.conectar(False) is True
        v.sel_insp_obj.SetStringSelection("stats")
        v._leer_inspector()
        stats_antes = dict(p.j.stats)

        v.txt_insp_clave.SetValue("stat_rota")
        v.txt_insp_valor.SetValue('{"x": [1, 2')
        v._escribir_inspector()

        assert len(errores_gui) == 1
        assert "sintaxis" in errores_gui[0][1].lower()
        assert "No se modificó ni añadió nada" in errores_gui[0][1]
        assert v.txt_insp_estado.GetValue() == errores_gui[0][1]
        assert v.txt_insp_valor.GetValue() == '{"x": [1, 2'
        assert {k: val for k, val in p.j.stats.items() if k != "tiempo"} == {k: val for k, val in stats_antes.items() if k != "tiempo"}
        assert "stat_rota" not in p.j.stats
    finally:
        parar.set()
        hilo.join(timeout=1.0)
        v.Close()
        v.Destroy()
        app_wx.ProcessPendingEvents()
        app_wx.Destroy()


def test_servidor_permite_trampas_solo_si_dueno_habilita(puente_activo, tmp_path):
    from servidor import nucleo, opciones
    from test_servidor import mundo

    # 1. Opción del servidor por defecto bloqueada ("no")
    assert opciones.POR_CLAVE["permitir_trampas"].defecto == "no"
    assert opciones.validar_valor("permitir_trampas", "si") == ("si", None)
    assert opciones.validar_valor("permitir_trampas", "no") == ("no", None)

    srv_dir = tmp_path / "srv_datos"
    sv_net = nucleo.Servidor({"datos": str(srv_dir), "puerto": 0, "cifrado": "no", "personajes": 0}, mundo())
    enviados = []
    sv_net._a_todos = lambda m, menos=None: enviados.append(m)

    # Un administrador desde el chat del juego NO puede activar trampas; solo dueño desde consola/panel
    r_chat = sv_net.orden("trampas si", "AdminJuego")
    assert "consola o el panel" in r_chat
    assert sv_net.cfg["permitir_trampas"] == "no"

    r_on = sv_net.orden("trampas si", "consola")
    assert "permitido" in r_on
    assert sv_net.cfg["permitir_trampas"] == "si"
    assert {"t": "trampas", "permitir": True} in enviados

    r_off = sv_net.orden("trampas no", "consola")
    assert "bloqueado" in r_off
    assert sv_net.cfg["permitir_trampas"] == "no"
    assert {"t": "trampas", "permitir": False} in enviados

    # 2. En el juego conectado a un servidor: bloqueado por defecto, habilitado solo si el servidor lo permite
    robot, p, srv, _, _, carpeta_fichas = puente_activo
    p.en_servidor = True
    p.sv = {"info": {"permitir_trampas": False}}
    robot.app.paso(1 / 60)
    assert srv._activo is False
    assert descubrir_instancias(str(carpeta_fichas)) == []
    with pytest.raises(ValueError, match="multijugador"):
        puente.despachar(robot.app, "hola", {})

    # El dueño del servidor permite trampas en vivo (_svm_trampas)
    p._svm_trampas({"t": "trampas", "permitir": True})
    robot.app.paso(1 / 60)
    assert srv._activo is True
    assert len(descubrir_instancias(str(carpeta_fichas))) == 1
    cli, conn_info = _conectar_vivo(robot.app, str(carpeta_fichas))
    assert conn_info["info"]["en_servidor"] is True
    assert conn_info["info"]["trampas_servidor_permitidas"] is True

    antes = p.j.dinero
    res = _llamar_vivo(robot.app, cli, "jugador.set", dinero_delta=250)
    assert res["jugador"]["dinero"] == antes + 250

    # El dueño vuelve a bloquearlas en vivo: anulación inmediata
    p._svm_trampas({"t": "trampas", "permitir": False})
    robot.app.paso(1 / 60)
    assert srv._activo is False
    assert descubrir_instancias(str(carpeta_fichas)) == []
    with pytest.raises(ErrorPuente):
        _llamar_vivo(robot.app, cli, "jugador.set", dinero_delta=100)

    # En modo con amigos (p.servidor / p.red), permanece siempre bloqueado
    p.en_servidor = False
    p.servidor = object()
    p.sv = {"info": {"permitir_trampas": True}}
    robot.app.paso(1 / 60)
    assert srv._activo is False
    assert descubrir_instancias(str(carpeta_fichas)) == []
