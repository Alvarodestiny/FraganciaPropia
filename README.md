# Fragancia Propia

Web: https://fragranciapropia.es

- `index.html`: el cuestionario (página principal).
- `catalogo.json`: catálogo de perfumes. Se genera con `buiild_catalog` (script de Python) a partir del CSV de Fragrantica.
- `generar_web.py`: crea las páginas estáticas para Google a partir de `catalogo.json`:
  - `perfume/<nombre>/`: ficha de cada perfume con notas, cuándo usarlo, perfumes parecidos y alternativas más baratas
  - `marca/<nombre>/` y `marcas/`: perfumes por marca
  - `perfumes/`: listados («perfumes dulces para mujer», «perfumes de invierno para hombre», «perfumes frescos baratos»…)
  - `alternativas-baratas/`: tabla de perfumes caros y su alternativa económica
  - `sitemap.xml` y `robots.txt`
- `plantillas/estilo.css`: estilos de las páginas generadas (se copia a `estilo.css`).

## Regenerar las páginas

Cada vez que cambie `catalogo.json`:

    python generar_web.py

Cuando te aprueben en un programa de afiliados, regenera con tu plantilla de enlace
(`{URL}` se sustituye por el enlace de Notino) y pon la misma plantilla en `AFF` dentro de `index.html`:

    python generar_web.py --afiliado "https://TU-ENLACE-DE-RED/?url={URL}"

No edites a mano las carpetas generadas: se borran y se vuelven a crear en cada ejecución.
