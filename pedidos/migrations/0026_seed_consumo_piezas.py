# Carga la receta fija de presas para 1/4, 1/2 y pollo entero (los combos 1/8 ya
# funcionan aparte: ahi el mesero elige la presa a mano). Solo crea filas para los
# productos/presas que existan hoy con ese nombre exacto; si no coincide, no falla,
# simplemente no crea esa fila (se puede cargar despues a mano desde /admin/).

from django.db import migrations

RECETAS = {
    "1/4 Pollo a la brasa (pechuga)": {"Pechuga": 1, "Ala": 1},
    "1/4 Pollo a la brasa (pierna)": {"Pierna": 1, "Cadera": 1},
    "1/2 Pollo a la brasa": {"Pechuga": 1, "Ala": 1, "Pierna": 1, "Cadera": 1},
    "1 Pollo a la brasa": {"Pechuga": 2, "Ala": 2, "Pierna": 2, "Cadera": 2},
}


def cargar_recetas(apps, schema_editor):
    Producto = apps.get_model("pedidos", "Producto")
    PiezaPollo = apps.get_model("pedidos", "PiezaPollo")
    ConsumoPieza = apps.get_model("pedidos", "ConsumoPieza")

    for nombre_producto, piezas in RECETAS.items():
        producto = Producto.objects.filter(nombre=nombre_producto, categoria="pollo").first()
        if not producto:
            continue
        for nombre_pieza, cantidad in piezas.items():
            pieza = PiezaPollo.objects.filter(nombre=nombre_pieza).first()
            if not pieza:
                continue
            ConsumoPieza.objects.get_or_create(
                producto=producto, pieza=pieza, defaults={"cantidad": cantidad},
            )


def revertir(apps, schema_editor):
    ConsumoPieza = apps.get_model("pedidos", "ConsumoPieza")
    ConsumoPieza.objects.filter(producto__nombre__in=RECETAS.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0025_consumopieza"),
    ]

    operations = [
        migrations.RunPython(cargar_recetas, revertir),
    ]
