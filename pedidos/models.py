from django.db import models
from django.utils import timezone


class Mesa(models.Model):
    numero = models.IntegerField(unique=True)

    def __str__(self):
        return f"Mesa {self.numero}"

    def tiene_orden_abierta(self):
        return self.orden_set.filter(estado="abierta").exists()


class Producto(models.Model):
    CATEGORIAS = [
        ("combos", "Combos"),
        ("pollo", "Pollo"),
        ("acompanamientos", "Acompañamientos"),
        ("bebidas", "Bebidas"),
        ("gaseosas", "Gaseosas"),
    ]

    PIEZAS_POLLO = ["Pechuga", "Cadera", "Muslo", "Pierna"]

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

    def __str__(self):
        return self.nombre

    def permite_cambio(self):
        return bool(self.acompanamiento_incluido)

    def es_cambio_valido(self):
        return self.precio_cambio is not None

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


class Orden(models.Model):
    ESTADOS = [
        ("abierta", "Abierta"),
        ("enviada", "Enviada a cocina"),
        ("entregada", "Entregada"),
        ("cerrada", "Cerrada"),
    ]

    mesa = models.ForeignKey(Mesa, on_delete=models.CASCADE)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="abierta")
    creado = models.DateTimeField(default=timezone.now)
    enviado_a_cocina = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Orden #{self.id} - Mesa {self.mesa.numero}"

    def total(self):
        return sum(item.subtotal() for item in self.items.all())

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

    def __str__(self):
        return f"{self.cantidad}x {self.descripcion()}"

    def descripcion(self):
        """Nombre para ticket de cocina: '1/4 Pollo (Pierna) · cambio: Moroclo'."""
        texto = self.producto.nombre
        if self.notas:
            texto += f" ({self.notas})"
        if self.acompanamiento:
            texto += f" · sin {self.producto.acompanamiento_incluido.lower()}, con {self.acompanamiento.nombre}"
        return texto

    def precio_unitario(self):
        precio = self.producto.precio
        if self.acompanamiento and self.acompanamiento.precio_cambio is not None:
            precio += self.acompanamiento.precio_cambio
        return precio

    def subtotal(self):
        return self.precio_unitario() * self.cantidad


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
