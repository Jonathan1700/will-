import os
from django.contrib.staticfiles import finders


def css_version(request):
    """Fecha de modificacion del CSS: se agrega como ?v= para que las tablets no usen una copia vieja."""
    ruta = finders.find("pedidos/estilo.css")
    return {"css_version": int(os.path.getmtime(ruta)) if ruta else 0}
