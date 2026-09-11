from django.contrib import admin
from .models import Mesa, Producto, Orden, DetalleOrden, RegistroAccion


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ("numero",)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "precio", "acompanamiento_incluido", "precio_cambio",
                    "disponible", "listo_en", "controla_stock", "stock", "es_combo", "requiere_pieza")
    list_editable = ("disponible", "stock", "precio_cambio")
    list_filter = ("categoria", "disponible", "controla_stock", "es_combo", "requiere_pieza")


class DetalleOrdenInline(admin.TabularInline):
    model = DetalleOrden
    extra = 0


@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    list_display = ("id", "mesa", "estado", "creado", "total")
    list_filter = ("estado", "mesa")
    inlines = [DetalleOrdenInline]


@admin.register(RegistroAccion)
class RegistroAccionAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario", "accion")
    list_filter = ("usuario",)
    date_hierarchy = "fecha"
    ordering = ("-fecha",)
