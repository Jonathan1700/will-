from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0012_gasto"),
    ]

    operations = [
        migrations.AddField(
            model_name="detalleorden",
            name="despresado",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="producto",
            name="permite_despresado",
            field=models.BooleanField(default=False),
        ),
    ]
