"""Las salidas de sonido de Windows (1.7.4): cuáles hay conectadas y cuál es ahora la de por defecto.

Los dos motores de sonido abren su salida al arrancar y se quedan con ella: si se desconectan los auriculares, el
juego se quedaba mudo, y si se conectaban después, seguía en los altavoces mientras el lector de pantalla, que sí sigue
a Windows, se iba a los auriculares. No era cosa de pygame, que aquí no toca el sonido: es que PortAudio (motor
clásico) no se entera de que los dispositivos cambian, y OpenAL (motor envolvente) se queda en el que abrió.

Aquí se pregunta a Windows, sin abrir nada y sin cortar el sonido, qué salidas hay y cuál es la de por defecto (la API
clásica winmm, que siempre está al día). Los motores lo miran cada poco y, si su salida se ha ido o la de Windows ha
cambiado, la vuelven a abrir donde toca. Los nombres de winmm llegan cortados a 31 letras: se comparan por el
principio con los de cada motor.
"""
import ctypes
import os

_WINMM = None


def _winmm():
    global _WINMM
    if _WINMM is None:
        if os.name != "nt":
            _WINMM = False
            return _WINMM
        try:
            from ctypes import wintypes
            w = ctypes.WinDLL("winmm")
            w.waveOutGetNumDevs.restype = wintypes.UINT
            w.waveOutGetDevCapsW.restype = wintypes.UINT
            w.waveOutMessage.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p]
            w.waveOutMessage.restype = wintypes.UINT
            _WINMM = w
        except Exception:
            _WINMM = False
    return _WINMM


def _caps():
    from ctypes import wintypes

    class CAPS(ctypes.Structure):
        _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("vDriverVersion", wintypes.UINT), ("szPname", wintypes.WCHAR * 32),
                    ("dwFormats", wintypes.DWORD), ("wChannels", wintypes.WORD), ("wReserved1", wintypes.WORD), ("dwSupport", wintypes.DWORD)]
    return CAPS


def disponibles():
    """Los nombres (cortos) de las salidas de sonido conectadas ahora mismo. Lista vacía si no se puede saber."""
    w = _winmm()
    if not w:
        return []
    caps = _caps()
    out = []
    try:
        for i in range(int(w.waveOutGetNumDevs())):
            c = caps()
            if w.waveOutGetDevCapsW(i, ctypes.byref(c), ctypes.sizeof(c)) == 0 and c.szPname.strip():
                out.append(c.szPname.strip())
    except Exception:
        return []
    return out


def por_defecto():
    """El nombre (corto) de la salida que Windows tiene ahora por defecto. Cadena vacía si no se puede saber."""
    w = _winmm()
    if not w:
        return ""
    from ctypes import wintypes
    dev, flags = wintypes.DWORD(0), wintypes.DWORD(0)
    try:
        r = w.waveOutMessage(ctypes.c_void_p(ctypes.c_size_t(-1).value), 0x2015,          # WAVE_MAPPER, DRVM_MAPPER_PREFERRED_GET
                             ctypes.cast(ctypes.byref(dev), ctypes.c_void_p), ctypes.cast(ctypes.byref(flags), ctypes.c_void_p))
    except Exception:
        return ""
    if r != 0:
        return ""
    nombres = disponibles()
    return nombres[dev.value] if 0 <= dev.value < len(nombres) else ""


def coincide(corto, largo):
    """Si el nombre corto de Windows es esa salida del motor: «Headphones (HyperX Cloud Alpha » con «Headphones (HyperX
    Cloud Alpha Wireless)», o con «OpenAL Soft on Headphones (HyperX Cloud Alpha Wireless)»."""
    c, l = (corto or "").strip().lower(), (largo or "").strip().lower()
    if not c or not l:
        return False
    if l.startswith("openal soft on "):
        l = l[len("openal soft on "):]
    return l.startswith(c) or c.startswith(l)


def presente(nombre):
    """Si esa salida (guardada con su nombre corto) está conectada ahora."""
    return any(coincide(nombre, n) for n in disponibles())
