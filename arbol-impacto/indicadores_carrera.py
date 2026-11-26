# -*- coding: utf-8 -*-
"""Indicadores del grafo de la carrera (el impacto del doctor).

Uso: python3 indicadores_carrera.py carrera-grafo-v0.json [--json]
Son conteos y cadenas, sin pesos: este grafo no entra en la curva ABC de la tesis.
"""
import json, sys
from collections import Counter, defaultdict

RANGO = {"A": 3, "B": 2, "C": 1}
LETRA = {3: "A", 2: "B", 1: "C"}
GRUPO = {"laboratorio": "estructuras", "centro": "estructuras", "formacion": "formacion",
         "politica": "planes", "transferencia": "transferencias", "empresa": "empresas",
         "publicacion": "estudios de terceros"}

def calcular(d):
    nodos = {n["id"]: n for n in d["nodos"]}
    raiz = d["caso"]["raiz"]
    corte = int(d["caso"]["fecha_corte"][:4])
    suc = defaultdict(list)
    for a in d["aristas"]:
        suc[a["desde"]].append(a)
    # alcanzables
    vistos, pila = set(), [raiz]
    while pila:
        u = pila.pop()
        for a in suc[u]:
            if a["hacia"] not in vistos:
                vistos.add(a["hacia"]); pila.append(a["hacia"])
    res = [nodos[i] for i in vistos if nodos[i]["tipo"] != "organizacion"]
    # camino más largo y su evidencia (eslabón más débil)
    memo = {}
    def largo(u):
        if u in memo: return memo[u]
        mejor = (0, 3, [u])
        for a in suc[u]:
            l, ev, cam = largo(a["hacia"])
            cand = (l + 1, min(ev, RANGO[a["evidencia"]]), [u] + cam)
            if (cand[0], cand[1]) > (mejor[0], mejor[1]): mejor = cand
        memo[u] = mejor
        return mejor
    l, ev, cam = largo(raiz)
    premios = [(n["id"], r) for n in res for r in n.get("resultados", []) if "Premio" in r["descripcion"]]
    social = [(n["id"], n["impacto_social"]) for n in res if "impacto_social" in n]
    activos = [n for n in res if n["estado"] == "activo"]
    activos_A = [n for n in activos if n["evidencia"] == "A"]
    paises = sorted({p for n in res for p in n.get("paises", [])})
    ult = max((n.get("activo_en", n["anio"]) for n in activos_A), default=None)
    o = dict(
        resultados=len(res),
        por_grupo=dict(Counter(GRUPO.get(n["tipo"], n["tipo"]) for n in res)),
        evidencia_nodos=dict(sorted(Counter(n["evidencia"] for n in res).items())),
        evidencia_aristas=dict(sorted(Counter(a["evidencia"] for a in d["aristas"]).items())),
        capacidad=dict(sorted(Counter(a["evidencia"] for a in d["aristas"] if a["tipo"] == "capacidad").items())),
        reconocimientos=[dict(nodo=i, descripcion=r["descripcion"], anio=r["anio"], evidencia=r["evidencia"]) for i, r in premios],
        impacto_social=[dict(nodo=i, descripcion=s["descripcion"], evidencia=s["evidencia"], nivel=s.get("nivel")) for i, s in social],
        niveles_social={k: sum(1 for _, s in social if s.get('nivel') == k) for k in ('declarado', 'documentado', 'evaluado', 'medido')},
        ambitos=sorted({n["ambito"] for n in res}),
        paises=paises,
        activos=[n["id"] for n in activos],
        persistencia_A=(ult - d["nodos"][0]["anio"]) if ult else None,
        persistencia_A_nodo=[n["id"] for n in activos_A],
        cadena_mas_larga=dict(largo=l, evidencia=LETRA[ev], camino=cam),
        organizaciones=sorted({o for n in res for o in n.get("organizaciones", [])}),
        fecha_corte=d["caso"]["fecha_corte"],
    )
    return o

def informe(o):
    L = []
    L.append("Grafo de la carrera — indicadores (corte %s)" % o["fecha_corte"])
    L.append("Resultados: %d  %s" % (o["resultados"], o["por_grupo"]))
    L.append("Evidencia de nodos: %s · de aristas: %s · aristas 'capacidad': %s" % (o["evidencia_nodos"], o["evidencia_aristas"], o["capacidad"]))
    L.append("Reconocimientos externos: %d" % len(o["reconocimientos"]))
    for r in o["reconocimientos"]:
        L.append("  [%s] %s (%s)" % (r["evidencia"], r["descripcion"], r["anio"]))
    L.append("Impactos sociales marcados: %d  niveles: %s" % (len(o["impacto_social"]), o["niveles_social"]))
    for s in o["impacto_social"]:
        L.append("  [%s · %s] %s: %s" % (s["evidencia"], s["nivel"], s["nodo"], s["descripcion"]))
    L.append("Ámbitos: %s · Países: %s · Organizaciones: %d" % (", ".join(o["ambitos"]), ", ".join(o["paises"]), len(o["organizaciones"])))
    L.append("Activos hoy: %s · Persistencia con evidencia A: %s años (%s)" % (", ".join(o["activos"]), o["persistencia_A"], ", ".join(o["persistencia_A_nodo"])))
    c = o["cadena_mas_larga"]
    L.append("Cadena más larga: %d eslabones, evidencia %s: %s" % (c["largo"], c["evidencia"], " → ".join(c["camino"])))
    return "\n".join(L)

if __name__ == "__main__":
    d = json.load(open(sys.argv[1]))
    o = calcular(d)
    print(json.dumps(o, ensure_ascii=False, indent=1) if "--json" in sys.argv else informe(o))
