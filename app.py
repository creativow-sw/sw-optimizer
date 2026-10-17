import json
import streamlit as st

st.set_page_config(page_title="SW Optimizer", layout="wide")
st.title("Summoners War Optimizer")

archivo = st.file_uploader("Sube tu archivo JSON de SWEX", type=["json"])

if archivo is None:
    st.info("Sube tu archivo para empezar.")
    st.stop()

try:
    datos = json.load(archivo)
except Exception:
    st.error("No pude leer el archivo. ¿Es el JSON que exporta SWEX?")
    st.stop()


def cantidad(x):
    return len(x) if x else 0


info = datos.get("wizard_info", {})
monstruos = datos.get("unit_list", [])
runas_libres = datos.get("runes", [])
artefactos_libres = datos.get("artifacts", [])

runas_equipadas = sum(cantidad(m.get("runes")) for m in monstruos)
artefactos_equipados = sum(cantidad(m.get("artifacts")) for m in monstruos)

st.success("Archivo leído correctamente.")
st.write("Cuenta:", info.get("wizard_name", "(sin nombre)"))

col1, col2, col3 = st.columns(3)
col1.metric("Monstruos", cantidad(monstruos))
col2.metric(
    "Runas",
    cantidad(runas_libres) + runas_equipadas,
    help="Sin equipar: " + str(cantidad(runas_libres)),
)
col3.metric(
    "Artefactos",
    cantidad(artefactos_libres) + artefactos_equipados,
    help="Sin equipar: " + str(cantidad(artefactos_libres)),
)
