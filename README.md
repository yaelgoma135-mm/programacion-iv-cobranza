# Gestor de Cobranza con Proyección Monte Carlo

API REST en FastAPI con persistencia en MongoDB Atlas, frontend en JavaScript
puro y un cálculo intensivo de CPU que se delega a un hilo secundario para no
bloquear el servidor.

**Programación IV** · Yael Gómez · Matrícula 224164501
Profesora: Nicole Michelle Leyva Munguía

---

## Qué hace

Gestiona clientes y sus facturas por cobrar, y **proyecta cuánto dinero va a
entrar en los próximos 30, 60 y 90 días** usando simulación de Monte Carlo.

El problema que resuelve es real: nadie sabe qué día va a pagar un cliente, pero
sí se sabe cómo ha pagado antes. En vez de dar un número único y falso —"en 30
días entran $400,000"— la aplicación simula decenas de miles de futuros posibles
usando el atraso histórico de cada cliente, y reporta el rango: lo esperado, lo
pesimista (percentil 10) y lo optimista (percentil 90).

Esa simulación es **genuinamente pesada**: 50,000 escenarios sobre 13 facturas
son más de medio millón de sorteos aleatorios en Python puro. Ahí entra la
concurrencia.

---

## Instalación

Requiere **Python 3.11 o superior**.

```bash
# 1. Clonar e instalar dependencias
pip install -r requirements.txt

# 2. Configurar la conexión a la base de datos
cp .env.example .env
#    Editar .env y poner la cadena de MongoDB Atlas en MONGODB_URI

# 3. (Opcional) Cargar datos de ejemplo
py sembrar.py

# 4. Levantar el servidor
py -m uvicorn app.main:app --reload
```

Abrir **http://localhost:8000**

La documentación interactiva de la API queda en **http://localhost:8000/docs**.

### Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `MONGODB_URI` | Sí | Cadena de conexión de Atlas (`mongodb+srv://...`) |
| `MONGODB_BASE` | No | Base dentro del cluster. Por omisión `cobranza_escuela` |
| `MAX_ESCENARIOS` | No | Tope de escenarios por petición. Por omisión `200000` |

El archivo `.env` **no se sube al repositorio** — contiene credenciales. El
`.env.example` documenta qué hace falta sin revelar valores.

Si la cadena de conexión está mal, **la aplicación no arranca**: hace un `ping`
al cluster durante el arranque. Es preferible a arrancar "bien" y fallar en la
primera petición de un usuario.

---

## Endpoints

### Clientes

| Método | Ruta | Qué hace | Códigos |
|---|---|---|---|
| `POST` | `/api/clientes` | Da de alta un cliente | `201` `409` `422` |
| `GET` | `/api/clientes` | Lista clientes | `200` `400` |
| `GET` | `/api/clientes/{id}` | Consulta uno | `200` `404` |
| `PATCH` | `/api/clientes/{id}` | Modifica campos sueltos | `200` `400` `404` |
| `DELETE` | `/api/clientes/{id}` | Elimina | `204` `404` `409` |

### Facturas

| Método | Ruta | Qué hace | Códigos |
|---|---|---|---|
| `POST` | `/api/facturas` | Registra una factura | `201` `404` `422` |
| `GET` | `/api/facturas` | Lista, con filtros por cliente y estado | `200` |
| `GET` | `/api/facturas/{id}` | Consulta una | `200` `404` |
| `POST` | `/api/facturas/{id}/pagos` | Registra un abono | `200` `400` `404` |
| `DELETE` | `/api/facturas/{id}` | Elimina | `204` `404` |

### Proyección

| Método | Ruta | Qué hace | Códigos |
|---|---|---|---|
| `POST` | `/api/proyecciones` | Simula la cobranza **en un hilo aparte** | `200` `400` `404` |
| `POST` | `/api/proyecciones/bloqueante` | Lo mismo **sin** hilo — demuestra el problema | `200` |
| `GET` | `/api/proyecciones/latido` | Señal de vida del servidor | `200` |
| `GET` | `/api/salud` | Estado del servicio | `200` |

**14 endpoints en total.**

### Por qué cada código

- **`201`** al crear, no `200`: hay un recurso nuevo.
- **`204`** al borrar: se hizo, y no hay nada que devolver.
- **`400`** cuando los datos son válidos pero la operación no tiene sentido —
  abonar más de lo que se debe, por ejemplo.
- **`404`** cuando el recurso no existe. También cuando el `id` tiene forma
  inválida: desde fuera, `/api/clientes/abc` simplemente no existe, y
  distinguirlo solo le diría a un atacante qué ids tienen la forma correcta.
- **`409`** cuando choca con algo que ya está — un RFC repetido, o borrar un
  cliente que todavía debe.
- **`422`** lo pone Pydantic solo cuando el cuerpo no cumple el esquema.

---

## La concurrencia

FastAPI corre sobre un **event loop de un solo hilo**. Mientras una corrutina no
haga `await`, nadie más avanza. Un cálculo de varios segundos metido directo en
una ruta `async` deja al servidor mudo para **todos** los usuarios.

```python
# app/rutas/proyecciones.py
resultado = await asyncio.to_thread(
    simular_cobranza, facturas, solicitud.escenarios, solicitud.horizontes_dias
)
```

`asyncio.to_thread()` manda la función síncrona a un hilo del pool y devuelve un
awaitable. El `await` le cede el control al event loop, que sigue atendiendo
peticiones mientras el hilo trabaja.

### Cómo comprobarlo sin creerme nada

La interfaz tiene un **latido** arriba a la derecha que llama a
`/api/proyecciones/latido` cada 400 ms y muestra cuánto tarda en responder.

1. Subir los escenarios a 150,000.
2. Pulsar **«Proyectar sin bloquear»** → el latido sigue pulsando en verde.
3. Pulsar **«Proyectar bloqueando»** → el latido se pone rojo y dice
   **BLOQUEADO**, y se queda así hasta que el cálculo termina.

Las dos rutas hacen *exactamente el mismo cálculo*. La única diferencia es
`asyncio.to_thread()`.

Además, la respuesta trae el campo `hilo` con el nombre del hilo donde corrió:

```json
{ "milisegundos_calculo": 1840, "hilo": "asyncio_0" }
```

Si dijera `MainThread`, el servidor habría estado bloqueado. No se puede fingir:
el dato lo pone el servidor.

### Medido

`pruebas.py` cuenta cuántas peticiones alcanza a atender el servidor mientras
corre el cálculo:

```
con to_thread:   0.67s de cálculo → el servidor atendió 14 latidos
sin to_thread:   1.09s de cálculo → el servidor atendió  0 latidos
```

---

## Pruebas

```bash
pip install -r requirements-dev.txt
py pruebas.py
```

21 comprobaciones de extremo a extremo contra una base **en memoria**, así que
corren en cualquier máquina sin credenciales y sin ensuciar el cluster. Se
ejercita la aplicación real por HTTP, no las funciones por separado.

---

## Estructura

```
.
├── app/
│   ├── main.py              FastAPI, lifespan y montaje de estáticos
│   ├── config.py            Variables de entorno validadas con Pydantic
│   ├── db.py                Conexión a MongoDB con Motor
│   ├── esquemas.py          Modelos de Pydantic (entrada y salida)
│   ├── rutas/
│   │   ├── clientes.py      CRUD de clientes
│   │   ├── facturas.py      CRUD de facturas y abonos
│   │   └── proyecciones.py  La parte con asyncio.to_thread()
│   └── servicios/
│       └── montecarlo.py    La simulación — código síncrono puro
├── static/                  Frontend: HTML, CSS y JS sin frameworks
├── sembrar.py               Datos de ejemplo
├── pruebas.py               Pruebas de extremo a extremo
└── .env.example             Qué variables hacen falta
```

### Dos decisiones que se notan en todo el código

**El dinero se guarda en centavos enteros.** Un `float` no representa `0.10`
exacto, y sumar miles de importes en una simulación arrastra el error hasta que
los totales dejan de cuadrar contra la factura. Entra y sale como pesos
decimales porque es cómodo; por dentro siempre es `int`.

**La simulación no sabe nada de concurrencia.** `montecarlo.py` es código
síncrono normal, sin un solo `async`. Quien lo llama decide mandarlo a un hilo.
Esa separación es lo que permite probarlo y razonarlo sin pensar en el event
loop — y es la razón de que el archivo se pueda leer de corrido.
