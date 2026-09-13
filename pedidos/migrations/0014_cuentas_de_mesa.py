import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0013_pollo_despresado"),
    ]

    operations = [
        migrations.CreateModel(
            name="Cuenta",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("numero", models.IntegerField()),
                ("creado", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "mesa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cuentas",
                        to="pedidos.mesa",
                    ),
                ),
            ],
            options={
                "ordering": ["numero"],
            },
        ),
        migrations.AddField(
            model_name="orden",
            name="cuenta",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ordenes",
                to="pedidos.cuenta",
            ),
        ),
    ]
