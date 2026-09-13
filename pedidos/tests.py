from decimal import Decimal

from django.contrib.auth.models import User, Group
from django.test import TestCase
from django.urls import reverse

from .models import Cuenta, DetalleOrden, Mesa, Orden, PiezaPollo, Producto, VarianteProducto


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
        self.client.post(reverse("marcar_entregada", args=[orden.id]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, "entregada")
        self.client.logout()

        self.client.login(username="mesero", password="1234")
        self.client.post(reverse("entregar_a_cliente", args=[orden.id]))
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
        self.client.post(reverse("confirmar_orden", args=[orden.id]), {"para_llevar": "1"})

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
        self.client.post(reverse("confirmar_orden", args=[orden.id]), {"para_llevar": "1"})

        orden.refresh_from_db()
        self.assertEqual(orden.items.get(producto=pollo).cantidad, 2)
        self.assertEqual(orden.total(), Decimal("3.75") * 2 + Decimal("0.25") * 2)

    def test_para_llevar_no_recarga_bebidas_ni_acompanamientos_sueltos(self):
        """El envase es por plato (pollo/combos); una bebida sola no suma recargo."""
        bebida = Producto.objects.create(
            nombre="Naranja", precio=Decimal("1.50"), categoria="bebidas"
        )
        orden = self._orden_abierta()
        self.client.post(reverse("agregar_item", args=[orden.id, bebida.id]))
        self.client.post(reverse("confirmar_orden", args=[orden.id]), {"para_llevar": "1"})

        orden.refresh_from_db()
        self.assertTrue(orden.para_llevar)
        self.assertEqual(orden.total(), Decimal("1.50"))


class CuentasDeMesaTest(TestCase):
    """Una mesa se puede dividir en varias cuentas (Cuenta 1, Cuenta 2...), cada una
    con su propio carrito y total. Cocina no debe enterarse de esto."""

    def setUp(self):
        Group.objects.get_or_create(name="Mesero")
        Group.objects.get_or_create(name="Cocina")
        self.mesero = User.objects.create_user("mesero", password="1234")
        self.mesero.groups.add(Group.objects.get(name="Mesero"))
        self.cocina = User.objects.create_user("cocina", password="1234")
        self.cocina.groups.add(Group.objects.get(name="Cocina"))

        self.mesa = Mesa.objects.create(numero=5)
        self.hamburguesa = Producto.objects.create(
            nombre="Hamburguesa", precio=Decimal("8.00"), categoria="combos"
        )
        self.pizza = Producto.objects.create(
            nombre="Pizza", precio=Decimal("12.00"), categoria="combos"
        )

    def test_mesa_nueva_arranca_con_una_sola_cuenta_automatica(self):
        self.client.login(username="mesero", password="1234")
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))

        self.assertEqual(Cuenta.objects.filter(mesa=self.mesa).count(), 1)
        self.assertEqual(Cuenta.objects.get(mesa=self.mesa).numero, 1)

    def test_agregar_cuenta_numera_1_2_3_y_no_mezcla_los_carritos(self):
        self.client.login(username="mesero", password="1234")

        respuesta = self.client.post(reverse("agregar_cuenta", args=[self.mesa.id]))
        cuenta1 = Cuenta.objects.get(mesa=self.mesa)
        self.assertEqual(cuenta1.numero, 1)
        self.assertRedirects(respuesta, f"{reverse('menu_mesa', args=[self.mesa.id])}?cuenta={cuenta1.id}")

        respuesta = self.client.post(reverse("agregar_cuenta", args=[self.mesa.id]))
        cuenta2 = Cuenta.objects.exclude(id=cuenta1.id).get(mesa=self.mesa)
        self.assertEqual(cuenta2.numero, 2)
        self.assertRedirects(respuesta, f"{reverse('menu_mesa', args=[self.mesa.id])}?cuenta={cuenta2.id}")

        orden1 = Orden.objects.get(cuenta=cuenta1, estado="abierta")
        orden2 = Orden.objects.get(cuenta=cuenta2, estado="abierta")
        self.client.post(reverse("agregar_item", args=[orden1.id, self.hamburguesa.id]))
        self.client.post(reverse("agregar_item", args=[orden2.id, self.pizza.id]))

        orden1.refresh_from_db()
        orden2.refresh_from_db()
        self.assertEqual(orden1.items.get().producto, self.hamburguesa)
        self.assertEqual(orden2.items.get().producto, self.pizza)
        self.assertEqual(orden1.total(), Decimal("8.00"))
        self.assertEqual(orden2.total(), Decimal("12.00"))

    def test_cuenta_se_cierra_sola_cuando_su_ultima_orden_se_entrega(self):
        self.client.login(username="mesero", password="1234")
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        cuenta = Cuenta.objects.get(mesa=self.mesa)
        orden = Orden.objects.get(cuenta=cuenta, estado="abierta")

        self.client.post(reverse("agregar_item", args=[orden.id, self.hamburguesa.id]))
        self.client.post(reverse("confirmar_orden", args=[orden.id]))
        self.client.logout()

        self.client.login(username="cocina", password="1234")
        self.client.post(reverse("marcar_entregada", args=[orden.id]))
        self.client.logout()

        self.client.login(username="mesero", password="1234")
        self.assertTrue(cuenta.esta_abierta())
        self.client.post(reverse("entregar_a_cliente", args=[orden.id]))

        self.assertFalse(cuenta.esta_abierta())

        # la mesa vuelve a estar libre: la siguiente cuenta sigue la numeracion (no reusa el 1)
        respuesta = self.client.post(reverse("agregar_cuenta", args=[self.mesa.id]))
        nueva = Cuenta.objects.exclude(id=cuenta.id).get(mesa=self.mesa)
        self.assertEqual(nueva.numero, 2)

    def test_panel_de_cocina_no_muestra_cuentas(self):
        self.client.login(username="mesero", password="1234")
        self.client.get(reverse("menu_mesa", args=[self.mesa.id]))
        orden = Orden.objects.get(mesa=self.mesa, estado="abierta", es_venta_directa=False)
        self.client.post(reverse("agregar_item", args=[orden.id, self.hamburguesa.id]))
        self.client.post(reverse("confirmar_orden", args=[orden.id]))
        self.client.logout()

        self.client.login(username="cocina", password="1234")
        respuesta = self.client.get(reverse("panel_cocina"))
        self.assertNotContains(respuesta, "Cuenta 1")
