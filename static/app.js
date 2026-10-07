/**
 * Frontend en JavaScript puro — sin frameworks ni dependencias.
 *
 * Todo el diálogo con la API pasa por fetch(). Lo único que vale la pena
 * explicar es el latido: late contra el servidor cada 400 ms y mide cuánto
 * tarda en contestar. Mientras la proyección corre en un hilo, el latido sigue;
 * si alguien llama a la versión bloqueante, se congela a la vista. Esa es la
 * demostración de concurrencia que pide la práctica, y no hay forma de fingirla
 * porque el dato lo pone el propio servidor.
 */

const $ = (sel) => document.querySelector(sel);
const pesos = (n) =>
  n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 2 });

/** Llama a la API y convierte cualquier error en una excepción con el detalle del servidor. */
async function api(ruta, opciones = {}) {
  const resp = await fetch(ruta, {
    headers: { 'Content-Type': 'application/json' },
    ...opciones,
  });
  if (resp.status === 204) return null;
  const cuerpo = await resp.json().catch(() => null);
  if (!resp.ok) {
    // FastAPI manda el error en `detail`; si es de validación de Pydantic,
    // viene como lista de problemas por campo y hay que armarlo legible.
    const d = cuerpo?.detail ?? cuerpo?.detalle;
    const texto = Array.isArray(d)
      ? d.map((e) => `${e.loc?.slice(1).join('.') ?? ''}: ${e.msg}`).join(' · ')
      : (d ?? `Error ${resp.status}`);
    throw new Error(texto);
  }
  return cuerpo;
}

function avisar(texto, tipo = '') {
  const el = document.createElement('div');
  el.className = `mensaje ${tipo}`;
  el.textContent = texto;
  $('#avisos').append(el);
  setTimeout(() => el.remove(), 4200);
}

// ───────────────────────── Latido ─────────────────────────

/**
 * Un ÚNICO latido en vuelo a la vez, en ciclo secuencial.
 *
 * Con setInterval se lanzaba uno cada 400 ms sin esperar al anterior: durante
 * un bloqueo se encimaban diez, y al liberarse el servidor resolvían todos
 * juntos. El último en pintar era uno recién iniciado —y rápido—, así que la
 * interfaz mostraba "servidor vivo · 7 ms" justo después de haber estado
 * congelada tres segundos. Medía bien y mentía al pintar.
 *
 * Así solo hay una petición viva, y el vigilante puede mirar cuánto lleva
 * esperando esa misma.
 */
let latidoEnVuelo = null; // instante en que arrancó la petición en curso

function pintarVivo(ms, hilo) {
  $('#pulso').className = 'pulso vivo';
  $('#latido-estado').textContent = `servidor vivo · ${ms} ms`;
  $('#latido-detalle').textContent = `hilo: ${hilo}`;
}

function pintarBloqueado(esperando) {
  $('#pulso').className = 'pulso congelado';
  $('#latido-estado').textContent = `BLOQUEADO · ${(esperando / 1000).toFixed(1)} s sin responder`;
  $('#latido-detalle').textContent = 'el event loop está ocupado';
}

async function cicloLatido() {
  for (;;) {
    const t0 = performance.now();
    latidoEnVuelo = t0;
    try {
      const r = await api('/api/proyecciones/latido');
      pintarVivo(Math.round(performance.now() - t0), r.hilo);
    } catch {
      $('#latido-estado').textContent = 'sin respuesta';
    }
    latidoEnVuelo = null;
    await new Promise((r) => setTimeout(r, 400));
  }
}

/**
 * Si la petición en vuelo lleva más de un segundo sin volver, el servidor está
 * bloqueado. Se vigila aparte porque cuando el event loop se congela el fetch
 * no falla: simplemente no regresa, y no hay error que atrapar.
 */
function vigilarLatido() {
  if (latidoEnVuelo === null) return;
  const esperando = performance.now() - latidoEnVuelo;
  if (esperando > 1000) pintarBloqueado(esperando);
}

setInterval(vigilarLatido, 100);
cicloLatido();

// ───────────────────────── Pestañas ─────────────────────────

$('#pestanas').addEventListener('click', (e) => {
  const boton = e.target.closest('button');
  if (!boton) return;
  document.querySelectorAll('#pestanas button').forEach((b) => b.classList.remove('activa'));
  boton.classList.add('activa');
  document.querySelectorAll('.panel').forEach((p) => p.classList.add('oculto'));
  $(`#${boton.dataset.panel}`).classList.remove('oculto');
});

// ───────────────────────── Clientes ─────────────────────────

async function cargarClientes() {
  try {
    const clientes = await api('/api/clientes');
    pintarClientes(clientes);
    llenarSelectClientes(clientes);
  } catch (err) {
    $('#tabla-clientes').innerHTML = `<p class="sutil">No se pudieron cargar: ${err.message}</p>`;
  }
}

function pintarClientes(clientes) {
  if (!clientes.length) {
    $('#tabla-clientes').innerHTML = '<p class="sutil">Todavía no hay clientes.</p>';
    return;
  }
  $('#tabla-clientes').innerHTML = `
    <table>
      <thead><tr>
        <th>Nombre</th><th>RFC</th><th class="num">Crédito</th>
        <th class="num">Atraso prom.</th><th class="num">Variabilidad</th><th></th>
      </tr></thead>
      <tbody>${clientes.map((c) => `
        <tr>
          <td>${c.nombre}</td>
          <td class="sutil">${c.rfc}</td>
          <td class="num">${c.dias_credito} d</td>
          <td class="num">${c.dias_atraso_promedio} d</td>
          <td class="num">± ${c.variabilidad_atraso} d</td>
          <td class="num"><button class="mini" data-borrar-cliente="${c.id}">Eliminar</button></td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

function llenarSelectClientes(clientes) {
  $('#select-cliente').innerHTML = clientes.length
    ? clientes.map((c) => `<option value="${c.id}">${c.nombre} — ${c.rfc}</option>`).join('')
    : '<option value="">Primero registre un cliente</option>';
}

$('#form-cliente').addEventListener('submit', async (e) => {
  e.preventDefault();
  const datos = Object.fromEntries(new FormData(e.target));
  ['dias_credito', 'dias_atraso_promedio', 'variabilidad_atraso'].forEach((k) => {
    datos[k] = Number(datos[k]);
  });
  try {
    await api('/api/clientes', { method: 'POST', body: JSON.stringify(datos) });
    avisar('Cliente guardado', 'exito');
    e.target.reset();
    cargarClientes();
  } catch (err) {
    avisar(err.message, 'error');
  }
});

$('#tabla-clientes').addEventListener('click', async (e) => {
  const id = e.target.dataset?.borrarCliente;
  if (!id) return;
  try {
    await api(`/api/clientes/${id}`, { method: 'DELETE' });
    avisar('Cliente eliminado', 'exito');
    cargarClientes();
  } catch (err) {
    avisar(err.message, 'error');
  }
});

// ───────────────────────── Facturas ─────────────────────────

async function cargarFacturas() {
  try {
    const [facturas, clientes] = await Promise.all([api('/api/facturas'), api('/api/clientes')]);
    const nombre = Object.fromEntries(clientes.map((c) => [c.id, c.nombre]));
    pintarFacturas(facturas, nombre);
  } catch (err) {
    $('#tabla-facturas').innerHTML = `<p class="sutil">No se pudieron cargar: ${err.message}</p>`;
  }
}

function pintarFacturas(facturas, nombre) {
  if (!facturas.length) {
    $('#tabla-facturas').innerHTML = '<p class="sutil">Todavía no hay facturas.</p>';
    return;
  }
  $('#tabla-facturas').innerHTML = `
    <table>
      <thead><tr>
        <th>Folio</th><th>Cliente</th><th class="num">Importe</th><th class="num">Saldo</th>
        <th>Vence</th><th class="num">Vencida</th><th>Estado</th><th></th>
      </tr></thead>
      <tbody>${facturas.map((f) => `
        <tr>
          <td>${f.folio}</td>
          <td class="sutil">${nombre[f.cliente_id] ?? '—'}</td>
          <td class="num">${pesos(f.importe)}</td>
          <td class="num">${pesos(f.saldo)}</td>
          <td class="sutil">${f.fecha_vencimiento}</td>
          <td class="num">${f.dias_vencida > 0 ? `${f.dias_vencida} d` : '—'}</td>
          <td><span class="etiqueta ${f.estado}">${f.estado}</span></td>
          <td class="num">
            ${f.saldo > 0 ? `<button class="mini" data-abonar="${f.id}" data-saldo="${f.saldo}">Abonar</button>` : ''}
            <button class="mini" data-borrar-factura="${f.id}">Eliminar</button>
          </td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

$('#form-factura').addEventListener('submit', async (e) => {
  e.preventDefault();
  const datos = Object.fromEntries(new FormData(e.target));
  datos.importe = Number(datos.importe);
  try {
    await api('/api/facturas', { method: 'POST', body: JSON.stringify(datos) });
    avisar('Factura registrada', 'exito');
    e.target.reset();
    cargarFacturas();
  } catch (err) {
    avisar(err.message, 'error');
  }
});

$('#tabla-facturas').addEventListener('click', async (e) => {
  const borrar = e.target.dataset?.borrarFactura;
  const abonar = e.target.dataset?.abonar;
  try {
    if (borrar) {
      await api(`/api/facturas/${borrar}`, { method: 'DELETE' });
      avisar('Factura eliminada', 'exito');
      cargarFacturas();
    } else if (abonar) {
      const saldo = Number(e.target.dataset.saldo);
      const texto = prompt(`Importe del abono (saldo ${pesos(saldo)}):`, saldo.toFixed(2));
      if (texto === null) return;
      await api(`/api/facturas/${abonar}/pagos`, {
        method: 'POST',
        body: JSON.stringify({ importe: Number(texto) }),
      });
      avisar('Abono registrado', 'exito');
      cargarFacturas();
    }
  } catch (err) {
    avisar(err.message, 'error');
  }
});

// ───────────────────────── Proyección ─────────────────────────

async function proyectar(ruta, boton) {
  const escenarios = Number($('#escenarios').value);
  const horizontes = $('#horizontes').value
    .split(',')
    .map((s) => Number(s.trim()))
    .filter((n) => Number.isFinite(n) && n > 0);

  $('#btn-proyectar').disabled = true;
  $('#btn-bloquear').disabled = true;
  $('#proyeccion-resultado').innerHTML = '<p class="sutil">Simulando…</p>';
  const t0 = performance.now();

  try {
    const r = await api(ruta, {
      method: 'POST',
      body: JSON.stringify({ escenarios, horizontes_dias: horizontes }),
    });
    pintarProyeccion(r, Math.round(performance.now() - t0), boton === 'bloqueante');
  } catch (err) {
    $('#proyeccion-resultado').innerHTML = '';
    avisar(err.message, 'error');
  } finally {
    $('#btn-proyectar').disabled = false;
    $('#btn-bloquear').disabled = false;
  }
}

function pintarProyeccion(r, msTotal, fueBloqueante) {
  const enHilo = r.hilo !== 'MainThread';
  $('#proyeccion-resultado').innerHTML = `
    <div class="resumen">
      <div class="dato">
        <div class="valor">${pesos(r.cartera_total)}</div>
        <div class="etq">Cartera por cobrar</div>
      </div>
      <div class="dato">
        <div class="valor">${r.facturas_consideradas}</div>
        <div class="etq">Facturas simuladas</div>
      </div>
      <div class="dato">
        <div class="valor">${r.escenarios.toLocaleString('es-MX')}</div>
        <div class="etq">Escenarios</div>
      </div>
      <div class="dato ${enHilo ? 'destaca' : ''}">
        <div class="valor">${r.milisegundos_calculo} ms</div>
        <div class="etq">Cálculo en <strong>${r.hilo}</strong></div>
      </div>
    </div>

    <p class="aviso" style="${enHilo ? 'border-color:var(--verde);color:var(--verde);background:rgba(47,191,113,0.09)' : ''}">
      ${enHilo
        ? `El cálculo corrió en el hilo <strong>${r.hilo}</strong>, no en el principal: el servidor nunca dejó de atender.`
        : `El cálculo corrió en <strong>MainThread</strong> — el event loop estuvo bloqueado ${r.milisegundos_calculo} ms y el servidor no pudo atender a nadie.`}
    </p>

    <table style="margin-top:16px">
      <thead><tr>
        <th>Horizonte</th><th class="num">Pesimista (p10)</th>
        <th class="num">Esperado</th><th class="num">Optimista (p90)</th>
        <th class="num">% cartera</th>
      </tr></thead>
      <tbody>${r.tramos.map((t) => `
        <tr>
          <td><strong>${t.dias} días</strong></td>
          <td class="num sutil">${pesos(t.pesimista)}</td>
          <td class="num"><strong>${pesos(t.esperado)}</strong></td>
          <td class="num sutil">${pesos(t.optimista)}</td>
          <td class="num">
            ${t.porcentaje_cartera}%
            <div class="barra"><div style="width:${Math.min(100, t.porcentaje_cartera)}%"></div></div>
          </td>
        </tr>`).join('')}
      </tbody>
    </table>
    <p class="sutil" style="margin-top:10px">
      Ida y vuelta completa: ${msTotal} ms${fueBloqueante ? ' · petición bloqueante' : ''}
    </p>`;
}

$('#btn-proyectar').addEventListener('click', () => proyectar('/api/proyecciones', 'hilo'));
$('#btn-bloquear').addEventListener('click', () => proyectar('/api/proyecciones/bloqueante', 'bloqueante'));

// ───────────────────────── Arranque ─────────────────────────

const hoy = new Date().toISOString().slice(0, 10);
const en30 = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);
document.querySelector('[name=fecha_emision]').value = hoy;
document.querySelector('[name=fecha_vencimiento]').value = en30;

cargarClientes();
cargarFacturas();
