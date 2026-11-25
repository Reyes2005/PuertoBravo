"""PR 39: la ficha de un mod en Opciones, Mods, y las mejoras del taller, en el idioma del juego.

- Un mod que llega como componente trae su traducción en data/idiomas/<código>/mods/<mod>.json. El juego la junta con
  su catálogo al cargar el idioma, pero la ficha del mod buscaba solo en el catálogo general y salía en español.
- Las mejoras del taller que añade un mod pasan por tr() al decirse, como los muebles y las mejoras de los negocios.
"""
import json
import types

from juego import gestor_mods, i18n, rutas, sistemas


def test_la_ficha_de_un_mod_usa_la_traduccion_que_trae_el_mod(tmp_path, monkeypatch):
    (tmp_path / "marisma.pbm").write_text(json.dumps({"info": {"nombre": "Marisma de prueba", "descripcion": "Un mod de prueba."}}),
                                          encoding="utf-8")
    monkeypatch.setattr(rutas, "MODS", str(tmp_path))
    monkeypatch.setitem(i18n._estado, "idioma", "vi")
    monkeypatch.setitem(i18n._estado, "textos", {"Marisma de prueba": "Đầm lầy thử", "Un mod de prueba.": "Một mod thử."})
    assert gestor_mods.ficha("marisma.pbm") == ("Đầm lầy thử", "Một mod thử.")
    monkeypatch.setitem(i18n._estado, "textos", {"otra cosa": "khác"})          # sin traducción: tal cual
    assert gestor_mods.ficha("marisma.pbm") == ("Marisma de prueba", "Un mod de prueba.")


def test_las_mejoras_de_un_mod_se_dicen_traducidas(monkeypatch):
    monkeypatch.setitem(sistemas.MEJORAS, "turbo_prueba", {"nombre": "Turbo de prueba", "precio": 100, "desc": "Corre más.",
                                                           "efecto": "", "niveles": 3, "por_nivel": 0.0})
    monkeypatch.setitem(i18n._estado, "idioma", "vi")
    monkeypatch.setitem(i18n._estado, "textos", {"Turbo de prueba": "Turbo thử", "{lower} nivel {n}": "{lower} cấp {n}"})
    v = types.SimpleNamespace(mejoras={"turbo_prueba": 2})
    assert "turbo thử cấp 2" in sistemas.resumen(v)
