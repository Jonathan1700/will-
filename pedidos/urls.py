from django.urls import path
from . import views

urlpatterns = [
    # login jej
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("post-login/", views.post_login, name="post_login"),

    # mesero 
    path("", views.elegir_mesa, name="elegir_mesa"),
    path("mesa/<int:mesa_id>/", views.menu_mesa, name="menu_mesa"),
    path("orden/<int:orden_id>/agregar/<int:producto_id>/", views.agregar_item, name="agregar_item"),
    path("orden/<int:orden_id>/item/<int:item_id>/cantidad/", views.cambiar_cantidad, name="cambiar_cantidad"),
    path("orden/<int:orden_id>/items/eliminar/", views.eliminar_items, name="eliminar_items"),
    path("orden/<int:orden_id>/confirmar/", views.confirmar_orden, name="confirmar_orden"),
    path("mesa/<int:mesa_id>/directo/<int:producto_id>/", views.agregar_item_directo, name="agregar_item_directo"),
    path("orden/<int:orden_id>/cobrar-directo/", views.confirmar_venta_directa, name="confirmar_venta_directa"),
    path("api/disponibilidad/", views.disponibilidad_json, name="disponibilidad_json"),
    path("api/listas/", views.ordenes_listas_json, name="ordenes_listas_json"),
    path("orden/<int:orden_id>/entregar/", views.entregar_a_cliente, name="entregar_a_cliente"),

    # cocina xd
    path("cocina/", views.panel_cocina, name="panel_cocina"),
    path("cocina/api/pendientes/", views.ordenes_pendientes_json, name="ordenes_pendientes_json"),
    path("cocina/orden/<int:orden_id>/entregada/", views.marcar_entregada, name="marcar_entregada"),
    path("cocina/producto/<int:producto_id>/toggle/", views.toggle_disponibilidad, name="toggle_disponibilidad"),
    path("cocina/producto/<int:producto_id>/temporizador/", views.poner_temporizador, name="poner_temporizador"),
    path("cocina/pieza/<int:pieza_id>/stock/", views.actualizar_stock_pieza, name="actualizar_stock_pieza"),
    path("cocina/menestra/<int:tipo_id>/toggle/", views.toggle_menestra, name="toggle_menestra"),

    # admin / reportes
    path("reportes/", views.reportes, name="reportes"),
    path("reportes/exportar/", views.exportar_excel, name="exportar_excel"),
    path("reportes/stock/", views.actualizar_stock, name="actualizar_stock"),
    path("reportes/gastos/agregar/", views.agregar_gasto, name="agregar_gasto"),
    path("reportes/gastos/<int:gasto_id>/eliminar/", views.eliminar_gasto, name="eliminar_gasto"),
]
