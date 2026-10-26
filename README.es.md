<p align="center"><a href="README.md">English</a> | <a href="README.zh-CN.md">中文</a> | <a href="README.es.md">Español</a></p>

<!-- canonical: README.md is authoritative -->
> **La versión en inglés es la referencia oficial.** Esta traducción puede quedar desactualizada; prevalece [README.md](README.md).

<div align="center">
<img src="docs/media/ephe-bee-512.png" alt="Emblema de la abeja de Ephe" width="88">

# Ephe

**Ephe es un espacio de trabajo para un agente de IA en tu propio ordenador que prioriza el uso local. Tú eliges el motor y el modelo, apruebas el uso de las herramientas y conservas los archivos. No necesitas una cuenta ni hay un modelo predeterminado oculto.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Licencia BUSL-1.1](https://img.shields.io/badge/License-BUSL%201.1-2d6a4f?style=flat-square)](LICENSE)
[![Pruebas](https://github.com/bemlerlabs/ephe/actions/workflows/tests.yml/badge.svg)](https://github.com/bemlerlabs/ephe/actions/workflows/tests.yml)
[![Compilación del frontend](https://github.com/bemlerlabs/ephe/actions/workflows/frontend-build.yml/badge.svg)](https://github.com/bemlerlabs/ephe/actions/workflows/frontend-build.yml)

</div>

![El espacio de trabajo de Ephe a 1280 px: lista de tareas a la izquierda, chat vacío del agente en el centro, selector de espacio de trabajo y cuadro de entrada.](docs/screenshots/readme-chat-1280.png)

- **Privado por defecto.** Con un motor local, tus instrucciones se quedan en tu ordenador. Las funciones en línea requieren tu activación.
- **Tu modelo.** Elige un modelo local de Ollama o un endpoint compatible con OpenAI. Ephe nunca elige por ti.
- **Tus archivos.** Trabaja en la carpeta que elijas. Los archivos que genera el agente se guardan en tu ordenador.

## Qué es Ephe

Ephe es un espacio de trabajo para un agente de IA en tu ordenador. Le das una tarea y el agente elabora un plan, utiliza herramientas y muestra el trabajo mientras lo realiza. En el perfil estricto predeterminado, las modificaciones de archivos y los comandos de shell requieren tu aprobación.

El motor utiliza un modelo para responder. Un motor local como Ollama ejecuta el modelo en tu hardware. Un endpoint compatible con OpenAI lo ejecuta en el proveedor que elijas. Ephe no incluye pesos de modelos ni selecciona un modelo predeterminado.

Un plugin agrupa comandos y un paquete de habilidades. Una habilidad es un conjunto de instrucciones reutilizables que el agente puede seguir. Un conector enlaza una herramienta externa. Ya puedes configurar servidores MCP manualmente. El paquete de habilidades Superpowers incluido se instala en tu propio perfil desde el Centro de extensiones tras una confirmación.

Ephe llama celda a cada ejecución. La celda es un espacio de trabajo desechable para la sesión. Los archivos que conserves y los ajustes que guardes permanecen en el disco. Ephe usa SI como abreviatura de superinteligencia personal: un agente capaz de planificar y utilizar herramientas con tu aprobación.

El banco de trabajo conserva los archivos que ha generado el agente. Puedes abrirlos, descargarlos o incorporarlos; el original permanece en el espacio de trabajo.

## Qué puedes hacer

Estos flujos de trabajo se incluyen como plugins propios. El chat identifica el resultado de la herramienta que respalda cada paso.

1. **Redactar un documento a partir de un conjunto de fuentes.** Los plugins [documents](plugins/documents) y [local-document-factory](plugins/local-document-factory) generan archivos PDF o DOCX con fuentes y un paso de verificación.
2. **Crear una presentación o una hoja de cálculo.** [presentations](plugins/presentations) genera presentaciones PPTX con evidencias y notas del orador; [spreadsheets](plugins/spreadsheets) crea modelos XLSX con datos de entrada y supuestos separados.
3. **Investigar con fuentes fechadas.** [web-research](plugins/web-research) conserva las URL directas, las fechas y las evidencias citadas. El acceso web requiere tu activación.
4. **Reproducir un error y demostrar que se ha corregido.** [code-shell](plugins/code-shell) reproduce el defecto, aplica la corrección mínima y la verifica ejecutando pruebas.
5. **Guardar notas que puedas recuperar.** [memory](plugins/memory) almacena, recupera y elimina datos persistentes tras tu confirmación; [private-research-notebook](plugins/private-research-notebook) elabora respuestas e informes con citas a partir de fuentes locales.

Elige el motor adecuado para tu ordenador:

![Ajustes de Ephe a 1280 px: un motor compatible con OpenAI, un selector de modelos y el endpoint.](docs/screenshots/readme-settings-1280.png)

Trabaja en una ventana del tamaño de un teléfono a través de tu propia red:

![Ephe en una vista móvil de 390 px: el espacio de trabajo del agente, el estado del motor y el cuadro de entrada.](docs/screenshots/readme-chat-390.png)

## Qué ocurre durante una tarea

1. Escribes una tarea en el cuadro de entrada. El agente la convierte en un plan.
2. Utiliza una herramienta, por ejemplo, para leer un archivo o ejecutar un comando. El perfil estricto exige aprobación para modificar archivos y ejecutar comandos de shell.
3. El resultado aparece en el chat. Los archivos y gráficos llegan al banco de trabajo, donde puedes abrirlos o incorporarlos.
4. La celda de la sesión termina. Los archivos generados y los ajustes que hayas guardado permanecen en el disco.

Cada resultado de una herramienta queda vinculado al turno que lo produjo. Las afirmaciones sobre un archivo proceden de resultados reales de herramientas, no de la memoria del modelo.

## Escritorio, terminal y teléfono

El escritorio y el navegador comparten una aplicación web instalable (PWA) y un mismo backend en Python. `ephe desktop` compila e instala la aplicación contenedora de escritorio; `ephe start --open` abre la aplicación en el navegador.

La terminal (`ephe tui`) utiliza el motor elegido en `~/.ephe/engine.json`. Un teléfono en tu red local puede abrir la PWA después de ejecutar `ephe start --lan --open`; el acceso público es una opción independiente que debes activar.

## Inicio rápido

### 1. Instalar

#### macOS y Linux

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/v0.1.10/install.sh | bash
```

Para leer el script antes de ejecutarlo, usa una copia local del repositorio:

```bash
git clone https://github.com/bemlerlabs/ephe.git
cd ephe
./install.sh
```

El instalador prepara Python y el entorno local, compila la aplicación web y la inicia en `http://127.0.0.1:8765`. Si macOS pregunta si quieres abrir la aplicación, ve a Ajustes del Sistema → Privacidad y seguridad → Abrir de todos modos.

#### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/bemlerlabs/ephe/v0.1.10/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Si usas una copia local del repositorio, abre PowerShell en esa carpeta y ejecuta el mismo comando: `powershell -ExecutionPolicy Bypass -File .\install.ps1`.

La instalación en Windows aún no se ha verificado de principio a fin para esta revisión. Los comandos están documentados, pero sigue pendiente comprobarlos en un entorno de ejecución o una máquina virtual con Windows.

#### Docker

Docker y todas las opciones del instalador se describen en [docs/INSTALL_OPTIONS.md](docs/INSTALL_OPTIONS.md).

El comando apunta a la versión pública actual, `v0.1.10`. El instalador Bash usa `--desktop` por defecto; pasa `--cli` o establece `EPHE_MODE=cli` para instalar solo la interfaz de terminal.

Antes de usar `ephe` en una terminal nueva, activa el entorno instalado.
Para la instalación predeterminada en macOS o Linux:

```bash
source "$HOME/Documents/Ephe/.venv/bin/activate"
```

Para la instalación predeterminada en Windows:

```powershell
& "$HOME\Documents\Ephe\.venv\Scripts\Activate.ps1"
```

Si usas una copia del repositorio o una ubicación personalizada, utiliza la `.venv` de esa carpeta.

### 2. Elegir el motor

La aplicación abre la página de configuración inicial (Setup). Elige un modelo local de Ollama, un Ollama remoto o un endpoint compatible con OpenAI. En la terminal, `ephe configure` guarda la misma elección en `~/.ephe/engine.json`. Ephe se niega a arrancar sin una elección; no hay una opción predeterminada oculta.

Si usas un endpoint alojado, introduce su clave en la misma página. La aplicación la guarda en el llavero del sistema operativo o en `~/.ephe/engine.key`, con permisos exclusivos para su propietario. Nunca se escribe en `engine.json` ni se muestra en el chat. La clave guardada queda vinculada a este motor en `~/.ephe/engine.key.binding.json`, que guarda un SHA-256 de la clave, no la clave. La aplicación se niega a usar una clave guardada sin ese vínculo.

### 3. Pedir una tarea

Abre `http://127.0.0.1:8765` o ejecuta `ephe start --open`. El contenedor de escritorio se compila a partir de la misma aplicación; `ephe desktop` lo instala. Desde la terminal, `ephe tui` abre la interfaz de texto. Escribe una tarea. El perfil estricto pide permiso antes de modificar archivos o ejecutar comandos de shell.

Para usar el mismo espacio de trabajo desde un teléfono de tu red, inicia con `ephe start --lan --open` y abre Ajustes (Settings) → Móvil (Mobile). Pulsa **Conectar móvil (Connect mobile)**. Escanea el código QR y abre la PWA en el teléfono. El acceso público requiere una activación independiente; los pasos están en [docs/MOBILE.md](docs/MOBILE.md).

## Qué necesitas

| Requisito | Detalle |
|---|---|
| Ordenador | macOS 13+ o Ubuntu 22+; un navegador actual; las instrucciones para Windows PowerShell siguen sin verificarse de principio a fin |
| RAM | 8 GB libres para un modelo local pequeño; 16 GB o más para un modelo de clase 12B; un motor remoto necesita menos |
| Disco | 12 GB libres; más espacio para el modelo que elijas |
| Herramientas de compilación | Node.js 22.23.4 es el entorno de compilación probado; úsalo con npm/pnpm. Se admite Python 3.11 o posterior; `.python-version` fija la serie 3.13 |
| Motor | Un modelo local de Ollama o un endpoint compatible con OpenAI y su clave; sin cuenta de Ephe |

Un modelo local utiliza la RAM y el disco de la máquina que lo ejecuta. Un endpoint alojado necesita conexión de red, una URL de endpoint y una clave de API. Un motor local no necesita clave de API. Ephe no incluye ningún modelo ni pide una cuenta. Para usar un modelo local, descarga primero una etiqueta: `ollama pull <tag>`.

## Cuánto cuesta

Ephe no tiene suscripción ni cuenta. Un modelo local utiliza tu hardware. Un motor alojado te factura directamente según sus propias condiciones. El código fuente está disponible bajo BUSL-1.1; el uso en producción requiere una licencia comercial, descrita en [COMMERCIAL.md](COMMERCIAL.md).

La inferencia local no tiene tarifas de proveedor. El uso fuera de producción es gratuito; el uso en producción requiere una licencia comercial independientemente del motor. Cada proveedor alojado fija sus propios precios.

## Privacidad y control

Con un motor local, las instrucciones se quedan en tu ordenador. Un motor remoto, la búsqueda web, el acceso móvil público y la conversión de texto a voz en la nube envían lo que solicitas al servicio correspondiente; cada opción requiere tu activación.

La clave del motor permanece en el llavero del sistema operativo o en `~/.ephe/engine.key`, con permisos exclusivos para su propietario. La página de ajustes y `ephe configure` la guardan; Ephe no la muestra.

El perfil estricto predeterminado pide permiso antes de modificar archivos y ejecutar comandos de shell. Otros modos que actives y las aprobaciones recordadas pueden permitir la ejecución sin volver a preguntar. Comprueba el perfil de aprobación en el cuadro de entrada. La celda se destruye al terminar la sesión; los archivos generados y los ajustes que hayas guardado permanecen en el disco.

No hay cuenta ni registro. La comprobación de actualizaciones consulta a GitHub cuál es la versión más reciente; cualquier otro acceso de red espera a que actúes. Las funciones en línea opcionales aparecen en Setup y Settings. Los detalles están en [docs/SECURITY_AND_PRIVACY.md](docs/SECURITY_AND_PRIVACY.md) y [SECURITY.md](SECURITY.md).

## Plugins, habilidades y conectores

Ephe incluye nueve plugins propios, siete preajustes de capacidades, cinco paquetes de habilidades propios y un paquete de habilidades de terceros incluido (Superpowers, MIT). Un plugin añade comandos y un paquete de habilidades; una habilidad es un conjunto de instrucciones reutilizables; un preajuste ofrece una capacidad sin atribuirle la calidad de un plugin. La aplicación también incluye sus habilidades integradas; consulta [docs/SKILLS.md](docs/SKILLS.md).

Los plugins son documents, presentations, spreadsheets, code-shell, browser-use, web-research, memory, local-document-factory y private-research-notebook. Los preajustes abarcan trabajo con imágenes, herramientas del Protocolo de Contexto de Modelos (MCP), visión, voz, guías, creación de plugins y creación de habilidades.

Los nueve plugins propios y los cinco paquetes de habilidades propios se distribuyen con la aplicación. El Centro de extensiones muestra qué puede hacer cada entrada. El paquete Superpowers se incluye como contenido de terceros y se instala en tu propio perfil tras una confirmación, porque no está firmado. Está previsto un catálogo público para editores externos.

Ya puedes añadir servidores MCP manualmente en Ajustes (Settings) → Conectores (Connectors). Su catálogo ofrece indicaciones de configuración y enlaces a la documentación; no instala esos servidores externos.

## Qué falta todavía

- No hay aplicación para iOS ni Android. En el teléfono se usa la PWA a través de tu propia red.
- No se incluyen pesos de modelos. Tú eliges el motor y el modelo.
- No hay rastreador web por defecto. La investigación web requiere tu activación.
- No hay instalación con un clic de servidores MCP externos. Las conexiones MCP requieren configuración manual.
- No es un servidor multiusuario. Cada instancia sirve a una persona en una máquina.
- No hay un catálogo público para editores de terceros. Un paquete de terceros (Superpowers, MIT) se incluye con la aplicación; el resto de las entradas son propias.
- La instalación y el arranque del navegador en Windows siguen pendientes de una comprobación de principio a fin en Windows.
- No hay un mercado público de plugins. El paquete incluido se puede instalar; está previsto un mercado con entradas externas.

## Si algo falla

- **El comando de instalación que guardaste apunta a una versión antigua.** Compáralo con el comando de Inicio rápido de arriba antes de instalar.
- **La aplicación abre Setup y no permite chatear.** Elige un motor allí o ejecuta `ephe configure`. Tanto un modelo local como un endpoint alojado son opciones válidas.
- **macOS indica que la aplicación no está notarizada.** Abre Ajustes del Sistema → Privacidad y seguridad y elige Abrir de todos modos.
- **PowerShell bloquea el script.** Usa `powershell -ExecutionPolicy Bypass -File .\install.ps1` en la carpeta donde descargaste el script.
- **Un modelo local va lento.** Comprueba primero la RAM libre; un modelo más pequeño consume menos. Un endpoint alojado traslada el trabajo a otra máquina.
- **¿Dónde están mis datos y mi clave?** `~/.ephe` contiene ajustes, sesiones, archivos generados y registros; el llavero del sistema operativo (preferido) o `~/.ephe/engine.key` (0600) guarda la clave del motor. `./uninstall.sh --dry-run` muestra el plan sin cambiar nada; `./uninstall.sh --keep-data` elimina la copia del repositorio y conserva `~/.ephe`; `./uninstall.sh --yes` elimina ambos.

## Documentación, contribuciones y licencia

El índice está en [docs/README.md](docs/README.md). Empieza por el [inicio rápido](docs/QUICKSTART.md), la [guía de instalación](docs/INSTALL.md), el [primer uso](docs/FIRST_RUN.md), la [referencia de la CLI](docs/CLI.md), los [plugins](docs/PLUGINS_OVERVIEW.md), las [habilidades](docs/SKILLS.md) y la [seguridad y privacidad](docs/SECURITY_AND_PRIVACY.md).

- Errores y solicitudes de funciones: el [gestor de incidencias](https://github.com/bemlerlabs/ephe/issues).
- Informes de seguridad: el canal privado indicado en [SECURITY.md](SECURITY.md).
- Contribuciones: [CONTRIBUTING.md](CONTRIBUTING.md).
- Licencia: Business Source License 1.1 (BUSL-1.1), con código fuente disponible. Las condiciones están en [LICENSE](LICENSE); el uso en producción se describe en [COMMERCIAL.md](COMMERCIAL.md). Cada versión pasa a Apache 2.0 cuatro años después de su primera publicación.
