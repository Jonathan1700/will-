from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum
from datetime import timedelta
import openpyxl

from .models import Mesa, Producto, Orden, DetalleOrden, RegistroAccion


# ---------- LOGIN / ROLES ----------

def es_mesero(user):
    return user.groups.filter(name="Mesero").exists() or user.is_superuser


def es_cocina(user):
    return user.groups.filter(name="Cocina").exists() or user.is_superuser


def es_admin(user):
    return user.groups.filter(name="Admin").exists() or user.is_superuser


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
    orden, _ = Orden.objects.get_or_create(mesa=mesa, estado="abierta")

    categoria = request.GET.get("categoria", "combos")
    productos = Producto.objects.filter(categoria=categoria).order_by("nombre")

    contexto = {
        "mesa": mesa,
        "orden": orden,
        "productos": productos,
        "categoria_activa": categoria,
        "categorias": Producto.CATEGORIAS,
        "piezas_pollo": Producto.PIEZAS_POLLO,
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
    if producto.requiere_pieza:
        if pieza not in Producto.PIEZAS_POLLO:
            return JsonResponse({"ok": False, "error": "Selecciona una pieza"}, status=400)
    else:
        pieza = ""

    item, creado = DetalleOrden.objects.get_or_create(orden=orden, producto=producto, notas=pieza)
    nueva_cantidad = item.cantidad + 1 if not creado else 1

    if producto.controla_stock and nueva_cantidad > producto.stock:
        return JsonResponse({"ok": False, "error": "No hay suficiente stock"}, status=400)

    item.cantidad = nueva_cantidad
    item.save()

    categoria = request.POST.get("categoria", "combos")
    return redirect(f"{reverse('menu_mesa', args=[orden.mesa.id])}?categoria={categoria}")


@login_required
@user_passes_test(es_mesero)
@require_POST
def confirmar_orden(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id, estado="abierta")

    for item in orden.items.all():
        if item.producto.controla_stock:
            item.producto.stock = max(0, item.producto.stock - item.cantidad)
            item.producto.save()

    orden.estado = "enviada"
    orden.enviado_a_cocina = timezone.now()
    orden.save()

    registrar(request.user, f"Confirmo orden #{orden.id} - Mesa {orden.mesa.numero} - ${orden.total()}")
    return redirect("elegir_mesa")


# ---------- COCINA ----------

@login_required
@user_passes_test(es_cocina)
def panel_cocina(request):
    ordenes = Orden.objects.filter(estado="enviada").order_by("enviado_a_cocina")
    productos_todos = Producto.objects.all().order_by("categoria", "nombre")
    return render(request, "pedidos/panel_cocina.html", {
        "ordenes": ordenes,
        "productos_todos": productos_todos,
    })


def ordenes_pendientes_json(request):
    ordenes = Orden.objects.filter(estado="enviada").order_by("enviado_a_cocina")
    data = [{
        "id": o.id,
        "mesa": o.mesa.numero,
        "minutos": o.minutos_en_espera(),
        "items": [f"{i.cantidad}x {i.producto.nombre}" for i in o.items.all()],
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
    return redirect("panel_cocina")


def disponibilidad_json(request):
    productos = Producto.objects.all()
    data = {p.id: p.esta_disponible() for p in productos}
    return JsonResponse({"disponibilidad": data})


# ---------- ADMIN: REPORTES ----------

def _rango_fechas(request):
    """Lee ?rango=dia|semana|mes de la URL y devuelve (desde, hasta, etiqueta)."""
    rango = request.GET.get("rango", "dia")
    hoy = timezone.localdate()

    if rango == "semana":
        desde = hoy - timedelta(days=hoy.weekday())
        etiqueta = f"Semana del {desde.strftime('%d/%m')}"
    elif rango == "mes":
        desde = hoy.replace(day=1)
        etiqueta = f"{hoy.strftime('%B %Y')}"
    else:
        rango = "dia"
        desde = hoy
        etiqueta = f"Hoy ({hoy.strftime('%d/%m/%Y')})"

    return rango, desde, hoy, etiqueta


@login_required
@user_passes_test(es_admin)
def reportes(request):
    rango, desde, hasta, etiqueta = _rango_fechas(request)

    ordenes = Orden.objects.filter(
        creado__date__gte=desde,
        creado__date__lte=hasta,
        estado__in=["entregada", "cerrada"],
    )

    total_ordenes = ordenes.count()
    ingreso_total = sum(o.total() for o in ordenes)
    ticket_promedio = (ingreso_total / total_ordenes) if total_ordenes else 0

    productos_vendidos = (
        DetalleOrden.objects.filter(orden__in=ordenes)
        .values("producto__nombre")
        .annotate(cantidad_total=Sum("cantidad"))
        .order_by("-cantidad_total")[:10]
    )

    registros = RegistroAccion.objects.all()[:30]

    contexto = {
        "rango": rango,
        "etiqueta": etiqueta,
        "total_ordenes": total_ordenes,
        "ingreso_total": ingreso_total,
        "ticket_promedio": ticket_promedio,
        "productos_vendidos": productos_vendidos,
        "registros": registros,
    }
    return render(request, "pedidos/reportes.html", contexto)


@login_required
@user_passes_test(es_admin)
def exportar_excel(request):
    rango, desde, hasta, etiqueta = _rango_fechas(request)

    ordenes = Orden.objects.filter(
        creado__date__gte=desde,
        creado__date__lte=hasta,
        estado__in=["entregada", "cerrada"],
    ).order_by("creado")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas"
    ws.append(["Orden", "Mesa", "Fecha", "Producto", "Cantidad", "Subtotal"])

    for orden in ordenes:
        for item in orden.items.all():
            ws.append([
                orden.id,
                orden.mesa.numero,
                orden.creado.strftime("%d/%m/%Y %H:%M"),
                item.producto.nombre,
                item.cantidad,
                float(item.subtotal()),
            ])

    ws2 = wb.create_sheet("Resumen por producto")
    ws2.append(["Producto", "Cantidad vendida", "Total"])
    resumen = (
        DetalleOrden.objects.filter(orden__in=ordenes)
        .values("producto__nombre")
        .annotate(cantidad=Sum("cantidad"))
    )
    for r in resumen:
        producto = Producto.objects.filter(nombre=r["producto__nombre"]).first()
        precio = float(producto.precio) if producto else 0
        ws2.append([r["producto__nombre"], r["cantidad"], r["cantidad"] * precio])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    nombre_archivo = f"ventas_{rango}_{hasta.strftime('%Y%m%d')}.xlsx"
    response["Content-Disposition"] = f"attachment; filename={nombre_archivo}"
    wb.save(response)
    return response
