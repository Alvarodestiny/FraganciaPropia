#!/usr/bin/env python3
"""Genera las páginas estáticas (SEO) de Fragancia Propia a partir de catalogo.json.

Uso:
    python generar_web.py

Configuración:
    afiliados.json   tiendas de los botones de compra y tus códigos de afiliado
    sitio.json       datos del titular para el aviso legal

Crea (y regenera desde cero cada vez):
    perfume/<slug>/          ficha de cada perfume + similares + alternativas más baratas
    marca/<slug>/            todos los perfumes de una marca
    perfumes/<lista>/        listados: "perfumes dulces para mujer", "perfumes de invierno para hombre"...
    regalar/<perfil>/        ideas de regalo: "perfumes para regalar a tu novio", "amigo invisible"...
    perfumes/  marcas/  alternativas-baratas/   páginas índice
    aviso-legal/  privacidad/   páginas legales
    estilo.css  tiendas.js  analitica.js  sitemap.xml  robots.txt

Solo usa la librería estándar de Python. Con la publicación por GitHub Actions
(.github/workflows/web.yml) se ejecuta sola en cada cambio de la rama main.
"""
import argparse, datetime, html, json, os, re, shutil, unicodedata
from urllib.parse import quote, quote_plus
from collections import defaultdict

SITIO = "https://fraganciapropia.es"
NOMBRE = "Fragancia Propia"
TIENDAS = []  # se cargan de afiliados.json
SITIO_DATOS = {}  # se cargan de sitio.json
CARPETAS = ["perfume", "marca", "perfumes", "regalar", "marcas", "alternativas-baratas", "aviso-legal", "privacidad"]

L = {"fresco": "Fresco", "citrico": "Cítrico", "floral": "Floral", "dulce": "Dulce",
     "amaderado": "Amaderado", "especiado": "Especiado", "ambar": "Ambarado"}
PL = {"fresco": "frescos", "citrico": "cítricos", "floral": "florales", "dulce": "dulces",
      "amaderado": "amaderados", "especiado": "especiados", "ambar": "ambarados"}
DESC_FAM = {
    "fresco": "transmiten limpieza y ligereza: notas aromáticas, acuáticas y verdes que funcionan muy bien con calor y a diario",
    "citrico": "se abren con bergamota, limón o mandarina; son luminosos, alegres y perfectos para primavera y verano",
    "floral": "giran en torno a rosa, jazmín, iris o azahar; van de lo delicado a lo opulento",
    "dulce": "tienen vainilla, praliné, caramelo o frutas; son envolventes, cálidos y muy de otoño e invierno",
    "amaderado": "se apoyan en cedro, sándalo, vetiver o pachulí; son elegantes, secos y fáciles de llevar",
    "especiado": "llevan canela, pimienta, cardamomo o azafrán; tienen carácter y brillan en noches frías",
    "ambar": "son resinosos y profundos: ámbar, incienso, almizcle y bálsamos que dejan estela",
}
TIER = {"e": ("Económico", "normalmente por debajo de unos 60 €"),
        "d": ("Diseñador", "normalmente entre unos 70 y 150 €"),
        "n": ("Nicho", "normalmente desde unos 150 €")}
GEN = {"m": "masculino", "f": "femenino", "u": "unisex"}
INT = {1: "suave", 2: "equilibrada", 3: "intensa"}
MOM = {"mañana": "la mañana", "tarde": "la tarde", "noche": "la noche"}
ESTACIONES = ["primavera", "verano", "otoño", "invierno"]
GLIST = {"hombre": ("para hombre", {"m", "u"}), "mujer": ("para mujer", {"f", "u"}), "unisex": ("unisex", {"u"})}


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


e = lambda s: html.escape(str(s or ""), quote=True)


def y(items):
    items = [x for x in items if x]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1] if items else ""


def notas(p):
    d = (p.get("d") or "").removeprefix("Notas:").strip().rstrip(".")
    return [x.strip() for x in d.split(",") if x.strip()]


# ---------------------------------------------------------------- similitud
def preparar(P):
    for t in "edn":
        g = [p for p in P if p["t"] == t]
        for i, p in enumerate(g):
            p["pop"] = 1 - i / max(1, len(g))  # el catálogo viene ordenado por votos dentro de cada rango
    for p in P:
        p["slug"] = slug(p["n"] + " " + p["b"])
        p["url"] = "/perfume/" + p["slug"] + "/"
        p["nt"] = notas(p)
        p["ns"] = set(p["nt"])
        p["nh"] = {x.split()[0] for x in p["nt"]}
        p["fw"] = {k: w for k, w in zip(p["k"], (1, .7, .5))}
    vistos = defaultdict(int)
    for p in P:
        vistos[p["slug"]] += 1
        if vistos[p["slug"]] > 1:  # no debería pasar; por si acaso
            p["slug"] += "-" + str(vistos[p["slug"]])
            p["url"] = "/perfume/" + p["slug"] + "/"


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0


def sim(a, b):
    if {a["g"], b["g"]} == {"m", "f"}:
        return 0
    fa, fb = a["fw"], b["fw"]
    num = sum(fa[k] * fb[k] for k in fa if k in fb)
    if not num:
        return 0
    fam = num / ((sum(v * v for v in fa.values()) * sum(v * v for v in fb.values())) ** .5)
    nts = .6 * jac(a["ns"], b["ns"]) + .4 * jac(a["nh"], b["nh"])
    s = .45 * fam + .35 * nts + .1 * jac(set(a["s"]), set(b["s"])) + .05 * jac(set(a["h"]), set(b["h"])) \
        + .05 * (1 - abs(a["i"] - b["i"]) / 2)
    return s * (1 if a["g"] == b["g"] else .92)


def parecidos(p, pool, n, minimo):
    r = sorted(((sim(p, q), q) for q in pool if q is not p), key=lambda x: (-x[0], -x[1]["pop"]))
    return [(s, q) for s, q in r[:n] if s >= minimo]


def grado(s):
    return "Muy parecido" if s >= .75 else "Parecido" if s >= .63 else "Aire similar"


# ---------------------------------------------------------------- plantillas
def enlace(t, p):
    u = p.get("u") if t["id"] == "notino" and p.get("u") else t["buscar"].replace("{Q}", quote_plus(p["n"] + " " + p["b"]))
    if t.get("tag"):
        u += ("&" if "?" in u else "?") + "tag=" + quote(t["tag"])
    af = t.get("afiliado") or ""
    return af.replace("{URL}", quote(u, safe="")).replace("{URL_RAW}", u) if af else u


def con_comision(t):
    return bool(t.get("afiliado") or t.get("tag"))


def comprar(p):
    return [(t["nombre"], enlace(t, p)) for t in TIENDAS]


def botones(p, primero="cta", resto="again", texto="Ver precio en {}"):
    return "".join(f'<a class="{primero if i == 0 else resto}" href="{e(u)}" target="_blank" rel="sponsored nofollow noopener">'
                   f'{e(texto.format(n))}</a>' for i, (n, u) in enumerate(comprar(p)))


def aviso_afiliados():
    if not any(con_comision(t) for t in TIENDAS):
        return ""
    txt = " Algunos enlaces a tiendas son de afiliado: si compras a través de ellos podemos recibir una comisión sin coste extra para ti."
    if any(t["id"] == "amazon" and con_comision(t) for t in TIENDAS):
        txt += " En calidad de Afiliado de Amazon, obtengo ingresos por las compras adscritas que cumplen los requisitos aplicables."
    return txt


def tarjeta(p, extra=""):
    chips = "".join(f"<span>{L[k]}</span>" for k in p["k"][:3])
    return (f'<article class="card"><span class="tg t{p["t"]}">{TIER[p["t"]][0]}</span>'
            f'<h3><a href="{p["url"]}">{e(p["n"])}</a></h3><p class="brand">{e(p["b"])} · {GEN[p["g"]]}</p>'
            f'{extra}<p class="d">{e(p.get("d"))}</p><div class="chips">{chips}</div>'
            f'<div class="lk"><a href="{p["url"]}">Ver ficha</a>{botones(p, "", "", "Ver en {}")}</div></article>')


def tarjeta_sim(base, s, q):
    comunes = [x for x in q["nt"] if x in base["ns"]]
    txt = f'<b>{grado(s)}</b>' + (f" · comparten {e(y(comunes[:3]))}" if comunes else
                                  f" · también {y([PL[k] for k in q['k'] if k in base['fw']][:2])}")
    return tarjeta(q, f'<p class="why">{txt}</p>')


def rejilla(items):
    return f'<div class="grid">{"".join(items)}</div>'


def migas(pares):
    vis = " › ".join(f'<a href="{u}">{e(t)}</a>' if u else f"<span>{e(t)}</span>" for t, u in pares)
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": t, **({"item": SITIO + u} if u else {})}
        for i, (t, u) in enumerate(pares)]}
    return f'<nav class="crumbs" aria-label="Migas de pan">{vis}</nav>', ld


def pagina(ruta, titulo, desc, cuerpo, ld=()):
    can = SITIO + ruta
    lds = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in ld)
    aviso = aviso_afiliados()
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo)}</title><meta name="description" content="{e(desc)}"><link rel="canonical" href="{can}">
<meta property="og:type" content="website"><meta property="og:site_name" content="{NOMBRE}"><meta property="og:locale" content="es_ES">
<meta property="og:title" content="{e(titulo)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{can}">
<link rel="preload" href="/fuentes/fraunces-latin.woff2" as="font" type="font/woff2" crossorigin><link rel="stylesheet" href="/fuentes/fuentes.css">
<link rel="stylesheet" href="/estilo.css"><script src="/analitica.js" defer></script>
<script>try{{var t=localStorage.getItem("fp:theme");if(t==="dark"||t==="light")document.documentElement.setAttribute("data-theme",t);}}catch(e){{}}</script>
{lds}</head><body><div class="wrap">
<header class="hd"><a class="logo" href="/">{NOMBRE}</a><nav class="nav"><a href="/regalar/">Regalos</a><a href="/perfumes/">Explorar</a><a href="/alternativas-baratas/">Alternativas baratas</a><a href="/marcas/">Marcas</a></nav></header>
<main>{cuerpo}
<aside class="cta-box"><h2>¿No sabes cuál elegir?</h2><p>Responde nueve preguntas sobre tu momento del día, tu estación y tus planes, y te recomendamos perfumes económicos, de diseñador y de nicho.</p><a class="cta" href="/">Hacer el cuestionario</a></aside>
</main>
<footer class="foot"><p>Datos orientativos basados en los votos de la comunidad de Fragrantica. Los rangos de precio son aproximados y la disponibilidad depende de cada tienda.{aviso}</p>
<p><a href="/">Cuestionario</a> · <a href="/regalar/">Perfumes para regalar</a> · <a href="/perfumes/">Explorar perfumes</a> · <a href="/alternativas-baratas/">Alternativas baratas</a> · <a href="/marcas/">Marcas</a> · <a href="/aviso-legal/">Aviso legal</a> · <a href="/privacidad/">Privacidad y cookies</a></p></footer>
</div></body></html>
"""


def escribir(raiz, ruta, contenido, urls):
    d = os.path.join(raiz, ruta.strip("/"))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(contenido)
    urls.append(ruta)


# ---------------------------------------------------------------- páginas
def ficha(p, similares, alts, alts_d, marca_url):
    nombre, marca = p["n"], p["b"]
    fam = [PL[k] for k in p["k"]]
    hay_alts = bool(alts and alts[0][0] >= .6 or alts_d)
    if hay_alts:
        titulo = f"{nombre} de {marca}: alternativas baratas, dupes y a qué huele"
        desc = (f"¿Buscas un dupe o algo que huela parecido a {nombre} de {marca} por menos dinero? Perfumes baratos con un "
                f"perfil olfativo similar ({y(fam)}), sus notas y cuándo llevarlo.")
    else:
        titulo = f"{nombre} de {marca}: a qué huele, notas y perfumes parecidos"
        desc = (f"¿A qué huele {nombre} de {marca}? Perfume {GEN[p['g']]} de aromas {y(fam)}: notas, estación, momento del día, "
                f"intensidad y perfumes parecidos.")
    tier, nota = TIER[p["t"]]
    nt = p["nt"]
    est = y(p["s"]) or "cualquier época"
    mom = y([MOM[x] for x in p["h"]]) or "cualquier momento"
    intro = (f"<p><b>{e(nombre)}</b> es un perfume {GEN[p['g']]} de <a href=\"{marca_url}\">{e(marca)}</a> "
             f"de aromas {e(y(fam))}." + (f" Destacan notas de {e(y(nt))}." if nt else "") +
             f" La comunidad lo asocia sobre todo a {e(est)} y a {e(mom)}, con una presencia {INT.get(p['i'], 'equilibrada')}."
             f" Por precio entra en el rango <b>{tier.lower()}</b> ({nota}).</p>")
    datos = (f'<dl class="facts"><div><dt>Familia</dt><dd>{e(y([L[k] for k in p["k"]]))}</dd></div>'
             f'<div><dt>Estación</dt><dd>{e(est.capitalize())}</dd></div><div><dt>Momento</dt><dd>{e(mom.capitalize())}</dd></div>'
             f'<div><dt>Presencia</dt><dd>{INT.get(p["i"], "equilibrada").capitalize()}</dd></div>'
             f'<div><dt>Género</dt><dd>{GEN[p["g"]].capitalize()}</dd></div><div><dt>Rango</dt><dd>{tier}</dd></div></dl>')
    acc = (f'<div class="acts">{botones(p)}'
           + (f'<a class="again" href="{e(p["f"])}" target="_blank" rel="noopener">Ficha en Fragrantica</a>' if p.get("f") else "") + "</div>")
    cuerpo = ""
    if alts:
        cuerpo += (f'<section><h2>Alternativas económicas a {e(nombre)}</h2><p class="lead">Perfumes de menos de unos 60 € con un perfil '
                   f'olfativo parecido. No son copias exactas: comparten familia, notas y ocasión de uso.</p>'
                   + rejilla(tarjeta_sim(p, s, q) for s, q in alts) + "</section>")
    if alts_d:
        cuerpo += (f'<section><h2>Alternativas de diseñador a {e(nombre)}</h2><p class="lead">Si quieres algo de gama media, '
                   f'estos perfumes de diseñador tienen un aire parecido.</p>' + rejilla(tarjeta_sim(p, s, q) for s, q in alts_d) + "</section>")
    if similares:
        cuerpo += (f'<section><h2>Perfumes parecidos a {e(nombre)}</h2>' + rejilla(tarjeta_sim(p, s, q) for s, q in similares) + "</section>")
    faq = preguntas(p, similares, alts, alts_d, fam, est, mom)
    cuerpo += (f'<section><h2>Preguntas frecuentes sobre {e(nombre)}</h2><div class="faq">'
               + "".join(f"<h3>{e(q)}</h3><p>{a}</p>" for q, a in faq) + "</div></section>")
    ld_faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"<[^>]+>", "", html.unescape(a))}}
        for q, a in faq]}
    nav, ld = migas([("Inicio", "/"), ("Marcas", "/marcas/"), (marca, marca_url), (nombre, None)])
    h1 = f"Alternativas baratas a {e(nombre)}" if hay_alts else e(nombre)
    sub = f'<p class="kicker">{e(nombre)} · {e(marca)}</p>' if hay_alts else f'<p class="kicker">{e(marca)}</p>'
    top = (f'{nav}<article class="hero-f"><div>{sub}<h1>{h1}</h1>{intro}{acc}</div>{datos}</article>')
    return titulo, desc, top + cuerpo, [ld, ld_faq]


def nombra(base, lista):
    """«X de Marca (comparten a, b)» enlazado, para respuestas de las preguntas frecuentes."""
    out = []
    for _, q in lista:
        com = [x for x in q["nt"] if x in base["ns"]][:2]
        out.append(f'<a href="{q["url"]}">{e(q["n"])}</a> de {e(q["b"])}' + (f" (comparten {e(y(com))})" if com else ""))
    return y(out)


def preguntas(p, similares, alts, alts_d, fam, est, mom):
    nombre, nt = e(p["n"]), p["nt"]
    r = [(f"¿A qué huele {p['n']}?",
          f"{nombre} es un perfume {GEN[p['g']]} de aromas {e(y(fam))}." +
          (f" Sus notas principales son {e(y(nt[:8]))}." if nt else "") +
          f" Tiene una presencia {INT.get(p['i'], 'equilibrada')}."),
         (f"¿Cuándo usar {p['n']}?",
          f"La comunidad lo asocia sobre todo a {e(est)} y a {e(mom)}. " +
          {1: "Al ser suave, es fácil de llevar a diario y en sitios cerrados.",
           2: "Su intensidad equilibrada lo hace versátil: sirve tanto para el día a día como para una cita.",
           3: "Es intenso, así que con dos o tres pulverizaciones basta; luce más en exteriores o de noche."}
          .get(p["i"], ""))]
    if alts:
        r.append((f"¿Hay algún dupe barato de {p['n']}?",
                  f"No conocemos copias exactas, pero por perfil olfativo los perfumes económicos (normalmente por debajo de unos 60 €) "
                  f"que más se le parecen son {nombra(p, alts[:3])}. Huelen en la misma dirección, aunque no son idénticos: "
                  f"si puedes, pruébalos antes en tienda."))
    if alts_d:
        r.append((f"¿Qué perfume de diseñador se parece a {p['n']}?",
                  f"Si prefieres algo de gama media, prueba {nombra(p, alts_d[:2])}."))
    if similares:
        r.append((f"¿Qué perfumes se parecen a {p['n']}?",
                  f"En su mismo rango de precio, los más parecidos son {nombra(p, similares[:3])}."))
    return r


def listado(titulo_h1, intro, items, nav):
    ld = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": SITIO + p["url"], "name": f'{p["n"]} de {p["b"]}'} for i, p in enumerate(items)]}
    return f'{nav}<h1>{e(titulo_h1)}</h1><p class="lead">{intro}</p>' + rejilla(tarjeta(p) for p in items), ld


def ranking(items, n):
    return sorted(items, key=lambda p: -p["pop"])[:n]


# ---------------------------------------------------------------- regalos
# Cada perfil: géneros (con peso), familias preferidas (peso), intensidad ideal, momento preferido y secciones por rango.
PERFILES = [
    {"sl": "novio", "a": "a tu novio", "g": {"m": 1, "u": .9}, "k": {"dulce": 1, "especiado": 1, "amaderado": .8, "ambar": .8, "fresco": .4},
     "i": None, "h": "noche", "ev": "valentin",
     "intro": "Para regalar a tu pareja funcionan muy bien los perfumes con algo de calidez: dulces, especiados o amaderados, "
              "que se notan de cerca y apetecen en una cena o una cita.",
     "tips": ["Fíjate en qué perfume usa ahora: si le gusta, uno parecido de otro rango es una apuesta segura.",
              "Si es de los que se ponen perfume solo para salir, elige algo intenso y de noche; si lo usa a diario, mejor algo equilibrado.",
              "Un frasco de 50 ml suele ser suficiente para probar si le encaja sin gastar de más."]},
    {"sl": "novia", "a": "a tu novia", "g": {"f": 1, "u": .9}, "k": {"dulce": 1, "floral": 1, "ambar": .7, "citrico": .4, "fresco": .4},
     "i": None, "h": "noche", "ev": "valentin",
     "intro": "Los perfumes florales y dulces son los que más se regalan a una pareja, y por algo: son agradables, se notan "
              "y gustan a casi todo el mundo. Si ya sabes qué estilo le va, los ambarados y especiados son un acierto más personal.",
     "tips": ["Mira qué perfumes tiene en el tocador: te dicen si le van los dulces, los florales o los frescos.",
              "Si dudas entre dos, elige el de presencia equilibrada: es más fácil de llevar a diario.",
              "Un perfume nuevo de una marca que ya usa suele ser una apuesta más segura que cambiarle de estilo."]},
    {"sl": "padre", "a": "a tu padre", "g": {"m": 1, "u": .8}, "k": {"amaderado": 1, "fresco": .9, "citrico": .9, "especiado": .6},
     "i": 2, "h": "mañana", "ev": "padre",
     "intro": "Para un padre suelen acertar los perfumes clásicos y fáciles de llevar: amaderados, cítricos y frescos con "
              "presencia equilibrada, que valen para el trabajo, el fin de semana y cualquier época.",
     "tips": ["Si lleva años con el mismo perfume, regálale algo parecido en lugar de algo radicalmente distinto.",
              "Para uso diario, mejor un perfume de presencia equilibrada que uno muy intenso.",
              "Las versiones «eau de toilette» suelen ser más frescas y ligeras que las «eau de parfum»."]},
    {"sl": "madre", "a": "a tu madre", "g": {"f": 1, "u": .8}, "k": {"floral": 1, "ambar": .8, "amaderado": .6, "citrico": .5, "dulce": .4},
     "i": 2, "h": None, "ev": "madre",
     "intro": "A una madre le suelen encantar los perfumes florales y elegantes, con un toque ambarado o amaderado, "
              "y con una presencia equilibrada que se pueda llevar a diario.",
     "tips": ["Pregunta con disimulo (o mira el baño) qué perfume usa: es la mejor pista.",
              "Si le gustan los perfumes de toda la vida, los florales con fondo amaderado rara vez fallan.",
              "Evita los muy intensos si no sabes sus gustos: cansan antes."]},
    {"sl": "amigo-invisible", "a": "en el amigo invisible", "g": {"m": 1, "f": 1, "u": 1}, "k": {}, "i": 2, "h": None,
     "ev": None, "solo": "e",
     "intro": "En el amigo invisible el presupuesto es limitado y a menudo no conoces bien a la persona. Por eso aquí solo hay "
              "perfumes económicos (normalmente por debajo de unos 60 €), muy populares y versátiles, que se pueden llevar casi en cualquier época.",
     "tips": ["Si no conoces a la persona, elige un perfume unisex y de presencia equilibrada.",
              "Pide tique regalo: los perfumes precintados suelen poder cambiarse.",
              "Con poco presupuesto, un frasco pequeño de un perfume bueno luce más que uno grande de uno flojo."]},
    {"sl": "chico-joven", "a": "a un chico joven", "g": {"m": 1, "u": .85}, "k": {"fresco": 1, "dulce": 1, "citrico": .7, "especiado": .4},
     "i": None, "h": None, "ev": None,
     "intro": "Entre los chicos jóvenes triunfan dos estilos: los frescos y limpios para el día a día y los dulces y "
              "llamativos para salir de fiesta. Aquí tienes los más populares de cada rango de precio.",
     "tips": ["Para clase o el trabajo, mejor algo fresco; para salir, uno dulce o especiado.",
              "Los perfumes de diseñador más conocidos son un acierto fácil en estas edades.",
              "Si el presupuesto es ajustado, las alternativas económicas tienen perfiles muy parecidos."]},
    {"sl": "chica-joven", "a": "a una chica joven", "g": {"f": 1, "u": .85}, "k": {"dulce": 1, "floral": .8, "fresco": .7, "citrico": .6},
     "i": None, "h": None, "ev": None,
     "intro": "A las chicas jóvenes suelen gustarles los perfumes dulces y afrutados, y los florales ligeros. "
              "Estos son los más populares de cada rango de precio.",
     "tips": ["Los dulces con vainilla o frutas son los favoritos; los florales ligeros, para quien prefiere algo más discreto.",
              "Para el día a día, mejor presencia suave o equilibrada.",
              "Si no sabes cuál elegir, el cuestionario de la web te da opciones en dos minutos."]},
    {"sl": "companero-de-trabajo", "a": "a un compañero de trabajo", "g": {"m": 1, "f": 1, "u": 1},
     "k": {"fresco": 1, "citrico": 1, "amaderado": .8, "floral": .5}, "i": 1, "h": "mañana", "ev": None,
     "intro": "Para un compañero o compañera de trabajo, mejor algo discreto: perfumes frescos, cítricos o amaderados "
              "de presencia suave, pensados para el día y para sitios cerrados.",
     "tips": ["En la oficina, cuanto más suave, mejor: nadie quiere un perfume que llene la sala.",
              "Los cítricos y frescos gustan a casi todo el mundo y no molestan.",
              "Si es un regalo de grupo, uno de diseñador conocido es una apuesta segura."]},
    {"sl": "aciertan-siempre", "a": "que siempre aciertan", "sin_a": True, "g": {"m": 1, "f": 1, "u": 1}, "k": {},
     "i": 2, "h": None, "ev": None,
     "intro": "Si no sabes nada de los gustos de la persona, estos perfumes, de los más populares, versátiles y de presencia "
              "equilibrada, son lo más parecido a un acierto seguro. Fíjate en si son masculinos, femeninos o unisex.",
     "tips": ["Muy popular, presencia equilibrada y válido para varias estaciones: esa es la fórmula del regalo seguro; si dudas del género, elige uno unisex.",
              "Pide tique regalo por si acaso.",
              "Si conoces algo de sus gustos, mejor una de las páginas más concretas de esta sección."]},
]
SECCIONES = [("d", "Para acertar seguro", "Perfumes de diseñador muy conocidos y valorados ({})."),
             ("e", "Con presupuesto ajustado", "Opciones económicas bien valoradas ({})."),
             ("n", "Para sorprender", "Perfumes de nicho, menos vistos y más especiales ({}).")]
SEC_GEN = [("m", "Para él"), ("f", "Para ella"), ("u", "Para cualquiera (unisex)")]


def evento(clave, hoy):
    """Ocasión de regalo según la fecha de generación (la web se regenera cada mes)."""
    m, d, a = hoy.month, hoy.day, hoy.year
    if m == 12 or m == 11:
        return f"Navidad {a}"
    if m == 1 and d <= 6:
        return f"Reyes {a}"
    if clave == "valentin" and m in (1, 2) and not (m == 2 and d > 14):
        return f"San Valentín {a}"
    if clave == "padre" and (m == 2 and d > 14 or m == 3 and d <= 19):
        return f"Día del Padre {a}"
    if clave == "madre" and (m == 4 or m == 5 and d <= 10):
        return f"Día de la Madre {a}"
    return ""


def nota_regalo(perf, p):
    fam = [PL[k] for k in p["k"] if k in perf["k"]][:2] or [PL[k] for k in p["k"][:2]]
    est = "todo el año" if len(p["s"]) >= 2 and set(p["s"]) & {"primavera", "verano"} and set(p["s"]) & {"otoño", "invierno"} \
        else y(p["s"]) or "cualquier época"
    return f'<p class="why">{e(y(fam).capitalize())} · {e(est)} · presencia {INT.get(p["i"], "equilibrada")}</p>'


def puntua(perf, p):
    g = perf["g"].get(p["g"], 0)
    if not g:
        return 0
    fam = sum(w * perf["k"].get(k, 0) for k, w in p["fw"].items()) / 2.2 if perf["k"] else .5
    inten = 1 if perf["i"] is None else (1, .8, .55)[abs(p["i"] - perf["i"])]
    mom = 1.1 if perf["h"] and perf["h"] in p["h"] else 1
    vers = 1.08 if len(p["s"]) >= 2 else 1
    return g * (.2 + p["pop"]) * (.6 + fam) * inten * mom * vers


def regalos(raiz, P, urls):
    hoy = datetime.date.today()
    filas = []
    for perf in PERFILES:
        ev = evento(perf["ev"], hoy)
        nombre = f"Perfumes para regalar {perf['a']}"
        ruta = f"/regalar/{perf['sl']}/"
        usados, secciones, todos = set(), [], []
        if perf.get("solo"):
            for gk, tit in SEC_GEN:
                pool = [p for p in P if p["t"] == perf["solo"] and p["g"] == gk]
                it = sorted(pool, key=lambda p: -puntua(perf, p))[:6]
                secciones.append((tit, "", it))
        else:
            for t, tit, sub in SECCIONES:
                pool = [p for p in P if p["t"] == t and puntua(perf, p) > 0]
                it = sorted(pool, key=lambda p: -puntua(perf, p))[:6 if t != "n" else 4]
                secciones.append((tit, sub.format(TIER[t][1]), it))
        for _, _, it in secciones:
            todos += it
        n = len(todos)
        titulo = f"{nombre}: {n} ideas" + ("" if perf.get("sin_a") else " que aciertan") + (f" ({ev})" if ev else "")
        desc = (f"{n} perfumes para regalar {perf['a']}" if not perf.get("sin_a") else f"{n} perfumes {perf['a']}") + \
               (f" en {ev}" if ev else "") + ": opciones de diseñador, económicas y de nicho, con por qué encajan y dónde comprarlos."
        nav, ld0 = migas([("Inicio", "/"), ("Regalos", "/regalar/"), (nombre, None)])
        cuerpo = (f'{nav}<p class="kicker">{e(ev) if ev else "Ideas de regalo"}</p><h1>{e(nombre)}</h1>'
                  f'<p class="lead">{e(perf["intro"])}</p>')
        for tit, sub, it in secciones:
            if not it:
                continue
            cuerpo += (f'<section><h2>{e(tit)}</h2>' + (f'<p class="lead">{e(sub)}</p>' if sub else "")
                       + rejilla(tarjeta(p, nota_regalo(perf, p)) for p in it) + "</section>")
        cuerpo += ('<section><h2>Consejos para acertar</h2><ul class="tips">' + "".join(f"<li>{e(t)}</li>" for t in perf["tips"])
                   + '</ul><p>¿Sigues sin decidirte? Responde al <a href="/">cuestionario</a> pensando en la persona a la que se lo vas a '
                   'regalar y te recomendaremos perfumes según su momento del día, su estación y sus planes.</p></section>')
        otros = [x for x in PERFILES if x is not perf]
        cuerpo += ('<section><h2>Más ideas de regalo</h2><ul class="cols">' + "".join(
            f'<li><a href="/regalar/{x["sl"]}/">Perfumes para regalar {e(x["a"])}</a></li>' for x in otros) + "</ul></section>")
        ld = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "url": SITIO + p["url"], "name": f'{p["n"]} de {p["b"]}'} for i, p in enumerate(todos)]}
        escribir(raiz, ruta, pagina(ruta, titulo, desc, cuerpo, [ld0, ld]), urls)
        filas.append((perf, nombre, ruta))

    ev = evento(None, hoy)
    nav, ld0 = migas([("Inicio", "/"), ("Regalos", None)])
    faq = [("¿Qué perfume regalar si no sé qué le gusta?",
            "Lo más seguro es un perfume unisex, muy popular, de presencia equilibrada y que valga para varias estaciones. "
            "Tienes una selección en <a href=\"/regalar/aciertan-siempre/\">perfumes que siempre aciertan</a>."),
           ("¿Cuánto gastar en un perfume de regalo?",
            "Hay perfumes económicos muy bien valorados por debajo de unos 60 €; los de diseñador suelen estar entre 70 y 150 € "
            "y los de nicho, desde unos 150 €. Un frasco de 50 ml es una buena medida para regalar."),
           ("¿Se puede cambiar un perfume regalado?",
            "Depende de la tienda, pero normalmente sí mientras siga precintado. Pide tique regalo y no abras el celofán."),
           ("¿Eau de parfum o eau de toilette?",
            "La eau de parfum tiene más concentración y dura más; la eau de toilette es más ligera y fresca. Para el día a día o "
            "para alguien que no suele usar perfume, la eau de toilette es una apuesta más segura.")]
    ld_faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"<[^>]+>", "", a)}} for q, a in faq]}
    c = (f'{nav}<p class="kicker">{e(ev) if ev else "Ideas de regalo"}</p><h1>Perfumes para regalar</h1>'
         f'<p class="lead">Ideas de perfume según a quién se lo regalas, con opciones de diseñador, económicas y de nicho. '
         f'Cada selección mezcla popularidad, versatilidad y el estilo que suele gustar a esa persona.</p>'
         '<div class="grid">' + "".join(
             f'<article class="card"><h3><a href="{r}">{e(n)}</a></h3><p class="d">{e(perf["intro"].split(". ")[0].rstrip("."))}.</p>'
             f'<div class="lk"><a href="{r}">Ver ideas</a></div></article>' for perf, n, r in filas) + "</div>"
         '<section><h2>Preguntas frecuentes</h2><div class="faq">' + "".join(f"<h3>{e(q)}</h3><p>{a}</p>" for q, a in faq) +
         "</div></section>")
    escribir(raiz, "/regalar/", pagina("/regalar/", "Perfumes para regalar: ideas que aciertan" + (f" ({ev})" if ev else ""),
                                       "Ideas de perfume para regalar a tu pareja, tu padre, tu madre, en el amigo invisible o a alguien "
                                       "cuyos gustos no conoces, con opciones para todos los presupuestos.", c, [ld0, ld_faq]), urls)
    return filas


def leer_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return defecto


def legales(raiz, urls):
    d = {k: str(SITIO_DATOS.get(k) or "").strip() for k in ("titular", "nif", "domicilio", "email")}
    falta = [k for k, v in d.items() if not v]
    if falta:
        print("AVISO: completa sitio.json (" + ", ".join(falta) + ") para que el aviso legal sea válido.")
    v = {k: e(x) if x else "[pendiente]" for k, x in d.items()}
    redes = [t["nombre"] for t in TIENDAS if con_comision(t)]
    nav, ld = migas([("Inicio", "/"), ("Aviso legal", None)])
    c = (f'{nav}<h1>Aviso legal</h1><div class="prose">'
         f'<h2>Titular</h2><p>En cumplimiento de la Ley 34/2002 de Servicios de la Sociedad de la Información (LSSI), se informa de que '
         f'el titular de {NOMBRE} ({SITIO.split("//")[1]}) es <b>{v["titular"]}</b>, con NIF {v["nif"]} y domicilio en {v["domicilio"]}. '
         f'Contacto: {v["email"]}.</p>'
         f'<h2>Objeto</h2><p>{NOMBRE} es una web informativa que recomienda perfumes según las preferencias de cada persona. '
         f'No vende productos: los enlaces de compra llevan a tiendas externas, que son las responsables de los precios, la disponibilidad, '
         f'el envío y la atención al cliente.</p>'
         f'<h2>Enlaces de afiliado</h2><p>Algunos enlaces a tiendas pueden ser de afiliado. Si compras a través de ellos, {NOMBRE} puede '
         f'recibir una comisión sin que el precio cambie para ti. Esto no influye en las recomendaciones, que se calculan a partir de '
         f'tus respuestas y de los datos del catálogo.' + (f" Programas actuales: {e(y(redes))}." if redes else "") +
         (" En calidad de Afiliado de Amazon, obtengo ingresos por las compras adscritas que cumplen los requisitos aplicables."
          if any(t["id"] == "amazon" and con_comision(t) for t in TIENDAS) else "") + '</p>'
         f'<h2>Información sobre los perfumes</h2><p>Las notas, estaciones, momentos de uso e intensidades se basan en los votos de la '
         f'comunidad de Fragrantica y son orientativos. Los rangos de precio son aproximados. Las marcas y nombres de perfumes pertenecen '
         f'a sus respectivos titulares y se citan solo con fines informativos. Las «alternativas» indican perfumes con un perfil olfativo '
         f'parecido, no copias ni productos equivalentes.</p>'
         f'<h2>Propiedad intelectual</h2><p>Los textos, el diseño y el código de esta web pertenecen a su titular, salvo los datos y '
         f'marcas de terceros mencionados.</p></div>')
    escribir(raiz, "/aviso-legal/", pagina("/aviso-legal/", f"Aviso legal | {NOMBRE}",
                                           f"Aviso legal de {NOMBRE}: titular, objeto de la web y enlaces de afiliado.", c, [ld]), urls)
    nav, ld = migas([("Inicio", "/"), ("Privacidad y cookies", None)])
    fecha = e(SITIO_DATOS.get("actualizado") or datetime.date.today().isoformat())
    c = (f'{nav}<h1>Privacidad y cookies</h1><div class="prose"><p class="n">Última actualización: {fecha}</p>'
         f'<h2>1. Responsable del tratamiento</h2><p>{v["titular"]}, con NIF {v["nif"]} y domicilio en {v["domicilio"]}. '
         f'Contacto: {v["email"]}.</p>'
         f'<h2>2. Qué datos tratamos y para qué</h2><p>{NOMBRE} no tiene formularios, cuentas de usuario ni newsletter, '
         f'y no te pide datos personales. Tus respuestas al cuestionario se procesan solo en tu navegador y no se envían '
         f'a ningún servidor.</p><ul>'
         f'<li><b>Datos técnicos de conexión</b> (dirección IP, navegador, página solicitada): los registra automáticamente el servicio '
         f'de alojamiento para servir la web y protegerla frente a abusos. Base legal: interés legítimo en el funcionamiento y la '
         f'seguridad de la web (art. 6.1.f RGPD).</li>'
         + (f'<li><b>Estadísticas de visitas</b>: usamos <b>GoatCounter</b> para saber cuántas personas visitan cada página, desde '
            f'qué web o buscador llegan y en qué botones de tienda se hace clic. Registra la página visitada, la web de procedencia, '
            f'el navegador y sistema operativo (sin la cadena completa), el ancho de pantalla, el idioma y el país aproximado. '
            f'No usa cookies ni almacenamiento local y no guarda tu dirección IP: solo la mantiene en memoria, junto con el '
            f'navegador, hasta 8 horas para no contar dos veces la misma visita, y después se descarta. No permite identificarte ni '
            f'seguirte entre webs. Solo vemos cifras agregadas. Base legal: interés legítimo en conocer el uso de la web para mejorarla '
            f'(art. 6.1.f RGPD). Puedes evitarlo con un bloqueador de contenido.</li>' if SITIO_DATOS.get("goatcounter") else "") +
         f'<li><b>Correos que nos envíes</b>: si escribes a {v["email"]}, usaremos tu dirección y tu mensaje solo para responderte. '
         f'Base legal: tu consentimiento al escribirnos (art. 6.1.a RGPD). Los conservaremos el tiempo necesario para atender tu consulta.</li></ul>'
         f'<h2>3. Destinatarios y transferencias internacionales</h2><p>La web está alojada en <b>GitHub Pages</b> (GitHub, Inc., '
         f'Estados Unidos), que actúa como proveedor de alojamiento y conserva los registros técnicos según su propia política de '
         f'privacidad. GitHub está adherida al Marco de Privacidad de Datos UE-EE. UU. (EU-US Data Privacy Framework), que la Comisión '
         f'Europea considera una garantía adecuada para estas transferencias.'
         + (' Las estadísticas de visitas las presta <b>GoatCounter</b>, servicio operado desde Irlanda, que guarda los datos '
            'agregados en servidores de Hetzner en Finlandia y Alemania (Unión Europea); no hay transferencia fuera del EEE.' if SITIO_DATOS.get("goatcounter") else "") +
         f' No cedemos ni vendemos datos a terceros.</p>'
         f'<h2>4. Cookies y almacenamiento local</h2><p><b>Esta web no instala cookies</b>, ni propias ni de terceros' +
         (', tampoco para las estadísticas de visitas' if SITIO_DATOS.get("goatcounter") else '') +
         f'. Las tipografías se sirven desde nuestro propio dominio, sin conectarse a servicios externos.</p><p>Usamos el almacenamiento local de tu '
         f'navegador (localStorage) solo para recordar los perfumes que guardas como favoritos y si prefieres el modo claro u oscuro. '
         f'Esa información no sale de tu dispositivo, no sirve para identificarte y es necesaria para funciones que tú solicitas, por '
         f'lo que no requiere consentimiento (art. 22.2 LSSI). Puedes borrarla desde los ajustes de tu navegador.</p>'
         f'<h2>5. Enlaces a tiendas y programas de afiliados</h2><p>Al pulsar un enlace de compra sales de {NOMBRE}. A partir de ese '
         f'momento, la tienda y, en su caso, la red de afiliados (por ejemplo CJ, Awin o Amazon) pueden instalar sus propias cookies '
         f'en sus dominios para registrar que la visita llegó desde aquí y atribuir la compra. Ese tratamiento es responsabilidad de '
         f'cada tienda o red y se rige por sus políticas de privacidad y cookies, que te recomendamos revisar. {NOMBRE} no recibe '
         f'datos personales tuyos de esas compras, solo informes agregados de comisiones.</p>'
         f'<h2>6. Tus derechos</h2><p>Puedes ejercer tus derechos de acceso, rectificación, supresión, oposición, limitación del '
         f'tratamiento y portabilidad escribiendo a {v["email"]}. Si consideras que no hemos atendido correctamente tu solicitud, '
         f'puedes presentar una reclamación ante la Agencia Española de Protección de Datos (www.aepd.es).</p>'
         f'<h2>7. Cambios</h2><p>Si cambiamos la forma de tratar datos (por ejemplo, si añadimos un formulario o una nueva herramienta), '
         f'actualizaremos esta página y su fecha.</p></div>')
    escribir(raiz, "/privacidad/", pagina("/privacidad/", f"Privacidad y cookies | {NOMBRE}",
                                          f"Política de privacidad y cookies de {NOMBRE}.", c, [ld]), urls)


def tiendas_js(raiz):
    cfg = [{"id": t["id"], "n": t["nombre"], "b": t["buscar"], "a": t.get("afiliado") or "", "tag": t.get("tag") or ""} for t in TIENDAS]
    with open(os.path.join(raiz, "tiendas.js"), "w", encoding="utf-8") as f:
        f.write("/* Generado por generar_web.py a partir de afiliados.json: no lo edites a mano. */\n"
                f"window.FP_TIENDAS={json.dumps(cfg, ensure_ascii=False)};\n"
                f"window.FP_AVISO={json.dumps(aviso_afiliados().strip(), ensure_ascii=False)};\n")


def analitica_js(raiz):
    """Estadísticas de visitas con GoatCounter (sin cookies). Se activa poniendo tu código en sitio.json → goatcounter."""
    codigo = re.sub(r"[^a-z0-9-]", "", str(SITIO_DATOS.get("goatcounter") or "").lower())
    js = "/* Generado por generar_web.py a partir de sitio.json (goatcounter): no lo edites a mano. */\n"
    if codigo:
        js += ("(function(){var s=document.createElement('script');s.async=true;s.src='https://gc.zgo.at/count.js';"
               f"s.setAttribute('data-goatcounter','https://{codigo}.goatcounter.com/count');document.head.appendChild(s);"
               # Cuenta los clics en los botones de compra (también los del cuestionario, que se crean después).
               "document.addEventListener('click',function(ev){var a=ev.target.closest&&ev.target.closest('a[rel~=\"sponsored\"]');"
               "if(!a||!window.goatcounter||!window.goatcounter.count)return;"
               "var t=(a.textContent||'').replace(/^Ver (precio )?en /,'').trim().toLowerCase();"
               "window.goatcounter.count({path:'compra-'+t,title:'Clic en '+t+' desde '+location.pathname,event:true});});})();\n")
    with open(os.path.join(raiz, "analitica.js"), "w", encoding="utf-8") as f:
        f.write(js)
    return codigo


def main():
    global TIENDAS, SITIO_DATOS
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalogo", default="catalogo.json")
    ap.add_argument("--salida", default=".")
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(__file__))
    TIENDAS = [t for t in leer_json(os.path.join(base, "afiliados.json"), {}).get("tiendas", []) if t.get("mostrar")] or \
        [{"id": "notino", "nombre": "Notino", "buscar": "https://www.notino.es/search.asp?exps={Q}"}]
    SITIO_DATOS = leer_json(os.path.join(base, "sitio.json"), {})
    with open(a.catalogo, encoding="utf-8") as f:
        P = json.load(f)
    preparar(P)
    raiz = a.salida
    for c in CARPETAS:
        shutil.rmtree(os.path.join(raiz, c), ignore_errors=True)
    urls = ["/"]
    econ = [p for p in P if p["t"] == "e"]
    dise = [p for p in P if p["t"] == "d"]
    marcas = defaultdict(list)
    for p in P:
        marcas[p["b"]].append(p)
    murl = {m: "/marca/" + slug(m) + "/" for m in marcas}

    # Fichas
    con_alts = []
    for i, p in enumerate(P):
        alts = parecidos(p, econ, 6, .55) if p["t"] in "dn" else []
        alts_d = parecidos(p, dise, 3, .55) if p["t"] == "n" else []
        sims = parecidos(p, [q for q in P if q["t"] == p["t"] and q["b"] != p["b"]], 6, .45)
        if alts and alts[0][0] >= .6:
            con_alts.append((p, alts[0]))
        t, d, c, ld = ficha(p, sims, alts, alts_d, murl[p["b"]])
        escribir(raiz, p["url"], pagina(p["url"], t, d, c, ld), urls)
        if i % 500 == 0:
            print(f"  fichas: {i}/{len(P)}")

    # Marcas
    for m, items in marcas.items():
        nav, ld0 = migas([("Inicio", "/"), ("Marcas", "/marcas/"), (m, None)])
        tiers = y(sorted({TIER[p["t"]][0].lower() for p in items}))
        fams = defaultdict(int)
        for p in items:
            for k in p["k"][:1]:
                fams[k] += 1
        top = [PL[k] for k, _ in sorted(fams.items(), key=lambda x: -x[1])[:2]]
        intro = (f"Los {len(items)} perfumes de {e(m)} de nuestro catálogo, ordenados por popularidad. "
                 f"Predominan los aromas {e(y(top))} y la marca se mueve en el rango {e(tiers)}.") if len(items) > 1 else \
                f"El perfume de {e(m)} de nuestro catálogo, con sus notas y alternativas."
        c, ld = listado(f"Perfumes de {m}", intro, ranking(items, 200), nav)
        escribir(raiz, murl[m], pagina(murl[m], f"Perfumes de {m}: los más populares y sus notas",
                                       f"Los perfumes más populares de {m}: notas, estación, intensidad y alternativas más baratas.",
                                       c, [ld0, ld]), urls)

    # Listados temáticos
    listas = []

    def lista(sl, h1, titulo, desc, intro, items, grupo):
        if len(items) < 6:
            return
        ruta = "/perfumes/" + sl + "/"
        nav, ld0 = migas([("Inicio", "/"), ("Explorar", "/perfumes/"), (h1, None)])
        c, ld = listado(h1, intro, items, nav)
        escribir(raiz, ruta, pagina(ruta, titulo, desc, c, [ld0, ld]), urls)
        listas.append((grupo, h1, ruta))

    for gk, (gtxt, gs) in GLIST.items():
        for k in L:
            it = ranking([p for p in P if p["g"] in gs and k in p["k"][:2]], 30)
            h1 = f"Perfumes {PL[k]} {gtxt}"
            lista(f"{PL[k]}-{gk}".replace("í", "i"), h1, f"{h1}: los mejores por popularidad",
                  f"Los perfumes {PL[k]} {gtxt} más valorados, de económicos a nicho, con sus notas y cuándo llevarlos.",
                  f"Los perfumes {PL[k]} {e(DESC_FAM[k])}. Aquí tienes los más populares {gtxt}, de todos los rangos de precio.",
                  it, "Por familia olfativa")
        for s in ESTACIONES:
            it = ranking([p for p in P if p["g"] in gs and s in p["s"]], 30)
            h1 = f"Perfumes de {s} {gtxt}"
            lista(f"{slug(s)}-{gk}", h1, f"{h1}: los más votados",
                  f"Los mejores perfumes de {s} {gtxt} según la comunidad: notas, intensidad y precio orientativo.",
                  f"Perfumes que la comunidad asocia sobre todo al {s}, {gtxt}. Ordenados por popularidad.", it, "Por estación")
        for t, (tn, nota) in TIER.items():
            adj = {"e": "baratos", "d": "de diseñador", "n": "de nicho"}[t]
            it = ranking([p for p in P if p["g"] in gs and p["t"] == t], 30)
            h1 = f"Perfumes {adj} {gtxt}"
            lista(f"{slug(adj)}-{gk}", h1, f"{h1}: los más populares",
                  f"Los perfumes {adj} {gtxt} más populares ({nota}), con notas y perfumes parecidos.",
                  f"Perfumes {gtxt} del rango {tn.lower()}, {nota}. Ordenados por popularidad.", it, "Por precio")
        for m in ["noche", "mañana"]:
            it = ranking([p for p in P if p["g"] in gs and m in p["h"]], 30)
            h1 = f"Perfumes para {MOM[m]} {gtxt}"
            lista(f"{slug(m)}-{gk}", h1, f"{h1}: los mejores",
                  f"Perfumes {gtxt} para {MOM[m]}: los más populares, con notas, intensidad y precio orientativo.",
                  f"Perfumes {gtxt} que la comunidad prefiere para {MOM[m]}.", it, "Por momento del día")
    for k in L:
        it = ranking([p for p in econ if k in p["k"][:2]], 30)
        h1 = f"Perfumes {PL[k]} baratos"
        lista(f"{PL[k]}-baratos".replace("í", "i"), h1, f"{h1}: los mejores por menos de 60 €",
              f"Perfumes {PL[k]} baratos y bien valorados, normalmente por debajo de unos 60 €.",
              f"Los perfumes {PL[k]} {e(DESC_FAM[k])}. Estos son los más populares por debajo de unos 60 €.", it, "Baratos por familia")

    # Regalos
    regalo = regalos(raiz, P, urls)

    # Índices
    grupos = defaultdict(list)
    for _, n, r in regalo:
        grupos["Para regalar"].append(f'<li><a href="{r}">{e(n)}</a></li>')
    for g, h1, ruta in listas:
        grupos[g].append(f'<li><a href="{ruta}">{e(h1)}</a></li>')
    nav, ld0 = migas([("Inicio", "/"), ("Explorar", None)])
    c = (f'{nav}<h1>Explorar perfumes</h1><p class="lead">{len(P)} perfumes de {len(marcas)} marcas, organizados por familia, '
         f'estación, momento del día y precio.</p>' +
         "".join(f'<section><h2>{g}</h2><ul class="cols">{"".join(v)}</ul></section>' for g, v in grupos.items()) +
         '<section><h2>Marcas más populares</h2><ul class="cols">' +
         "".join(f'<li><a href="{murl[m]}">{e(m)}</a></li>' for m in sorted(marcas, key=lambda m: -len(marcas[m]))[:30]) +
         '</ul><p><a href="/marcas/">Ver todas las marcas</a></p></section>')
    escribir(raiz, "/perfumes/", pagina("/perfumes/", "Explorar perfumes por familia, estación y precio",
                                        "Listados de perfumes para hombre, mujer y unisex por familia olfativa, estación, momento del día y rango de precio.",
                                        c, [ld0]), urls)

    letras = defaultdict(list)
    for m in sorted(marcas, key=lambda s: slug(s)):
        letras[(slug(m)[:1] or "#").upper() if slug(m)[:1].isalpha() else "#"].append(m)
    nav, ld0 = migas([("Inicio", "/"), ("Marcas", None)])
    c = (f'{nav}<h1>Marcas de perfume</h1><p class="lead">{len(marcas)} marcas, de las más asequibles al nicho.</p>' +
         "".join(f'<section><h2>{l}</h2><ul class="cols">' + "".join(
             f'<li><a href="{murl[m]}">{e(m)}</a> <span class="n">{len(marcas[m])}</span></li>' for m in ms) + "</ul></section>"
                 for l, ms in letras.items()))
    escribir(raiz, "/marcas/", pagina("/marcas/", "Marcas de perfume de la A a la Z",
                                      f"Todas las marcas de perfume del catálogo de {NOMBRE}: {len(marcas)} marcas con sus perfumes más populares.",
                                      c, [ld0]), urls)

    filas = sorted(con_alts, key=lambda x: -x[0]["pop"])[:300]
    nav, ld0 = migas([("Inicio", "/"), ("Alternativas baratas", None)])
    c = (f'{nav}<h1>Alternativas baratas a perfumes caros</h1><p class="lead">Perfumes de diseñador y de nicho populares y, al lado, '
         f'la opción económica con el perfil olfativo más parecido. Entra en cada uno para ver más alternativas.</p>'
         '<div class="table"><table><thead><tr><th>Perfume</th><th>Alternativa económica</th><th>Por qué se parecen</th></tr></thead><tbody>' +
         "".join(f'<tr><td><a href="{p["url"]}">{e(p["n"])}</a><br><span class="n">{e(p["b"])} · {TIER[p["t"]][0]}</span></td>'
                 f'<td><a href="{q["url"]}">{e(q["n"])}</a><br><span class="n">{e(q["b"])}</span></td>'
                 f'<td>{grado(s)}' + (f' · {e(y([x for x in q["nt"] if x in p["ns"]][:3]))}' if p["ns"] & q["ns"] else "") + '</td></tr>'
                 for p, (s, q) in filas) + "</tbody></table></div>")
    escribir(raiz, "/alternativas-baratas/", pagina("/alternativas-baratas/", "Alternativas baratas y dupes de perfumes caros",
                                                    "Dupes y alternativas económicas a perfumes de diseñador y de nicho populares, con perfil olfativo parecido y notas en común.",
                                                    c, [ld0]), urls)

    legales(raiz, urls)
    tiendas_js(raiz)
    if not analitica_js(raiz):
        print("AVISO: sin estadísticas de visitas. Pon tu código de GoatCounter en sitio.json (goatcounter).")

    # CSS, sitemap, robots
    shutil.copyfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "plantillas", "estilo.css"), os.path.join(raiz, "estilo.css"))
    hoy = datetime.date.today().isoformat()
    with open(os.path.join(raiz, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        f.writelines(f"<url><loc>{SITIO}{u}</loc><lastmod>{hoy}</lastmod></url>\n" for u in urls)
        f.write("</urlset>\n")
    with open(os.path.join(raiz, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {SITIO}/sitemap.xml\n")
    print(f"Listo: {len(urls)} páginas ({len(P)} fichas, {len(con_alts)} con alternativas baratas, "
          f"{len(marcas)} marcas, {len(listas)} listados, {len(regalo)} páginas de regalo).")


if __name__ == "__main__":
    main()
