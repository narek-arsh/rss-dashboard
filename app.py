# aura_trends_app.py — Aura Trends con IA (Gemini para resúmenes)
import time
import re
import hashlib
from html import unescape
from pathlib import Path
from typing import Dict, List, Any, Optional

import streamlit as st
import feedparser
import yaml

# === IA (Gemini) ===
try:
    import google.generativeai as genai
    GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
        _GEMINI_OK = True
    else:
        _GEMINI_OK = False
except Exception:
    _GEMINI_OK = False

# -------------------- Config de página --------------------
st.set_page_config(page_title="Aura Trends • RSS + IA", layout="wide")
st.title("✨ Aura Trends Dashboard")
st.caption("Moda, música, arte/cultura, gastronomía, lifestyle/lujo y hospitality — en la nube")
# --- TEST GEMINI KEY ---
if "GEMINI_API_KEY" in st.secrets:
    st.sidebar.success("🔑 Se encontró GEMINI_API_KEY en Secrets.")
    try:
        import google.generativeai as genai
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content("Di 'Hola desde Gemini' en una frase corta, en español.")
        st.sidebar.write("Gemini responde:", resp.text)
    except Exception as e:
        st.sidebar.error("Error al probar Gemini: " + str(e))
else:
    st.sidebar.error("❌ No se encontró GEMINI_API_KEY en Secrets.")

# -------------------- Utilidades --------------------
DEFAULT_THUMB = "https://upload.wikimedia.org/wikipedia/commons/3/3f/Placeholder_view_vector.svg"

def clean_html(raw_html: str) -> str:
    """Elimina etiquetas HTML y decodifica entidades (&euro; -> €)."""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", "", raw_html)
    return unescape(text).strip()

def to_epoch(tstruct) -> Optional[int]:
    if not tstruct:
        return None
    try:
        return int(time.mktime(tstruct))
    except Exception:
        return None

def freshness_label(epoch: Optional[int]) -> str:
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
    try:
        if hasattr(e, "media_content"):
            mc = e.media_content
            if isinstance(mc, list) and mc:
                url = mc[0].get("url")
                if url: return url
        if hasattr(e, "media_thumbnail"):
            mt = e.media_thumbnail
            if isinstance(mt, list) and mt:
                url = mt[0].get("url")
                if url: return url
        if hasattr(e, "image") and isinstance(e.image, dict):
            url = e.image.get("href") or e.image.get("url")
            if url: return url
        if hasattr(e, "enclosures") and e.enclosures:
            url = e.enclosures[0].get("href")
            if url: return url
    except Exception:
        pass
    return None

def chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

# -------------------- Carga de sources --------------------
@st.cache_data(ttl=3600)
def load_sources() -> List[Dict[str, str]]:
    p = Path("sources.yaml")
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    items = data.get("sources", []) if isinstance(data, dict) else []
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
    """Devuelve dicts simples (serializables) por entrada."""
    d = feedparser.parse(url)
    items = []
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

# -------------------- IA: resúmenes con Gemini --------------------
def _hash_key(*parts: str) -> str:
    return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()

@st.cache_data(ttl=7 * 24 * 3600)  # cachea 7 días
def ai_summarize_cached(model_name: str, title: str, summary: str, link: str) -> str:
    """Llama a Gemini con entrada recortada y devuelve un resumen en español."""
    if not _GEMINI_OK:
        return ""
    # Recorta entrada para no enviar textos enormes
    base_text = (title + ". " + summary)[:2200]
    prompt = (
        "Eres un analista de tendencias. Resume en una o dos frases, claras y concretas, "
        "esta noticia para un público profesional de hospitality y lujo. Devuélvelo en español, "
        "sin emojis, sin enlaces ni HTML:\n\n"
        f"{base_text}"
    )
    model = genai.GenerativeModel(model_name)
    resp = model.generate_content(prompt)
    text = resp.text.strip() if hasattr(resp, "text") and resp.text else ""
    # Post-procesado mínimo
    text = re.sub(r"\s+", " ", text).strip()
    return text

def ai_summary(title: str, summary: str, link: str, strength: str = "flash") -> str:
    """Wrapper que elige el modelo y clave de caché."""
    model = "gemini-1.5-flash" if strength == "flash" else "gemini-1.5-pro"
    key = _hash_key(model, title, summary, link)
    return ai_summarize_cached(model, title, summary, link)

# -------------------- Controles UI --------------------
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

st.sidebar.divider()
use_ai = st.sidebar.toggle("Usar IA (Gemini) para resumen", value=False,
                           help="Actívalo para ver un 'Resumen IA' en español bajo cada tarjeta.")
ai_model_strength = st.sidebar.radio("Modelo", ["Flash (rápido)", "Pro (más preciso)"], index=0,
                                     help="Flash es más barato/rápido; Pro es más fino.")
ai_strength_key = "flash" if ai_model_strength.startswith("Flash") else "pro"

refrescar = st.sidebar.button("🔄 Refrescar todo")
if refrescar:
    load_sources.clear()
    fetch_feed_sanitized.clear()
    ai_summarize_cached.clear()
    st.success("✅ Caché limpiada, pulsa arriba en 'Rerun' o recarga la página.")

# -------------------- Render --------------------
if vista == "Por fuente (expanders)":
    for cat in sel_cats:
        st.markdown(f"## {cat}")
        cat_sources = [s for s in sources if s["category"] == cat]
        for src in cat_sources:
            with st.expander(f"📡 {src['name']}"):
                entries = fetch_feed_sanitized(src["url"])[:max_por_fuente]
                if busqueda:
                    q = busqueda.lower()
                    entries = [e for e in entries if q in e["title"].lower() or q in e["summary"].lower()]
                if not entries:
                    st.write("Sin entradas.")
                    continue

                for row in chunk(entries, 3):
                    cols = st.columns(3)
                    for col, e in zip(cols, row):
                        with col:
                            img = e["image"] or DEFAULT_THUMB
                            st.image(img, use_container_width=True)
                            st.markdown(f"### {e['title']}")
                            st.caption(f"{freshness_label(e['epoch'])}" + (f" · por {e['author']}" if e['author'] else ""))

                            if e["summary"]:
                                txt = e["summary"][:220] + ("..." if len(e["summary"]) > 220 else "")
                                st.write(txt)

                            # Resumen IA opcional
                            if use_ai and _GEMINI_OK:
                                try:
                                    resumen = ai_summary(e["title"], e["summary"], e["link"], strength=ai_strength_key)
                                    if resumen:
                                        st.caption("Resumen IA: " + resumen)
                                except Exception as ex:
                                    st.caption("Resumen IA: (no disponible)")

                            st.markdown(f"[Leer más]({e['link']})")
                st.write("---")
else:
    # Mezclado
    all_entries = []
    for src in sources:
        if src["category"] not in sel_cats:
            continue
        for e in fetch_feed_sanitized(src["url"])[:max_por_fuente]:
            e["_source_name"] = src["name"]
            e["_category"] = src["category"]
            all_entries.append(e)

    if busqueda:
        q = busqueda.lower()
        all_entries = [e for e in all_entries if q in e["title"].lower() or q in e["summary"].lower()]

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

                    if use_ai and _GEMINI_OK:
                        try:
                            resumen = ai_summary(e["title"], e["summary"], e["link"], strength=ai_strength_key)
                            if resumen:
                                st.caption("Resumen IA: " + resumen)
                        except Exception:
                            st.caption("Resumen IA: (no disponible)")

                    st.markdown(f"[Leer más]({e['link']})")
        st.write("---")

# Nota de estado IA
if use_ai and not _GEMINI_OK:
    st.warning("Has activado IA, pero no encuentro GEMINI_API_KEY en Secrets.")
