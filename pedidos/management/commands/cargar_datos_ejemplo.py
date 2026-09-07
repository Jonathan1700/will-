from django.core.management.base import BaseCommand
from pedidos.models import Mesa, Producto


class Command(BaseCommand):
    help = "Carga mesas y productos de ejemplo para probar el sistema"

    def handle(self, *args, **kwargs):
        for numero in range(1, 9):
            Mesa.objects.get_or_create(numero=numero)

        productos = [
            dict(nombre="Combo familiar", precio=14.00, categoria="combos", es_combo=True,
                 combo_incluye="Pollo entero + papas grandes + ensalada + 4 colas"),
            dict(nombre="Combo personal", precio=5.50, categoria="combos", es_combo=True,
                 combo_incluye="1/4 pollo + papas + gaseosa", requiere_pieza=True),
            dict(nombre="1/8 de pollo", precio=2.00, categoria="pollo", requiere_pieza=True),
            dict(nombre="1/4 de pollo", precio=3.50, categoria="pollo", requiere_pieza=True),
            dict(nombre="1/2 pollo", precio=6.00, categoria="pollo"),
            dict(nombre="Pollo entero", precio=11.00, categoria="pollo"),
            dict(nombre="Papas fritas", precio=1.50, categoria="papas"),
            dict(nombre="Papas con salsa", precio=2.00, categoria="papas"),
            dict(nombre="Papas al horno", precio=1.80, categoria="papas"),
            dict(nombre="Coca-Cola", precio=1.50, categoria="bebidas", controla_stock=True, stock=24),
            dict(nombre="Jugo natural", precio=2.00, categoria="bebidas"),
            dict(nombre="Agua", precio=1.00, categoria="bebidas"),
            dict(nombre="Chicha morada", precio=2.00, categoria="bebidas", controla_stock=True, stock=50),
        ]
        for p in productos:
            Producto.objects.get_or_create(nombre=p["nombre"], defaults=p)

        self.stdout.write(self.style.SUCCESS("Datos de ejemplo cargados: 8 mesas y 13 productos."))
