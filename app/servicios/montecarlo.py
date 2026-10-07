"""
Proyección de cobranza por simulación de Monte Carlo.

El problema que resuelve: nadie sabe qué día va a pagar un cliente. Lo que sí
se sabe es cómo ha pagado antes — un cliente que suele atrasarse 20 días rara
vez paga al día. En vez de dar un número único y falso ("en 30 días entran
$400,000"), se simulan miles de futuros posibles usando ese historial y se
reporta el rango: lo esperado, lo pesimista y lo optimista.

**Esta función es deliberadamente intensiva en CPU y SÍNCRONA.** Es puro Python
sin numpy, así que para 50,000 escenarios sobre 30 facturas hace millón y medio
de sorteos aleatorios y sumas. Correrla directo dentro de una ruta `async`
congelaría el event loop de FastAPI y el servidor dejaría de contestar a
cualquier otro usuario mientras tanto.

Por eso quien la llama lo hace con `asyncio.to_thread()` (ver rutas/proyecciones.py):
el cálculo se va a un hilo secundario y el event loop queda libre. Esta función
no sabe nada de eso a propósito — es código síncrono normal, y esa separación es
justamente lo que permite probarla y razonarla sin pensar en concurrencia.
"""

import random
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class FacturaParaSimular:
    """
    Lo mínimo que la simulación necesita de una factura.

    Es un dataclass y no el esquema de Pydantic porque esta función corre en
    otro hilo: conviene pasarle datos simples e inmutables, sin referencias a
    la base ni objetos que alguien más pueda estar modificando.
    """

    saldo_centavos: int
    # Días desde hoy hasta el vencimiento. Negativo si ya venció.
    dias_al_vencimiento: int
    atraso_promedio: float
    variabilidad: float


@dataclass(frozen=True)
class ResultadoTramo:
    dias: int
    esperado_centavos: int
    pesimista_centavos: int
    optimista_centavos: int


@dataclass(frozen=True)
class ResultadoProyeccion:
    tramos: list[ResultadoTramo]
    milisegundos: int
    hilo: str


# Una factura muy vencida tiene menos probabilidad de cobrarse. La curva es
# simple a propósito: cada 90 días vencida se pierde ~20% de probabilidad, con
# piso en 30%. No pretende ser un modelo de riesgo, pero evita el supuesto
# ingenuo de que todo se cobra.
_DIAS_POR_ESCALON = 90
_CASTIGO_POR_ESCALON = 0.20
_PROBABILIDAD_MINIMA = 0.30


def _probabilidad_de_cobro(dias_vencida: int) -> float:
    """Qué tan probable es cobrar una factura según lo vencida que esté."""
    if dias_vencida <= 0:
        return 1.0
    escalones = dias_vencida / _DIAS_POR_ESCALON
    return max(_PROBABILIDAD_MINIMA, 1.0 - _CASTIGO_POR_ESCALON * escalones)


def simular_cobranza(
    facturas: list[FacturaParaSimular],
    escenarios: int,
    horizontes_dias: list[int],
    semilla: int | None = None,
) -> ResultadoProyeccion:
    """
    Corre la simulación y devuelve lo esperado por cada horizonte.

    :param semilla: Fija el azar para que una misma entrada dé siempre el mismo
        resultado. Sirve para las pruebas; en producción se deja en None.
    """
    inicio = time.perf_counter()
    azar = random.Random(semilla)

    horizontes = sorted(horizontes_dias)
    # Un acumulador por horizonte: en cada escenario se suma lo cobrado dentro
    # de ese plazo, y al final se ordena para sacar los percentiles.
    totales: list[list[int]] = [[] for _ in horizontes]

    # Se precalcula lo que no cambia entre escenarios. Dentro del bucle
    # principal cada operación se repite cientos de miles de veces.
    preparadas = [
        (
            f.saldo_centavos,
            f.dias_al_vencimiento,
            f.atraso_promedio,
            f.variabilidad,
            _probabilidad_de_cobro(-f.dias_al_vencimiento),
        )
        for f in facturas
    ]

    for _ in range(escenarios):
        cobrado_por_horizonte = [0] * len(horizontes)
        for saldo, dias_venc, atraso, variabilidad, probabilidad in preparadas:
            # ¿Se cobra esta factura en este escenario?
            if azar.random() > probabilidad:
                continue
            # ¿Cuándo? Vencimiento + atraso sorteado de una normal.
            atraso_simulado = azar.gauss(atraso, variabilidad) if variabilidad > 0 else atraso
            dia_de_pago = dias_venc + atraso_simulado
            # Un pago no puede ocurrir en el pasado: lo vencido se cobra hoy o
            # después, nunca "hace 40 días".
            if dia_de_pago < 0:
                dia_de_pago = 0.0
            for i, limite in enumerate(horizontes):
                if dia_de_pago <= limite:
                    cobrado_por_horizonte[i] += saldo
        for i, total in enumerate(cobrado_por_horizonte):
            totales[i].append(total)

    tramos: list[ResultadoTramo] = []
    for i, dias in enumerate(horizontes):
        muestras = sorted(totales[i])
        n = len(muestras)
        promedio = sum(muestras) // n if n else 0
        tramos.append(
            ResultadoTramo(
                dias=dias,
                esperado_centavos=promedio,
                pesimista_centavos=_percentil(muestras, 10),
                optimista_centavos=_percentil(muestras, 90),
            )
        )

    return ResultadoProyeccion(
        tramos=tramos,
        milisegundos=int((time.perf_counter() - inicio) * 1000),
        # El nombre del hilo es la prueba de que el trabajo NO corrió en el
        # event loop: si dice 'MainThread', algo se cableó mal.
        hilo=threading.current_thread().name,
    )


def _percentil(ordenados: list[int], p: int) -> int:
    """
    Percentil por el método del vecino más cercano, sobre una lista ya ordenada.

    Se evita interpolar: con dinero en centavos, un percentil interpolado da un
    importe que ningún escenario produjo realmente.
    """
    if not ordenados:
        return 0
    indice = min(len(ordenados) - 1, max(0, round(p / 100 * len(ordenados)) - 1))
    return ordenados[indice]
