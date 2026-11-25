"""Interfaz gráfica accesible (wxPython) del Menú de Trampas para Puerto Bravo."""
from __future__ import annotations

import json
import wx

from . import NOMBRE, descubrir_instancias
from .protocolo import ClienteTrampas, ErrorPuente

try:
    from editor.accesibilidad import voz as _voz
    from editor.accesibilidad.ayuda import asegurar_ayudas, habilitar_ayuda_contextual
    from editor.accesibilidad.dialogos import mostrar_error
    from editor.accesibilidad.nombres import crear_campo
except Exception:  # pragma: no cover - respaldo ante cambios futuros en editor.accesibilidad
    class _VozFallback:
        NAVEGACION = "navegacion"
        AVISOS = "avisos"

        @staticmethod
        def hablar(texto: str, interrumpir: bool = True, canal: str = "navegacion") -> None:
            pass

    _voz = _VozFallback()

    def habilitar_ayuda_contextual(ventana: wx.Window) -> None:
        pass

    def asegurar_ayudas(ventana: wx.Window) -> None:
        pass

    def mostrar_error(padre: wx.Window | None, mensaje: str, titulo: str = "Error") -> None:
        wx.MessageBox(mensaje, titulo, wx.OK | wx.ICON_ERROR, parent=padre)

    def crear_campo(padre, etiqueta, fabrica, *args, ayuda="", sizer=None, horizontal=False, expandir=True, **kwargs):
        lbl = wx.StaticText(padre, label=etiqueta)
        ctrl = fabrica(padre, *args, **kwargs)
        if ayuda:
            ctrl.SetHelpText(ayuda)
        if sizer is not None:
            if horizontal:
                fila = wx.BoxSizer(wx.HORIZONTAL)
                fila.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
                fila.Add(ctrl, 1 if expandir else 0, wx.EXPAND if expandir else 0)
                sizer.Add(fila, 0, wx.EXPAND | wx.ALL, 4)
            else:
                sizer.Add(lbl, 0, wx.LEFT | wx.RIGHT | wx.TOP, 4)
                sizer.Add(ctrl, 0, (wx.EXPAND if expandir else 0) | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        return lbl, ctrl


def _hablar(texto: str) -> None:
    try:
        _voz.hablar(texto, interrumpir=True, canal=_voz.AVISOS)
    except Exception:
        pass


class VentanaTrampas(wx.Frame):
    """Ventana principal del menú de trampas conectado en tiempo real a Puerto Bravo."""

    def __init__(self, padre=None, auto_conectar: bool = True, intervalo_ms: int = 2000) -> None:
        super().__init__(padre, title=NOMBRE, size=(920, 720), name=NOMBRE)
        self.cliente: ClienteTrampas | None = None
        self.instancias: list[dict] = []
        self.catalogos: dict = {}
        self.estado: dict = {}
        self._vehiculos_vivos: list[dict] = []
        self._personas_vistas: list[dict] = []
        self._inspector_campos: dict = {}
        self._ultimo_resumen: str = ""
        self._ultimas_claves_veh: list[str] = []
        self._ultimas_claves_npc: list[str] = []

        panel = wx.Panel(self)
        raiz = wx.BoxSizer(wx.VERTICAL)

        # Barra superior de conexión
        barra = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sel_instancia = crear_campo(
            panel, "&Instancia del juego:", wx.Choice, choices=["(ninguna detectada)"],
            ayuda="Elige qué proceso de Puerto Bravo quieres controlar.",
            sizer=barra, horizontal=True,
        )
        self.btn_conectar = wx.Button(panel, label="&Conectar")
        self.btn_conectar.SetHelpText("Busca y conecta con el proceso de Puerto Bravo seleccionado.")
        self.btn_refrescar = wx.Button(panel, label="&Actualizar (F5)")
        self.btn_refrescar.SetHelpText("Actualiza catálogos, estadísticas, vehículos y NPCs desde la partida.")
        barra.Add(self.btn_conectar, 0, wx.ALL, 4)
        barra.Add(self.btn_refrescar, 0, wx.ALL, 4)
        raiz.Add(barra, 0, wx.EXPAND | wx.ALL, 4)

        _, self.txt_conexion = crear_campo(
            panel, "Estado de &conexión:", wx.TextCtrl, style=wx.TE_READONLY,
            ayuda="Indica si hay conexión con el juego y si hay una partida activa.",
            sizer=raiz, horizontal=True,
        )
        self.txt_conexion.SetValue("Sin conectar. Pulsa Conectar cuando Puerto Bravo esté abierto.")

        self.libro = wx.Notebook(panel, name="Secciones de trampas")
        self.libro.SetHelpText("Pestañas de trampas. Cambia con Control+Tab o las flechas.")
        self._construir_tab_jugador()
        self._construir_tab_inventario()
        self._construir_tab_vehiculos()
        self._construir_tab_npcs()
        self._construir_tab_policia()
        self._construir_tab_eventos()
        self._construir_tab_mundo()
        self._construir_tab_inspector()
        raiz.Add(self.libro, 1, wx.EXPAND | wx.ALL, 4)

        panel.SetSizer(raiz)
        self.CreateStatusBar()
        self.SetStatusText("Listo. Ctrl+H lee la ayuda del control enfocado; F5 actualiza.")

        self.btn_conectar.Bind(wx.EVT_BUTTON, lambda e: self.conectar(anunciar=True))
        self.btn_refrescar.Bind(wx.EVT_BUTTON, lambda e: self.refrescar_todo(anunciar=True))
        self.Bind(wx.EVT_CHAR_HOOK, self._tecla_global)
        self.Bind(wx.EVT_CLOSE, self._al_cerrar)

        habilitar_ayuda_contextual(self)
        asegurar_ayudas(self)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._al_timer, self.timer)
        if intervalo_ms > 0:
            self.timer.Start(intervalo_ms)

        self.Centre()
        if auto_conectar:
            wx.CallAfter(self._auto_conectar_silencioso)

    # ------------------------------------------------------------------ pestañas
    def _construir_tab_jugador(self) -> None:
        pag = wx.Panel(self.libro, name="Jugador")
        s = wx.BoxSizer(wx.VERTICAL)

        _, self.txt_resumen_jug = crear_campo(
            pag, "Resumen de &partida:", wx.TextCtrl,
            style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 105),
            ayuda="Resumen actual del jugador. Recórrelo con las flechas.",
            sizer=s,
        )

        grid = wx.FlexGridSizer(cols=4, vgap=4, hgap=8)
        grid.AddGrowableCol(1, 1)
        grid.AddGrowableCol(3, 1)

        def _campo_num(etiqueta, minimo, maximo, defecto, ayuda):
            lbl = wx.StaticText(pag, label=etiqueta)
            ctrl = wx.SpinCtrl(pag, min=minimo, max=maximo, initial=defecto, name=etiqueta.replace("&", "").rstrip(":"))
            ctrl.SetHelpText(ayuda)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        self.sp_salud = _campo_num("&Salud:", 1, 9999, 100, "Salud actual del jugador.")
        self.sp_salud_max = _campo_num("Salud má&xima:", 10, 9999, 100, "Salud máxima del jugador.")
        self.sp_blindaje = _campo_num("&Blindaje:", 0, 1000, 0, "Puntos de chaleco antibalas.")
        self.sp_dinero = _campo_num("&Dinero en mano:", 0, 99999999, 50, "Euros en efectivo.")
        self.sp_banco = _campo_num("Dinero en &banco:", 0, 99999999, 0, "Saldo en la cuenta bancaria.")
        self.sp_animo = _campo_num("Á&nimo:", 0, 100, 55, "Nivel de ánimo (0 a 100).")
        self.sp_ciudadania = _campo_num("&Prestigio vecinal:", 0, 100, 20, "Ciudadanía o prestigio (0 a 100).")
        self.sp_reputacion = _campo_num("&Fama callejera:", 0, 100, 0, "Reputación criminal (0 a 100).")
        self.sp_hambre = _campo_num("Ha&mbre:", 0, 100, 0, "Nivel de hambre (0 = saciado).")
        self.sp_sed = _campo_num("Se&d:", 0, 100, 0, "Nivel de sed (0 = hidratado).")
        self.sp_sueno = _campo_num("S&ueño:", 0, 100, 0, "Nivel de sueño (0 = descansado).")
        self.sp_suciedad = _campo_num("Suc&iedad:", 0, 100, 0, "Suciedad corporal (0 = limpio).")
        self.sp_carne = _campo_num("Puntos &carné:", 0, 12, 12, "Puntos del carné de conducir (0 a 12).")
        self.sp_guardaespaldas = _campo_num("&Guardaespaldas:", 0, 20, 0, "Cantidad de guardaespaldas activos.")
        s.Add(grid, 0, wx.EXPAND | wx.ALL, 6)

        fila_hab = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sel_hab = crear_campo(
            pag, "Habilidad:", wx.Choice, choices=["conduccion", "punteria", "resistencia", "pesca"],
            ayuda="Elige qué habilidad quieres ajustar.",
            sizer=fila_hab, horizontal=True,
        )
        _, self.sp_hab_nivel = crear_campo(
            pag, "Nive&l (0-10):", wx.SpinCtrl, min=0, max=10, initial=10,
            ayuda="Nivel objetivo de la habilidad seleccionada.",
            sizer=fila_hab, horizontal=True, expandir=False,
        )
        self.btn_hab = wx.Button(pag, label="Fijar &habilidad")
        fila_hab.Add(self.btn_hab, 0, wx.ALL, 4)
        s.Add(fila_hab, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)

        fila_chk = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_invulnerable = wx.CheckBox(pag, label="Modo &invulnerable")
        self.chk_invulnerable.SetHelpText("Activa o desactiva la invulnerabilidad nativa del jugador.")
        self.chk_sin_policia = wx.CheckBox(pag, label="Jugar sin p&olicía")
        self.chk_sin_policia.SetHelpText("Activa o desactiva la opción nativa sin policía.")
        fila_chk.Add(self.chk_invulnerable, 0, wx.ALL, 6)
        fila_chk.Add(self.chk_sin_policia, 0, wx.ALL, 6)
        s.Add(fila_chk, 0, wx.LEFT | wx.RIGHT, 4)

        botones = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_aplicar_jug = wx.Button(pag, label="&Aplicar cambios")
        self.btn_curar = wx.Button(pag, label="&Curar todo")
        self.btn_necesidades = wx.Button(pag, label="Llenar necesida&des")
        self.btn_dinero5k = wx.Button(pag, label="+5.000 &euros")
        self.btn_dinero50k = wx.Button(pag, label="+50.000 e&uros")
        self.btn_max_habs = wx.Button(pag, label="Má&x. habilidades")
        self.btn_antecedentes = wx.Button(pag, label="Borrar an&tecedentes")
        self.btn_propiedades = wx.Button(pag, label="Todas las p&ropiedades")
        self.btn_banda = wx.Button(pag, label="Llamar &banda")
        self.btn_perro = wx.Button(pag, label="Ad&optar perro")
        for b in (
            self.btn_aplicar_jug, self.btn_curar, self.btn_necesidades, self.btn_dinero5k,
            self.btn_dinero50k, self.btn_max_habs, self.btn_antecedentes, self.btn_propiedades,
            self.btn_banda, self.btn_perro,
        ):
            botones.Add(b, 0, wx.ALL, 4)
        s.Add(botones, 0, wx.EXPAND | wx.ALL, 4)

        self.btn_aplicar_jug.Bind(wx.EVT_BUTTON, lambda e: self._aplicar_jugador())
        self.btn_hab.Bind(wx.EVT_BUTTON, lambda e: self._fijar_habilidad())
        self.btn_curar.Bind(wx.EVT_BUTTON, lambda e: self._accion_jugador("curar_todo", "Salud, blindaje y foco restaurados."))
        self.btn_necesidades.Bind(wx.EVT_BUTTON, lambda e: self._accion_jugador("llenar_necesidades", "Necesidades rellenadas al máximo."))
        self.btn_dinero5k.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("jugador.set", {"dinero_delta": 5000}, "Añadidos 5000 euros en mano."))
        self.btn_dinero50k.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("jugador.set", {"dinero_delta": 50000}, "Añadidos 50000 euros en mano."))
        self.btn_max_habs.Bind(wx.EVT_BUTTON, lambda e: self._accion_jugador("max_habilidades", "Todas las habilidades al nivel máximo."))
        self.btn_antecedentes.Bind(wx.EVT_BUTTON, lambda e: self._accion_jugador("borrar_antecedentes", "Antecedentes, sospechas y dinero negro limpiados."))
        self.btn_propiedades.Bind(wx.EVT_BUTTON, lambda e: self._accion_jugador("desbloquear_propiedades", "Todas las casas y negocios añadidos a tus propiedades."))
        self.btn_banda.Bind(wx.EVT_BUTTON, lambda e: self._accion_jugador("llamar_banda", "Tu banda acude a tu lado."))
        self.btn_perro.Bind(wx.EVT_BUTTON, lambda e: self._accion_jugador("adoptar_perro", "Perro compañero activado junto a ti."))
        self.chk_invulnerable.Bind(wx.EVT_CHECKBOX, lambda e: self._toggle_cfg("invulnerable", self.chk_invulnerable.GetValue()))
        self.chk_sin_policia.Bind(wx.EVT_CHECKBOX, lambda e: self._toggle_cfg("sin_policia", self.chk_sin_policia.GetValue()))

        pag.SetSizer(s)
        self.libro.AddPage(pag, "Jugador")

    def _construir_tab_inventario(self) -> None:
        pag = wx.Panel(self.libro, name="Inventario")
        s = wx.BoxSizer(wx.VERTICAL)

        _, self.sel_arma = crear_campo(
            pag, "&Arma del catálogo:", wx.Choice, choices=[],
            ayuda="Lista dinámica de todas las armas del juego y sus mods.",
            sizer=s,
        )
        fila_arma = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sp_balas = crear_campo(
            pag, "&Munición:", wx.SpinCtrl, min=0, max=99999, initial=250,
            ayuda="Balas de reserva que añadir o fijar.",
            sizer=fila_arma, horizontal=True, expandir=False,
        )
        self.chk_silenciador = wx.CheckBox(pag, label="S&ilenciador")
        self.chk_ampliado = wx.CheckBox(pag, label="Cargador am&pliado")
        fila_arma.Add(self.chk_silenciador, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        fila_arma.Add(self.chk_ampliado, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        s.Add(fila_arma, 0, wx.EXPAND | wx.ALL, 4)

        b_armas = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_dar_arma = wx.Button(pag, label="&Dar y equipar arma")
        self.btn_dar_todas = wx.Button(pag, label="Dar &todas las armas")
        self.btn_equipar_arma = wx.Button(pag, label="&Equipar")
        self.btn_quitar_arma = wx.Button(pag, label="&Quitar arma")
        for b in (self.btn_dar_arma, self.btn_dar_todas, self.btn_equipar_arma, self.btn_quitar_arma):
            b_armas.Add(b, 0, wx.ALL, 4)
        s.Add(b_armas, 0, wx.EXPAND | wx.ALL, 2)

        fila_obj = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sel_objeto = crear_campo(
            pag, "&Objeto útil:", wx.Choice, choices=[],
            ayuda="Botiquines, ganzúas, pienso, chaleco, bidón, rueda, etc.",
            sizer=fila_obj, horizontal=True,
        )
        _, self.sp_obj_cant = crear_campo(
            pag, "Ca&ntidad:", wx.SpinCtrl, min=1, max=999, initial=5,
            sizer=fila_obj, horizontal=True, expandir=False,
        )
        self.btn_dar_objeto = wx.Button(pag, label="Añadir o&bjeto")
        fila_obj.Add(self.btn_dar_objeto, 0, wx.ALL, 4)
        s.Add(fila_obj, 0, wx.EXPAND | wx.ALL, 2)

        fila_val = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sel_valor = crear_campo(
            pag, "Objeto de &valor (mochila):", wx.Choice, choices=[],
            sizer=fila_val, horizontal=True,
        )
        self.btn_dar_valor = wx.Button(pag, label="Meter en moc&hila")
        self.btn_mochila_grande = wx.Button(pag, label="Mochila &grande (40)")
        self.btn_blanquear_mochila = wx.Button(pag, label="&Limpiar marca robado")
        fila_val.Add(self.btn_dar_valor, 0, wx.ALL, 4)
        fila_val.Add(self.btn_mochila_grande, 0, wx.ALL, 4)
        fila_val.Add(self.btn_blanquear_mochila, 0, wx.ALL, 4)
        s.Add(fila_val, 0, wx.EXPAND | wx.ALL, 2)

        fila_sust = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sel_sustancia = crear_campo(
            pag, "&Sustancia:", wx.Choice, choices=[],
            sizer=fila_sust, horizontal=True,
        )
        self.btn_dar_sustancia = wx.Button(pag, label="Añadir +10 &unidades")
        fila_sust.Add(self.btn_dar_sustancia, 0, wx.ALL, 4)
        s.Add(fila_sust, 0, wx.EXPAND | wx.ALL, 2)

        fila_prod = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sel_producto = crear_campo(
            pag, "Comida / &producto:", wx.Choice, choices=[],
            sizer=fila_prod, horizontal=True,
        )
        self.btn_dar_producto = wx.Button(pag, label="Añadir +5 al &bolsillo")
        fila_prod.Add(self.btn_dar_producto, 0, wx.ALL, 4)
        s.Add(fila_prod, 0, wx.EXPAND | wx.ALL, 2)

        self.btn_dar_arma.Bind(wx.EVT_BUTTON, lambda e: self._accion_arma("dar"))
        self.btn_dar_todas.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar(
            "inventario.arma",
            {"accion": "dar_todas", "balas": self.sp_balas.GetValue(), "silenciador": self.chk_silenciador.GetValue(), "ampliado": self.chk_ampliado.GetValue()},
            "Todas las armas añadidas al arsenal.",
        ))
        self.btn_equipar_arma.Bind(wx.EVT_BUTTON, lambda e: self._accion_arma("equipar"))
        self.btn_quitar_arma.Bind(wx.EVT_BUTTON, lambda e: self._accion_arma("quitar"))
        self.btn_dar_objeto.Bind(wx.EVT_BUTTON, lambda e: self._dar_objeto())
        self.btn_dar_valor.Bind(wx.EVT_BUTTON, lambda e: self._dar_valor())
        self.btn_mochila_grande.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("inventario.objeto", {"tipo": "mochila_grande", "valor": True}, "Mochila grande activada."))
        self.btn_blanquear_mochila.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("inventario.objeto", {"tipo": "vaciar_robados"}, "Objetos de la mochila marcados como legítimos."))
        self.btn_dar_sustancia.Bind(wx.EVT_BUTTON, lambda e: self._dar_sustancia())
        self.btn_dar_producto.Bind(wx.EVT_BUTTON, lambda e: self._dar_producto())

        pag.SetSizer(s)
        self.libro.AddPage(pag, "Inventario")

    def _construir_tab_vehiculos(self) -> None:
        pag = wx.Panel(self.libro, name="Vehículos")
        s = wx.BoxSizer(wx.VERTICAL)

        box_crear = wx.StaticBoxSizer(wx.VERTICAL, pag, "Generar vehículo nuevo")
        box_p = box_crear.GetStaticBox()
        _, self.sel_modelo_veh = crear_campo(
            box_p, "&Modelo a generar:", wx.Choice, choices=[],
            ayuda="Todos los vehículos del juego y mods.",
            sizer=box_crear,
        )
        fila_c1 = wx.BoxSizer(wx.HORIZONTAL)
        _, self.txt_veh_nombre = crear_campo(
            box_p, "&Nombre propio (opcional):", wx.TextCtrl,
            sizer=fila_c1, horizontal=True,
        )
        self.chk_veh_mio = wx.CheckBox(box_p, label="Hacer &mío")
        self.chk_veh_mio.SetValue(True)
        self.chk_veh_subir = wx.CheckBox(box_p, label="&Subir al instante")
        self.chk_veh_subir.SetValue(True)
        self.chk_veh_mejoras_max = wx.CheckBox(box_p, label="Me&joras al máximo")
        fila_c1.Add(self.chk_veh_mio, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        fila_c1.Add(self.chk_veh_subir, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        fila_c1.Add(self.chk_veh_mejoras_max, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        box_crear.Add(fila_c1, 0, wx.EXPAND | wx.ALL, 2)

        self.btn_crear_veh = wx.Button(box_p, label="&Generar vehículo junto a mí")
        box_crear.Add(self.btn_crear_veh, 0, wx.ALL, 4)
        s.Add(box_crear, 0, wx.EXPAND | wx.ALL, 4)

        _, self.lista_vehiculos = crear_campo(
            pag, "&Vehículos en la localidad actual:", wx.ListBox, choices=[], size=(-1, 130),
            ayuda="Selecciona un vehículo vivo para editar sus especificaciones o aplicar acciones.",
            sizer=s,
        )

        b_veh = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_veh_subir = wx.Button(pag, label="S&ubir")
        self.btn_veh_traer = wx.Button(pag, label="&Traer aquí")
        self.btn_veh_reparar = wx.Button(pag, label="&Reparar")
        self.btn_veh_combustible = wx.Button(pag, label="Llenar &depósito")
        self.btn_veh_averias = wx.Button(pag, label="Quitar a&verías")
        self.btn_veh_mejoras = wx.Button(pag, label="M&ejoras máx.")
        self.btn_veh_mio = wx.Button(pag, label="Hacer &propio")
        self.btn_veh_explotar = wx.Button(pag, label="E&xplotar")
        self.btn_veh_eliminar = wx.Button(pag, label="E&liminar")
        self.btn_veh_limpiar = wx.Button(pag, label="Limpiar tráf&ico")
        for b in (
            self.btn_veh_subir, self.btn_veh_traer, self.btn_veh_reparar, self.btn_veh_combustible,
            self.btn_veh_averias, self.btn_veh_mejoras, self.btn_veh_mio, self.btn_veh_explotar,
            self.btn_veh_eliminar, self.btn_veh_limpiar,
        ):
            b_veh.Add(b, 0, wx.ALL, 3)
        s.Add(b_veh, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)

        box_ed = wx.StaticBoxSizer(wx.VERTICAL, pag, "Especificaciones del vehículo seleccionado")
        ed_p = box_ed.GetStaticBox()
        grid_v = wx.FlexGridSizer(cols=4, vgap=4, hgap=8)
        grid_v.AddGrowableCol(1, 1)
        grid_v.AddGrowableCol(3, 1)

        def _vnum(etq, minimo, maximo, inc):
            lbl = wx.StaticText(ed_p, label=etq)
            ctrl = wx.SpinCtrlDouble(ed_p, min=minimo, max=maximo, initial=25.0, inc=inc, name=etq.replace("&", "").rstrip(":"))
            ctrl.SetDigits(1)
            grid_v.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid_v.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        self.sp_veh_vel = _vnum("Velocidad má&x. (m/s):", 1.0, 250.0, 2.0)
        self.sp_veh_acel = _vnum("&Aceleración:", 0.5, 100.0, 1.0)
        self.sp_veh_freno = _vnum("&Freno:", 0.5, 100.0, 1.0)
        self.sp_veh_salud = _vnum("Salud a&ctual:", 1.0, 50000.0, 20.0)
        self.sp_veh_salud_max = _vnum("Salud má&xima:", 10.0, 50000.0, 20.0)
        box_ed.Add(grid_v, 0, wx.EXPAND | wx.ALL, 4)

        fila_ed = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sel_veh_ia = crear_campo(
            ed_p, "Modo &IA:", wx.Choice, choices=["None", "aparcado", "trafico", "huida", "policia", "barco"],
            sizer=fila_ed, horizontal=True,
        )
        self.chk_veh_solo_este = wx.CheckBox(ed_p, label="Aplicar solo a este e&jemplar")
        self.chk_veh_solo_este.SetValue(True)
        self.btn_veh_guardar_specs = wx.Button(ed_p, label="A&plicar especificaciones")
        fila_ed.Add(self.chk_veh_solo_este, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        fila_ed.Add(self.btn_veh_guardar_specs, 0, wx.ALL, 4)
        box_ed.Add(fila_ed, 0, wx.EXPAND | wx.ALL, 2)
        s.Add(box_ed, 0, wx.EXPAND | wx.ALL, 4)

        self.btn_crear_veh.Bind(wx.EVT_BUTTON, lambda e: self._crear_vehiculo())
        self.lista_vehiculos.Bind(wx.EVT_LISTBOX, lambda e: self._cargar_vehiculo_seleccionado())
        self.btn_veh_subir.Bind(wx.EVT_BUTTON, lambda e: self._accion_vehiculo("subir", "Has subido al vehículo."))
        self.btn_veh_traer.Bind(wx.EVT_BUTTON, lambda e: self._accion_vehiculo("traer_aqui", "Vehículo traído junto a ti."))
        self.btn_veh_reparar.Bind(wx.EVT_BUTTON, lambda e: self._editar_vehiculo({"reparar": True}, "Vehículo reparado."))
        self.btn_veh_combustible.Bind(wx.EVT_BUTTON, lambda e: self._editar_vehiculo({"llenar_combustible": True}, "Depósito lleno."))
        self.btn_veh_averias.Bind(wx.EVT_BUTTON, lambda e: self._editar_vehiculo({"quitar_averias": True}, "Averías y pinchazos eliminados."))
        self.btn_veh_mejoras.Bind(wx.EVT_BUTTON, lambda e: self._editar_vehiculo({"mejoras_max": True}, "Todas las mejoras de taller aplicadas."))
        self.btn_veh_mio.Bind(wx.EVT_BUTTON, lambda e: self._accion_vehiculo("hacer_mio", "Vehículo marcado como tuyo."))
        self.btn_veh_explotar.Bind(wx.EVT_BUTTON, lambda e: self._accion_vehiculo("explotar", "Vehículo detonado."))
        self.btn_veh_eliminar.Bind(wx.EVT_BUTTON, lambda e: self._accion_vehiculo("eliminar", "Vehículo eliminado."))
        self.btn_veh_limpiar.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("vehiculos.accion", {"accion": "limpiar_trafico"}, "Tráfico de la calle limpiado."))
        self.btn_veh_guardar_specs.Bind(wx.EVT_BUTTON, lambda e: self._guardar_specs_vehiculo())

        pag.SetSizer(s)
        self.libro.AddPage(pag, "Vehículos")

    def _construir_tab_npcs(self) -> None:
        pag = wx.Panel(self.libro, name="NPCs y Bandas")
        s = wx.BoxSizer(wx.VERTICAL)

        box_gen = wx.StaticBoxSizer(wx.VERTICAL, pag, "Generar NPCs / Enemigos / Aliados")
        gp = box_gen.GetStaticBox()
        fila1 = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sel_npc_modo = crear_campo(
            gp, "&Tipo de entidad:", wx.Choice,
            choices=["enemigo", "pandillero", "policia", "civil", "aliado", "perro"],
            sizer=fila1, horizontal=True,
        )
        _, self.sel_npc_clase = crear_campo(
            gp, "&Clase (catálogo):", wx.Choice, choices=[],
            sizer=fila1, horizontal=True,
        )
        _, self.sel_npc_banda = crear_campo(
            gp, "&Banda:", wx.Choice, choices=["(ninguna)"],
            sizer=fila1, horizontal=True,
        )
        box_gen.Add(fila1, 0, wx.EXPAND | wx.ALL, 2)

        fila2 = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sel_npc_arma = crear_campo(
            gp, "Ar&ma:", wx.Choice, choices=["(por defecto)"],
            sizer=fila2, horizontal=True,
        )
        _, self.sp_npc_cant = crear_campo(
            gp, "&Cantidad:", wx.SpinCtrl, min=1, max=20, initial=1,
            sizer=fila2, horizontal=True, expandir=False,
        )
        _, self.sp_npc_salud = crear_campo(
            gp, "&Salud:", wx.SpinCtrl, min=1, max=5000, initial=75,
            sizer=fila2, horizontal=True, expandir=False,
        )
        self.chk_npc_veh = wx.CheckBox(gp, label="Llegan en &vehículo")
        self.chk_npc_hostil = wx.CheckBox(gp, label="&Hostil")
        self.chk_npc_hostil.SetValue(True)
        fila2.Add(self.chk_npc_veh, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        fila2.Add(self.chk_npc_hostil, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        box_gen.Add(fila2, 0, wx.EXPAND | wx.ALL, 2)

        self.btn_npc_crear = wx.Button(gp, label="&Generar NPC(s) aquí")
        box_gen.Add(self.btn_npc_crear, 0, wx.ALL, 4)
        s.Add(box_gen, 0, wx.EXPAND | wx.ALL, 4)

        _, self.lista_npcs = crear_campo(
            pag, "&Personas en la zona actual:", wx.ListBox, choices=[], size=(-1, 130),
            sizer=s,
        )

        fila_ed = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sp_npc_ed_salud = crear_campo(
            pag, "Salud se&leccionado:", wx.SpinCtrl, min=0, max=10000, initial=80,
            sizer=fila_ed, horizontal=True, expandir=False,
        )
        _, self.sp_npc_ed_punt = crear_campo(
            pag, "&Puntería (0-1):", wx.SpinCtrlDouble, min=0.0, max=1.0, initial=0.42, inc=0.05,
            sizer=fila_ed, horizontal=True, expandir=False,
        )
        self.sp_npc_ed_punt.SetDigits(2)
        self.chk_npc_ed_hostil = wx.CheckBox(pag, label="Hostil a&hora")
        self.btn_npc_aplicar = wx.Button(pag, label="A&plicar a NPC")
        fila_ed.Add(self.chk_npc_ed_hostil, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        fila_ed.Add(self.btn_npc_aplicar, 0, wx.ALL, 4)
        s.Add(fila_ed, 0, wx.EXPAND | wx.ALL, 2)

        b_npc = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_npc_traer = wx.Button(pag, label="&Traer aquí")
        self.btn_npc_curar = wx.Button(pag, label="Cu&rar")
        self.btn_npc_matar = wx.Button(pag, label="M&atar")
        self.btn_npc_eliminar = wx.Button(pag, label="Elimina&r")
        self.btn_npc_limp_hostiles = wx.Button(pag, label="Eliminar todos los h&ostiles")
        self.btn_npc_limp_muertos = wx.Button(pag, label="Limpiar caí&dos")
        for b in (
            self.btn_npc_traer, self.btn_npc_curar, self.btn_npc_matar,
            self.btn_npc_eliminar, self.btn_npc_limp_hostiles, self.btn_npc_limp_muertos,
        ):
            b_npc.Add(b, 0, wx.ALL, 3)
        s.Add(b_npc, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)

        fila_rep = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sel_rep_banda = crear_campo(
            pag, "Reputación con ban&da:", wx.Choice, choices=["__todas__"],
            sizer=fila_rep, horizontal=True,
        )
        _, self.sp_rep_val = crear_campo(
            pag, "Valor (-100 a 100):", wx.SpinCtrl, min=-100, max=100, initial=60,
            sizer=fila_rep, horizontal=True, expandir=False,
        )
        self.btn_rep_aplicar = wx.Button(pag, label="&Fijar reputación")
        fila_rep.Add(self.btn_rep_aplicar, 0, wx.ALL, 4)
        s.Add(fila_rep, 0, wx.EXPAND | wx.ALL, 4)

        self.btn_npc_crear.Bind(wx.EVT_BUTTON, lambda e: self._crear_npc())
        self.lista_npcs.Bind(wx.EVT_LISTBOX, lambda e: self._cargar_npc_seleccionado())
        self.btn_npc_aplicar.Bind(wx.EVT_BUTTON, lambda e: self._aplicar_npc())
        self.btn_npc_traer.Bind(wx.EVT_BUTTON, lambda e: self._accion_npc("traer_aqui", "NPC traído junto a ti."))
        self.btn_npc_curar.Bind(wx.EVT_BUTTON, lambda e: self._accion_npc("curar", "NPC curado."))
        self.btn_npc_matar.Bind(wx.EVT_BUTTON, lambda e: self._accion_npc("matar", "NPC abatido."))
        self.btn_npc_eliminar.Bind(wx.EVT_BUTTON, lambda e: self._accion_npc("eliminar", "NPC eliminado."))
        self.btn_npc_limp_hostiles.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("npcs.accion", {"accion": "eliminar_hostiles"}, "Hostiles eliminados."))
        self.btn_npc_limp_muertos.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("npcs.accion", {"accion": "eliminar_muertos"}, "NPCs caídos limpiados."))
        self.btn_rep_aplicar.Bind(wx.EVT_BUTTON, lambda e: self._fijar_rep_banda())

        pag.SetSizer(s)
        self.libro.AddPage(pag, "NPCs y Bandas")

    def _construir_tab_policia(self) -> None:
        pag = wx.Panel(self.libro, name="Policía")
        s = wx.BoxSizer(wx.VERTICAL)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sp_estrellas = crear_campo(
            pag, "&Nivel de búsqueda (0 a 5 estrellas):", wx.SpinCtrl, min=0, max=5, initial=0,
            ayuda="Nivel de búsqueda policial de 0 a 5.",
            sizer=fila, horizontal=True, expandir=False,
        )
        self.btn_estrellas = wx.Button(pag, label="&Fijar estrellas")
        self.btn_limpiar_busq = wx.Button(pag, label="&Limpiar búsqueda y persecución")
        fila.Add(self.btn_estrellas, 0, wx.ALL, 4)
        fila.Add(self.btn_limpiar_busq, 0, wx.ALL, 4)
        s.Add(fila, 0, wx.EXPAND | wx.ALL, 6)

        b_pol = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_patrulla = wx.Button(pag, label="Mandar &patrulla")
        self.btn_patrulla_ronda = wx.Button(pag, label="Patrulla de &ronda")
        self.btn_heli_on = wx.Button(pag, label="Lanzar &helicóptero")
        self.btn_heli_off = wx.Button(pag, label="&Retirar helicóptero")
        for b in (self.btn_patrulla, self.btn_patrulla_ronda, self.btn_heli_on, self.btn_heli_off):
            b_pol.Add(b, 0, wx.ALL, 4)
        s.Add(b_pol, 0, wx.EXPAND | wx.ALL, 4)

        self.chk_pol_heli = wx.CheckBox(pag, label="Activar helicóptero policial en &nivel 5")
        s.Add(self.chk_pol_heli, 0, wx.ALL, 6)

        self.btn_estrellas.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("policia.set", {"estrellas": self.sp_estrellas.GetValue()}, f"Nivel de búsqueda fijado a {self.sp_estrellas.GetValue()}."))
        self.btn_limpiar_busq.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("policia.set", {"estrellas": 0, "limpiar_policias": True}, "Búsqueda limpiada y agentes retirados."))
        self.btn_patrulla.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("policia.set", {"lanzar_patrulla": True}, "Patrulla enviada."))
        self.btn_patrulla_ronda.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("policia.set", {"lanzar_patrulla_ronda": True}, "Patrulla de ronda generada."))
        self.btn_heli_on.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("policia.set", {"lanzar_helicoptero": True}, "Helicóptero de la policía desplegado."))
        self.btn_heli_off.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("policia.set", {"quitar_helicoptero": True}, "Helicóptero retirado."))
        self.chk_pol_heli.Bind(wx.EVT_CHECKBOX, lambda e: self._toggle_cfg("helicoptero_policia", self.chk_pol_heli.GetValue()))

        pag.SetSizer(s)
        self.libro.AddPage(pag, "Policía")

    def _construir_tab_eventos(self) -> None:
        pag = wx.Panel(self.libro, name="Eventos")
        s = wx.BoxSizer(wx.VERTICAL)

        box_suc = wx.StaticBoxSizer(wx.HORIZONTAL, pag, "Sucesos callejeros aleatorios")
        sp_suc = box_suc.GetStaticBox()
        self.btn_ev_atraco = wx.Button(sp_suc, label="Suceso: &Atraco a peatón")
        self.btn_ev_banda = wx.Button(sp_suc, label="Suceso: &Pandilleros")
        self.btn_ev_maletin = wx.Button(sp_suc, label="Suceso: &Maletín perdido")
        self.btn_ev_cancelar = wx.Button(sp_suc, label="&Cancelar suceso")
        for b in (self.btn_ev_atraco, self.btn_ev_banda, self.btn_ev_maletin, self.btn_ev_cancelar):
            box_suc.Add(b, 0, wx.ALL, 4)
        s.Add(box_suc, 0, wx.EXPAND | wx.ALL, 4)

        box_pers = wx.StaticBoxSizer(wx.HORIZONTAL, pag, "Persecución en vehículo")
        pp = box_pers.GetStaticBox()
        _, self.sel_pers_modelo = crear_campo(
            pp, "M&odelo fugitivo:", wx.Choice, choices=[],
            sizer=box_pers, horizontal=True,
        )
        _, self.sp_pers_vel = crear_campo(
            pp, "&Velocidad objetivo:", wx.SpinCtrl, min=8, max=80, initial=24,
            sizer=box_pers, horizontal=True, expandir=False,
        )
        self.btn_ev_pers = wx.Button(pp, label="Lanzar &persecución")
        box_pers.Add(self.btn_ev_pers, 0, wx.ALL, 4)
        s.Add(box_pers, 0, wx.EXPAND | wx.ALL, 4)

        box_gue = wx.StaticBoxSizer(wx.HORIZONTAL, pag, "Guerras, peleas y territorio")
        gp = box_gue.GetStaticBox()
        _, self.sel_ev_banda = crear_campo(
            gp, "&Banda rival:", wx.Choice, choices=[],
            sizer=box_gue, horizontal=True,
        )
        self.btn_ev_guerra = wx.Button(gp, label="Iniciar &guerra de barrio")
        self.btn_ev_pelea = wx.Button(gp, label="Buscar &pelea")
        self.btn_ev_fin_guerra = wx.Button(gp, label="&Terminar guerra")
        for b in (self.btn_ev_guerra, self.btn_ev_pelea, self.btn_ev_fin_guerra):
            box_gue.Add(b, 0, wx.ALL, 4)
        s.Add(box_gue, 0, wx.EXPAND | wx.ALL, 4)

        b_otros = wx.WrapSizer(wx.HORIZONTAL)
        self.btn_ev_atr_local = wx.Button(pag, label="Atracar &local cercano")
        self.btn_ev_atr_banco = wx.Button(pag, label="Atracar ba&nco cercano")
        self.btn_ev_vetos = wx.Button(pag, label="Limpiar &vetos de locales")
        self.btn_ev_ambu = wx.Button(pag, label="Mandar am&bulancia")
        self.btn_ev_dinero = wx.Button(pag, label="Soltar maletín de &1.000 €")
        self.btn_ev_contrato = wx.Button(pag, label="Iniciar &contrato")
        self.btn_ev_encargo = wx.Button(pag, label="Encargo de &coche")
        for b in (
            self.btn_ev_atr_local, self.btn_ev_atr_banco, self.btn_ev_vetos,
            self.btn_ev_ambu, self.btn_ev_dinero, self.btn_ev_contrato, self.btn_ev_encargo,
        ):
            b_otros.Add(b, 0, wx.ALL, 4)
        s.Add(b_otros, 0, wx.EXPAND | wx.ALL, 4)

        self.btn_ev_atraco.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("eventos.lanzar", {"tipo": "suceso_atraco"}, "Suceso de atraco generado cerca."))
        self.btn_ev_banda.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("eventos.lanzar", {"tipo": "suceso_banda"}, "Suceso de pandilleros generado cerca."))
        self.btn_ev_maletin.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("eventos.lanzar", {"tipo": "suceso_maletin"}, "Maletín perdido generado cerca."))
        self.btn_ev_cancelar.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("eventos.lanzar", {"tipo": "cancelar_suceso"}, "Suceso cancelado."))
        self.btn_ev_pers.Bind(wx.EVT_BUTTON, lambda e: self._lanzar_persecucion())
        self.btn_ev_guerra.Bind(wx.EVT_BUTTON, lambda e: self._lanzar_guerra("guerra_barrio"))
        self.btn_ev_pelea.Bind(wx.EVT_BUTTON, lambda e: self._lanzar_guerra("buscar_pelea"))
        self.btn_ev_fin_guerra.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("eventos.lanzar", {"tipo": "terminar_guerra"}, "Guerra o pelea terminada."))
        self.btn_ev_atr_local.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("eventos.lanzar", {"tipo": "atraco_local_cercano"}, "Atraco al local cercano iniciado."))
        self.btn_ev_atr_banco.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("eventos.lanzar", {"tipo": "atraco_banco_cercano"}, "Atraco al banco cercano iniciado."))
        self.btn_ev_vetos.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("eventos.lanzar", {"tipo": "limpiar_vetos"}, "Vetos de locales y proveedores limpiados."))
        self.btn_ev_ambu.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("eventos.lanzar", {"tipo": "ambulancia"}, "Ambulancia en camino."))
        self.btn_ev_dinero.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("eventos.lanzar", {"tipo": "soltar_dinero", "valor": 1000}, "Maletín de 1000 euros soltado junto a ti."))
        self.btn_ev_contrato.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("eventos.lanzar", {"tipo": "contrato"}, "Contrato iniciado."))
        self.btn_ev_encargo.Bind(wx.EVT_BUTTON, lambda e: self._ejecutar("eventos.lanzar", {"tipo": "encargo_coche"}, "Encargo de vehículo iniciado."))

        pag.SetSizer(s)
        self.libro.AddPage(pag, "Eventos")

    def _construir_tab_mundo(self) -> None:
        pag = wx.Panel(self.libro, name="Mundo y Teletransporte")
        s = wx.BoxSizer(wx.VERTICAL)

        _, self.sel_mapa = crear_campo(
            pag, "&Mapa / Localidad:", wx.Choice, choices=[],
            sizer=s,
        )
        _, self.txt_filtro_lugar = crear_campo(
            pag, "&Filtrar lugares:", wx.TextCtrl,
            ayuda="Escribe parte del nombre o tipo de lugar para filtrar la lista.",
            sizer=s,
        )
        _, self.sel_lugar = crear_campo(
            pag, "&Lugar de destino:", wx.Choice, choices=[],
            sizer=s,
        )
        self.btn_tp = wx.Button(pag, label="&Teletransportar al lugar elegido")
        s.Add(self.btn_tp, 0, wx.ALL, 4)

        fila_t = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sp_hora = crear_campo(
            pag, "&Hora (0-23):", wx.SpinCtrl, min=0, max=23, initial=12,
            sizer=fila_t, horizontal=True, expandir=False,
        )
        _, self.sp_dia = crear_campo(
            pag, "&Día:", wx.SpinCtrl, min=1, max=99999, initial=1,
            sizer=fila_t, horizontal=True, expandir=False,
        )
        self.chk_lluvia = wx.CheckBox(pag, label="&Lluvia")
        fila_t.Add(self.chk_lluvia, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        _, self.sel_dia_azar = crear_campo(
            pag, "Tipo de &día:", wx.Choice, choices=[],
            sizer=fila_t, horizontal=True,
        )
        self.btn_aplicar_tiempo = wx.Button(pag, label="A&plicar tiempo")
        fila_t.Add(self.btn_aplicar_tiempo, 0, wx.ALL, 4)
        s.Add(fila_t, 0, wx.EXPAND | wx.ALL, 4)

        box_cfg = wx.StaticBoxSizer(wx.VERTICAL, pag, "Opciones rápidas de jugabilidad (cfg)")
        cp = box_cfg.GetStaticBox()
        wrap_cfg = wx.WrapSizer(wx.HORIZONTAL)
        self._chks_cfg: dict[str, wx.CheckBox] = {}
        for clave, etiqueta in (
            ("adultos", "Contenido +18"),
            ("fuego_amigo", "Fuego amigo"),
            ("guerra_calle", "Guerra de barrios"),
            ("vida_realista", "Vida realista"),
            ("combustible", "Combustible"),
            ("averias", "Averías"),
            ("normas_trafico", "Normas de tráfico"),
            ("soltar_armas", "Soltar armas"),
            ("mod_enemigos", "Enemigos duros"),
            ("mod_policia", "Policía estricta"),
        ):
            chk = wx.CheckBox(cp, label=etiqueta)
            chk.Bind(wx.EVT_CHECKBOX, lambda e, k=clave, c=chk: self._toggle_cfg(k, c.GetValue()))
            self._chks_cfg[clave] = chk
            wrap_cfg.Add(chk, 0, wx.ALL, 5)
        box_cfg.Add(wrap_cfg, 0, wx.EXPAND)
        s.Add(box_cfg, 0, wx.EXPAND | wx.ALL, 4)

        self.sel_mapa.Bind(wx.EVT_CHOICE, lambda e: self._poblar_lugares())
        self.txt_filtro_lugar.Bind(wx.EVT_TEXT, lambda e: self._poblar_lugares())
        self.btn_tp.Bind(wx.EVT_BUTTON, lambda e: self._teletransportar())
        self.btn_aplicar_tiempo.Bind(wx.EVT_BUTTON, lambda e: self._aplicar_tiempo())

        pag.SetSizer(s)
        self.libro.AddPage(pag, "Mundo")

    def _construir_tab_inspector(self) -> None:
        pag = wx.Panel(self.libro, name="Inspector Avanzado")
        s = wx.BoxSizer(wx.VERTICAL)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        _, self.sel_insp_obj = crear_campo(
            pag, "Á&mbito:", wx.Choice, choices=["jugador", "stats", "cfg", "vehiculo_actual"],
            ayuda="Permite inspeccionar y modificar cualquier atributo en vivo, incluso de futuras actualizaciones.",
            sizer=fila, horizontal=True,
        )
        _, self.txt_insp_filtro = crear_campo(
            pag, "&Filtrar clave:", wx.TextCtrl,
            sizer=fila, horizontal=True,
        )
        self.btn_insp_leer = wx.Button(pag, label="&Leer ámbito")
        fila.Add(self.btn_insp_leer, 0, wx.ALL, 4)
        s.Add(fila, 0, wx.EXPAND | wx.ALL, 4)

        _, self.lista_insp = crear_campo(
            pag, "&Campos disponibles:", wx.ListBox, choices=[], size=(-1, 220),
            sizer=s,
        )

        fila_ed = wx.BoxSizer(wx.HORIZONTAL)
        _, self.txt_insp_clave = crear_campo(
            pag, "&Clave:", wx.TextCtrl,
            sizer=fila_ed, horizontal=True,
        )
        _, self.txt_insp_valor = crear_campo(
            pag, "&Nuevo valor (texto o JSON):", wx.TextCtrl,
            sizer=fila_ed, horizontal=True,
        )
        self.btn_insp_escribir = wx.Button(pag, label="A&plicar cambio")
        fila_ed.Add(self.btn_insp_escribir, 0, wx.ALL, 4)
        s.Add(fila_ed, 0, wx.EXPAND | wx.ALL, 4)

        self.btn_insp_leer.Bind(wx.EVT_BUTTON, lambda e: self._leer_inspector())
        self.sel_insp_obj.Bind(wx.EVT_CHOICE, lambda e: self._leer_inspector())
        self.txt_insp_filtro.Bind(wx.EVT_TEXT, lambda e: self._filtrar_inspector())
        self.lista_insp.Bind(wx.EVT_LISTBOX, lambda e: self._seleccionar_clave_inspector())
        self.btn_insp_escribir.Bind(wx.EVT_BUTTON, lambda e: self._escribir_inspector())

        pag.SetSizer(s)
        self.libro.AddPage(pag, "Inspector")

    # ------------------------------------------------------------------ red y datos
    def _tecla_global(self, evento: wx.KeyEvent) -> None:
        if evento.GetKeyCode() == wx.WXK_F5 and evento.GetModifiers() == wx.MOD_NONE:
            self.refrescar_todo(anunciar=True)
            return
        evento.Skip()

    def _al_cerrar(self, evento: wx.CloseEvent) -> None:
        if self.timer.IsRunning():
            self.timer.Stop()
        evento.Skip()

    def _al_timer(self, evento: wx.TimerEvent) -> None:
        if self.cliente is not None:
            self.refrescar_estado(anunciar_error=False)

    def _auto_conectar_silencioso(self) -> None:
        try:
            self.conectar(anunciar=False)
        except Exception:
            pass

    def conectar(self, anunciar: bool = True) -> bool:
        self.instancias = descubrir_instancias()
        if not self.instancias:
            self.cliente = None
            self.sel_instancia.Set(["(ninguna detectada)"])
            self.sel_instancia.SetSelection(0)
            self.txt_conexion.SetValue("No hay ningún Puerto Bravo en ejecución con el puente activo.")
            if anunciar:
                _hablar("No se encontró Puerto Bravo en ejecución.")
            return False
        etiquetas = [f"PID {f['pid']} — v{f.get('version', '?')} (puerto {f['puerto']})" for f in self.instancias]
        sel_idx = max(0, min(self.sel_instancia.GetSelection(), len(self.instancias) - 1))
        self.sel_instancia.Set(etiquetas)
        self.sel_instancia.SetSelection(sel_idx)
        ficha = self.instancias[sel_idx]
        try:
            cli = ClienteTrampas.desde_ficha(ficha)
            hola = cli.llamar("hola")
            self.cliente = cli
            self.catalogos = cli.llamar("catalogos")
            self._poblar_catalogos()
            self.refrescar_estado(anunciar_error=False)
            self.SetStatusText(f"Conectado a PID {hola['pid']} (Puerto Bravo v{hola.get('version', '?')}).")
            if anunciar:
                _hablar("Conectado a Puerto Bravo.")
            return True
        except ErrorPuente as exc:
            self.cliente = None
            self.txt_conexion.SetValue(str(exc))
            if anunciar:
                mostrar_error(self, str(exc), "Error de conexión")
            return False

    def _ejecutar(self, cmd: str, args: dict | None = None, mensaje_voz: str = ""):
        if self.cliente is None:
            if not self.conectar(anunciar=False):
                mostrar_error(self, "Conecta primero con Puerto Bravo en marcha.", "Sin conexión")
                return None
        try:
            res = self.cliente.llamar(cmd, **(args or {}))
            if mensaje_voz:
                self.SetStatusText(mensaje_voz)
                _hablar(mensaje_voz)
            self.refrescar_estado(anunciar_error=False)
            return res
        except ErrorPuente as exc:
            mostrar_error(self, str(exc), "No se pudo aplicar")
            return None

    def refrescar_todo(self, anunciar: bool = False) -> None:
        if self.cliente is None:
            self.conectar(anunciar=anunciar)
            return
        try:
            self.catalogos = self.cliente.llamar("catalogos")
            self._poblar_catalogos()
            self.refrescar_estado(anunciar_error=True)
            if anunciar:
                _hablar("Datos actualizados.")
        except ErrorPuente as exc:
            self.txt_conexion.SetValue(str(exc))

    def refrescar_estado(self, anunciar_error: bool = False) -> None:
        if self.cliente is None:
            return
        try:
            est = self.cliente.llamar("estado")
            self.estado = est
            en_partida = bool(est.get("en_partida"))
            en_linea = bool(est.get("en_linea"))
            if not en_partida:
                self.txt_conexion.SetValue(f"Conectado (pantalla: {est.get('pantalla')}). Esperando a que empieces o cargues una partida.")
                return
            mapa = est.get("mapa", {})
            j = est.get("jugador", {})
            t = est.get("tiempo", {})
            estado_txt = (
                f"Conectado — {mapa.get('nombre')} ({mapa.get('barrio')}) | "
                f"Día {t.get('dia')} {t.get('hora_txt')} | "
                f"Salud {j.get('salud')}/{j.get('salud_max')} | {j.get('dinero')} €"
                + (" [BLOQUEADO EN LÍNEA]" if en_linea else "")
            )
            if self.txt_conexion.GetValue() != estado_txt:
                self.txt_conexion.SetValue(estado_txt)

            resumen = (
                f"{j.get('nombre')} {j.get('apellido')} — Salud {j.get('salud')}/{j.get('salud_max')}, Blindaje {j.get('blindaje')}\n"
                f"Dinero: {j.get('dinero')} € en mano, {j.get('banco')} € en banco | Búsqueda: {j.get('estrellas')} estrellas\n"
                f"Ánimo {j.get('animo')}, Prestigio {j.get('ciudadania')}, Fama {j.get('reputacion')} | Arma: {j.get('arma')}\n"
                f"Entidades vivas: {est.get('conteos', {}).get('vehiculos', 0)} vehículos, {est.get('conteos', {}).get('personas', 0)} personas"
            )
            if resumen != self._ultimo_resumen:
                self._ultimo_resumen = resumen
                self.txt_resumen_jug.SetValue(resumen)

            cfg = est.get("cfg", {})
            self.chk_invulnerable.SetValue(bool(cfg.get("invulnerable", False)))
            self.chk_sin_policia.SetValue(bool(cfg.get("sin_policia", False)))
            self.chk_pol_heli.SetValue(bool(cfg.get("helicoptero_policia", False)))
            for k, chk in self._chks_cfg.items():
                if k in cfg:
                    chk.SetValue(bool(cfg[k]))

            vehs = self.cliente.llamar("vehiculos.listar").get("vehiculos", [])
            self._actualizar_lista_vehiculos(vehs)
            npcs = self.cliente.llamar("npcs.listar").get("personas", [])
            self._actualizar_lista_npcs(npcs)
        except ErrorPuente as exc:
            self.cliente = None
            self.txt_conexion.SetValue(f"Desconectado: {exc}")
            if anunciar_error:
                mostrar_error(self, str(exc), "Error al actualizar")

    def _poblar_catalogos(self) -> None:
        cat = self.catalogos
        armas = cat.get("armas", [])
        self._ids_armas = [a["id"] for a in armas]
        self.sel_arma.Set([f"{a['nombre']} ({a['id']}, daño {a['dano']})" for a in armas])
        if armas:
            self.sel_arma.SetSelection(0)
        self.sel_npc_arma.Set(["(por defecto)"] + [f"{a['nombre']} ({a['id']})" for a in armas])
        self.sel_npc_arma.SetSelection(0)

        objs = cat.get("objetos", [])
        self._ids_objetos = [o["id"] for o in objs]
        self.sel_objeto.Set([f"{o['nombre']} ({o['id']})" for o in objs])
        if objs:
            self.sel_objeto.SetSelection(0)

        vals = cat.get("objetos_valor", [])
        self._ids_valor = [v["id"] for v in vals]
        self.sel_valor.Set([f"{v['nombre']} ({v['valor']} €)" for v in vals])
        if vals:
            self.sel_valor.SetSelection(0)

        susts = cat.get("sustancias", [])
        self._ids_sust = [x["id"] for x in susts]
        self.sel_sustancia.Set([f"{x['nombre']} ({x['id']})" for x in susts] or ["(ninguna)"])
        self.sel_sustancia.SetSelection(0)

        prods = cat.get("productos", [])
        self._ids_prod = [x["id"] for x in prods]
        self.sel_producto.Set([f"{x['nombre']} ({x['id']})" for x in prods] or ["(ninguno)"])
        self.sel_producto.SetSelection(0)

        vehs = cat.get("vehiculos", [])
        self._ids_vehiculos = [v["id"] for v in vehs]
        etq_v = [f"{v['nombre']} ({v['id']} — {v['vel_max']} m/s)" for v in vehs]
        self.sel_modelo_veh.Set(etq_v)
        self.sel_pers_modelo.Set(etq_v)
        if vehs:
            self.sel_modelo_veh.SetSelection(0)
            self.sel_pers_modelo.SetSelection(0)

        tipos_e = cat.get("tipos_enemigo", [])
        self._ids_tipos_enemigo = [""] + [t["id"] for t in tipos_e]
        self.sel_npc_clase.Set(["(genérico)"] + [f"{t.get('nombre', t['id'])} ({t['id']})" for t in tipos_e])
        self.sel_npc_clase.SetSelection(0)

        bandas = [b["nombre"] for b in cat.get("bandas", [])]
        self._nombres_bandas = bandas
        self.sel_npc_banda.Set(["(ninguna)"] + bandas)
        self.sel_npc_banda.SetSelection(0)
        self.sel_rep_banda.Set(["Todas las bandas"] + bandas)
        self.sel_rep_banda.SetSelection(0)
        self.sel_ev_banda.Set(bandas or ["Los Calaveras"])
        self.sel_ev_banda.SetSelection(0)

        dias = cat.get("dias_azar", [])
        self._ids_dias = [d["id"] for d in dias]
        self.sel_dia_azar.Set([d["id"] for d in dias] or ["normal"])
        self.sel_dia_azar.SetSelection(0)

        mapas = cat.get("mapas", [])
        self._mapas = mapas
        self.sel_mapa.Set([f"{m['nombre']} ({m['id']})" for m in mapas])
        if mapas:
            self.sel_mapa.SetSelection(0)
            self._poblar_lugares()

        habs = cat.get("habilidades", {})
        if habs:
            self._ids_habs = list(habs.keys())
            self.sel_hab.Set([f"{v['nombre']} ({k})" for k, v in habs.items()])
            self.sel_hab.SetSelection(0)

    def _poblar_lugares(self) -> None:
        idx = self.sel_mapa.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(getattr(self, "_mapas", [])):
            return
        lugares = self._mapas[idx].get("lugares", [])
        filtro = self.txt_filtro_lugar.GetValue().strip().lower()
        filtrados = [l for l in lugares if not filtro or filtro in l["nombre"].lower() or filtro in l["tipo"].lower() or filtro in l["id"].lower()]
        self._lugares_filtrados = filtrados
        self.sel_lugar.Set([f"{l['nombre']} [{l['tipo']}]" for l in filtrados] or ["(sin coincidencias)"])
        self.sel_lugar.SetSelection(0)

    def _actualizar_lista_vehiculos(self, vehs: list[dict]) -> None:
        sel_id = self._veh_seleccionado_id()
        claves = [f"{v['id']}:{v['nombre']}:{int(v['salud'])}:{v['es_actual']}:{v['mio']}:{v['ia']}" for v in vehs]
        self._vehiculos_vivos = vehs
        if claves == self._ultimas_claves_veh:
            return
        self._ultimas_claves_veh = claves
        etiquetas = [
            f"{'[ACTUAL] ' if v['es_actual'] else ''}{'[MÍO] ' if v['mio'] else ''}"
            f"{v['nombre']} (#{v['id']}, {int(v['salud'])}/{int(v['salud_max'])} HP, {v['dist']} m, ia={v['ia']})"
            for v in vehs
        ]
        self.lista_vehiculos.Set(etiquetas)
        if sel_id is not None:
            for i, v in enumerate(vehs):
                if v["id"] == sel_id:
                    self.lista_vehiculos.SetSelection(i)
                    break
        elif vehs:
            self.lista_vehiculos.SetSelection(0)
            self._cargar_vehiculo_seleccionado()

    def _actualizar_lista_npcs(self, npcs: list[dict]) -> None:
        sel_id = self._npc_seleccionado_id()
        claves = [f"{n['id']}:{n['nombre']}:{int(n['salud'])}:{n['hostil']}:{n['muerto']}" for n in npcs]
        self._personas_vistas = npcs
        if claves == self._ultimas_claves_npc:
            return
        self._ultimas_claves_npc = claves
        etiquetas = [
            f"{'[MUERTO] ' if n['muerto'] else ''}{'[HOSTIL] ' if n['hostil'] else ''}"
            f"{n['nombre']} (#{n['id']}, {n['tipo']}, {int(n['salud'])} HP, {n['dist']} m)"
            for n in npcs
        ]
        self.lista_npcs.Set(etiquetas)
        if sel_id is not None:
            for i, n in enumerate(npcs):
                if n["id"] == sel_id:
                    self.lista_npcs.SetSelection(i)
                    break
        elif npcs:
            self.lista_npcs.SetSelection(0)

    # ------------------------------------------------------------------ acciones UI
    def _toggle_cfg(self, clave: str, valor: bool) -> None:
        self._ejecutar("cfg.set", {"clave": clave, "valor": bool(valor)}, f"{clave} {'activado' if valor else 'desactivado'}.")

    def _aplicar_jugador(self) -> None:
        self._ejecutar(
            "jugador.set",
            {
                "salud": self.sp_salud.GetValue(),
                "salud_max": self.sp_salud_max.GetValue(),
                "blindaje": self.sp_blindaje.GetValue(),
                "dinero": self.sp_dinero.GetValue(),
                "banco": self.sp_banco.GetValue(),
                "animo": self.sp_animo.GetValue(),
                "ciudadania": self.sp_ciudadania.GetValue(),
                "reputacion": self.sp_reputacion.GetValue(),
                "hambre": self.sp_hambre.GetValue(),
                "sed": self.sp_sed.GetValue(),
                "sueno": self.sp_sueno.GetValue(),
                "suciedad": self.sp_suciedad.GetValue(),
                "carne_puntos": self.sp_carne.GetValue(),
                "guardaespaldas": self.sp_guardaespaldas.GetValue(),
            },
            "Estadísticas del jugador actualizadas.",
        )

    def _accion_jugador(self, accion: str, voz: str) -> None:
        self._ejecutar("jugador.set", {"accion": accion}, voz)

    def _fijar_habilidad(self) -> None:
        ids = getattr(self, "_ids_habs", ["conduccion", "punteria", "resistencia", "pesca"])
        idx = self.sel_hab.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(ids):
            return
        hab = ids[idx]
        niv = self.sp_hab_nivel.GetValue()
        self._ejecutar("jugador.habilidad", {"habilidad": hab, "nivel": niv}, f"Habilidad {hab} al nivel {niv}.")

    def _accion_arma(self, accion: str) -> None:
        idx = self.sel_arma.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(getattr(self, "_ids_armas", [])):
            return
        aid = self._ids_armas[idx]
        self._ejecutar(
            "inventario.arma",
            {
                "accion": accion,
                "arma_id": aid,
                "balas": self.sp_balas.GetValue(),
                "silenciador": self.chk_silenciador.GetValue(),
                "ampliado": self.chk_ampliado.GetValue(),
            },
            f"Arma {aid}: acción {accion} aplicada.",
        )

    def _dar_objeto(self) -> None:
        idx = self.sel_objeto.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(getattr(self, "_ids_objetos", [])):
            return
        oid = self._ids_objetos[idx]
        self._ejecutar("inventario.objeto", {"tipo": "objeto", "id": oid, "cantidad": self.sp_obj_cant.GetValue()}, f"Añadido {oid}.")

    def _dar_valor(self) -> None:
        idx = self.sel_valor.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(getattr(self, "_ids_valor", [])):
            return
        vid = self._ids_valor[idx]
        self._ejecutar("inventario.objeto", {"tipo": "valor", "id": vid, "cantidad": 1}, f"Guardado en mochila: {vid}.")

    def _dar_sustancia(self) -> None:
        idx = self.sel_sustancia.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(getattr(self, "_ids_sust", [])):
            return
        sid = self._ids_sust[idx]
        self._ejecutar("inventario.objeto", {"tipo": "sustancia", "id": sid, "cantidad": 10}, f"Añadidas 10 unidades de {sid}.")

    def _dar_producto(self) -> None:
        idx = self.sel_producto.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(getattr(self, "_ids_prod", [])):
            return
        pid = self._ids_prod[idx]
        self._ejecutar("inventario.objeto", {"tipo": "producto", "id": pid, "cantidad": 5}, f"Añadidos 5 de {pid}.")

    def _crear_vehiculo(self) -> None:
        idx = self.sel_modelo_veh.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(getattr(self, "_ids_vehiculos", [])):
            return
        mid = self._ids_vehiculos[idx]
        self._ejecutar(
            "vehiculos.crear",
            {
                "modelo_id": mid,
                "nombre": self.txt_veh_nombre.GetValue().strip(),
                "hacer_mio": self.chk_veh_mio.GetValue(),
                "subir_ahora": self.chk_veh_subir.GetValue(),
                "mejoras_max": self.chk_veh_mejoras_max.GetValue(),
            },
            f"Vehículo {mid} generado.",
        )

    def _veh_seleccionado_id(self) -> int | None:
        idx = self.lista_vehiculos.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self._vehiculos_vivos):
            return None
        return int(self._vehiculos_vivos[idx]["id"])

    def _cargar_vehiculo_seleccionado(self) -> None:
        idx = self.lista_vehiculos.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self._vehiculos_vivos):
            return
        v = self._vehiculos_vivos[idx]
        self.sp_veh_vel.SetValue(float(v.get("vel_max", 25.0)))
        self.sp_veh_acel.SetValue(float(v.get("acel", 6.0)))
        self.sp_veh_freno.SetValue(float(v.get("freno", 12.0)))
        self.sp_veh_salud.SetValue(float(v.get("salud", 100.0)))
        self.sp_veh_salud_max.SetValue(float(v.get("salud_max", 100.0)))
        ia_str = str(v.get("ia")) if v.get("ia") is not None else "None"
        pos = self.sel_veh_ia.FindString(ia_str)
        if pos != wx.NOT_FOUND:
            self.sel_veh_ia.SetSelection(pos)

    def _accion_vehiculo(self, accion: str, voz: str) -> None:
        vid = self._veh_seleccionado_id()
        if vid is None:
            mostrar_error(self, "Selecciona primero un vehículo de la lista.", "Sin selección")
            return
        self._ejecutar("vehiculos.accion", {"id": vid, "accion": accion}, voz)

    def _editar_vehiculo(self, payload: dict, voz: str) -> None:
        vid = self._veh_seleccionado_id()
        if vid is None:
            mostrar_error(self, "Selecciona primero un vehículo de la lista.", "Sin selección")
            return
        datos = dict(payload, id=vid)
        self._ejecutar("vehiculos.editar", datos, voz)

    def _guardar_specs_vehiculo(self) -> None:
        vid = self._veh_seleccionado_id()
        if vid is None:
            mostrar_error(self, "Selecciona primero un vehículo de la lista.", "Sin selección")
            return
        self._ejecutar(
            "vehiculos.editar",
            {
                "id": vid,
                "solo_este": self.chk_veh_solo_este.GetValue(),
                "salud": self.sp_veh_salud.GetValue(),
                "salud_max": self.sp_veh_salud_max.GetValue(),
                "ia": self.sel_veh_ia.GetStringSelection(),
                "specs": {
                    "vel_max": self.sp_veh_vel.GetValue(),
                    "acel": self.sp_veh_acel.GetValue(),
                    "freno": self.sp_veh_freno.GetValue(),
                },
            },
            "Especificaciones del vehículo aplicadas.",
        )

    def _crear_npc(self) -> None:
        c_idx = self.sel_npc_clase.GetSelection()
        clase = self._ids_tipos_enemigo[c_idx] if c_idx != wx.NOT_FOUND and c_idx < len(getattr(self, "_ids_tipos_enemigo", [])) else ""
        b_idx = self.sel_npc_banda.GetSelection()
        banda = self._nombres_bandas[b_idx - 1] if b_idx > 0 and (b_idx - 1) < len(getattr(self, "_nombres_bandas", [])) else None
        a_idx = self.sel_npc_arma.GetSelection()
        arma = self._ids_armas[a_idx - 1] if a_idx > 0 and (a_idx - 1) < len(getattr(self, "_ids_armas", [])) else None
        self._ejecutar(
            "npcs.crear",
            {
                "modo": self.sel_npc_modo.GetStringSelection(),
                "clase": clase,
                "banda": banda,
                "arma": arma,
                "cantidad": self.sp_npc_cant.GetValue(),
                "salud": self.sp_npc_salud.GetValue(),
                "en_vehiculo": self.chk_npc_veh.GetValue(),
                "hostil": self.chk_npc_hostil.GetValue(),
            },
            "NPC generado en la partida.",
        )

    def _npc_seleccionado_id(self) -> int | None:
        idx = self.lista_npcs.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self._personas_vistas):
            return None
        return int(self._personas_vistas[idx]["id"])

    def _cargar_npc_seleccionado(self) -> None:
        idx = self.lista_npcs.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(self._personas_vistas):
            return
        n = self._personas_vistas[idx]
        self.sp_npc_ed_salud.SetValue(int(max(0, n.get("salud", 50))))
        self.sp_npc_ed_punt.SetValue(float(n.get("punteria", 0.42)))
        self.chk_npc_ed_hostil.SetValue(bool(n.get("hostil", False)))

    def _aplicar_npc(self) -> None:
        pid = self._npc_seleccionado_id()
        if pid is None:
            mostrar_error(self, "Selecciona primero una persona de la lista.", "Sin selección")
            return
        self._ejecutar(
            "npcs.editar",
            {
                "id": pid,
                "salud": self.sp_npc_ed_salud.GetValue(),
                "punteria": self.sp_npc_ed_punt.GetValue(),
                "hostil": self.chk_npc_ed_hostil.GetValue(),
            },
            "Atributos del NPC actualizados.",
        )

    def _accion_npc(self, accion: str, voz: str) -> None:
        pid = self._npc_seleccionado_id()
        if pid is None:
            mostrar_error(self, "Selecciona primero una persona de la lista.", "Sin selección")
            return
        self._ejecutar("npcs.accion", {"id": pid, "accion": accion}, voz)

    def _fijar_rep_banda(self) -> None:
        idx = self.sel_rep_banda.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        banda = "__todas__" if idx == 0 else self._nombres_bandas[idx - 1]
        val = self.sp_rep_val.GetValue()
        self._ejecutar("policia.set", {"rep_banda": {"banda": banda, "valor": val}}, f"Reputación de banda fijada a {val}.")

    def _lanzar_persecucion(self) -> None:
        idx = self.sel_pers_modelo.GetSelection()
        mid = self._ids_vehiculos[idx] if idx != wx.NOT_FOUND and idx < len(getattr(self, "_ids_vehiculos", [])) else "deportivo"
        self._ejecutar(
            "eventos.lanzar",
            {"tipo": "persecucion_vehiculo", "modelo_id": mid, "vel_obj": self.sp_pers_vel.GetValue(), "marcar_gps": True},
            "Persecución lanzada y marcada en tu GPS.",
        )

    def _lanzar_guerra(self, tipo: str) -> None:
        idx = self.sel_ev_banda.GetSelection()
        banda = self._nombres_bandas[idx] if idx != wx.NOT_FOUND and idx < len(getattr(self, "_nombres_bandas", [])) else None
        self._ejecutar("eventos.lanzar", {"tipo": tipo, "banda": banda}, "Enfrentamiento de banda iniciado.")

    def _teletransportar(self) -> None:
        lugares = getattr(self, "_lugares_filtrados", [])
        idx = self.sel_lugar.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(lugares):
            return
        l = lugares[idx]
        self._ejecutar("jugador.teletransportar", {"lugar_id": l["id"]}, f"Teletransportado a {l['nombre']}.")

    def _aplicar_tiempo(self) -> None:
        idx_d = self.sel_dia_azar.GetSelection()
        dia_azar = self._ids_dias[idx_d] if idx_d != wx.NOT_FOUND and idx_d < len(getattr(self, "_ids_dias", [])) else None
        self._ejecutar(
            "mundo.set",
            {
                "hora": self.sp_hora.GetValue(),
                "dia": self.sp_dia.GetValue(),
                "lluvia": self.chk_lluvia.GetValue(),
                "dia_azar": dia_azar,
            },
            "Hora, día y clima actualizados.",
        )

    def _leer_inspector(self) -> None:
        if self.cliente is None:
            return
        try:
            res = self.cliente.llamar("inspector.leer", objetivo=self.sel_insp_obj.GetStringSelection())
            self._inspector_campos = res.get("campos", {})
            self._filtrar_inspector()
        except ErrorPuente as exc:
            mostrar_error(self, str(exc), "Inspector")

    def _filtrar_inspector(self) -> None:
        filtro = self.txt_insp_filtro.GetValue().strip().lower()
        claves = [k for k in sorted(self._inspector_campos.keys()) if not filtro or filtro in k.lower()]
        self._inspector_claves = claves
        self.lista_insp.Set([f"{k} = {json.dumps(self._inspector_campos[k], ensure_ascii=False)}" for k in claves])
        if claves:
            self.lista_insp.SetSelection(0)
            self._seleccionar_clave_inspector()

    def _seleccionar_clave_inspector(self) -> None:
        idx = self.lista_insp.GetSelection()
        if idx == wx.NOT_FOUND or idx >= len(getattr(self, "_inspector_claves", [])):
            return
        clave = self._inspector_claves[idx]
        val = self._inspector_campos[clave]
        self.txt_insp_clave.SetValue(clave)
        self.txt_insp_valor.SetValue(val if isinstance(val, str) else json.dumps(val, ensure_ascii=False))

    def _escribir_inspector(self) -> None:
        clave = self.txt_insp_clave.GetValue().strip()
        if not clave:
            return
        res = self._ejecutar(
            "inspector.escribir",
            {"objetivo": self.sel_insp_obj.GetStringSelection(), "clave": clave, "valor": self.txt_insp_valor.GetValue()},
            f"Campo {clave} actualizado.",
        )
        if res is not None:
            self._leer_inspector()


def ejecutar() -> None:
    app = wx.App(False)
    wx.HelpProvider.Set(wx.SimpleHelpProvider())
    v = VentanaTrampas()
    v.Show()
    app.MainLoop()
