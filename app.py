# aura_trends_app.py — Aura Trends + IA + Web Scraping
import time, re, hashlib, json
from html import unescape
from pathlib import Path
from typing import Dict, List, Any, Optional

import streamlit as st
import feedparser
import yaml
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

# -------------------- Config de página --------------------
st.set_page_config(page_title="Aura Trends • RSS + IA + Scraping", layout="wide")
st.title("✨ Aura Trends Dashboard")
st.caption("Moda, música, arte/cultura, gastronomía, lifestyle/lujo y hospitality — RSS + Scraping + IA")

# -------------------- Utilidades --------------------
DEFAULT_THUMB = "https://upload.wikimedia.org/wikipedia/commons/3/3f/Placeholder_view_vector.svg"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119 Safari/537.36"
}

def clean_html(raw_html: str) -> str:
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

def parse_epoch_from_str(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    try:
        dt = dateparser.parse(s)
        if not dt:
            return None
        return int(dt.timestamp())
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
        if hasattr(e, "media_content") and isinstance(e.media_content, list) and e.media_content:
            url = e.media_content[0].get("url")
            if url: return url
        if hasattr(e, "media_thumbnail") and isinstance(e.media_thumbnail, list) and e.media_thumbnail:
            url = e.media_thumbnail[0].get("url")
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

def http_get(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=12)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    return None

# -------------------- Carga de fuentes --------------------
@st.cache_data(ttl=3600)
def load_sources() -> List[Dict[str, str]]:
    p = Path("sources.yaml")
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
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

# -------------------- Scrapers --------------------
@st.cache_data(ttl=10 * 60)
def scrape_gastroeconomy(max_items: int = 20) -> List[Dict[str, Any]]:
    """Scraper simple para https://www.gastroeconomy.com/ (WordPress)."""
    html = http_get("https://www.gastroeconomy.com/")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for art in soup.select("article")[:max_items]:
        # Título y enlace
        a = art.select_one("h2.entry-title a, h3.entry-title a, .entry-title a, h2 a, h3 a")
        if not a or not a.get("href"):
            continue
        title = a.get_text(strip=True)
        link = a["href"]

        # Resumen
        sum_tag = art.select_one(".entry-summary, .post-excerpt, p")
        summary = clean_html(sum_tag.get_text(" ", strip=True)) if sum_tag else ""

        # Imagen
        img_tag = art.find("img")
        img = ""
        if img_tag:
            img = img_tag.get("data-src") or img_tag.get("data-lazy-src") or img_tag.get("src") or ""

        # Fecha
        time_tag = art.find("time")
        dt = time_tag.get("datetime") if time_tag and time_tag.has_attr("datetime") else None
        epoch = parse_epoch_from_str(dt)

        items.append({
            "title": title or "(sin título)",
            "summary": summary,
            "link": link,
            "author": "",
            "epoch": epoch,
            "image": img,
            "feed_title": "Gastroeconomy (scraped)",
        })
    return items

@st.cache_data(ttl=10 * 60)
def scrape_elcomidista(max_items: int = 24) -> List[Dict[str, Any]]:
    """Scraper para https://elcomidista.elpais.com/ (portada)."""
    html = http_get("https://elcomidista.elpais.com/")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    # Buscamos bloques de artículos; selector amplio para aguantar cambios
    for art in soup.select("article, .c-card, .c")[:max_items]:
        h = art.find(["h2", "h3"])
        a = h.find("a") if h else None
        if not a or not a.get("href"):
            continue
        title = a.get_text(strip=True)
        link = a["href"]
        if link.startswith("//"):
            link = "https:" + link
        elif link.startswith("/"):
            link = "https://elcomidista.elpais.com" + link

        # Resumen (si lo hay)
        sum_tag = art.find("p") or art.find("div", class_="c-article-summary")
        summary = clean_html(sum_tag.get_text(" ", strip=True)) if sum_tag else ""

        # Imagen
        img_tag = art.find("img")
        img = ""
        if img_tag:
            img = img_tag.get("data-src") or img_tag.get("data-lazy-src") or img_tag.get("src") or ""

        # Fecha (si hay <time datetime="...">)
        time_tag = art.find("time")
        dt = time_tag.get("datetime") if time_tag and time_tag.has_attr("datetime") else None
        epoch = parse_epoch_from_str(dt)

        items.append({
            "title": title or "(sin título)",
            "summary": summary,
            "link": link,
            "author": "",
            "epoch": epoch,
            "image": img,
            "feed_title": "El Comidista (scraped)",
        })
    return items

SCRAPERS = {
    "gastroeconomy": scrape_gastroeconomy,
    "elcomidista": scrape_elcomidista,
}

def fetch_source_entries(src_url: str) -> List[Dict[str, Any]]:
    """Decide si es RSS normal o una fuente 'scrape:slug'."""
    if src_url.startswith("scrape:"):
        slug = src_url.split(":", 1)[1].strip().lower()
        func = SCRAPERS.get(slug)
        if not func:
            return []
        return func()
    else:
        return fetch_feed_sanitized(src_url)

# -------------------- IA (Gemini) --------------------
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")
_SDK_OK = False
try:
    import google.generativeai as genai
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
        _SDK_OK = True
except Exception:
    _SDK_OK = False

def _hash_key(*parts: str) -> str:
    return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()

def _rest_generate(prompt: str, model: str = "gemini-1.5-flash") -> str:
    if not GEMINI_KEY:
        return ""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, headers={"Content-Type": "application/json"},
                          data=json.dumps(payload), timeout=20)
        if r.status_code != 200:
            return ""
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return ""

@st.cache_data(ttl=7 * 24 * 3600)
def ai_summarize_cached(model: str, key: str, base_text: str) -> str:
    if not GEMINI_KEY:
        return ""
    prompt = (
        "Eres analista de tendencias. Resume en 1–2 frases claras esta noticia para un público "
        "profesional de hospitality y lujo. Devuelve el texto en español, sin emojis, enlaces ni HTML.\n\n"
        f"{base_text}"
    )
    if _SDK_OK:
        try:
            m = genai.GenerativeModel(model)
            resp = m.generate_content(prompt)
            return (resp.text or "").strip()
        except Exception:
            return _rest_generate(prompt, model=model)
    else:
        return _rest_generate(prompt, model=model)

def ai_summary(title: str, summary: str, strength: str = "flash") -> str:
    model = "gemini-1.5-flash" if strength == "flash" else "gemini-1.5-pro"
    base_text = (title + ". " + summary)[:2200]
    key = _hash_key(model, base_text)
    return ai_summarize_cached(model, key, base_text)

# -------------------- Controles UI --------------------
sources = load_sources()
if not sources:
    st.error("No encuentro `sources.yaml` en la raíz del repo. Súbelo con tus fuentes (RSS o scrape:slug).")
    st.stop()

categorias = sorted({s["category"] for s in sources})
st.sidebar.header("Filtros")
sel_cats = st.sidebar.multiselect("Categorías", categorias, default=categorias)
max_por_fuente = st.sidebar.slider("Máximo por fuente", 3, 30, 9, 1)
busqueda = st.sidebar.text_input("Buscar (título/resumen)...", "")
vista = st.sidebar.radio("Vista", ["Por fuente (expanders)", "Mezclado por fecha"])

st.sidebar.divider()
use_ai = st.sidebar.toggle("Usar IA (Gemini) para resumen", value=False)
ai_model_strength = st.sidebar.radio("Modelo", ["Flash (rápido)", "Pro (más preciso)"], index=0)
ai_strength_key = "flash" if ai_model_strength.startswith("Flash") else "pro"

only_on_click = st.sidebar.toggle("Generar resúmenes solo al pulsar", value=True,
                                  help="Ahorra cuota: solo genera cuando pulses el botón.")
gen_now = st.sidebar.button("⚡ Generar resúmenes ahora")

max_ai = st.sidebar.slider("Máx. resúmenes IA por página", 3, 60, 12, 1)

# Botón de refresco integral (limpia TODAS las cachés)
if st.sidebar.button("♻️ Limpiar caché de datos (feeds + scrapers + IA)"):
    load_sources.clear()
    fetch_feed_sanitized.clear()
    scrape_gastroeconomy.clear()
    scrape_elcomidista.clear()
    ai_summarize_cached.clear()
    st.success("Caché limpiada. Pulsa Rerun (arriba) o recarga la página.")

# Estado IA
if use_ai and not GEMINI_KEY:
    st.warning("Has activado IA, pero no encuentro GEMINI_API_KEY en Secrets.")
if use_ai and GEMINI_KEY and not _SDK_OK:
    st.info("Usando Gemini por API REST (SDK no disponible).")

# -------------------- Render --------------------
def maybe_ai_summary(e, ai_counter: List[int]):
    if not (use_ai and GEMINI_KEY):
        return
    should_generate = (not only_on_click) or gen_now
    if not should_generate:
        return
    if ai_counter[0] >= max_ai:
        return
    try:
        resumen = ai_summary(e["title"], e["summary"], strength=ai_strength_key)
        if resumen:
            st.caption("Resumen IA: " + resumen)
            ai_counter[0] += 1
    except Exception:
        st.caption("Resumen IA: (no disponible)")

ai_count = [0]

if vista == "Por fuente (expanders)":
    for cat in sel_cats:
        st.markdown(f"## {cat}")
        cat_sources = [s for s in sources if s["category"] == cat]
        for src in cat_sources:
            with st.expander(f"📡 {src['name']}"):
                entries = fetch_source_entries(src["url"])[:max_por_fuente]
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
                            maybe_ai_summary(e, ai_count)
                            st.markdown(f"[Leer más]({e['link']})")
                st.write("---")
else:
    # Mezclado por fecha
    all_entries = []
    for src in sources:
        if src["category"] not in sel_cats:
            continue
        for e in fetch_source_entries(src["url"])[:max_por_fuente]:
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
                    maybe_ai_summary(e, ai_count)
                    st.markdown(f"[Leer más]({e['link']})")
        st.write("---")
