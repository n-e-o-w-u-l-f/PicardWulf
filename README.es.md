<div align="center">

[English](README.md) · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Français](README.fr.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt-BR.md) · [Polski](README.pl.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [简体中文](README.zh-CN.md)

</div>

# PicardWulf v1.0

**Búsqueda de lanzamientos en múltiples fuentes, selección automática y escritura segura de etiquetas para MusicBrainz Picard 3.0.**

> **Estado:** versión candidata. Pruebas locales correctas; aún falta comprobar la ejecución real en BMAX-B6, las API y el guardado de archivos.

## Funciones

- Consulta MusicBrainz, Deezer y Apple/iTunes, además de Spotify, SoundCloud y Last.fm con credenciales autorizadas.
- Tras **Añadir carpeta**, compara artista, pista, álbum, duración, ISRC e identificadores válidos de todas las fuentes.
- **Gana el lanzamiento mejor puntuado**, aunque proceda de Deezer, Spotify u otro servicio y no de MusicBrainz.
- Los resultados ambiguos, las ediciones diferentes y los conflictos de artista o identificador exigen revisión manual.
- El panel nativo de álbumes de Picard solo recibe pares Release/Recording MBID auténticos. No se convierten IDs externos en MBID.
- La selección automática modifica por defecto únicamente las etiquetas pendientes en Picard. **La escritura automática de audio está desactivada**; si se activa expresamente, crea antes una copia íntegra verificada por SHA-256.
- Conserva las reglas NEOWULF y corrige la clasificación errónea de compilaciones como Various Artists. *Curtain Call 2* sigue perteneciendo a Eminem.

## Instalación

Cierra Picard **3.0**, extrae el paquete y ejecuta **`Install-NEOWULF.cmd`** con la cuenta de escritorio (en BMAX-B6, `megal`). Se copia a `%APPDATA%\MusicBrainz\Picard\plugins3\neowulf_picard_repair`; no utiliza el `picard-cli.exe` defectuoso. Habilita el complemento en **Options → Plugins**.

## Uso y seguridad

**File → Add Folder** inicia la búsqueda. **Tools → PicardWulf** permite revisar el mejor resultado y configurar el guardado opcional; **Tools → NEOWULF** ofrece estado de fuentes y reparación del nombrado. La aplicación automática requiere un resultado inequívoco con al menos **93,5 %**. Los términos de búsqueda se envían a proveedores habilitados y deben respetarse sus límites de API. Los cambios reales en Windows siguen pendientes de validación.

## Desarrollo

```bash
python -m unittest discover -s tests -v
```

[Documentación detallada en inglés](README.md) · [Cambios](CHANGELOG.md) · [Estado](LAST_TASKS.md) · [Licencia](LICENSE)


## v1.0 S2 – estado del código

Se implementaron el consentimiento por proveedor, estados de disponibilidad, presupuestos y esperas persistentes y gestión segura de tokens. Las respuestas incompletas no se aplican automáticamente. Pasan las consultas anónimas de MusicBrainz/Deezer/iTunes y 145 pruebas; los proveedores autenticados y BMAX siguen pendientes. No se crea ninguna suscripción.

[S2 evidence / Nachweise](docs/planning/S2-EXECUTION-2026-10-14.md).
