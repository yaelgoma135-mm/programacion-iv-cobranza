"""
Configuración de la aplicación, leída del entorno.

Nada de credenciales en el código: la cadena de conexión vive en el archivo
.env, que no se sube al repositorio. El .env.example documenta qué variables
hacen falta sin revelar sus valores.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracion(BaseSettings):
    """Variables de entorno de la aplicación, validadas al arrancar."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mongodb_uri: str = Field(
        ...,
        description="Cadena de conexión de MongoDB Atlas (mongodb+srv://...)",
    )
    mongodb_base: str = Field(
        default="cobranza_escuela",
        description="Nombre de la base de datos dentro del cluster",
    )
    # El límite existe para que nadie tumbe el servidor pidiendo diez millones
    # de escenarios: la simulación es intensiva a propósito, no infinita.
    max_escenarios: int = Field(default=200_000, ge=1_000)

    titulo_app: str = Field(default="Gestor de Cobranza con Proyección Monte Carlo")


@lru_cache
def obtener_configuracion() -> Configuracion:
    """
    Devuelve la configuración una sola vez por proceso.

    El `lru_cache` no es por velocidad: evita releer y revalidar el .env en
    cada petición, y hace que un valor mal puesto reviente al arrancar y no a
    media operación.
    """
    return Configuracion()  # type: ignore[call-arg]
