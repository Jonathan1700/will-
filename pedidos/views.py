from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Max
from datetime import timedelta, date
import json
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from .models import (
    Mesa, Producto, Orden, DetalleOrden, RegistroAccion, PiezaPollo, TipoMenestra, VarianteProducto,
    Gasto, Cuenta,
)


# ---------- LOGIN / ROLES ----------

def es_mesero(user):
    return user.groups.filter(name="Mesero").exists() or user.is_superuser


def es_cocina(user):
    return user.groups.filter(name="Cocina").exists() or user.is_superuser


def es_admin(user):
    return user.groups.filter(name="Admin").exists() or user.is_superuser


# categorias que se pueden vender directo (sin pasar por cocina) cuando la mesa
# ya esta comiendo y pide algo suelto de mas
CATEGORIAS_VENTA_DIRECTA = {"acompanamientos", "bebidas", "gaseosas"}


def registrar(usuario, texto):
    RegistroAccion.objects.create(usuario=usuario, accion=texto)


def login_view(request):
    if request.user.is_authenticated:
        return redirect("post_login")

    error = None
    if request.method == "POST":
        usuario = authenticate(
            request,
            username=request.POST.get("username"),
            password=request.POST.get("password"),
        )
        if usuario is not None:
            login(request, usuario)
            return redirect("post_login")
        error = "Usuario o contraseña incorrectos"

    return render(request, "pedidos/login.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("login")


def csrf_failure(request, reason=""):
    return render(
        request,
        "pedidos/login.html",
        {"error": "Tu sesion expiro, intenta ingresar de nuevo"},
        status=403,
    )


@login_required
def post_login(request):
    """Redirige segun el rol del usuario que acaba de entrar."""
    if es_admin(request.user):
        return redirect("reportes")
    if es_cocina(request.user):
        return redirect("panel_cocina")
    return redirect("elegir_mesa")


# ---------- MESERO ----------

@login_required
@user_passes_test(es_mesero)
def elegir_mesa(request):
    mesas = Mesa.objects.all().order_by("numero")
    listas = Orden.objects.filter(estado="entregada").order_by("enviado_a_cocina")
    return render(request, "pedidos/elegir_mesa.html", {
        "mesas": mesas,
        "ordenes_listas": listas,
    })


def _siguiente_numero_cuenta(mesa):
    """1, 2, 3... nunca se repite en la mesa aunque cuentas anteriores ya se hayan cerrado."""
    ultimo = mesa.cuentas.aggregate(Max("numero"))["numero__max"]
    return (ultimo or 0) + 1


@login_required
@user_passes_test(es_mesero)
def seleccionar_cuenta(request, mesa_id):
    """Al elegir una mesa: cuantas cuentas tiene abiertas y boton para agregar una mas
    (Cuenta 1, Cuenta 2...). Cocina nunca ve esto, solo organiza el trabajo del mesero."""
    mesa = get_object_or_404(Mesa, id=mesa_id)
    cuentas = [c for c in mesa.cuentas.all() if c.esta_abierta()]
    return render(request, "pedidos/seleccionar_cuenta.html", {"mesa": mesa, "cuentas": cuentas})


@login_required
@user_passes_test(es_mesero)
@require_POST
def agregar_cuenta(request, mesa_id):
    """Boton 'Agregar cuenta': crea la siguiente (Cuenta 1, luego Cuenta 2...) y entra directo a ella."""
    mesa = get_object_or_404(Mesa, id=mesa_id)
    cuenta = Cuenta.objects.create(mesa=mesa, numero=_siguiente_numero_cuenta(mesa))
    return redirect(f"{reverse('menu_mesa', args=[mesa.id])}?cuenta={cuenta.id}")


def ordenes_listas_json(request):
    """Pedidos que cocina ya marco como listos, para avisar en la tablet del mesero."""
    ordenes = Orden.objects.filter(estado="entregada").order_by("enviado_a_cocina")
    data = [{"id": o.id, "mesa": o.mesa.numero} for o in ordenes]
    return JsonResponse({"listas": data})


@login_required
@user_passes_test(es_mesero)
@require_POST
def entregar_a_cliente(request, orden_id):
    """El mesero confirma que ya llevo el pedido listo a la mesa."""
    orden = get_object_or_404(Orden, id=orden_id, estado="entregada")
    orden.estado = "cerrada"
    orden.save()
    registrar(request.user, f"Entrego al cliente orden #{orden.id} - Mesa {orden.mesa.numero}")
    return redirect("elegir_mesa")


@login_required
@user_passes_test(es_mesero)
def menu_mesa(request, mesa_id):
    mesa = get_object_or_404(Mesa, id=mesa_id)

    cuenta_id = request.GET.get("cuenta")
    if cuenta_id:
        cuenta = get_object_or_404(Cuenta, id=cuenta_id, mesa=mesa)
    else:
        # sin cuenta indicada: usa la unica que este abierta, o crea la primera
        cuenta = next((c for c in mesa.cuentas.all() if c.esta_abierta()), None)
        if cuenta is None:
            cuenta = Cuenta.objects.create(mesa=mesa, numero=_siguiente_numero_cuenta(mesa))

    orden, _ = Orden.objects.get_or_create(mesa=mesa, cuenta=cuenta, estado="abierta", es_venta_directa=False)
    orden_directa = Orden.objects.filter(mesa=mesa, estado="abierta", es_venta_directa=True).first()

    categoria = request.GET.get("categoria", "combos")
    productos = Producto.objects.filter(categoria=categoria).order_by("nombre")

    # acompañamientos que pueden reemplazar las papas de un plato ("Mejora tu combo")
    cambios = [
        p for p in Producto.objects.filter(precio_cambio__isnull=False).order_by("nombre")
        if p.esta_disponible()
    ]

    contexto = {
        "mesa": mesa,
        "cuenta": cuenta,
        "orden": orden,
        "orden_directa": orden_directa,
        "productos": productos,
        "categoria_activa": categoria,
        "categorias": Producto.CATEGORIAS,
        "piezas_pollo": PiezaPollo.objects.all(),
        "acompanamientos_cambio": cambios,
        "categorias_venta_directa": CATEGORIAS_VENTA_DIRECTA,
        "menestra_json": json.dumps({t.nombre: t.disponible for t in TipoMenestra.objects.all()}),
    }
    return render(request, "pedidos/menu_mesa.html", contexto)


@login_required
@user_passes_test(es_mesero)
@require_POST
def agregar_item(request, orden_id, producto_id):
    orden = get_object_or_404(Orden, id=orden_id, estado="abierta")
    producto = get_object_or_404(Producto, id=producto_id)

    if not producto.esta_disponible():
        return JsonResponse({"ok": False, "error": "Producto no disponible"}, status=400)

    pieza = request.POST.get("pieza", "").strip()
    pieza_obj = None
    if producto.requiere_pieza:
        pieza_obj = PiezaPollo.objects.filter(nombre=pieza).first()
        if pieza_obj is None or pieza_obj.stock <= 0:
            return JsonResponse({"ok": False, "error": "Selecciona una presa disponible"}, status=400)
    else:
        pieza = ""

    # cambio de acompañamiento: solo si el plato lo permite y el acompañamiento tiene precio_cambio
    cambio = None
    cambio_id = request.POST.get("acompanamiento", "").strip()
    if cambio_id and producto.permite_cambio():
        cambio = Producto.objects.filter(id=cambio_id, precio_cambio__isnull=False).first()
        if cambio is None or not cambio.esta_disponible():
            return JsonResponse({"ok": False, "error": "Acompañamiento no disponible"}, status=400)

    # acompañamientos incluidos que el cliente no quiere (ej: sin maduro). No cambia el precio.
    validos = set(producto.lista_opciones_incluidas())
    sin_pedidos = [s.strip() for s in request.POST.get("sin_acompanamientos", "").split(",") if s.strip()]
    sin_acompanamientos = ",".join(s for s in sin_pedidos if s in validos)

    # variantes de eleccion unica (ej: Menestra -> Lenteja/Frejol). Si el producto tiene, son obligatorias.
    grupos_producto = {v.nombre: set(v.lista_opciones()) for v in producto.variantes.all()}
    elegidas = {}
    for parte in request.POST.get("variantes", "").split("|"):
        if ":" in parte:
            grupo, opcion = parte.split(":", 1)
            elegidas[grupo.strip()] = opcion.strip()
    for nombre_grupo, opciones_validas in grupos_producto.items():
        if elegidas.get(nombre_grupo) not in opciones_validas:
            return JsonResponse({"ok": False, "error": f"Selecciona {nombre_grupo.lower()}"}, status=400)
    variantes_elegidas = "|".join(f"{g}:{elegidas[g]}" for g in grupos_producto)

    despresado = producto.permite_despresado and request.POST.get("despresado") == "1"

    item, creado = DetalleOrden.objects.get_or_create(
        orden=orden, producto=producto, notas=pieza, acompanamiento=cambio,
        sin_acompanamientos=sin_acompanamientos, variantes_elegidas=variantes_elegidas,
        despresado=despresado,
    )
    nueva_cantidad = item.cantidad + 1 if not creado else 1

    if producto.controla_stock and nueva_cantidad > producto.stock:
        return JsonResponse({"ok": False, "error": "No hay suficiente stock"}, status=400)
    if pieza_obj is not None and nueva_cantidad > pieza_obj.stock:
        return JsonResponse({"ok": False, "error": "No hay suficientes presas de esa"}, status=400)

    item.cantidad = nueva_cantidad
    item.save()

    categoria = request.POST.get("categoria", "combos")
    return redirect(_url_menu_mesa(orden.mesa_id, categoria, orden.cuenta_id))


def _url_menu_mesa(mesa_id, categoria, cuenta_id=None, extra=""):
    """URL del menu de la mesa conservando la pestaña activa y la cuenta que se esta viendo."""
    url = f"{reverse('menu_mesa', args=[mesa_id])}?categoria={categoria}"
    if cuenta_id:
        url += f"&cuenta={cuenta_id}"
    return url + extra


def _volver_al_menu(request, orden, abrir_carrito=False):
    """URL del menu de la mesa conservando la pestaña activa (y el detalle abierto si se pide).
    La venta directa no tiene cuenta propia: usa la que venia marcada en el formulario."""
    categoria = request.POST.get("categoria", "combos")
    cuenta_id = orden.cuenta_id or request.POST.get("cuenta")
    extra = ("&directo=1" if orden.es_venta_directa else "&carrito=1") if abrir_carrito else ""
    return _url_menu_mesa(orden.mesa_id, categoria, cuenta_id, extra)


@login_required
@user_passes_test(es_mesero)
@require_POST
def cambiar_cantidad(request, orden_id, item_id):
    """Botones - / + del detalle de la orden. Si la cantidad llega a 0 se borra la linea."""
    orden = get_object_or_404(Orden, id=orden_id, estado="abierta")
    item = get_object_or_404(DetalleOrden, id=item_id, orden=orden)
    delta = 1 if request.POST.get("delta") == "1" else -1
    nueva_cantidad = item.cantidad + delta

    if nueva_cantidad <= 0:
        item.delete()
    else:
        producto = item.producto
        if delta > 0 and producto.controla_stock and nueva_cantidad > (producto.stock or 0):
            return JsonResponse({"ok": False, "error": "No hay suficiente stock"}, status=400)
        item.cantidad = nueva_cantidad
        item.save()

    return redirect(_volver_al_menu(request, orden, abrir_carrito=True))


@login_required
@user_passes_test(es_mesero)
@require_POST
def eliminar_items(request, orden_id):
    """Elimina las lineas marcadas con checkbox en el detalle de la orden."""
    orden = get_object_or_404(Orden, id=orden_id, estado="abierta")
    ids = request.POST.getlist("item_ids")
    orden.items.filter(id__in=ids).delete()
    return redirect(_volver_al_menu(request, orden, abrir_carrito=True))


@login_required
@user_passes_test(es_mesero)
@require_POST
def confirmar_orden(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id, estado="abierta")

    for item in orden.items.all():
        if item.producto.controla_stock:
            item.producto.stock = max(0, item.producto.stock - item.cantidad)
            item.producto.save()
        if item.producto.requiere_pieza and item.notas:
            pieza = PiezaPollo.objects.filter(nombre=item.notas).first()
            if pieza:
                pieza.stock = max(0, pieza.stock - item.cantidad)
                pieza.save()

    orden.estado = "enviada"
    orden.enviado_a_cocina = timezone.now()
    orden.para_llevar = request.POST.get("para_llevar") == "1"
    orden.save()

    tipo = "para llevar" if orden.para_llevar else "para servir"
    cuenta_txt = f" - Cuenta {orden.cuenta.numero}" if orden.cuenta_id else ""
    registrar(request.user, f"Confirmo orden #{orden.id} ({tipo}) - Mesa {orden.mesa.numero}{cuenta_txt} - ${orden.total()}")
    return redirect("elegir_mesa")


@login_required
@user_passes_test(es_mesero)
@require_POST
def agregar_item_directo(request, mesa_id, producto_id):
    """Venta de mostrador: acompañamiento/bebida/gaseosa que se cobra al instante,
    sin pasar por la pantalla de cocina (mesa que ya esta comiendo y pide algo suelto)."""
    mesa = get_object_or_404(Mesa, id=mesa_id)
    producto = get_object_or_404(Producto, id=producto_id)

    if producto.categoria not in CATEGORIAS_VENTA_DIRECTA:
        return JsonResponse({"ok": False, "error": "Ese producto no se puede vender directo"}, status=400)
    if not producto.esta_disponible():
        return JsonResponse({"ok": False, "error": "Producto no disponible"}, status=400)

    orden, _ = Orden.objects.get_or_create(mesa=mesa, estado="abierta", es_venta_directa=True)

    item, creado = DetalleOrden.objects.get_or_create(orden=orden, producto=producto)
    nueva_cantidad = item.cantidad + 1 if not creado else 1

    if producto.controla_stock and nueva_cantidad > producto.stock:
        return JsonResponse({"ok": False, "error": "No hay suficiente stock"}, status=400)

    item.cantidad = nueva_cantidad
    item.save()

    categoria = request.POST.get("categoria", "combos")
    return redirect(_url_menu_mesa(mesa.id, categoria, request.POST.get("cuenta"), "&directo=1"))


@login_required
@user_passes_test(es_mesero)
@require_POST
def confirmar_venta_directa(request, orden_id):
    """Cobra la venta directa: se cierra al instante, nunca pasa por cocina."""
    orden = get_object_or_404(Orden, id=orden_id, estado="abierta", es_venta_directa=True)

    for item in orden.items.all():
        if item.producto.controla_stock:
            item.producto.stock = max(0, item.producto.stock - item.cantidad)
            item.producto.save()

    orden.estado = "cerrada"
    orden.enviado_a_cocina = timezone.now()
    orden.save()

    registrar(request.user, f"Venta directa #{orden.id} (sin cocina) - Mesa {orden.mesa.numero} - ${orden.total()}")
    categoria = request.POST.get("categoria", "combos")
    return redirect(_url_menu_mesa(orden.mesa_id, categoria, request.POST.get("cuenta")))


# ---------- COCINA ----------

@login_required
@user_passes_test(es_cocina)
def panel_cocina(request):
    ordenes = Orden.objects.filter(estado="enviada").order_by("enviado_a_cocina")

    # disponibilidad agrupada por categoria, en el mismo orden que las pestañas del mesero
    productos = list(Producto.objects.all().order_by("nombre"))
    grupos = []
    for valor, nombre in Producto.CATEGORIAS:
        lista = [p for p in productos if p.categoria == valor]
        if lista:
            grupos.append((nombre, lista))

    return render(request, "pedidos/panel_cocina.html", {
        "ordenes": ordenes,
        "grupos": grupos,
        "temporizadores": Producto.TEMPORIZADORES,
        "piezas_pollo": PiezaPollo.objects.all(),
        "tipos_menestra": TipoMenestra.objects.all(),
    })


def ordenes_pendientes_json(request):
    ordenes = Orden.objects.filter(estado="enviada").order_by("enviado_a_cocina")
    data = [{
        "id": o.id,
        "mesa": o.mesa.numero,
        "minutos": o.minutos_en_espera(),
        "items": [f"{i.cantidad}x {i.descripcion()}" for i in o.items.all()],
    } for o in ordenes]
    return JsonResponse({"ordenes": data})


@login_required
@user_passes_test(es_cocina)
@require_POST
def marcar_entregada(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id)
    orden.estado = "entregada"
    orden.save()
    registrar(request.user, f"Marco como listo orden #{orden.id} - Mesa {orden.mesa.numero}")
    return redirect("panel_cocina")


@login_required
@user_passes_test(es_cocina)
@require_POST
def toggle_disponibilidad(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    producto.disponible = not producto.disponible
    producto.save()
    estado_txt = "disponible" if producto.disponible else "agotado"
    registrar(request.user, f"Marco '{producto.nombre}' como {estado_txt}")
    return JsonResponse({"ok": True, "disponible": producto.disponible})


@login_required
@user_passes_test(es_cocina)
@require_POST
def poner_temporizador(request, producto_id):
    """Cocina avisa 'faltan X min' para un producto; minutos=0 quita el temporizador."""
    producto = get_object_or_404(Producto, id=producto_id)
    try:
        minutos = int(request.POST.get("minutos", 0))
    except ValueError:
        minutos = 0
    if minutos and minutos not in Producto.TEMPORIZADORES:
        return JsonResponse({"ok": False, "error": "Tiempo no valido"}, status=400)

    producto.listo_en = timezone.now() + timedelta(minutes=minutos) if minutos else None
    producto.save()
    if minutos:
        registrar(request.user, f"Temporizador '{producto.nombre}': faltan {minutos} min")
    else:
        registrar(request.user, f"Quito temporizador de '{producto.nombre}'")
    return JsonResponse({"ok": True, "segundos": producto.segundos_restantes()})


@login_required
@user_passes_test(es_cocina)
@require_POST
def toggle_menestra(request, tipo_id):
    tipo = get_object_or_404(TipoMenestra, id=tipo_id)
    tipo.disponible = not tipo.disponible
    tipo.save()
    estado_txt = "disponible" if tipo.disponible else "agotada"
    registrar(request.user, f"Marco menestra de '{tipo.nombre}' como {estado_txt}")
    return JsonResponse({"ok": True, "disponible": tipo.disponible})


@login_required
@user_passes_test(es_cocina)
@require_POST
def actualizar_stock_pieza(request, pieza_id):
    """El deslizador de presas en cocina guarda cuantas hay disponibles de cada tipo."""
    pieza = get_object_or_404(PiezaPollo, id=pieza_id)
    try:
        cantidad = max(0, int(request.POST.get("cantidad", 0)))
    except ValueError:
        return JsonResponse({"ok": False, "error": "Cantidad invalida"}, status=400)

    pieza.stock = cantidad
    pieza.save()
    registrar(request.user, f"Actualizo presas de '{pieza.nombre}': {cantidad}")
    return JsonResponse({"ok": True, "stock": pieza.stock})


def disponibilidad_json(request):
    """Lo consulta la tablet del mesero cada pocos segundos: disponibilidad + temporizadores."""
    productos = Producto.objects.all()
    data = {p.id: p.esta_disponible() for p in productos}
    temporizadores = {p.id: p.segundos_restantes() for p in productos if p.segundos_restantes()}
    piezas = {p.nombre: p.stock for p in PiezaPollo.objects.all()}
    menestra = {t.nombre: t.disponible for t in TipoMenestra.objects.all()}
    return JsonResponse({
        "disponibilidad": data, "temporizadores": temporizadores, "piezas": piezas, "menestra": menestra,
    })


# ---------- ADMIN: REPORTES ----------

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
DIAS = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]


def _fin_de_mes(d):
    siguiente = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return siguiente - timedelta(days=1)


def _rango_fechas(request):
    """Lee ?rango=dia|semana|mes y ?fecha=YYYY-MM-DD (o YYYY-MM) de la URL.

    Devuelve (rango, desde, hasta, etiqueta, ancla). `ancla` es la fecha elegida (hoy por
    defecto) y sirve para navegar al periodo anterior/siguiente. Se puede pedir cualquier
    periodo, pasado o futuro.
    """
    rango = request.GET.get("rango", "dia")
    if rango not in ("dia", "semana", "mes"):
        rango = "dia"
    hoy = timezone.localdate()

    texto = request.GET.get("fecha", "").strip()
    if len(texto) == 7:           # <input type="month"> manda YYYY-MM
        texto += "-01"
    try:
        ancla = date.fromisoformat(texto)
    except ValueError:
        ancla = hoy

    if rango == "semana":
        desde = ancla - timedelta(days=ancla.weekday())
        fin = desde + timedelta(days=6)
        etiqueta = f"Semana del {desde:%d/%m} al {fin:%d/%m/%Y}"
    elif rango == "mes":
        desde = ancla.replace(day=1)
        fin = _fin_de_mes(desde)
        etiqueta = f"{MESES[desde.month - 1]} {desde.year}"
    else:
        desde = fin = ancla
        etiqueta = f"Hoy ({ancla:%d/%m/%Y})" if ancla == hoy else f"{DIAS[ancla.weekday()]} {ancla:%d/%m/%Y}"

    # el periodo en curso se corta en hoy (no hay ventas del futuro); uno pasado o futuro va completo
    hasta = min(fin, hoy) if desde <= hoy <= fin else fin
    return rango, desde, hasta, etiqueta, ancla


def _navegacion(rango, desde, ancla):
    """Fechas ancla del periodo anterior y siguiente, para las flechas del dashboard."""
    if rango == "semana":
        return desde - timedelta(days=7), desde + timedelta(days=7)
    if rango == "mes":
        return _fin_de_mes(desde - timedelta(days=1)).replace(day=1), (_fin_de_mes(desde) + timedelta(days=1))
    return ancla - timedelta(days=1), ancla + timedelta(days=1)


def _ordenes_periodo(desde, hasta):
    return Orden.objects.filter(
        creado__date__gte=desde,
        creado__date__lte=hasta,
        estado__in=["entregada", "cerrada"],
    ).select_related("mesa").prefetch_related("items__producto", "items__acompanamiento")


def _resumen(ordenes):
    """Totales de un conjunto de ordenes (el subtotal incluye el cambio de acompañamiento)."""
    n_ordenes = 0
    ingresos = 0
    items = 0
    for o in ordenes:
        n_ordenes += 1
        for it in o.items.all():
            ingresos += it.subtotal()
            items += it.cantidad
    ticket = (ingresos / n_ordenes) if n_ordenes else 0
    return {"ordenes": n_ordenes, "ingresos": float(ingresos), "ticket": float(ticket), "items": items}


def _delta(actual, anterior):
    """Variacion % vs el periodo anterior (None si no hay base para comparar)."""
    if not anterior:
        return None
    return round((actual - anterior) / anterior * 100)


def _resumen_financiero(desde, hasta, ingresos):
    """Ingresos vs gastos de materia prima cargados a mano, para un periodo dado."""
    gastos = list(Gasto.objects.filter(fecha__gte=desde, fecha__lte=hasta))
    total_gastos = float(sum(g.monto for g in gastos))
    ganancia = ingresos - total_gastos
    margen = round(ganancia / ingresos * 100) if ingresos else None
    return {
        "gastos": gastos,
        "total_gastos": total_gastos,
        "ganancia": ganancia,
        "margen": margen,
    }


@login_required
@user_passes_test(es_admin)
def reportes(request):
    rango, desde, hasta, etiqueta, ancla = _rango_fechas(request)
    hoy = timezone.localdate()
    ordenes = list(_ordenes_periodo(desde, hasta))
    actual = _resumen(ordenes)

    # periodo anterior del mismo largo, para los deltas de los indicadores
    dias = (hasta - desde).days + 1
    anterior = _resumen(_ordenes_periodo(desde - timedelta(days=dias), desde - timedelta(days=1)))

    # ---- serie de ventas: por hora (dia) o por dia (semana / mes) ----
    if rango == "dia":
        horas = [timezone.localtime(o.creado).hour for o in ordenes]
        h_ini, h_fin = min([10] + horas), max([21] + horas)
        cubetas = {h: {"etiqueta": f"{h:02d}h", "titulo": f"{h:02d}:00 a {h:02d}:59", "valor": 0.0, "ordenes": 0, "destacar": False}
                   for h in range(h_ini, h_fin + 1)}
        for o in ordenes:
            c = cubetas[timezone.localtime(o.creado).hour]
            c["valor"] += float(o.total()); c["ordenes"] += 1
        serie = list(cubetas.values())
        titulo_serie = "Ventas por hora"
    else:
        cubetas = {}
        d = desde
        while d <= (desde + timedelta(days=6) if rango == "semana" else hasta):
            etiq = f"{DIAS[d.weekday()]} {d.day}" if rango == "semana" else str(d.day)
            titulo = f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1].lower()[:3]}" + (" (hoy)" if d == hoy else "")
            cubetas[d] = {"etiqueta": etiq, "titulo": titulo, "valor": 0.0, "ordenes": 0, "destacar": d == hoy}
            d += timedelta(days=1)
        for o in ordenes:
            c = cubetas.get(timezone.localtime(o.creado).date())
            if c:
                c["valor"] += float(o.total()); c["ordenes"] += 1
        serie = list(cubetas.values())
        titulo_serie = "Ventas por dia"

    # ---- que se vendio: unidades por producto, agrupado por categoria ----
    # los acompañamientos usados como cambio de plato se cuentan aparte (cocina los prepara igual)
    por_producto = {}
    for o in ordenes:
        for it in o.items.all():
            p = it.producto
            pp = por_producto.setdefault(p.id, {"nombre": p.nombre, "categoria": p.categoria, "cantidad": 0, "ingresos": 0.0})
            pp["cantidad"] += it.cantidad
            pp["ingresos"] += float(it.subtotal())
            if it.acompanamiento:
                a = it.acompanamiento
                pa = por_producto.setdefault(f"cambio-{a.id}", {"nombre": f"{a.nombre} (cambio en plato)", "categoria": a.categoria, "cantidad": 0, "ingresos": 0.0})
                pa["cantidad"] += it.cantidad
                pa["ingresos"] += float(a.precio_cambio or 0) * it.cantidad
    top_productos = sorted(por_producto.values(), key=lambda x: -x["cantidad"])[:8]

    desglose = []
    for valor, nombre in Producto.CATEGORIAS:
        filas = sorted([x for x in por_producto.values() if x["categoria"] == valor], key=lambda x: -x["cantidad"])
        if filas:
            desglose.append({
                "nombre": nombre,
                "filas": filas,
                "cantidad": sum(f["cantidad"] for f in filas),
                "ingresos": sum(f["ingresos"] for f in filas),
            })

    # ---- inventario de bebidas y gaseosas (el admin lo edita desde el dashboard) ----
    vendidas = {k: v["cantidad"] for k, v in por_producto.items() if isinstance(k, int)}
    inventario = []
    for p in Producto.objects.filter(categoria__in=["bebidas", "gaseosas"]).order_by("categoria", "nombre"):
        inventario.append({"p": p, "vendidas": vendidas.get(p.id, 0)})

    # ---- todas las ordenes del periodo ----
    todas = sorted(ordenes, key=lambda o: o.creado, reverse=True)

    # ---- gastos de materia prima vs ingresos, del periodo que se esta viendo ----
    financiero = _resumen_financiero(desde, hasta, actual["ingresos"])

    # ---- ganancia del mes en curso: fija, no cambia con el selector dia/semana/mes,
    # para que el dueño siempre pueda ver de ahi cuanto hay para repartir de sueldos ----
    mes_desde = hoy.replace(day=1)
    mes_ingresos = _resumen(_ordenes_periodo(mes_desde, hoy))["ingresos"]
    mes_actual = _resumen_financiero(mes_desde, hoy, mes_ingresos)
    mes_actual["ingresos"] = mes_ingresos
    mes_actual["etiqueta"] = f"{MESES[hoy.month - 1]} {hoy.year}"

    anterior_ancla, siguiente_ancla = _navegacion(rango, desde, ancla)
    contexto = {
        "rango": rango,
        "etiqueta": etiqueta,
        "ancla": ancla,
        "es_hoy": ancla == hoy,
        "nav_anterior": anterior_ancla,
        "nav_siguiente": siguiente_ancla,
        "kpi": actual,
        "deltas": {
            "ordenes": _delta(actual["ordenes"], anterior["ordenes"]),
            "ingresos": _delta(actual["ingresos"], anterior["ingresos"]),
            "ticket": _delta(actual["ticket"], anterior["ticket"]),
            "items": _delta(actual["items"], anterior["items"]),
        },
        "titulo_serie": titulo_serie,
        "datos": {"serie": serie, "top": top_productos},
        "desglose": desglose,
        "inventario": inventario,
        "todas": todas,
        "financiero": financiero,
        "mes_actual": mes_actual,
        "categorias_gasto": Gasto.CATEGORIAS,
    }
    return render(request, "pedidos/reportes.html", contexto)


@login_required
@user_passes_test(es_admin)
@require_POST
def agregar_gasto(request):
    fecha = request.POST.get("fecha", "").strip()
    categoria = request.POST.get("categoria", "otros")
    descripcion = request.POST.get("descripcion", "").strip()
    monto = request.POST.get("monto", "").strip()

    try:
        fecha = date.fromisoformat(fecha)
    except ValueError:
        fecha = timezone.localdate()
    try:
        monto = round(float(monto), 2)
    except ValueError:
        monto = 0

    if descripcion and monto > 0:
        Gasto.objects.create(
            fecha=fecha, categoria=categoria, descripcion=descripcion, monto=monto, usuario=request.user,
        )
        registrar(request.user, f"Cargo gasto '{descripcion}' (${monto:.2f}) del {fecha:%d/%m/%Y}")

    volver = reverse("reportes") + "?" + request.POST.get("volver", "rango=dia")
    return redirect(volver)


@login_required
@user_passes_test(es_admin)
@require_POST
def eliminar_gasto(request, gasto_id):
    gasto = get_object_or_404(Gasto, id=gasto_id)
    registrar(request.user, f"Elimino gasto '{gasto.descripcion}' (${gasto.monto:.2f}) del {gasto.fecha:%d/%m/%Y}")
    gasto.delete()

    volver = reverse("reportes") + "?" + request.POST.get("volver", "rango=dia")
    return redirect(volver)


@login_required
@user_passes_test(es_admin)
@require_POST
def actualizar_stock(request):
    """Guarda el inventario de bebidas/gaseosas editado en el dashboard."""
    cambios = []
    for p in Producto.objects.filter(categoria__in=["bebidas", "gaseosas"]):
        controla = request.POST.get(f"controla_{p.id}") == "1"
        try:
            stock = max(0, int(request.POST.get(f"stock_{p.id}", "") or 0))
        except ValueError:
            stock = p.stock or 0
        if controla != p.controla_stock or (controla and stock != (p.stock or 0)):
            p.controla_stock = controla
            p.stock = stock if controla else None
            p.save()
            cambios.append(f"{p.nombre}: {stock if controla else 'sin control'}")
    if cambios:
        registrar(request.user, "Actualizo inventario - " + ", ".join(cambios))

    volver = reverse("reportes") + "?" + request.POST.get("volver", "rango=dia") + "&guardado=1"
    return redirect(volver)


@login_required
@user_passes_test(es_admin)
def exportar_excel(request):
    rango, desde, hasta, etiqueta, _ = _rango_fechas(request)

    ordenes = Orden.objects.filter(
        creado__date__gte=desde,
        creado__date__lte=hasta,
        estado__in=["entregada", "cerrada"],
    ).order_by("creado")

    azul = "1F4E78"
    gris_claro = "F2F2F2"
    borde_fino = Side(style="thin", color="BFBFBF")
    borde = Border(left=borde_fino, right=borde_fino, top=borde_fino, bottom=borde_fino)
    fuente_encabezado = Font(color="FFFFFF", bold=True, size=11)
    relleno_encabezado = PatternFill("solid", fgColor=azul)

    def estilizar_encabezado(ws, columnas):
        ws.append(columnas)
        for celda in ws[1]:
            celda.font = fuente_encabezado
            celda.fill = relleno_encabezado
            celda.alignment = Alignment(horizontal="center", vertical="center")
            celda.border = borde
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(columnas))}1"

    def ajustar_anchos(ws, anchos):
        for i, ancho in enumerate(anchos, start=1):
            ws.column_dimensions[get_column_letter(i)].width = ancho

    def bordear_filas(ws, num_columnas):
        for fila in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=num_columnas):
            for celda in fila:
                celda.border = borde
            if fila[0].row % 2 == 0:
                for celda in fila:
                    celda.fill = PatternFill("solid", fgColor=gris_claro)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas"
    estilizar_encabezado(ws, ["Orden", "Fecha", "Producto", "Cantidad", "Subtotal"])

    for orden in ordenes:
        for item in orden.items.all():
            ws.append([
                orden.id,
                orden.creado.strftime("%d/%m/%Y %H:%M"),
                item.descripcion(),
                item.cantidad,
                float(item.subtotal()),
            ])

    for fila in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=4, max_col=4):
        for celda in fila:
            celda.alignment = Alignment(horizontal="center")
    for fila in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=5, max_col=5):
        for celda in fila:
            celda.number_format = '"$"#,##0.00'
    bordear_filas(ws, 5)
    ajustar_anchos(ws, [10, 18, 40, 12, 14])

    ws2 = wb.create_sheet("Resumen por producto")
    estilizar_encabezado(ws2, ["Producto", "Cantidad vendida", "Total"])
    # se suma el subtotal real de cada linea (incluye el +$ del cambio de acompañamiento)
    resumen = {}
    for item in DetalleOrden.objects.filter(orden__in=ordenes).select_related("producto", "acompanamiento"):
        nombre = item.producto.nombre
        cant, total = resumen.get(nombre, (0, 0.0))
        resumen[nombre] = (cant + item.cantidad, total + float(item.subtotal()))
    for nombre, (cant, total) in sorted(resumen.items()):
        ws2.append([nombre, cant, round(total, 2)])

    for fila in ws2.iter_rows(min_row=2, max_row=ws2.max_row, min_col=2, max_col=2):
        for celda in fila:
            celda.alignment = Alignment(horizontal="center")
    for fila in ws2.iter_rows(min_row=2, max_row=ws2.max_row, min_col=3, max_col=3):
        for celda in fila:
            celda.number_format = '"$"#,##0.00'
    bordear_filas(ws2, 3)
    ajustar_anchos(ws2, [40, 18, 16])

    # ---- gastos de materia prima vs ingresos, del mismo periodo exportado ----
    resumen_periodo = _resumen(ordenes)
    financiero = _resumen_financiero(desde, hasta, resumen_periodo["ingresos"])

    ws3 = wb.create_sheet("Gastos y ganancia")
    estilizar_encabezado(ws3, ["Fecha", "Categoria", "Descripcion", "Monto"])
    for g in financiero["gastos"]:
        ws3.append([g.fecha.strftime("%d/%m/%Y"), g.get_categoria_display(), g.descripcion, float(g.monto)])
    for fila in ws3.iter_rows(min_row=2, max_row=ws3.max_row, min_col=4, max_col=4):
        for celda in fila:
            celda.number_format = '"$"#,##0.00'
    bordear_filas(ws3, 4)
    ajustar_anchos(ws3, [14, 18, 40, 14])

    fila = ws3.max_row + 2
    etiquetas_resumen = [
        ("Ingresos del periodo", resumen_periodo["ingresos"]),
        ("Gastos del periodo", financiero["total_gastos"]),
        ("Ganancia (o perdida)" if financiero["ganancia"] >= 0 else "Perdida", financiero["ganancia"]),
    ]
    for i, (etiqueta_fila, valor) in enumerate(etiquetas_resumen):
        ws3.cell(row=fila + i, column=1, value=etiqueta_fila).font = Font(bold=True)
        celda_valor = ws3.cell(row=fila + i, column=2, value=valor)
        celda_valor.number_format = '"$"#,##0.00'
    if financiero["margen"] is not None:
        ws3.cell(row=fila + 3, column=1, value="Margen").font = Font(bold=True)
        ws3.cell(row=fila + 3, column=2, value=f"{financiero['margen']}%")

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    nombre_archivo = f"ventas_{rango}_{desde:%Y%m%d}_{hasta:%Y%m%d}.xlsx"
    response["Content-Disposition"] = f"attachment; filename={nombre_archivo}"
    wb.save(response)
    return response
