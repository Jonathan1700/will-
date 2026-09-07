from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group


class Command(BaseCommand):
    help = "Crea los 3 grupos (Mesero, Cocina, Admin) y un usuario de prueba por cada uno"

    def handle(self, *args, **kwargs):
        for nombre in ["Mesero", "Cocina", "Admin"]:
            Group.objects.get_or_create(name=nombre)

        usuarios = [
            ("mesero1", "mesero123", "Mesero"),
            ("cocina1", "cocina123", "Cocina"),
            ("admin1", "admin123", "Admin"),
        ]

        for username, password, grupo in usuarios:
            user, creado = User.objects.get_or_create(username=username)
            if creado:
                user.set_password(password)
                user.save()
            user.groups.add(Group.objects.get(name=grupo))

        self.stdout.write(self.style.SUCCESS(
            "Roles y usuarios de prueba creados:\n"
            "  mesero1 / mesero123\n"
            "  cocina1 / cocina123\n"
            "  admin1  / admin123\n"
            "CAMBIA estas contraseñas antes de usar el sistema en el restaurante real."
        ))
