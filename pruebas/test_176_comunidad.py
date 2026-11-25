"""La Comunidad de jugadores se pone al día sola (1.7.6, issue 25).

La lista se publica firmada en comunidad.json, junto a componentes.json de cada fuente, con la traducción de sus textos.
El juego la baja en segundo plano, la guarda en data/comunidad_descargada.json y usa la de «revision» más alta entre
esa y la que trae. Sin red, con otra firma o con una revisión más vieja, se queda la que trae.
"""
import copy
import io
import json
import os
import sys

import pytest

from juego import actualizador as A, comunidad, ed25519, i18n, rutas

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import publicar as P  # noqa: E402
import publicar_comunidad as Q  # noqa: E402

SEMILLA = bytes(range(32))
PUBLICA = ed25519.publica(SEMILLA).hex()


def _local():
    with open(os.path.join(rutas.DATOS, "comunidad.json"), encoding="utf-8") as f:
        return json.load(f)


def _publicada(revision, extra_desc="Un servidor nuevo de prueba.", textos=None, semilla=SEMILLA):
    datos = copy.deepcopy({k: v for k, v in _local().items() if not k.startswith("_")})
    datos["revision"] = revision
    sv = next(s for s in datos["secciones"] if s["id"] == "servidores")
    sv["enlaces"].append({"nombre": "Prueba", "idioma": "inglés", "servidor": "puertobravo://prueba.invalid:47820", "desc": extra_desc})
    return P.firmar({"formato": 1, "revision": revision, "datos": datos, "textos": textos or {}}, semilla)


class _Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "CLAVES_PUBLICAS", [PUBLICA])
    monkeypatch.setattr(comunidad, "ruta_descargada", lambda: str(tmp_path / comunidad.DESCARGADA))
    antes = i18n.actual()
    yield tmp_path
    monkeypatch.delenv("PUERTOBRAVO_IDIOMA", raising=False)
    i18n.cargar(antes)


def _abrir(doc, pedidas):
    def abrir(url):
        pedidas.append(url)
        if doc is None:
            raise OSError("sin red")
        return _Respuesta(json.dumps(doc, ensure_ascii=False).encode("utf-8"))
    return abrir


def test_la_lista_trae_el_servidor_de_la_issue_25_y_su_revision():
    d = _local()
    assert int(d["revision"]) >= 2
    servidores = next(s for s in d["secciones"] if s["id"] == "servidores")["enlaces"]
    assert any(e["servidor"] == "puertobravo://posix.live:47820" and e["nombre"] == "Patricus productions" for e in servidores)


def test_la_publicada_lleva_la_traduccion_de_sus_textos():
    doc = Q.construir()
    assert doc["revision"] == int(_local()["revision"]) and "_nota" not in doc["datos"]
    desc = "Un servidor que lleva un jugador. Sus normas las pone quien lo lleva."
    for cod in ("en", "pt", "ru", "vi"):
        assert doc["textos"][cod][desc] and doc["textos"][cod][desc] != desc
    assert "puertobravo://posix.live:47820" not in doc["textos"]["en"]            # las direcciones no se traducen


def test_se_baja_de_junto_a_los_componentes_se_guarda_y_se_usa(entorno, monkeypatch):
    pedidas = []
    doc = _publicada(99, textos={"en": {"Un servidor nuevo de prueba.": "A new test server."}})
    m = comunidad.descargar("servidor", abrir=_abrir(doc, pedidas))
    assert m and m["revision"] == 99
    assert pedidas and all(u.endswith("/componentes/comunidad.json") for u in pedidas)
    assert (entorno / comunidad.DESCARGADA).exists()
    monkeypatch.setenv("PUERTOBRAVO_IDIOMA", "en")
    i18n.cargar("en")
    d = comunidad.cargar()
    sv = next(s for s in d["secciones"] if s["id"] == "servidores")["enlaces"]
    assert sv[-1]["desc"] == "A new test server."                                  # con la traducción que trae
    assert sv[0]["desc"] != "Un servidor que lleva un jugador. Sus normas las pone quien lo lleva."     # y el catálogo, para lo demás


def test_sin_red_con_otra_firma_o_mas_vieja_se_queda_la_que_trae(entorno):
    local = _local()
    assert comunidad.descargar("servidor", abrir=_abrir(None, [])) is None
    otra = _publicada(99, semilla=bytes(32))                                          # firmada con otra clave
    assert comunidad.descargar("servidor", abrir=_abrir(otra, [])) is None
    vieja = _publicada(1)
    assert comunidad.descargar("servidor", abrir=_abrir(vieja, [])) is not None
    d = comunidad.cargar()
    assert sum(len(s["enlaces"]) for s in d["secciones"]) == sum(len(s["enlaces"]) for s in local["secciones"])
    (entorno / comunidad.DESCARGADA).write_text('{"datos": {"revision": 500}}', encoding="utf-8")      # sin firma
    assert comunidad._leer_descargada() is None


def test_una_lista_mas_vieja_no_pisa_la_guardada(entorno):
    comunidad.descargar("servidor", abrir=_abrir(_publicada(50), []))
    comunidad.descargar("servidor", abrir=_abrir(_publicada(40), []))
    assert comunidad._leer_descargada()["revision"] == 50


def test_en_las_pruebas_no_sale_a_internet(entorno):
    class _App:
        pruebas = True
        cfg = {"act_fuente": "servidor", "act_url": ""}
    comunidad.poner_al_dia(_App(), en_segundo_plano=False)
    assert not (entorno / comunidad.DESCARGADA).exists()


def test_la_lista_bajada_no_se_reparte_con_el_juego():
    from herramientas import comprobar_limpio
    assert ("data", "comunidad_descargada.json") in comprobar_limpio.SOLO_DESARROLLO
