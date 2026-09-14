from django.contrib import admin
from .models import (
    Mesa, Producto, Orden, DetalleOrden, RegistroAccion, PiezaPollo, VarianteProducto,
    TipoMenestra, Gasto, GastoRecurrente, Cuenta, EstadoCuentaOrden,
)


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ("numero",)


class VarianteProductoInline(admin.TabularInline):
    model = VarianteProducto
    extra = 0


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "precio", "acompanamiento_incluido", "opciones_incluidas",
                    "precio_cambio", "disponible", "listo_en", "controla_stock", "stock", "es_combo",
                    "requiere_pieza")
    list_editable = ("disponible", "stock", "precio_cambio")
    list_filter = ("categoria", "disponible", "controla_stock", "es_combo", "requiere_pieza")
    inlines = [VarianteProductoInline]


@admin.register(PiezaPollo)
class PiezaPolloAdmin(admin.ModelAdmin):
    list_display = ("nombre", "orden", "stock")
    list_editable = ("orden", "stock")
    ordering = ("orden", "id")


@admin.register(TipoMenestra)
class TipoMenestraAdmin(admin.ModelAdmin):
    list_display = ("nombre", "orden", "disponible")
    list_editable = ("orden", "disponible")
    ordering = ("orden", "id")


class DetalleOrdenInline(admin.TabularInline):
    model = DetalleOrden
    extra = 0


class EstadoCuentaOrdenInline(admin.TabularInline):
    model = EstadoCuentaOrden
    extra = 0


@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    list_display = ("id", "mesa", "estado", "creado", "total")
    list_filter = ("estado", "mesa")
    inlines = [DetalleOrdenInline, EstadoCuentaOrdenInline]


@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "categoria", "descripcion", "monto", "usuario", "recurrente")
    list_filter = ("categoria", "fecha")
    date_hierarchy = "fecha"
    ordering = ("-fecha", "-creado")


@admin.register(GastoRecurrente)
class GastoRecurrenteAdmin(admin.ModelAdmin):
    """Gastos fijos mensuales (alquiler, sueldos, luz...): normalmente se cargan desde
    el dashboard (seccion 'Gastos fijos'); aqui tambien se pueden editar/revisar."""
    list_display = ("nombre", "tipo", "monto", "dia_mes", "activo")
    list_editable = ("monto", "dia_mes", "activo")
    list_filter = ("tipo", "activo")


@admin.register(Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    list_display = ("mesa", "numero", "cerrada", "creado")
    list_filter = ("cerrada", "mesa")


@admin.register(RegistroAccion)
class RegistroAccionAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario", "accion")
    list_filter = ("usuario",)
    date_hierarchy = "fecha"
    ordering = ("-fecha",)
