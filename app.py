import time
import feedparser
import streamlit as st

# ---------- Config de página ----------
st.set_page_config(page_title="Tendencias • RSS", layout="wide")
st.title("🌍 Dashboard de Tendencias (RSS)")
st.caption("Moda, música, arte, gastronomía, lifestyle y hospitality • Online")

# ---------- Feeds ----------
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

# ---------- Utilidades ----------
def to_epoch(tstruct):
    """Convierte time.struct_time -> epoch (int). Si no hay fecha, None."""
    if not tstruct:
        return None
    try:
        return int(time.mktime(tstruct))
    except Exception:
        return None

@st.cache_data(ttl=15 * 60)
def fetch_feed_sanitized(url: str):
    """
    Lee el RSS y devuelve SOLO datos simples (dicts con str/int).
    Esto evita errores de serialización (pickle) en Streamlit Cloud.
    """
    d = feedparser.parse(url)
    items = []
    for e in d.entries:
        # Tomamos published o updated y lo pasamos a epoch (int)
        ts = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
        items.append({
            "title": getattr(e, "title", "") or "(sin título)",
            "summary": getattr(e, "summary", "") or "",
            "link": getattr(e, "link", "") or "#",
            "author": getattr(e, "author", "") or "",
            "epoch": to_epoch(ts),
            "source": d.feed.title if hasattr(d, "feed") and hasattr(d.feed, "title") else "",
        })
    return items

def human_timeago_epoch(epoch):
    if not epoch:
        return "—"
    delta = int(time.time() - epoch)
    if delta < 60:
        return "hace segundos"
    if delta < 3600:
        return f"hace {delta // 60} min"
    if delta < 86400:
        return f"hace {delta // 3600} h"
    return f"hace {delta // 86400} días"

# ---------- Sidebar ----------
st.sidebar.header("Filtros")
categorias = list(FEEDS.keys())
sel_cats = st.sidebar.multiselect("Categorías", categorias, default=categorias)
max_por_fuente = st.sidebar.slider("Máximo por fuente", 3, 30, 10, 1)
busqueda = st.sidebar.text_input("Buscar (título/resumen)...", "")
modo = st.sidebar.radio("Modo de vista", ["Por categorías", "Todo mezclado (por fecha)"])

# ---------- Render ----------
if modo == "Por categorías":
    for cat in sel_cats:
        st.markdown(f"## {cat}")
        for nombre, url in FEEDS[cat].items():
            entries = fetch_feed_sanitized(url)[:max_por_fuente]
            with st.expander(f"📡 {nombre}"):
                if not entries:
                    st.write("Sin entradas.")
                for e in entries:
                    st.markdown(f"### {e['title']}")
                    if e["summary"]:
                        resumen = e["summary"]
                        st.write((resumen[:400] + "...") if len(resumen) > 400 else resumen)
                    meta = []
                    if e["epoch"]: meta.append(human_timeago_epoch(e["epoch"]))
                    if e["author"]: meta.append(f"por {e['author']}")
                    if meta:
                        st.caption(" · ".join(meta))
                    st.markdown(f"[Leer más]({e['link']})")
                    st.write("---")
else:
    # Reunir todo y ordenar por fecha
    todos = []
    for cat in sel_cats:
        for nombre, url in FEEDS[cat].items():
            for e in fetch_feed_sanitized(url)[:max_por_fuente]:
                todos.append((cat, nombre, e))
    todos.sort(key=lambda x: x[2]["epoch"] or 0, reverse=True)

    st.markdown("## Últimas publicaciones")
    if busqueda:
        q = busqueda.lower()
        todos = [
            item for item in todos
            if (q in item[2]["title"].lower()) or (q in item[2]["summary"].lower())
        ]

    for cat, fuente, e in todos:
        st.markdown(f"### {e['title']}")
        st.caption(f"{cat} · {fuente} · {human_timeago_epoch(e['epoch'])}")
        if e["summary"]:
            resumen = e["summary"]
            st.write((resumen[:400] + "...") if len(resumen) > 400 else resumen)
        st.markdown(f"[Leer más]({e['link']})")
        st.write("---")

st.sidebar.info("Consejo: usa la vista 'Todo mezclado' + búsqueda para detectar tendencias rápidas.")

