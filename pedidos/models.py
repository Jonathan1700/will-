import json
from decimal import Decimal

from django.db import models
from django.utils import timezone


class Mesa(models.Model):
    numero = models.IntegerField(unique=True)

    def __str__(self):
        return f"Mesa {self.numero}"

    def tiene_orden_abierta(self):
        return self.orden_set.filter(estado="abierta", es_venta_directa=False).exists()


class Producto(models.Model):
    CATEGORIAS = [
        ("combos", "Combos"),
        ("pollo", "Pollo"),
        ("acompanamientos", "Acompañamientos"),
        ("bebidas", "Bebidas"),
        ("gaseosas", "Gaseosas"),
    ]

    # opciones del temporizador de cocina (minutos): un toque, sin escribir
    TEMPORIZADORES = [5, 10, 15, 20, 25]

    nombre = models.CharField(max_length=100)
    precio = models.DecimalField(max_digits=6, decimal_places=2)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS)

    # foto del plato: se sube desde /admin/, si no hay se muestra un emoji
    imagen = models.FileField(upload_to="productos/", blank=True)

    # disponibilidad manual: cocina la prende/apaga (ej: se acabaron las papas)
    disponible = models.BooleanField(default=True)

    # temporizador de cocina: "faltan X min para que salgan las papas". El mesero lo ve en su
    # tablet en tiempo real. Se calcula al vuelo; vencido, se ignora.
    listo_en = models.DateTimeField(null=True, blank=True)

    # stock: solo aplica a gaseosas (botella/lata); el admin lo actualiza en /admin/
    controla_stock = models.BooleanField(default=False)
    stock = models.IntegerField(null=True, blank=True)

    # combos: descripcion de que incluye (sin descontar stock de componentes por ahora)
    es_combo = models.BooleanField(default=False)
    combo_incluye = models.CharField(max_length=250, blank=True)

    # piezas de pollo (1/8, 1/4): el mesero debe elegir pechuga/cadera/muslo/pierna
    requiere_pieza = models.BooleanField(default=False)

    # platos: lo que trae por defecto y que el cliente puede cambiar (ej: "Papas fritas").
    # Si esta vacio, el plato no permite cambiar acompañamiento.
    acompanamiento_incluido = models.CharField(max_length=100, blank=True)

    # acompañamientos: precio cuando REEMPLAZA lo incluido en un plato ("Mejora tu combo").
    # Vacio = no se puede usar como cambio. Pedido aparte se cobra a `precio` normal.
    precio_cambio = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # lista (separada por comas) de los acompañamientos incluidos que SI se pueden quitar
    # individualmente sin costo, ej: "Papas fritas,Patacones,Maduro". Vacio = no aplica
    # (ej. "Arroz y menestra" es un solo plato, no se puede separar en partes).
    opciones_incluidas = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.nombre

    def permite_cambio(self):
        return bool(self.acompanamiento_incluido)

    def es_cambio_valido(self):
        return self.precio_cambio is not None

    def lista_opciones_incluidas(self):
        return [o.strip() for o in self.opciones_incluidas.split(",") if o.strip()]

    def tiene_opciones_incluidas(self):
        return len(self.lista_opciones_incluidas()) > 1

    def tiene_variantes(self):
        return self.variantes.exists()

    def variantes_json(self):
        """Grupos de variantes en JSON, para que el modal del mesero los arme al vuelo."""
        return json.dumps([
            {"nombre": v.nombre, "opciones": v.lista_opciones()}
            for v in self.variantes.all()
        ])

    def esta_disponible(self):
        """Regla unica: disponible manualmente Y (si controla stock) con stock > 0."""
        if not self.disponible:
            return False
        if self.controla_stock and (self.stock or 0) <= 0:
            return False
        return True

    def stock_bajo(self, umbral=3):
        return self.controla_stock and self.stock is not None and 0 < self.stock <= umbral

    def segundos_restantes(self):
        """Segundos que faltan del temporizador de cocina (0 si no hay o ya vencio)."""
        if not self.listo_en:
            return 0
        return max(0, int((self.listo_en - timezone.now()).total_seconds()))

    def minutos_restantes(self):
        """Minutos redondeados hacia arriba, para mostrar 'faltan 5 min'."""
        return -(-self.segundos_restantes() // 60)


class PiezaPollo(models.Model):
    """Presas de pollo (pechuga, ala, pierna...) que cocina tiene listas para servir.
    El mesero solo puede elegir una presa con stock > 0."""
    nombre = models.CharField(max_length=30, unique=True)
    orden = models.IntegerField(default=0)
    stock = models.IntegerField(default=0)

    class Meta:
        ordering = ["orden", "id"]

    def __str__(self):
        return self.nombre


class TipoMenestra(models.Model):
    """Frejol o lenteja: cocina avisa cual hay, para el 'Clasico arroz con menestra'."""
    nombre = models.CharField(max_length=20, unique=True)
    disponible = models.BooleanField(default=True)
    orden = models.IntegerField(default=0)

    class Meta:
        ordering = ["orden", "id"]

    def __str__(self):
        return self.nombre


class VarianteProducto(models.Model):
    """Grupo de eleccion unica dentro de un producto, ej: 'Menestra' -> Lenteja/Frejol.
    No cambia el precio, solo le avisa a cocina que preparacion quiere el cliente."""
    producto = models.ForeignKey(Producto, related_name="variantes", on_delete=models.CASCADE)
    nombre = models.CharField(max_length=40)
    opciones = models.CharField(max_length=200)
    orden = models.IntegerField(default=0)

    class Meta:
        ordering = ["orden", "id"]

    def __str__(self):
        return f"{self.producto.nombre} - {self.nombre}"

    def lista_opciones(self):
        return [o.strip() for o in self.opciones.split(",") if o.strip()]


class Orden(models.Model):
    ESTADOS = [
        ("abierta", "Abierta"),
        ("enviada", "Enviada a cocina"),
        ("entregada", "Entregada"),
        ("cerrada", "Cerrada"),
    ]

    RECARGO_PARA_LLEVAR = Decimal("0.25")
    # el envase se cobra por cada plato principal (pollo/combos), no por bebidas ni acompañamientos sueltos
    CATEGORIAS_CON_ENVASE = ("pollo", "combos")

    mesa = models.ForeignKey(Mesa, on_delete=models.CASCADE)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="abierta")
    creado = models.DateTimeField(default=timezone.now)
    enviado_a_cocina = models.DateTimeField(null=True, blank=True)

    # true = pedido "de mostrador" (acompañamiento/bebida/gaseosa) que se cobra al
    # instante y nunca pasa por la pantalla de cocina
    es_venta_directa = models.BooleanField(default=False)

    # para llevar suma un recargo fijo (envases); para servir en mesa es precio normal
    para_llevar = models.BooleanField(default=False)

    def __str__(self):
        return f"Orden #{self.id} - Mesa {self.mesa.numero}"

    def unidades_con_envase(self):
        """Cuantos platos (pollo/combos) hay en el pedido: cada uno necesita su envase."""
        return sum(
            item.cantidad for item in self.items.all()
            if item.producto.categoria in self.CATEGORIAS_CON_ENVASE
        )

    def total(self):
        total = sum(item.subtotal() for item in self.items.all())
        if self.para_llevar:
            total += self.RECARGO_PARA_LLEVAR * self.unidades_con_envase()
        return total

    def minutos_en_espera(self):
        if not self.enviado_a_cocina:
            return 0
        delta = timezone.now() - self.enviado_a_cocina
        return int(delta.total_seconds() // 60)


class DetalleOrden(models.Model):
    orden = models.ForeignKey(Orden, related_name="items", on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.IntegerField(default=1)
    notas = models.CharField(max_length=200, blank=True)

    # acompañamiento que reemplaza al incluido del plato (se cobra a precio_cambio, no a precio)
    acompanamiento = models.ForeignKey(
        Producto, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    # cuales de los `producto.opciones_incluidas` NO quiere el cliente (separados por coma),
    # ej: "Maduro" o "Patacones,Maduro". No cambia el precio, solo avisa a cocina.
    sin_acompanamientos = models.CharField(max_length=200, blank=True)

    # eleccion de cada `producto.variantes`, ej: "Arroz:Moro|Menestra:Frejol"
    variantes_elegidas = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.cantidad}x {self.descripcion()}"

    def lista_variantes_elegidas(self):
        pares = []
        for parte in self.variantes_elegidas.split("|"):
            if ":" in parte:
                grupo, opcion = parte.split(":", 1)
                pares.append((grupo.strip(), opcion.strip()))
        return pares

    def descripcion(self):
        """Nombre para ticket de cocina: '1/4 Pollo (Pierna) · cambio: Moroclo'."""
        texto = self.producto.nombre
        if self.notas:
            texto += f" ({self.notas})"
        if self.acompanamiento:
            texto += f" · sin {self.producto.acompanamiento_incluido.lower()}, con {self.acompanamiento.nombre}"
        if self.sin_acompanamientos:
            texto += f" · sin {self.sin_acompanamientos.lower()}"
        for grupo, opcion in self.lista_variantes_elegidas():
            texto += f" · {grupo}: {opcion}"
        return texto

    def precio_unitario(self):
        precio = self.producto.precio
        if self.acompanamiento and self.acompanamiento.precio_cambio is not None:
            precio += self.acompanamiento.precio_cambio
        return precio

    def subtotal(self):
        return self.precio_unitario() * self.cantidad


class Gasto(models.Model):
    """Gasto de materia prima/insumos que el admin carga a mano desde el dashboard
    (pollos, papas, vegetales, aceite, condimentos, bebidas para reventa, etc.),
    para comparar contra los ingresos del mismo periodo."""
    CATEGORIAS = [
        ("pollo", "Pollo"),
        ("papa", "Papa"),
        ("vegetales", "Vegetales"),
        ("aceite", "Aceite"),
        ("condimentos", "Condimentos"),
        ("bebidas", "Bebidas y gaseosas"),
        ("otros", "Otros"),
    ]

    fecha = models.DateField(default=timezone.localdate)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default="otros")
    descripcion = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=8, decimal_places=2)
    creado = models.DateTimeField(default=timezone.now)
    usuario = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-fecha", "-creado"]

    def __str__(self):
        return f"{self.fecha} - {self.descripcion} (${self.monto})"


class RegistroAccion(models.Model):
    """Log de acciones de mesero y cocina, visible para el admin en /admin/."""
    usuario = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    accion = models.CharField(max_length=250)
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        nombre = self.usuario.username if self.usuario else "desconocido"
        return f"{nombre} - {self.accion} - {self.fecha:%d/%m %H:%M}"
