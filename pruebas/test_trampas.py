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


def test_bloqueo_en_linea_e_inspector(puente_activo):
    robot, p, _, cli, _, _ = puente_activo
    _llamar_vivo(robot.app, cli, "inspector.escribir", objetivo="jugador", clave="alias", valor="El Jefe")
    assert p.j.alias == "El Jefe"
    campos = _llamar_vivo(robot.app, cli, "inspector.leer", objetivo="jugador")["campos"]
    assert campos["alias"] == "El Jefe"

    p.en_servidor = True
    with pytest.raises(ErrorPuente, match="Bloqueado"):
        _llamar_vivo(robot.app, cli, "jugador.set", dinero=999999)
    p.en_servidor = False


def test_ganchos_y_gui_wx(tmp_path):
    assert instalar_gancho.verificar() == []

    wx = pytest.importorskip("wx")
    try:
        app_wx = wx.App(False)
    except Exception as exc:
        pytest.skip(f"Sin entorno gráfico wx disponible: {exc}")
    from trampas.ventana import VentanaTrampas

    wx.HelpProvider.Set(wx.SimpleHelpProvider())
    v = VentanaTrampas(auto_conectar=False, intervalo_ms=0)
    try:
        assert v.libro.GetPageCount() == 8
    finally:
        v.Close()
        v.Destroy()
        app_wx.ProcessPendingEvents()
        app_wx.Destroy()
