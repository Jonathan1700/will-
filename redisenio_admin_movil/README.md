# Rediseño móvil del panel admin — Brasas

Paquete para implementar el rediseño con Claude Code.

## Contenido
```
PROMPT_CLAUDE_CODE.md          <- pegar en Claude Code
reference_mockup/              <- 6 pantallas de referencia (390x844), HTML legible
  Main.dc.html                    1. Resumen
  Ventas.dc.html                  2. Ventas: qué se vendió (acordeón)
  Ordenes.dc.html                 3. Ventas: órdenes (tarjetas)
  Inventario.dc.html              4. Inventario (tarjetas + guardar sticky)
  Gastos.dc.html                  5. Gastos y ganancia (aviso + cobertura + FAB)
  NuevoGasto.dc.html              6. Hoja "Nuevo gasto"
snippets/
  templatetags/formato.py         filtro |dinero
  static/css/admin_movil.css      todo el CSS
  static/js/admin_movil.js        barra inferior, sub-pestañas, diálogos
  templates/partials/             _header, _filtro, _bottom_nav, _resumen, _ventas,
                                  _inventario, _gastos, _panel_admin_ejemplo
  templates/icons/                SVGs de la barra inferior
  python/gastos_logica.py         corrección del cálculo de ganancia/margen
```

## Cómo usarlo
1. Descomprime dentro de la raíz de tu proyecto Django (queda `redisenio_admin_movil/`).
2. Abre Claude Code en esa raíz y pega el contenido de `PROMPT_CLAUDE_CODE.md`.
3. Revisa el diff por commits (uno por paso) antes de fusionar la rama.

## Importante
- Los `snippets` usan nombres genéricos (`o.total`, `d.nota`, `b.lleva_conteo`,
  `gastos_del_mes()`, `agregar_gasto`, `exportar_excel`...). Están marcados con `ADAPTAR`.
- Los `.dc.html` de `reference_mockup` son de referencia visual: ábrelos como texto,
  no como página (dependen del editor de diseño donde se crearon).
- Los totales de las órdenes del mockup son ilustrativos.
