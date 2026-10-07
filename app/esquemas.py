"""
Esquemas de Pydantic: la frontera entre lo que llega de fuera y lo que la
aplicación da por bueno.

Dos decisiones que se repiten en todo el archivo:

1. **El dinero se maneja en CENTAVOS enteros.** Un `float` no puede representar
   0.10 exacto, y sumar miles de importes en una simulación arrastra el error
   hasta que los totales dejan de cuadrar contra la factura. Entra y sale como
   pesos decimales para que sea cómodo de usar; por dentro siempre es `int`.

2. **Los esquemas de entrada y de salida son distintos.** Lo que el cliente
   puede mandar no es lo mismo que lo que la API devuelve: nadie debería poder
   fijar el `id` ni el saldo de una factura desde fuera.
"""

from datetime import date, datetime
from enum import Enum
from typing import Annotated, Any

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

# El _id de Mongo es un ObjectId; hacia fuera siempre viaja como texto.
IdMongo = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class EstadoFactura(str, Enum):
    """Una factura solo puede estar en uno de estos tres estados."""

    PENDIENTE = "pendiente"
    PARCIAL = "parcial"
    PAGADA = "pagada"


# ─────────────────────────── Clientes ───────────────────────────


class ClienteBase(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=120)
    rfc: str = Field(..., min_length=12, max_length=13)
    dias_credito: int = Field(
        default=30,
        ge=0,
        le=365,
        description="Días de crédito pactados con el cliente",
    )
    # Qué tan puntual es históricamente. Alimenta la simulación: un cliente que
    # siempre se atrasa 20 días no se proyecta igual que uno que paga al día.
    dias_atraso_promedio: float = Field(default=0.0, ge=0, le=365)
    variabilidad_atraso: float = Field(
        default=5.0,
        ge=0,
        le=180,
        description="Desviación estándar del atraso, en días",
    )

    @field_validator("rfc")
    @classmethod
    def rfc_en_mayusculas(cls, v: str) -> str:
        """
        El RFC se normaliza, no solo se valida.

        Si entrara tal cual, 'gso200317np9' y 'GSO200317NP9' serían dos
        clientes distintos y el índice único no los detendría.
        """
        limpio = v.strip().upper()
        if not limpio.isalnum():
            raise ValueError("El RFC solo puede tener letras y números")
        return limpio

    @field_validator("nombre")
    @classmethod
    def nombre_sin_espacios_sobrantes(cls, v: str) -> str:
        limpio = " ".join(v.split())
        if not limpio:
            raise ValueError("El nombre no puede ser solo espacios")
        return limpio


class ClienteCrear(ClienteBase):
    """Lo que se acepta al dar de alta un cliente."""


class ClienteActualizar(BaseModel):
    """
    Todo opcional: un PATCH cambia solo lo que manda.

    Se separa de ClienteBase a propósito; heredar de él obligaría a reenviar
    todos los campos para cambiar uno.
    """

    nombre: str | None = Field(default=None, min_length=3, max_length=120)
    dias_credito: int | None = Field(default=None, ge=0, le=365)
    dias_atraso_promedio: float | None = Field(default=None, ge=0, le=365)
    variabilidad_atraso: float | None = Field(default=None, ge=0, le=180)


class ClienteRespuesta(ClienteBase):
    # validation_alias y no alias: el alias normal se usaría TAMBIÉN al
    # serializar, y la API acabaría devolviendo "_id" en vez de "id". Así
    # entra como "_id" —que es como lo guarda Mongo— y sale como "id".
    model_config = ConfigDict(populate_by_name=True)

    id: IdMongo = Field(..., validation_alias="_id")
    creado_en: datetime


# ─────────────────────────── Facturas ───────────────────────────


class FacturaCrear(BaseModel):
    cliente_id: str = Field(..., description="Id del cliente que debe la factura")
    folio: str = Field(..., min_length=1, max_length=40)
    # Entra en pesos por comodidad; se convierte a centavos al guardar.
    importe: float = Field(..., gt=0, le=100_000_000, description="Importe en pesos")
    fecha_emision: date
    fecha_vencimiento: date

    @field_validator("folio")
    @classmethod
    def folio_normalizado(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("fecha_vencimiento")
    @classmethod
    def vence_despues_de_emitir(cls, v: date, info: Any) -> date:
        """
        Una factura no puede vencer antes de existir.

        Esta validación necesita dos campos a la vez, así que se hace aquí y no
        con un Field: Pydantic ya tiene `fecha_emision` validada cuando llega a
        este punto porque se declaró antes.
        """
        emision = info.data.get("fecha_emision")
        if emision is not None and v < emision:
            raise ValueError("La fecha de vencimiento no puede ser anterior a la de emisión")
        return v


class PagoRegistrar(BaseModel):
    """Un abono contra una factura."""

    importe: float = Field(..., gt=0, description="Importe del abono, en pesos")
    fecha: date = Field(default_factory=date.today)


class FacturaRespuesta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: IdMongo = Field(..., validation_alias="_id")
    cliente_id: IdMongo
    folio: str
    importe: float
    pagado: float
    saldo: float
    estado: EstadoFactura
    fecha_emision: date
    fecha_vencimiento: date
    dias_vencida: int = Field(
        default=0,
        description="Días transcurridos desde el vencimiento; 0 si aún no vence",
    )


# ─────────────────────────── Proyección ───────────────────────────


class ProyeccionSolicitud(BaseModel):
    """Parámetros de la simulación."""

    escenarios: int = Field(
        default=50_000,
        ge=1_000,
        description="Cuántos futuros simular. Más escenarios = más precisión y más CPU.",
    )
    horizontes_dias: list[int] = Field(
        default=[30, 60, 90],
        min_length=1,
        max_length=6,
        description="Cortes en días sobre los que se reporta lo cobrado",
    )

    @field_validator("horizontes_dias")
    @classmethod
    def horizontes_validos(cls, v: list[int]) -> list[int]:
        if any(d <= 0 for d in v):
            raise ValueError("Los horizontes deben ser días positivos")
        if len(set(v)) != len(v):
            raise ValueError("No repitas horizontes")
        return sorted(v)


class TramoProyeccion(BaseModel):
    """Lo que se espera cobrar al cumplirse cierto número de días."""

    dias: int
    esperado: float = Field(..., description="Promedio de todos los escenarios, en pesos")
    pesimista: float = Field(..., description="Percentil 10: solo 1 de cada 10 sale peor")
    optimista: float = Field(..., description="Percentil 90")
    porcentaje_cartera: float


class ProyeccionRespuesta(BaseModel):
    cartera_total: float
    facturas_consideradas: int
    escenarios: int
    tramos: list[TramoProyeccion]
    milisegundos_calculo: int = Field(
        ...,
        description="Cuánto tardó el cálculo. Es la evidencia de que es trabajo real de CPU.",
    )
    hilo: str = Field(
        ...,
        description="Nombre del hilo donde corrió. Si no dice MainThread, no bloqueó el servidor.",
    )


class RespuestaError(BaseModel):
    """Forma única de los errores, para que el frontend no adivine."""

    detalle: str
