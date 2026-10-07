"""
Pruebas de extremo a extremo de toda la API.

Corren contra una base de datos EN MEMORIA (mongomock-motor), no contra Atlas:
así se pueden ejecutar en cualquier máquina, sin credenciales y sin dejar
basura en el cluster. Se ejercita la aplicación real por HTTP, no las funciones
por separado, para que lo que se prueba sea lo mismo que ve un usuario.

La última sección es la que importa para esta práctica: mide cuántas peticiones
alcanza a atender el servidor MIENTRAS corre el cálculo pesado, con y sin
asyncio.to_thread(). La diferencia no se argumenta, se cuenta.

Requiere:  py -m pip install -r requirements-dev.txt
Uso:       py pruebas.py
"""
import asyncio, os, time
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
from mongomock_motor import AsyncMongoMockClient
import app.db as db
from httpx import ASGITransport, AsyncClient

# Se sustituye la base real por una en memoria, sin tocar el codigo de la app.
mock = AsyncMongoMockClient()
db._base = mock["prueba"]
from app.main import app as fastapi_app
fastapi_app.router.lifespan_context = None

async def main():
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def sin_mongo(app):
        # Los indices se crean en conectar(), que aqui no corre: hay que
        # crearlos a mano o el indice unico del RFC no existiria y la prueba
        # de duplicados pasaria por una razon falsa.
        await db._crear_indices(db._base)
        yield
    fastapi_app.router.lifespan_context = sin_mongo
    # httpx con ASGITransport NO dispara el lifespan, asi que los indices se
    # crean aqui a mano. Sin esto, el indice unico del RFC no existe y la
    # prueba de duplicados pasaria sin probar nada.
    await db._crear_indices(db._base)
    ok = fail = 0
    def chk(nombre, cond, extra=""):
        nonlocal ok, fail
        if cond: ok += 1; print(f"  OK  {nombre} {extra}")
        else: fail += 1; print(f"  X   {nombre} {extra}")

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://t") as c:
        print("=== CLIENTES ===")
        r = await c.post("/api/clientes", json={"nombre":"Gas Natural del Noroeste","rfc":"gnn9706053s3","dias_credito":30,"dias_atraso_promedio":8,"variabilidad_atraso":5})
        chk("POST crea y responde 201", r.status_code==201, f"-> {r.status_code}")
        cid = r.json()["id"]
        chk("el RFC se guardo en mayusculas", r.json()["rfc"]=="GNN9706053S3")

        r = await c.post("/api/clientes", json={"nombre":"Otro","rfc":"GNN9706053S3"})
        chk("RFC duplicado -> 409", r.status_code==409, f"-> {r.status_code}")

        r = await c.post("/api/clientes", json={"nombre":"ab","rfc":"GNN9706053S3"})
        chk("nombre invalido -> 422", r.status_code==422, f"-> {r.status_code}")

        r = await c.get("/api/clientes/000000000000000000000000")
        chk("cliente inexistente -> 404", r.status_code==404, f"-> {r.status_code}")

        r = await c.patch(f"/api/clientes/{cid}", json={"dias_atraso_promedio": 12})
        chk("PATCH actualiza", r.status_code==200 and r.json()["dias_atraso_promedio"]==12)

        r = await c.patch(f"/api/clientes/{cid}", json={})
        chk("PATCH vacio -> 400", r.status_code==400, f"-> {r.status_code}")

        print("\n=== FACTURAS ===")
        from datetime import date, timedelta
        hoy = date.today()
        r = await c.post("/api/facturas", json={"cliente_id":cid,"folio":"fac03881","importe":18560.00,"fecha_emision":str(hoy-timedelta(days=40)),"fecha_vencimiento":str(hoy-timedelta(days=10))})
        chk("POST crea factura -> 201", r.status_code==201, f"-> {r.status_code}")
        fid = r.json()["id"]
        chk("folio normalizado a mayusculas", r.json()["folio"]=="FAC03881")
        chk("calcula dias vencida", r.json()["dias_vencida"]==10, f"({r.json()['dias_vencida']}d)")

        r = await c.post("/api/facturas", json={"cliente_id":"000000000000000000000000","folio":"X","importe":10,"fecha_emision":str(hoy),"fecha_vencimiento":str(hoy)})
        chk("factura con cliente inexistente -> 404", r.status_code==404, f"-> {r.status_code}")

        r = await c.post(f"/api/facturas/{fid}/pagos", json={"importe": 99999999})
        chk("abono mayor al saldo -> 400", r.status_code==400, f"-> {r.status_code}")

        r = await c.post(f"/api/facturas/{fid}/pagos", json={"importe": 8560.00})
        chk("abono parcial deja estado 'parcial'", r.status_code==200 and r.json()["estado"]=="parcial", f"saldo {r.json().get('saldo')}")

        r = await c.delete(f"/api/clientes/{cid}")
        chk("borrar cliente con deuda -> 409", r.status_code==409, f"-> {r.status_code}")

        # Mas facturas con vencimientos variados, para que los horizontes difieran
        for i, (dias, imp) in enumerate([(25, 12006), (55, 20300), (85, 42550), (-120, 5080.80)]):
            await c.post("/api/facturas", json={"cliente_id":cid,"folio":f"FAC0{3900+i}","importe":imp,"fecha_emision":str(hoy-timedelta(days=5)),"fecha_vencimiento":str(hoy+timedelta(days=dias))})

        print("\n=== PROYECCION ===")
        r = await c.post("/api/proyecciones", json={"escenarios":30000,"horizontes_dias":[30,60,90]})
        chk("proyeccion responde 200", r.status_code==200, f"-> {r.status_code}")
        p = r.json()
        chk("corrio FUERA del hilo principal", p["hilo"]!="MainThread", f"-> hilo '{p['hilo']}'")
        chk("los horizontes dan resultados distintos", len({t["esperado"] for t in p["tramos"]})>1,
            " / ".join(f"{t['dias']}d=${t['esperado']:,.0f}" for t in p["tramos"]))

        r = await c.post("/api/proyecciones", json={"escenarios":999})
        chk("escenarios por debajo del minimo -> 422", r.status_code==422, f"-> {r.status_code}")
        r = await c.post("/api/proyecciones", json={"escenarios":9999999})
        chk("escenarios por encima del tope -> 400", r.status_code==400, f"-> {r.status_code}")

        r = await c.post("/api/proyecciones/bloqueante", json={"escenarios":30000})
        chk("la version bloqueante corre en MainThread", r.json()["hilo"]=="MainThread", f"-> '{r.json()['hilo']}'")

        print("\n=== CONCURRENCIA REAL ===")
        latidos = 0
        async def latir():
            nonlocal latidos
            while True:
                await c.get("/api/proyecciones/latido"); latidos += 1
                await asyncio.sleep(0.02)
        t = asyncio.create_task(latir()); await asyncio.sleep(0.1); latidos = 0
        t0 = time.perf_counter()
        await c.post("/api/proyecciones", json={"escenarios":120000,"horizontes_dias":[30,60,90]})
        dur_hilo = time.perf_counter()-t0; lat_hilo = latidos
        await asyncio.sleep(0.1); latidos = 0
        t0 = time.perf_counter()
        await c.post("/api/proyecciones/bloqueante", json={"escenarios":120000,"horizontes_dias":[30,60,90]})
        dur_bloq = time.perf_counter()-t0; lat_bloq = latidos
        t.cancel()
        print(f"  con to_thread:   {dur_hilo:.2f}s de calculo, el servidor atendio {lat_hilo} latidos")
        print(f"  sin to_thread:   {dur_bloq:.2f}s de calculo, el servidor atendio {lat_bloq} latidos")
        chk("to_thread deja al servidor responder", lat_hilo > lat_bloq*3, f"({lat_hilo} vs {lat_bloq})")

        print(f"\n=== {ok} OK, {fail} fallos ===")
        return fail

raise SystemExit(asyncio.run(main()))
