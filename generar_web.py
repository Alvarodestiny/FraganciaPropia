#!/usr/bin/env python3
"""Genera las páginas estáticas (SEO) de Fragancia Propia a partir de catalogo.json.

Uso:
    python generar_web.py
    python generar_web.py --afiliado "https://TU-ENLACE-DE-RED/?url={URL}"

Crea (y regenera desde cero cada vez):
    perfume/<slug>/          ficha de cada perfume + similares + alternativas más baratas
    marca/<slug>/            todos los perfumes de una marca
    perfumes/<lista>/        listados: "perfumes dulces para mujer", "perfumes de invierno para hombre"...
    perfumes/  marcas/  alternativas-baratas/   páginas índice
    estilo.css  sitemap.xml  robots.txt

Solo usa la librería estándar de Python. Vuelve a ejecutarlo cada vez que cambie catalogo.json
o cuando tengas tu enlace de afiliado.
"""
import argparse, datetime, html, json, os, re, shutil, unicodedata
from urllib.parse import quote
from collections import defaultdict

SITIO = "https://fragranciapropia.es"
NOMBRE = "Fragancia Propia"
# Plantilla de afiliado: {URL} se sustituye por el enlace de Notino. Vacío = enlace normal.
AFILIADO = ""
CARPETAS = ["perfume", "marca", "perfumes", "marcas", "alternativas-baratas"]

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
def comprar(p):
    u = p.get("u") or "https://www.notino.es/search.asp?exps=" + quote(p["n"] + " " + p["b"])
    return AFILIADO.replace("{URL}", quote(u, safe="")) if AFILIADO else u


def tarjeta(p, extra=""):
    chips = "".join(f"<span>{L[k]}</span>" for k in p["k"][:3])
    return (f'<article class="card"><span class="tg t{p["t"]}">{TIER[p["t"]][0]}</span>'
            f'<h3><a href="{p["url"]}">{e(p["n"])}</a></h3><p class="brand">{e(p["b"])} · {GEN[p["g"]]}</p>'
            f'{extra}<p class="d">{e(p.get("d"))}</p><div class="chips">{chips}</div>'
            f'<div class="lk"><a href="{p["url"]}">Ver ficha</a>'
            f'<a href="{e(comprar(p))}" target="_blank" rel="sponsored nofollow noopener">Ver precio</a></div></article>')


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
    aviso = (" Algunos enlaces son de afiliado: si compras a través de ellos podemos recibir una comisión sin coste extra para ti."
             if AFILIADO else "")
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo)}</title><meta name="description" content="{e(desc)}"><link rel="canonical" href="{can}">
<meta property="og:type" content="website"><meta property="og:site_name" content="{NOMBRE}"><meta property="og:locale" content="es_ES">
<meta property="og:title" content="{e(titulo)}"><meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{can}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Figtree:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/estilo.css">
<script>try{{var t=localStorage.getItem("fp:theme");if(t==="dark"||t==="light")document.documentElement.setAttribute("data-theme",t);}}catch(e){{}}</script>
{lds}</head><body><div class="wrap">
<header class="hd"><a class="logo" href="/">{NOMBRE}</a><nav class="nav"><a href="/perfumes/">Explorar</a><a href="/alternativas-baratas/">Alternativas baratas</a><a href="/marcas/">Marcas</a></nav></header>
<main>{cuerpo}
<aside class="cta-box"><h2>¿No sabes cuál elegir?</h2><p>Responde nueve preguntas sobre tu momento del día, tu estación y tus planes, y te recomendamos perfumes económicos, de diseñador y de nicho.</p><a class="cta" href="/">Hacer el cuestionario</a></aside>
</main>
<footer class="foot"><p>Datos orientativos basados en los votos de la comunidad de Fragrantica. Los rangos de precio son aproximados y la disponibilidad depende de cada tienda.{aviso}</p>
<p><a href="/">Cuestionario</a> · <a href="/perfumes/">Explorar perfumes</a> · <a href="/alternativas-baratas/">Alternativas baratas</a> · <a href="/marcas/">Marcas</a></p></footer>
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
        titulo = f"{nombre} de {marca}: alternativas más baratas y notas"
        desc = (f"¿Buscas algo parecido a {nombre} de {marca} por menos dinero? Perfumes con un perfil olfativo similar "
                f"({y(fam)}), sus notas y cuándo llevarlo.")
    else:
        titulo = f"{nombre} de {marca}: notas, cuándo usarlo y similares"
        desc = (f"{nombre} de {marca}: perfume {GEN[p['g']]} de aromas {y(fam)}. Notas, estación, momento del día, "
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
    acc = (f'<div class="acts"><a class="cta" href="{e(comprar(p))}" target="_blank" rel="sponsored nofollow noopener">Ver precio de {e(nombre)}</a>'
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
    nav, ld = migas([("Inicio", "/"), ("Marcas", "/marcas/"), (marca, marca_url), (nombre, None)])
    h1 = f"Alternativas baratas a {e(nombre)}" if hay_alts else e(nombre)
    sub = f'<p class="kicker">{e(nombre)} · {e(marca)}</p>' if hay_alts else f'<p class="kicker">{e(marca)}</p>'
    top = (f'{nav}<article class="hero-f"><div>{sub}<h1>{h1}</h1>{intro}{acc}</div>{datos}</article>')
    return titulo, desc, top + cuerpo, [ld]


def listado(titulo_h1, intro, items, nav):
    ld = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": SITIO + p["url"], "name": f'{p["n"]} de {p["b"]}'} for i, p in enumerate(items)]}
    return f'{nav}<h1>{e(titulo_h1)}</h1><p class="lead">{intro}</p>' + rejilla(tarjeta(p) for p in items), ld


def ranking(items, n):
    return sorted(items, key=lambda p: -p["pop"])[:n]


def main():
    global AFILIADO
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalogo", default="catalogo.json")
    ap.add_argument("--salida", default=".")
    ap.add_argument("--afiliado", default=AFILIADO)
    a = ap.parse_args()
    AFILIADO = a.afiliado
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

    # Índices
    grupos = defaultdict(list)
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
    escribir(raiz, "/alternativas-baratas/", pagina("/alternativas-baratas/", "Alternativas baratas a perfumes caros: las mejores",
                                                    "Alternativas económicas a perfumes de diseñador y de nicho populares, con perfil olfativo parecido y notas en común.",
                                                    c, [ld0]), urls)

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
          f"{len(marcas)} marcas, {len(listas)} listados).")


if __name__ == "__main__":
    main()
