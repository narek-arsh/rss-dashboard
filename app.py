import time
import feedparser
import streamlit as st

# ---------- Configuración de la página ----------
st.set_page_config(page_title="Tendencias • RSS", layout="wide")
st.title("🌍 Dashboard de Tendencias (RSS)")
st.caption("Moda, música, arte, gastronomía, lifestyle y hospitality • Actualizado en la nube")

# ---------- LISTA DE FEEDS ----------
# Puedes añadir o quitar líneas. Formato: "Nombre visible": "URL del RSS"
FEEDS = {
    "Moda": {
        "The Guardian – Fashion": "https://www.theguardian.com/fashion/rss",
        "WWD – Business": "https://wwd.com/business-news/feed",
        "Hypebeast": "https://hypebeast.com/feed",
        "Highsnobiety": "https://www.highsnobiety.com/feed/",
    },
    "Música": {
        "Rolling Stone – Music": "https://www.rollingstone.com/music/feed",
        "Pitchfork – News": "https://pitchfork.com/feed/feed",
    },
    "Arte/Cultura": {
        "El País – Cultura": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/cultura/portada",
    },
    "Gastronomía": {
        "Fine Dining Lovers": "https://www.finedininglovers.com/rss",
    },
    "Lifestyle/Lujo": {
        "Wallpaper*": "https://www.wallpaper.com/rss",
        "Robb Report": "https://robbreport.com/feed",
    },
    "Hospitality": {
        "Skift": "https://skift.com/feed",
        "HospitalityNet": "https://www.hospitalitynet.org/feed/atom.xml",
    },
}

# ---------- Funciones útiles ----------
@st.cache_data(ttl=15 * 60)
def fetch_feed(url: str):
    """Descarga y parsea un feed RSS. Se cachea 15 min para ir ligero."""
    return feedparser.parse(url)

def entry_time_struct(e):
    """Devuelve la fecha de publicación si existe (struct_time)."""
    return getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)

def human_timeago(ts):
    """Convierte una fecha en 'hace X min/h/días'."""
    if not ts:
        return "—"
    published = time.mktime(ts)
    delta = int(time.time() - published)
    if delta < 60:
        return "hace segundos"
    if delta < 3600:
        return f"hace {delta // 60} min"
    if delta < 86400:
        return f"hace {delta // 3600} h"
    return f"hace {delta // 86400} días"

# ---------- Barra lateral (filtros) ----------
st.sidebar.header("Filtros")
categorias = list(FEEDS.keys())
sel_cats = st.sidebar.multiselect("Categorías", categorias, default=categorias)
max_por_fuente = st.sidebar.slider("Máximo por fuente", 3, 30, 10, 1)
busqueda = st.sidebar.text_input("Buscar (título/resumen)...", "")
modo = st.sidebar.radio("Modo de vista", ["Por categorías", "Todo mezclado (por fecha)"])

# ---------- Pintado ----------
if modo == "Por categorías":
    for cat in sel_cats:
        st.markdown(f"## {cat}")
        for nombre, url in FEEDS[cat].items():
            feed = fetch_feed(url)
            entries = feed.entries[:max_por_fuente]
            with st.expander(f"📡 {nombre}"):
                if not entries:
                    st.write("Sin entradas.")
                for e in entries:
                    titulo = getattr(e, "title", "(sin título)")
                    resumen = getattr(e, "summary", "")
                    link = getattr(e, "link", "#")
                    ts = entry_time_struct(e)

                    st.markdown(f"### {titulo}")
                    if resumen:
                        st.write((resumen[:400] + "...") if len(resumen) > 400 else resumen)
                    meta = []
                    if ts: meta.append(human_timeago(ts))
                    if hasattr(e, "author"): meta.append(f"por {e.author}")
                    if meta:
                        st.caption(" · ".join(meta))
                    st.markdown(f"[Leer más]({link})")
                    st.write("---")

else:  # Todo mezclado (por fecha)
    todos = []
    for cat in sel_cats:
        for nombre, url in FEEDS[cat].items():
            feed = fetch_feed(url)
            for e in feed.entries[:max_por_fuente]:
                todos.append((cat, nombre, e))

    # Ordenar por fecha (más reciente primero). Si no hay fecha, lo manda al final.
    todos.sort(key=lambda x: entry_time_struct(x[2]) or time.gmtime(0), reverse=True)

    st.markdown("## Últimas publicaciones")
    if busqueda:
        q = busqueda.lower()
        todos = [
            item for item in todos
            if (hasattr(item[2], "title") and q in item[2].title.lower())
            or (hasattr(item[2], "summary") and q in item[2].summary.lower())
        ]

    for cat, fuente, e in todos:
        titulo = getattr(e, "title", "(sin título)")
        resumen = getattr(e, "summary", "")
        link = getattr(e, "link", "#")
        ts = entry_time_struct(e)

        st.markdown(f"### {titulo}")
        st.caption(f"{cat} · {fuente} · {human_timeago(ts)}")
        if resumen:
            st.write((resumen[:400] + "...") if len(resumen) > 400 else resumen)
        st.markdown(f"[Leer más]({link})")
        st.write("---")

st.sidebar.info("Consejo: usa la vista 'Todo mezclado' y la búsqueda para detectar tendencias rápidas.")
