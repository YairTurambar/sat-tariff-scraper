# Procesamiento por lotes de más de 500 HS Codes

El límite de **500 códigos por archivo** (`MAX_LINES`) se mantiene intacto: `validate-input` y
`run` siguen rechazando un archivo con más líneas. Para proyectos con miles de códigos, el archivo
maestro configurado en `SAT_INPUT_FILE` se divide en lotes y **todos los lotes se procesan en una
sola ejecución, con una sola sesión persistente de Chrome**.

## Por qué existía el problema

Cada ejecución de `python -m sat_tariff run` abre `BrowserSession(config)` y la cierra al terminar.
Cambiar manualmente de `HS_codes_001.txt` a `HS_codes_002.txt` y volver a ejecutar `run` cerraba
Chrome, perdía la sesión JSF y obligaba a resolver otro CAPTCHA. Los comandos de lotes abren el
navegador una sola vez y recorren todos los lotes dentro del mismo contexto.

## Flujo

```text
Abrir SQLite una vez
└── Abrir Chrome una vez
    ├── Resolver CAPTCHA manualmente cuando SAT lo solicite
    ├── Procesar lote 1
    ├── Procesar lote 2 sin cerrar ni volver a abrir Chrome
    ├── Procesar los lotes restantes en la misma página/contexto
    └── Cerrar Chrome al terminar o ante la salida definitiva del comando
Exportar posteriormente con el comando existente
```

## Uso (PowerShell)

```powershell
$env:SAT_BROWSER_CHANNEL="chrome"
python -m sat_tariff prepare-batches
python -m sat_tariff run-batches
python -m sat_tariff export
```

Recuperación tras una interrupción:

```powershell
python -m sat_tariff resume-batches
python -m sat_tariff export
```

### Archivos TXT explícitos (sin manifiesto)

Si ya tienes archivos batch independientes, no necesitas crear un archivo maestro ni ejecutar
`prepare-batches`. Repite `--file` en el orden deseado; no hay límite en la cantidad de archivos:

```powershell
$env:SAT_SQLITE_DB="sat_tariff_prueba_30.db"
python -m sat_tariff run-batches `
  --file .\HS_codes_batch_01.txt `
  --file .\HS_codes_batch_02.txt `
  --file .\HS_codes_batch_03.txt
python -m sat_tariff export
```

Para reanudar, pasa los mismos archivos a `resume-batches`:

```powershell
python -m sat_tariff resume-batches `
  --file .\HS_codes_batch_01.txt `
  --file .\HS_codes_batch_02.txt `
  --file .\HS_codes_batch_03.txt
```

Cada archivo se valida con el límite normal de 500 códigos. Los duplicados dentro o entre archivos
se omiten globalmente y se reportan. Todos los códigos faltantes se registran en la misma base
configurada en `SAT_SQLITE_DB`, sin restablecer estados ni secciones guardadas. `resume-batches`
omite códigos `completed`/`permanent_error`, procesa los demás y conserva los checkpoints por
sección. `--file` no se puede combinar con `--directory`; esa opción continúa reservada al flujo
basado en manifiesto.

El programa abre una sola sesión de navegador, contexto y página, y navega al portal una sola vez
por ejecución; las cookies y el formulario se mantienen al pasar de un archivo al siguiente. Por
eso, normalmente basta resolver el CAPTCHA inicial para todos los batches. SAT aún puede exigir
otro CAPTCHA por expiración o por sus propias políticas; esa pausa sigue siendo manual. El Excel
consolidado se genera al final con `python -m sat_tariff export` y no se exporta automáticamente.

Chrome permanece abierto **únicamente mientras el mismo comando `run-batches`/`resume-batches`
siga ejecutándose**. Si el proceso termina o el equipo se reinicia, el navegador se cierra y SAT
puede volver a pedir un CAPTCHA al reanudar. El CAPTCHA siempre se resuelve manualmente en el
navegador: no hay OCR, ni servicios externos, ni evasión automática.

## `prepare-batches`

Lee el archivo maestro (`SAT_INPUT_FILE`, por defecto `HS_codes.txt`) y:

- ignora líneas vacías y conserva los ceros iniciales;
- valida formatos con las reglas existentes y aplica `SAT_INVALID_LINE_POLICY`;
- elimina duplicados globalmente conservando la primera aparición y el orden original;
- divide los códigos en archivos de a lo sumo `SAT_BATCH_SIZE` (máximo 500) códigos;
- escribe `HS_codes_001.txt`, `HS_codes_002.txt`, … en `SAT_BATCH_DIRECTORY` (por defecto
  `batches/`) en UTF-8 y de forma atómica, validando cada lote con el validador normal;
- borra o reemplaza **solo** los archivos que la herramienta administra
  (`HS_codes_NNN.txt` y `manifest.json`); cualquier otro archivo del directorio se conserva;
- genera `manifest.json`.

Opciones: `--batch-size N` y `--directory RUTA`. `run-batches` y `resume-batches` aceptan el mismo
`--directory RUTA` para trabajar con un conjunto de lotes fuera de `SAT_BATCH_DIRECTORY`, o
repeticiones de `--file RUTA` para procesar TXT explícitos sin manifiesto; ambas opciones son
mutuamente excluyentes.

Los archivos de lote obsoletos de una preparación anterior se eliminan **después** de escribir y
validar el conjunto nuevo, y el manifiesto se publica al final: un fallo nunca deja un manifiesto
apuntando a lotes inexistentes.

## Formato del manifiesto

```json
{
  "version": 1,
  "master_file": "HS_codes.txt",
  "master_sha256": "…",
  "created_at": "2026-10-15T21:31:20.154038+00:00",
  "batch_size": 500,
  "total_lines": 7598,
  "total_codes": 7578,
  "duplicates_skipped": ["0101210000"],
  "suspicious_codes": [],
  "invalid_line_policy": "skip",
  "batches": [
    {"number": 1, "path": "HS_codes_001.txt", "count": 500, "sha256": "…"}
  ]
}
```

- `path` es **relativo al propio manifiesto** y usa `/`, por lo que mover o clonar el repositorio no
  rompe los lotes y el manifiesto funciona igual en Windows, macOS y Linux.
- `master_file` se guarda tal como se configuró (normalmente relativo a la raíz del repositorio) y se
  resuelve desde el directorio de trabajo.
- El manifiesto describe **qué** códigos deben procesarse; SQLite sigue siendo la única fuente de
  verdad sobre **qué ya se procesó**. El manifiesto no almacena estado operativo por lote.
- `manifest.json` se escribe de forma atómica (archivo temporal + `os.replace`), igual que los
  archivos de lote.
- Cada lote debe declarar un SHA-256 válido de 64 caracteres; un manifiesto sin ese hash se rechaza,
  de modo que la verificación de integridad no puede desactivarse editando el archivo.
- La política de líneas inválidas registrada en el manifiesto es la autoritativa al cargar los lotes:
  cambiar `SAT_INVALID_LINE_POLICY` después de preparar no altera silenciosamente el conjunto.

## `run-batches` y `resume-batches`

Ambos comandos:

1. cargan y validan el manifiesto (versión, estructura);
2. verifican el SHA-256 del archivo maestro y de cada lote **antes** de abrir el navegador;
3. cargan todos los lotes en orden y validan cada archivo con el validador normal;
4. registran en SQLite los códigos del manifiesto que aún no existen, sin tocar el estado ni las
   secciones de los códigos ya almacenados;
5. excluyen los códigos `completed` y `permanent_error`;
6. abren Chrome una sola vez, **solo si quedan pendientes**;
7. procesan todos los pendientes de todos los lotes en el orden global original, reanudando desde la
   sección correcta mediante los checkpoints existentes;
8. terminan con un resumen: total, completados previamente, procesados ahora, fallidos/pendientes y
   lotes recorridos.

Si no quedan pendientes, el navegador no se abre y se informa `Processed 0 HS codes.`

Estados soportados al reanudar: `pending`, `in_progress`, `rights_completed`,
`nomenclature_completed`, `restrictions_completed`, `quotas_completed`, `retryable_error` y
`captcha_required`. Un código presente en el manifiesto pero todavía ausente de SQLite se considera
pendiente y se procesa.

La exportación **no** es automática: `python -m sat_tariff export` sigue siendo el paso explícito de
consolidación.

## Progreso

```text
Lote 2/16 — 500 códigos
[global 501/7578 | lote 1/500] HS 1234567890
```

## Errores accionables

| Situación | Resultado |
| --- | --- |
| `manifest.json` ausente o corrupto | error con indicación de volver a ejecutar `prepare-batches` |
| Versión de manifiesto incompatible | error explícito, sin procesar |
| Archivo maestro modificado tras preparar | error antes de abrir Chrome |
| Lote faltante o modificado | error antes de abrir Chrome |
| `SAT_BATCH_SIZE` fuera de 1..500 | `Configuration error` al cargar la configuración |

Los lotes nunca se regeneran automáticamente como efecto secundario de `run-batches` o
`resume-batches`.
