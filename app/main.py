"""
Punto de entrada de la aplicación.

Aquí se arma todo: el ciclo de vida de la conexión a MongoDB, las rutas de la
API y el frontend servido como archivos estáticos.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import obtener_configuracion
from .db import conectar, desconectar
from .rutas import clientes, facturas, proyecciones

RAIZ = Path(__file__).resolve().parent.parent
ESTATICOS = RAIZ / "static"


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    """
    Abre la conexión a MongoDB al arrancar y la cierra al apagar.

    Es el patrón que pide la práctica, y la razón es concreta: un
    `AsyncIOMotorClient` mantiene un pool de conexiones al cluster. Crearlo por
    petición agota el límite de conexiones de Atlas y paga un handshake TLS
    cada vez; crearlo al importar el módulo lo ataría al event loop equivocado
    cuando corren las pruebas.

    Lo que va antes del `yield` corre al arrancar; lo de después, al apagar —
    incluso si el servidor se detiene por un error.
    """
    config = obtener_configuracion()
    await conectar(config.mongodb_uri, config.mongodb_base)
    print(f"✓ Conectado a MongoDB · base '{config.mongodb_base}'")
    try:
        yield
    finally:
        await desconectar()
        print("✓ Conexión a MongoDB cerrada")


config = obtener_configuracion()

app = FastAPI(
    title=config.titulo_app,
    version="1.0.0",
    description=(
        "API de cobranza con proyección de flujo por simulación Monte Carlo. "
        "El cálculo pesado se delega a un hilo con asyncio.to_thread() para no "
        "bloquear el event loop."
    ),
    lifespan=ciclo_de_vida,
)

app.include_router(clientes.router)
app.include_router(facturas.router)
app.include_router(proyecciones.router)


@app.exception_handler(500)
async def error_no_controlado(request: Request, exc: Exception) -> JSONResponse:
    """
    Un error interno no debe filtrar el traceback al navegador.

    Se responde con una forma estable y el detalle queda en la consola del
    servidor, que es donde sirve.
    """
    return JSONResponse(
        status_code=500,
        content={"detalle": "Error interno del servidor"},
    )


@app.get("/api/salud", tags=["sistema"], summary="Estado del servicio")
async def salud() -> dict:
    """Comprueba que la aplicación está arriba y contra qué base trabaja."""
    return {"estado": "ok", "base": config.mongodb_base}


@app.get("/", include_in_schema=False)
async def inicio() -> FileResponse:
    """Sirve la interfaz. Se declara antes del montaje para que '/' no dé 404."""
    return FileResponse(ESTATICOS / "index.html")


# El frontend se sirve desde la misma aplicación: así no hace falta un servidor
# aparte ni configurar CORS, porque la API y la interfaz comparten origen.
# Va al FINAL a propósito: montar en '/' captura todo lo que no haya casado
# antes, y si se montara primero se comería las rutas de la API.
app.mount("/", StaticFiles(directory=ESTATICOS, html=True), name="static")
