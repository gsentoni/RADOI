#!/usr/bin/env python3
"""
Indicadores de un árbol de impacto (esquema arbol-impacto v0).

Uso:   python3 indicadores.py caso.json            -> informe legible
       python3 indicadores.py caso.json --json     -> resultados en JSON
       python3 indicadores.py caso.json --html tablero.html
                                                   -> tablero visual (un solo archivo HTML)

Sin dependencias externas. Los pesos de la sección PARÁMETROS son decisiones de
diseño declaradas, no verdades: el script informa cuánto cambian los resultados
si se los mueve (análisis de sensibilidad).
"""
import json, math, random, sys
from collections import defaultdict

# ------------------------------------------------------------------ PARÁMETROS
# Aristas que representan derivación (las de 'contexto' solo dicen dónde ocurrió algo).
ARISTAS_DERIVACION = {"precursor", "derivacion_conceptual", "ingenieria", "comercializacion",
                      "despliegue", "documentacion", "formacion"}
# Nodos que cuentan como impacto fuera de la publicación académica.
TIPOS_IMPACTO = {"patente", "software", "producto", "despliegue", "empresa", "politica"}
# Hipótesis de valoración (solo para el indicador de concentración en la cola).
PESO_TIPO = {"tesis": 1, "publicacion": 1, "formacion": 2, "patente": 3, "software": 4,
             "producto": 5, "despliegue": 6, "empresa": 6, "politica": 6}
FACTOR_ACTIVO = 1.5          # un nodo que sigue activo pesa más (persistencia, no decaimiento)
PESO_RESULTADO_MEDIDO = 3    # suma por cada resultado cuantificado con fuente
FRACCION_COLA = 0.20         # la "cola": el 20% de nodos de mayor valor
SENSIBILIDAD_RANGO = 0.5     # cada peso se multiplica por U(1-r, 1+r)
SENSIBILIDAD_CORRIDAS = 2000
SEMILLA = 1997
# ------------------------------------------------------------------------------

RANGO = {"A": 3, "B": 2, "C": 1}
LETRA = {3: "A", 2: "B", 1: "C"}


def cargar(path):
    d = json.load(open(path, encoding="utf-8"))
    nodos = {n["id"]: n for n in d["nodos"]}
    for a in d["aristas"]:
        for k in ("desde", "hacia"):
            if a[k] not in nodos:
                sys.exit(f"Arista con nodo inexistente: {a[k]}")
    return d, nodos


def sucesores(d, solo_derivacion=True):
    s = defaultdict(list)
    for a in d["aristas"]:
        if not solo_derivacion or a["tipo"] in ARISTAS_DERIVACION:
            s[a["desde"]].append(a)
    return s


def alcanzables(raiz, suc):
    vistos, pila = set(), [raiz]
    while pila:
        u = pila.pop()
        for a in suc[u]:
            if a["hacia"] not in vistos:
                vistos.add(a["hacia"]); pila.append(a["hacia"])
    vistos.discard(raiz)
    return vistos


def orden_topologico(nodos, suc):
    grado = {n: 0 for n in nodos}
    for u in suc:
        for a in suc[u]:
            grado[a["hacia"]] += 1
    cola = [n for n in nodos if grado[n] == 0]; orden = []
    while cola:
        u = cola.pop(); orden.append(u)
        for a in suc[u]:
            grado[a["hacia"]] -= 1
            if grado[a["hacia"]] == 0:
                cola.append(a["hacia"])
    if len(orden) != len(nodos):
        sys.exit("El grafo tiene ciclos: un árbol de impacto debe ser acíclico.")
    return orden


def cadena_mas_documentada(raiz, suc, orden, override=None):
    """Para cada nodo: el camino desde la raíz cuyo eslabón más débil tiene la mejor evidencia
    (problema del camino más ancho en un DAG). override: {(desde,hacia): rango} para simular mejoras."""
    mejor = {raiz: (4, [])}  # rango 4 = sin eslabones todavía
    for u in orden:
        if u not in mejor:
            continue
        for a in suc[u]:
            r = RANGO[a["evidencia"]]
            if override and (a["desde"], a["hacia"]) in override:
                r = override[(a["desde"], a["hacia"])]
            cand = (min(mejor[u][0], r), mejor[u][1] + [a])
            v = a["hacia"]
            if v not in mejor or cand[0] > mejor[v][0] or (cand[0] == mejor[v][0] and len(cand[1]) < len(mejor[v][1])):
                mejor[v] = cand
    return mejor


def camino_mas_largo(raiz, suc, orden, destinos):
    largo = {raiz: (0, [])}
    for u in orden:
        if u not in largo:
            continue
        for a in suc[u]:
            v = a["hacia"]; cand = (largo[u][0] + 1, largo[u][1] + [a])
            if v not in largo or cand[0] > largo[v][0]:
                largo[v] = cand
    cands = [(largo[v][0], v) for v in destinos if v in largo]
    if not cands:
        return None
    L, v = max(cands)
    return v, largo[v][1]


def valor_nodo(n, pesos):
    v = pesos.get(n["tipo"], 0)
    if n.get("estado") == "activo":
        v *= FACTOR_ACTIVO
    v += PESO_RESULTADO_MEDIDO * len(n.get("resultados", []))
    return v


def concentracion_cola(ids, nodos, pesos):
    vals = sorted((valor_nodo(nodos[i], pesos) for i in ids), reverse=True)
    total = sum(vals)
    k = max(1, math.ceil(FRACCION_COLA * len(vals)))
    return (sum(vals[:k]) / total if total else 0.0), k


def calcular(d, nodos):
    caso = d["caso"]; raiz = caso["raiz"]; anio0 = nodos[raiz]["anio"]
    suc = sucesores(d)
    orden = orden_topologico(list(nodos), suc)
    alc = alcanzables(raiz, suc)
    # orden fijo (año, id): el resultado no depende del orden de un conjunto -> reproducible
    resultados = sorted((i for i in alc if nodos[i]["tipo"] != "organizacion"), key=lambda i: (nodos[i]["anio"], i))
    impacto = [i for i in resultados if nodos[i]["tipo"] in TIPOS_IMPACTO or nodos[i].get("resultados")]
    externos = [i for i in resultados if nodos[i]["ambito"] != "academico"]
    despliegues = [i for i in resultados if nodos[i]["tipo"] == "despliegue"]
    activos = [i for i in resultados if nodos[i].get("estado") == "activo"]

    out = {"caso": caso["titulo"], "raiz": raiz, "anio_raiz": anio0, "fecha_corte": caso["fecha_corte"]}

    # --- Estructura y evidencia
    cuenta_tipo = defaultdict(int)
    for n in nodos.values():
        cuenta_tipo[n["tipo"]] += 1
    cuenta_arista = defaultdict(int)
    for a in d["aristas"]:
        cuenta_arista[a["tipo"]] += 1
    ev_n = defaultdict(int); ev_a = defaultdict(int)
    for n in nodos.values():
        ev_n[n["evidencia"]] += 1
    for a in d["aristas"]:
        if a["tipo"] in ARISTAS_DERIVACION:
            ev_a[a["evidencia"]] += 1
    out["estructura"] = {"nodos": len(nodos), "aristas": len(d["aristas"]), "nodos_por_tipo": dict(cuenta_tipo),
                         "aristas_por_tipo": dict(cuenta_arista),
                         "evidencia_nodos": dict(ev_n), "evidencia_aristas_derivacion": dict(ev_a)}

    # --- Perfil
    primer_ext = min((nodos[i]["anio"] for i in externos), default=None)
    primer_desp = min((nodos[i]["anio"] for i in despliegues), default=None)
    ultimo_activo = max((nodos[i].get("activo_en", nodos[i]["anio"]) for i in activos), default=None)
    paises = sorted({p for i in resultados for p in nodos[i].get("paises", [])})
    orgs = sorted({o for i in resultados for o in nodos[i].get("organizaciones", [])})
    ambitos = sorted({nodos[i]["ambito"] for i in resultados})
    prof = camino_mas_largo(raiz, suc, orden, impacto)
    medidos = [(i, r) for i in resultados for r in nodos[i].get("resultados", [])]
    out["perfil"] = {
        "rezago_primer_resultado_no_academico_anios": None if primer_ext is None else primer_ext - anio0,
        "rezago_primera_adopcion_externa_anios": None if primer_desp is None else primer_desp - anio0,
        "persistencia_anios": None if ultimo_activo is None else ultimo_activo - anio0,
        "nodos_activos": [f'{nodos[i]["titulo"]} ({nodos[i].get("activo_en")})' for i in sorted(activos)],
        "alcance_paises": paises, "alcance_organizaciones": orgs, "alcance_ambitos": ambitos,
        "profundidad_eslabones": None if not prof else len(prof[1]),
        "profundidad_camino": None if not prof else [f'{a["desde"]} -[{a["tipo"]}]-> {a["hacia"]}' for a in prof[1]],
        "transferencia_proporcion": round(len(externos) / len(resultados), 2) if resultados else None,
        "transferencia_detalle": f"{len(externos)} de {len(resultados)} resultados fuera de la academia",
        "resultados_medidos": [f'{r["anio"]}: {r["descripcion"]} [{r["evidencia"]}]' for i, r in medidos],
    }

    # --- Evidencia de la cadena hasta cada impacto (eslabón más débil del camino mejor documentado)
    mejor = cadena_mas_documentada(raiz, suc, orden)
    cadenas = []
    for i in sorted(impacto, key=lambda x: (nodos[x]["anio"], x)):
        r, camino = mejor[i]
        debiles = [f'{a["desde"]}->{a["hacia"]}' for a in camino if RANGO[a["evidencia"]] == r]
        cadenas.append({"nodo": i, "titulo": nodos[i]["titulo"], "evidencia_cadena": LETRA[min(r, 3)],
                        "camino": " -> ".join([raiz] + [a["hacia"] for a in camino]),
                        "eslabones_mas_debiles": debiles})
    out["cadenas"] = cadenas

    # --- Eslabones críticos: qué arista, si se documentara con A, mejora más cadenas
    base = {c["nodo"]: RANGO[c["evidencia_cadena"]] for c in cadenas}
    criticos = []
    for a in d["aristas"]:
        if a["tipo"] not in ARISTAS_DERIVACION or a["evidencia"] == "A":
            continue
        m = cadena_mas_documentada(raiz, suc, orden, override={(a["desde"], a["hacia"]): 3})
        mejora = [i for i in base if min(m[i][0], 3) > base[i]]
        if mejora:
            criticos.append({"arista": f'{a["desde"]} -> {a["hacia"]}', "evidencia_actual": a["evidencia"],
                             "cadenas_que_mejoran": len(mejora), "nota": a.get("nota", "")})
    criticos.sort(key=lambda x: -x["cadenas_que_mejoran"])
    out["eslabones_criticos"] = criticos

    # --- Concentración en la cola (hipótesis) + sensibilidad
    share, k = concentracion_cola(resultados, nodos, PESO_TIPO)
    rng = random.Random(SEMILLA); muestras = []
    for _ in range(SENSIBILIDAD_CORRIDAS):
        p = {t: w * rng.uniform(1 - SENSIBILIDAD_RANGO, 1 + SENSIBILIDAD_RANGO) for t, w in PESO_TIPO.items()}
        muestras.append(concentracion_cola(resultados, nodos, p)[0])
    muestras.sort()
    ranking = sorted(resultados, key=lambda i: (-valor_nodo(nodos[i], PESO_TIPO), nodos[i]["anio"], i))
    top = ranking[:k]
    out["cola_hipotesis"] = {
        "fraccion_nodos": FRACCION_COLA, "nodos_en_la_cola": k, "resultados_totales": len(resultados),
        "proporcion_del_valor": round(share, 2),
        "nodos": [nodos[i]["titulo"] for i in top],
        "valores": [{"id": i, "valor": _num(valor_nodo(nodos[i], PESO_TIPO))} for i in ranking],
        "sensibilidad": {"min": round(muestras[0], 2), "mediana": round(muestras[len(muestras) // 2], 2),
                         "max": round(muestras[-1], 2), "corridas": SENSIBILIDAD_CORRIDAS,
                         "rango_pesos": f"x{1 - SENSIBILIDAD_RANGO:.1f} a x{1 + SENSIBILIDAD_RANGO:.1f}"},
        "pesos_declarados": PESO_TIPO, "factor_activo": FACTOR_ACTIVO, "peso_resultado_medido": PESO_RESULTADO_MEDIDO,
    }
    return out


def _num(x):
    x = round(x, 2)
    return int(x) if x == int(x) else x


def anios(x):
    return "sin dato" if x is None else f"{x} año" + ("" if x == 1 else "s")


def informe(o):
    L = []; w = L.append
    w(f'INDICADORES — {o["caso"]}')
    w(f'Raíz: {o["raiz"]} ({o["anio_raiz"]})   ·   Fecha de corte: {o["fecha_corte"]}')
    e = o["estructura"]
    w("\n1. ESTRUCTURA Y EVIDENCIA")
    w(f'   {e["nodos"]} nodos, {e["aristas"]} arista' + ('' if e["aristas"] == 1 else 's'))
    w(f'   Nodos por tipo: ' + ", ".join(f"{k} {v}" for k, v in sorted(e["nodos_por_tipo"].items())))
    w(f'   Aristas por tipo: ' + ", ".join(f"{k} {v}" for k, v in sorted(e["aristas_por_tipo"].items())))
    w(f'   Evidencia de nodos: ' + ", ".join(f"{k} {e['evidencia_nodos'].get(k, 0)}" for k in "ABC"))
    w(f'   Evidencia de aristas de derivación: ' + ", ".join(f"{k} {e['evidencia_aristas_derivacion'].get(k, 0)}" for k in "ABC"))
    p = o["perfil"]
    w("\n2. PERFIL")
    w(f'   Rezago al primer resultado no académico: {anios(p["rezago_primer_resultado_no_academico_anios"])}')
    w(f'   Rezago a la primera adopción externa:     {anios(p["rezago_primera_adopcion_externa_anios"])}')
    w(f'   Persistencia (hasta el último nodo activo): {anios(p["persistencia_anios"])}')
    for x in p["nodos_activos"]:
        w(f'      activo: {x}')
    w(f'   Alcance: {len(p["alcance_paises"])} países ({", ".join(p["alcance_paises"])}), '
      f'{len(p["alcance_organizaciones"])} organizaciones, ámbitos: {", ".join(p["alcance_ambitos"])}')
    if p["profundidad_eslabones"] is None:
        w('   Profundidad: sin impacto fuera de la publicación académica')
    else:
        w(f'   Profundidad: {p["profundidad_eslabones"]} eslabones hasta el impacto más lejano')
    for x in p["profundidad_camino"] or []:
        w(f'      {x}')
    w(f'   Transferencia: {p["transferencia_proporcion"]} ({p["transferencia_detalle"]})')
    w('   Resultados medidos:' + ('' if p["resultados_medidos"] else ' ninguno'))
    for x in p["resultados_medidos"]:
        w(f'      {x}')
    w("\n3. EVIDENCIA DE LA CADENA HASTA CADA IMPACTO (eslabón más débil del camino mejor documentado)")
    if not o["cadenas"]:
        w('   No hay nodos de impacto fuera de la publicación académica.')
    for c in o["cadenas"]:
        w(f'   [{c["evidencia_cadena"]}] {c["titulo"]}')
        w(f'       {c["camino"]}   · más débil: {", ".join(c["eslabones_mas_debiles"])}')
    w("\n4. ESLABONES CRÍTICOS (documentarlos con evidencia A mejora más cadenas)")
    if not o["cadenas"]:
        w("   No aplica.")
    elif not o["eslabones_criticos"]:
        w("   Ninguno: documentar un solo eslabón no mejora ninguna cadena por sí solo.")
    for c in o["eslabones_criticos"]:
        w(f'   {c["arista"]} (hoy {c["evidencia_actual"]}): mejora {c["cadenas_que_mejoran"]} cadena(s). {c["nota"]}')
    t = o["cola_hipotesis"]; s = t["sensibilidad"]
    w("\n5. CONCENTRACIÓN EN LA COLA (hipótesis, con pesos declarados)")
    w(f'   El {int(t["fraccion_nodos"] * 100)}% de nodos de mayor valor ({t["nodos_en_la_cola"]}) concentra el {int(round(t["proporcion_del_valor"] * 100))}% del valor.')
    w(f'   Esos nodos: ' + "; ".join(t["nodos"]))
    if t["resultados_totales"] < 5:
        w(f'   Atención: con {t["resultados_totales"]} resultado(s) este indicador no es significativo.')
    w(f'   Sensibilidad ({s["corridas"]} corridas, pesos {s["rango_pesos"]}): entre {int(round(s["min"] * 100))}% y {int(round(s["max"] * 100))}% (mediana {int(round(s["mediana"] * 100))}%).')
    w(f'   Pesos: ' + ", ".join(f"{k} {v}" for k, v in t["pesos_declarados"].items()) + f'; activo x{t["factor_activo"]}; resultado medido +{t["peso_resultado_medido"]}')
    return "\n".join(L)


def tablero(d, o):
    """Devuelve el tablero HTML autocontenido (sin dependencias ni red)."""
    datos = {"caso": d["caso"], "version": d.get("version", ""), "nodos": d["nodos"],
             "aristas": d["aristas"], "fuentes": d["fuentes"], "ind": o}
    js = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    titulo = "Tablero de impacto — " + d["caso"].get("id", d["caso"]["titulo"])
    t = titulo.replace("&", "&amp;").replace("<", "&lt;")
    return PLANTILLA.replace("__TITULO__", t).replace("__DATA__", js)


# ------------------------------------------------------------------ PLANTILLA DEL TABLERO
PLANTILLA = r'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__TITULO__</title>
<style>
/* Layout: tablero de una columna — resumen arriba, grafo temporal al centro, evidencia y valoración debajo. */
:root{
  --bg:#F4F8FA; --surface:#FFFFFF; --ink:#1F2D3A; --muted:#5B6B77; --faint:#8C9AA5; --line:#DCE6EC; --grid:#EBF1F4;
  --accent:#117AA9; --teal:#66B69F;
  --t-tesis:#D97706; --t-pub:#2563EB; --t-pat:#DC2626; --t-soft:#7C3AED; --t-prod:#16A34A; --t-org:#8C9AA5;
  --ev-a:#1B6A55; --ev-b:#3F9A80; --ev-c:#7DBFA9; --ev-ink:#FFFFFF;
  --hot:#C05621;
  --f-sans:Calibri, Carlito, 'Segoe UI', system-ui, -apple-system, sans-serif;
  --f-disp:'Calibri Light', Calibri, Carlito, 'Segoe UI Light', 'Segoe UI', system-ui, sans-serif;
  color-scheme:light;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#0E171F; --surface:#15202B; --ink:#E7EEF3; --muted:#A3B2BD; --faint:#6F808C; --line:#26343F; --grid:#1D2A35;
  --accent:#4BA3D6; --teal:#7DC8B0;
  --t-tesis:#C97A05; --t-pub:#4A89E6; --t-pat:#E65353; --t-soft:#8F70EA; --t-prod:#22A854; --t-org:#6F808C;
  --ev-a:#9ED9C5; --ev-b:#5FB89D; --ev-c:#2F8A70; --ev-ink:#0E171F;
  --hot:#E07A45; color-scheme:dark; } }
:root[data-theme="dark"]{
  --bg:#0E171F; --surface:#15202B; --ink:#E7EEF3; --muted:#A3B2BD; --faint:#6F808C; --line:#26343F; --grid:#1D2A35;
  --accent:#4BA3D6; --teal:#7DC8B0;
  --t-tesis:#C97A05; --t-pub:#4A89E6; --t-pat:#E65353; --t-soft:#8F70EA; --t-prod:#22A854; --t-org:#6F808C;
  --ev-a:#9ED9C5; --ev-b:#5FB89D; --ev-c:#2F8A70; --ev-ink:#0E171F;
  --hot:#E07A45; color-scheme:dark; }

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--f-sans);font-variant-numeric:tabular-nums}
.wrap{max-width:1180px;margin:0 auto;padding-inline:20px;padding-block:0 48px}
header.top{border-top:6px solid var(--accent);padding-block:26px 18px;display:grid;gap:6px}
.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
h1{font:400 clamp(26px,3.4vw,36px)/1.15 var(--f-disp);margin:0;text-wrap:balance}
.meta{color:var(--muted);font-size:14px;display:flex;flex-wrap:wrap;gap:4px 18px}
h2{font:400 22px/1.2 var(--f-disp);margin:0 0 4px;text-wrap:balance}
.lede{color:var(--muted);margin:0 0 14px;max-width:72ch;font-size:14px}
section{margin-top:34px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:18px}

/* KPI tiles */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:8px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;display:grid;gap:2px;align-content:start;min-width:0}
.kpi .k{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.kpi .v{font:400 34px/1.1 var(--f-disp);color:var(--ink)}
.kpi .v small{font-size:16px;color:var(--muted);margin-left:4px}
.kpi .s{font-size:13px;color:var(--muted)}

/* chips & pills */
.ev{display:inline-flex;align-items:center;justify-content:center;min-width:22px;height:22px;padding:0 6px;border-radius:11px;font-weight:700;font-size:12px;color:var(--ev-ink)}
.ev.A{background:var(--ev-a)} .ev.B{background:var(--ev-b)} .ev.C{background:var(--ev-c)}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--muted);margin-bottom:10px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend svg{flex:0 0 auto}

/* graph */
.graph-box{overflow-x:auto;-webkit-overflow-scrolling:touch}
#graph{display:block;min-width:900px;width:100%;height:auto}
#graph .lane-label{font:700 12px var(--f-sans);letter-spacing:.06em;text-transform:uppercase;fill:var(--muted)}
#graph .yr{font:12px var(--f-sans);fill:var(--muted)}
#graph .gridline{stroke:var(--grid);stroke-width:1}
#graph .brk{stroke:var(--faint);stroke-width:1.5;fill:none}
#graph .lane-bg{fill:var(--bg)}
#graph .edge{fill:none;stroke:var(--faint);stroke-width:1.6}
#graph .edge.B{stroke-dasharray:6 4} #graph .edge.C{stroke-dasharray:1.5 4;stroke-linecap:round}
#graph .edge.ctx{stroke-opacity:.35}
#graph .node{cursor:pointer;outline:none}
#graph .node .mk{stroke:var(--surface);stroke-width:2}
#graph .node .lbl{font:12px var(--f-sans);fill:var(--ink);paint-order:stroke;stroke:var(--bg);stroke-width:4px;stroke-linejoin:round}
#graph .node .mk.ring{stroke:var(--t-org);stroke-width:2.5}
#graph .node:hover .mk,#graph .node:focus .mk,#graph .node.on .mk{stroke:var(--ink)}
#graph .node.dim{opacity:.25} #graph .edge.dim{opacity:.12} #graph .edge.hl{stroke:var(--ink);stroke-width:2.4;opacity:1}
#graph .active-ring{fill:none;stroke:var(--teal);stroke-width:2}
.detail{margin-top:12px;min-height:3.2em;font-size:14px;color:var(--muted);border-top:1px solid var(--line);padding-top:10px}
.detail b{color:var(--ink)}
details.tbl{margin-top:10px;font-size:14px}
details.tbl summary{cursor:pointer;color:var(--accent)}
.scroll-x{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:700;color:var(--muted);font-size:12px;letter-spacing:.05em;text-transform:uppercase}
td.path{color:var(--muted)}

/* two columns */
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:860px){.cols{grid-template-columns:1fr}}
.cols>*{min-width:0}

/* evidence bars */
.stack{display:grid;grid-template-columns:130px 1fr;gap:10px 12px;align-items:center;font-size:14px}
.bar{display:flex;gap:2px;height:26px;border-radius:5px;overflow:hidden}
.bar div{display:flex;align-items:center;justify-content:center;color:var(--ev-ink);font-weight:700;font-size:12px;min-width:0}
.crit{display:grid;gap:10px;margin:0;padding:0;list-style:none}
.crit li{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;align-items:start}
.crit .n{font:400 26px/1 var(--f-disp);color:var(--accent);grid-row:span 2}
.crit .a{font-weight:700}
.crit .t{color:var(--muted);font-size:13px}

/* tail chart */
#tail{display:block;width:100%;height:auto}
#tail .nm{font:12px var(--f-sans);fill:var(--ink)} #tail .val{font:12px var(--f-sans);fill:var(--muted)}
#tail .b{fill:var(--line)} #tail .b.top{fill:var(--accent)}
#tail .axis{stroke:var(--line)}
.sens{margin-top:14px;font-size:14px;color:var(--muted)}
#sens{display:block;width:100%;height:auto;margin-top:6px}
#sens .track{fill:var(--grid)} #sens .band{fill:var(--teal);fill-opacity:.45} #sens .pt{fill:var(--accent);stroke:var(--surface);stroke-width:2}
#sens .med{stroke:var(--ink);stroke-width:2} #sens text{font:12px var(--f-sans);fill:var(--muted)}
.results{display:grid;gap:10px;margin:0;padding:0;list-style:none}
.results li{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:start}
.results .y{font:400 22px/1 var(--f-disp);color:var(--hot);min-width:3.2em}
.method{font-size:14px;color:var(--muted);display:grid;gap:8px;max-width:90ch}
.method b{color:var(--ink)}
.tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:13px;max-width:320px;box-shadow:0 6px 18px rgba(0,0,0,.14);z-index:10}
footer{margin-top:40px;font-size:12px;color:var(--faint)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="eyebrow">Árbol de impacto · instrumento v0</div>
    <h1 id="h1"></h1>
    <div class="meta" id="meta"></div>
  </header>

  <section aria-labelledby="s-perfil">
    <h2 id="s-perfil">Perfil</h2>
    <p class="lede">Indicadores descriptivos que salen del grafo. No se agregan en un número único.</p>
    <div class="kpis" id="kpis"></div>
  </section>

  <section aria-labelledby="s-grafo">
    <h2 id="s-grafo">La trayectoria</h2>
    <p class="lede">Cada resultado en su año y su ámbito (los tramos sin resultados se acortan: ⫽). Las líneas son derivaciones: su trazo indica la evidencia. Pasá el cursor o tocá un nodo para ver su detalle y resaltar su cadena desde la tesis.</p>
    <div class="panel">
      <div class="legend" id="legend"></div>
      <div class="graph-box"><svg id="graph" role="img" aria-label="Grafo temporal de la trayectoria de impacto"></svg></div>
      <div class="detail" id="detail" aria-live="polite">Seleccioná un nodo.</div>
      <details class="tbl"><summary>Ver los nodos como tabla</summary><div class="scroll-x"><table id="nodetable"></table></div></details>
    </div>
  </section>

  <section aria-labelledby="s-ev">
    <h2 id="s-ev">Evidencia</h2>
    <p class="lede">A: un documento público lo afirma explícitamente. B: se infiere de documentos públicos. C: solo testimonio del autor.</p>
    <div class="cols">
      <div class="panel">
        <div class="stack" id="evbars"></div>
        <h3 style="font:400 17px/1.2 var(--f-disp);margin:22px 0 10px">Eslabones críticos</h3>
        <p class="lede" style="margin-bottom:10px">Documentarlos con evidencia A mejora más cadenas.</p>
        <ul class="crit" id="crit"></ul>
      </div>
      <div class="panel">
        <h3 style="font:400 17px/1.2 var(--f-disp);margin:0 0 10px">Resultados medidos</h3>
        <ul class="results" id="results"></ul>
      </div>
    </div>
    <div class="panel" style="margin-top:16px">
      <h3 style="font:400 17px/1.2 var(--f-disp);margin:0 0 4px">Cadena mejor documentada hasta cada impacto</h3>
      <p class="lede" style="margin-bottom:8px">La evidencia de una cadena es la de su eslabón más débil.</p>
      <div class="scroll-x"><table id="chains"></table></div>
    </div>
  </section>

  <section aria-labelledby="s-cola">
    <h2 id="s-cola">Concentración en la cola</h2>
    <p class="lede">Hipótesis de valoración con pesos declarados. Muestra cuánto del valor se concentra en los pocos resultados de mayor impacto, y cuánto cambia si los pesos se mueven.</p>
    <div class="cols">
      <div class="panel"><svg id="tail" role="img" aria-label="Valor de cada resultado, ordenado"></svg></div>
      <div class="panel">
        <div id="tailsum"></div>
        <div class="sens" id="senstxt"></div>
        <svg id="sens" role="img" aria-label="Rango de sensibilidad"></svg>
        <div class="sens" id="pesos"></div>
      </div>
    </div>
  </section>

  <section aria-labelledby="s-met">
    <h2 id="s-met">Método</h2>
    <div class="method" id="method"></div>
  </section>
  <footer id="foot"></footer>
</div>
<div class="tip" id="tip" hidden></div>

<script type="application/json" id="data">__DATA__</script>
<script>
(function(){
const D = JSON.parse(document.getElementById('data').textContent);
const O = D.ind, N = {}, NS = 'http://www.w3.org/2000/svg';
D.nodos.forEach(n => N[n.id] = n);
const F = {}; D.fuentes.forEach(f => F[f.id] = f);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const lab = id => N[id].etiqueta || N[id].titulo;
const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
const plural = (n, s, p) => n + ' ' + (n === 1 ? s : p);

// ---- header
document.getElementById('h1').textContent = D.caso.titulo;
document.getElementById('meta').innerHTML =
  `<span>${esc(D.caso.autor)}</span><span>Tesis: ${esc(N[D.caso.raiz].titulo)} (${N[D.caso.raiz].anio})</span><span>Fecha de corte: ${esc(D.caso.fecha_corte)}</span>`;

// ---- KPIs
const P = O.perfil, ca = O.cadenas;
const evCount = {A:0,B:0,C:0}; ca.forEach(c => evCount[c.evidencia_cadena]++);
const kpis = [
  ['Primera adopción externa', P.rezago_primera_adopcion_externa_anios, 'años', 'Primer resultado no académico: ' + (P.rezago_primer_resultado_no_academico_anios ?? 'sin dato') + (P.rezago_primer_resultado_no_academico_anios === 1 ? ' año' : ' años')],
  ['Persistencia', P.persistencia_anios, 'años', P.nodos_activos.length ? plural(P.nodos_activos.length, 'nodo activo', 'nodos activos') + ' hoy' : 'sin nodos activos'],
  ['Alcance', P.alcance_paises.length, P.alcance_paises.length === 1 ? 'país' : 'países', plural(P.alcance_organizaciones.length, 'organización', 'organizaciones') + ' · ' + P.alcance_ambitos.length + ' ámbitos'],
  ['Profundidad', P.profundidad_eslabones, 'eslabones', 'De la tesis al impacto más lejano'],
  ['Transferencia', P.transferencia_proporcion == null ? null : Math.round(P.transferencia_proporcion * 100), '%', P.transferencia_detalle],
  ['Cadenas documentadas', ca.length, ca.length === 1 ? 'impacto' : 'impactos', ['A','B','C'].filter(k => evCount[k]).map(k => evCount[k] + ' en ' + k).join(' · ') || 'sin impactos'],
];
document.getElementById('kpis').innerHTML = kpis.map(([k, v, u, s]) =>
  `<div class="kpi"><div class="k">${esc(k)}</div><div class="v">${v == null ? '—' : v}<small>${v == null ? '' : esc(u)}</small></div><div class="s">${esc(s)}</div></div>`).join('');

// ---- graph
const TYPE = {
  tesis:{c:'var(--t-tesis)', s:'big', n:'Tesis'}, publicacion:{c:'var(--t-pub)', s:'circle', n:'Publicación'},
  patente:{c:'var(--t-pat)', s:'diamond', n:'Patente'}, software:{c:'var(--t-soft)', s:'square', n:'Software'},
  producto:{c:'var(--t-prod)', s:'square', n:'Producto'}, despliegue:{c:'var(--t-prod)', s:'triangle', n:'Despliegue'},
  empresa:{c:'var(--t-prod)', s:'triangle', n:'Empresa'}, politica:{c:'var(--t-soft)', s:'triangle', n:'Política'},
  formacion:{c:'var(--t-pub)', s:'diamond', n:'Formación'}, organizacion:{c:'var(--t-org)', s:'ring', n:'Organización'}};
function shape(g, t, x, y, r){
  const T = TYPE[t] || TYPE.publicacion, fill = T.c;
  if (T.s === 'big') return el('circle', {cx:x, cy:y, r:r+4, fill, class:'mk'}, g);
  if (T.s === 'circle') return el('circle', {cx:x, cy:y, r, fill, class:'mk'}, g);
  if (T.s === 'ring') return el('circle', {cx:x, cy:y, r:r-1, fill:'var(--surface)', stroke:fill, 'stroke-width':2.5, class:'mk ring'}, g);
  if (T.s === 'square') return el('rect', {x:x-r+1, y:y-r+1, width:2*r-2, height:2*r-2, rx:2, fill, class:'mk'}, g);
  if (T.s === 'diamond') return el('path', {d:`M${x} ${y-r-1}L${x+r+1} ${y}L${x} ${y+r+1}L${x-r-1} ${y}Z`, fill, class:'mk'}, g);
  return el('path', {d:`M${x} ${y-r-1}L${x+r+1} ${y+r}L${x-r-1} ${y+r}Z`, fill, class:'mk'}, g);
}
// legend (identity never by color alone: shape + label)
const usedTypes = [...new Set(D.nodos.map(n => n.tipo))];
const lg = document.getElementById('legend');
usedTypes.forEach(t => { const s = document.createElement('span'); const sv = document.createElementNS(NS,'svg'); sv.setAttribute('width',18); sv.setAttribute('height',18); shape(sv, t, 9, 9, 6); s.appendChild(sv); s.appendChild(document.createTextNode(TYPE[t] ? TYPE[t].n : t)); lg.appendChild(s); });
[['A','solid'],['B','6 4'],['C','1.5 4']].forEach(([g, da]) => { const s = document.createElement('span'); s.innerHTML = `<svg width="30" height="10"><line x1="1" y1="5" x2="29" y2="5" stroke="currentColor" stroke-width="1.8" ${da==='solid'?'':`stroke-dasharray="${da}"`} stroke-linecap="round"/></svg>Evidencia ${g}`; lg.appendChild(s); });
{ const s = document.createElement('span'); s.innerHTML = `<svg width="18" height="18"><circle cx="9" cy="9" r="7" fill="none" stroke="var(--teal)" stroke-width="2"/></svg>Activo hoy`; lg.appendChild(s); }

const svg = document.getElementById('graph');
const lanes = ['academico','industria','gobierno'].filter(a => D.nodos.some(n => n.ambito === a));
const laneName = {academico:'Academia', industria:'Industria', gobierno:'Gobierno'};
const years = D.nodos.map(n => n.anio); const y0 = Math.min(...years) - 1, y1 = Math.max(...years) + 1;
const W = 1140, padL = 96, padR = 70, top = 16, subH = 40, laneGap = 10;
// Compressed time axis: each year with nodes gets room; empty stretches longer than 3 years are shortened (marked with a break).
const uy = [...new Set(years)].sort((a, b) => a - b), GAPMAX = 3;
const cum = {}; let acc = 0; cum[uy[0]] = 0;
for (let i = 1; i < uy.length; i++) { acc += Math.min(uy[i] - uy[i-1], GAPMAX); cum[uy[i]] = acc; }
const span = Math.max(acc, 1) + 2;
const X = y => { let u; if (cum[y] != null) u = cum[y]; else { const i = uy.findIndex(v => v > y); if (i <= 0) u = y < uy[0] ? -1 : acc + 1; else { const a = uy[i-1], b = uy[i]; u = cum[a] + (y - a) / (b - a) * (cum[b] - cum[a]); } }
  return padL + (u + 1) / span * (W - padL - padR); };
const breaks = []; for (let i = 1; i < uy.length; i++) if (uy[i] - uy[i-1] > GAPMAX) breaks.push((X(uy[i-1]) + X(uy[i])) / 2);
// place nodes in sub-rows so labels never overlap
const place = {}; const laneRows = {};
lanes.forEach(a => {
  const ns = D.nodos.filter(n => n.ambito === a).sort((p, q) => p.anio - q.anio || p.id.localeCompare(q.id));
  const rowsEnd = [];
  ns.forEach(n => {
    const x = X(n.anio), w = 26 + lab(n.id).length * 6.6;
    let r = rowsEnd.findIndex(e => e < x - 14);
    if (r === -1) { r = rowsEnd.length; rowsEnd.push(0); }
    rowsEnd[r] = x + w; place[n.id] = {x, row:r};
  });
  laneRows[a] = Math.max(1, rowsEnd.length);
});
let yCur = top; const laneY = {};
lanes.forEach(a => { laneY[a] = yCur; yCur += laneRows[a] * subH + 18 + laneGap; });
const H = yCur + 26;
svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
// lanes and grid
lanes.forEach(a => { const h = laneRows[a] * subH + 18; el('rect', {x:0, y:laneY[a], width:W, height:h, rx:6, class:'lane-bg'}, svg);
  const t = el('text', {x:10, y:laneY[a] + 20, class:'lane-label'}, svg); t.textContent = laneName[a]; });
// ticks at the years that have nodes, thinned so labels never collide
let lastX = -1e9; uy.forEach(y => { const x = X(y); el('line', {x1:x, y1:top, x2:x, y2:H - 22, class:'gridline'}, svg);
  if (x - lastX >= 34) { const t = el('text', {x, y:H - 6, 'text-anchor':'middle', class:'yr'}, svg); t.textContent = y; lastX = x; } });
breaks.forEach(x => { el('path', {d:`M${x-7} ${H-13}l6 -10M${x+1} ${H-13}l6 -10`, class:'brk'}, svg); });
Object.keys(place).forEach(id => { const n = N[id]; place[id].y = laneY[n.ambito] + 26 + place[id].row * subH; });
// edges
const edgeEls = [];
D.aristas.forEach(a => {
  const p = place[a.desde], q = place[a.hacia]; if (!p || !q) return;
  const dx = Math.max(30, Math.abs(q.x - p.x) * 0.5);
  const d = `M${p.x} ${p.y} C${p.x + dx} ${p.y}, ${q.x - dx} ${q.y}, ${q.x} ${q.y}`;
  const e = el('path', {d, class:`edge ${a.evidencia}${a.tipo === 'contexto' ? ' ctx' : ''}`}, svg);
  e.appendChild(el('title', {})).textContent = `${lab(a.desde)} → ${lab(a.hacia)} · ${a.tipo.replace('_',' ')} · evidencia ${a.evidencia}`;
  edgeEls.push({a, e});
});
// nodes
const nodeEls = {};
D.nodos.forEach(n => {
  const {x, y} = place[n.id];
  const g = el('g', {class:'node', tabindex:0, role:'button', 'aria-label':`${n.titulo}, ${n.anio}`}, svg);
  if (n.estado === 'activo') el('circle', {cx:x, cy:y, r:13, class:'active-ring'}, g);
  shape(g, n.tipo, x, y, 7);
  const t = el('text', {x:x + 12, y:y + 4, class:'lbl'}, g); t.textContent = lab(n.id);
  nodeEls[n.id] = g;
  const show = ev => select(n.id, ev);
  g.addEventListener('mouseenter', show); g.addEventListener('focus', show); g.addEventListener('click', show);
  g.addEventListener('mouseleave', hideTip);
});
// chain highlighting: best-documented path from the root (from the indicators)
const chainOf = {}; ca.forEach(c => chainOf[c.nodo] = c.camino.split(' -> '));
function select(id, ev){
  const n = N[id];
  const path = chainOf[id] || null;
  const onPath = new Set(path || [id]);
  Object.entries(nodeEls).forEach(([k, g]) => { g.classList.toggle('dim', !!path && !onPath.has(k)); g.classList.toggle('on', k === id); });
  edgeEls.forEach(({a, e}) => { const inPath = path && path.indexOf(a.desde) >= 0 && path.indexOf(a.hacia) === path.indexOf(a.desde) + 1;
    e.classList.toggle('hl', !!inPath); e.classList.toggle('dim', !!path && !inPath); });
  const fu = (n.fuentes || []).map(f => F[f] ? F[f].cita : f);
  const res = (n.resultados || []).map(r => `${r.anio}: ${esc(r.descripcion)} <span class="ev ${r.evidencia}">${r.evidencia}</span>`).join('<br>');
  const ch = chainOf[id] ? ` · cadena desde la tesis: <span class="ev ${ca.find(c => c.nodo === id).evidencia_cadena}">${ca.find(c => c.nodo === id).evidencia_cadena}</span> (${chainOf[id].map(lab).map(esc).join(' → ')})` : '';
  document.getElementById('detail').innerHTML =
    `<b>${esc(n.titulo)}</b> · ${n.anio}${n.anio_nota ? ' (' + esc(n.anio_nota) + ')' : ''} · ${TYPE[n.tipo] ? TYPE[n.tipo].n : n.tipo} · ${laneName[n.ambito]} · evidencia <span class="ev ${n.evidencia}">${n.evidencia}</span>${ch}` +
    (res ? `<br>${res}` : '') + (n.nota ? `<br>${esc(n.nota)}` : '') + (fu.length ? `<br><span style="font-size:13px">Fuentes: ${fu.map(esc).join(' · ')}</span>` : '');
  if (ev && ev.type === 'mouseenter') showTip(ev, `<b>${esc(n.titulo)}</b><br>${n.anio} · evidencia ${n.evidencia}`);
}
const tip = document.getElementById('tip');
function showTip(ev, html){ tip.innerHTML = html; tip.hidden = false; const r = ev.target.getBoundingClientRect(); tip.style.left = Math.max(8, r.right + 338 > window.innerWidth ? r.left - tip.offsetWidth - 8 : r.right + 8) + 'px'; tip.style.top = (r.top - 8) + 'px'; }
function hideTip(){ tip.hidden = true; }
// node table (accessible view)
document.getElementById('nodetable').innerHTML = '<tr><th>Año</th><th>Nodo</th><th>Tipo</th><th>Ámbito</th><th>Estado</th><th>Evidencia</th></tr>' +
  D.nodos.slice().sort((p, q) => p.anio - q.anio).map(n => `<tr><td>${n.anio}</td><td>${esc(n.titulo)}</td><td>${TYPE[n.tipo] ? TYPE[n.tipo].n : n.tipo}</td><td>${laneName[n.ambito]}</td><td>${n.estado}</td><td><span class="ev ${n.evidencia}">${n.evidencia}</span></td></tr>`).join('');

// ---- evidence bars
const E = O.estructura;
const bar = (label, cnt) => { const tot = ['A','B','C'].reduce((s, k) => s + (cnt[k] || 0), 0) || 1;
  return `<div>${label}</div><div class="bar" role="img" aria-label="${label}: A ${cnt.A||0}, B ${cnt.B||0}, C ${cnt.C||0}">` +
    ['A','B','C'].filter(k => cnt[k]).map(k => `<div class="ev ${k}" style="flex:${cnt[k]} 1 0;border-radius:0;height:100%" title="${k}: ${cnt[k]}">${k} ${cnt[k]}</div>`).join('') + '</div>'; };
document.getElementById('evbars').innerHTML = bar('Nodos', E.evidencia_nodos) + bar('Derivaciones', E.evidencia_aristas_derivacion);
const cr = O.eslabones_criticos;
document.getElementById('crit').innerHTML = cr.length ? cr.map(c => { const [a, b] = c.arista.split(' -> ');
  return `<li><span class="n">${c.cadenas_que_mejoran}</span><span class="a">${esc(lab(a))} → ${esc(lab(b))} <span class="ev ${c.evidencia_actual}">${c.evidencia_actual}</span></span><span class="t">${c.cadenas_que_mejoran === 1 ? 'cadena mejora' : 'cadenas mejoran'} si se documenta con A. ${esc(c.nota || '')}</span></li>`; }).join('')
  : `<li><span class="t">${ca.length ? 'Ningún eslabón mejora una cadena por sí solo.' : 'No aplica: no hay impactos fuera de la publicación académica.'}</span></li>`;
const RM = D.nodos.flatMap(n => (n.resultados || []).map(r => ({n, r}))).sort((p, q) => p.r.anio - q.r.anio);
document.getElementById('results').innerHTML = RM.length ? RM.map(({n, r}) => `<li><span class="y">${r.anio}</span><span>${esc(r.descripcion)} <span class="ev ${r.evidencia}">${r.evidencia}</span><br><span style="color:var(--muted);font-size:13px">${esc(lab(n.id))} · ${(r.fuentes||[]).map(f => F[f] ? esc(F[f].cita.split('.')[0]) : f).join(' · ')}</span></span></li>`).join('')
  : '<li><span></span><span style="color:var(--muted)">Ninguno registrado.</span></li>';
document.getElementById('chains').innerHTML = '<tr><th>Impacto</th><th>Año</th><th>Evidencia</th><th>Camino desde la tesis</th><th>Eslabón más débil</th></tr>' +
  (ca.length ? ca.map(c => `<tr><td>${esc(lab(c.nodo))}</td><td>${N[c.nodo].anio}</td><td><span class="ev ${c.evidencia_cadena}">${c.evidencia_cadena}</span></td><td class="path">${c.camino.split(' -> ').map(lab).map(esc).join(' → ')}</td><td>${c.eslabones_mas_debiles.map(x => x.split('->').map(lab).map(esc).join(' → ')).join('<br>')}</td></tr>`).join('')
  : '<tr><td colspan="5" style="color:var(--muted)">No hay impactos fuera de la publicación académica.</td></tr>');

// ---- tail chart (horizontal bars, ranked)
const T = O.cola_hipotesis;
const vals = (T.valores || []).slice();
const tsvg = document.getElementById('tail');
const rowH = 22, lw = 110, tw = 520, th = vals.length * rowH + 30, maxV = Math.max(...vals.map(v => v.valor), 1);
tsvg.setAttribute('viewBox', `0 0 ${tw} ${th}`);
const XV = v => lw + v / maxV * (tw - lw - 44);
vals.forEach((v, i) => { const y = 6 + i * rowH;
  const nm = el('text', {x:lw - 8, y:y + 14, 'text-anchor':'end', class:'nm'}, tsvg); nm.textContent = lab(v.id);
  const w = Math.max(2, XV(v.valor) - lw);
  const b = el('path', {d:`M${lw} ${y+3}h${w-4}q4 0 4 4v6q0 4 -4 4h${-(w-4)}Z`, class:'b' + (i < T.nodos_en_la_cola ? ' top' : '')}, tsvg);
  b.appendChild(el('title', {})).textContent = `${lab(v.id)}: valor ${v.valor}`;
  if (i < T.nodos_en_la_cola) { const t = el('text', {x:lw + w + 6, y:y + 14, class:'val'}, tsvg); t.textContent = v.valor; }
});
el('line', {x1:lw, y1:2, x2:lw, y2:th - 22, class:'axis'}, tsvg);
const pct = x => Math.round(x * 100) + '%';
document.getElementById('tailsum').innerHTML = `<div class="kpi" style="border:0;padding:0"><div class="k">El ${pct(T.fraccion_nodos)} de mayor valor</div><div class="v">${pct(T.proporcion_del_valor)}<small>del valor</small></div><div class="s">${plural(T.nodos_en_la_cola, 'resultado', 'resultados')} de ${T.resultados_totales}: ${T.nodos.map(esc).join(' · ')}</div></div>` +
  (T.resultados_totales < 5 ? `<p class="sens">Con ${T.resultados_totales} resultado(s) este indicador no es significativo.</p>` : '');
const S = T.sensibilidad;
document.getElementById('senstxt').innerHTML = `Si cada peso se mueve entre ${S.rango_pesos.replace('x','×').replace('x','×')} (${S.corridas} corridas), la concentración queda entre <b style="color:var(--ink)">${pct(S.min)}</b> y <b style="color:var(--ink)">${pct(S.max)}</b>; mediana ${pct(S.mediana)}.`;
const ss = document.getElementById('sens'), sw = 520, sh = 58, SX = v => 10 + v * (sw - 20);
ss.setAttribute('viewBox', `0 0 ${sw} ${sh}`);
el('rect', {x:SX(0), y:14, width:SX(1) - SX(0), height:12, rx:6, class:'track'}, ss);
el('rect', {x:SX(S.min), y:14, width:Math.max(3, SX(S.max) - SX(S.min)), height:12, rx:6, class:'band'}, ss);
el('line', {x1:SX(S.mediana), y1:10, x2:SX(S.mediana), y2:30, class:'med'}, ss);
el('circle', {cx:SX(T.proporcion_del_valor), cy:20, r:7, class:'pt'}, ss);
[0, .25, .5, .75, 1].forEach(v => { const t = el('text', {x:SX(v), y:50, 'text-anchor':v === 0 ? 'start' : v === 1 ? 'end' : 'middle'}, ss); t.textContent = pct(v); });
document.getElementById('pesos').innerHTML = 'Pesos declarados: ' + Object.entries(T.pesos_declarados).map(([k, v]) => `${esc(k)} ${v}`).join(' · ') + ` · activo ×${T.factor_activo} · resultado medido +${T.peso_resultado_medido}. El punto es el valor con estos pesos; la franja, el rango con pesos perturbados; la línea, la mediana.`;

// ---- method
document.getElementById('method').innerHTML = [
  '<div><b>Qué es.</b> Un árbol de impacto representa la trayectoria de una tesis como un grafo dirigido: resultados con tipo y fecha, y derivaciones con tipo, fuente y grado de evidencia.</div>',
  '<div><b>Tipos de derivación.</b> precursor · derivación conceptual · ingeniería · comercialización · despliegue · documentación · formación. Las aristas de contexto (dónde o con quién ocurrió algo) se dibujan tenues y no cuentan como derivación.</div>',
  '<div><b>Evidencia de una cadena.</b> Entre todos los caminos desde la tesis, el que tiene el eslabón más débil mejor documentado; la cadena vale lo que ese eslabón.</div>',
  '<div><b>Concentración en la cola.</b> Es una hipótesis de valoración, no un índice validado: sus pesos son decisiones declaradas y el tablero muestra su sensibilidad.</div>',
  `<div><b>Estado del caso.</b> ${esc((D.caso.construccion && D.caso.construccion.verificado_por) || 'Sin datos de verificación')}.</div>`
].join('');
document.getElementById('foot').textContent = `Generado por indicadores.py (esquema ${D.version}) · ${D.nodos.length} nodos · ${D.aristas.length} aristas · ${D.fuentes.length} fuentes`;
})();
</script>
</body>
</html>
'''



if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    d, nodos = cargar(sys.argv[1])
    o = calcular(d, nodos)
    if "--html" in sys.argv:
        i = sys.argv.index("--html")
        if i + 1 >= len(sys.argv):
            sys.exit("Falta el archivo de salida: --html tablero.html")
        with open(sys.argv[i + 1], "w", encoding="utf-8") as f:
            f.write(tablero(d, o))
        print(f"Tablero escrito en {sys.argv[i + 1]}")
    else:
        print(json.dumps(o, ensure_ascii=False, indent=2) if "--json" in sys.argv else informe(o))
