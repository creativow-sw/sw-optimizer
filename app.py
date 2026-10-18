import json
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

import motor

st.set_page_config(page_title="SW Optimizer", layout="wide")
st.title("Summoners War Optimizer")

# ---------- Contraseña ----------
clave = st.secrets.get("APP_PASSWORD")
if not clave:
    st.error("Falta APP_PASSWORD en Secrets.")
    st.stop()
if st.text_input("Contraseña (escríbela y pulsa Enter)", type="password") != clave:
    st.stop()

CARPETA = Path(__file__).parent
CLAVES_UTILES = [
    "wizard_info", "unit_list", "runes", "deck_list", "raid_deck",
    "raid_best_clear_info_list", "rtpvp_info",
]


@st.cache_data(ttl=60 * 60 * 24 * 7, show_spinner=False)
def nombres_swarfarm():
    """Solo se usa si tienes un monstruo que no esta en meta_rules.json."""
    nombres = {}
    url = "https://swarfarm.com/api/v2/monsters/?format=json"
    paginas = 0
    try:
        while url and paginas < 60:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            pagina = resp.json()
            for m in pagina.get("results", []):
                if m.get("com2us_id") is not None:
                    nombres[str(m["com2us_id"])] = m.get("name", "?")
            url = pagina.get("next")
            paginas += 1
    except Exception:
        pass
    return nombres


@st.cache_data(show_spinner="Leyendo tu cuenta...")
def leer_cuenta(contenido, version_meta):
    completo = json.loads(contenido)
    datos = {k: completo.get(k) for k in CLAVES_UTILES}
    meta = json.loads((CARPETA / "meta_rules.json").read_text(encoding="utf-8"))
    conocidos = meta.get("nombres", {})
    faltan = [
        u for u in datos["unit_list"]
        if u.get("unit_level") == 40 and u.get("class", 0) >= 5
        and str(u.get("unit_master_id")) not in conocidos
    ]
    if faltan:
        meta["nombres"] = {**nombres_swarfarm(), **conocidos}
    cuenta = motor.preparar_cuenta(datos, meta)
    return datos, meta, cuenta


def tabla_monstruos(lista):
    filas = []
    for m in lista:
        s = m["stats"]
        filas.append({
            "Tier": m["tier"], "Monstruo": m["etiqueta"], "Elemento": m["elemento"],
            "SPD": s["SPD"], "HP": s["HP"], "DEF": s["DEF"], "EHP": s["EHP"],
            "CR": s["CR"], "CD": s["CD"], "RES": s["RES"], "ACC": s["ACC"],
            "Sets": m["sets"], "Efic. media runas %": m["ef_media"],
        })
    return pd.DataFrame(filas)


def mostrar(df, vacio="Nada que mostrar."):
    if df is None or len(df) == 0:
        st.info(vacio)
    else:
        try:
            st.dataframe(df, width="stretch", hide_index=True)
        except TypeError:
            st.dataframe(df, use_container_width=True, hide_index=True)


# ---------- Subir el archivo ----------
archivo = st.file_uploader("Sube tu archivo JSON de SWEX", type=["json"])
if archivo is None:
    st.info("Sube tu archivo para empezar.")
    st.stop()

meta_texto = (CARPETA / "meta_rules.json").read_text(encoding="utf-8")
try:
    datos, meta, cuenta = leer_cuenta(archivo.getvalue(), meta_texto)
except Exception as e:
    st.error("No pude leer el archivo. ¿Es el JSON que exporta SWEX? (" + str(e) + ")")
    st.stop()

info = datos.get("wizard_info") or {}
st.success(
    "Cuenta: " + str(info.get("wizard_name", "?"))
    + " · " + str(len(cuenta)) + " monstruos de 6★ nivel 40 analizados"
)
st.caption(
    "Stats finales = base + runas + bonos de set + artefactos (stat principal) + reliquia. "
    "No incluyen torres, totem, líder ni buffs, así que pueden diferir un poco del juego."
)

por_id = {m["id"]: m for m in cuenta}
reglas = meta["r5"]

# ---------- Cálculos (una sola vez) ----------
tab_rta, tab_r5, tab_vender = st.tabs(["RTA", "R5 solo", "Runas para vender"])

with tab_rta:
    tier_max = st.select_slider(
        "Mostrar mis monstruos hasta el tier",
        options=motor.ORDEN_TIER, value="C",
    )

pool = motor.pool_rta(cuenta, tier_max)
equipos, candidatos = motor.mejores_tres_equipos(datos, cuenta, reglas)
ids_r5 = [i for e in equipos for i in e["ids"]]
ids_en_uso = {m["id"] for m in pool} | set(ids_r5)

pool_ids = {m["id"] for m in pool}
objetivo = list(pool) + [por_id[i] for i in ids_r5 if i not in pool_ids]
protegidos = motor.ids_protegidos(datos)
fuente = motor.candidatas_runas(datos, set(por_id), protegidos)
cambios = motor.cambios_seguros(objetivo, fuente)
cambios_por_monstruo = {}
for c in cambios:
    cambios_por_monstruo.setdefault(c["Monstruo"], []).append(c)

# ---------- RTA ----------
with tab_rta:
    st.subheader("Mis monstruos que sirven para RTA")
    st.write(
        "Son los monstruos que **tú tienes** y que aparecen en la tier list de RTA "
        "(" + meta["fuente_rta"] + "). La tier mide qué tan elegido y ganador es cada monstruo "
        "en el rango más alto; para rangos más bajos puede variar."
    )
    mostrar(tabla_monstruos(pool), "Ninguno de tus monstruos entra en ese tier.")
    st.caption(
        "La app no evalúa la sinergia entre monstruos (necesita leer sus habilidades). "
        "Úsala para elegir con quién construir, y revisa los grupos en el RTA Builder de SWLens."
    )

    st.subheader("Runas que puedes usar para ellos")
    st.write(
        "Cambios **seguros**: misma posición, mismo set y mismo stat principal, con una runa "
        "mejor que ya tienes (libre o en un monstruo que no usas). No bajan la velocidad ni "
        "los stats clave."
    )
    df = pd.DataFrame([c for m in pool for c in cambios_por_monstruo.get(m["etiqueta"], [])])
    mostrar(df, "No hay cambios seguros: las runas de estos monstruos ya son de lo mejor que tienes.")

    st.subheader("Runas flojas que no tienen reemplazo")
    debiles = motor.runas_debiles(pool)
    hechas = {(c["Monstruo"], c["Slot"]) for c in cambios}
    debiles = [f for f in debiles if (f["Monstruo"], f["Slot"]) not in hechas]
    mostrar(pd.DataFrame(debiles), "Ninguna.")
    st.caption("Estas son las posiciones donde conviene farmear o mejorar una runa.")

# ---------- R5 ----------
with tab_r5:
    st.subheader("Mis 3 equipos para R5 solo")
    st.write(
        "Sale de los equipos de 6 que ya tienes guardados en el juego y de tus limpiezas de R5. "
        "La app elige la mejor combinación de **3 equipos sin monstruos repetidos**."
    )
    if len(equipos) < 3:
        st.warning(
            "Solo encontré %d equipo(s) de 6 que no se repitan entre sí. "
            "Guarda más equipos en el juego para que la app pueda armar los 3." % len(equipos)
        )
    for n, e in enumerate(equipos, start=1):
        avisos, miembros = motor.avisos_equipo(e, por_id, reglas)
        etiqueta = "✅ ya limpió R5" if e["probado"] else "sin limpieza de R5 registrada"
        st.markdown("**Equipo %d** · %s · origen: %s" % (n, etiqueta, e["origen"]))
        lider = por_id.get(e["lider"])
        if lider:
            st.write("Líder guardado: " + lider["etiqueta"])
        mostrar(tabla_monstruos(miembros))
        if avisos:
            with st.expander("Avisos por estadísticas (%d)" % len(avisos)):
                for a in avisos:
                    st.write("• " + a)
                st.caption(
                    "Son guías orientativas de HP y DEF para frontal y fondo. "
                    "Si el equipo ya limpió R5, tómalas como información."
                )
        df = pd.DataFrame([c for m in miembros for c in cambios_por_monstruo.get(m["etiqueta"], [])])
        if len(df):
            st.write("Cambios de runas seguros para este equipo:")
            mostrar(df)
    st.caption(
        "La app no verifica debuffs (romper defensa, bloqueo de curación, etc.) ni líderes, "
        "porque eso requiere leer las habilidades. Un equipo que ya limpió R5 sí está comprobado."
    )

# ---------- Vender ----------
with tab_vender:
    st.subheader("Runas libres que no sirven")
    excluir = {c["Poner runa (ID)"] for c in cambios}
    filas, revisadas, otras = motor.runas_para_vender(datos, excluir)
    c1, c2, c3 = st.columns(3)
    c1.metric("Runas libres 6★ revisadas", revisadas)
    c2.metric("Para vender", len(filas))
    c3.metric("Maná estimado", f"{sum(f['Mana'] for f in filas):,}")
    st.write(
        "Se marcan solo las que **no sirven ni en el mejor caso**: stat principal plano en "
        "slots 2/4/6, eficiencia máxima menor a 70%, Swift sin velocidad, o Blade/Rage sin "
        "crítico. No incluye las runas que la app te sugiere usar. "
        "Las runas de 5★ o menos (" + str(otras) + ") no se revisan."
    )
    df = pd.DataFrame(filas)
    mostrar(df, "No encontré runas libres para vender.")
    if len(df):
        st.download_button(
            "Descargar lista (CSV)",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="runas_para_vender.csv", mime="text/csv",
        )

    with st.expander("Runas equipadas en monstruos que no entran en tus planes"):
        sin_uso = motor.runas_equipadas_sin_uso(cuenta, ids_en_uso)
        st.write(
            "Son runas flojas (eficiencia máxima menor a 65%) puestas en monstruos que no "
            "están en tu lista de RTA ni en tus 3 equipos de R5. Véndelas solo si ya no usas "
            "ese monstruo."
        )
        mostrar(pd.DataFrame(sin_uso), "Ninguna.")

st.caption("Datos de meta: versión " + meta["version"] + ". " + meta["fuente_rta"])
