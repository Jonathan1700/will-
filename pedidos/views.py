from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Max, Count
from datetime import timedelta, date
from decimal import Decimal, InvalidOperation
import calendar
import json
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from .models import (
    Mesa, Producto, Orden, DetalleOrden, RegistroAccion, PiezaPollo, TipoMenestra, VarianteProducto,
    Gasto, GastoRecurrente, Cuenta, EstadoCuentaOrden,
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

    # pedidos (cuentas) que cocina ya dejo listos, mas las ventas directas ya confirmadas,
    # que el mesero todavia no llevo a la mesa. Se agrupan por mesa+cuenta: si la misma
    # cuenta tiene un pedido de cocina Y una venta directa (ej: ya estaban comiendo y
    # pidieron una gaseosa suelta), aparecen juntas en una sola tarjeta con un solo total,
    # para que el mesero cobre todo de una vez en vez de sumar dos tarjetas separadas.
    estados = (
        EstadoCuentaOrden.objects.filter(listo=True, entregado=False)
        .select_related("orden", "orden__mesa")
        .prefetch_related("orden__items__producto", "orden__items__acompanamiento")
        .order_by("orden__enviado_a_cocina", "cuenta")
    )

    grupos = {}
    for ec in estados:
        items = [i for i in ec.orden.items.all() if i.cuenta == ec.cuenta]
        clave = (ec.orden.mesa_id, ec.cuenta)
        grupo = grupos.setdefault(clave, {
            "mesa": ec.orden.mesa, "cuenta": ec.cuenta, "items": [], "total": 0,
            "tiene_cocina": False, "tiene_directo": False, "recargo_llevar": 0,
        })
        grupo["items"].extend(items)
        grupo["total"] += sum(i.subtotal() for i in items)
        if ec.orden.es_venta_directa:
            grupo["tiene_directo"] = True
        else:
            grupo["tiene_cocina"] = True
        if ec.orden.para_llevar:
            unidades = sum(
                i.cantidad for i in items if i.producto.categoria in Orden.CATEGORIAS_CON_ENVASE
            )
            grupo["recargo_llevar"] += Orden.RECARGO_PARA_LLEVAR * unidades
    pendientes = list(grupos.values())
    # total ya con el recargo por llevar sumado, para la tarjeta del mesero
    for grupo in pendientes:
        grupo["total_llevar"] = grupo["total"] + grupo["recargo_llevar"]
    # ids en el mismo formato que ordenes_listas_json, para que el polling de la tablet
    # detecte cambios aunque la tarjeta agrupada no cambie de cantidad (ej: se agrego una
    # venta directa a una cuenta que ya tenia un pedido de cocina listo).
    ids_listas = ",".join(f"{ec.orden_id}-{ec.cuenta}" for ec in estados)

    return render(request, "pedidos/elegir_mesa.html", {
        "mesas": mesas,
        "ordenes_listas": pendientes,
        "ids_listas": ids_listas,
    })


@login_required
@user_passes_test(es_mesero)
def cuentas_mesa(request, mesa_id):
    """Cuentas en las que esta dividida una mesa (ej: 3 personas piden junto y pagan
    separado). Cocina los ve como 'pedidos' separados de la misma mesa."""
    mesa = get_object_or_404(Mesa, id=mesa_id)
    cuentas = []
    for cuenta in mesa.cuentas.filter(cerrada=False):
        items = list(cuenta.items())
        cuentas.append({
            "cuenta": cuenta,
            "items": items,
            "total": sum(i.subtotal() for i in items),
        })

    orden = Orden.objects.filter(mesa=mesa, estado="abierta", es_venta_directa=False).first()

    return render(request, "pedidos/cuentas_mesa.html", {
        "mesa": mesa,
        "cuentas": cuentas,
        "orden": orden,
    })


@login_required
@user_passes_test(es_mesero)
@require_POST
def crear_cuenta(request, mesa_id):
    mesa = get_object_or_404(Mesa, id=mesa_id)
    siguiente = (mesa.cuentas.aggregate(m=Max("numero"))["m"] or 0) + 1
    Cuenta.objects.create(mesa=mesa, numero=siguiente)
    registrar(request.user, f"Abrio cuenta {siguiente} - Mesa {mesa.numero}")
    return redirect("cuentas_mesa", mesa_id=mesa.id)


@login_required
@user_passes_test(es_mesero)
@require_POST
def cobrar_cuenta(request, cuenta_id):
    cuenta = get_object_or_404(Cuenta, id=cuenta_id, cerrada=False)
    cuenta.cerrada = True
    cuenta.save()
    registrar(request.user, f"Cobro cuenta {cuenta.numero} - Mesa {cuenta.mesa.numero}")
    return redirect("cuentas_mesa", mesa_id=cuenta.mesa_id)


@login_required
@user_passes_test(es_mesero)
@require_POST
def eliminar_cuenta(request, cuenta_id):
    """Borra una cuenta creada de mas, ej. por error. Solo si esta vacia (si ya tiene
    productos, hay que cobrarla o sacar los items desde el menu antes de borrarla)."""
    cuenta = get_object_or_404(Cuenta, id=cuenta_id, cerrada=False)
    mesa_id = cuenta.mesa_id
    if not cuenta.items().exists():
        registrar(request.user, f"Elimino cuenta {cuenta.numero} - Mesa {cuenta.mesa.numero}")
        cuenta.delete()
    return redirect("cuentas_mesa", mesa_id=mesa_id)


def ordenes_listas_json(request):
    """Pedidos (cuenta por cuenta) que cocina ya marco como listos, mas ventas directas
    ya confirmadas, para avisar a la tablet."""
    estados = (
        EstadoCuentaOrden.objects.filter(listo=True, entregado=False)
        .select_related("orden__mesa")
    )
    data = [{
        "id": f"{ec.orden_id}-{ec.cuenta}",
        "orden": ec.orden_id,
        "cuenta": ec.cuenta,
        "mesa": ec.orden.mesa.numero,
    } for ec in estados]
    return JsonResponse({"listas": data})


@login_required
@user_passes_test(es_mesero)
@require_POST
def entregar_grupo(request, mesa_id, cuenta):
    """El mesero confirma que ya llevo a la mesa todo lo listo de una cuenta: el pedido
    de cocina Y la venta directa, si hay de las dos, se entregan y cobran juntas.
    Cada orden involucrada se cierra cuando ya se entregaron todos sus pedidos."""
    estados = list(
        EstadoCuentaOrden.objects.filter(
            orden__mesa_id=mesa_id, cuenta=cuenta, listo=True, entregado=False,
        ).select_related("orden", "orden__mesa")
    )
    mesa = get_object_or_404(Mesa, id=mesa_id)

    for estado in estados:
        estado.entregado = True
        estado.save()
        orden = estado.orden
        if not EstadoCuentaOrden.objects.filter(orden=orden, entregado=False).exists():
            orden.estado = "cerrada"
            orden.save()

    registrar(request.user, f"Entrego pedido {cuenta} - Mesa {mesa.numero}")
    return redirect("elegir_mesa")


@login_required
@user_passes_test(es_mesero)
def detalle_pedido(request, mesa_id, cuenta):
    """Detalle (items, notas, total) de un pedido ya listo que el mesero todavia
    no lleva a la mesa: a donde va al tocar su tarjeta en 'Listos para llevar a la mesa'."""
    mesa = get_object_or_404(Mesa, id=mesa_id)
    estados = list(
        EstadoCuentaOrden.objects.filter(
            orden__mesa_id=mesa_id, cuenta=cuenta, listo=True, entregado=False,
        ).select_related("orden").prefetch_related("orden__items__producto", "orden__items__acompanamiento")
    )
    if not estados:
        return redirect("elegir_mesa")

    items, total, recargo_llevar = [], 0, 0
    tiene_cocina, tiene_directo = False, False
    for estado in estados:
        orden = estado.orden
        propios = [i for i in orden.items.all() if i.cuenta == cuenta]
        items.extend(propios)
        total += sum(i.subtotal() for i in propios)
        if orden.es_venta_directa:
            tiene_directo = True
        else:
            tiene_cocina = True
        if orden.para_llevar:
            unidades = sum(
                i.cantidad for i in propios if i.producto.categoria in Orden.CATEGORIAS_CON_ENVASE
            )
            recargo_llevar += Orden.RECARGO_PARA_LLEVAR * unidades

    return render(request, "pedidos/detalle_pedido.html", {
        "mesa": mesa,
        "cuenta": cuenta,
        "items": items,
        "total": total,
        "recargo_llevar": recargo_llevar,
        "total_llevar": total + recargo_llevar,
        "tiene_cocina": tiene_cocina,
        "tiene_directo": tiene_directo,
    })


@login_required
@user_passes_test(es_mesero)
def menu_mesa(request, mesa_id):
    mesa = get_object_or_404(Mesa, id=mesa_id)
    orden, _ = Orden.objects.get_or_create(mesa=mesa, estado="abierta", es_venta_directa=False)
    orden_directa = Orden.objects.filter(mesa=mesa, estado="abierta", es_venta_directa=True).first()

    # cuenta que el mesero esta viendo/editando (division de la mesa). Cocina ve cada
    # cuenta como un 'pedido' aparte y los prepara/entrega por separado.
    try:
        cuenta_activa = int(request.GET.get("cuenta", 1))
    except ValueError:
        cuenta_activa = 1
    items_cuenta = list(orden.items.filter(cuenta=cuenta_activa).select_related("producto", "acompanamiento"))
    total_cuenta = sum(item.subtotal() for item in items_cuenta)

    categoria = request.GET.get("categoria", "combos")
    if categoria == "gaseosas":
        # gaseosas se agrupan por tamano (personal, litro, 1.35L, 2L) para que el
        # mesero las encuentre rapido; el orden de TAMANOS manda, no el alfabetico.
        orden_tamano = {valor: i for i, (valor, _) in enumerate(Producto.TAMANOS)}
        productos = sorted(
            Producto.objects.filter(categoria=categoria),
            key=lambda p: (orden_tamano.get(p.tamano, 0), p.nombre),
        )
    else:
        productos = Producto.objects.filter(categoria=categoria).order_by("nombre")

    # acompañamientos que pueden reemplazar las papas de un plato ("Mejora tu combo")
    cambios = [
        p for p in Producto.objects.filter(precio_cambio__isnull=False).order_by("nombre")
        if p.esta_disponible()
    ]

    contexto = {
        "mesa": mesa,
        "orden": orden,
        "orden_directa": orden_directa,
        "cuenta_activa": cuenta_activa,
        "items_cuenta": items_cuenta,
        "total_cuenta": total_cuenta,
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

    # despresado: solo aplica a pollo 1/4, 1/2 o entero (no a los 1/8 de combos, que ya son una presa)
    despresado = producto.categoria == "pollo" and request.POST.get("despresado") == "1"

    cuenta = _leer_cuenta(request)

    item, creado = DetalleOrden.objects.get_or_create(
        orden=orden, producto=producto, notas=pieza, acompanamiento=cambio,
        sin_acompanamientos=sin_acompanamientos, variantes_elegidas=variantes_elegidas,
        despresado=despresado, cuenta=cuenta,
    )
    nueva_cantidad = item.cantidad + 1 if not creado else 1

    if producto.controla_stock and nueva_cantidad > producto.stock:
        return JsonResponse({"ok": False, "error": "No hay suficiente stock"}, status=400)
    if pieza_obj is not None and nueva_cantidad > pieza_obj.stock:
        return JsonResponse({"ok": False, "error": "No hay suficientes presas de esa"}, status=400)

    item.cantidad = nueva_cantidad
    item.save()

    categoria = request.POST.get("categoria", "combos")
    return redirect(f"{reverse('menu_mesa', args=[orden.mesa.id])}?categoria={categoria}&cuenta={cuenta}")


def _leer_cuenta(request):
    """Cuenta activa (division de la mesa) que llega en el form. 1 si no se manda."""
    try:
        return int(request.POST.get("cuenta", 1))
    except ValueError:
        return 1


def _volver_al_menu(request, orden, abrir_carrito=False):
    """URL del menu de la mesa conservando la pestaña activa (y el detalle abierto si se pide)."""
    categoria = request.POST.get("categoria", "combos")
    url = f"{reverse('menu_mesa', args=[orden.mesa.id])}?categoria={categoria}&cuenta={_leer_cuenta(request)}"
    if abrir_carrito:
        url += "&directo=1" if orden.es_venta_directa else "&carrito=1"
    return url


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
    # cada cuenta (division de la mesa) se prepara y se entrega por separado: cocina
    # ve "Pedido 1", "Pedido 2"... igual que el mesero los separo al cargar los items.
    for numero in sorted({item.cuenta for item in orden.items.all()}):
        EstadoCuentaOrden.objects.get_or_create(orden=orden, cuenta=numero)
    orden.save()

    tipo = "para llevar" if orden.para_llevar else "para servir"
    registrar(request.user, f"Confirmo orden #{orden.id} ({tipo}) - Mesa {orden.mesa.numero} - ${orden.total()}")
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
    return redirect(f"{reverse('menu_mesa', args=[mesa.id])}?categoria={categoria}&directo=1")


@login_required
@user_passes_test(es_mesero)
@require_POST
def confirmar_venta_directa(request, orden_id):
    """Confirma la venta directa (descuenta stock ya) pero no la cobra todavia: nunca
    pasa por cocina, pero queda 'lista para entregar' junto con los pedidos de cocina
    en la pantalla del mesero. Se cobra (orden.estado -> cerrada) recien cuando el
    mesero marca que ya la entrego, para no contar como venta algo que no salio."""
    orden = get_object_or_404(Orden, id=orden_id, estado="abierta", es_venta_directa=True)

    for item in orden.items.all():
        if item.producto.controla_stock:
            item.producto.stock = max(0, item.producto.stock - item.cantidad)
            item.producto.save()

    orden.estado = "lista"
    orden.enviado_a_cocina = timezone.now()
    orden.save()
    EstadoCuentaOrden.objects.get_or_create(orden=orden, cuenta=1, defaults={"listo": True})

    registrar(request.user, f"Confirmo venta directa #{orden.id} (pendiente de entregar) - Mesa {orden.mesa.numero} - ${orden.total()}")
    categoria = request.POST.get("categoria", "combos")
    return redirect(f"{reverse('menu_mesa', args=[orden.mesa.id])}?categoria={categoria}")


# ---------- COCINA ----------

@login_required
@user_passes_test(es_cocina)
def panel_cocina(request):
    ordenes = list(
        Orden.objects.filter(estado="enviada")
        .order_by("enviado_a_cocina")
        .prefetch_related("items__producto", "items__acompanamiento", "cuentas_estado")
    )

    # cada orden llega dividida en 'pedidos' (las cuentas de la mesa): cocina arma cada
    # uno por separado y los marca como listos uno a uno, igual que el mesero los separo.
    for orden in ordenes:
        estados = {e.cuenta: e for e in orden.cuentas_estado.all()}
        pedidos = []
        for numero in sorted({item.cuenta for item in orden.items.all()}):
            items_cuenta = [item for item in orden.items.all() if item.cuenta == numero]
            estado = estados.get(numero)
            pedidos.append({
                "numero": numero,
                "listo": bool(estado and estado.listo),
                "items": items_cuenta,
                "total": sum(item.subtotal() for item in items_cuenta),
            })
        orden.pedidos_cocina = pedidos

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
def marcar_pedido_listo(request, orden_id, cuenta):
    """Cocina marca que un pedido (cuenta) ya salio. Cuando estan todos listos,
    la orden completa pasa a 'entregada' y avisa a la tablet del mesero."""
    orden = get_object_or_404(Orden, id=orden_id)
    estado, _ = EstadoCuentaOrden.objects.get_or_create(orden=orden, cuenta=cuenta)
    estado.listo = True
    estado.save()

    if not EstadoCuentaOrden.objects.filter(orden=orden, listo=False).exists():
        orden.estado = "entregada"
        orden.save()

    registrar(request.user, f"Marco listo pedido {cuenta} - Mesa {orden.mesa.numero}")
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


def _resumen_financiero_variable(financiero, ingresos):
    """Solo los gastos variables (insumos de cocina cargados a mano en esta pestaña),
    sin los fijos recurrentes: esos tienen su propia pestaña 'Gastos fijos' y no deben
    listarse ni sumarse de nuevo aqui. Reutiliza los gastos ya traidos por
    _resumen_financiero para no repetir la consulta a la base."""
    gastos = [g for g in financiero["gastos"] if g.recurrente_id is None]
    total_gastos = float(sum(g.monto for g in gastos))
    ganancia = ingresos - total_gastos
    margen = round(ganancia / ingresos * 100) if ingresos else None
    return {"gastos": gastos, "total_gastos": total_gastos, "ganancia": ganancia, "margen": margen}


def _generar_gastos_recurrentes(usuario):
    """Gastos fijos mensuales (alquiler, sueldos, luz...): en vez de que el dueno los
    vuelva a escribir cada mes, se cargan una sola vez en /admin/ como GastoRecurrente
    y esta funcion los convierte en un Gasto normal del mes en curso la primera vez que
    alguien entra al dashboard despues de la fecha (dia_mes) que le corresponde."""
    hoy = timezone.localdate()
    for plantilla in GastoRecurrente.objects.filter(activo=True):
        ya_generado = Gasto.objects.filter(
            recurrente=plantilla, fecha__year=hoy.year, fecha__month=hoy.month,
        ).exists()
        if ya_generado:
            continue
        ultimo_dia_mes = calendar.monthrange(hoy.year, hoy.month)[1]
        dia = min(plantilla.dia_mes, ultimo_dia_mes)
        if dia > hoy.day:
            continue  # todavia no le toca este mes
        Gasto.objects.create(
            fecha=hoy.replace(day=dia),
            categoria=plantilla.categoria,
            descripcion=plantilla.nombre,
            monto=plantilla.monto,
            usuario=usuario,
            recurrente=plantilla,
        )
        registrar(usuario, f"Genero automaticamente el gasto fijo '{plantilla.nombre}' (${plantilla.monto:.2f})")


def _plantillas_gasto(limite=6):
    """Las descripciones de gasto que mas se repiten en el historial (ej: 'Compra de
    pollo'), con la categoria y el monto usados la ultima vez, para llenar el
    formulario en 1 clic en vez de escribir todo de nuevo."""
    mas_repetidas = (
        Gasto.objects.exclude(recurrente__isnull=False)
        .values("descripcion")
        .annotate(n=Count("id"))
        .filter(n__gte=2)
        .order_by("-n")[:limite]
    )
    plantillas = []
    for fila in mas_repetidas:
        ultimo = (
            Gasto.objects.filter(descripcion=fila["descripcion"]).order_by("-fecha", "-creado").first()
        )
        if ultimo:
            plantillas.append({
                "descripcion": ultimo.descripcion, "categoria": ultimo.categoria, "monto": ultimo.monto,
            })
    return plantillas


# a que grupo de ingresos (categorias de Producto) corresponde cada categoria de Gasto:
# los insumos de cocina (pollo, papa, vegetales, aceite, condimentos) se cocinan todos
# juntos para pollo/combos/acompanamientos, asi que no se pueden separar mas fino que eso;
# "otros" (alquiler, sueldos, etc.) no se puede atribuir a un grupo de venta especifico.
_GRUPO_DE_CATEGORIA_GASTO = {
    "pollo": "comida", "papa": "comida", "vegetales": "comida",
    "aceite": "comida", "condimentos": "comida",
    "bebidas": "bebidas",
    "otros": None,
}
_CATEGORIAS_PRODUCTO_POR_GRUPO = {
    "comida": ("combos", "pollo", "acompanamientos"),
    "bebidas": ("bebidas", "gaseosas"),
}


def _margen_por_grupo(gastos, por_producto):
    """Ingresos vs gastos separados en 'Comida' y 'Bebidas', para saber cual de los dos
    deja mas margen en vez de un solo numero global. El costo de las bebidas/gaseosas
    vendidas se calcula solo (cantidad vendida x precio de compra cargado en el
    inventario), sin que el dueno tenga que cargarlo a mano como Gasto. Los gastos que
    no se pueden atribuir a ninguno de los dos (alquiler, sueldos...) se muestran aparte."""
    precios_compra = dict(
        Producto.objects.filter(categoria__in=("bebidas", "gaseosas"), precio_compra__isnull=False)
        .values_list("id", "precio_compra")
    )
    costo_bebidas_vendidas = sum(
        v["cantidad"] * float(precios_compra[k])
        for k, v in por_producto.items() if isinstance(k, int) and k in precios_compra
    )

    grupos = []
    for grupo, nombre in [("comida", "Comida (pollo, combos, acompañamientos)"), ("bebidas", "Bebidas y gaseosas")]:
        categorias = _CATEGORIAS_PRODUCTO_POR_GRUPO[grupo]
        ingresos = sum(v["ingresos"] for v in por_producto.values() if v["categoria"] in categorias)
        gasto_grupo = sum(float(g.monto) for g in gastos if _GRUPO_DE_CATEGORIA_GASTO.get(g.categoria) == grupo)
        if grupo == "bebidas":
            gasto_grupo += costo_bebidas_vendidas
        ganancia = ingresos - gasto_grupo
        margen = round(ganancia / ingresos * 100) if ingresos else None
        grupos.append({
            "nombre": nombre, "ingresos": ingresos, "gastos": gasto_grupo, "ganancia": ganancia, "margen": margen,
        })

    gastos_generales = sum(float(g.monto) for g in gastos if _GRUPO_DE_CATEGORIA_GASTO.get(g.categoria) is None)
    return grupos, gastos_generales


@login_required
@user_passes_test(es_admin)
def reportes(request):
    _generar_gastos_recurrentes(request.user)

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
    financiero_variable = _resumen_financiero_variable(financiero, actual["ingresos"])
    margen_grupos, gastos_generales = _margen_por_grupo(financiero["gastos"], por_producto)
    plantillas_gasto = _plantillas_gasto()

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
        "datos": {"serie": serie, "top": top_productos, "margenes": margen_grupos},
        "desglose": desglose,
        "inventario": inventario,
        "todas": todas,
        "financiero": financiero,
        "financiero_variable": financiero_variable,
        "mes_actual": mes_actual,
        "categorias_gasto": Gasto.CATEGORIAS,
        "margen_grupos": margen_grupos,
        "gastos_generales": gastos_generales,
        "plantillas_gasto": plantillas_gasto,
        "gastos_recurrentes": GastoRecurrente.objects.all(),
        "tipos_gasto_fijo": GastoRecurrente.TIPOS,
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
def agregar_gasto_recurrente(request):
    """Crea (o actualiza) una plantilla de gasto fijo mensual desde el dashboard: el
    propio sistema genera el Gasto de cada mes a partir de ella.

    Los tipos predefinidos (luz, agua, internet, alquiler, sueldos) son unicos: si ya
    existe uno y el dueno vuelve a cargarlo (ej. cambio el monto de la luz), se
    actualiza el mismo en vez de crear un duplicado que generaria el doble cada mes.
    "Otros" es libre: cada envio crea uno nuevo con el nombre que haya escrito."""
    tipo = request.POST.get("tipo", "otros")
    if tipo not in dict(GastoRecurrente.TIPOS):
        tipo = "otros"
    nombre = (
        request.POST.get("nombre_otro", "").strip() if tipo == "otros"
        else dict(GastoRecurrente.TIPOS)[tipo]
    )
    monto = request.POST.get("monto", "").strip()
    dia_mes = request.POST.get("dia_mes", "1").strip()

    try:
        monto = round(float(monto), 2)
    except ValueError:
        monto = 0
    try:
        dia_mes = max(1, min(31, int(dia_mes)))
    except ValueError:
        dia_mes = 1

    if nombre and monto > 0:
        if tipo == "otros":
            GastoRecurrente.objects.create(tipo=tipo, nombre=nombre, categoria="otros", monto=monto, dia_mes=dia_mes)
            verbo = "Creo"
        else:
            _, creado = GastoRecurrente.objects.update_or_create(
                tipo=tipo,
                defaults={"nombre": nombre, "categoria": "otros", "monto": monto, "dia_mes": dia_mes, "activo": True},
            )
            verbo = "Creo" if creado else "Actualizo"
        registrar(request.user, f"{verbo} el gasto fijo '{nombre}' (${monto:.2f}/mes, dia {dia_mes})")

    volver = reverse("reportes") + "?" + request.POST.get("volver", "rango=dia")
    return redirect(volver)


@login_required
@user_passes_test(es_admin)
@require_POST
def toggle_gasto_recurrente(request, recurrente_id):
    """Pausa/reactiva un gasto fijo sin borrarlo (ej: se cerro un contrato de internet
    pero se puede volver a activar mas adelante)."""
    recurrente = get_object_or_404(GastoRecurrente, id=recurrente_id)
    recurrente.activo = not recurrente.activo
    recurrente.save()
    registrar(request.user, f"{'Activo' if recurrente.activo else 'Pauso'} el gasto fijo '{recurrente.nombre}'")

    volver = reverse("reportes") + "?" + request.POST.get("volver", "rango=dia")
    return redirect(volver)


@login_required
@user_passes_test(es_admin)
@require_POST
def eliminar_gasto_recurrente(request, recurrente_id):
    recurrente = get_object_or_404(GastoRecurrente, id=recurrente_id)
    registrar(request.user, f"Elimino el gasto fijo '{recurrente.nombre}' (${recurrente.monto:.2f}/mes)")
    recurrente.delete()

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
        texto_compra = request.POST.get(f"precio_compra_{p.id}", "").strip()
        try:
            precio_compra = Decimal(texto_compra).quantize(Decimal("0.01")) if texto_compra else None
        except InvalidOperation:
            precio_compra = p.precio_compra

        cambio_precio = precio_compra != p.precio_compra
        if controla != p.controla_stock or (controla and stock != (p.stock or 0)) or cambio_precio:
            p.controla_stock = controla
            p.stock = stock if controla else None
            p.precio_compra = precio_compra
            p.save()
            detalle = f"{p.nombre}: {stock if controla else 'sin control'}"
            if cambio_precio:
                detalle += f", compra ${precio_compra:.2f}" if precio_compra is not None else ", sin precio de compra"
            cambios.append(detalle)
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
