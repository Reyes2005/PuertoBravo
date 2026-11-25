"""Puente IPC del lado del juego: escucha en 127.0.0.1 y ejecuta comandos en el hilo principal."""
from __future__ import annotations

import json
import math
import os
import queue
import random
import secrets
import socket
import sys
import threading
import time

from . import PROTOCOLO, carpeta_fichas
from .protocolo import MAX_MENSAJE, leer_linea_socket

COMANDOS_LECTURA = {"ping", "hola", "catalogos", "estado", "vehiculos.listar", "npcs.listar", "inspector.leer"}


def _json_seguro(val, profundidad: int = 0):
    """Convierte valores arbitrarios a estructuras serializables en JSON sin fallar."""
    if profundidad > 5:
        return repr(val)
    if val is None or isinstance(val, (bool, int, str)):
        return val
    if isinstance(val, float):
        return val if math.isfinite(val) else str(val)
    if isinstance(val, (list, tuple)):
        return [_json_seguro(x, profundidad + 1) for x in val[:200]]
    if isinstance(val, set):
        return [_json_seguro(x, profundidad + 1) for x in sorted(val, key=str)[:200]]
    if isinstance(val, dict):
        return {str(k): _json_seguro(v, profundidad + 1) for k, v in list(val.items())[:200]}
    return repr(val)


def _en_linea_bloqueado(partida) -> bool:
    if partida is None:
        return False
    if getattr(partida, "en_servidor", False):
        return True
    fn = getattr(partida, "online_activo", None)
    try:
        return bool(fn()) if callable(fn) else False
    except Exception:
        return False


def _convertir_valor(raw, referencia=None):
    """Convierte texto o valor JSON al tipo adecuado, respetando el tipo existente si lo hay."""
    if isinstance(referencia, bool):
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        txt = str(raw).strip().lower()
        if txt in ("1", "true", "si", "sí", "on", "verdadero"):
            return True
        if txt in ("0", "false", "no", "off", "falso"):
            return False
        raise ValueError(f"Valor booleano no válido: {raw!r}")
    if isinstance(referencia, int) and not isinstance(referencia, bool):
        return int(float(raw))
    if isinstance(referencia, float):
        return float(raw)
    if isinstance(referencia, (list, dict)) and isinstance(raw, str):
        parsed = json.loads(raw)
        if isinstance(referencia, list) and not isinstance(parsed, list):
            raise ValueError("Se esperaba una lista JSON.")
        if isinstance(referencia, dict) and not isinstance(parsed, dict):
            raise ValueError("Se esperaba un objeto JSON.")
        return parsed
    if isinstance(raw, str):
        txt = raw.strip()
        if txt.lower() in ("true", "false", "null") or (txt.startswith(("{", "[")) and txt.endswith(("}", "]"))):
            try:
                return json.loads(txt.lower() if txt.lower() in ("true", "false", "null") else txt)
            except ValueError:
                pass
    return raw


def _info_vehiculo(p, v) -> dict:
    mo = getattr(v, "modelo", None) or {}
    px, py = p.pos()
    return {
        "id": int(getattr(v, "id", 0)),
        "modelo_id": str(mo.get("id", "")),
        "modelo_nombre": str(mo.get("nombre", "")),
        "nombre": str(getattr(v, "nombre", "")),
        "es_actual": v is p.j.veh,
        "mio": bool(getattr(v, "mio", False)),
        "propio": bool(getattr(v, "propio", False)),
        "ia": getattr(v, "ia", None),
        "tag": getattr(v, "tag", None),
        "salud": round(float(getattr(v, "salud", 0.0)), 2),
        "salud_max": round(float(getattr(v, "salud_max", 1.0)), 2),
        "vel": round(float(getattr(v, "vel", 0.0)), 2),
        "vel_obj": round(float(getattr(v, "vel_obj", 0.0)), 2),
        "vel_max": float(mo.get("vel_max", 0.0)),
        "acel": float(mo.get("acel", 0.0)),
        "freno": float(mo.get("freno", 0.0)),
        "barco": bool(mo.get("barco", False)),
        "vuela": bool(mo.get("vuela", False)),
        "sirena": mo.get("sirena"),
        "mejoras": dict(getattr(v, "mejoras", {}) or {}),
        "litros": getattr(v, "litros", None),
        "queroseno": getattr(v, "queroseno", None),
        "km": round(float(getattr(v, "km", 0.0)), 2),
        "pinchada": bool(getattr(v, "pinchada", False)),
        "revision_debida": bool(getattr(v, "revision_debida", False)),
        "ardiendo": round(float(getattr(v, "ardiendo", -1.0)), 2),
        "hostil": bool(getattr(v, "hostil", False)),
        "cerrado": bool(getattr(v, "cerrado", False)),
        "x": round(float(getattr(v, "x", 0.0)), 2),
        "y": round(float(getattr(v, "y", 0.0)), 2),
        "rumbo": round(float(getattr(v, "rumbo", 0.0)), 1),
        "dist": round(float(v.dist(px, py)), 1),
    }


def _info_persona(p, per) -> dict:
    px, py = p.pos()
    ficha = getattr(per, "ficha", None)
    d = {
        "id": int(getattr(per, "id", 0)),
        "tipo": str(getattr(per, "tipo", "")),
        "nombre": str(getattr(per, "nombre", "")),
        "salud": round(float(getattr(per, "salud", 0.0)), 2),
        "arma": getattr(per, "arma", None),
        "punteria": round(float(getattr(per, "punteria", 0.42)), 3),
        "vel": round(float(getattr(per, "vel", 1.3)), 2),
        "hostil": bool(getattr(per, "hostil", False)),
        "estado": str(getattr(per, "estado", "")),
        "banda": getattr(per, "banda", None),
        "clase": getattr(per, "clase", None),
        "tag": getattr(per, "tag", None),
        "agresor": bool(getattr(per, "agresor", False)),
        "provocado": bool(getattr(per, "provocado", False)),
        "de_banda": bool(getattr(per, "de_banda", False)),
        "muerto": bool(getattr(per, "muerto", False)),
        "x": round(float(getattr(per, "x", 0.0)), 2),
        "y": round(float(getattr(per, "y", 0.0)), 2),
        "dist": round(float(per.dist(px, py)), 1),
    }
    if isinstance(ficha, dict):
        d["ficha"] = {
            "edad": ficha.get("edad"),
            "oficio": ficha.get("oficio"),
            "caracter": ficha.get("caracter"),
            "confianza": ficha.get("confianza"),
            "genero": ficha.get("genero"),
            "ofendido": ficha.get("ofendido"),
        }
    return d


def _buscar_vehiculo(p, vid):
    if vid in (None, "", "actual"):
        return p.j.veh
    try:
        vid_int = int(vid)
    except (TypeError, ValueError):
        return None
    return next((v for v in p.vehiculos if v.id == vid_int), None)


def _buscar_persona(p, pid):
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return None
    return next((per for per in p.personas if per.id == pid_int), None)


def _asegurar_modelo_propio(p, v):
    """Clona v.modelo si apunta al diccionario compartido de partida.modelos."""
    mid = v.modelo.get("id")
    compartido = p.modelos.get(mid)
    if compartido is None or v.modelo is compartido:
        v.modelo = dict(v.modelo)


def _set_estrellas(p, nivel: int, limpiar_policias: bool = True) -> dict:
    from juego.combate import UMBRAL

    j = p.j
    nivel = max(0, min(5, int(nivel)))
    if nivel == 0:
        if limpiar_policias:
            p._fin_persecucion()
        else:
            p.limpiar_busqueda(hablar=False)
        return {"estrellas": j.estrellas, "puntos_busqueda": j.puntos_busqueda}
    p.cfg["sin_policia"] = False
    j.puntos_busqueda = float(UMBRAL[nivel - 1])
    j.estrellas = nivel
    if not any(v.ia == "policia" and not v.muerto for v in p.vehiculos):
        p.t_policia = 0.2
        p.patrulla_enviada = False
    for v in p.vehiculos:
        if v.ia == "policia":
            v.hostil = True
    for per in p.personas:
        if per.tipo == "policia" and not per.muerto:
            per.hostil = True
            per.estado = "ataca"
    return {"estrellas": j.estrellas, "puntos_busqueda": j.puntos_busqueda}


def _recolectar_catalogos(app) -> dict:
    from juego import azar, config, extras2, gente, mochila, sistemas

    datos = getattr(app, "datos", None) or {}
    mapas_dict = getattr(app, "mapas", None) or {}
    vehiculos = [
        {
            "id": str(v.get("id", "")),
            "nombre": str(v.get("nombre", v.get("id", ""))),
            "vel_max": float(v.get("vel_max", 0.0)),
            "acel": float(v.get("acel", 0.0)),
            "freno": float(v.get("freno", 0.0)),
            "salud": float(v.get("salud", 100.0)),
            "precio": v.get("precio"),
            "barco": bool(v.get("barco", False)),
            "vuela": bool(v.get("vuela", False)),
            "trabajo": v.get("trabajo"),
            "sirena": v.get("sirena"),
            "motor": v.get("motor"),
        }
        for v in datos.get("vehiculos", [])
        if isinstance(v, dict) and v.get("id")
    ]
    armas = [
        {
            "id": str(a.get("id", "")),
            "nombre": str(a.get("nombre", a.get("id", ""))),
            "tipo": str(a.get("tipo", "fuego")),
            "dano": float(a.get("dano", 0.0)),
            "alcance": float(a.get("alcance", 0.0)),
            "cadencia": float(a.get("cadencia", 1.0)),
            "precision": float(a.get("precision", 1.0)),
            "cargador": int(a.get("cargador") or 0),
            "automatica": bool(a.get("automatica", False)),
            "precio": int(a.get("precio") or 0),
        }
        for a in datos.get("armas", [])
        if isinstance(a, dict) and a.get("id")
    ]
    objetos = [
        {"id": str(o.get("id", "")), "nombre": str(o.get("nombre", o.get("id", ""))), "precio": int(o.get("precio") or 0)}
        for o in datos.get("objetos", [])
        if isinstance(o, dict) and o.get("id")
    ]
    ids_obj = {o["id"] for o in objetos}
    for extra_id, extra_nom in (("bidon", "Bidón de gasolina"), ("rueda", "Rueda de repuesto")):
        if extra_id not in ids_obj:
            objetos.append({"id": extra_id, "nombre": extra_nom, "precio": 0})
    adultos = datos.get("adultos") if isinstance(datos.get("adultos"), dict) else {}
    sustancias = [
        {"id": str(s.get("id", "")), "nombre": str(s.get("nombre", s.get("id", ""))), "legal": bool(s.get("legal", False))}
        for s in (adultos.get("sustancias") or datos.get("sustancias") or [])
        if isinstance(s, dict) and s.get("id")
    ]
    productos = [
        {"id": str(pr.get("id", "")), "nombre": str(pr.get("nombre", pr.get("id", ""))), "precio": pr.get("precio")}
        for pr in datos.get("productos", [])
        if isinstance(pr, dict) and pr.get("id")
    ]
    mapas = []
    for mid, m in mapas_dict.items():
        barrios = [{"id": str(b.get("id", "")), "nombre": str(b.get("nombre", b.get("id", "")))} for b in getattr(m, "barrios", [])]
        lugares = [
            {
                "id": str(l.id),
                "nombre": str(l.nombre),
                "tipo": str(l.tipo),
                "x": round(float(l.x), 1),
                "y": round(float(l.y), 1),
                "precio": l.get("precio"),
            }
            for l in getattr(m, "lugares", {}).values()
        ]
        lugares.sort(key=lambda x: x["nombre"].lower())
        mapas.append({"id": str(mid), "nombre": str(m.nombre), "tipo": str(m.tipo), "barrios": barrios, "lugares": lugares})
    mapas.sort(key=lambda x: x["nombre"].lower())

    cfg_ops = {}
    for k, val in config.POR_DEFECTO.items():
        cfg_ops[k] = {
            "tipo": type(val).__name__,
            "opciones": list(config.OPCIONES[k]) if k in config.OPCIONES else None,
        }

    return {
        "vehiculos": vehiculos,
        "armas": armas,
        "mejoras": {str(k): dict(v) for k, v in sistemas.MEJORAS.items()},
        "objetos": objetos,
        "objetos_valor": [dict(v) for v in mochila.CATALOGO.values()],
        "productos": productos,
        "sustancias": sustancias,
        "bandas": [dict(b) for b in gente.BANDAS],
        "tipos_enemigo": [dict(t) for t in gente.TIPOS.values()],
        "caracteres": {str(k): dict(v) for k, v in gente.CARACTERES.items()},
        "cajas_locales": {str(k): dict(v) for k, v in gente.CAJAS.items()},
        "dias_azar": [{"id": ident, "texto": texto} for ident, _, texto, _ in azar.DIAS],
        "mapas": mapas,
        "habilidades": {k: {"nombre": v[0], "desc": v[1]} for k, v in extras2.HABILIDADES.items()},
        "logros": [{"id": ident, "nombre": nom, "desc": desc} for ident, nom, desc, _ in extras2.LOGROS],
        "cfg_opciones": cfg_ops,
    }


def _recolectar_estado(app) -> dict:
    p = getattr(app, "partida", None)
    cima = app.pila[-1] if getattr(app, "pila", None) else None
    base = {
        "en_partida": p is not None,
        "pantalla": type(cima).__name__ if cima is not None else "ninguna",
        "cfg": _json_seguro(getattr(getattr(app, "cfg", None), "v", {})),
    }
    if p is None:
        return base
    j = p.j
    px, py = p.pos()
    barrio = p.mundo.barrio(px, py)
    habs = {k: {"xp": round(float(j.hab.get(k, 0.0)), 1), "nivel": p.nivel(k)} for k in j.hab}
    base.update({
        "en_linea": _en_linea_bloqueado(p),
        "mapa": {"id": p.mundo.id, "nombre": p.mundo.nombre, "tipo": p.mundo.tipo, "barrio_id": barrio.get("id"), "barrio": barrio.get("nombre")},
        "pos": {"x": round(float(px), 2), "y": round(float(py), 2), "rumbo": round(float(j.rumbo), 1)},
        "tiempo": {"dia": int(p.dia), "reloj": round(float(p.reloj), 2), "hora_txt": p.hora_txt(), "lluvia": bool(p.lluvia), "dia_azar": getattr(p, "dia_azar", {})},
        "jugador": {
            "nombre": j.nombre,
            "apellido": j.apellido,
            "salud": round(float(j.salud), 2),
            "salud_max": round(float(j.salud_max), 2),
            "blindaje": round(float(j.blindaje), 2),
            "dinero": int(j.dinero),
            "banco": int(j.banco),
            "foco": round(float(j.foco), 2),
            "animo": round(float(j.animo), 2),
            "ciudadania": round(float(j.ciudadania), 2),
            "reputacion": round(float(j.reputacion), 2),
            "hambre": round(float(j.hambre), 2),
            "sed": round(float(j.sed), 2),
            "sueno": round(float(j.sueno), 2),
            "suciedad": round(float(j.suciedad), 2),
            "carne_puntos": int(j.carne_puntos),
            "cocina_practica": round(float(j.cocina_practica), 1),
            "estrellas": int(j.estrellas),
            "puntos_busqueda": round(float(j.puntos_busqueda), 2),
            "arma": j.arma,
            "armas": _json_seguro(j.armas),
            "objetos": _json_seguro(j.objetos),
            "mochila": _json_seguro(j.mochila),
            "mochila_grande": bool(j.mochila_grande),
            "sustancias": _json_seguro(j.sustancias),
            "encima": _json_seguro(j.encima),
            "hab": habs,
            "rep_bandas": _json_seguro(j.rep_bandas),
            "territorios": list(j.territorios),
            "propiedades": list(j.propiedades),
            "banda": int(j.banda),
            "banda_nombre": j.banda_nombre,
            "alias": j.alias,
            "guardaespaldas": int(j.guardaespaldas),
            "perro": j.perro,
            "perro_hambre": round(float(j.perro_hambre), 1),
            "perro_confianza": round(float(j.perro_confianza), 1),
            "perro_en_casa": bool(j.perro_en_casa),
            "antecedentes": _json_seguro(j.antecedentes),
            "logros": list(j.logros),
            "stats": _json_seguro(j.stats),
        },
        "vehiculo_actual": _info_vehiculo(p, j.veh) if j.veh is not None else None,
        "conteos": {
            "vehiculos": len(p.vehiculos),
            "personas": len(p.personas),
            "objetos": len(p.objetos),
            "misiones_completadas": len(p.completadas),
            "mision_activa": p.mision["def"]["id"] if p.mision else None,
            "evento_activo": p.evento["tipo"] if p.evento else None,
            "guerra_activa": p.guerra["tipo"] if p.guerra else None,
            "heli_activo": p.heli["estado"] if p.heli else None,
        },
    })
    return base


def _punto_spawn_vehiculo(p, mo: dict):
    px, py = p.pos()
    if mo.get("vuela"):
        x, y = p.mundo.punto_libre(px + 6.0, py + 6.0)
        return x, y, 0
    if mo.get("barco") or p.mundo.tipo == "mar":
        for d in (12, 20, 30, 45):
            for ang in (0, 90, 180, 270):
                rx = px + math.sin(math.radians(ang)) * d
                ry = py + math.cos(math.radians(ang)) * d
                if p.mundo.superficie(rx, ry) == "agua":
                    return rx, ry, 0
        return p.mundo.punto_libre(px + 10.0, py + 10.0)[0], p.mundo.punto_libre(px + 10.0, py + 10.0)[1], 0
    x, y, d = p.plaza_cercana()
    if any(not o.muerto and o.dist(x, y) < 4.5 for o in p.vehiculos):
        x, y, d = p._plaza_al_lado(px, py)
    return x, y, d


def despachar(app, cmd: str, args: dict | None = None):
    """Ejecuta un comando del puente sobre la instancia viva de App y Partida."""
    args = args or {}
    from juego import VERSION, azar, config, gente, mochila, sistemas
    from juego.entidades import Objeto, Persona, Vehiculo

    p = getattr(app, "partida", None)

    if cmd in ("ping", "hola"):
        return {
            "proto": PROTOCOLO,
            "version": VERSION,
            "pid": os.getpid(),
            "en_partida": p is not None,
            "en_linea": _en_linea_bloqueado(p),
        }

    if cmd == "catalogos":
        return _recolectar_catalogos(app)

    if cmd == "estado":
        return _recolectar_estado(app)

    if cmd == "cfg.set":
        if _en_linea_bloqueado(p):
            raise ValueError("Bloqueado en servidores o partidas en línea.")
        cambios = args.get("cambios")
        if not isinstance(cambios, dict):
            cambios = {args["clave"]: args["valor"]} if "clave" in args else {}
        aplicados = {}
        adultos_antes = app.cfg["adultos"]
        for clave, val in cambios.items():
            if clave not in app.cfg.v:
                raise ValueError(f"Opción desconocida en cfg: {clave}")
            conv = _convertir_valor(val, config.POR_DEFECTO.get(clave, app.cfg.v[clave]))
            if clave in config.OPCIONES and conv not in config.OPCIONES[clave]:
                raise ValueError(f"Valor no permitido para {clave}: {conv}")
            app.cfg[clave] = conv
            aplicados[clave] = conv
        if "adultos" in aplicados and app.cfg["adultos"] != adultos_antes:
            app.aplicar_adultos()
        return {"aplicados": aplicados}

    if p is None:
        raise ValueError("No hay ninguna partida cargada en este momento.")

    if cmd == "vehiculos.listar":
        px, py = p.pos()
        lista = [_info_vehiculo(p, v) for v in p.vehiculos if not v.muerto]
        lista.sort(key=lambda x: (not x["es_actual"], x["dist"]))
        return {"vehiculos": lista, "garajes": _json_seguro(p.j.garajes)}

    if cmd == "npcs.listar":
        lista = [_info_persona(p, per) for per in p.personas]
        lista.sort(key=lambda x: (x["muerto"], x["dist"]))
        return {"personas": lista}

    if cmd == "inspector.leer":
        objetivo = args.get("objetivo", "jugador")
        if objetivo == "jugador":
            d = p.j.a_dict()
            return {"objetivo": objetivo, "campos": _json_seguro(d)}
        if objetivo == "stats":
            return {"objetivo": objetivo, "campos": _json_seguro(p.j.stats)}
        if objetivo == "cfg":
            return {"objetivo": objetivo, "campos": _json_seguro(app.cfg.v)}
        if objetivo in ("vehiculo", "vehiculo_actual"):
            v = _buscar_vehiculo(p, args.get("id"))
            if v is None:
                raise ValueError("Vehículo no encontrado.")
            campos = {k: val for k, val in v.__dict__.items() if k not in ("canal", "sirena", "alarma", "fuego", "pasajeros")}
            return {"objetivo": "vehiculo", "id": v.id, "campos": _json_seguro(campos)}
        if objetivo == "persona":
            per = _buscar_persona(p, args.get("id"))
            if per is None:
                raise ValueError("Persona no encontrada.")
            return {"objetivo": "persona", "id": per.id, "campos": _json_seguro(per.__dict__)}
        raise ValueError(f"Objetivo de inspector no soportado: {objetivo}")

    # A partir de aquí, todo son comandos de escritura en la partida
    if cmd not in COMANDOS_LECTURA and _en_linea_bloqueado(p):
        raise ValueError("Bloqueado: no se permiten trampas en servidores ni partidas en línea.")

    j = p.j

    if cmd == "inspector.escribir":
        objetivo = args.get("objetivo", "jugador")
        clave = str(args.get("clave", ""))
        valor = args.get("valor")
        if not clave:
            raise ValueError("Falta la clave a modificar.")
        if objetivo == "jugador":
            if not hasattr(j, clave) or clave in ("veh",):
                raise ValueError(f"Atributo inexistente o protegido en Jugador: {clave}")
            actual = getattr(j, clave)
            setattr(j, clave, _convertir_valor(valor, actual))
        elif objetivo == "stats":
            actual = j.stats.get(clave)
            j.stats[clave] = _convertir_valor(valor, actual)
        elif objetivo == "cfg":
            return despachar(app, "cfg.set", {"clave": clave, "valor": valor})
        elif objetivo in ("vehiculo", "vehiculo_actual"):
            v = _buscar_vehiculo(p, args.get("id"))
            if v is None:
                raise ValueError("Vehículo no encontrado.")
            if clave in ("canal", "sirena", "alarma", "fuego"):
                raise ValueError(f"Campo de audio protegido: {clave}")
            if clave in ("vel_max", "acel", "freno", "tono") and not hasattr(v, clave):
                _asegurar_modelo_propio(p, v)
                v.modelo[clave] = _convertir_valor(valor, v.modelo.get(clave))
            else:
                actual = getattr(v, clave, None)
                setattr(v, clave, _convertir_valor(valor, actual))
        elif objetivo == "persona":
            per = _buscar_persona(p, args.get("id"))
            if per is None:
                raise ValueError("Persona no encontrada.")
            actual = getattr(per, clave, None)
            setattr(per, clave, _convertir_valor(valor, actual))
        else:
            raise ValueError(f"Objetivo no soportado: {objetivo}")
        return {"ok": True}

    if cmd == "jugador.set":
        accion = args.get("accion")
        if accion == "curar_todo":
            j.salud = float(j.salud_max)
            j.blindaje = 100.0
            j.foco = 100.0
            j.animo = max(j.animo, 80.0)
            p.aguante = 100.0
            p.aire = 100.0
        elif accion == "llenar_necesidades":
            j.hambre = 0.0
            j.sed = 0.0
            j.sueno = 0.0
            j.suciedad = 0.0
        elif accion == "max_habilidades":
            for k in list(j.hab.keys()):
                j.hab[k] = 6000.0
            j.cocina_practica = 100.0
        elif accion == "borrar_antecedentes":
            j.antecedentes = []
            if isinstance(j.honra, dict):
                j.honra["sospecha"] = 0
                j.honra["negro"] = 0
                j.honra["deuda"] = 0
        elif accion == "desbloquear_propiedades":
            nuevas = [l.id for l in p.lugares.values() if l.tipo in ("casa", "negocio") and l.id not in j.propiedades]
            j.propiedades.extend(nuevas)
        elif accion == "conquistar_barrio_actual":
            b = p.mundo.barrio(*p.pos())
            if b["id"] not in j.territorios:
                j.territorios.append(b["id"])
            j.barrios_banda.pop(b["id"], None)
        elif accion == "conquistar_todos_barrios":
            for m in p.mapas.values():
                if m.tipo == "ciudad":
                    for b in m.barrios:
                        if b["id"] not in j.territorios:
                            j.territorios.append(b["id"])
                        j.barrios_banda.pop(b["id"], None)
        elif accion == "llamar_banda":
            if j.banda <= 0:
                if not j.territorios:
                    b = p.mundo.barrio(*p.pos())
                    j.territorios.append(b["id"])
                j.banda = max(1, int(args.get("cantidad", 4)))
                j.banda_nombre = j.banda_nombre or "La Guardia"
            sistemas.llamar(p)
        elif accion == "adoptar_perro":
            j.perro = str(args.get("nombre") or j.perro or "Rayo")
            j.perro_hambre = 0.0
            j.perro_confianza = 100.0
            j.perro_en_casa = False
            if p.perro() is None and p.mundo.tipo != "mar":
                p.crear_perro()

        campos = ("salud", "salud_max", "blindaje", "dinero", "banco", "foco", "animo", "ciudadania", "reputacion",
                  "hambre", "sed", "sueno", "suciedad", "carne_puntos", "cocina_practica", "perro_hambre",
                  "perro_confianza", "banda", "banda_nombre", "alias")
        for c in campos:
            if c in args and args[c] is not None:
                setattr(j, c, _convertir_valor(args[c], getattr(j, c)))
        if "dinero_delta" in args and args["dinero_delta"] is not None:
            j.dinero = max(0, int(j.dinero) + int(args["dinero_delta"]))
        if "banco_delta" in args and args["banco_delta"] is not None:
            j.banco = max(0, int(j.banco) + int(args["banco_delta"]))
        if "guardaespaldas" in args and args["guardaespaldas"] is not None:
            deseados = max(0, int(args["guardaespaldas"]))
            actuales = [per for per in p.personas if per.tipo == "aliado" and not per.muerto and not getattr(per, "de_banda", False)]
            while len(actuales) < deseados:
                actuales.append(p.crear_aliado())
            while len(actuales) > deseados:
                quitar = actuales.pop()
                if quitar in p.personas:
                    p.personas.remove(quitar)
            j.guardaespaldas = deseados
        j.salud_max = max(1.0, float(j.salud_max))
        j.salud = max(1.0, min(float(j.salud_max), float(j.salud)))
        j.blindaje = max(0.0, float(j.blindaje))
        j.animo = max(0.0, min(100.0, float(j.animo)))
        j.ciudadania = max(0.0, min(100.0, float(j.ciudadania)))
        j.reputacion = max(0.0, min(100.0, float(j.reputacion)))
        j.carne_puntos = max(0, min(12, int(j.carne_puntos)))
        return {"jugador": _recolectar_estado(app)["jugador"]}

    if cmd == "jugador.habilidad":
        hab = str(args.get("habilidad", ""))
        if hab not in j.hab:
            raise ValueError(f"Habilidad desconocida: {hab}")
        if "nivel" in args and args["nivel"] is not None:
            niv = max(0, min(10, int(args["nivel"])))
            j.hab[hab] = float(60 * niv * niv)
        elif "xp" in args and args["xp"] is not None:
            j.hab[hab] = max(0.0, float(args["xp"]))
        return {"hab": hab, "xp": j.hab[hab], "nivel": p.nivel(hab)}

    if cmd == "jugador.teletransportar":
        lugar_id = args.get("lugar_id")
        if lugar_id:
            l = p.lug(lugar_id)
            if l is None:
                raise ValueError(f"Lugar no encontrado: {lugar_id}")
            mapa_id, x, y = l.mapa, float(l.x), float(l.y)
        else:
            mapa_id = str(args.get("mapa_id") or p.mundo.id)
            if mapa_id not in p.mapas:
                raise ValueError(f"Mapa no encontrado: {mapa_id}")
            m = p.mapas[mapa_id]
            x = float(args["x"]) if "x" in args and args["x"] is not None else float(m.ancho) * 0.5
            y = float(args["y"]) if "y" in args and args["y"] is not None else float(m.alto) * 0.5
        if mapa_id != p.mundo.id:
            p.cambiar_mapa(mapa_id, x, y)
        else:
            if j.veh is not None:
                if p.mundo.transitable(x, y):
                    j.veh.x, j.veh.y = x, y
                    j.veh.vel = 0.0
                else:
                    p.teletransportar(x, y)
            else:
                p.teletransportar(x, y)
        return {"mapa": p.mundo.id, "pos": p.pos()}

    if cmd == "mundo.set":
        if "hora" in args and args["hora"] is not None:
            h = float(args["hora"]) % 24.0
            p.reloj = h * 60.0
        if "dia" in args and args["dia"] is not None:
            p.dia = max(1, int(args["dia"]))
        if "pasar_horas" in args and args["pasar_horas"] is not None:
            p.pasar_horas(float(args["pasar_horas"]))
        if "lluvia" in args and args["lluvia"] is not None:
            p.lluvia = bool(args["lluvia"])
        if "dia_azar" in args and args["dia_azar"]:
            ident = str(args["dia_azar"])
            encontrado = next((d for d in azar.DIAS if d[0] == ident), None)
            if encontrado is None:
                raise ValueError(f"Tipo de día desconocido: {ident}")
            p.dia_azar = {"id": encontrado[0], "texto": encontrado[2], "efectos": dict(encontrado[3]), "dia": p.dia}
        return {"dia": p.dia, "reloj": p.reloj, "lluvia": p.lluvia, "dia_azar": p.dia_azar}

    if cmd == "inventario.arma":
        accion = args.get("accion", "dar")
        ident = args.get("arma_id")
        balas = int(args.get("balas", 200))
        if accion == "dar_todas":
            for aid, a in p.armas_d.items():
                cap = int(a.get("cargador") or 0)
                j.armas[aid] = {
                    "cargador": cap,
                    "reserva": max(balas, cap * 4) if a.get("tipo") in ("fuego", "explosivo") else 0,
                    "silenciador": bool(args.get("silenciador", False)),
                    "ampliado": bool(args.get("ampliado", False)),
                }
            return {"total_armas": len(j.armas)}
        if not ident or ident not in p.armas_d:
            raise ValueError(f"Arma desconocida: {ident}")
        a = p.armas_d[ident]
        if accion == "quitar":
            if ident == "punos":
                raise ValueError("No se pueden quitar los puños.")
            j.armas.pop(ident, None)
            if j.arma == ident:
                j.arma = "punos"
            return {"arma_actual": j.arma}
        if accion == "equipar":
            if ident not in j.armas:
                p.dar_arma(ident, balas)
            j.arma = ident
            return {"arma_actual": j.arma}
        if ident not in j.armas:
            p.dar_arma(ident, balas)
        else:
            j.armas[ident]["reserva"] = int(j.armas[ident].get("reserva", 0)) + balas
        entry = j.armas[ident]
        if "cargador" in args and args["cargador"] is not None:
            entry["cargador"] = max(0, int(args["cargador"]))
        if "reserva" in args and args["reserva"] is not None:
            entry["reserva"] = max(0, int(args["reserva"]))
        if "silenciador" in args and args["silenciador"] is not None:
            entry["silenciador"] = bool(args["silenciador"])
        if "ampliado" in args and args["ampliado"] is not None:
            entry["ampliado"] = bool(args["ampliado"])
            if entry["ampliado"]:
                entry["cargador"] = max(entry["cargador"], p.capacidad(ident))
        if args.get("equipar", True):
            j.arma = ident
        return {"arma": ident, "estado": entry}

    if cmd == "inventario.objeto":
        tipo = args.get("tipo", "objeto")
        ident = str(args.get("id", ""))
        cantidad = int(args.get("cantidad", 1))
        if tipo == "objeto":
            if not ident:
                raise ValueError("Falta el identificador del objeto.")
            if ident == "chaleco":
                j.blindaje = 100.0
            else:
                if args.get("fijar"):
                    j.objetos[ident] = max(0, cantidad)
                else:
                    j.objetos[ident] = max(0, int(j.objetos.get(ident, 0)) + cantidad)
            return {"objetos": _json_seguro(j.objetos), "blindaje": j.blindaje}
        if tipo == "mochila_grande":
            j.mochila_grande = bool(args.get("valor", True))
            return {"mochila_grande": j.mochila_grande}
        if tipo == "vaciar_robados":
            for x in j.mochila:
                x["robado"] = False
            return {"mochila": _json_seguro(j.mochila)}
        if tipo == "valor":
            if ident not in mochila.CATALOGO:
                raise ValueError(f"Objeto de valor desconocido: {ident}")
            robado = bool(args.get("robado", False))
            anadidos = 0
            for _ in range(max(1, cantidad)):
                if p.moc_libre() >= mochila.CATALOGO[ident]["peso"]:
                    p.moc_meter(ident, robado=robado, callar=True)
                    anadidos += 1
            return {"anadidos": anadidos, "mochila": _json_seguro(j.mochila)}
        if tipo == "sustancia":
            if not ident:
                raise ValueError("Falta la sustancia.")
            j.sustancias[ident] = max(0, int(j.sustancias.get(ident, 0)) + cantidad)
            return {"sustancias": _json_seguro(j.sustancias)}
        if tipo == "producto":
            if not ident:
                raise ValueError("Falta el producto.")
            j.encima.append({"id": ident, "n": max(1, cantidad), "cad": p.dia + 7})
            return {"encima": _json_seguro(j.encima)}
        raise ValueError(f"Tipo de inventario no soportado: {tipo}")

    if cmd == "vehiculos.crear":
        modelo_id = str(args.get("modelo_id", "utilitario"))
        if modelo_id not in p.modelos:
            raise ValueError(f"Modelo de vehículo desconocido: {modelo_id}")
        mo = p.modelos[modelo_id]
        x, y, d = _punto_spawn_vehiculo(p, mo)
        ia = args.get("ia", "aparcado")
        if ia == "None" or ia == "":
            ia = None
        v = p.crear_vehiculo(modelo_id, x, y, d, ia=ia, nombre=args.get("nombre") or None)
        v.cerrado = False
        overrides = args.get("specs") or {}
        if overrides:
            _asegurar_modelo_propio(p, v)
            for k in ("vel_max", "acel", "freno", "salud", "tono"):
                if k in overrides and overrides[k] is not None:
                    v.modelo[k] = float(overrides[k])
            if "salud" in overrides and overrides["salud"] is not None:
                v.salud = v.salud_max = float(overrides["salud"])
        if args.get("mejoras_max"):
            sistemas.poner(v, {k: sistemas.niveles(k) for k in sistemas.MEJORAS})
            v.salud = v.salud_max
        if args.get("hacer_mio", True):
            p.hacer_mio(v, callar=True)
        if args.get("subir_ahora", False):
            if j.veh is not None:
                p.salir_vehiculo(forzado=True)
            p._subir(v, False, callar=True)
        return {"vehiculo": _info_vehiculo(p, v)}

    if cmd == "vehiculos.editar":
        v = _buscar_vehiculo(p, args.get("id"))
        if v is None:
            raise ValueError("Vehículo no encontrado.")
        solo_este = bool(args.get("solo_este", True))
        specs = args.get("specs") or {}
        if specs:
            if solo_este:
                _asegurar_modelo_propio(p, v)
            target = v.modelo if solo_este else p.modelos.get(v.modelo.get("id"), v.modelo)
            for k in ("vel_max", "acel", "freno", "tono"):
                if k in specs and specs[k] is not None:
                    target[k] = max(0.1, float(specs[k]))
            if "salud_modelo" in specs and specs["salud_modelo"] is not None:
                target["salud"] = max(1.0, float(specs["salud_modelo"]))
                sistemas.poner(v, getattr(v, "mejoras", {}))
            for bkey in ("barco", "vuela"):
                if bkey in specs and specs[bkey] is not None:
                    target[bkey] = bool(specs[bkey])
        if "mejoras" in args and isinstance(args["mejoras"], dict):
            sistemas.poner(v, args["mejoras"])
        if args.get("mejoras_max"):
            sistemas.poner(v, {k: sistemas.niveles(k) for k in sistemas.MEJORAS})
        if "nombre" in args and args["nombre"] is not None:
            v.nombre = str(args["nombre"]).strip() or v.modelo["nombre"]
        if "ia" in args:
            v.ia = None if args["ia"] in ("", "None", None) else str(args["ia"])
        for bfield in ("hostil", "cerrado"):
            if bfield in args and args[bfield] is not None:
                setattr(v, bfield, bool(args[bfield]))
        if "salud_max" in args and args["salud_max"] is not None:
            v.salud_max = max(1.0, float(args["salud_max"]))
            v.salud = min(v.salud, v.salud_max)
        if "salud" in args and args["salud"] is not None:
            v.salud = max(0.0, min(v.salud_max, float(args["salud"])))
        if args.get("reparar"):
            v.salud = float(v.salud_max)
            v.ardiendo = -1.0
            if v.fuego:
                v.fuego.parar()
                v.fuego = None
        if args.get("llenar_combustible"):
            from juego import combustible
            cap = combustible.capacidad(v)
            if cap > 0:
                v.litros = cap
            v.seco = False
            if getattr(v, "queroseno", None) is not None or v.modelo.get("vuela"):
                v.queroseno = 100.0
        if args.get("quitar_averias"):
            p.pasar_revision(v)
        if args.get("pinchar"):
            p.pinchar(v)
        if args.get("mio") is True:
            p.hacer_mio(v, callar=True)
        elif args.get("mio") is False:
            v.mio = False
        return {"vehiculo": _info_vehiculo(p, v)}

    if cmd == "vehiculos.accion":
        accion = str(args.get("accion", ""))
        if accion == "limpiar_trafico":
            quitados = 0
            for v in list(p.vehiculos):
                if v is not j.veh and not getattr(v, "mio", False) and not v.tag:
                    p.quitar_vehiculo(v)
                    quitados += 1
            return {"quitados": quitados}
        v = _buscar_vehiculo(p, args.get("id"))
        if v is None:
            raise ValueError("Vehículo no encontrado.")
        if accion == "subir":
            if j.veh is not None and j.veh is not v:
                p.salir_vehiculo(forzado=True)
            if j.veh is not v:
                p._subir(v, False, callar=True)
        elif accion == "traer_aqui":
            x, y, d = _punto_spawn_vehiculo(p, v.modelo)
            v.x, v.y, v.dir, v.rumbo = x, y, d, d * 90.0
            v.vel = 0.0
        elif accion == "hacer_mio":
            p.hacer_mio(v, callar=True)
        elif accion == "explotar":
            p.explotar(v)
            return {"explotado": True}
        elif accion == "eliminar":
            if v is j.veh:
                p.salir_vehiculo(forzado=True)
            p.quitar_vehiculo(v)
            return {"eliminado": True}
        else:
            raise ValueError(f"Acción de vehículo desconocida: {accion}")
        return {"vehiculo": _info_vehiculo(p, v)}

    if cmd == "npcs.crear":
        modo = str(args.get("modo", "enemigo"))
        cantidad = max(1, min(20, int(args.get("cantidad", 1))))
        clase = str(args.get("clase") or "")
        banda = args.get("banda") or None
        arma = args.get("arma") or None
        nombre = args.get("nombre") or None
        salud = args.get("salud")
        punteria = args.get("punteria")
        en_vehiculo = bool(args.get("en_vehiculo", False))
        px, py = p.pos()
        creados = []

        if modo == "perro":
            j.perro = nombre or j.perro or "Rayo"
            j.perro_hambre = 0.0
            j.perro_confianza = 100.0
            j.perro_en_casa = False
            per = p.perro() or p.crear_perro()
            return {"creados": [_info_persona(p, per)]}

        if modo == "aliado":
            for _ in range(cantidad):
                a = p.crear_aliado()
                if nombre:
                    a.nombre = nombre
                if arma and arma in p.armas_d:
                    a.arma = arma
                if salud is not None:
                    a.salud = float(salud)
                creados.append(_info_persona(p, a))
            return {"creados": creados}

        if en_vehiculo and modo in ("enemigo", "pandillero", "policia"):
            grupo_gente = []
            for _ in range(cantidad):
                ficha_e = gente.enemigo({"clase": clase, "arma": arma, "salud": salud or 75, "punteria": punteria or 0.42})
                per = gente.vestir(Persona("banda" if modo == "pandillero" else "enemigo", px, py, nombre or ficha_e["nombre"]), ficha_e)
                per.hostil = bool(args.get("hostil", True))
                per.estado = "ataca" if per.hostil else "quieto"
                per.activo = True
                per.agresor = True
                if banda:
                    per.banda = banda
                grupo_gente.append(per)
            veh_mod = args.get("vehiculo_modelo") or (gente.tipo_enemigo(clase) or {}).get("vehiculo") or "sedan"
            if veh_mod not in p.modelos:
                veh_mod = "sedan"
            veh = p.llegar_en_vehiculo(veh_mod, grupo_gente)
            if veh is not None:
                return {"creados": [_info_persona(p, x) for x in grupo_gente], "vehiculo": _info_vehiculo(p, veh)}

        for _ in range(cantidad):
            ang = random.uniform(0, 2 * math.pi)
            dist = random.uniform(6.0, 18.0)
            nx, ny = p.mundo.punto_libre(px + math.sin(ang) * dist, py + math.cos(ang) * dist)
            if modo == "civil":
                per = Persona("civil", nx, ny, nombre)
                from juego import charla
                f = charla.ficha(per)
                if args.get("caracter") in gente.CARACTERES:
                    f["caracter"] = args["caracter"]
                if nombre:
                    f["nombre"] = nombre
                    f["presentado"] = True
                    per.nombre = nombre
                else:
                    per.nombre = f["nombre"]
                per.hostil = bool(args.get("hostil", False))
                per.estado = str(args.get("estado") or ("ataca" if per.hostil else "quieto"))
                if arma and arma in p.armas_d:
                    per.arma = arma
                if salud is not None:
                    per.salud = float(salud)
            else:
                tipo_ent = "policia" if modo == "policia" else "banda" if modo == "pandillero" else "enemigo"
                ficha_e = gente.enemigo({"clase": clase, "arma": arma, "salud": salud or 70, "punteria": punteria or 0.42})
                nom = nombre or (f"{ficha_e['nombre']} de {banda}" if banda and banda not in ficha_e["nombre"] else ficha_e["nombre"])
                per = gente.vestir(Persona(tipo_ent, nx, ny, nom), ficha_e)
                per.hostil = bool(args.get("hostil", True))
                per.estado = str(args.get("estado") or ("ataca" if per.hostil else "quieto"))
                per.activo = True
                if banda:
                    per.banda = banda
                if per.hostil:
                    per.agresor = True
            p.personas.append(per)
            creados.append(_info_persona(p, per))
        return {"creados": creados}

    if cmd == "npcs.editar":
        per = _buscar_persona(p, args.get("id"))
        if per is None:
            raise ValueError("Persona no encontrada.")
        for k in ("nombre", "estado", "banda", "arma"):
            if k in args and args[k] is not None:
                val = args[k]
                if k == "arma" and val not in p.armas_d and val not in ("", None):
                    raise ValueError(f"Arma desconocida: {val}")
                setattr(per, k, None if val == "" else val)
        for k in ("salud", "punteria", "vel"):
            if k in args and args[k] is not None:
                setattr(per, k, float(args[k]))
        for k in ("hostil", "agresor", "provocado"):
            if k in args and args[k] is not None:
                setattr(per, k, bool(args[k]))
        if per.hostil and per.estado in ("pasea", "quieto"):
            per.estado = "ataca"
            per.activo = True
        if "confianza" in args and args["confianza"] is not None:
            from juego import charla
            f = charla.ficha(per)
            f["confianza"] = max(-100, min(100, int(args["confianza"])))
        return {"persona": _info_persona(p, per)}

    if cmd == "npcs.accion":
        accion = str(args.get("accion", ""))
        if accion == "eliminar_hostiles":
            n = 0
            for per in list(p.personas):
                if per.hostil and per.tipo not in ("aliado", "perro"):
                    p.personas.remove(per)
                    n += 1
            return {"eliminados": n}
        if accion == "eliminar_muertos":
            n = 0
            for per in list(p.personas):
                if per.muerto:
                    p.personas.remove(per)
                    n += 1
            return {"eliminados": n}
        if accion == "eliminar_civiles":
            n = 0
            for per in list(p.personas):
                if per.tipo == "civil":
                    p.personas.remove(per)
                    n += 1
            return {"eliminados": n}
        per = _buscar_persona(p, args.get("id"))
        if per is None:
            raise ValueError("Persona no encontrada.")
        if accion == "matar":
            per.muerto = True
            per.salud = 0.0
            if p.objetivo is per:
                p.objetivo = None
        elif accion == "curar":
            per.muerto = False
            per.salud = max(100.0, float(per.salud))
        elif accion == "eliminar":
            if p.objetivo is per:
                p.objetivo = None
            p.personas.remove(per)
            return {"eliminado": True}
        elif accion == "traer_aqui":
            px, py = p.pos()
            per.x, per.y = p.mundo.punto_libre(px + 2.0, py + 2.0)
        elif accion == "hacer_hostil":
            per.hostil = True
            per.activo = True
            per.estado = "ataca"
        elif accion == "pacificar":
            per.hostil = False
            per.agresor = False
            per.estado = "quieto"
        else:
            raise ValueError(f"Acción de NPC desconocida: {accion}")
        return {"persona": _info_persona(p, per)}

    if cmd == "policia.set":
        if "estrellas" in args and args["estrellas"] is not None:
            _set_estrellas(p, int(args["estrellas"]), limpiar_policias=bool(args.get("limpiar_policias", True)))
        if args.get("lanzar_patrulla"):
            p._llegar_patrulla(*p.pos())
        if args.get("lanzar_patrulla_ronda"):
            p._crear_patrulla(*p.pos(), ronda=True)
        if args.get("lanzar_helicoptero") and p.heli is None and "helicoptero" in p.modelos:
            p.cfg["helicoptero_policia"] = True
            p.cfg["sin_policia"] = False
            if j.estrellas < 5:
                _set_estrellas(p, 5, limpiar_policias=False)
            p._heli_llega()
        if args.get("quitar_helicoptero") and p.heli is not None:
            p._heli_fuera()
        if "rep_banda" in args and isinstance(args["rep_banda"], dict):
            banda_nom = args["rep_banda"].get("banda")
            valor = float(args["rep_banda"].get("valor", 0.0))
            valor = max(-100.0, min(100.0, valor))
            if banda_nom == "__todas__":
                for b in gente.nombres_bandas():
                    j.rep_bandas[b] = valor
            elif banda_nom:
                j.rep_bandas[str(banda_nom)] = valor
        return {"estrellas": j.estrellas, "puntos_busqueda": j.puntos_busqueda, "rep_bandas": _json_seguro(j.rep_bandas)}

    if cmd == "eventos.lanzar":
        tipo = str(args.get("tipo", ""))
        px, py = p.pos()

        if tipo == "cancelar_suceso":
            p._fin_evento()
            return {"evento": None}

        if tipo in ("suceso_atraco", "suceso_banda", "suceso_maletin"):
            if p.evento:
                p._fin_evento()
            pos = p._punto_cercano(22, 55) or p.mundo.punto_libre(px + 25.0, py + 10.0)
            ex, ey = pos
            if tipo == "suceso_maletin":
                o = Objeto("dinero", "Maletín perdido", ex, ey)
                o.valor = int(args.get("valor", random.randint(250, 900)))
                p.objetos.append(o)
                p.evento = {"tipo": "maletin", "t": 180.0, "objeto": o}
                return {"evento": "maletin", "pos": (ex, ey), "valor": o.valor}
            personas = []
            if tipo == "suceso_atraco":
                vic = Persona("civil", ex, ey, "Víctima del atraco")
                vic.estado = "quieto"
                vic.tag = "evento"
                personas.append(vic)
                n, clase, nombre = 1, "atracador", "Atracador"
            else:
                n = max(2, int(args.get("cantidad", 3)))
                clase, nombre = "pandillero_calle", "Pandillero"
            for _ in range(n):
                f = gente.enemigo(gente.grupo(clase, tipo=nombre, arma=random.choice(["navaja", "pistola", "bate"]), salud=55))
                e = gente.vestir(Persona("enemigo", *p.mundo.punto_libre(ex + random.uniform(-3, 3), ey + random.uniform(-3, 3)), f["nombre"]), f)
                e.hostil, e.estado, e.activo, e.tag, e.agresor = True, "ataca", False, "evento", True
                personas.append(e)
            p.personas += personas
            p.evento = {"tipo": "atraco" if tipo == "suceso_atraco" else "banda", "t": 150.0, "personas": personas, "premio": 300 * n}
            return {"evento": p.evento["tipo"], "pos": (ex, ey)}

        if tipo == "persecucion_vehiculo":
            modelo_id = str(args.get("modelo_id") or "deportivo")
            if modelo_id not in p.modelos:
                modelo_id = "sedan"
            pos = p._punto_llegada(px, py)
            if pos is None:
                vx, vy, vd = _punto_spawn_vehiculo(p, p.modelos[modelo_id])
            else:
                vx, vy, vd = pos
            v = p.crear_vehiculo(modelo_id, vx, vy, vd, ia="huida", nombre=args.get("nombre") or f"Fugitivo ({p.modelos[modelo_id]['nombre']})", tag="persecucion")
            v.hostil = True
            v.ocupado = True
            v.vel_obj = float(args.get("vel_obj", 24.0))
            v.vel = 10.0
            if args.get("marcar_gps", True):
                p.fijar_gps(v.x, v.y, v.nombre, sigue=v, auto=False, callar=True)
            return {"vehiculo": _info_vehiculo(p, v)}

        if tipo == "guerra_barrio":
            p.cfg["guerra_calle"] = True
            b = p.mundo.barrio(px, py)
            banda = args.get("banda") or p.banda_de_barrio(b) or (gente.nombres_bandas()[0] if gente.nombres_bandas() else "Los Calaveras")
            ok = p.empezar_guerra(b, defensa=bool(args.get("defensa", False)), banda=banda)
            return {"iniciada": bool(ok), "guerra": p.guerra["tipo"] if p.guerra else None}

        if tipo == "buscar_pelea":
            banda = args.get("banda") or (gente.nombres_bandas()[0] if gente.nombres_bandas() else "Los Calaveras")
            ok = p.buscar_pelea(banda, larga=bool(args.get("larga", False)))
            return {"iniciada": bool(ok), "guerra": p.guerra["tipo"] if p.guerra else None}

        if tipo == "terminar_guerra":
            p.guerra_retirada(callar=True)
            return {"guerra": None}

        if tipo == "atraco_local_cercano":
            cands = [l for l in p.mundo.lugares.values() if p.local_atracable(l)]
            if not cands:
                raise ValueError("No hay locales atracables en este mapa.")
            l = min(cands, key=lambda l: math.hypot(l.x - px, l.y - py))
            p.atracadas.pop(l.id, None)
            j.locales_vetados.pop(l.id, None)
            if p.arma()["tipo"] != "fuego":
                p.dar_arma("pistola", 60)
                j.arma = "pistola"
            p.teletransportar(l.x, l.y)
            ok = p.atracar_local(l)
            return {"iniciado": bool(ok), "lugar": l.nombre}

        if tipo == "atraco_banco_cercano":
            bancos = [l for l in p.mundo.lugares.values() if l.tipo == "banco"]
            if not bancos:
                raise ValueError("No hay bancos en este mapa.")
            l = min(bancos, key=lambda l: math.hypot(l.x - px, l.y - py))
            p.atracadas.pop("banco:" + l.id, None)
            if p.arma()["tipo"] != "fuego":
                p.dar_arma("pistola", 60)
                j.arma = "pistola"
            p.teletransportar(l.x, l.y)
            p.empezar_atraco_banco(l)
            return {"iniciado": True, "lugar": l.nombre}

        if tipo == "limpiar_vetos":
            p.atracadas.clear()
            j.locales_vetados.clear()
            j.proveedores.clear()
            return {"limpiado": True}

        if tipo == "ambulancia":
            p.cfg["ambulancias"] = True
            p.ambulancia = None
            p.t_ambulancia = 0.0
            p.ambulancia = {"estado": "espera", "t": 0.2, "x": px, "y": py, "limite": 150.0, "veh": None}
            return {"ambulancia": True}

        if tipo == "soltar_dinero":
            valor = max(1, int(args.get("valor", 1000)))
            ox, oy = p.mundo.punto_libre(px + 2.5, py)
            o = Objeto("dinero", f"Maletín con {valor} euros", ox, oy)
            o.valor = valor
            p.objetos.append(o)
            return {"valor": valor, "pos": (ox, oy)}

        if tipo == "contrato":
            cands = [l for l in p.mundo.lugares.values() if l.tipo not in ("salida", "embarcadero")]
            if not cands:
                raise ValueError("No hay lugares disponibles en este mapa para iniciar un contrato.")
            l = min(cands, key=lambda q: math.hypot(q.x - px, q.y - py))
            p.empezar_contrato(l)
            return {"iniciado": True, "mision": p.mision["def"]["titulo"] if p.mision else None}

        if tipo == "encargo_coche":
            cands = [l for l in p.mundo.lugares.values() if l.tipo not in ("salida", "embarcadero")]
            if not cands:
                raise ValueError("No hay lugares disponibles en este mapa para iniciar un encargo.")
            l = min(cands, key=lambda q: math.hypot(q.x - px, q.y - py))
            p.empezar_encargo_coche(l)
            return {"iniciado": True, "mision": p.mision["def"]["titulo"] if p.mision else None}

        raise ValueError(f"Tipo de evento desconocido: {tipo}")

    raise ValueError(f"Comando desconocido: {cmd}")


class ServidorPuente:
    """Servidor TCP local no bloqueante que procesa órdenes en el hilo principal del juego."""

    def __init__(self, app, carpeta: str | None = None) -> None:
        self.app = app
        self._carpeta = carpeta or carpeta_fichas()
        self.token = secrets.token_hex(16)
        self.puerto = 0
        self._ficha_ruta: str | None = None
        self._sock: socket.socket | None = None
        self._hilo: threading.Thread | None = None
        self._activo = False
        self._cola: queue.Queue = queue.Queue()

    def iniciar(self) -> None:
        if self._activo:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(8)
        sock.settimeout(0.25)
        self._sock = sock
        self.puerto = int(sock.getsockname()[1])
        self._activo = True
        self._escribir_ficha()
        self._hilo = threading.Thread(target=self._bucle_red, name="PuertoBravoPuenteTrampas", daemon=True)
        self._hilo.start()

    def _escribir_ficha(self) -> None:
        from juego import VERSION

        os.makedirs(self._carpeta, exist_ok=True)
        ruta = os.path.join(self._carpeta, f"{os.getpid()}.json")
        tmp = ruta + ".tmp"
        ficha = {
            "pid": os.getpid(),
            "puerto": self.puerto,
            "token": self.token,
            "proto": PROTOCOLO,
            "version": VERSION,
            "exe": os.path.abspath(sys.executable),
            "inicio": int(time.time()),
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(ficha, f, ensure_ascii=False)
        os.replace(tmp, ruta)
        self._ficha_ruta = ruta

    def _bucle_red(self) -> None:
        while self._activo and self._sock is not None:
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._atender_conexion, args=(conn,), daemon=True).start()

    def _atender_conexion(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(5.0)
            try:
                linea = leer_linea_socket(conn, MAX_MENSAJE)
                if not linea:
                    return
                req = json.loads(linea)
            except Exception as exc:
                self._enviar(conn, {"ok": False, "error": f"Petición inválida: {exc}"})
                return
            if not isinstance(req, dict) or not secrets.compare_digest(str(req.get("token", "")), self.token):
                self._enviar(conn, {"ok": False, "error": "Token de autenticación inválido."})
                return
            cmd = str(req.get("cmd", ""))
            args = req.get("args") if isinstance(req.get("args"), dict) else {}
            ev = threading.Event()
            caja: dict = {}
            self._cola.put((cmd, args, ev, caja))
            if not ev.wait(timeout=4.5):
                self._enviar(conn, {"ok": False, "error": "Tiempo de espera agotado ejecutando el comando en el juego."})
                return
            self._enviar(conn, caja.get("resp", {"ok": False, "error": "Sin respuesta."}))

    @staticmethod
    def _enviar(conn: socket.socket, resp: dict) -> None:
        try:
            data = json.dumps(resp, ensure_ascii=False).encode("utf-8") + b"\n"
            conn.sendall(data)
        except OSError:
            pass

    def atender(self, max_ops: int = 25) -> None:
        """Drena comandos pendientes desde el hilo principal de Pygame."""
        atendidos = 0
        while atendidos < max_ops:
            try:
                cmd, args, ev, caja = self._cola.get_nowait()
            except queue.Empty:
                break
            atendidos += 1
            try:
                datos = despachar(self.app, cmd, args)
                caja["resp"] = {"ok": True, "datos": _json_seguro(datos)}
            except Exception as exc:
                caja["resp"] = {"ok": False, "error": str(exc)}
            finally:
                ev.set()

    def detener(self) -> None:
        self._activo = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._hilo is not None and self._hilo.is_alive():
            self._hilo.join(timeout=1.0)
        self._hilo = None
        if self._ficha_ruta:
            try:
                os.remove(self._ficha_ruta)
            except OSError:
                pass
            self._ficha_ruta = None


def iniciar(app, forzar: bool = False, carpeta: str | None = None) -> ServidorPuente | None:
    """Inicia el puente de trampas en App, respetando el modo pruebas y PUERTOBRAVO_TRAMPAS."""
    env = os.environ.get("PUERTOBRAVO_TRAMPAS")
    if env == "0":
        return None
    if getattr(app, "pruebas", False) and not forzar and env != "1":
        return None
    actual = getattr(app, "_puente_trampas", None)
    if actual is not None:
        return actual
    srv = ServidorPuente(app, carpeta=carpeta)
    srv.iniciar()
    app._puente_trampas = srv
    return srv


def atender(app) -> None:
    srv = getattr(app, "_puente_trampas", None)
    if srv is not None:
        srv.atender()


def detener(app) -> None:
    srv = getattr(app, "_puente_trampas", None)
    if srv is not None:
        srv.detener()
        app._puente_trampas = None
