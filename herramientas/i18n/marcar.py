"""Marca para traducir los textos del código: los envuelve en tr() sin cambiar lo que hacen.

    python herramientas\\i18n\\marcar.py carpeta [carpeta...]        reescribe los .py de esas carpetas
    python herramientas\\i18n\\marcar.py --probar archivo.py         enseña lo que haría, sin escribir

Qué hace con cada texto que se dice o se lee:
- «Hola, qué tal» pasa a ser tr("Hola, qué tal").
- f"Tienes {j.dinero} euros" pasa a ser tr("Tienes {dinero} euros").format(dinero=j.dinero): el texto de origen, el que
  se busca en el catálogo de cada idioma, lleva huecos con nombre, para que quien traduce sepa qué va en cada uno.
- Dentro de los huecos de un f-string también se marcan los textos que acaban en la frase ({'día' if n == 1 else 'días'}),
  pero no los que solo se comparan o sirven de clave.

Qué no toca: las cadenas de documentación, los identificadores (palabras sueltas en minúscula), lo que va al registro de
fallos (registro.*, logging, print), las claves de diccionario, lo que se compara o se usa de índice, lo que ya va en tr()
y las órdenes de Windows (las líneas de un .bat, con sus %VARIABLES%, >nul, goto o set): traducidas, cmd.exe no las
entiende, y en la 1.7.3 el instalador de las actualizaciones dejó de funcionar en ruso por eso.
Añade al principio del módulo la importación de tr. Es idempotente: pasarla dos veces no cambia nada.
"""
import ast
import os
import re
import sys

LETRAS = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]")
MAYUS = re.compile(r"[A-ZÁÉÍÓÚÜÑ¿¡]")
SALTAR_LLAMADAS = {"registro", "logging", "log", "logger", "print", "depurar", "tr", "es", "_volcar", "anotar_fallo", "literal"}   # literal(): tal cual, a propósito
SALTAR_ATRIBUTOS = {"info", "aviso", "error", "debug", "warning", "exception", "critical", "anotar", "evento", "fallo", "estado", "tecla_pulsada",
                    "son", "sonar", "cargar_sonido", "get", "setdefault", "pop", "split", "rsplit", "partition",
                    "replace", "strip", "lstrip", "rstrip", "encode", "decode", "lug", "lugar", "persona_social", "dato_adulto", "precio",
                    "frase", "lista", "entero", "seccion", "index", "count", "find", "rfind", "join_path", "data", "carpeta_data", "archivo_config"}


# Una orden de Windows: una línea de .bat, sus variables (%REG%, %~f0, %errorlevel%) o sus redirecciones (>nul, 2>nul).
ORDEN_WINDOWS = re.compile(r"%~|%(?![sdifr]%)[A-Za-z_][A-Za-z0-9_]*%|[12]?>\s*nul\b"                 # %REG%, %~f0, >nul; no %s%s
                           r"|^\s*(?:@echo\b|echo\s|setlocal\b|endlocal\b|set\s+(?:/a\s+)?\"?[A-Za-z_]+\+?=|if\s+(?:not\s+)?(?:exist|errorlevel|%)"
                           r"|goto\s|rmdir\s|rd\s+/|del\s+[\"/%]|mkdir\s|start\s+\"|call\s|chcp\s|\(goto\)|:[a-z_]+$)")


def es_orden_windows(s):
    """¿Es una orden de Windows, de las que van en un .bat? Esas no se traducen nunca."""
    return isinstance(s, str) and bool(ORDEN_WINDOWS.search(s))


def es_texto(s):
    """¿Es un texto para personas? Tiene letras y, además, espacios o mayúsculas. Lo demás son claves."""
    if not isinstance(s, str) or not LETRAS.search(s):
        return False
    if es_orden_windows(s):                                     # una línea de .bat: traducida, cmd.exe no la entiende
        return False
    if re.search(r"%[YmdHMSfjbBaAp]", s) or "(?" in s or s.count("\\") > 1:     # formatos de fecha y expresiones regulares
        return False
    if not LETRAS.search(re.sub(r"%[-+ #0-9.]*[sdifr]|\{[^{}]*\}", "", s)):         # solo huecos: «%s: %s», «{a} {b}»
        return False
    t = s.strip()
    if not t:
        return False
    if "\r\n" in s or "HTTP/" in s or t.startswith("PID ") or re.search(r"[a-z]+[A-Z]\w*$", t) and " " not in t or ":generateContent" in s or t.startswith("urn:"):
        return False                                             # peticiones de red, órdenes de Windows, nombres de funciones de una API
    if " " not in t and (re.search(r"\.[A-Za-z0-9]{2,4}$", t) or re.search(r"[a-z][A-Z]", t)):
        return False                                             # nombres de archivo y de programa: PuertoBravo.exe, LEEME.txt
    if " " in s:                                                 # con espacios, aunque sea « y » u « objetos», es texto
        return True
    if re.fullmatch(r"[a-z0-9_.:/\\\-]+", t):                   # identificadores, rutas, claves
        return False
    if re.fullmatch(r"[A-Z0-9_]+", t):                          # constantes
        return False
    if t.startswith(("http://", "https://", "<", "{")) and " " not in t:
        return False
    return " " in s or bool(MAYUS.search(s))


def _nombre_hueco(expr, usados):
    """Un nombre para el hueco, a partir de la expresión: j.dinero -> dinero; nombre -> nombre; lo demás, v1, v2..."""
    n = None
    if isinstance(expr, ast.Name):
        n = expr.id
    elif isinstance(expr, ast.Attribute):
        n = expr.attr
    elif isinstance(expr, ast.Subscript) and isinstance(expr.slice, ast.Constant) and isinstance(expr.slice.value, str):
        n = expr.slice.value
    elif isinstance(expr, ast.Call):
        f = expr.func
        n = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
    if not n or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n) or n in ("format", "tr", "self", "p", "j"):
        n = "v"
    base, k = n, 1
    while n in usados:
        k += 1
        n = f"{base}{k}"
    return n


class Marcador:
    def __init__(self, src):
        self.src = src
        self.lineas = src.splitlines(keepends=True)
        self.inicio = [0]
        for l in self.lineas:
            self.inicio.append(self.inicio[-1] + len(l))
        self.arbol = ast.parse(src)
        self.padres = {}
        for p in ast.walk(self.arbol):
            for h in ast.iter_child_nodes(p):
                self.padres[id(h)] = p
        self.docs = set()
        for n in ast.walk(self.arbol):
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) \
                    and isinstance(n.body[0].value, ast.Constant) and isinstance(n.body[0].value.value, str):
                self.docs.add(id(n.body[0].value))
        self.cambios = 0

    def pos(self, linea, col):
        """Posición absoluta en caracteres. ast da las columnas en bytes UTF-8."""
        texto = self.lineas[linea - 1]
        return self.inicio[linea - 1] + len(texto.encode("utf-8")[:col].decode("utf-8", "replace"))

    def tramo(self, n):
        return self.pos(n.lineno, n.col_offset), self.pos(n.end_lineno, n.end_col_offset)

    # ---------------------------------------------------------------- ¿se marca?
    def _en_llamada_saltada(self, n):
        p = n
        while id(p) in self.padres:
            hijo, p = p, self.padres[id(p)]
            if isinstance(p, ast.Call):
                f = p.func
                if isinstance(f, ast.Name) and f.id in SALTAR_LLAMADAS:
                    return True
                if isinstance(f, ast.Attribute):
                    raiz = f
                    while isinstance(raiz, ast.Attribute):
                        raiz = raiz.value
                    if isinstance(raiz, ast.Name) and raiz.id in SALTAR_LLAMADAS:
                        return True
                    por_defecto = f.attr in ("get", "setdefault", "pop") and len(p.args) > 1 and hijo is p.args[1]     # .get(clave, "Lo que se dice si no está")
                    if f.attr in SALTAR_ATRIBUTOS and hijo is not f and not por_defecto:     # el texto es argumento; si es de quien llama ({...}.get), se marca
                        return True
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                return False
        return False

    def _contexto_clave(self, n):
        """Se compara, es índice o clave de diccionario: no se traduce."""
        p = self.padres.get(id(n))
        if isinstance(p, ast.Compare):
            return True
        if isinstance(p, ast.Subscript) and p.slice is n:
            return True
        if isinstance(p, ast.Dict) and any(k is n for k in p.keys):
            return True
        if isinstance(p, (ast.Tuple, ast.List, ast.Set)):
            q = self.padres.get(id(p))
            if isinstance(q, ast.Compare):                       # x in ("a b", "c d")
                return True
        if isinstance(p, ast.keyword) and p.arg in ("cat", "clave", "id", "ident", "sonido", "encoding", "errors", "mode", "sep", "end"):
            return True
        if isinstance(p, ast.FormattedValue) and p.format_spec is n:
            return True
        if isinstance(p, ast.JoinedStr):                        # trozo literal de un f-string: lo lleva el f-string entero
            return True
        return False

    def se_marca(self, n):
        if isinstance(n, ast.Constant):
            if not isinstance(n.value, str) or id(n) in self.docs or not es_texto(n.value):
                return False
        elif isinstance(n, ast.JoinedStr):
            literal = "".join(v.value for v in n.values if isinstance(v, ast.Constant))
            if not es_texto(literal):
                return False
            for v in n.values:                                   # f"{x:{ancho}}" o f"{x=}": se deja como está
                if isinstance(v, ast.FormattedValue) and isinstance(v.format_spec, ast.JoinedStr) and any(isinstance(w, ast.FormattedValue) for w in v.format_spec.values):
                    return False
        else:
            return False
        if self._contexto_clave(n) or self._en_llamada_saltada(n):
            return False
        p = self.padres.get(id(n))
        if isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and p.func.id == "tr":
            return False
        if isinstance(p, ast.Attribute) and p.attr == "format":          # "texto {}".format(...): se marca el literal, sigue funcionando
            return True
        return True

    def se_marca_en_hueco(self, n):
        """Dentro del hueco de un f-string: también las palabras sueltas, si acaban en la frase."""
        if not (isinstance(n, ast.Constant) and isinstance(n.value, str) and LETRAS.search(n.value)):
            return False
        if self._contexto_clave(n) or self._en_llamada_saltada(n):
            return False
        p = self.padres.get(id(n))
        if isinstance(p, ast.IfExp) and n is p.test:
            return False
        if isinstance(p, (ast.IfExp, ast.BoolOp, ast.FormattedValue)):
            return True
        if isinstance(p, ast.BinOp) and isinstance(p.op, ast.Add):
            return True
        return False

    # ---------------------------------------------------------------- reescribir
    def texto_de(self, n, en_hueco=False):
        """El código de un nodo, con sus textos ya marcados."""
        if isinstance(n, ast.JoinedStr) and self.se_marca(n):
            return self._fstring(n)
        if isinstance(n, ast.Constant) and (self.se_marca(n) or (en_hueco and self.se_marca_en_hueco(n))):
            a, b = self.tramo(n)
            self.cambios += 1
            return f"tr({self.src[a:b]})"
        a, b = self.tramo(n)
        trozos = []
        for h in self._objetivos(n, en_hueco):
            ha, hb = self.tramo(h)
            trozos.append((ha, hb, self.texto_de(h, en_hueco)))
        out, cur = [], a
        for ha, hb, t in sorted(trozos):
            if ha < cur:
                continue
            out.append(self.src[cur:ha])
            out.append(t)
            cur = hb
        out.append(self.src[cur:b])
        return "".join(out)

    def _objetivos(self, n, en_hueco):
        """Los descendientes más cercanos que hay que reescribir: textos que se marcan y f-strings."""
        r = []
        for h in ast.iter_child_nodes(n):
            if not hasattr(h, "lineno"):
                r += self._objetivos(h, en_hueco)
                continue
            if isinstance(h, ast.JoinedStr) and self.se_marca(h):
                r.append(h)
            elif isinstance(h, ast.Constant) and (self.se_marca(h) or (en_hueco and self.se_marca_en_hueco(h))):
                r.append(h)
            elif isinstance(h, ast.JoinedStr):
                r.append(h)                                      # un f-string que no se marca: sus huecos sí pueden llevar textos
            else:
                if self._tiene_objetivos(h, en_hueco):
                    r.append(h)
        return r

    def _tiene_objetivos(self, n, en_hueco):
        for h in ast.walk(n):
            if h is n:
                continue
            if isinstance(h, ast.JoinedStr):
                return True
            if isinstance(h, ast.Constant) and (self.se_marca(h) or (en_hueco and self.se_marca_en_hueco(h))):
                return True
        return False

    def _fstring(self, n):
        plantilla, args, usados, cache = [], [], set(), {}
        for v in n.values:
            if isinstance(v, ast.Constant):
                plantilla.append(v.value.replace("{", "{{").replace("}", "}}"))
                continue
            codigo = self.texto_de(v.value, en_hueco=True)
            if codigo in cache:
                nombre = cache[codigo]
            else:
                nombre = _nombre_hueco(v.value, usados)
                usados.add(nombre)
                cache[codigo] = nombre
                args.append((nombre, codigo))
            conv = {115: "!s", 114: "!r", 97: "!a"}.get(v.conversion, "")
            spec = ""
            if isinstance(v.format_spec, ast.JoinedStr):
                spec = ":" + "".join(w.value for w in v.format_spec.values if isinstance(w, ast.Constant))
            plantilla.append("{" + nombre + conv + spec + "}")
        t = "".join(plantilla)
        self.cambios += 1
        lit = repr(t)
        if args:
            dentro = ", ".join(f"{k}=({c})" if "\n" not in c else f"{k}=(\n{c})" for k, c in args)
            return f"tr({lit}).format({dentro})"
        return f"tr({lit})"

    def reescribir(self):
        out = self.texto_de(self.arbol_modulo_como_nodo())
        return out

    def arbol_modulo_como_nodo(self):
        m = self.arbol
        m.lineno, m.col_offset = 1, 0
        m.end_lineno = len(self.lineas)
        m.end_col_offset = len(self.lineas[-1].encode("utf-8")) if self.lineas else 0
        return m


def importacion(ruta):
    """Cómo se importa tr desde ese archivo."""
    partes = os.path.normpath(ruta).split(os.sep)
    if len(partes) > 1 and partes[-2] == "servidor":            # el servidor va solo: tiene su propio módulo de idiomas
        return "from .idioma import tr"
    if "juego" in partes[:-1] and partes[partes.index("juego") + 1:-1] == []:
        return "from .i18n import tr"
    return "from juego.i18n import tr"


def poner_importacion(src, linea):
    if re.search(r"^from (\.|juego\.)(i18n|idioma) import (es, )?tr\b", src, re.M):
        return src
    arbol = ast.parse(src)
    cuerpo = arbol.body
    k = 0
    if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(getattr(cuerpo[0], "value", None), ast.Constant):
        k = 1
    while k < len(cuerpo) and isinstance(cuerpo[k], ast.ImportFrom) and cuerpo[k].module == "__future__":
        k += 1
    lineas = src.splitlines(keepends=True)
    if k < len(cuerpo):
        n = cuerpo[k].lineno - 1
    else:
        n = len(lineas)
    lineas.insert(n, linea + "\n")
    return "".join(lineas)


def marcar_archivo(ruta, escribir=True):
    crudo = open(ruta, "rb").read()
    fin = "\r\n" if b"\r\n" in crudo else "\n"                    # se respeta el final de línea de cada archivo
    src = crudo.decode("utf-8").replace("\r\n", "\n")
    if os.path.basename(ruta) in ("i18n.py", "idioma.py", "ed25519.py"):     # ed25519.py es copia exacta de servidor/firma.py
        return 0
    m = Marcador(src)
    nuevo = m.reescribir()
    if not m.cambios:
        return 0
    nuevo = poner_importacion(nuevo, importacion(ruta))
    compile(nuevo, ruta, "exec")                                     # que siga siendo Python válido
    if escribir:
        with open(ruta, "w", encoding="utf-8", newline=fin) as f:
            f.write(nuevo)
    return m.cambios


def main(args):
    if args[:1] == ["--probar"]:
        for r in args[1:]:
            src = open(r, encoding="utf-8").read()
            m = Marcador(src)
            print(m.reescribir())
        return 0
    total = 0
    for carpeta in args:
        for raiz, _d, archivos in os.walk(carpeta):
            if "__pycache__" in raiz:
                continue
            for a in archivos:
                if a.endswith(".py"):
                    r = os.path.join(raiz, a)
                    n = marcar_archivo(r)
                    if n:
                        print(f"{r}: {n}")
                    total += n
    print("Textos marcados:", total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
