"""La traducción brasileña: catálogo, nombres, mensajes, género y guías."""
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys

RAIZ = Path(__file__).resolve().parents[1]
GUIAS = ("manual", "teclas", "cambiar_sonidos", "editor_mods", "servidor")      # las novedades, desde la 1.7.3, solo en español y en inglés
HUECOS = re.compile(r"\{[^{}]*\}")
PORCIENTOS = re.compile(r"%[-+ #0-9.]*[sdifr]")


def _leer(ruta):
    return json.loads((RAIZ / ruta).read_text(encoding="utf-8"))


def _en_portugues(codigo):
    env = dict(os.environ, PUERTOBRAVO_IDIOMA="pt", PYTHONIOENCODING="utf-8",
               SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy", PYGAME_HIDE_SUPPORT_PROMPT="1")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr[-3000:]
    return r.stdout.strip().splitlines()


def test_catalogo_completo_y_sincronizado():
    origen = _leer("traduccion/origen.json")
    trabajo = _leer("traduccion/pt/pt.json")
    instalado = _leer("data/idiomas/pt/textos.json")["textos"]
    assert trabajo["textos"] == instalado
    assert set(origen) == set(instalado)
    assert all(isinstance(v, str) and v.strip() for v in instalado.values())
    assert trabajo["_idioma"]["variante"] == "pt-BR"
    ingles = _leer("data/idiomas/en/textos.json")["textos"]
    for es, pt in instalado.items():
        assert set(HUECOS.findall(pt)) <= set(HUECOS.findall(es)), es
        assert set(HUECOS.findall(ingles[es])) <= set(HUECOS.findall(pt)), es
        assert PORCIENTOS.findall(es) == PORCIENTOS.findall(pt), es
        assert es[:len(es) - len(es.lstrip(" "))] == pt[:len(pt) - len(pt.lstrip(" "))], es
        assert es[len(es.rstrip(" ")):] == pt[len(pt.rstrip(" ")):], es
        if "\t" in es:
            assert pt.rsplit("\t", 1)[-1] == es.rsplit("\t", 1)[-1], es
        if len(es) < 100 and es.count("&") == 1 and "<" not in es:
            assert pt.count("&") == 1, es


def test_el_juego_carga_portugues_y_respeta_los_nombres():
    assert _en_portugues(
        "from juego import i18n, mundo\n"
        "d = mundo.cargar_datos()\n"
        "print(i18n.actual()); print(i18n.tr('Opciones'))\n"
        "print(d['ciudad']['nombre']); print(d['ciudad']['barrios'][0]['nombre'])\n"
        "print(i18n.tr('Dani')); print(i18n.tr('Ganzúas'))\n"
        "print(all(i18n.doc(g).endswith('_pt.html') for g in " + repr(GUIAS) + "))\n"
        "print(i18n.doc('novedades').endswith('novedades_en.html'))\n"
    ) == ["pt", "Opções", "Puerto Bravo", "El Puerto", "Dani", "Gazuas", "True", "True"]


def test_las_distancias_y_el_resumen_de_voz_son_comprensibles():
    assert _en_portugues(
        "from juego import i18n, voz\n"
        "print(i18n.tr('{d} metros').format(d=25))\n"
        "print(i18n.tr('Alcance {_grado}: {_num} metros').format(_grado='curto', _num=40))\n"
        "print(voz.resumir('Você está em Calle Mayor. Pressione F1 para consultar as teclas.'))\n"
    ) == ["25 metros", "Alcance curto: 40 metros", "Você está em Calle Mayor."]


def test_los_nombres_siguen_el_glosario_y_preservan_los_propios():
    cat = _leer("data/idiomas/pt/textos.json")["textos"]
    for nombre, portugues in _leer("traduccion/pt/nombres.json").items():
        if nombre in cat:
            assert cat[nombre] == portugues, nombre
    for nombre, tipo in _leer("traduccion/en/nombres_origen.json").items():
        if tipo in ("localidad", "barrio", "calle", "persona", "personaje") and nombre in cat:
            assert cat[nombre] == nombre, nombre


def test_los_tipos_de_local_se_traducen_sin_cambiar_sus_nombres():
    assert _en_portugues(
        "from juego import i18n, mundo\n"
        "d = mundo.cargar_datos()\n"
        "lugares = {l['id']: l['nombre'] for l in d['ciudad']['lugares']}\n"
        "print(i18n.tr('Cementerio de la Alameda'))\n"
        "print(i18n.tr('Armería El Plomo'))\n"
        "print(i18n.tr('Farmacia Luna'))\n"
        "print(i18n.tr('Banco Mercantil'))\n"
        "print(i18n.tr('Aeropuerto de Bahía del Ocaso'))\n"
        "print('Cemitério da Alameda' in lugares.values())\n"
        "print(i18n.tr('Tercer ejercicio: llevar el coche al Gimnasio El Yunque. Cuando subas, el destino se marca solo. Conduce tú, o pulsa Y y deja que te lleve.'))\n"
    ) == ["Cemitério da Alameda", "Loja de armas El Plomo", "Farmácia Luna", "Banco Mercantil",
          "Aeroporto de Bahía del Ocaso", "True",
          "Terceiro exercício: levar o carro à Academia El Yunque. Ao entrar, o destino é definido automaticamente. Dirija sozinho ou pressione Y e deixe-o levá-lo."]


def test_las_dos_formas_del_protagonista_se_oyen_sin_marcas():
    assert _en_portugues(
        "from juego import genero, i18n\n"
        "t = i18n.tr('Estás agachad[o|a] y por eso vas despacio. Pulsa X para levantarte.')\n"
        "print(genero.resolver(t, 'h')); print(genero.resolver(t, 'm'))\n"
    ) == ["Você está agachado, por isso anda devagar. Pressione X para se levantar.",
          "Você está agachada, por isso anda devagar. Pressione X para se levantar."]


def test_los_mensajes_del_servidor_se_traducen_con_datos_reales():
    assert _en_portugues(
        "from juego import i18n\n"
        "print(i18n.tr_servidor('Dani compra Atlas, en Puerto Bravo.'))\n"
        "from servidor import idioma\n"
        "print(idioma.actual()); print(idioma.tr('Servidor parado. Todo guardado.'))\n"
        "print(idioma.es('Ese vehículo ya no está.'))\n"
    ) == ["Dani compra Atlas, em Puerto Bravo.", "pt", "Servidor parado. Tudo salvo.", "Ese vehículo ya no está."]


def test_las_partidas_se_pueden_cambiar_de_idioma():
    assert _en_portugues(
        "from juego import i18n\n"
        "d = {'nombre': 'Nombre personal', 'objetos': ['First aid kit']}\n"
        "i18n.al_idioma_de_ahora(d, respetar=('nombre',))\n"
        "print(d['nombre']); print(d['objetos'][0])\n"
    ) == ["Nombre personal", "Kit de primeiros socorros"]


class _Documento(HTMLParser):
    def __init__(self):
        super().__init__()
        self.etiquetas, self.enlaces, self.ids = [], [], set()

    def handle_starttag(self, tag, attrs):
        self.etiquetas.append(("", tag))
        a = dict(attrs)
        if "href" in a:
            self.enlaces.append(a["href"])
        if "id" in a:
            self.ids.add(a["id"])

    def handle_endtag(self, tag):
        self.etiquetas.append(("/", tag))


def test_las_guias_no_pierden_contenido_ni_enlaces():
    docs = RAIZ / "data/docs"
    for guia in GUIAS:
        original, traducido = _Documento(), _Documento()
        original.feed((docs / f"{guia}_en.html").read_text(encoding="utf-8"))
        texto = (docs / f"{guia}_pt.html").read_text(encoding="utf-8")
        traducido.feed(texto)
        assert 'lang="pt-BR"' in texto
        assert original.etiquetas == traducido.etiquetas, guia
        for href in traducido.enlaces:
            if ":" in href or href.startswith("//"):
                continue
            archivo, _, fragmento = href.partition("#")
            destino = docs / archivo if archivo else docs / f"{guia}_pt.html"
            assert destino.is_file(), (guia, href)
            if fragmento:
                d = _Documento()
                d.feed(destino.read_text(encoding="utf-8"))
                assert fragmento in d.ids, (guia, href)


def test_el_mod_extra_y_su_paquete_incluyen_portugues():
    en = _leer("traduccion/en/mods/marisma_negra.json")["textos"]
    pt = _leer("traduccion/pt/mods/marisma_negra.json")["textos"]
    assert set(pt) == set(en)
    for es, texto in pt.items():
        assert texto.strip()
        assert set(HUECOS.findall(texto)) <= set(HUECOS.findall(es)), es
    spec = _leer("componentes_extra/mod_marisma_negra/componente.json")
    assert spec["nombres"]["pt"] == "Marisma Negra"
    assert spec["descripciones"]["pt"]
    assert any(a.get("destino") == "data/idiomas/pt/mods/marisma_negra.json" for a in spec["archivos"])


def test_el_glosario_auxiliar_tambien_esta_completo():
    en = {k: v for k, v in _leer("data/idiomas/en/palabras.json").items() if not k.startswith("_")}     # "_del_idioma": las del inglés
    pt = {k: v for k, v in _leer("data/idiomas/pt/palabras.json").items() if not k.startswith("_")}
    assert set(en) == set(pt)
    assert all(isinstance(t, str) and t.strip() for t in pt.values())
    assert pt["cargador"] == "carregador" and pt["derecha"] == "direita"


def test_las_plantillas_html_no_se_rompen_al_regenerar():
    en = _leer("data/idiomas/en/textos.json")["textos"]
    pt = _leer("data/idiomas/pt/textos.json")["textos"]
    for es in pt:
        if not es.startswith("<!DOCTYPE html>"):
            continue
        a, b = _Documento(), _Documento()
        a.feed(en[es])
        b.feed(pt[es])
        assert a.etiquetas == b.etiquetas
        assert 'lang="pt-BR"' in pt[es]
    from herramientas import preparar_carpeta_servidor as carpeta
    assert carpeta.guia_al_dia(str(RAIZ / "data/docs/servidor_pt.html"))


def test_el_paquete_del_servidor_lleva_las_instrucciones_y_el_catalogo(tmp_path):
    from herramientas import preparar_carpeta_servidor as carpeta
    destino = Path(carpeta.preparar(str(tmp_path)))
    assert (destino / "README_pt.txt").is_file()
    assert (destino / "otros_sistemas/README_pt.txt").is_file()
    assert (destino / "documentacion_pt.html").is_file()
    cat = json.loads((destino / "otros_sistemas/servidor/idiomas/pt.json").read_text(encoding="utf-8"))
    assert cat["textos"]["Servidor parado. Todo guardado."] == "Servidor parado. Tudo salvo."


def test_la_referencia_tecnica_conserva_las_etiquetas():
    a, b = _Documento(), _Documento()
    a.feed((RAIZ / "desarrollo/formato_de_los_mods.html").read_text(encoding="utf-8"))
    b.feed((RAIZ / "desarrollo/formato_de_los_mods_pt.html").read_text(encoding="utf-8"))
    assert a.etiquetas == b.etiquetas
    assert "../data/docs/editor_mods_pt.html" in b.enlaces


def test_las_instrucciones_de_ia_piden_portugues_brasileno():
    cat = _leer("data/idiomas/pt/textos.json")["textos"]
    claves = [k for k in cat if k.startswith(("Eres un personaje secundario", "Eres una vecina amable", "Interpretas a una persona corriente"))]
    assert len(claves) == 3
    assert all("português do Brasil" in cat[k] for k in claves)


def test_el_readme_conserva_los_enlaces_y_sus_apartados():
    texto = (RAIZ / "README_pt.md").read_text(encoding="utf-8")
    titulos = re.findall(r"^#{1,6} (.+)$", texto, re.M)
    anclas = {re.sub(r"[^\w\- ]", "", t.lower()).replace(" ", "-") for t in titulos}
    for enlace in re.findall(r"\[[^\]\n]*\]\(([^)\n]*)\)", texto):
        if enlace.startswith("#"):
            assert enlace[1:] in anclas, enlace
        elif ":" not in enlace:
            assert (RAIZ / enlace).is_file(), enlace
