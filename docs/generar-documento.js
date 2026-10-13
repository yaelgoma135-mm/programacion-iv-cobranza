/**
 * Genera el documento de Word del proyecto.
 *
 * Uso:  node docs/generar-documento.js
 */
const fs = require('node:fs');
const path = require('node:path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  ImageRun, PageBreak, LevelFormat, TableOfContents,
} = require('docx');

const DIR = __dirname;

// El anexo con la cadena de conexion es OPCIONAL y se pide con --con-conexion.
// La cadena NO se escribe aqui ni se pasa por la linea de comandos: se lee del
// .env, que es el unico lugar donde vive. Asi la copia del repositorio nunca
// puede llevar la contrasena por descuido.
const CON_CONEXION = process.argv.includes('--con-conexion');
const SALIDA = (() => {
  const i = process.argv.indexOf('--salida');
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : null;
})();

function cadenaDelEnv() {
  const archivo = path.join(DIR, '..', '.env');
  if (!fs.existsSync(archivo)) throw new Error('No existe el .env; no hay cadena que anexar.');
  for (const linea of fs.readFileSync(archivo, 'utf8').split(/\r?\n/)) {
    if (linea.startsWith('MONGODB_URI=')) return linea.slice('MONGODB_URI='.length).trim();
  }
  throw new Error('El .env no tiene MONGODB_URI.');
}
const CAPTURAS = path.join(DIR, 'capturas');
// Todo el texto va en negro. La jerarquia se sostiene con el tamano y la
// negrita de los titulos, no con el color.
const NEGRO = '000000';

// ─── Ayudas de formato ───────────────────────────────────────────────

const p = (texto, opts = {}) =>
  new Paragraph({ spacing: { after: 140, line: 276 }, ...opts,
    children: [new TextRun({ text: texto, size: 22, ...opts.run })] });

const h1 = (texto) =>
  new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 180 },
    children: [new TextRun({ text: texto, size: 30, bold: true, color: NEGRO })] });

const h2 = (texto) =>
  new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 260, after: 130 },
    children: [new TextRun({ text: texto, size: 25, bold: true, color: NEGRO })] });

/** Párrafo con partes en negrita: mezcla ['texto normal', ['negrita'], 'más'] */
const mixto = (partes) =>
  new Paragraph({ spacing: { after: 140, line: 276 },
    children: partes.map((x) =>
      Array.isArray(x)
        ? new TextRun({ text: x[0], size: 22, bold: true })
        : new TextRun({ text: x, size: 22 })) });

const codigo = (lineas) =>
  lineas.map((l, i) => new Paragraph({
    spacing: { after: i === lineas.length - 1 ? 160 : 0, line: 240 },
    shading: { type: ShadingType.CLEAR, fill: 'F2F2F2' },
    indent: { left: 280 },
    children: [new TextRun({ text: l || ' ', font: 'Consolas', size: 18 })] }));

const vineta = (texto) =>
  new Paragraph({ numbering: { reference: 'vinetas', level: 0 }, spacing: { after: 90 },
    children: [new TextRun({ text: texto, size: 22 })] });

const pie = (texto) =>
  new Paragraph({ spacing: { after: 240 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: texto, size: 18, italics: true, color: NEGRO })] });

function imagen(archivo, leyenda) {
  const ruta = path.join(CAPTURAS, archivo);
  if (!fs.existsSync(ruta)) return [p(`[falta la captura ${archivo}]`)];
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 80 },
      children: [new ImageRun({ data: fs.readFileSync(ruta), type: 'jpg',
        transformation: { width: 580, height: 435 } })] }),
    pie(leyenda),
  ];
}

function tabla(encabezados, filas, anchos) {
  const total = anchos.reduce((a, b) => a + b, 0);
  const celda = (texto, { negrita = false, fondo = null } = {}, ancho) =>
    new TableCell({
      width: { size: ancho, type: WidthType.DXA },
      shading: fondo ? { type: ShadingType.CLEAR, fill: fondo } : undefined,
      margins: { top: 60, bottom: 60, left: 110, right: 110 },
      children: [new Paragraph({ children: [new TextRun({ text: texto, size: 20, bold: negrita })] })],
    });
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: anchos,
    rows: [
      new TableRow({ tableHeader: true,
        children: encabezados.map((t, i) => celda(t, { negrita: true, fondo: 'DEEAF6' }, anchos[i])) }),
      ...filas.map((f) => new TableRow({ children: f.map((t, i) => celda(String(t), {}, anchos[i])) })),
    ],
  });
}

// ─── Contenido ───────────────────────────────────────────────────────

const portada = [
  new Paragraph({ spacing: { before: 2400, after: 120 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'Gestor de Cobranza', size: 56, bold: true, color: NEGRO })] }),
  new Paragraph({ spacing: { after: 900 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'con Proyección de Flujo por Simulación Monte Carlo', size: 28, color: NEGRO })] }),
  new Paragraph({ spacing: { after: 160 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'Proyecto final — Programación IV', size: 26, bold: true })] }),
  new Paragraph({ spacing: { after: 700 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'API REST con FastAPI, MongoDB Atlas y concurrencia no bloqueante', size: 22, color: NEGRO })] }),
  new Paragraph({ spacing: { after: 90 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'Yael Gómez', size: 24, bold: true })] }),
  new Paragraph({ spacing: { after: 90 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'Matrícula 224164501', size: 22 })] }),
  new Paragraph({ spacing: { after: 600 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'Profesora: Nicole Michelle Leyva Munguía', size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: new Date().toLocaleDateString('es-MX',
      { day: 'numeric', month: 'long', year: 'numeric' }), size: 20, color: NEGRO })] }),
  new Paragraph({ children: [new PageBreak()] }),
];

const cuerpo = [
  h1('1. Qué hace la aplicación'),
  mixto([
    'La aplicación administra clientes y sus facturas por cobrar, y proyecta ',
    ['cuánto dinero va a entrar en los próximos 30, 60 y 90 días'],
    ' usando simulación de Monte Carlo.',
  ]),
  p('El problema que resuelve es real y lo conozco de cerca: nadie sabe qué día va a pagar un cliente. Lo que sí se sabe es cómo ha pagado antes. Un cliente que históricamente se atrasa veinte días rara vez va a pagar al día, y tratarlo igual que a uno puntual produce proyecciones que nunca se cumplen.'),
  p('En lugar de dar un número único y falso —«en 30 días entran $400,000»— la aplicación simula decenas de miles de futuros posibles. En cada escenario sortea, para cada factura, si se cobra y en qué día, usando el atraso promedio y la variabilidad de ese cliente en concreto. Después reporta el rango: lo esperado, lo pesimista (percentil 10) y lo optimista (percentil 90).'),
  p('Esa decisión de diseño es la que hace que el proyecto tenga sentido para esta práctica: la simulación es genuinamente pesada, y eso obliga a resolver el problema de concurrencia de verdad y no de adorno.'),

  h2('Por qué este tema'),
  p('Elegí cobranza porque llevo meses trabajando en un sistema de contabilidad real, con conciliación bancaria y cartera vencida. Eso me permitió modelar el dominio con criterios que vienen de haber visto el problema: que el dinero debe guardarse en centavos enteros, que una factura puede pagarse en abonos parciales, que una factura muy vencida tiene menos probabilidad de cobrarse, y que un cliente no se puede eliminar si todavía debe.'),

  h1('2. Arquitectura'),
  p('El proyecto separa responsabilidades en capas, de modo que cada archivo tenga una sola razón para cambiar:'),
  ...codigo([
    'app/',
    '  main.py              FastAPI, lifespan y montaje de estáticos',
    '  config.py            Variables de entorno validadas con Pydantic',
    '  db.py                Conexión a MongoDB con Motor',
    '  esquemas.py          Modelos de Pydantic (entrada y salida)',
    '  rutas/',
    '    clientes.py        CRUD de clientes',
    '    facturas.py        CRUD de facturas y abonos',
    '    proyecciones.py    La parte con asyncio.to_thread()',
    '  servicios/',
    '    montecarlo.py      La simulación — código síncrono puro',
    'static/                Frontend: HTML, CSS y JS sin frameworks',
    'sembrar.py             Datos de ejemplo',
    'pruebas.py             Pruebas de extremo a extremo',
  ]),
  mixto([
    'La separación que más importa es la última: ',
    ['montecarlo.py no sabe nada de concurrencia'],
    '. Es código síncrono normal, sin un solo async. Quien lo llama decide mandarlo a un hilo. Eso permite probarlo y razonarlo sin pensar en el event loop, y es la razón de que ese archivo se pueda leer de corrido.',
  ]),

  h2('Variables de entorno'),
  p('Ninguna credencial está en el código. La configuración se lee del archivo .env mediante pydantic-settings, que además la valida al arrancar: si falta MONGODB_URI, la aplicación no inicia y lo dice.'),
  tabla(
    ['Variable', 'Obligatoria', 'Qué hace'],
    [
      ['MONGODB_URI', 'Sí', 'Cadena de conexión de MongoDB Atlas'],
      ['MONGODB_BASE', 'No', 'Base dentro del cluster (por omisión cobranza_escuela)'],
      ['MAX_ESCENARIOS', 'No', 'Tope de escenarios por petición (por omisión 200000)'],
    ],
    [2400, 1500, 5100],
  ),
  p(''),
  p('El archivo .env está en .gitignore y no se sube al repositorio. El .env.example documenta qué variables hacen falta sin revelar ningún valor.'),

  new Paragraph({ children: [new PageBreak()] }),

  h1('3. Base de datos: Motor y el ciclo de vida'),
  p('La conexión a MongoDB Atlas usa Motor, el driver asíncrono oficial, y se administra con el lifespan de FastAPI declarado con @asynccontextmanager:'),
  ...codigo([
    '@asynccontextmanager',
    'async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:',
    '    config = obtener_configuracion()',
    '    await conectar(config.mongodb_uri, config.mongodb_base)',
    '    try:',
    '        yield                 # aquí vive la aplicación',
    '    finally:',
    '        await desconectar()   # corre aunque el servidor falle',
  ]),
  mixto([
    'La razón de hacerlo así es concreta. Un AsyncIOMotorClient mantiene un ',
    ['pool de conexiones'],
    ' al cluster. Crearlo por petición agota el límite de conexiones de Atlas y paga un handshake TLS cada vez; crearlo al importar el módulo lo ataría al event loop equivocado cuando corren las pruebas. El lifespan lo abre una sola vez, cuando ya existe el loop correcto, y garantiza que se cierre al apagar.',
  ]),

  h2('El ping al arrancar'),
  p('Motor conecta de forma perezosa: no toca la red hasta la primera consulta. Eso significa que con una cadena de conexión inválida la aplicación arrancaría «bien» y el error aparecería hasta que un usuario pidiera algo. Por eso el arranque hace un ping explícito al cluster. Si no responde, la aplicación no inicia. Es preferible fallar al arrancar que fallar en producción.'),

  h2('Índices que protegen la corrección'),
  p('Los índices no se crearon para ganar velocidad sino para impedir datos inválidos. El del RFC es único: dos clientes con el mismo RFC son el mismo cliente, y dejar que se dupliquen rompería la proyección, que contaría su cartera dos veces.'),
  mixto([
    'Importa que sea ',
    ['la base de datos'],
    ' quien lo impida y no una consulta previa en la aplicación: entre un «¿ya existe?» y el insert cabe otra petición. El código captura el DuplicateKeyError y responde 409.',
  ]),

  h1('4. Validación con Pydantic'),
  p('Los esquemas de entrada y de salida están separados a propósito: lo que un cliente puede mandar no es lo mismo que lo que la API devuelve. Nadie debería poder fijar el id de un documento ni el saldo de una factura desde fuera.'),
  p('Algunas validaciones no solo rechazan, también normalizan:'),
  ...codigo([
    '@field_validator("rfc")',
    '@classmethod',
    'def rfc_en_mayusculas(cls, v: str) -> str:',
    '    limpio = v.strip().upper()',
    '    if not limpio.isalnum():',
    '        raise ValueError("El RFC solo puede tener letras y números")',
    '    return limpio',
  ]),
  p('Si el RFC entrara tal cual, «gso200317np9» y «GSO200317NP9» serían dos clientes distintos y el índice único no los detendría. Normalizar en la frontera evita el problema en todas las capas de adentro.'),
  p('Otra validación necesita dos campos a la vez: una factura no puede vencer antes de existir. Eso se resuelve con un validador que lee el campo anterior ya validado.'),

  h2('Códigos HTTP y por qué cada uno'),
  tabla(
    ['Código', 'Cuándo se usa'],
    [
      ['201', 'Al crear. Hay un recurso nuevo, no es un 200 cualquiera.'],
      ['204', 'Al borrar. Se hizo y no hay nada que devolver.'],
      ['400', 'Los datos son válidos pero la operación no tiene sentido (abonar más de lo que se debe).'],
      ['404', 'El recurso no existe. También si el id tiene forma inválida.'],
      ['409', 'Choca con algo que ya está: RFC repetido, o borrar un cliente que aún debe.'],
      ['422', 'Lo pone Pydantic solo cuando el cuerpo no cumple el esquema.'],
    ],
    [1200, 7800],
  ),
  p(''),
  mixto([
    'La decisión de responder ',
    ['404 y no 400'],
    ' ante un id con forma inválida es deliberada: desde fuera, /api/clientes/abc simplemente no existe, y distinguirlo de un id válido inexistente solo le diría a un atacante qué ids tienen la forma correcta.',
  ]),

  new Paragraph({ children: [new PageBreak()] }),

  h1('5. Concurrencia: el núcleo del proyecto'),
  mixto([
    'FastAPI corre sobre un ',
    ['event loop de un solo hilo'],
    '. Mientras una corrutina no haga await, nadie más avanza. Un cálculo de varios segundos metido directo en una ruta async deja al servidor mudo para todos los usuarios, no solo para quien lo pidió.',
  ]),
  p('La simulación de Monte Carlo es exactamente ese caso: 200,000 escenarios sobre 13 facturas son más de dos millones y medio de sorteos aleatorios y sumas, en Python puro, sin numpy. Tarda más de tres segundos.'),
  p('La solución es una línea:'),
  ...codigo([
    'resultado = await asyncio.to_thread(',
    '    simular_cobranza,',
    '    facturas,',
    '    solicitud.escenarios,',
    '    solicitud.horizontes_dias,',
    ')',
  ]),
  p('asyncio.to_thread() manda la función síncrona a un hilo del pool y devuelve un awaitable. El await le cede el control al event loop, que sigue atendiendo peticiones mientras el hilo trabaja.'),

  h2('Cómo lo hice demostrable'),
  p('Que algo funcione y que se pueda comprobar que funciona son dos cosas distintas. Para que la diferencia se vea y no haya que creerme nada, implementé tres mecanismos:'),
  vineta('Dos rutas que calculan exactamente lo mismo: /api/proyecciones usa to_thread y /api/proyecciones/bloqueante no. La segunda existe solo para demostrar el problema; en código real no se escribiría.'),
  vineta('La respuesta incluye el campo «hilo» con el nombre del hilo donde corrió el cálculo. Si dijera MainThread, el servidor habría estado bloqueado. El dato lo pone el servidor, no se puede fingir desde el navegador.'),
  vineta('La interfaz tiene un latido que llama al servidor cada 400 ms y muestra cuánto tarda en responder. Si el servidor se bloquea, se pone rojo a la vista de todos.'),

  h2('La medición'),
  p('Desde la consola del navegador medí cuántas peticiones alcanza a atender el servidor mientras corre cada versión, con 200,000 escenarios en ambas:'),
  tabla(
    ['Versión', 'Duración del cálculo', 'Latidos atendidos', 'Demora máxima'],
    [
      ['Con asyncio.to_thread()', '3,573 ms', '22', '435 ms'],
      ['Sin asyncio.to_thread()', '3,220 ms', '2', '3,113 ms'],
    ],
    [2900, 2100, 2100, 1900],
  ),
  p(''),
  mixto([
    'El dato que lo resume es la demora máxima. Con to_thread, ningún latido esperó más de medio segundo. Sin él, ',
    ['un latido quedó colgado los 3.1 segundos completos'],
    ': el servidor no pudo atender a nadie durante todo el cálculo.',
  ]),

  new Paragraph({ children: [new PageBreak()] }),
  h2('Evidencia visual'),
  ...imagen('03-sin-bloquear-verde.jpg',
    'Figura 1. Durante el cálculo con asyncio.to_thread(): el indicador sigue en verde y el servidor responde en 34 ms.'),
  ...imagen('04-bloqueado-rojo.jpg',
    'Figura 2. El mismo cálculo sin to_thread: el indicador se pone rojo y marca 2.9 segundos sin responder.'),
  p('Las dos capturas se tomaron durante el cálculo, con los mismos 200,000 escenarios. La única diferencia entre una y otra es asyncio.to_thread().'),

  new Paragraph({ children: [new PageBreak()] }),

  h1('6. El modelo de simulación'),
  p('Cada escenario recorre todas las facturas por cobrar y decide dos cosas por cada una:'),
  vineta('Si se cobra. Una factura muy vencida tiene menos probabilidad de cobrarse: cada 90 días vencida se castiga un 20% de probabilidad, con piso en 30%. No pretende ser un modelo de riesgo, pero evita el supuesto ingenuo de que todo se cobra.'),
  vineta('En qué día. Se sortea el atraso de una distribución normal centrada en el atraso promedio del cliente, con su variabilidad como desviación estándar. Un pago no puede ocurrir en el pasado, así que lo vencido se cobra hoy o después.'),
  p('Con los totales de todos los escenarios ordenados se obtienen los percentiles. Deliberadamente no se interpola: con dinero en centavos, un percentil interpolado da un importe que ningún escenario produjo realmente.'),
  p('La función acepta una semilla opcional que fija el azar. Sirve para las pruebas —la misma entrada da siempre el mismo resultado— y en producción se deja sin fijar.'),
  ...imagen('01-proyeccion-resultados.jpg',
    'Figura 3. Resultado de la proyección: 50,000 escenarios sobre una cartera de $223,635.00, calculados en 811 ms dentro del hilo asyncio_0.'),

  h1('7. Frontend'),
  p('La interfaz es HTML, CSS y JavaScript puro, sin frameworks ni dependencias, servida por la misma aplicación con StaticFiles. Al compartir origen con la API no hace falta configurar CORS ni levantar un segundo servidor.'),
  p('Un detalle de orden que importa: el montaje de estáticos va al final de main.py. Montar en «/» captura todo lo que no haya casado antes, así que si se montara primero se comería las rutas de la API.'),
  p('Todo el diálogo con el servidor pasa por fetch(). Los errores de la API se muestran tal como los manda el servidor, incluidos los de validación de Pydantic, que vienen como lista de problemas por campo y se arman legibles antes de mostrarlos.'),
  ...imagen('02-clientes.jpg',
    'Figura 4. Alta y listado de clientes. Cada cliente tiene su propio perfil de pago, que es lo que alimenta la simulación.'),

  h2('Un error que encontré probando'),
  p('La primera versión del latido usaba setInterval cada 400 ms sin esperar a que la petición anterior terminara. Durante un bloqueo se encimaban diez peticiones y, al liberarse el servidor, resolvían todas juntas; la última en pintar era una recién iniciada y rápida. La interfaz mostraba «servidor vivo · 7 ms» justo después de haber estado congelada tres segundos.'),
  mixto([
    'Medía bien y mentía al pintar. Lo corregí con un ciclo secuencial: una sola petición en vuelo a la vez, y un vigilante que mira cuánto lleva esperando ',
    ['esa misma'],
    ' petición. Lo encontré porque tomé una captura durante el bloqueo y el indicador salía verde, cuando los números decían lo contrario.',
  ]),

  new Paragraph({ children: [new PageBreak()] }),

  h1('8. Pruebas'),
  p('El proyecto incluye 21 pruebas de extremo a extremo que ejercitan la aplicación real por HTTP, no las funciones por separado. Corren contra una base de datos en memoria, así que funcionan en cualquier máquina sin credenciales y sin dejar basura en el cluster.'),
  p('Cubren los casos correctos y, sobre todo, los incorrectos: RFC duplicado, nombre demasiado corto, factura con cliente inexistente, abono mayor al saldo, borrar un cliente que todavía debe, escenarios fuera de rango. La última sección es la medición de concurrencia descrita arriba.'),
  ...codigo([
    '=== 21 OK, 0 fallos ===',
    '',
    '  OK  RFC duplicado -> 409',
    '  OK  abono mayor al saldo -> 400',
    '  OK  borrar cliente con deuda -> 409',
    '  OK  corrio FUERA del hilo principal -> hilo \'asyncio_0\'',
    '  OK  to_thread deja al servidor responder (14 vs 0)',
  ]),
  p('Dos de esas pruebas encontraron errores reales durante el desarrollo. La primera: la API devolvía «_id» en lugar de «id», porque en Pydantic el alias de un campo se usa también al serializar; se corrige con validation_alias, que aplica solo a la entrada. La segunda fue del propio arnés de pruebas, no del código, y vale la pena contarla porque casi la doy por buena: la prueba de RFC duplicado pasaba sin probar nada, porque los índices se crean en el lifespan y httpx no lo dispara.'),

  h2('El error que ninguna prueba podía encontrar'),
  p('Con las 21 pruebas en verde levanté el servidor en una consola normal de Windows y no arrancó. No alcanzó a atender una sola petición:'),
  ...codigo([
    "UnicodeEncodeError: 'charmap' codec can't encode character '\u2713'",
    'ERROR:    Application startup failed. Exiting.',
  ]),
  p('El mensaje de bienvenida llevaba una palomita «✓». La consola de Windows no usa UTF-8 sino cp1252, que no tiene ese carácter; el print lanzaba la excepción dentro del lifespan y la aplicación moría durante el arranque, antes de abrir el puerto.'),
  mixto([
    'Lo interesante no es el error sino por qué tardó tanto en salir: yo lo probaba desde una terminal configurada en UTF-8, y esa terminal ',
    ['escondía el problema'],
    '. Las pruebas tampoco podían verlo, porque capturan la salida en vez de escribirla en una consola real. Era un fallo que solo existía en la computadora de alguien más.',
  ]),
  p('Lo corregí en dos capas. Los mensajes de arranque y cierre quedaron en ASCII puro; y sys.stdout se reconfigura con errors="replace" al importar la aplicación, de modo que ningún print futuro pueda repetir el accidente. La segunda capa importa más que la primera: un saludo en consola no debería tener la capacidad de impedir que arranque el servidor.'),

  h1('9. Cómo ejecutarlo'),

  h2('Lo que debe estar listo en MongoDB Atlas'),
  vineta('Un cluster M0 (el gratuito) y un usuario de base de datos con permiso de lectura y escritura.'),
  vineta('La cadena de conexión que entrega Atlas en Connect → Drivers → Python, con la contraseña real sustituida en el marcador <db_password>. Esa cadena va en el archivo .env, que no se sube al repositorio.'),
  vineta('En Network Access, una entrada 0.0.0.0/0 en estado Active. Atlas bloquea las conexiones por IP de origen, y si solo está autorizada la IP de quien desarrolló el proyecto, al abrirlo desde otra computadora no falla con un mensaje claro: falla con un ServerSelectionTimeoutError que parece un error del programa.'),
  vineta('La base cobranza_escuela no hace falta crearla a mano. MongoDB la crea en el primer insert.'),

  ...codigo([
    '# 1. Instalar dependencias',
    'pip install -r requirements.txt',
    '',
    '# 2. Configurar la base de datos',
    'copy .env.example .env',
    '#    editar .env y poner la cadena de MongoDB Atlas',
    '',
    '# 3. Cargar datos de ejemplo (opcional)',
    'py sembrar.py',
    '',
    '# 4. Levantar el servidor',
    'py -m uvicorn app.main:app --reload',
  ]),
  p('La aplicación queda en http://localhost:8000 y la documentación interactiva de la API, generada automáticamente por FastAPI, en http://localhost:8000/docs.'),

  h2('Para comprobar la concurrencia'),
  vineta('Subir los escenarios a 150,000 o más.'),
  vineta('Pulsar «Proyectar sin bloquear»: el latido de arriba sigue pulsando en verde y el resultado dice que corrió en un hilo asyncio_N.'),
  vineta('Pulsar «Proyectar bloqueando»: el latido se pone rojo y marca los segundos que lleva sin responder, hasta que el cálculo termina.'),

  h1('10. Conclusiones'),
  p('Lo que más me costó de este proyecto no fue escribir el código sino comprobar que hacía lo que yo creía. Cuatro veces di algo por bueno y al medirlo resultó que no: el latido que pintaba verde mientras el servidor estaba congelado, la prueba de RFC duplicado que pasaba sin índice, la respuesta que devolvía «_id» donde yo esperaba «id», y un servidor que no arrancaba en cuanto salía de mi terminal. Las cuatro las encontré corriendo la aplicación, no leyéndola.'),
  p('De las cuatro, la última es la que más me enseñó. Las otras tres estaban en el código y podía encontrarlas yo solo; esa dependía del entorno de quien lo ejecutara, y mi propia forma de probar era justamente lo que la ocultaba. Un proyecto no está terminado cuando funciona en la máquina donde se escribió.'),
  mixto([
    'Sobre el tema de la práctica: entendí que ',
    ['asyncio no es paralelismo'],
    '. Un servidor async atiende muchas peticiones a la vez porque casi todas pasan el tiempo esperando —a la base de datos, a la red— y durante esa espera cede el control. Pero un cálculo de CPU no espera nada: ocupa el procesador de principio a fin, y ahí el modelo async no ayuda por sí solo. asyncio.to_thread() es el puente entre los dos mundos.',
  ]),
  p('También me quedó claro por qué conviene que el código pesado no sepa nada de concurrencia. La simulación es una función síncrona normal que recibe datos y devuelve datos. Quien la llama decide mandarla a un hilo. Si mañana hiciera falta correrla en un proceso aparte o en una máquina distinta, la función no cambiaría.'),
];

// ─── Anexo opcional con la cadena de conexion ────────────────────────

const anexo = !CON_CONEXION ? [] : [
  new Paragraph({ children: [new PageBreak()] }),

  h1('Anexo. Datos de conexión y ejecución'),
  p('Este anexo acompaña solo a la copia entregada. No forma parte del repositorio público, porque incluye la contraseña del usuario de base de datos.'),

  h2('Cadena de conexión'),
  p('El proyecto lee la configuración de un archivo .env que no se versiona. Hay que crearlo a partir de .env.example y dejar la variable MONGODB_URI con este valor:'),
  ...codigo(['MONGODB_URI=' + cadenaDelEnv()]),
  p('Las otras dos variables ya vienen con el valor correcto en .env.example: MONGODB_BASE=cobranza_escuela y MAX_ESCENARIOS=200000.'),

  h2('Pasos para ejecutarlo'),
  ...codigo([
    '# 1. Instalar dependencias (requiere Python 3.11 o superior)',
    'pip install -r requirements.txt',
    '',
    '# 2. Crear el archivo de configuracion',
    'copy .env.example .env',
    '#    y pegar la cadena de arriba en MONGODB_URI',
    '',
    '# 3. Levantar el servidor',
    'py -m uvicorn app.main:app --reload',
  ]),
  p('La aplicación queda en http://localhost:8000 y la documentación interactiva de la API en http://localhost:8000/docs.'),
  p('La base ya tiene cinco clientes y trece facturas cargados, así que el paso de sembrar.py no hace falta. Si se quisiera volver a empezar desde cero: py sembrar.py (borra y vuelve a cargar los datos de ejemplo).'),
  p('El acceso por IP ya está abierto en Atlas, de modo que no hay nada que configurar del lado de la red.'),

  h2('Si algo falla'),
  vineta('ServerSelectionTimeoutError: el cluster no acepta la IP de origen. Se resuelve en Atlas, en Network Access, con una entrada 0.0.0.0/0 en estado Active. Debería estar ya puesta.'),
  vineta('Authentication failed: la contraseña dentro de la cadena no es correcta, o se copió con un salto de línea en medio. Debe ir todo en un solo renglón.'),
  vineta('La aplicación no arranca y no dice por qué: casi siempre es que falta el archivo .env, o que la línea tiene espacios alrededor del signo igual. Debe quedar MONGODB_URI=mongodb+srv://... sin comillas.'),

  h2('Para revisar la parte de concurrencia'),
  vineta('En la pestaña «Proyección», subir los escenarios a 150,000 o más.'),
  vineta('Pulsar «Proyectar sin bloquear»: el indicador de arriba a la derecha sigue en verde y el resultado dice que el cálculo corrió en un hilo asyncio_N.'),
  vineta('Pulsar «Proyectar bloqueando»: el mismo cálculo, sin asyncio.to_thread(). El indicador se pone rojo y cuenta los segundos que el servidor lleva sin responder.'),
  vineta('Las pruebas automáticas se corren con: pip install -r requirements-dev.txt y luego py pruebas.py. Usan una base en memoria, así que no tocan el cluster.'),
];

// ─── Armado ──────────────────────────────────────────────────────────

const doc = new Document({
  creator: 'Yael Gómez — 224164501',
  title: 'Gestor de Cobranza con Proyección Monte Carlo',
  description: 'Proyecto final de Programación IV',
  // Word trae sus estilos Heading1/Heading2 en azul. Cada titulo ya lleva el
  // color directo encima, pero el estilo tambien se redefine: si no, el panel
  // de navegacion o un indice generado los seguirian pintando de azul.
  styles: {
    default: {
      heading1: { run: { color: NEGRO } },
      heading2: { run: { color: NEGRO } },
      heading3: { run: { color: NEGRO } },
    },
  },
  numbering: {
    config: [{
      reference: 'vinetas',
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: '•',
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 460, hanging: 240 } } },
      }],
    }],
  },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 },
      margin: { top: 1300, right: 1300, bottom: 1300, left: 1300 } } },
    children: [...portada, ...cuerpo, ...anexo],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const salida = SALIDA || path.join(DIR, 'Proyecto Programacion IV - Gestor de Cobranza.docx');
  fs.writeFileSync(salida, buf);
  console.log(`Generado: ${salida} (${Math.round(buf.length / 1024)} KB)`);
});
