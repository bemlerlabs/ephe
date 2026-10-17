<p align="center">
  <a href="README.zh-CN.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.md">English</a>
</p>

# Ephe — Agente SI local, efímero y privado

**PWA local-first + FastAPI que corre en tu máquina. Sin cuenta, sin telemetría; las funciones en línea (búsqueda web, motores remotos) son siempre opcionales y explícitas. Tú eliges el motor: Ollama local, Ollama remoto o cualquier endpoint compatible con OpenAI (DGX Spark, vLLM, SGLang). Sin valor silencioso por defecto: hasta que elijas, la app lo dice.**

<table>
<tr><td><b>Bucle de aprendizaje cerrado</b></td><td>51 paquetes de habilidades integrados con verificación rubric+golden, habilidades ejecutadas como rutas rápidas deterministas, memoria personal y búsqueda de sesiones de texto completo — tu historial se acumula en lugar de evaporarse.</td></tr>
<tr><td><b>Herramientas con aprobación</b></td><td>Sistema de archivos, shell, navegador y herramientas de documentos bajo un perfil de seguridad que controlas (strict / session / autonomous). Las escrituras requieren consentimiento; el modo Ask no usa herramientas.</td></tr>
<tr><td><b>Medido, no prometido</b></td><td>Un benchmark reproducible (matriz de 60 tareas + mapeo pass³ inspirado en TAU/GAIA) corre contra el endpoint de streaming real en cada ronda — las mismas compuertas que publican, verifican.</td></tr>
</table>

## Instalación rápida

```bash
curl -fsSL https://raw.githubusercontent.com/bemlerlabs/ephe/main/install.sh | bash
```

El instalador coloca la app en `~/Documents/Ephe`, construye la PWA e inicia el servidor local (por defecto `http://127.0.0.1:8765`). No instala Ollama ni descarga modelos — en el primer inicio eliges el motor dentro de la app.

## Documentación

Funciones completas, arquitectura, pruebas y seguridad en el [README en inglés](README.md) (documento principal).

## Licencia

[BUSL-1.1](LICENSE)
