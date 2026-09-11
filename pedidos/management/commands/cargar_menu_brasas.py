from django.core.management.base import BaseCommand
from pedidos.models import Producto


# Menu "Brasas" transcrito de la carta fisica. Se puede correr varias veces:
# crea lo que falta y actualiza precios/descripciones de lo que ya existe (por nombre).
# "Mejora tu combo": el plato trae papas fritas, patacones y maduros. Si el cliente los cambia
# por uno de los 3 acompañamientos premium paga $1.50 en vez de $2.25. Si quiere una porcion
# extra (sin renunciar a lo incluido) se agrega desde la pestaña Acompañamientos a precio normal.
PRECIO_CAMBIO = 1.50

INCLUIDO_POLLO = "Papas fritas, patacones y maduros"
INCLUYE_PAPAS = "Papas fritas, patacones, maduros, ensalada y cremas de la casa"
INCLUYE_ARROZ = "Arroz y menestra, ensalada y cremas de la casa"

POLLO = [
    dict(nombre="1 Pollo a la brasa", precio=12.99, combo_incluye=INCLUYE_PAPAS,
         acompanamiento_incluido=INCLUIDO_POLLO),
    dict(nombre="1/2 Pollo a la brasa", precio=6.50, combo_incluye=INCLUYE_PAPAS,
         acompanamiento_incluido=INCLUIDO_POLLO),
    dict(nombre="1/4 Pollo a la brasa (pechuga)", precio=3.75, combo_incluye=INCLUYE_PAPAS,
         acompanamiento_incluido=INCLUIDO_POLLO),
    dict(nombre="1/4 Pollo a la brasa (pierna)", precio=3.25, combo_incluye=INCLUYE_PAPAS,
         acompanamiento_incluido=INCLUIDO_POLLO),
]

# los 1/8 van en la pestaña "Combos"
COMBOS = [
    dict(nombre="1/8 Pollo a la brasa con arroz y menestra", precio=2.99, combo_incluye=INCLUYE_ARROZ,
         acompanamiento_incluido="Arroz y menestra", requiere_pieza=True, es_combo=True),
    dict(nombre="1/8 Pollo a la brasa", precio=2.75, combo_incluye=INCLUYE_PAPAS,
         acompanamiento_incluido=INCLUIDO_POLLO, requiere_pieza=True, es_combo=True),
]

# gaseosas: el catalogo no trae precio, se asume $1.50 (cambialo en /admin/)
PRECIO_GASEOSA = 1.50

BEBIDAS = [
    dict(nombre="Naranja", precio=1.50),
    dict(nombre="Chicha morada", precio=1.25),
    dict(nombre="Agua de coco", precio=1.50),
    dict(nombre="Jugo de naranja", precio=1.00),
    dict(nombre="Agua normal", precio=0.50),
]

# con control de stock: el admin pone las unidades en /admin/ y se descuentan al confirmar orden
GASEOSAS = [
    dict(nombre="Coca-Cola", precio=PRECIO_GASEOSA),
    dict(nombre="Fioravanti", precio=PRECIO_GASEOSA),
    dict(nombre="Fanta", precio=PRECIO_GASEOSA),
    dict(nombre="Sprite", precio=PRECIO_GASEOSA),
    dict(nombre="Inca Kola", precio=PRECIO_GASEOSA),
]

ACOMPANAMIENTOS = [
    # premium: se pueden usar como cambio (precio_cambio)
    dict(nombre="Chauchitas de la casa", precio=2.25, precio_cambio=PRECIO_CAMBIO,
         combo_incluye="Papas chauchas salteadas en mantequilla de ajo, hierbas finas y queso parmesano"),
    dict(nombre="Moroclo", precio=2.25, precio_cambio=PRECIO_CAMBIO,
         combo_incluye="Arroz con choclo dulce envuelto en una mezcla derretida de quesos"),
    dict(nombre="Moro Chicoloso", precio=2.25, precio_cambio=PRECIO_CAMBIO,
         combo_incluye="Arroz cremoso cocinado con lenteja y fundido queso criollo"),
    # basicos: solo como porcion extra a precio normal
    dict(nombre="Maduro", precio=1.75, precio_cambio=None,
         combo_incluye="Tajadas de platano maduro cocidas con un toque de queso fresco"),
    dict(nombre="Patacones", precio=1.75, precio_cambio=None,
         combo_incluye="Porcion de rodajas de platano verde, doradas y crocantes"),
    dict(nombre="Clasico arroz con menestra", precio=1.75, precio_cambio=None,
         combo_incluye="Arroz blanco con menestra de frijol o lenteja"),
    dict(nombre="Moro Tradicional", precio=1.75, precio_cambio=None,
         combo_incluye="Arroz moro con refrito criollo y menestra"),
]


class Command(BaseCommand):
    help = "Carga el menu real 'Brasas': combos, pollo, acompañamientos (cambio $1.50), bebidas y gaseosas"

    def handle(self, *args, **kwargs):
        creados = actualizados = 0

        grupos = [
            (COMBOS, dict(categoria="combos")),
            (POLLO, dict(categoria="pollo")),
            (ACOMPANAMIENTOS, dict(categoria="acompanamientos")),
            (BEBIDAS, dict(categoria="bebidas")),
            (GASEOSAS, dict(categoria="gaseosas", controla_stock=True)),
        ]
        for lista, extra in grupos:
            for datos in lista:
                datos = dict(datos, **extra)
                producto, creado = Producto.objects.update_or_create(nombre=datos["nombre"], defaults=datos)
                creados += creado
                actualizados += not creado
                # el stock no se toca si ya existe: solo se inicializa en 0 al crear
                if producto.controla_stock and producto.stock is None:
                    producto.stock = 0
                    producto.save()

        self.stdout.write(self.style.SUCCESS(
            f"Menu Brasas cargado: {creados} productos nuevos, {actualizados} actualizados.\n"
            f"Chauchitas, Moroclo y Moro Chicoloso tienen precio de cambio ${PRECIO_CAMBIO:.2f} "
            "(el resto viene incluido en el plato o se agrega como porcion extra a precio normal).\n"
            "Las gaseosas nuevas arrancan con stock 0 (aparecen agotadas): pon las unidades en /admin/ > Productos."
        ))
