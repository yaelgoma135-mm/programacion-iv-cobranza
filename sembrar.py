"""
Carga datos de ejemplo para poder probar la aplicación sin capturar nada a mano.

Los clientes tienen perfiles de pago distintos a propósito —uno puntual, uno
que se atrasa poco y uno muy irregular— porque si todos pagaran igual la
simulación daría siempre el mismo número y no habría nada que proyectar. Los
vencimientos también se reparten entre hoy y tres meses adelante, para que los
horizontes de 30, 60 y 90 días den resultados diferentes.

Uso:  py sembrar.py
"""

import asyncio
from datetime import UTC, date, datetime, timedelta

from app.config import obtener_configuracion
from app.db import conectar, desconectar

CLIENTES = [
    # (nombre, rfc, días de crédito, atraso promedio, variabilidad)
    ("Gas Natural del Noroeste", "GNN9706053S3", 30, 3.0, 2.0),
    ("Servicio de Montajes Industriales", "SMI111010HI8", 30, 12.0, 8.0),
    ("Pastelerías Petit", "PPE160314TN1", 15, 5.0, 4.0),
    ("Municipio de Chapala", "MCJ980101U72", 60, 35.0, 25.0),
    ("Meson Eco", "MEC060724RH1", 30, 8.0, 6.0),
]

# (rfc del cliente, folio, importe, días desde hoy hasta el vencimiento)
FACTURAS = [
    ("GNN9706053S3", "FAC03870", 18_826.80, -22),
    ("GNN9706053S3", "FAC03921", 18_826.80, 8),
    ("GNN9706053S3", "FAC03984", 18_826.80, 38),
    ("SMI111010HI8", "FAC03871", 18_560.00, -15),
    ("SMI111010HI8", "FAC03950", 24_360.00, 25),
    ("PPE160314TN1", "FAC03875", 5_080.80, -40),
    ("PPE160314TN1", "FAC03960", 5_080.80, 12),
    ("MCJ980101U72", "FAC03801", 5_046.00, -120),
    ("MCJ980101U72", "FAC03990", 42_550.00, 55),
    ("MCJ980101U72", "FAC04020", 30_633.00, 85),
    ("MEC060724RH1", "FAC03918", 3_538.00, -8),
    ("MEC060724RH1", "FAC04001", 12_006.00, 45),
    ("MEC060724RH1", "FAC04055", 20_300.00, 75),
]


async def main() -> None:
    config = obtener_configuracion()
    base = await conectar(config.mongodb_uri, config.mongodb_base)
    print(f"Conectado a '{config.mongodb_base}'")

    # Se vacía primero para que correrlo dos veces no acumule duplicados.
    await base.facturas.delete_many({})
    await base.clientes.delete_many({})
    print("Colecciones vaciadas")

    por_rfc: dict[str, object] = {}
    for nombre, rfc, credito, atraso, variabilidad in CLIENTES:
        r = await base.clientes.insert_one(
            {
                "nombre": nombre,
                "rfc": rfc,
                "dias_credito": credito,
                "dias_atraso_promedio": atraso,
                "variabilidad_atraso": variabilidad,
                "creado_en": datetime.now(UTC),
            }
        )
        por_rfc[rfc] = r.inserted_id
    print(f"{len(CLIENTES)} clientes insertados")

    hoy = date.today()
    total = 0
    for rfc, folio, importe, dias in FACTURAS:
        vencimiento = hoy + timedelta(days=dias)
        await base.facturas.insert_one(
            {
                "cliente_id": por_rfc[rfc],
                "folio": folio,
                "importe_centavos": int(round(importe * 100)),
                "pagado_centavos": 0,
                "estado": "pendiente",
                "fecha_emision": datetime.combine(vencimiento - timedelta(days=30), datetime.min.time()),
                "fecha_vencimiento": datetime.combine(vencimiento, datetime.min.time()),
                "creado_en": datetime.now(UTC),
            }
        )
        total += importe
    print(f"{len(FACTURAS)} facturas insertadas · cartera ${total:,.2f}")

    await desconectar()
    print("\nListo. Levanta el servidor con:  py -m uvicorn app.main:app --reload")


if __name__ == "__main__":
    asyncio.run(main())
