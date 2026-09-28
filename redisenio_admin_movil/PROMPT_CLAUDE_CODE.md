# Prompt para Claude Code

Pega esto en Claude Code, con la terminal abierta en la raíz del proyecto Django
y esta carpeta (`redisenio_admin_movil/`) copiada dentro del proyecto.

---

Vas a rediseñar la experiencia MÓVIL del panel de administración de mi sistema Django de pedidos para un asadero (marca "Brasas"). Es un proyecto que ya funciona y está en uso; NO cambies la lógica de negocio, los modelos ni los permisos, solo la capa de presentación y una corrección puntual del cálculo de gastos.

## Material que ya tienes
En `redisenio_admin_movil/`:
- `README.md`: resumen y mapa de archivos.
- `reference_mockup/*.dc.html`: 6 pantallas de referencia visual (390×844). Léelas como HTML para ver estructura, colores, tamaños y textos. Son la fuente de verdad del diseño.
- `snippets/`: código listo para adaptar (CSS, JS, filtro `dinero`, parciales de template, lógica de gastos). Es un punto de partida, NO lo pegues a ciegas: los nombres de variables, URLs y campos son genéricos y están marcados con `ADAPTAR`.

## Antes de tocar nada
1. Explora el proyecto: encuentra las vistas y templates del panel admin (reportes día/semana/mes, "Qué se vendió", Bebidas/inventario, Órdenes, Gastos y ganancia, Gastos fijos, Margen), las URLs, los modelos (`Orden`, `DetalleOrden`, `Producto`, `Gasto`, gastos fijos) y cómo se cambia hoy de pestaña.
2. Resúmeme en pocas líneas qué encontraste y qué archivos vas a modificar. Si algo no coincide con los snippets, adapta los snippets al proyecto, no al revés.
3. Crea una rama `rediseno-admin-movil`.

## Cambios a implementar (en este orden, un commit por paso)
1. **Formato y tildes.** Agrega el filtro `dinero` (`-$2.693,30`, `$59,70`) y úsalo en todo el panel. Corrige textos sin tilde: Día, Qué se vendió, Órdenes, Pérdida, Administración→Admin. Pluralización correcta ("1 ud", "5 uds").
2. **Lógica de gastos.** Aplica `snippets/python/gastos_logica.py`: hoy se comparan gastos de todo el mes contra ventas de un solo día y sale "-4511% de margen". Debe mostrar resultado del mes, cobertura de gastos ("Faltan $X en ventas para cubrir los gastos del mes"), aviso de datos parciales (menos de 7 días de datos) y NO mostrar el margen % hasta tener datos suficientes. Separa claramente "Mes en curso" de "Día seleccionado". Reutiliza tu función actual que suma gastos; no dupliques cálculos.
3. **Base móvil y navegación.** Viewport con `viewport-fit=cover`, fuentes Anton + Work Sans, `admin_movil.css`, `admin_movil.js`. Reemplaza las 7+ pestañas con scroll horizontal por barra inferior fija de 5 ítems: Resumen · Ventas · Inventario · Gastos · Más. Ventas agrupa "Qué se vendió" + "Órdenes"; Gastos agrupa Resumen/Diarios/Fijos/Margen como sub-pestañas. "Más" abre un menú con Exportar Excel y Salir (y cualquier otra sección que exista hoy y no encaje: no elimines funcionalidad).
4. **Encabezado y filtro compactos.** Filtro Día/Semana/Mes + navegación de fecha en un bloque sticky; Exportar Excel pasa a ícono en el header; el filtro de periodo se oculta en Inventario. Áreas táctiles mínimas de 44×44 px.
5. **Tablas → tarjetas.** Órdenes como tarjetas (mesa, hora, total, detalle); "Qué se vendió" como acordeón `<details>` por categoría; Inventario de bebidas como tarjeta por producto donde el switch "Llevar conteo" muestra los campos de stock y precio de compra; botón "Guardar inventario" sticky sobre la barra inferior. Optimiza consultas con `select_related`/`prefetch_related` para no crear N+1.
6. **Gastos: botón flotante y hoja inferior.** "+ Gasto" (solo visible en el grupo Gastos) abre un `<dialog>` con el formulario (fecha, categoría, descripción, monto con `inputmode="decimal"`). La lista de gastos queda primero en la sub-pestaña Diarios. Iguala el estilo del input "Día del mes" de gastos fijos al resto.
7. **Detalles.** Quitar "sin periodo anterior" repetido (mostrar solo si hay comparación real), KPIs de Resumen en una fila de 3, nombres largos a dos líneas sin truncar.

## Reglas
- Sin dependencias nuevas: HTML/CSS/JS vanilla y Django puro. Conserva la paleta (navy #1B2A4E, mostaza #F2A63B, crema #F5EEE2) y las fuentes.
- Mobile-first (390 px de ancho). En escritorio no debe romperse; no hace falta rediseñarlo.
- Accesibilidad: `<button>`/`<a>`/`<label>` reales, `aria-label` en botones de solo ícono, contraste legible, foco visible.
- No cambies roles, login, permisos ni la exportación a Excel (solo su ubicación en la UI).
- No borres archivos ni datos. Si necesitas una migración, dime antes de crearla (no debería hacer falta).
- Si algo es ambiguo, decide con criterio, déjalo anotado en el commit y sigue; pregúntame solo si algo bloquea de verdad.

## Verificación al final
- `python manage.py check` y los tests existentes.
- Levanta el servidor y revisa con datos reales: cada grupo de la barra inferior, sub-pestañas, filtro de fecha, switch de inventario, hoja de "+ Gasto" (crea un gasto de prueba y bórralo después), y que el resumen de gastos ya no muestre márgenes absurdos.
- Dime qué probaste, qué no pudiste probar y qué campos/URLs tuviste que adaptar.
