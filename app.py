# aura_trends_app.py
# Dashboard de Tendencias (RSS) con fuentes en sources.yaml
# - Limpia HTML de resúmenes
# - Carga feeds en caché (datos primitivos -> aptos para Streamlit Cloud)
# - Etiquetas de frescura y grid con imagen
# - Filtros por categoría, búsqueda y límite por fuente

import time
import re
from html import unescape
from pathlib import Path
from typing import Dict, List, Any, Optional

import streamlit as st
import feedparser
import yaml

# -------------------- Config de página --------------------
st.set_page_config(page_title="Aura Trends • RSS", layout="wide")
st.title("✨ Aura Trends Dashboard")
st.caption("Moda, música, arte/cultura, gastronomía, lifestyle/lujo y hospitality — en la nube")

# -------------------- Utilidades --------------------
DEFAULT_THUMB = "https://upload.wikimedia.org/wikipedia/commons/3/3f/Placeholder_view_vector.svg"

def clean_html(raw_html: str) -> str:
    """Elimina etiquetas HTML y decodifica entidades (&euro; -> €)."""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", "", raw_html)      # quita <p> <br> <span> ...
    text = unescape(text)
    return text.strip()

def to_epoch(tstruct) -> Optional[int]:
    """time.struct_time -> epoch (int)."""
    if not tstruct:
        return None
    try:
        return int(time.mktime(tstruct))
    except Exception:
        return None

def freshness_label(epoch: Optional[int]) -> str:
    """Devuelve chip de frescura según la antigüedad."""
    if not epoch:
        return "—"
    delta = int(time.time() - epoch)
    if delta < 3 * 3600:
        return "🔥 muy reciente"
    if delta < 24 * 3600:
        return "🆕 hoy"
    if delta < 3 * 24 * 3600:
        return "🗞️ esta semana"
    dias = delta // 86400
    return f"📅 hace {dias} d"

def first_image_from_entry(e) -> Optional[str]:
    """Intenta obtener una imagen del entry (media_content/media_thumbnail)."""
    # feedparser normaliza algunos campos
    try:
        if hasattr(e, "media_content"):
            mc = e.media_content
            if isinstance(mc, list) and mc:
                url = mc[0].get("url")
                if url:
                    return url
        if hasattr(e, "media_thumbnail"):
            mt = e.media_thumbnail
            if isinstance(mt, list) and mt:
                url = mt[0].get("url")
                if url:
                    return url
        # Algunas veces viene como 'image' o 'enclosures'
        if hasattr(e, "image") and isinstance(e.image, dict):
            url = e.image.get("href") or e.image.get("url")
            if url:
                return url
        if hasattr(e, "enclosures") and e.enclosures:
            url = e.enclosures[0].get("href")
            if url:
                return url
    except Exception:
        pass
    return None

# -------------------- Carga de configuration --------------------
@st.cache_data(ttl=3600)
def load_sources() -> List[Dict[str, str]]:
    """Lee sources.yaml (lista de {name, url, category})."""
    p = Path("sources.yaml")
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    items = data.get("sources", []) if isinstance(data, dict) else []
    # Normaliza claves esperadas
    norm = []
    for it in items:
        norm.append({
            "name": str(it.get("name", "")).strip(),
            "url": str(it.get("url", "")).strip(),
            "category": str(it.get("category", "Otros")).strip() or "Otros",
        })
    return norm

@st.cache_data(ttl=15 * 60)
def fetch_feed_sanitized(url: str) -> List[Dict[str, Any]]:
    """Descarga un feed y devuelve una lista de dicts simples (serializables)."""
    d = feedparser.parse(url)
    items = []
    feed_title = ""
    try:
        feed_title = getattr(d.feed, "title", "") if hasattr(d, "feed") else ""
    except Exception:
        feed_title = ""
    for e in d.entries:
        ts = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
        items.append({
            "title": getattr(e, "title", "") or "(sin título)",
            "summary": clean_html(getattr(e, "summary", "") or ""),
            "link": getattr(e, "link", "") or "#",
            "author": getattr(e, "author", "") or "",
            "epoch": to_epoch(ts),
            "image": first_image_from_entry(e) or "",
            "feed_title": feed_title,
        })
    return items

def chunk(lst, n):
    """Divide una lista en trozos de tamaño n (para grid)."""
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

# -------------------- Cargar fuentes --------------------
sources = load_sources()
if not sources:
    st.error("No encuentro `sources.yaml` en la raíz del repo. Súbelo con tus fuentes RSS.")
    st.stop()

categorias = sorted({s["category"] for s in sources})
st.sidebar.header("Filtros")
sel_cats = st.sidebar.multiselect("Categorías", categorias, default=categorias)
max_por_fuente = st.sidebar.slider("Máximo por fuente", 3, 30, 9, 1)
busqueda = st.sidebar.text_input("Buscar (título/resumen)...", "")
vista = st.sidebar.radio("Vista", ["Por fuente (expanders)", "Mezclado por fecha"])
refrescar = st.sidebar.button("🔄 Refrescar")

if refrescar:
    # Limpia cachés de datos
    load_sources.clear()
    fetch_feed_sanitized.clear()
    st.experimental_rerun()

# -------------------- Render --------------------
if vista == "Por fuente (expanders)":
    # Agrupar por categoría para un orden lógico
    for cat in sel_cats:
        st.markdown(f"## {cat}")
        cat_sources = [s for s in sources if s["category"] == cat]
        for src in cat_sources:
            with st.expander(f"📡 {src['name']}"):
                entries = fetch_feed_sanitized(src["url"])[:max_por_fuente]
                if busqueda:
                    q = busqueda.lower()
                    entries = [
                        e for e in entries
                        if q in e["title"].lower() or q in e["summary"].lower()
                    ]
                if not entries:
                    st.write("Sin entradas.")
                    continue

                # Grid 3 columnas
                for row in chunk(entries, 3):
                    cols = st.columns(3)
                    for col, e in zip(cols, row):
                        with col:
                            img = e["image"] or DEFAULT_THUMB
                            st.image(img, use_container_width=True)
                            st.markdown(f"### {e['title']}")
                            st.caption(f"{freshness_label(e['epoch'])}"
                                       + (f" · por {e['author']}" if e['author'] else ""))
                            if e["summary"]:
                                txt = e["summary"][:220] + ("..." if len(e["summary"]) > 220 else "")
                                st.write(txt)
                            st.markdown(f"[Leer más]({e['link']})")
                st.write("---")
else:
    # Mezclado por fecha: reunir todo lo seleccionado y ordenar
    all_entries = []
    for src in sources:
        if src["category"] not in sel_cats:
            continue
        for e in fetch_feed_sanitized(src["url"])[:max_por_fuente]:
            e["_source_name"] = src["name"]
            e["_category"] = src["category"]
            all_entries.append(e)

    # Filtro de búsqueda
    if busqueda:
        q = busqueda.lower()
        all_entries = [
            e for e in all_entries
            if q in e["title"].lower() or q in e["summary"].lower()
        ]

    # Orden por fecha (más reciente primero)
    all_entries.sort(key=lambda x: x["epoch"] or 0, reverse=True)

    st.markdown("## Últimas publicaciones")
    if not all_entries:
        st.info("Sin resultados para los filtros actuales.")
    else:
        for row in chunk(all_entries, 3):
            cols = st.columns(3)
            for col, e in zip(cols, row):
                with col:
                    img = e["image"] or DEFAULT_THUMB
                    st.image(img, use_container_width=True)
                    st.markdown(f"### {e['title']}")
                    st.caption(f"{e['_category']} · {e.get('feed_title','') or e.get('_source_name','')}"
                               f" · {freshness_label(e['epoch'])}")
                    if e["summary"]:
                        txt = e["summary"][:240] + ("..." if len(e["summary"]) > 240 else "")
                        st.write(txt)
                    st.markdown(f"[Leer más]({e['link']})")
        st.write("---")

st.sidebar.info("Tip: usa 'Mezclado por fecha' + búsqueda para detectar tendencias rápido.")
