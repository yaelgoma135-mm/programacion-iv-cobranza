"""
Proyección de cobranza: la parte intensiva en CPU.

Aquí está el punto central de la práctica. FastAPI corre sobre un **event loop
de un solo hilo**: mientras una corrutina no haga `await`, nadie más avanza. Un
cálculo de varios segundos metido directo en una ruta `async` deja al servidor
mudo para TODOS los usuarios, no solo para quien lo pidió.

`asyncio.to_thread()` manda esa función síncrona a un hilo del pool y devuelve
un awaitable. El `await` le cede el control al event loop, que sigue atendiendo
peticiones mientras el hilo trabaja.

Para que la diferencia se pueda ver y no solo leer, hay dos rutas que calculan
EXACTAMENTE lo mismo:

  POST /api/proyecciones            → con to_thread. El servidor sigue vivo.
  POST /api/proyecciones/bloqueante → sin to_thread. El servidor se congela.

La segunda existe solo para demostrar el problema. En código real no se escribe.
"""

import asyncio
import threading
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..config import obtener_configuracion
from ..db import obtener_base
from ..esquemas import ProyeccionRespuesta, ProyeccionSolicitud, TramoProyeccion
from ..servicios.montecarlo import (
    FacturaParaSimular,
    ResultadoProyeccion,
    simular_cobranza,
)

router = APIRouter(prefix="/api/proyecciones", tags=["proyección"])


async def _reunir_facturas(base: AsyncIOMotorDatabase) -> tuple[list[FacturaParaSimular], int]:
    """
    Junta las facturas por cobrar con el perfil de pago de su cliente.

    Toda la parte de entrada/salida vive aquí, en el mundo `async`. Lo que se
    manda al hilo es una lista de datos simples, ya cerrada: el hilo no toca la
    base ni comparte objetos con el event loop, que es lo que hace segura esta
    separación.
    """
    hoy = date.today()
    clientes = {c["_id"]: c for c in await base.clientes.find().to_list(length=1000)}

    facturas: list[FacturaParaSimular] = []
    cartera_centavos = 0
    cursor = base.facturas.find({"estado": {"$ne": "pagada"}})
    for doc in await cursor.to_list(length=5000):
        saldo = doc["importe_centavos"] - doc.get("pagado_centavos", 0)
        if saldo <= 0:
            continue
        cliente = clientes.get(doc["cliente_id"])
        if cliente is None:
            # Factura huérfana: se ignora en vez de inventarle un perfil de pago.
            continue
        vencimiento = doc["fecha_vencimiento"]
        if isinstance(vencimiento, datetime):
            vencimiento = vencimiento.date()
        cartera_centavos += saldo
        facturas.append(
            FacturaParaSimular(
                saldo_centavos=saldo,
                dias_al_vencimiento=(vencimiento - hoy).days,
                atraso_promedio=float(cliente.get("dias_atraso_promedio", 0.0)),
                variabilidad=float(cliente.get("variabilidad_atraso", 5.0)),
            )
        )
    return facturas, cartera_centavos


def _armar_respuesta(
    resultado: ResultadoProyeccion,
    cartera_centavos: int,
    cuantas: int,
    escenarios: int,
) -> ProyeccionRespuesta:
    return ProyeccionRespuesta(
        cartera_total=cartera_centavos / 100,
        facturas_consideradas=cuantas,
        escenarios=escenarios,
        milisegundos_calculo=resultado.milisegundos,
        hilo=resultado.hilo,
        tramos=[
            TramoProyeccion(
                dias=t.dias,
                esperado=t.esperado_centavos / 100,
                pesimista=t.pesimista_centavos / 100,
                optimista=t.optimista_centavos / 100,
                porcentaje_cartera=(
                    round(t.esperado_centavos / cartera_centavos * 100, 1)
                    if cartera_centavos
                    else 0.0
                ),
            )
            for t in resultado.tramos
        ],
    )


@router.post(
    "",
    response_model=ProyeccionRespuesta,
    summary="Proyectar la cobranza (sin bloquear el servidor)",
)
async def proyectar(
    solicitud: ProyeccionSolicitud,
    base: AsyncIOMotorDatabase = Depends(obtener_base),
) -> ProyeccionRespuesta:
    config = obtener_configuracion()
    if solicitud.escenarios > config.max_escenarios:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El máximo es {config.max_escenarios:,} escenarios. "
                "El tope evita que una sola petición acapare un hilo durante minutos."
            ),
        )

    facturas, cartera = await _reunir_facturas(base)
    if not facturas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay facturas por cobrar que proyectar",
        )

    # ─────────────────────────────────────────────────────────────────────
    # AQUÍ está lo importante de toda la práctica.
    #
    # `simular_cobranza` es síncrona y tarda segundos. Llamarla directo
    # congelaría el event loop. `asyncio.to_thread` la corre en un hilo del
    # pool; el `await` devuelve el control al event loop, que sigue
    # atendiendo peticiones mientras tanto.
    #
    # Se puede comprobar: el campo `hilo` de la respuesta trae el nombre del
    # hilo donde corrió, y nunca dice 'MainThread'.
    # ─────────────────────────────────────────────────────────────────────
    resultado = await asyncio.to_thread(
        simular_cobranza,
        facturas,
        solicitud.escenarios,
        solicitud.horizontes_dias,
    )

    return _armar_respuesta(resultado, cartera, len(facturas), solicitud.escenarios)


@router.post(
    "/bloqueante",
    response_model=ProyeccionRespuesta,
    summary="LA FORMA INCORRECTA — calcula igual pero congela el servidor",
    description=(
        "Existe solo para demostrar el problema que `asyncio.to_thread()` resuelve. "
        "Hace el mismo cálculo SIN mandarlo a un hilo, así que el event loop queda "
        "bloqueado y el servidor deja de responder a cualquier otra petición hasta "
        "que termina. Compare el latido de la interfaz con una y con otra."
    ),
)
async def proyectar_bloqueando(
    solicitud: ProyeccionSolicitud,
    base: AsyncIOMotorDatabase = Depends(obtener_base),
) -> ProyeccionRespuesta:
    config = obtener_configuracion()
    if solicitud.escenarios > config.max_escenarios:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El máximo es {config.max_escenarios:,} escenarios",
        )
    facturas, cartera = await _reunir_facturas(base)
    if not facturas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay facturas por cobrar que proyectar",
        )

    # Sin to_thread: la corrutina nunca cede el control y el event loop se
    # queda atorado aquí. Es exactamente lo que NO hay que hacer.
    resultado = simular_cobranza(facturas, solicitud.escenarios, solicitud.horizontes_dias)

    return _armar_respuesta(resultado, cartera, len(facturas), solicitud.escenarios)


@router.get(
    "/latido",
    summary="Señal de vida del servidor",
    description=(
        "Responde de inmediato y dice en qué hilo corre. La interfaz lo llama varias "
        "veces por segundo: si sigue contestando mientras la proyección trabaja, el "
        "servidor no está bloqueado."
    ),
)
async def latido() -> dict:
    return {
        "vivo": True,
        "momento": datetime.now().isoformat(timespec="milliseconds"),
        "hilo": threading.current_thread().name,
    }
