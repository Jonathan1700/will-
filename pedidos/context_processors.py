import os
from django.contrib.staticfiles import finders


def _version(nombre_estatico):
    ruta = finders.find(nombre_estatico)
    return int(os.path.getmtime(ruta)) if ruta else 0


def css_version(request):
    """Fecha de modificacion de cada estatico: se agrega como ?v= para que las tablets
    no se queden con una copia vieja en cache."""
    return {
        "css_version": _version("pedidos/estilo.css"),
        "admin_movil_css_version": _version("pedidos/admin_movil.css"),
        "admin_movil_js_version": _version("pedidos/admin_movil.js"),
    }
