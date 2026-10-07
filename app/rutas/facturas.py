"""
CRUD de facturas y registro de abonos.

El dinero se guarda en centavos enteros (ver esquemas.py). La conversión
pesos↔centavos ocurre solo en esta frontera, para que el resto del sistema
nunca vea un float.
"""

from datetime import UTC, date, datetime

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from ..db import obtener_base
from ..esquemas import EstadoFactura, FacturaCrear, FacturaRespuesta, PagoRegistrar

router = APIRouter(prefix="/api/facturas", tags=["facturas"])


def _a_object_id(id_texto: str, que: str) -> ObjectId:
    try:
        return ObjectId(id_texto)
    except (InvalidId, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe {que} {id_texto}",
        ) from exc


def _a_centavos(pesos: float) -> int:
    """Pesos a centavos, redondeando al centavo más cercano."""
    return int(round(pesos * 100))


def _vista(doc: dict) -> dict:
    """
    Traduce el documento de Mongo a lo que ve quien consume la API.

    Los saldos y los días vencidos se CALCULAN aquí en vez de guardarse: un
    campo `dias_vencida` almacenado queda desactualizado al día siguiente, y
    `saldo` guardado puede desincronizarse de importe − pagado.
    """
    importe = doc["importe_centavos"]
    pagado = doc.get("pagado_centavos", 0)
    saldo = importe - pagado
    vencimiento: date = doc["fecha_vencimiento"]
    if isinstance(vencimiento, datetime):
        vencimiento = vencimiento.date()
    dias_vencida = max(0, (date.today() - vencimiento).days) if saldo > 0 else 0
    emision = doc["fecha_emision"]
    if isinstance(emision, datetime):
        emision = emision.date()
    return {
        "_id": doc["_id"],
        "cliente_id": doc["cliente_id"],
        "folio": doc["folio"],
        "importe": importe / 100,
        "pagado": pagado / 100,
        "saldo": saldo / 100,
        "estado": doc["estado"],
        "fecha_emision": emision,
        "fecha_vencimiento": vencimiento,
        "dias_vencida": dias_vencida,
    }


@router.post(
    "",
    response_model=FacturaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una factura",
)
async def crear_factura(
    datos: FacturaCrear,
    base: AsyncIOMotorDatabase = Depends(obtener_base),
) -> dict:
    cliente_id = _a_object_id(datos.cliente_id, "el cliente")
    # Una factura sin cliente no se puede proyectar: se verifica antes de
    # guardar y se responde 404 señalando cuál es el recurso que falta.
    if await base.clientes.count_documents({"_id": cliente_id}, limit=1) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe el cliente {datos.cliente_id}",
        )
    documento = {
        "cliente_id": cliente_id,
        "folio": datos.folio,
        "importe_centavos": _a_centavos(datos.importe),
        "pagado_centavos": 0,
        "estado": EstadoFactura.PENDIENTE.value,
        # Mongo no guarda `date`, solo `datetime`: se normaliza al guardar y se
        # recorta al leer, para que el tipo sea consistente a ambos lados.
        "fecha_emision": datetime.combine(datos.fecha_emision, datetime.min.time()),
        "fecha_vencimiento": datetime.combine(datos.fecha_vencimiento, datetime.min.time()),
        "creado_en": datetime.now(UTC),
    }
    try:
        resultado = await base.facturas.insert_one(documento)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe la factura {datos.folio} para ese cliente",
        ) from exc
    documento["_id"] = resultado.inserted_id
    return _vista(documento)


@router.get("", response_model=list[FacturaRespuesta], summary="Listar facturas")
async def listar_facturas(
    cliente_id: str | None = Query(default=None, description="Filtrar por cliente"),
    estado: EstadoFactura | None = Query(default=None, description="Filtrar por estado"),
    limite: int = Query(default=100, ge=1, le=500),
    base: AsyncIOMotorDatabase = Depends(obtener_base),
) -> list[dict]:
    filtro: dict = {}
    if cliente_id is not None:
        filtro["cliente_id"] = _a_object_id(cliente_id, "el cliente")
    if estado is not None:
        filtro["estado"] = estado.value
    cursor = base.facturas.find(filtro).sort("fecha_vencimiento", 1).limit(limite)
    return [_vista(d) for d in await cursor.to_list(length=limite)]


@router.get("/{factura_id}", response_model=FacturaRespuesta, summary="Consultar una factura")
async def obtener_factura(
    factura_id: str,
    base: AsyncIOMotorDatabase = Depends(obtener_base),
) -> dict:
    doc = await base.facturas.find_one({"_id": _a_object_id(factura_id, "la factura")})
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe la factura {factura_id}",
        )
    return _vista(doc)


@router.post(
    "/{factura_id}/pagos",
    response_model=FacturaRespuesta,
    summary="Registrar un abono a la factura",
)
async def registrar_pago(
    factura_id: str,
    pago: PagoRegistrar,
    base: AsyncIOMotorDatabase = Depends(obtener_base),
) -> dict:
    _id = _a_object_id(factura_id, "la factura")
    doc = await base.facturas.find_one({"_id": _id})
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe la factura {factura_id}",
        )

    abono = _a_centavos(pago.importe)
    saldo = doc["importe_centavos"] - doc.get("pagado_centavos", 0)
    if saldo <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esa factura ya está pagada",
        )
    # Cobrar de más es un error del capturista, no algo que deba quedar
    # guardado: la factura acabaría con saldo negativo y la proyección contaría
    # dinero que no existe.
    if abono > saldo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El abono de ${pago.importe:,.2f} excede el saldo de ${saldo / 100:,.2f}",
        )

    pagado = doc.get("pagado_centavos", 0) + abono
    nuevo_estado = (
        EstadoFactura.PAGADA.value
        if pagado >= doc["importe_centavos"]
        else EstadoFactura.PARCIAL.value
    )
    actualizado = await base.facturas.find_one_and_update(
        {"_id": _id},
        {
            "$set": {"pagado_centavos": pagado, "estado": nuevo_estado},
            "$push": {
                "abonos": {
                    "importe_centavos": abono,
                    "fecha": datetime.combine(pago.fecha, datetime.min.time()),
                }
            },
        },
        return_document=True,
    )
    return _vista(actualizado)


@router.delete(
    "/{factura_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar una factura",
)
async def eliminar_factura(
    factura_id: str,
    base: AsyncIOMotorDatabase = Depends(obtener_base),
) -> None:
    resultado = await base.facturas.delete_one({"_id": _a_object_id(factura_id, "la factura")})
    if resultado.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe la factura {factura_id}",
        )
