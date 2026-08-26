# Catálogo de Equipos UNPHU

Portal estático para publicar equipos vinculados a proyectos de investigación a partir de archivos Excel de inventario.

## Cómo funciona

1. Coloca uno o varios archivos `.xlsx` en `datos/`.
2. El generador busca automáticamente la fila de encabezados y reconoce estas columnas:
   - Institución
   - Nombre del equipo
   - Tipo de equipo y funcionamiento
   - Número de serie
   - Nombre del proyecto que adquirió el equipo
   - Ubicación del equipo
   - Funcionamiento
   - Equipo apto para brindar servicio a otra institución
   - Foto
3. También extrae las **imágenes incrustadas dentro del Excel** cuando están ancladas a la fila del equipo.
4. Se crea `data/equipos.json` y las imágenes se guardan en `assets/equipos/`.
5. La web lee ese JSON y genera automáticamente las tarjetas, filtros y estadísticas.

## Probar localmente

```bash
python scripts/generar_catalogo.py
python -m http.server 8000
```

Luego abre `http://localhost:8000`.

## Publicar con GitHub Pages

1. Crea un repositorio y copia estos archivos.
2. Sube todo a la rama `main`.
3. En **Settings → Pages**, selecciona **Deploy from a branch**, rama `main`, carpeta `/ (root)`.
4. Cada vez que subas o sustituyas un Excel dentro de `datos/`, GitHub Actions ejecutará `scripts/generar_catalogo.py`, actualizará los datos/fotos y hará un commit automático.
5. GitHub Pages publicará la nueva versión.

> Nota: en **Settings → Actions → General → Workflow permissions**, el repositorio debe permitir **Read and write permissions** si la política de la cuenta no lo habilita por defecto.

## Estructura

```text
.
├── index.html
├── assets/
│   ├── styles.css
│   ├── app.js
│   └── equipos/        # fotos extraídas automáticamente
├── data/
│   └── equipos.json    # generado automáticamente
├── datos/
│   └── *.xlsx          # fuente maestra
├── scripts/
│   └── generar_catalogo.py
└── .github/workflows/
    └── actualizar-catalogo.yml
```

## Añadir nuevos proyectos

No es necesario combinar todos los proyectos en un solo Excel. Puedes subir varios archivos `.xlsx` a `datos/`; el generador los integra en un único catálogo web.
