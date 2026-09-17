from django.urls import path
from . import views

urlpatterns = [
    # login jej
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("post-login/", views.post_login, name="post_login"),

    # mesero
    path("", views.elegir_mesa, name="elegir_mesa"),
    path("mesa/<int:mesa_id>/cuentas/", views.cuentas_mesa, name="cuentas_mesa"),
    path("mesa/<int:mesa_id>/cuentas/nueva/", views.crear_cuenta, name="crear_cuenta"),
    path("cuenta/<int:cuenta_id>/cobrar/", views.cobrar_cuenta, name="cobrar_cuenta"),
    path("cuenta/<int:cuenta_id>/eliminar/", views.eliminar_cuenta, name="eliminar_cuenta"),
    path("mesa/<int:mesa_id>/", views.menu_mesa, name="menu_mesa"),
    path("orden/<int:orden_id>/agregar/<int:producto_id>/", views.agregar_item, name="agregar_item"),
    path("orden/<int:orden_id>/item/<int:item_id>/cantidad/", views.cambiar_cantidad, name="cambiar_cantidad"),
    path("orden/<int:orden_id>/items/eliminar/", views.eliminar_items, name="eliminar_items"),
    path("orden/<int:orden_id>/confirmar/", views.confirmar_orden, name="confirmar_orden"),
    path("mesa/<int:mesa_id>/directo/<int:producto_id>/", views.agregar_item_directo, name="agregar_item_directo"),
    path("orden/<int:orden_id>/cobrar-directo/", views.confirmar_venta_directa, name="confirmar_venta_directa"),
    path("api/disponibilidad/", views.disponibilidad_json, name="disponibilidad_json"),
    path("api/listas/", views.ordenes_listas_json, name="ordenes_listas_json"),
    path("mesa/<int:mesa_id>/cuenta/<int:cuenta>/entregar/", views.entregar_grupo, name="entregar_grupo"),
    path("mesa/<int:mesa_id>/cuenta/<int:cuenta>/detalle/", views.detalle_pedido, name="detalle_pedido"),
    path("mesa/<int:mesa_id>/entregar-todo/", views.entregar_mesa, name="entregar_mesa"),

    # cocina xd
    path("cocina/", views.panel_cocina, name="panel_cocina"),
    path("cocina/api/pendientes/", views.ordenes_pendientes_json, name="ordenes_pendientes_json"),
    path("cocina/orden/<int:orden_id>/cuenta/<int:cuenta>/lista/", views.marcar_pedido_listo, name="marcar_pedido_listo"),
    path("cocina/disponibilidad/", views.panel_disponibilidad, name="panel_disponibilidad"),
    path("cocina/producto/<int:producto_id>/toggle/", views.toggle_disponibilidad, name="toggle_disponibilidad"),
    path("cocina/producto/<int:producto_id>/temporizador/", views.poner_temporizador, name="poner_temporizador"),
    path("cocina/pieza/<int:pieza_id>/stock/", views.actualizar_stock_pieza, name="actualizar_stock_pieza"),
    path("cocina/pieza/agregar-pollos/", views.agregar_pollos_enteros, name="agregar_pollos_enteros"),
    path("cocina/menestra/<int:tipo_id>/toggle/", views.toggle_menestra, name="toggle_menestra"),

    # admin / reportes
    path("reportes/", views.reportes, name="reportes"),
    path("reportes/exportar/", views.exportar_excel, name="exportar_excel"),
    path("reportes/stock/", views.actualizar_stock, name="actualizar_stock"),
    path("reportes/gastos/agregar/", views.agregar_gasto, name="agregar_gasto"),
    path("reportes/gastos/<int:gasto_id>/eliminar/", views.eliminar_gasto, name="eliminar_gasto"),
    path("reportes/gastos-fijos/agregar/", views.agregar_gasto_recurrente, name="agregar_gasto_recurrente"),
    path("reportes/gastos-fijos/<int:recurrente_id>/toggle/", views.toggle_gasto_recurrente, name="toggle_gasto_recurrente"),
    path("reportes/gastos-fijos/<int:recurrente_id>/eliminar/", views.eliminar_gasto_recurrente, name="eliminar_gasto_recurrente"),
]
