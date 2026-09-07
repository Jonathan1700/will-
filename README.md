# Sistema de pedidos - Asadero Don Beto (nombre placeholder)

Proyecto Django: mesero toma pedidos desde tablet, cocina los ve en otra tablet,
y el dueño/admin controla todo desde reportes. Fase 1 completa (sin SRI ni correos).

## Como correrlo (primera vez)

```bash
cd restaurante
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

pip install django openpyxl

python manage.py migrate
python manage.py cargar_datos_ejemplo       # crea 8 mesas y 10 productos de prueba
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

## Rutas principales
- `/login/` -> pantalla de ingreso (todas las rutas de abajo requieren estar logueado con el rol correcto)
- `/` -> mesero elige mesa
- `/mesa/<id>/` -> menu de esa mesa (agregar productos, ver carrito)
- `/cocina/` -> panel de cocina (pedidos pendientes + marcar productos agotados)
- `/reportes/` -> solo Admin: totales del dia/semana/mes, mas vendidos, registro de acciones, exportar Excel
- `/admin/` -> panel de Django (gestionar productos, mesas, usuarios, ver ordenes)

## Como esta armada la logica

**Modelos** (`pedidos/models.py`):
- `Mesa` - simple, solo numero
- `Producto` - tiene `disponible` (on/off manual de cocina), `controla_stock` + `stock` (solo bebidas), `es_combo` + `combo_incluye`
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
y cuando cocina marca una orden lista o cambia la disponibilidad de un producto.
El admin lo ve en `/reportes/` (ultimas 30) o completo en `/admin/pedidos/registroaccion/`.

**Reportes:** `/reportes/?rango=dia|semana|mes` — total de ordenes, ingresos, ticket promedio,
top 10 productos mas vendidos. Cuenta solo ordenes en estado `entregada` o `cerrada`.

**Exportar a Excel:** `/reportes/exportar/?rango=dia|semana|mes` descarga un `.xlsx` con
detalle fila por fila (hoja "Ventas") y un resumen agregado por producto (hoja "Resumen por producto").

**Tiempo real (sin WebSockets, con polling):**
- La tablet de mesero revisa `/api/disponibilidad/` cada 8 segundos
- La tablet de cocina se recarga sola cada 8 segundos

**Al confirmar una orden:** se descuenta el stock de las bebidas automaticamente.

## Lo que falta (fase 2, ya con precio hablado con el dueño)
- Facturacion electronica SRI real (via Factuplan, reusando estructura del microservicio
  simulado de Tecnogamer) — regla acordada: factura automatica a "Consumidor Final" por
  default, y solo pide datos si el cliente los pide expresamente
- Envio de la factura por correo (reusar configuracion de SendGrid de Tecnogamer)
- Decision pendiente: si el combo descuenta stock de sus componentes (por ahora NO lo hace)
- Despliegue en Railway (cuando ya este probado en local con el dueño)
# Restaurante
# Restaurante
