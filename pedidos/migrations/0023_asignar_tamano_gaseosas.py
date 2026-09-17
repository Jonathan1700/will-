from django.db import migrations


def tamano_desde_nombre(nombre):
    """Adivina el tamano a partir del nombre cargado a mano en /admin/ (ej. 'Coca-Cola 1.35L')."""
    normalizado = nombre.lower().replace(" ", "")
    if "2l" in normalizado:
        return "dos_litros"
    if "1.35" in normalizado or "135" in normalizado:
        return "litro_35"
    if "1l" in normalizado:
        return "litro"
    return "personal"


def asignar_tamano(apps, schema_editor):
    Producto = apps.get_model("pedidos", "Producto")
    for p in Producto.objects.filter(categoria="gaseosas"):
        tamano = tamano_desde_nombre(p.nombre)
        if tamano != p.tamano:
            p.tamano = tamano
            p.save(update_fields=["tamano"])


def revertir(apps, schema_editor):
    Producto = apps.get_model("pedidos", "Producto")
    Producto.objects.filter(categoria="gaseosas").update(tamano="personal")


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0022_producto_tamano'),
    ]

    operations = [
        migrations.RunPython(asignar_tamano, revertir),
    ]
