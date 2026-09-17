from decimal import Decimal

from django.contrib.auth.models import User, Group
from django.test import TestCase
from django.urls import reverse

from .models import (
    ConsumoPieza, DetalleOrden, Mesa, Orden, PiezaPollo, Producto, VarianteProducto, EstadoCuentaOrden,
)


class FlujoPedidoCompletoTest(TestCase):
    """Reproduce el flujo completo: mesero crea/confirma un pedido, cocina lo
    entrega y el mesero lo cierra. Verifica que ese pedido se refleje en el
    resumen (dashboard de reportes) del admin.
    """

    def setUp(self):
        Group.objects.get_or_create(name="Mesero")
        Group.objects.get_or_create(name="Cocina")
        Group.objects.get_or_create(name="Admin")

        self.mesero = User.objects.create_user("mesero", password="1234")
        self.mesero.groups.add(Group.objects.get(name="Mesero"))

        self.cocina = User.objects.create_user("cocina", password="1234")
        self.cocina.groups.add(Group.objects.get(name="Cocina"))

        self.admin = User.objects.create_user("admin", password="1234")
        self.admin.groups.add(Group.objects.get(name="Admin"))

        self.mesa = Mesa.objects.create(numero=1)
        self.producto = Producto.objects.create(
            nombre="Combo 1", precio=10, categoria="combos"
        )

    def _completar_pedido(self):
        """Camina todo el flujo mesero -> cocina -> mesero y devuelve la orden."""
        self.client.login(username="mesero", password="1234")
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        orden = Orden.objects.get(mesa=self.mesa, estado="abierta")

        self.client.post(
            reverse("agregar_item", args=[orden.id, self.producto.id])
        )
        self.client.post(reverse("confirmar_orden", args=[orden.id]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "enviada")
        self.client.logout()

        self.client.login(username="cocina", password="1234")
        self.client.post(reverse("marcar_pedido_listo", args=[orden.id, 1]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "entregada")
        self.client.logout()

        self.client.login(username="mesero", password="1234")
        self.client.post(reverse("entregar_pedido", args=[orden.id, 1]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "cerrada")
        self.client.logout()

        return orden

    def test_pedido_completado_aparece_en_resumen_de_hoy(self):
        orden = self._completar_pedido()

        self.client.login(username="admin", password="1234")
        respuesta = self.client.get(reverse("reportes"), {"rango": "dia"})

        kpi = respuesta.context["kpi"]
        self.assertEqual(
            kpi["ordenes"], 1,
            "El pedido cerrado no aparece contado en el resumen de hoy",
        )
        self.assertEqual(kpi["ingresos"], 10.0)

        ids_en_tabla = [o.id for o in respuesta.context["todas"]]
        self.assertIn(
            orden.id, ids_en_tabla,
            "El pedido cerrado no aparece en la lista 'todas las ordenes' del resumen",
        )

    def test_pedido_completado_aparece_en_desglose_por_producto(self):
        self._completar_pedido()

        self.client.login(username="admin", password="1234")
        respuesta = self.client.get(reverse("reportes"), {"rango": "dia"})

        nombres_top = [p["nombre"] for p in respuesta.context["datos"]["top"]]
        self.assertIn(
            self.producto.nombre, nombres_top,
            "El producto del pedido cerrado no aparece en 'top productos'",
        )

    def test_primer_pedido_de_una_mesa_nueva_se_guarda_igual_que_los_siguientes(self):
        """Reproduce el reporte del usuario: 'siempre el primer pedido se queda sin
        guardarse, los demas si'. Completa 3 pedidos seguidos en la MISMA mesa (recien
        creada, sin ninguna Orden previa) y verifica que los 3 - incluido el primero -
        queden contados en el resumen.
        """
        ids_cerrados = []
        for _ in range(3):
            orden = self._completar_pedido()
            ids_cerrados.append(orden.id)

        self.assertEqual(len(set(ids_cerrados)), 3, "Se reutilizo la misma Orden en vez de crear una nueva por ronda")

        self.client.login(username="admin", password="1234")
        respuesta = self.client.get(reverse("reportes"), {"rango": "dia"})

        kpi = respuesta.context["kpi"]
        ids_en_tabla = [o.id for o in respuesta.context["todas"]]

        self.assertEqual(kpi["ordenes"], 3, f"Se esperaban 3 ordenes en el resumen, hay {kpi['ordenes']}")
        for i, oid in enumerate(ids_cerrados):
            self.assertIn(oid, ids_en_tabla, f"El pedido #{i+1} (id={oid}) no aparece en el resumen")


class VentaDirectaTest(TestCase):
    """Acompañamiento/bebida/gaseosa vendido suelto: se cobra al instante y nunca
    pasa por la pantalla de cocina, pero sigue ligado a la mesa."""

    def setUp(self):
        Group.objects.get_or_create(name="Mesero")
        self.mesero = User.objects.create_user("mesero", password="1234")
        self.mesero.groups.add(Group.objects.get(name="Mesero"))
        self.client.login(username="mesero", password="1234")

        self.mesa = Mesa.objects.create(numero=1)
        self.gaseosa = Producto.objects.create(
            nombre="Coca-Cola", precio=Decimal("1.50"), categoria="gaseosas"
        )
        self.plato = Producto.objects.create(
            nombre="Combo 1", precio=Decimal("10.00"), categoria="combos"
        )

    def test_venta_directa_se_cierra_al_instante_sin_pasar_por_cocina(self):
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        self.client.post(reverse("agregar_item_directo", args=[self.mesa.id, self.gaseosa.id]))

        orden_directa = Orden.objects.get(mesa=self.mesa, es_venta_directa=True)
        self.assertEqual(orden_directa.estado, "abierta")

        self.client.post(reverse("confirmar_venta_directa", args=[orden_directa.id]))
        orden_directa.refresh_from_db()

        self.assertEqual(orden_directa.estado, "cerrada")
        self.assertNotEqual(orden_directa.estado, "enviada")
        self.assertEqual(orden_directa.total(), Decimal("1.50"))

    def test_venta_directa_no_se_mezcla_con_el_carrito_normal_de_la_mesa(self):
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        orden_normal = Orden.objects.get(mesa=self.mesa, estado="abierta", es_venta_directa=False)

        self.client.post(reverse("agregar_item_directo", args=[self.mesa.id, self.gaseosa.id]))
        self.client.post(reverse("agregar_item", args=[orden_normal.id, self.plato.id]))

        orden_normal.refresh_from_db()
        self.assertEqual(orden_normal.items.count(), 1)
        self.assertEqual(orden_normal.items.first().producto, self.plato)

        orden_directa = Orden.objects.get(mesa=self.mesa, es_venta_directa=True)
        self.assertEqual(orden_directa.items.count(), 1)
        self.assertEqual(orden_directa.items.first().producto, self.gaseosa)

    def test_no_se_puede_vender_directo_un_plato_de_pollo(self):
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        respuesta = self.client.post(
            reverse("agregar_item_directo", args=[self.mesa.id, self.plato.id])
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Orden.objects.filter(mesa=self.mesa, es_venta_directa=True).exists())


class PiezaPolloTest(TestCase):
    """El pollo requiere elegir una presa; cocina controla cuantas hay de cada tipo."""

    def setUp(self):
        Group.objects.get_or_create(name="Mesero")
        self.mesero = User.objects.create_user("mesero", password="1234")
        self.mesero.groups.add(Group.objects.get(name="Mesero"))
        self.client.login(username="mesero", password="1234")

        self.mesa = Mesa.objects.create(numero=1)
        self.pollo = Producto.objects.create(
            nombre="1/4 Pollo a la brasa", precio=Decimal("3.75"), categoria="pollo",
            requiere_pieza=True,
        )
        self.pierna = PiezaPollo.objects.create(nombre="Pierna", stock=2)
        PiezaPollo.objects.create(nombre="Ala", stock=0)

    def _orden_abierta(self):
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        return Orden.objects.get(mesa=self.mesa, estado="abierta", es_venta_directa=False)

    def test_no_deja_elegir_una_presa_sin_stock(self):
        orden = self._orden_abierta()
        respuesta = self.client.post(
            reverse("agregar_item", args=[orden.id, self.pollo.id]), {"pieza": "Ala"}
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(orden.items.count(), 0)

    def test_confirmar_orden_descuenta_el_stock_de_la_presa_usada(self):
        orden = self._orden_abierta()
        self.client.post(
            reverse("agregar_item", args=[orden.id, self.pollo.id]), {"pieza": "Pierna"}
        )
        self.client.post(reverse("confirmar_orden", args=[orden.id]))

        self.pierna.refresh_from_db()
        self.assertEqual(self.pierna.stock, 1)


class OpcionesIncluidasYVariantesTest(TestCase):
    """Quitar acompañamientos incluidos (ej. sin maduro) y elegir variantes de
    eleccion unica (ej. Menestra: Lenteja/Frejol), sin afectar el precio."""

    def setUp(self):
        Group.objects.get_or_create(name="Mesero")
        self.mesero = User.objects.create_user("mesero", password="1234")
        self.mesero.groups.add(Group.objects.get(name="Mesero"))
        self.client.login(username="mesero", password="1234")

        self.mesa = Mesa.objects.create(numero=1)
        self.pollo = Producto.objects.create(
            nombre="1 Pollo a la brasa", precio=Decimal("12.99"), categoria="pollo",
            acompanamiento_incluido="Papas fritas, patacones y maduros",
            opciones_incluidas="Papas fritas,Patacones,Maduro",
        )
        self.arroz = Producto.objects.create(
            nombre="Clasico arroz con menestra", precio=Decimal("1.75"), categoria="acompanamientos",
        )
        VarianteProducto.objects.create(producto=self.arroz, nombre="Arroz", opciones="Blanco,Moro", orden=0)
        VarianteProducto.objects.create(producto=self.arroz, nombre="Menestra", opciones="Lenteja,Frejol", orden=1)

    def _orden_abierta(self):
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        return Orden.objects.get(mesa=self.mesa, estado="abierta", es_venta_directa=False)

    def test_quitar_un_acompanamiento_incluido_no_cambia_el_precio(self):
        orden = self._orden_abierta()
        self.client.post(
            reverse("agregar_item", args=[orden.id, self.pollo.id]),
            {"sin_acompanamientos": "Maduro"},
        )
        item = orden.items.get()
        self.assertEqual(item.sin_acompanamientos, "Maduro")
        self.assertEqual(item.subtotal(), Decimal("12.99"))
        self.assertIn("sin maduro", item.descripcion().lower())

    def test_variantes_son_obligatorias_si_el_producto_las_tiene(self):
        orden = self._orden_abierta()
        respuesta = self.client.post(
            reverse("agregar_item", args=[orden.id, self.arroz.id]),
            {"variantes": "Arroz:Moro"},  # falta elegir Menestra
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(orden.items.count(), 0)

    def test_variantes_completas_se_guardan_en_el_detalle(self):
        orden = self._orden_abierta()
        self.client.post(
            reverse("agregar_item", args=[orden.id, self.arroz.id]),
            {"variantes": "Arroz:Moro|Menestra:Frejol"},
        )
        item = orden.items.get()
        self.assertEqual(item.lista_variantes_elegidas(), [("Arroz", "Moro"), ("Menestra", "Frejol")])
        self.assertIn("Arroz: Moro", item.descripcion())
        self.assertIn("Menestra: Frejol", item.descripcion())


class ParaLlevarTest(TestCase):
    """El checkbox 'para llevar' suma un recargo fijo; 'para servir' es precio normal."""

    def setUp(self):
        Group.objects.get_or_create(name="Mesero")
        self.mesero = User.objects.create_user("mesero", password="1234")
        self.mesero.groups.add(Group.objects.get(name="Mesero"))
        self.client.login(username="mesero", password="1234")

        self.mesa = Mesa.objects.create(numero=1)
        self.producto = Producto.objects.create(
            nombre="Combo 1", precio=Decimal("10.00"), categoria="combos"
        )

    def _orden_abierta(self):
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        return Orden.objects.get(mesa=self.mesa, estado="abierta", es_venta_directa=False)

    def test_para_llevar_suma_el_recargo(self):
        orden = self._orden_abierta()
        self.client.post(reverse("agregar_item", args=[orden.id, self.producto.id]))
        self.client.post(reverse("confirmar_orden", args=[orden.id]), {"para_llevar_1": "1"})

        orden.refresh_from_db()
        self.assertTrue(orden.para_llevar)
        self.assertEqual(orden.total(), Decimal("10.25"))

    def test_para_servir_no_suma_recargo(self):
        orden = self._orden_abierta()
        self.client.post(reverse("agregar_item", args=[orden.id, self.producto.id]))
        self.client.post(reverse("confirmar_orden", args=[orden.id]))

        orden.refresh_from_db()
        self.assertFalse(orden.para_llevar)
        self.assertEqual(orden.total(), Decimal("10.00"))

    def test_para_llevar_multiplica_el_recargo_por_cada_plato(self):
        """2x 1/4 de pollo para llevar: los 25 centavos se cobran por cada uno, no una sola vez."""
        pollo = Producto.objects.create(
            nombre="1/4 Pollo a la brasa", precio=Decimal("3.75"), categoria="pollo"
        )
        orden = self._orden_abierta()
        self.client.post(reverse("agregar_item", args=[orden.id, pollo.id]))
        self.client.post(reverse("agregar_item", args=[orden.id, pollo.id]))  # sube a cantidad 2
        self.client.post(reverse("confirmar_orden", args=[orden.id]), {"para_llevar_1": "1"})

        orden.refresh_from_db()
        self.assertEqual(orden.items.get(producto=pollo).cantidad, 2)
        self.assertEqual(orden.total(), Decimal("3.75") * 2 + Decimal("0.25") * 2)

    def test_para_llevar_no_recarga_bebidas(self):
        """El envase no aplica a bebidas/gaseosas: una bebida sola no suma recargo."""
        bebida = Producto.objects.create(
            nombre="Naranja", precio=Decimal("1.50"), categoria="bebidas"
        )
        orden = self._orden_abierta()
        self.client.post(reverse("agregar_item", args=[orden.id, bebida.id]))
        self.client.post(reverse("confirmar_orden", args=[orden.id]), {"para_llevar_1": "1"})

        orden.refresh_from_db()
        self.assertTrue(orden.para_llevar)
        self.assertEqual(orden.total(), Decimal("1.50"))

    def test_para_llevar_recarga_cada_acompanamiento(self):
        """3 acompañamientos para llevar: se cobra el envase de 25 centavos por cada uno."""
        acompanamiento = Producto.objects.create(
            nombre="Maduro", precio=Decimal("1.75"), categoria="acompanamientos"
        )
        orden = self._orden_abierta()
        for _ in range(3):
            self.client.post(reverse("agregar_item", args=[orden.id, acompanamiento.id]))
        self.client.post(reverse("confirmar_orden", args=[orden.id]), {"para_llevar_1": "1"})

        orden.refresh_from_db()
        self.assertEqual(orden.items.get(producto=acompanamiento).cantidad, 3)
        self.assertEqual(
            orden.total(), Decimal("1.75") * 3 + Decimal("0.25") * 3
        )

    def test_para_llevar_recarga_pollo_y_acompanamientos(self):
        """Un pollo mas un acompañamiento juntos: cada uno lleva su propio envase."""
        pollo = Producto.objects.create(
            nombre="1/4 Pollo a la brasa", precio=Decimal("3.75"), categoria="pollo"
        )
        acompanamiento = Producto.objects.create(
            nombre="Patacones", precio=Decimal("1.75"), categoria="acompanamientos"
        )
        orden = self._orden_abierta()
        self.client.post(reverse("agregar_item", args=[orden.id, pollo.id]))
        self.client.post(reverse("agregar_item", args=[orden.id, acompanamiento.id]))
        self.client.post(reverse("confirmar_orden", args=[orden.id]), {"para_llevar_1": "1"})

        orden.refresh_from_db()
        self.assertEqual(orden.total(), Decimal("3.75") + Decimal("1.75") + Decimal("0.25") * 2)

    def test_una_cuenta_para_llevar_no_recarga_la_otra_cuenta_de_la_misma_mesa(self):
        """Mesa con 2 cuentas: cuenta 1 se va (para llevar), cuenta 2 se sirve en la mesa.
        Antes el checkbox era por mesa entera y recargaba tambien a la cuenta 2."""
        pollo = Producto.objects.create(
            nombre="1/4 Pollo a la brasa", precio=Decimal("3.75"), categoria="pollo"
        )
        orden = self._orden_abierta()
        self.client.post(reverse("agregar_item", args=[orden.id, pollo.id]), {"cuenta": "1"})
        self.client.post(reverse("agregar_item", args=[orden.id, self.producto.id]), {"cuenta": "2"})
        self.client.post(reverse("confirmar_orden", args=[orden.id]), {"para_llevar_1": "1"})

        orden.refresh_from_db()
        self.assertTrue(orden.cuentas_estado.get(cuenta=1).para_llevar)
        self.assertFalse(orden.cuentas_estado.get(cuenta=2).para_llevar)
        # 1/4 pollo (3.75 + 0.25 de envase) + combo de la cuenta 2 sin recargo (10.00)
        self.assertEqual(orden.total(), Decimal("3.75") + Decimal("0.25") + Decimal("10.00"))


class ConsumoPiezasTest(TestCase):
    """1/4, 1/2 y pollo entero traen fija la combinacion de presas que consumen (a
    diferencia del 1/8, donde el mesero elige la presa): antes no descontaban nada."""

    def setUp(self):
        Group.objects.get_or_create(name="Mesero")
        Group.objects.get_or_create(name="Cocina")
        self.mesero = User.objects.create_user("mesero", password="1234")
        self.mesero.groups.add(Group.objects.get(name="Mesero"))
        self.cocina = User.objects.create_user("cocina", password="1234")
        self.cocina.groups.add(Group.objects.get(name="Cocina"))
        self.client.login(username="mesero", password="1234")

        self.mesa = Mesa.objects.create(numero=1)
        self.pechuga = PiezaPollo.objects.create(nombre="Pechuga", stock=10)
        self.cadera = PiezaPollo.objects.create(nombre="Cadera", stock=10)
        self.pierna = PiezaPollo.objects.create(nombre="Pierna", stock=10)
        self.ala = PiezaPollo.objects.create(nombre="Ala", stock=10)

        self.medio = Producto.objects.create(
            nombre="1/2 Pollo a la brasa", precio=Decimal("6.50"), categoria="pollo"
        )
        for pieza in (self.pechuga, self.cadera, self.pierna, self.ala):
            ConsumoPieza.objects.create(producto=self.medio, pieza=pieza, cantidad=1)

    def test_medio_pollo_descuenta_una_de_cada_presa(self):
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        orden = Orden.objects.get(mesa=self.mesa, estado="abierta", es_venta_directa=False)
        self.client.post(reverse("agregar_item", args=[orden.id, self.medio.id]))
        self.client.post(reverse("confirmar_orden", args=[orden.id]))

        for pieza in (self.pechuga, self.cadera, self.pierna, self.ala):
            pieza.refresh_from_db()
            self.assertEqual(pieza.stock, 9)

    def test_dos_medios_pollo_descuentan_dos_de_cada_presa(self):
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        orden = Orden.objects.get(mesa=self.mesa, estado="abierta", es_venta_directa=False)
        self.client.post(reverse("agregar_item", args=[orden.id, self.medio.id]))
        self.client.post(reverse("agregar_item", args=[orden.id, self.medio.id]))
        self.client.post(reverse("confirmar_orden", args=[orden.id]))

        for pieza in (self.pechuga, self.cadera, self.pierna, self.ala):
            pieza.refresh_from_db()
            self.assertEqual(pieza.stock, 8)

    def test_agregar_pollos_enteros_reparte_2_de_cada_presa_por_pollo(self):
        self.client.logout()
        self.client.login(username="cocina", password="1234")
        respuesta = self.client.post(reverse("agregar_pollos_enteros"), {"cantidad": "5"})

        self.assertEqual(respuesta.status_code, 200)
        for pieza in (self.pechuga, self.cadera, self.pierna, self.ala):
            pieza.refresh_from_db()
            self.assertEqual(pieza.stock, 20)  # 10 + 5*2

    def test_agregar_pollos_enteros_requiere_ser_cocina(self):
        respuesta = self.client.post(reverse("agregar_pollos_enteros"), {"cantidad": "5"})
        self.assertEqual(respuesta.status_code, 302)
        self.pechuga.refresh_from_db()
        self.assertEqual(self.pechuga.stock, 10)


class CuentasSeparadasTest(TestCase):
    """Una mesa con varias cuentas (ej: 2 personas que pagan separado): cocina prepara
    cada 'pedido' por separado y el mesero lo lleva a la mesa por separado. En cocina y
    en la tablet aparecen uno a uno (Pedido 1, Pedido 2...), igual que el mesero los separo."""

    def setUp(self):
        Group.objects.get_or_create(name="Mesero")
        Group.objects.get_or_create(name="Cocina")
        self.mesero = User.objects.create_user("mesero", password="1234")
        self.mesero.groups.add(Group.objects.get(name="Mesero"))
        self.cocina = User.objects.create_user("cocina", password="1234")
        self.cocina.groups.add(Group.objects.get(name="Cocina"))

        self.mesa = Mesa.objects.create(numero=1)
        self.pollo = Producto.objects.create(
            nombre="1/4 Pollo a la brasa", precio=Decimal("3.75"), categoria="pollo"
        )
        self.bebida = Producto.objects.create(
            nombre="Coca-Cola", precio=Decimal("1.50"), categoria="bebidas"
        )

    def _crear_orden_dividida(self):
        """Cuenta 1: 1/4 de pollo. Cuenta 2: coca. Confirmada y enviada a cocina."""
        self.client.login(username="mesero", password="1234")
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        orden = Orden.objects.get(mesa=self.mesa, estado="abierta", es_venta_directa=False)
        self.client.post(reverse("agregar_item", args=[orden.id, self.pollo.id]), {"cuenta": "1"})
        self.client.post(reverse("agregar_item", args=[orden.id, self.bebida.id]), {"cuenta": "2"})
        self.client.post(reverse("confirmar_orden", args=[orden.id]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "enviada")
        self.assertEqual(
            {e.cuenta for e in orden.cuentas_estado.all()},
            {1, 2},
            "Se deben crear estados de entrega para cada cuenta de la orden",
        )
        return orden

    def test_cocina_ve_pedidos_separados_y_se_marcan_listos_uno_a_uno(self):
        """cocina prepara la coca (pedido 2) y la marca lista sin tocar el pollo (pedido 1)."""
        orden = self._crear_orden_dividida()

        self.client.login(username="cocina", password="1234")
        respuesta = self.client.get(reverse("panel_cocina"))
        cocina = respuesta.context["ordenes"][0]
        pedidos = {pc["numero"]: pc for pc in cocina.pedidos_cocina}
        self.assertIn(1, pedidos, "El pedido 1 (1/4 pollo) debe aparecer en cocina")
        self.assertIn(2, pedidos, "El pedido 2 (coca) debe aparecer en cocina")
        self.assertEqual(pedidos[1]["items"][0].producto, self.pollo)
        self.assertEqual(pedidos[2]["items"][0].producto, self.bebida)
        self.assertFalse(pedidos[1]["listo"])

        # solo el pedido 2 sale: la orden sigue en cocina hasta que todo este listo
        self.client.post(reverse("marcar_pedido_listo", args=[orden.id, 2]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "enviada")
        self.assertFalse(orden.cuentas_estado.get(cuenta=1).listo)
        self.assertTrue(orden.cuentas_estado.get(cuenta=2).listo)

        # la tablet del mesero avisa solo el pedido 2 (coca), no el pollo que falta
        self.client.login(username="mesero", password="1234")
        respuesta = self.client.get(reverse("elegir_mesa"))
        pendientes = [(p["orden"].id, p["cuenta"]) for p in respuesta.context["ordenes_listas"]]
        self.assertEqual(pendientes, [(orden.id, 2)])
        tarjeta = respuesta.context["ordenes_listas"][0]
        self.assertEqual([i.producto for i in tarjeta["items"]], [self.bebida])
        self.assertEqual(tarjeta["total"], Decimal("1.50"))

        # el mesero entrega el pedido 2: la mesa sigue pendiente en cocina (falta el 1)
        self.client.post(reverse("entregar_pedido", args=[orden.id, 2]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "enviada")

        # cocina marca el pedido 1: recien ahi la orden pasa a 'entregada'
        self.client.login(username="cocina", password="1234")
        self.client.post(reverse("marcar_pedido_listo", args=[orden.id, 1]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "entregada")

        # entregado el 1/4 de pollo, se cierra la orden completa
        self.client.login(username="mesero", password="1234")
        self.client.post(reverse("entregar_pedido", args=[orden.id, 1]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "cerrada")
        self.assertTrue(orden.cuentas_estado.get(cuenta=1).entregado)
        self.assertTrue(orden.cuentas_estado.get(cuenta=2).entregado)

    def test_una_sola_cuenta_sete_entrega_normal(self):
        """Con una unica cuenta no se divide nada: cocina marca listo y el mesero entrega."""
        self.client.login(username="mesero", password="1234")
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        orden = Orden.objects.get(mesa=self.mesa, estado="abierta", es_venta_directa=False)
        self.client.post(reverse("agregar_item", args=[orden.id, self.pollo.id]), {"cuenta": "1"})
        self.client.post(reverse("confirmar_orden", args=[orden.id]))

        orden.refresh_from_db()
        self.assertEqual(list(orden.cuentas_estado.values_list("cuenta", flat=True)), [1])

        self.client.login(username="cocina", password="1234")
        respuesta = self.client.get(reverse("panel_cocina"))
        cocina = respuesta.context["ordenes"][0]
        pedidos = cocina.pedidos_cocina
        self.assertEqual(len(pedidos), 1)
        self.assertTemplateUsed(respuesta, "pedidos/panel_cocina.html")

        self.client.post(reverse("marcar_pedido_listo", args=[orden.id, 1]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "entregada")

        self.client.login(username="mesero", password="1234")
        respuesta = self.client.get(reverse("elegir_mesa"))
        self.assertEqual(respuesta.context["ordenes_listas"][0]["cuenta"], 1)
        self.client.post(reverse("entregar_pedido", args=[orden.id, 1]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "cerrada")
