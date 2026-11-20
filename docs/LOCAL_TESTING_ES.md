# Guía paso a paso: probar Land AI Multi-Hazard en local antes de producción

Alcance de esta versión: **solo Incendios (Wildfire) e Inundaciones (Flood)**, en español (por defecto) e inglés. Deslizamientos no forma parte de esta versión.

Esta guía asume **Windows + PowerShell**, que ya tienes la versión de Incendios funcionando en local y en producción, y que
esta nueva versión se prueba **al lado**, sin tocar ninguna de las dos.

> Regla de oro: **no se despliega nada** hasta completar la lista de la sección 9. Nada de esto modifica el proyecto actual
> (`landai-wildfire`) ni su servicio de Cloud Run.

---

## 0. El mapa: tres entornos que no se mezclan

| Entorno | Backend | Frontend | Estado |
|---|---|---|---|
| Producción (v2 Incendios) | Cloud Run `landai-wildfire-api` | `https://landaiapp.github.io/landai-wildfire/` | **No se toca** |
| Local actual (v2) | `http://localhost:8000` | `http://localhost:5173` | **No se toca** (puede seguir encendido) |
| **Local nuevo (v3 Multi-Hazard)** | **`http://localhost:8001`** | **`http://localhost:5174`** | Lo que probamos aquí |

Puertos distintos = puedes comparar las dos versiones en paralelo, en dos pestañas.

---

## 1. Preparar la carpeta nueva

Descomprime el paquete **en una carpeta nueva**, hermana de la actual (nunca encima):

```powershell
cd C:\ruta\a\tus\proyectos            # donde está landai-wildfire
Expand-Archive .\landai-multihazard.zip -DestinationPath .\landai-multihazard
cd .\landai-multihazard
git status                            # el paquete ya trae un repositorio git (rama main) con los commits locales
```

Comprueba que **no** hay credenciales dentro: no debe existir `.env`, ni `credentials\`, ni ningún `*.json` de llaves.

---

## 2. Requisitos (verifica versiones)

```powershell
python --version        # 3.11 o superior
node --version          # 18 o superior (22 recomendado)
npm --version
gcloud --version        # solo se necesita para desplegar
```

---

## 3. Entorno Python **nuevo** (no reutilices el de v2)

```powershell
conda create -n landai-mh python=3.11 -y
conda activate landai-mh
pip install -r backend\requirements-dev.txt
```

(Con `venv`: `python -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -r backend\requirements-dev.txt`.)

---

## 4. Configuración local (`.env`)

```powershell
Copy-Item .env.example .env
notepad .env
```

Edita **solo** estas líneas (deja el resto como viene):

```ini
EE_PROJECT=applandai
# Autenticación local con `earthengine authenticate` (la misma que ya usas): deja ambas vacías
EE_SERVICE_ACCOUNT=
EE_PRIVATE_KEY_PATH=

# Permite el frontend nuevo (puerto 5174) además del viejo
CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174,http://localhost:5173

# Límites relajados SOLO para probar (si no, a la sexta prueba recibirás 429)
RATE_LIMIT_ANALYZE=60/hour;200/day
RATE_LIMIT_EXPOSURE=60/hour;200/day

# WorldPop V3 (síncrono). Estos valores ya son los predeterminados; solo ajústalos tras la prueba real 5B
WORLDPOP_API_VERSION=v3
OVERPASS_TOTAL_BUDGET_S=420
MAX_EXPOSURE_AOI_HECTARES=40000

# Cualquier cadena larga (solo local)
ANALYSIS_REF_SECRET=cambia-esto-por-una-cadena-larga-y-aleatoria-local
```

Notas:
* Si nunca has hecho login de Earth Engine en esta máquina: `earthengine authenticate` (una sola vez).
* El `.env` está en `.gitignore`: **no se sube**. Nunca pegues llaves en el repositorio.
* Si usas una llave de cuenta de servicio en vez del login local, ponla en `credentials\` y apunta `EE_PRIVATE_KEY_PATH` a ella.

---

## 5. Pruebas automáticas (no necesitan Earth Engine)

```powershell
# Backend (desde la raíz del proyecto)
pytest -q
# Esperado: 323 passed

# Frontend
cd frontend
npm ci
npm test                 # Esperado: 9 archivos, 106 pruebas OK
npm run typecheck        # sin errores
npm run build            # "built in ..." sin errores
cd ..
```

Si alguna falla, **detente** y envíame la salida completa. Estas pruebas verifican, sin credenciales, que el grafo de
Earth Engine de Inundaciones tiene la estructura del script (radio 30 m, escala 10, píxeles conectados 100/20, `min(VV,VH)`,
fallback −0.3, sin pendiente ni Sentinel-2 en la detección) y que **Incendios sigue idéntico** (las pruebas originales de
Incendios siguen dentro del total).

> Importante: pasar pruebas **no demuestra** que los números coinciden con el Code Editor. Eso se hace en la sección 8.

---

## 5B. Pruebas reales de WorldPop V3 y Overpass (sin Earth Engine, 1 vez cada una)

Estas pruebas llaman a los servicios públicos reales con el **mismo cliente del backend**. No son parte de `pytest` y no
imprimen llaves. Ejecútalas **una vez** (son servicios compartidos; no las pongas en bucle). Desde la raíz del proyecto:

```powershell
python scripts\smoke_worldpop_v3.py        # contrato real de WorldPop V3 + footprint fragmentado (413/chunking)
python scripts\smoke_overpass.py           # estado por categoría: facilities / roads / buildings
python scripts\smoke_exposure.py           # OSM + WorldPop juntos, estado general success|partial|failed
```

Qué mirar:
* `smoke_worldpop_v3.py` → `HTTP 200`, claves JSON con `total_population`. Si responde otra cosa (404, 401, 422, otro formato),
  **envíame la salida**: el contrato V3 (cabecera de la llave, límites de tamaño) no se pudo verificar desde mi entorno.
* La segunda parte imprime `chunks`, `requests`, `coverage_pct`, `simplification`. Con un 413 debe dividir y terminar, no dar cero.
* `smoke_overpass.py` → una línea por categoría con estado, celdas, segundos y servidor que respondió. Que **buildings** falle
  y **roads/facilities** funcionen es el modo degradado previsto (`PASS`).
* Si ves límites distintos a los supuestos, ajusta `WORLDPOP_CHUNK_PARTS`, `WORLDPOP_CHUNK_VERTICES`, `WORLDPOP_MAX_VERTICES` en `.env`.

Con el backend encendido y Earth Engine real, además:

```powershell
python scripts\smoke_wildfire.py --exposure
python scripts\smoke_flood.py --pre-start 2026-01-01 --pre-end 2026-01-26 --post-start 2026-02-02 --post-end 2026-02-15
```
(usa fechas de una inundación **real** conocida; el módulo es experimental).

---

## 6. Arrancar el backend y el frontend nuevos

**Terminal 1 — backend (puerto 8001):**

```powershell
conda activate landai-mh
cd C:\ruta\a\landai-multihazard\backend
uvicorn app.main:app --reload --port 8001
```

**Verificación rápida (terminal 2):**

```powershell
Invoke-RestMethod "http://localhost:8001/health?check_ee=true"
(Invoke-RestMethod "http://localhost:8001/api/v1/config").version        # debe decir 3.0.0
Invoke-RestMethod "http://localhost:8001/api/v1/hazards" | ConvertTo-Json -Depth 4
```

Debe listar **dos** módulos: `wildfire` (operational) y `flood` (experimental, under_validation). `check_ee=true` debe confirmar que Earth Engine inicializa.
También puedes abrir <http://localhost:8001/docs>.

**Terminal 3 — frontend (puerto 5174):**

```powershell
cd C:\ruta\a\landai-multihazard\frontend
"VITE_API_BASE_URL=http://localhost:8001" | Out-File -Encoding ascii .env.local
npm run dev -- --port 5174
```

Abre <http://localhost:5174>. (`.env.local` también está ignorado por git.)

---

## 7. Pruebas manuales en la interfaz

Anota el resultado de cada una (OK / fallo / observación). Todas son gratuitas salvo las que ejecutan análisis.

### 7.1 Landing y selector (sin costo)
1. La página abre en **español** y muestra dos tarjetas: Incendios forestales (**Operativo**) e Inundaciones (**Experimental · En validación**). No aparece ningún otro módulo.
2. Pestaña Network del navegador (F12): al abrir **no** hay llamadas a `/analysis/run`, `/wildfire/analyze` ni `/exposure/*`. Solo `config`, `hazards`.
3. Cambia ES ↔ EN: todo cambia; recarga y verifica que recuerda el idioma.
4. Cambia de amenaza varias veces: nunca se dispara un análisis solo; fechas, resultados, capas y exposición de la amenaza anterior se limpian, y el área de estudio se conserva.

### 7.2 Incendios — regresión (cuesta un análisis)
1. Entra a Incendios → **Cargar ejemplo** (Tolima · San Luis · 2026-08-05 → 2026-08-15) → **Analizar incendio**.
2. En paralelo, ejecuta lo mismo en tu v2 local (puerto 5173) o en producción.
3. Compara: área «probable» y «alta confianza». Deben ser **prácticamente iguales** (el Random Forest se reentrena en cada corrida, así que puede haber pequeñas diferencias; diferencias grandes = detenerse y avisarme).
4. Prueba **Dibujar área**, una exposición pequeña y los exportes (GeoJSON, CSV, informe).

### 7.3 Inundaciones — flujo básico
1. Entra a Inundaciones. Al cambiar de amenaza **todo se reinicia** (área, fechas, resultados, capas y vista del mapa): cada módulo empieza limpio.
2. **Cargar ejemplo** carga el polígono y las fechas del script de referencia (PRE 2026-01-01→01-26, POST 2026-02-02→02-15) y centra el mapa. El polígono mide ~417.450 ha: el análisis lo acepta (límite dibujado de Inundaciones 500.000 ha) pero **la exposición se rechaza** (límite 40.000 ha): para exposición, dibuja un área menor. No es un evento validado.
3. Los botones permanecen desactivados hasta tener las 4 fechas y un área válida.
4. **Verificar disponibilidad**: muestra escenas S1 PRE/POST y S2 PRE/POST. No ejecuta el análisis.
5. **Detectar inundación**: barra de progreso con etapas reales; al terminar, mapa con «Extensión de inundación detectada», hectáreas, % del área, umbral de Otsu, estado **En validación** y la lista de limitaciones.
6. Capas: la extensión está encendida; en «Principales» están la extensión, el radar Sentinel-1 PRE/POST y Sentinel-2 PRE/POST (apagados salvo la extensión); log-ratio y máscara cruda están en «Avanzadas».
7. Cambia una fecha: el resultado se **borra** (no queda un resultado viejo con parámetros nuevos) y no se ejecuta nada solo.

### 7.4 Inundaciones — validaciones (gratuitas, no llegan a Earth Engine)
| Prueba | Esperado |
|---|---|
| POST termina en el futuro | Bloqueado: «La ventana POST termina en el futuro» |
| Inicio PRE antes de 2015-01-01 | Bloqueado por fecha mínima |
| Ventana de más de 90 días | Bloqueado: «La ventana … abarca N días; el máximo es 90» |
| POST empieza antes de que termine PRE | Mensaje de orden de fechas, botones desactivados |
| Área enorme o polígono inválido | Mensaje de límite, sin llamada a Earth Engine |
| Ventana sin imágenes Sentinel-1 | Bloqueado: «No hay imágenes Sentinel-1 …» |

### 7.5 Exposición (segundo paso, explícito)
1. Tras un resultado de inundación, aparece la tarjeta **Exposición e impacto** con aviso de que puede tardar varios minutos. **Nunca** arranca sola.
2. Pruébala primero en un área **pequeña** (unos pocos km²). Resultado: tarjetas de área inundada, población, edificios, vías, salud, educación.
3. Verifica que el texto habla de **«área inundada detectada»** (no de «quema»), que **no hay** tabla de sensibilidad por umbral, y que el aviso metodológico es el de inundación.
4. Exporta GeoJSON/CSV/JSON: deben incluir `hazard`, tipo de producto, estado de validación y limitaciones.
5. Estados de la exposición (insignia superior):
   * **Completo**: todas las fuentes respondieron.
   * **Parcial**: falló una fuente o una categoría de OSM (p. ej. edificios por *timeout*) o WorldPop respondió solo para parte del área. Lo que falta aparece como «No disponible» (nunca cero). Si WorldPop u OSM respondieron solo para parte del área, el valor se muestra como «≥ N» con la cobertura (cota inferior). OSM usa pocas celdas grandes y un presupuesto de tiempo por categoría (instalaciones → vías → edificios), por lo que el servidor público lento ya no multiplica las consultas.
   * **Fallido**: ninguna fuente externa respondió; se conserva el área detectada por satélite y el resto es «No disponible».
   Un resultado Parcial/Fallido no se guarda en caché: al pulsar de nuevo se vuelve a consultar solo lo que falta.
6. Límite: flood exposure usa píxeles de 10 m (≈ 600 km² máximo). Un área mayor debe rechazarse con mensaje claro, no colgarse.

### 7.6 Límites de costo
1. Con los límites de prueba relajados no verás 429. Para verlo: pon `RATE_LIMIT_ANALYZE=2/hour` en `.env`, reinicia el backend y lanza 3 análisis: el tercero debe devolver el mensaje de límite con el tiempo de espera.
2. Kill switch: `ANALYSIS_ENABLED=false` en `.env` + reinicio → la UI muestra «pausado» y no hay cómputo. Vuelve a `true` al terminar.
3. Doble clic en «Detectar inundación»: solo debe ejecutarse **una** solicitud.

---

## 8. Comparación exacta contra el Code Editor (lo que valida de verdad)

Es la única forma de comprobar que el puerto del script produce los mismos números.

1. En la UI de Inundaciones, **dibuja un polígono** (o elige un municipio), pon las fechas de tu script (`2026-01-01 → 2026-01-26` PRE y `2026-02-02 → 2026-02-15` POST son las del script entregado) y ejecuta el análisis. Anota: **hectáreas**, **umbral de Otsu**, número de escenas S1.
2. Obtén el polígono exacto que envió la UI: F12 → Network → solicitud `run` → *Payload* → copia `geometry.coordinates`.
3. En el Code Editor pega **el script entregado**, reemplaza la primera línea `var apm = …` por `var apm = ee.Geometry.Polygon(<coordenadas copiadas>);` y añade al final:

```js
var ha = floodMask.multiply(ee.Image.pixelArea()).divide(10000)
  .reduceRegion({reducer: ee.Reducer.sum(), geometry: apm, scale: 10, maxPixels: 1e13, tileScale: 4});
print('Flood ha (script):', ha);
```
4. Compara con la UI (la aplicación usa solo potencia lineal):
   * Otsu: debe coincidir hasta ~3 decimales (el histograma usa `bestEffort`, puede variar levemente).
   * Hectáreas: esperadas muy cercanas (≈ 1-2 %); una diferencia mayor es motivo para detenerse y revisar.
5. **Cociente**: la aplicación usa potencia lineal (dB→lineal antes del cociente). El script activo divide dB; para comparar, en el Code Editor descomenta las líneas 127-133 (y comenta 124-125). Ver `docs/flood/methodology.md`.
6. Valida visualmente: activa Sentinel-2 POST y compara que la extensión coincide con agua/anegamiento real; revisa falsos positivos (sombras, suelo húmedo, pendientes).

Registra tus resultados:

| Caso | Fecha | Área | ha UI | ha Code Editor | Otsu UI | Otsu CE | Variante | Observación |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | linear (por defecto) | |
| | | | | | | | reference (solo comparar) | |

---

## 9. Lista de verificación antes de producción (Go / No-Go)

**Go solo si todo es «sí»:**

- [ ] `pytest -q` → 323 passed; `npm test`, `npm run typecheck`, `npm run build` en verde.
- [ ] Landing y selector (solo Incendios e Inundaciones) se comportan como en 7.1 (sin cómputo al navegar), en ES y EN.
- [ ] `smoke_worldpop_v3.py`, `smoke_overpass.py` y `smoke_exposure.py` ejecutados con éxito (sección 5B) y resultados anotados.
- [ ] Incendios: ejemplo Tolima/San Luis coincide con v2/producción (7.2).
- [ ] Inundaciones: flujo completo en local con Earth Engine real (7.3), validaciones (7.4), exposición pequeña (7.5).
- [ ] Comparación con el Code Editor hecha (sección 8) y área inundada coherente con potencia lineal.
- [ ] Rate limit / kill switch / doble clic verificados (7.6).
- [ ] Revocaste la llave de Earth Engine que se expuso y creaste una nueva (IAM → Cuentas de servicio → Claves).
- [ ] Creaste una **alerta de presupuesto** en Billing (no existe tope duro de gasto).
- [ ] Comunicación honesta lista: Inundaciones se presenta como **Experimental / En validación**.
- [ ] Revisaste que `git status` no muestra `.env`, `.env.local` ni llaves.

Si algún punto es «no»: **No-Go**, y se corrige antes de desplegar. Luego sigue `docs/deployment.md` (servicio **nuevo**
`landai-multihazard-api`, sitio nuevo `/landai-multihazard/`; producción actual intacta).

---

## 10. Problemas frecuentes (PowerShell)

| Síntoma | Causa / solución |
|---|---|
| `curl` da errores raros con JSON | En PowerShell `curl` es un alias de `Invoke-WebRequest`. Usa `curl.exe` o `Invoke-RestMethod`. |
| Comillas de JSON se rompen | Guarda el JSON en un archivo y usa `Invoke-RestMethod -Method Post -ContentType application/json -InFile body.json` |
| `Address already in use` / puerto ocupado | Cambia el puerto (`--port 8002`) y ajusta `VITE_API_BASE_URL` y `CORS_ORIGINS`. No cierres la v2 (usa 8000/5173). |
| La web muestra «No se puede conectar con el servidor … 8001» | El backend no está encendido o `.env.local` apunta a otro puerto. Reinicia `npm run dev` tras cambiar `.env.local`. |
| Error CORS en la consola | Falta `http://localhost:5174` en `CORS_ORIGINS`; reinicia el backend. |
| `Earth Engine could not be initialized` | `earthengine authenticate` y revisa `EE_PROJECT=applandai`. En Windows con conda, ejecuta el comando dentro del entorno activo. |
| No encuentra el municipio / activo | Tu cuenta debe tener lectura en `users/maikolzaraza07/mpios`. |
| `429 rate_limit_exceeded` | Subiste el límite en `.env`? Reinicia el backend; el contador es en memoria. |
| `earth_engine_computation_limit` / memoria | Área demasiado grande para Earth Engine; usa un área menor o ventanas más cortas. |
| Archivos con finales de línea CRLF dan advertencias en git | Normal en Windows; no afecta. `git config core.autocrlf true` si molesta. |
| Overpass responde 429/504 | Es un servicio público compartido. Reintenta más tarde o con un área menor; el resultado debe quedar «Parcial», no en ceros. |

---

## 11. Cuando todo esté en verde

No despliegues aún: avísame con la tabla de la sección 8 y la lista de la sección 9 completa. El despliegue (Cloud Run nuevo
+ GitHub Pages nuevo) se hace con `docs/deployment.md`, primero como servicio de prueba, y solo después se decide cómo
promover.
