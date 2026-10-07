"""
Conexión asíncrona a MongoDB Atlas con Motor.

El cliente se abre UNA vez al arrancar la aplicación y se cierra al apagarla.
Abrir uno por petición es el error clásico: cada conexión a Atlas cuesta un
handshake TLS y el cluster tiene un tope de conexiones simultáneas; con tráfico
real se agota en minutos. Por eso el ciclo de vida se maneja en el lifespan de
FastAPI (ver main.py) y aquí solo se guarda la referencia.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

# Referencias de proceso. Se llenan en el arranque y se vacían al apagar.
_cliente: AsyncIOMotorClient | None = None
_base: AsyncIOMotorDatabase | None = None


async def conectar(uri: str, nombre_base: str) -> AsyncIOMotorDatabase:
    """
    Abre el cliente y verifica que el cluster responda.

    El `ping` es deliberado: Motor conecta de forma perezosa, así que sin él la
    aplicación arrancaría "bien" con una cadena inválida y el primer error
    aparecería hasta la primera petición de un usuario. Es preferible no
    arrancar.
    """
    global _cliente, _base
    _cliente = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=10_000)
    await _cliente.admin.command("ping")
    _base = _cliente[nombre_base]
    await _crear_indices(_base)
    return _base


async def desconectar() -> None:
    """Cierra el cliente al apagar la aplicación."""
    global _cliente, _base
    if _cliente is not None:
        _cliente.close()
    _cliente = None
    _base = None


def obtener_base() -> AsyncIOMotorDatabase:
    """
    Da la base ya conectada, para inyectarla en las rutas con Depends().

    Si alguien la pide antes de que el lifespan haya corrido, truena con un
    mensaje claro en vez de devolver None y fallar más adelante con un
    AttributeError incomprensible.
    """
    if _base is None:
        raise RuntimeError(
            "La base de datos no está conectada. "
            "¿Se está usando la app sin pasar por el lifespan de FastAPI?"
        )
    return _base


async def _crear_indices(base: AsyncIOMotorDatabase) -> None:
    """
    Índices que la aplicación necesita para ser correcta, no solo rápida.

    El de `rfc` es único: dos clientes con el mismo RFC son el mismo cliente, y
    dejar que se dupliquen rompería la proyección (contaría su cartera dos
    veces). Vale más que la base lo impida a confiar en que la validación de
    la aplicación nunca falle.
    """
    await base.clientes.create_index("rfc", unique=True)
    await base.facturas.create_index([("cliente_id", 1), ("estado", 1)])
    await base.facturas.create_index("fecha_vencimiento")
