"""
CRUD de clientes.

Cada ruta devuelve el código HTTP que corresponde al hecho, no un 200 genérico:
201 cuando se creó algo nuevo, 404 cuando el recurso no existe, 409 cuando el
RFC choca con otro cliente y 204 cuando se borró y no hay nada que devolver.
"""

from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from ..db import obtener_base
from ..esquemas import ClienteActualizar, ClienteCrear, ClienteRespuesta

router = APIRouter(prefix="/api/clientes", tags=["clientes"])


def _a_object_id(id_texto: str) -> ObjectId:
    """
    Convierte el id de la URL, o devuelve 404.

    Un id con forma inválida es 404 y no 400 a propósito: desde el punto de
    vista de quien consulta, '/api/clientes/abc' simplemente no existe, y
    distinguirlo de un id válido inexistente solo le diría a un atacante qué
    ids tienen la forma correcta.
    """
    try:
        return ObjectId(id_texto)
    except (InvalidId, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe el cliente {id_texto}",
        ) from exc


@router.post(
    "",
    response_model=ClienteRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Dar de alta un cliente",
)
async def crear_cliente(
    datos: ClienteCrear,
    base: AsyncIOMotorDatabase = Depends(obtener_base),
) -> dict:
    documento = datos.model_dump()
    documento["creado_en"] = datetime.now(UTC)
    try:
        resultado = await base.clientes.insert_one(documento)
    except DuplicateKeyError as exc:
        # El índice único del RFC es quien detecta el choque, no una consulta
        # previa: entre el "¿ya existe?" y el insert cabe otra petición.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un cliente con el RFC {datos.rfc}",
        ) from exc
    documento["_id"] = resultado.inserted_id
    return documento


@router.get("", response_model=list[ClienteRespuesta], summary="Listar clientes")
async def listar_clientes(
    limite: int = 100,
    base: AsyncIOMotorDatabase = Depends(obtener_base),
) -> list[dict]:
    if not 1 <= limite <= 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El límite debe estar entre 1 y 500",
        )
    cursor = base.clientes.find().sort("creado_en", -1).limit(limite)
    return await cursor.to_list(length=limite)


@router.get("/{cliente_id}", response_model=ClienteRespuesta, summary="Consultar un cliente")
async def obtener_cliente(
    cliente_id: str,
    base: AsyncIOMotorDatabase = Depends(obtener_base),
) -> dict:
    documento = await base.clientes.find_one({"_id": _a_object_id(cliente_id)})
    if documento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe el cliente {cliente_id}",
        )
    return documento


@router.patch("/{cliente_id}", response_model=ClienteRespuesta, summary="Modificar un cliente")
async def actualizar_cliente(
    cliente_id: str,
    cambios: ClienteActualizar,
    base: AsyncIOMotorDatabase = Depends(obtener_base),
) -> dict:
    # exclude_unset distingue "no lo mandó" de "lo mandó vacío": sin eso, un
    # PATCH que solo cambia el nombre borraría los demás campos con None.
    actualizacion = cambios.model_dump(exclude_unset=True)
    if not actualizacion:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No mandaste ningún campo que cambiar",
        )
    documento = await base.clientes.find_one_and_update(
        {"_id": _a_object_id(cliente_id)},
        {"$set": actualizacion},
        return_document=True,
    )
    if documento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe el cliente {cliente_id}",
        )
    return documento


@router.delete(
    "/{cliente_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un cliente",
)
async def eliminar_cliente(
    cliente_id: str,
    base: AsyncIOMotorDatabase = Depends(obtener_base),
) -> None:
    _id = _a_object_id(cliente_id)
    # No se permite borrar un cliente que todavía debe: dejaría facturas
    # apuntando a un cliente inexistente y la proyección no sabría de quién son.
    pendientes = await base.facturas.count_documents({"cliente_id": _id, "estado": {"$ne": "pagada"}})
    if pendientes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El cliente tiene {pendientes} factura(s) sin pagar; no se puede eliminar",
        )
    resultado = await base.clientes.delete_one({"_id": _id})
    if resultado.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe el cliente {cliente_id}",
        )
