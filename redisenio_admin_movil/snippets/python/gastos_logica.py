"""
Lógica de "Gastos y ganancia" sin el artefacto del -4511%.

Problema original: se comparaban los gastos de TODO el mes (sueldos, alquiler...)
contra las ventas de un solo día, porque el sistema recién tiene datos de ese día.

Solución: mostrar resultado + cobertura de gastos + aviso de datos parciales,
y NO calcular el margen % hasta tener datos suficientes.

ADAPTAR: imports de modelos, nombres de campos y tu función actual que suma
gastos (variables + fijos). Pegar el resultado en el contexto de tu vista de reportes.
"""
from django.db.models import Sum
from django.utils import timezone

# from .models import Orden           # ADAPTAR
# from .models import Gasto           # ADAPTAR

UMBRAL_DIAS = 7  # días de datos mínimos para mostrar el margen %


def resumen_gastos_mes(hoy=None):
    hoy = hoy or timezone.localdate()
    inicio_mes = hoy.replace(day=1)

    # ADAPTAR: filtro de órdenes válidas (estado='enviada', etc.) y campo total
    ordenes_mes = Orden.objects.filter(fecha__date__gte=inicio_mes, fecha__date__lte=hoy)
    ingresos_mes = ordenes_mes.aggregate(t=Sum("total"))["t"] or 0

    # ADAPTAR: tu suma actual de gastos del mes (variables + fijos ya generados)
    gastos_mes = gastos_del_mes(inicio_mes, hoy)

    primer = ordenes_mes.order_by("fecha").values_list("fecha", flat=True).first()
    if primer:
        primer_dia = timezone.localtime(primer).date()
        dias_con_datos = (hoy - primer_dia).days + 1
    else:
        primer_dia, dias_con_datos = None, 0

    datos_parciales = dias_con_datos < UMBRAL_DIAS
    resultado = ingresos_mes - gastos_mes
    cobertura = round(ingresos_mes / gastos_mes * 100) if gastos_mes else None
    faltan = max(gastos_mes - ingresos_mes, 0)
    margen = None if (datos_parciales or not ingresos_mes) else round(resultado / ingresos_mes * 100)

    return {
        "hoy": hoy,
        "ingresos_mes": ingresos_mes,
        "gastos_mes": gastos_mes,
        "resultado": resultado,
        "cobertura": cobertura,
        "faltan": faltan,
        "margen": margen,
        "datos_parciales": datos_parciales,
        "dias_con_datos": dias_con_datos,
        "primer_dia": primer_dia,
    }

# En la vista:  ctx.update(resumen_gastos_mes())
# Alternativa (prorratear fijos en vez de mostrar mes completo):
#   from calendar import monthrange
#   gastos_mes = variables + fijos * dias_con_datos / monthrange(hoy.year, hoy.month)[1]
