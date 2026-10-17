import json
from collections import Counter

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="SW Optimizer", layout="wide")
st.title("Summoners War Optimizer")

# ---------- Contraseña ----------
clave = st.secrets.get("APP_PASSWORD")
if not clave:
    st.error("Falta APP_PASSWORD en Secrets.")
    st.stop()
if st.text_input("Contraseña (escríbela y pulsa Enter)", type="password") != clave:
    st.stop()

# ---------- Datos fijos del juego ----------
NOMBRE_STAT = {
    1: "HP", 2: "HP%", 3: "ATK", 4: "ATK%", 5: "DEF", 6: "DEF%",
    8: "SPD", 9: "CR", 10: "CD", 11: "RES", 12: "ACC",
}
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
    1: (2, "HP%", 15),
    2: (2, "DEF%", 15),
    3: (4, "SPD%", 25),
    4: (2, "CR", 12),
    5: (4, "CD", 40),
    6: (2, "ACC", 20),
    7: (2, "RES", 20),
    8: (4, "ATK%", 35),
}


def cantidad(x):
    return len(x) if x else 0


def texto_stat(par):
    if not par or par[0] not in NOMBRE_STAT:
        return ""
    return NOMBRE_STAT[par[0]] + "+" + str(par[1])


def eficiencia(r):
    innato = r.get("prefix_eff") or [0, 0]
    suma = 0.0
    if innato and innato[0] in MAX_MEJORA:
        suma += innato[1] / MAX_MEJORA[innato[0]]
    for s in r.get("sec_eff") or []:
        molienda = s[3] if len(s) > 3 else 0
        if s[0] in MAX_MEJORA:
            suma += (s[1] + molienda) / MAX_MEJORA[s[0]]
    return round((1 + suma * 0.2) / 2.8 * 100)


def resumen_runa(r):
    pri = r.get("pri_eff") or [0, 0]
    innato = r.get("prefix_eff") or [0, 0]
    subs = []
    for s in r.get("sec_eff") or []:
        molienda = s[3] if len(s) > 3 else 0
        subs.append(texto_stat([s[0], s[1] + molienda]))
    nombre_set = NOMBRE_SET.get(r.get("set_id"), str(r.get("set_id")))
    texto = "S" + str(r.get("slot_no")) + " " + nombre_set
    texto += " +" + str(r.get("upgrade_curr", 0)) + " " + texto_stat(pri)
    if innato and innato[0]:
        texto += " (innato " + texto_stat(innato) + ")"
    texto += " [" + ", ".join(subs) + "]"
    texto += " ef" + str(eficiencia(r)) + "%"
    return texto


def stats_finales(u, runas):
    base = {
        "HP": u.get("con", 0) * 15,
        "ATK": u.get("atk", 0),
        "DEF": u.get("def", 0),
        "SPD": u.get("spd", 0),
        "CR": u.get("critical_rate", 0),
        "CD": u.get("critical_damage", 0),
        "RES": u.get("resist", 0),
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
            molienda = s[3] if len(s) > 3 else 0
            sumar(s[0], s[1] + molienda)

    conteo_ids = Counter(r.get("set_id") for r in runas)
    for sid, n in conteo_ids.items():
        if sid in BONO_SET:
            piezas, stat, valor = BONO_SET[sid]
            veces = n // piezas
            if stat.endswith("%"):
                pct[stat[:-1]] += valor * veces
            else:
                plano[stat] += valor * veces

    total = {}
    for k in base:
        if k in pct:
            total[k] = round(base[k] * (1 + pct[k] / 100) + plano[k])
        else:
            total[k] = round(base[k] + plano[k])
    total["EHP"] = round(total["HP"] * (1 + 3.5 * total["DEF"] / 1140))
    return total


@st.cache_data(ttl=60 * 60 * 24 * 7, show_spinner="Cargando nombres de monstruos...")
def cargar_nombres():
    nombres = {}
    url = "https://swarfarm.com/api/v2/monsters/?format=json"
    paginas = 0
    try:
        while url and paginas < 60:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            datos_pagina = resp.json()
            for m in datos_pagina.get("results", []):
                if m.get("com2us_id") is not None:
                    nombres[m["com2us_id"]] = m.get("name", "?")
            url = datos_pagina.get("next")
            paginas += 1
    except Exception:
        pass
    return nombres


# ---------- Subir el archivo ----------
archivo = st.file_uploader("Sube tu archivo JSON de SWEX", type=["json"])
if archivo is None:
    st.info("Sube tu archivo para empezar.")
    st.stop()

try:
    datos = json.load(archivo)
except Exception:
    st.error("No pude leer el archivo. ¿Es el JSON que exporta SWEX?")
    st.stop()

info = datos.get("wizard_info", {})
monstruos = datos.get("unit_list", [])
runas_libres = datos.get("runes", [])

st.success("Archivo leído correctamente. Cuenta: " + str(info.get("wizard_name", "?")))

nombres = cargar_nombres()
if not nombres:
    st.warning("No pude cargar los nombres de los monstruos. Se mostrarán solo números.")

# ---------- Resumen de la cuenta ----------
unidades = [
    u for u in monstruos
    if u.get("unit_level") == 40 and u.get("class", 0) >= 5
]

lineas = []
filas = []
total_runas_equipadas = 0

for u in unidades:
    mid = u.get("unit_master_id")
    nombre = nombres.get(mid, "ID " + str(mid))
    elemento = ELEMENTOS.get(u.get("attribute"), "?")
    runas = u.get("runes") or []
    if isinstance(runas, dict):
        runas = list(runas.values())
    total_runas_equipadas += len(runas)

    conteo = Counter(
        NOMBRE_SET.get(r.get("set_id"), str(r.get("set_id"))) for r in runas
    )
    sets_txt = " ".join(k + "x" + str(v) for k, v in conteo.items())

    f = stats_finales(u, runas)
    finales = (
        "HP " + str(f["HP"]) + " ATK " + str(f["ATK"]) + " DEF " + str(f["DEF"])
        + " SPD " + str(f["SPD"]) + " CR " + str(f["CR"]) + " CD " + str(f["CD"])
        + " RES " + str(f["RES"]) + " ACC " + str(f["ACC"]) + " EHP " + str(f["EHP"])
    )

    cabecera = (
        nombre + " (" + elemento + ", " + str(u.get("class")) + "*)"
        + " id" + str(u.get("unit_id"))
        + " | finales: " + finales
        + " | sets: " + sets_txt
        + " | artefactos: " + str(cantidad(u.get("artifacts")))
    )
    detalle = "\n".join("   " + resumen_runa(r) for r in runas)
    lineas.append(cabecera + "\n" + detalle)

    filas.append({
        "Monstruo": nombre,
        "Elemento": elemento,
        "Runas": len(runas),
        "Sets": sets_txt,
        "SPD": f["SPD"],
        "HP": f["HP"],
        "DEF": f["DEF"],
        "EHP": f["EHP"],
        "CR": f["CR"],
        "CD": f["CD"],
        "RES": f["RES"],
        "ACC": f["ACC"],
    })

libres = [r for r in runas_libres if r.get("class", 0) % 10 == 6]
libres.sort(key=eficiencia, reverse=True)
mejores_libres = libres[:60]

texto_final = "MONSTRUOS (nivel 40, 5 estrellas o más):\n\n" + "\n\n".join(lineas)
texto_final += "\n\nMEJORES RUNAS SIN EQUIPAR (6 estrellas):\n"
texto_final += "\n".join(resumen_runa(r) for r in mejores_libres)

# ---------- Mostrar ----------
c1, c2, c3 = st.columns(3)
c1.metric("Monstruos incluidos", len(unidades))
c2.metric("Runas equipadas incluidas", total_runas_equipadas)
c3.metric("Tamaño del resumen (tokens aprox.)", f"{len(texto_final) // 4:,}")

st.subheader("Tus monstruos")
st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

with st.expander("Ver el texto completo del resumen"):
    st.code(texto_final, language=None)

st.caption(
    "Stats finales = base + runas + bonos de set propios. "
    "No incluyen torres, totem ni líder. Todavía no se envía nada a OpenAI."
)



# ---------- Análisis con ChatGPT ----------
import re
from openai import OpenAI

st.header("Análisis del entrenador (ChatGPT)")

modelo = st.text_input("Modelo de OpenAI", value="gpt-5.4-mini")
usar_web = st.checkbox(
    "Buscar el meta actual en internet (cuesta un poco más)", value=True
)

INSTRUCCIONES = """
Eres un entrenador experto de Summoners War (nivel profesional, RTA y Rift Raid R5).
Recibirás el inventario de UN jugador: sus monstruos con stats finales (sin torres,
líder ni artefactos), las runas equipadas con su eficiencia y sus mejores runas libres.

Reglas:
- Usa SOLO monstruos y runas que aparecen en los datos. Cita cada monstruo como
  Nombre (idNUMERO) para que se pueda verificar.
- Si no estás seguro de cuál es el meta actual, dilo en vez de inventar.
  Si puedes buscar en internet, busca el meta actual de RTA y de Solo R5 y menciona la fuente.
- Responde en español, claro y sin jerga innecesaria.

Entrega:
1. RTA: los 12 a 15 monstruos más fuertes para RTA que tiene el jugador, con su rol,
   qué sets y stats deberían tener, y qué runas actuales están mal para ese rol
   (ejemplos concretos, y qué runas libres o de otros monstruos usar).
2. Dos o tres grupos de RTA que hagan sinergia, con el orden de velocidad.
3. Solo R5: 3 equipos de 6 monstruos (18 distintos, sin repetir), con líder de cada
   equipo, qué debuffs y roles cubre y qué les falta. Si no se puede armar completo
   con su caja, dilo y explica qué falta.
4. Runas para vender o reemplazar: lista concreta (monstruo, slot, set, motivo) de
   runas equipadas o libres que no aportan a ninguno de los planes anteriores.
5. Las 5 mejoras de mayor impacto, en orden.
"""

if st.button("Analizar mi cuenta"):
    cliente = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    pedido = {"model": modelo, "instructions": INSTRUCCIONES, "input": texto_final}
    with st.spinner("Pensando... puede tardar un minuto."):
        try:
            if usar_web:
                try:
                    resp = cliente.responses.create(
                        **pedido, tools=[{"type": "web_search"}]
                    )
                except Exception:
                    st.warning("No pude usar la búsqueda web; analizo sin ella.")
                    resp = cliente.responses.create(**pedido)
            else:
                resp = cliente.responses.create(**pedido)
            st.session_state["respuesta"] = resp.output_text
            try:
                st.session_state["uso"] = (
                    str(resp.usage.input_tokens) + " entrada / "
                    + str(resp.usage.output_tokens) + " salida"
                )
            except Exception:
                st.session_state["uso"] = "no disponible"
        except Exception as e:
            st.error("Error al llamar a OpenAI: " + str(e))

if "respuesta" in st.session_state:
    respuesta = st.session_state["respuesta"]
    st.markdown(respuesta)
    st.caption("Tokens usados: " + st.session_state.get("uso", "?"))

    ids_validos = {str(u.get("unit_id")) for u in unidades}
    ids_citados = set(re.findall(r"id(\d+)", respuesta))
    raros = ids_citados - ids_validos
    if raros:
        st.warning(
            "Ojo: la respuesta menciona ids que no están en tu cuenta: "
            + ", ".join(sorted(raros))
        )
