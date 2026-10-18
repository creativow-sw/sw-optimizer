"""Motor de calculo del optimizador de Summoners War.
Solo usa datos de TU cuenta (el JSON de SWEX) y el archivo meta_rules.json.
"""
import copy
import itertools
from collections import Counter

NOMBRE_STAT = {
    1: "HP", 2: "HP%", 3: "ATK", 4: "ATK%", 5: "DEF", 6: "DEF%",
    8: "SPD", 9: "CR", 10: "CD", 11: "RES", 12: "ACC",
}
# Valor maximo que puede dar una mejora de cada stat (runa de 6 estrellas)
MAX_MEJORA = {
    1: 375, 2: 8, 3: 20, 4: 8, 5: 20, 6: 8,
    8: 6, 9: 6, 10: 7, 11: 8, 12: 8,
}
NOMBRE_SET = {
    1: "Energy", 2: "Guard", 3: "Swift", 4: "Blade", 5: "Rage",
    6: "Focus", 7: "Endure", 8: "Fatal", 10: "Despair", 11: "Vampire",
    13: "Violent", 14: "Nemesis", 15: "Will", 16: "Shield", 17: "Revenge",
    18: "Destroy", 19: "Fight", 20: "Determination", 21: "Enhance",
    22: "Accuracy", 23: "Tolerance", 99: "Immemorial",
}
ELEMENTOS = {1: "Water", 2: "Fire", 3: "Wind", 4: "Light", 5: "Dark"}
# Bonos de set que suben stats del propio monstruo: (piezas, stat, valor)
BONO_SET = {
    1: (2, "HP%", 15), 2: (2, "DEF%", 15), 3: (4, "SPD%", 25),
    4: (2, "CR", 12), 5: (4, "CD", 40), 6: (2, "ACC", 20),
    7: (2, "RES", 20), 8: (4, "ATK%", 35),
}
ORDEN_TIER = ["S+", "S", "A", "B", "C", "D"]


# ---------------------------------------------------------------- runas
def _molienda(s):
    return s[3] if len(s) > 3 else 0


def suma_mejoras(r):
    """Suma (valor / maximo de una mejora) de innato + sub-stats, con molienda."""
    total = 0.0
    innato = r.get("prefix_eff") or [0, 0]
    if innato and innato[0] in MAX_MEJORA:
        total += innato[1] / MAX_MEJORA[innato[0]]
    for s in r.get("sec_eff") or []:
        if s[0] in MAX_MEJORA:
            total += (s[1] + _molienda(s)) / MAX_MEJORA[s[0]]
    return total


def eficiencia(r):
    return round((1 + suma_mejoras(r) * 0.2) / 2.8 * 100)


def eficiencia_max(r):
    """Eficiencia en el mejor caso: cada mejora que falta sale al maximo."""
    nivel = r.get("upgrade_curr", 0)
    faltan = len([n for n in (3, 6, 9, 12) if nivel < n])
    return round((1 + suma_mejoras(r) * 0.2 + faltan * 0.2) / 2.8 * 100)


def valor_stat(r, stat_id):
    total = 0
    innato = r.get("prefix_eff") or [0, 0]
    if innato and innato[0] == stat_id:
        total += innato[1]
    for s in r.get("sec_eff") or []:
        if s[0] == stat_id:
            total += s[1] + _molienda(s)
    return total


def texto_stat(par):
    if not par or par[0] not in NOMBRE_STAT:
        return ""
    return NOMBRE_STAT[par[0]] + "+" + str(par[1])


def texto_runa(r):
    pri = r.get("pri_eff") or [0, 0]
    innato = r.get("prefix_eff") or [0, 0]
    subs = [texto_stat([s[0], s[1] + _molienda(s)]) for s in (r.get("sec_eff") or [])]
    texto = "S%s %s +%s %s" % (
        r.get("slot_no"), NOMBRE_SET.get(r.get("set_id"), r.get("set_id")),
        r.get("upgrade_curr", 0), texto_stat(pri),
    )
    if innato and innato[0]:
        texto += " (innato " + texto_stat(innato) + ")"
    return texto + " [" + ", ".join(subs) + "] ef" + str(eficiencia(r)) + "%"


def runas_de(u):
    runas = u.get("runes") or []
    if isinstance(runas, dict):
        runas = list(runas.values())
    return runas


# ---------------------------------------------------------------- stats
def stats_finales(u, runas=None):
    """Stats con runas, bonos de set propios, artefactos (stat principal) y reliquia.
    No incluye torres, totem, lider ni buffs."""
    if runas is None:
        runas = runas_de(u)
    base = {
        "HP": u.get("con", 0) * 15, "ATK": u.get("atk", 0), "DEF": u.get("def", 0),
        "SPD": u.get("spd", 0), "CR": u.get("critical_rate", 0),
        "CD": u.get("critical_damage", 0), "RES": u.get("resist", 0),
        "ACC": u.get("accuracy", 0),
    }
    plano = {k: 0 for k in base}
    pct = {"HP": 0, "ATK": 0, "DEF": 0, "SPD": 0}

    def sumar(stat_id, valor):
        nombre = NOMBRE_STAT.get(stat_id)
        if nombre is None:
            return
        if nombre in ("HP%", "ATK%", "DEF%"):
            pct[nombre[:-1]] += valor
        else:
            plano[nombre] += valor

    for r in runas:
        pri = r.get("pri_eff") or [0, 0]
        sumar(pri[0], pri[1])
        innato = r.get("prefix_eff") or [0, 0]
        if innato and innato[0]:
            sumar(innato[0], innato[1])
        for s in r.get("sec_eff") or []:
            sumar(s[0], s[1] + _molienda(s))

    for sid, n in Counter(r.get("set_id") for r in runas).items():
        if sid in BONO_SET:
            piezas, stat, valor = BONO_SET[sid]
            veces = n // piezas
            if stat.endswith("%"):
                pct[stat[:-1]] += valor * veces
            else:
                plano[stat] += valor * veces

    for a in u.get("artifacts") or []:
        pe = a.get("pri_effect") or [0, 0]
        if pe[0] == 100:
            plano["HP"] += pe[1]
        elif pe[0] == 101:
            plano["ATK"] += pe[1]
        elif pe[0] == 102:
            plano["DEF"] += pe[1]
    for rl in u.get("relics") or []:
        pe = rl.get("pri_effect") or [0, 0]
        if pe[0] == 100:
            pct["HP"] += pe[1]
        elif pe[0] == 101:
            pct["ATK"] += pe[1]
        elif pe[0] == 102:
            pct["DEF"] += pe[1]

    total = {}
    for k in base:
        if k in pct:
            total[k] = round(base[k] * (1 + pct[k] / 100) + plano[k])
        else:
            total[k] = round(base[k] + plano[k])
    total["EHP"] = round(total["HP"] * (1 + 3.5 * total["DEF"] / 1140))
    return total


def texto_sets(runas):
    c = Counter(NOMBRE_SET.get(r.get("set_id"), str(r.get("set_id"))) for r in runas)
    return " ".join("%sx%d" % (k, v) for k, v in c.items())


# ---------------------------------------------------------------- cuenta
def preparar_cuenta(datos, meta):
    """Devuelve la lista de tus monstruos (6 estrellas, nivel 40) ya procesados."""
    nombres = meta.get("nombres", {})
    tier_de = {}
    for tier, ids in meta.get("tiers_rta", {}).items():
        for i in ids:
            tier_de[int(i)] = tier

    unidades = [
        u for u in datos.get("unit_list", [])
        if u.get("unit_level") == 40 and u.get("class", 0) >= 5
    ]
    conteo_nombres = Counter(
        nombres.get(str(u.get("unit_master_id")), "ID " + str(u.get("unit_master_id")))
        for u in unidades
    )
    cuenta = []
    for u in unidades:
        mid = u.get("unit_master_id")
        nombre = nombres.get(str(mid), "ID " + str(mid))
        etiqueta = nombre
        if conteo_nombres[nombre] > 1:
            etiqueta = nombre + " #" + str(u["unit_id"])[-4:]
        runas = runas_de(u)
        cuenta.append({
            "unit": u,
            "id": u["unit_id"],
            "nombre": nombre,
            "etiqueta": etiqueta,
            "elemento": ELEMENTOS.get(u.get("attribute"), "?"),
            "tier": tier_de.get(mid, "-"),
            "stats": stats_finales(u, runas),
            "sets": texto_sets(runas),
            "n_runas": len(runas),
            "ef_media": round(sum(eficiencia(r) for r in runas) / len(runas)) if runas else 0,
        })
    return cuenta


def ids_protegidos(datos):
    """Monstruos que aparecen en tus equipos guardados (no se les toman runas)."""
    ids = set()
    for dk in datos.get("deck_list", []):
        ids.update(i for i in dk.get("unit_id_list", []) if i)
    ids.update(i for i in (datos.get("raid_deck") or {}).get("unit_id_list", []) if i)
    for e in datos.get("raid_best_clear_info_list", []):
        ids.update(x["unit_id"] for x in e.get("my_unit_deck_list", []) if x.get("unit_id"))
    return ids


# ---------------------------------------------------------------- RTA
def pool_rta(cuenta, tier_maximo):
    """Tus monstruos que aparecen en la tier list hasta el tier elegido."""
    limite = ORDEN_TIER.index(tier_maximo)
    pool = [m for m in cuenta if m["tier"] in ORDEN_TIER and ORDEN_TIER.index(m["tier"]) <= limite]
    pool.sort(key=lambda m: (ORDEN_TIER.index(m["tier"]), -m["stats"]["SPD"]))
    return pool


def candidatas_runas(datos, ids_cuenta, protegidos):
    """Runas 6*, +12 o mas, que puedes mover: libres o en monstruos que no usas."""
    fuente = []
    for r in datos.get("runes", []):
        if r.get("occupied_id") in (0, None) and r.get("class", 0) % 10 == 6 and r.get("upgrade_curr", 0) >= 12:
            fuente.append(("libre", r))
    for u in datos.get("unit_list", []):
        if u["unit_id"] in ids_cuenta or u["unit_id"] in protegidos:
            continue
        for r in runas_de(u):
            if r.get("class", 0) % 10 == 6 and r.get("upgrade_curr", 0) >= 12:
                fuente.append(("en un monstruo que no usas (id %s)" % u["unit_id"], r))
    return fuente


def cambios_seguros(monstruos, fuente, usadas=None, ganancia_minima=8):
    """Para cada monstruo, busca runas mejores del MISMO slot, MISMO set y MISMO stat
    principal que no bajen velocidad ni los stats clave."""
    usadas = set() if usadas is None else usadas
    propuestas = []
    for m in monstruos:
        u = m["unit"]
        antes = m["stats"]
        for r in sorted(runas_de(u), key=lambda x: x["slot_no"]):
            e = eficiencia(r)
            mejor = None
            for origen, c in fuente:
                if c["rune_id"] in usadas:
                    continue
                if c["slot_no"] != r["slot_no"] or c["set_id"] != r["set_id"]:
                    continue
                if c["pri_eff"][0] != r["pri_eff"][0]:
                    continue
                ec = eficiencia(c)
                if ec < e + ganancia_minima:
                    continue
                nuevas = [c if x["rune_id"] == r["rune_id"] else x for x in runas_de(u)]
                des = stats_finales(u, nuevas)
                ok = (
                    des["SPD"] >= antes["SPD"]
                    and des["CR"] >= antes["CR"] - 3
                    and des["RES"] >= antes["RES"] - 3
                    and des["ACC"] >= antes["ACC"] - 3
                    and des["CD"] >= antes["CD"] - 10
                    and des["HP"] >= antes["HP"] * 0.97
                    and des["DEF"] >= antes["DEF"] * 0.97
                )
                if ok and (mejor is None or ec > mejor[0]):
                    mejor = (ec, origen, c, des)
            if mejor:
                ec, origen, c, des = mejor
                usadas.add(c["rune_id"])
                cambios = {
                    k: des[k] - antes[k]
                    for k in ("SPD", "HP", "DEF", "CR", "CD", "RES", "ACC")
                    if des[k] != antes[k]
                }
                propuestas.append({
                    "Monstruo": m["etiqueta"],
                    "Slot": r["slot_no"],
                    "Set": NOMBRE_SET.get(r["set_id"], r["set_id"]),
                    "Quitar runa (ID)": r["rune_id"],
                    "Efic. actual %": e,
                    "Poner runa (ID)": c["rune_id"],
                    "Efic. nueva %": ec,
                    "La runa nueva esta": origen,
                    "Cambia en stats": ", ".join("%s %+d" % (k, v) for k, v in cambios.items()) or "sin cambios",
                })
                # actualizar el monstruo para que otros cambios usen sus runas nuevas
                u = copy.copy(u)
                u["runes"] = [c if x["rune_id"] == r["rune_id"] else x for x in runas_de(u)]
                antes = des
    return propuestas


def runas_debiles(monstruos, limite=75):
    """Runas equipadas de los monstruos elegidos con eficiencia baja (para saber donde falta)."""
    filas = []
    for m in monstruos:
        for r in sorted(runas_de(m["unit"]), key=lambda x: x["slot_no"]):
            e = eficiencia(r)
            if e < limite:
                filas.append({
                    "Monstruo": m["etiqueta"], "Slot": r["slot_no"],
                    "Set": NOMBRE_SET.get(r["set_id"], r["set_id"]),
                    "Runa (ID)": r["rune_id"], "Efic. %": e,
                    "SPD de la runa": valor_stat(r, 8),
                })
    return filas


# ---------------------------------------------------------------- R5
def equipos_candidatos(datos, por_id):
    """Equipos de 6 que ya tienes guardados (raid y limpiezas de R5)."""
    vistos = {}
    for e in datos.get("raid_best_clear_info_list", []):
        ids = [x["unit_id"] for x in e.get("my_unit_deck_list", []) if x.get("owner", 1) == 1]
        if len(ids) == 6 and all(i in por_id for i in ids):
            clave = frozenset(ids)
            probado = e.get("stage_id", 0) >= 5
            if clave not in vistos or (probado and not vistos[clave]["probado"]):
                lider = [x["unit_id"] for x in e["my_unit_deck_list"] if x.get("leader")]
                vistos[clave] = {"ids": ids, "probado": probado, "lider": lider[0] if lider else None,
                                 "origen": "limpieza de R%d" % e.get("stage_id", 0)}
    for dk in datos.get("deck_list", []):
        if dk.get("deck_type") != 3:
            continue
        ids = [i for i in dk.get("unit_id_list", []) if i]
        if len(ids) == 6 and all(i in por_id for i in ids):
            clave = frozenset(ids)
            if clave not in vistos:
                vistos[clave] = {"ids": ids, "probado": False, "lider": dk.get("leader_unit_id"),
                                 "origen": "equipo guardado %s" % dk.get("deck_seq")}
    return list(vistos.values())


def puntaje_equipo(equipo, por_id, reglas):
    miembros = sorted((por_id[i] for i in equipo["ids"]), key=lambda m: -m["stats"]["EHP"])
    frente, fondo = miembros[:2], miembros[2:]
    p = 0.0
    for m in frente:
        s = m["stats"]
        p += min(1, s["HP"] / reglas["frente_hp"]) + min(1, s["DEF"] / reglas["frente_def"])
    for m in fondo:
        s = m["stats"]
        p += min(1, s["HP"] / reglas["atras_hp"]) + min(1, s["DEF"] / reglas["atras_def"])
    if equipo["probado"]:
        p += 20
    return p


def mejores_tres_equipos(datos, cuenta, reglas):
    por_id = {m["id"]: m for m in cuenta}
    cands = equipos_candidatos(datos, por_id)
    for c in cands:
        c["puntaje"] = puntaje_equipo(c, por_id, reglas)
    mejor, mejor_p = [], -1
    for k in (3, 2, 1):
        for combo in itertools.combinations(cands, k):
            todos = [i for c in combo for i in c["ids"]]
            if len(set(todos)) != len(todos):
                continue
            p = sum(c["puntaje"] for c in combo)
            if p > mejor_p:
                mejor, mejor_p = list(combo), p
        if mejor:
            break
    mejor.sort(key=lambda c: (not c["probado"], -c["puntaje"]))
    return mejor, cands


def avisos_equipo(equipo, por_id, reglas):
    miembros = sorted((por_id[i] for i in equipo["ids"]), key=lambda m: -m["stats"]["EHP"])
    avisos = []
    for rol, grupo, hp_min, def_min in (
        ("frontal", miembros[:2], reglas["frente_hp"], reglas["frente_def"]),
        ("fondo", miembros[2:], reglas["atras_hp"], reglas["atras_def"]),
    ):
        for m in grupo:
            s = m["stats"]
            faltas = []
            if s["HP"] < hp_min:
                faltas.append("HP %d (guia %d)" % (s["HP"], hp_min))
            if s["DEF"] < def_min:
                faltas.append("DEF %d (guia %d)" % (s["DEF"], def_min))
            if faltas:
                avisos.append("%s (%s): %s" % (m["etiqueta"], rol, ", ".join(faltas)))
    return avisos, miembros


# ---------------------------------------------------------------- vender
def runas_para_vender(datos, excluir_ids=None):
    """Runas libres de 6 estrellas que no sirven ni en el mejor caso."""
    excluir_ids = excluir_ids or set()
    filas = []
    revisadas = 0
    otras = 0
    for r in datos.get("runes", []):
        if r.get("occupied_id") not in (0, None):
            continue
        if r.get("class", 0) % 10 != 6:
            otras += 1
            continue
        revisadas += 1
        if r["rune_id"] in excluir_ids:
            continue
        pri = r["pri_eff"][0]
        slot = r["slot_no"]
        presentes = {pri, (r.get("prefix_eff") or [0])[0]} | {s[0] for s in (r.get("sec_eff") or [])}
        nivel = r.get("upgrade_curr", 0)
        n_subs = len(r.get("sec_eff") or [])
        razones = []
        if slot in (2, 4, 6) and pri in (1, 3, 5):
            razones.append("stat principal plano")
        emax = eficiencia_max(r)
        if emax < 70:
            razones.append("eficiencia maxima %d%%" % emax)
        if n_subs >= 4 or nivel >= 12:
            if r["set_id"] == 3 and 8 not in presentes:
                razones.append("Swift sin SPD")
            if r["set_id"] in (4, 5) and not ({9, 10} & presentes):
                razones.append("Blade/Rage sin CR ni CD")
        if razones:
            filas.append({
                "Runa (ID)": r["rune_id"], "Set": NOMBRE_SET.get(r["set_id"], r["set_id"]),
                "Slot": slot, "Nivel": nivel, "Efic. actual %": eficiencia(r),
                "Efic. maxima %": emax, "Mana": r.get("sell_value", 0),
                "Razon": "; ".join(razones),
            })
    filas.sort(key=lambda f: f["Efic. maxima %"])
    return filas, revisadas, otras


def runas_equipadas_sin_uso(cuenta, ids_en_uso, limite=65):
    """Runas puestas en monstruos que no entran en tus planes y que son flojas."""
    filas = []
    for m in cuenta:
        if m["id"] in ids_en_uso:
            continue
        for r in runas_de(m["unit"]):
            emax = eficiencia_max(r)
            if emax < limite:
                filas.append({
                    "Esta en": m["etiqueta"], "Runa (ID)": r["rune_id"],
                    "Set": NOMBRE_SET.get(r["set_id"], r["set_id"]), "Slot": r["slot_no"],
                    "Nivel": r.get("upgrade_curr", 0), "Efic. maxima %": emax,
                    "Mana": r.get("sell_value", 0),
                })
    filas.sort(key=lambda f: f["Efic. maxima %"])
    return filas
