from django.db import migrations

NOMBRE_COMBO = "1/8 Pollo a la brasa con arroz y menestra"
GRUPOS = [
    ("Arroz", "Blanco,Moro"),
    ("Menestra", "Lenteja,Frejol"),
]


def agregar_variantes(apps, schema_editor):
    """El combo de arroz y menestra tambien deja elegir arroz blanco/moro y
    lenteja/frejol, igual que el acompanamiento 'Clasico arroz con menestra'.
    El combo de papas y maduros ('1/8 Pollo a la brasa') no se toca."""
    Producto = apps.get_model("pedidos", "Producto")
    VarianteProducto = apps.get_model("pedidos", "VarianteProducto")
    producto = Producto.objects.filter(nombre=NOMBRE_COMBO).first()
    if not producto:
        return
    for orden, (nombre_grupo, opciones) in enumerate(GRUPOS):
        VarianteProducto.objects.update_or_create(
            producto=producto, nombre=nombre_grupo,
            defaults={"opciones": opciones, "orden": orden},
        )


def quitar_variantes(apps, schema_editor):
    VarianteProducto = apps.get_model("pedidos", "VarianteProducto")
    VarianteProducto.objects.filter(
        producto__nombre=NOMBRE_COMBO, nombre__in=[g[0] for g in GRUPOS],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0020_alter_orden_estado"),
    ]

    operations = [
        migrations.RunPython(agregar_variantes, quitar_variantes),
    ]
