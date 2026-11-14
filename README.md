# 📡 Radar de empleo

Bot que busca ofertas de trabajo cada 3 horas, **descarta las sospechosas**, calcula **qué tanto encajan con mi perfil** y me avisa por **Telegram** con sugerencias para ajustar el CV a cada oferta.

No se postula solo: **la decisión de mandar el CV siempre es mía.** Postularse en automático a cientos de avisos es mala idea: los reclutadores lo notan y la mayoría de los portales lo prohíbe.

```
🟢 89% · Desarrollador Java Junior
🏢 Acme Software · 📍 Remoto (Argentina) · Get on Board
🎯 Nivel: junior
✅ Tenés: java, spring boot, api rest, sql, junit, docker, git
❌ Te falta: microservicios

📝 Para tu CV:
• Poné TurnoBot primero en Proyectos: muestra java, api rest, junit y docker, que pide el aviso.
• En Habilidades, empezá por java, spring boot, api rest, sql y junit.
• Te falta microservicios. No lo agregues si no lo usaste: en la entrevista decí que lo estás aprendiendo.

[ Ver oferta ↗ ]
```

## Cómo decide

| Paso | Qué hace |
|---|---|
| **1. Busca** | Consulta fuentes con acceso público para programas: [Get on Board](https://www.getonbrd.com) (empleo tech de Latinoamérica) y [Remotive](https://remotive.com) (remoto internacional). Además lee las **alertas por mail** de LinkedIn, Computrabajo, Bumeran, ZonaJobs e Indeed (sin scraping, que esos sitios prohíben). Si una fuente falla, las demás siguen, con pausas y reintentos para no saturarlas. |
| **2. Anti-estafas** | Señales **graves** (descartan solas): te piden plata, datos bancarios o DNI, o prometen ganancias fáciles. Señales **medias** (dos o más descartan): contacto solo por WhatsApp o Telegram, mail de Gmail, empresa anónima, descripción vaga, aviso de hace más de 45 días. |
| **3. Nivel** | Descarta lo que pide semi senior o senior. Lee el título y, en la descripción, los años de experiencia pedidos ("3 años" → semi senior). No se confunde con frases como *"vas a trabajar con seniors"*. |
| **4. Ubicación** | Descarta remotos restringidos a otros países ("USA only") y presenciales fuera de mi zona. Empresas de cualquier país que contratan desde Argentina o LATAM entran. |
| **5. Idioma** | Con inglés básico (`ingles: basico` en el perfil), descarta avisos escritos en inglés o que piden inglés intermedio, avanzado o bilingüe. |
| **6. Compatibilidad** | Detecta las tecnologías del aviso con un catálogo de sinónimos y calcula el % que tengo. Las del título pesan el doble. |
| **7. Sugerencias** | Qué proyecto poner primero, en qué orden listar las habilidades y cómo escribir cada tecnología como la escribe el aviso. **Nunca agrega habilidades que no tengo.** |

**El catálogo solo agrupa nombres que significan lo mismo** (*Postgres* = *PostgreSQL*). Herramientas parecidas pero distintas van separadas (*Maven ≠ Gradle*), para que el radar no diga que sé algo que no usé.

## Seguridad

| Riesgo | Cómo se cubre |
|---|---|
| Que alguien use el token de Telegram o la clave del Gmail | Viven solo en *GitHub Secrets* (cifrados, no aparecen en los registros). Un pull request desde otro repo no tiene acceso a los secretos. |
| Mails falsos que imitan a LinkedIn con links a sitios truchos | Solo se aceptan links cuyo **dominio real** es el del sitio y con `https` (test incluido con links disfrazados). |
| Botones o comandos de otra persona | Solo se procesan los que vienen de tu `chat_id`. |
| Texto malicioso en un aviso | Todo se escapa antes de mandarlo a Telegram; los avisos nunca se ejecutan, solo se leen como texto. |
| Que se vean tus postulaciones | Archivo cifrado; los registros públicos solo muestran cantidades. |
| Acceso a tu buzón | Gmail **separado**, solo para alertas, abierto en **solo lectura**. |

El radar corre en los servidores de GitHub: no se conecta nunca a tu computadora.

## Estructura

```
perfil.yaml              ← mis habilidades, nivel, ubicaciones y proyectos (se edita sin tocar código)
cv.txt                   ← texto del CV, sin datos de contacto
radar_empleo/
├── catalogo.py          tecnologías y sus sinónimos
├── analisis.py          detección de tecnologías, nivel y % de compatibilidad
├── antiestafa.py        reglas anti-estafa
├── evaluador.py         une los filtros y arma las sugerencias para el CV
├── fuentes/             un archivo por sitio de empleo (+ alertas_mail.py)
├── telegram.py          mensajes y envío
├── estado.py            memoria de ofertas ya revisadas
├── estadisticas.py      números del día para el resumen diario
└── __main__.py          punto de entrada
tests/                   46 tests con pytest
.github/workflows/       radar.yml (corre 2 veces por día) · tests.yml
```

## Ponerlo en marcha

**1. Crear el bot de Telegram (2 minutos)**
1. En Telegram, buscá **@BotFather** → `/newbot` → elegí un nombre y un usuario (tiene que terminar en `bot`).
2. BotFather te da un **token** (algo como `123456:ABC-xyz…`). **No lo compartas con nadie.**
3. Buscá tu bot, abrí el chat y mandale cualquier mensaje: si no, no puede escribirte.
4. Buscá **@userinfobot**, mandale un mensaje y te responde tu **Id**: ese es tu `chat_id`.

**2. Cargar los datos en GitHub (no en el código)**

En el repo: *Settings → Secrets and variables → Actions → New repository secret*:
- `TELEGRAM_TOKEN` = el token de BotFather
- `TELEGRAM_CHAT_ID` = tu Id

**3. Probarlo**

*Actions → Radar de empleo → Run workflow*. En un minuto te llega el primer aviso. Después corre solo cada 3 horas, de 8:17 a 23:17 (hora de Argentina). Si no hay nada nuevo, no te escribe, salvo **una vez por día (desde las 20 hs)**, cuando manda un resumen corto para confirmar que sigue activo.

**4. (Opcional) Alertas de LinkedIn, Computrabajo, Bumeran, ZonaJobs e Indeed**

1. **Creá una cuenta de Gmail nueva, solo para alertas de empleo.** La contraseña de aplicación da acceso a todo el buzón: mejor que sea uno que no tenga nada más.
2. En esa cuenta activá la **verificación en 2 pasos** (*Cuenta de Google → Seguridad*), que es requisito para el paso siguiente.
3. Creá una **contraseña de aplicación** en https://myaccount.google.com/apppasswords con el nombre "radar". Google muestra 16 letras: **no las compartas con nadie**.
4. Con ese mail, creá alertas en cada sitio (por ejemplo *"desarrollador java junior"* en Argentina). En LinkedIn: buscá el puesto en *Empleos* y activá *"Crear alerta"*.
5. En GitHub cargá dos secretos más: `GMAIL_USER` (la dirección) y `GMAIL_APP_PASSWORD` (las 16 letras, sin espacios).
6. Probalo con *Run workflow → muestra*: la sección "Alertas por mail" dice cuántas ofertas encontró en cada sitio.

El radar abre el buzón en **solo lectura** y mira únicamente los mails de esos sitios. Las alertas traen solo el título del puesto, así que en el aviso te marca que leas la oferta completa antes de postularte.

## Correrlo en tu compu

```bash
pip install -r requirements-dev.txt
python -m pytest            # tests
python -m radar_empleo --simular   # imprime los avisos en vez de mandarlos
python -m radar_empleo --muestra   # muestra cómo llegan los datos de cada fuente
```

## Notas

- GitHub pausa las tareas programadas de un repo público si pasan 60 días sin actividad: si deja de llegar el aviso, entrá a *Actions* y reactivalo.
- Los registros de GitHub Actions son públicos en un repo público: el radar solo imprime cantidades, nunca el detalle de las ofertas.

## Próximos pasos

- [ ] Generar automáticamente un PDF del CV reordenado para cada oferta
- [ ] Ajuste fino de las frases del CV con IA (Claude), manteniendo la regla de no inventar
- [ ] Botones "Me interesa / Descartar" en Telegram para llevar un registro de postulaciones
