from django.core.management.base import BaseCommand
from django.core.management import call_command
from pedidos.models import Mesa


class Command(BaseCommand):
    help = "Crea 5 mesas y carga el menu real (equivale a correr cargar_menu_brasas)"

    def handle(self, *args, **kwargs):
        for numero in range(1, 6):
            Mesa.objects.get_or_create(numero=numero)
        self.stdout.write("5 mesas listas.")
        call_command("cargar_menu_brasas")
