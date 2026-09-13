# Sistema de pedidos - Brasas

Proyecto Django: mesero toma pedidos desde tablet, cocina los ve en otra tablet,
y el dueño/admin controla todo desde reportes. Fase 1 completa (sin SRI ni correos).

## Como correrlo (primera vez)

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

pip install django openpyxl

python manage.py migrate
python manage.py cargar_datos_ejemplo       # crea 5 mesas y carga el menu real
python manage.py cargar_menu_brasas         # (solo el menu: combos, pollo, acompañamientos, bebidas, gaseosas)
python manage.py crear_roles_y_usuarios     # crea los 3 roles + 1 usuario de prueba por rol
```

**Usuarios de prueba creados** (cambialos antes de usar en el restaurante real):
| Usuario | Password | Rol |
|---|---|---|
| mesero1 | mesero123 | Mesero |
| cocina1 | cocina123 | Cocina |
| admin1  | admin123  | Admin |

Para crear usuarios reales: entra a `/admin/` (con `python manage.py createsuperuser` primero),
crea el usuario y asignale el grupo correspondiente (Mesero / Cocina / Admin).

## Correr en tu PC (localhost)
```bash
python manage.py runserver
```
Abre http://127.0.0.1:8000/ -> te pide login, luego te manda segun tu rol:
- Mesero -> elegir mesa
- Cocina -> panel de cocina
- Admin -> reportes

## Correr para que las tablets conecten por WiFi
```bash
python manage.py runserver 0.0.0.0:8000
```
1. Busca la IP local de tu PC: `ipconfig` (Windows) y busca "IPv4"
2. En cada tablet, abre Chrome y entra a `http://TU_IP:8000/`
3. Todas las tablets y la PC deben estar en la MISMA red WiFi

## Fotos de productos
Las fotos actuales son de Wikimedia Commons (licencia libre, ver `media/productos/CREDITOS.md`) y son
referenciales. Para poner la foto real del plato: `/admin/` > Productos > el producto > campo "imagen"
(una foto con la tablet sirve; ideal horizontal, 800px de ancho aprox.).

## Pantalla completa en las tablets
- Boton **⛶** en la cabecera (mesero y cocina): pantalla completa del navegador. Mientras esta
  activa, los enlaces y formularios se cargan con `fetch` y se reemplaza el contenido en sitio
  ("navegacion suave", script en `base.html`), porque el navegador sale de pantalla completa en
  cualquier navegacion real. Fuera de pantalla completa todo navega normal. Reglas para nuevas
  pantallas: enviar formularios por JS con `form.requestSubmit()` (no `.submit()`), recargar con
  `recargar()` (no `location.reload()`), y marcar descargas con `data-nav="normal"`.
- **Recomendado:** en Chrome de la tablet, con la app abierta, menu ⋮ > "Agregar a pantalla de inicio"
  (o "Instalar app"). Gracias al `manifest.webmanifest` se abre como app a pantalla completa
  **siempre**, sin barra de direcciones, con icono propio. En ese modo el boton ⛶ se oculta solo.

## Rutas principales
- `/login/` -> pantalla de ingreso (todas las rutas de abajo requieren estar logueado con el rol correcto)
- `/` -> mesero elige mesa
- `/mesa/<id>/` -> menu de esa mesa (agregar productos; la barra de abajo se despliega para ver
  el detalle, cambiar cantidades con - / + y eliminar lineas marcadas)
- `/cocina/` -> panel de cocina (pedidos pendientes + marcar productos agotados)
- `/reportes/` -> solo Admin: dashboard (ingresos, ordenes, ticket, productos vendidos con variacion vs el
  periodo anterior; ventas por hora/dia, mas vendidos, "que se vendio" por categoria, inventario editable
  de bebidas/gaseosas, todas las ordenes del periodo; exportar Excel)
- `/reportes/stock/` (POST) -> guarda el inventario editado en el dashboard
- `/admin/` -> panel de Django (gestionar productos, mesas, usuarios, ver ordenes)

## Como esta armada la logica

**Modelos** (`pedidos/models.py`):
- `Mesa` - simple, solo numero
- `Producto` - tiene `disponible` (on/off manual de cocina), `controla_stock` + `stock` (gaseosas: el admin
  carga las unidades en `/admin/` > Productos, columna editable "stock"), `es_combo` + `combo_incluye`
- `Orden` - una orden abierta por mesa, pasa a `enviada` al confirmar, a `entregada` cuando cocina la marca lista
- `DetalleOrden` - cada item dentro de una orden
- `RegistroAccion` - log de acciones de mesero/cocina, visible en `/reportes/` y en `/admin/`

**Disponibilidad de un producto** = `disponible == True` Y (si `controla_stock`, que `stock > 0`)
Esta regla vive en `Producto.esta_disponible()`.

**Roles** (Django auth + Group, sin librerias externas):
- Los 3 grupos son "Mesero", "Cocina", "Admin" (se crean con `crear_roles_y_usuarios`)
- Cada vista esta protegida con `@login_required` + `@user_passes_test(es_mesero/es_cocina/es_admin)`
- Un superusuario (`createsuperuser`) pasa todos los checks automaticamente

**Registro de acciones:** se guarda automaticamente cuando el mesero confirma una orden,
y cuando cocina marca una orden lista, cambia disponibilidad o pone un temporizador.
Se consulta en `/admin/pedidos/registroaccion/` (ya no aparece en el dashboard).

**Dashboard:** `/reportes/?rango=dia|semana|mes&fecha=YYYY-MM-DD` (o `YYYY-MM`) — cualquier periodo,
pasado o futuro, con flechas anterior/siguiente y selector de fecha; sin `fecha` es hoy. Indicadores con
variacion vs el periodo anterior del mismo largo, ventas por hora (dia) o por dia (semana/mes), mas vendidos,
"que se vendio" (unidades por producto agrupadas por categoria; los acompañamientos usados como cambio de
plato se cuentan aparte), inventario de bebidas/gaseosas (switch "controlar stock" + unidades + botones
+6/+12/+24, guarda en `actualizar_stock`) y la tabla de todas las ordenes del periodo. Graficos en SVG sin
librerias (script en `reportes.html`). Cuenta solo ordenes `entregada`/`cerrada`.

**Exportar a Excel:** `/reportes/exportar/?rango=dia|semana|mes` descarga un `.xlsx` con
detalle fila por fila (hoja "Ventas") y un resumen agregado por producto (hoja "Resumen por producto").

**Tiempo real (sin WebSockets, con polling):**
- La tablet de mesero revisa `/api/disponibilidad/` cada 2.5 segundos (disponibilidad + temporizadores)
- La tablet de cocina revisa pedidos nuevos cada 8 segundos

**Temporizadores de cocina ("faltan X min"):** en `/cocina/` la seccion de disponibilidad esta
agrupada por categoria; al tocar un producto sale una hoja con "Marcar agotado/disponible" y
botones de 5 / 10 / 15 / 20 / 25 min (un toque, sin escribir). Se guarda en `Producto.listo_en`;
el mesero ve "⏱ faltan X min" sobre la tarjeta y el conteo baja solo. Vencido, desaparece.
"Quitar temporizador" lo borra antes. El producto sigue pudiendo pedirse mientras corre el tiempo.

**Al confirmar una orden:** se descuenta el stock de las gaseosas automaticamente.

**"Mejora tu combo" (cambio de acompañamiento):**
- El pollo trae incluido "Papas fritas, patacones y maduros" (`Producto.acompanamiento_incluido`).
  En el modal el mesero elige: quedarse con lo incluido, o cambiarlo por un acompañamiento premium
  (Chauchitas / Moroclo / Moro Chicoloso, los que tienen `precio_cambio`).
- Si se cambia, la linea cobra `precio del plato + precio_cambio` ($1.50) en vez del precio normal
  del acompañamiento ($2.25). Se guarda en `DetalleOrden.acompanamiento`.
- Si el cliente quiere lo incluido Y ADEMAS una porcion extra (de cualquier acompañamiento), se
  agrega desde la pestaña "Acompañamientos" y se cobra a su precio normal.
- Maduro, Patacones, arroz con menestra y Moro tradicional no tienen `precio_cambio`: solo van
  como porcion extra. Para habilitar/quitar un cambio: `/admin/` > Productos > `precio_cambio`.
- Cocina ve la linea como "1/4 Pollo (Pierna) · sin papas fritas, patacones y maduros → Moroclo".

## Lo que falta (fase 2, ya con precio hablado con el dueño)
- Facturacion electronica SRI real (via Factuplan, reusando estructura del microservicio
  simulado de Tecnogamer) — regla acordada: factura automatica a "Consumidor Final" por
  default, y solo pide datos si el cliente los pide expresamente
- Envio de la factura por correo (reusar configuracion de SendGrid de Tecnogamer)
- Decision pendiente: si el combo descuenta stock de sus componentes (por ahora NO lo hace)
- Despliegue en Railway (cuando ya este probado en local con el dueño)
# Restaurante
# Restaurante
# will-
