# Fragancia Propia

Web: https://fraganciapropia.es

- `index.html`: el cuestionario (página principal).
- `catalogo.json`: catálogo de perfumes. Se genera con `buiild_catalog` (script de Python) a partir del CSV de Fragrantica.
- `generar_web.py`: crea las páginas estáticas para Google a partir de `catalogo.json`:
  - `perfume/<nombre>/`: ficha de cada perfume con notas, cuándo usarlo, perfumes parecidos y alternativas más baratas
  - `marca/<nombre>/` y `marcas/`: perfumes por marca
  - `perfumes/`: listados («perfumes dulces para mujer», «perfumes de invierno para hombre», «perfumes frescos baratos»…)
  - `alternativas-baratas/`: tabla de perfumes caros y su alternativa económica
  - `notas/<nota>/` (y `/hombre/`, `/mujer/`, `/unisex/`, `/baratos/`): «perfumes con vainilla», «perfumes con oud para hombre»… Las variantes de cada nota (incluidas las que vienen en inglés) se agrupan en `NOTAS_ALIAS` y las descripciones están en `NOTAS_DESC`, dentro de `generar_web.py`
  - `regalar/`: ideas de regalo por persona (novio, padre, amigo invisible…)
  - `sitemap.xml` y `robots.txt`
- `plantillas/estilo.css`: estilos de las páginas generadas (se copia a `estilo.css`).

## Afiliados y datos legales

- `afiliados.json`: tiendas que salen en los botones de compra y tus códigos de afiliado.
  - Notino (red CJ): en `afiliado` pon `https://www.anrdoezrs.net/links/TU_ID_DE_WEB/type/dlg/{URL_RAW}`. Usa el formato exacto que te dé CJ.
  - Amazon: pon `"mostrar": true` y tu ID en `tag` (por ejemplo `tunombre-21`).
  - Primor (Awin): pon `"mostrar": true` y en `afiliado` el enlace profundo de Awin con `{URL}`.
- `sitio.json`: titular, NIF, domicilio y email para el aviso legal (lo exige la LSSI y lo revisan las redes de afiliados).
- `sitio.json` → `goatcounter`: código de tu cuenta de [GoatCounter](https://www.goatcounter.com) (estadísticas de visitas sin cookies). Cuenta visitas por página, procedencia y clics en los botones de tienda (eventos `compra-<tienda>`). Si lo dejas vacío no se mide nada y la política de privacidad deja de mencionarlo.

Puedes editar estos archivos desde la web de GitHub (icono del lápiz).

## Publicación automática

`.github/workflows/web.yml` ejecuta `generar_web.py` y publica la web en cada cambio de `main`.
Requiere **Settings → Pages → Source: GitHub Actions**.

Para probarlo en tu ordenador:

    python generar_web.py

No edites a mano las carpetas generadas ni `tiendas.js`: se vuelven a crear en cada ejecución.
