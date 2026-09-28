"""
Filtros de formato para el panel admin.
Copiar a: <tu_app>/templatetags/formato.py  (y crear __init__.py si no existe)
Uso en templates:  {% load formato %}  {{ valor|dinero }}
"""
from django import template

register = template.Library()


@register.filter
def dinero(valor):
    """1234.5 -> $1.234,50   |   -2693.3 -> -$2.693,30"""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "$0,00"
    signo = "-" if v < 0 else ""
    txt = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{signo}${txt}"
