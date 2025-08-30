
# aura_trends_only.py — Aura Trends • Solo TENDENCIAS (con o sin IA)
import time, re, json, hashlib
from html import unescape
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin

import streamlit as st
import yaml, requests, feedparser
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

# ---------- Config ----------
st.set_page_config(page_title="Aura Trends • Solo Tendencias", layout="wide")
st.title("✨ Aura Trends — Solo TENDENCIAS")
st.caption("Detección y síntesis de tendencias por vertical. Vista enfocada a señales, no a todo el feed.")

DEFAULT_THUMB = "https://upload.wikimedia.org/wikipedia/commons/3/3f/Placeholder_view_vector.svg"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "https://www.google.com/"
}

# ---------- Utils ----------
def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", "", raw_html)
    return unescape(text).strip()

def to_epoch_from_timestruct(ts) -> Optional[int]:
    if not ts:
        return None
    try:
        import time as _t
        return int(_t.mktime(ts))
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
    d = delta // 86400
    return f"📅 hace {d} d"

def http_get(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=15)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    return None

def first_image_from_entry(e) -> str:
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
    return ""

def pick_meta_image(url: str) -> str:
    html = http_get(url)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for sel in ["meta[property='og:image']","meta[name='og:image']","meta[name='twitter:image:src']","meta[name='twitter:image']"]:
        tag = soup.select_one(sel)
        if tag and tag.get("content"):
            return urljoin(url, tag["content"])
    img = soup.select_one("article img, .article img, .post img, figure img")
    if img and img.get("src"):
        return urljoin(url, img.get("src"))
    return ""

# ---------- Load sources ----------
@st.cache_data(ttl=None)
def load_sources() -> List[Dict[str, str]]:
    p = Path("sources.yaml")
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    items = data.get("sources", []) if isinstance(data, dict) else []
    out = []
    for it in items:
        out.append({
            "name": str(it.get("name","")).strip(),
            "url": str(it.get("url","")).strip(),
            "category": str(it.get("category","Otros")).strip() or "Otros",
        })
    return out

@st.cache_data(ttl=15*60)
def fetch_rss(url: str) -> List[Dict[str, Any]]:
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
            "epoch": to_epoch_from_timestruct(ts),
            "image": first_image_from_entry(e) or "",
            "feed_title": feed_title,
        })
    return items

# --- Simple scrapers (opcionales; puedes quitar si no los usas) ---
@st.cache_data(ttl=10*60)
def scrape_gastroeconomy(max_items=24):
    html = http_get("https://www.gastroeconomy.com/")
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    scope = soup.find("main") or soup
    out, seen = [], set()
    for a in scope.select("h2 a, h3 a, h4 a"):
        href = a.get("href") or ""; title = a.get_text(strip=True)
        if not href or not title: continue
        if "/category/" in href or "/tag/" in href or "/author/" in href: continue
        if "/20" not in href and "/19" not in href: continue
        if href in seen: continue
        seen.add(href)
        # meta image por artículo
        img = pick_meta_image(href) or ""
        out.append({"title": title, "summary": "", "link": href, "author":"", "epoch": None, "image": img, "feed_title":"Gastroeconomy (scraped)"})
        if len(out)>=max_items: break
    return out

SCRAPERS = {"gastroeconomy": scrape_gastroeconomy}

def fetch_entries(src_url: str) -> List[Dict[str, Any]]:
    if src_url.startswith("scrape:"):
        slug = src_url.split(":",1)[1].strip().lower()
        func = SCRAPERS.get(slug)
        return func() if func else []
    return fetch_rss(src_url)

# ---------- Trend engine ----------
POS_WORDS = [
    # acción
    "abre","apertura","lanza","presenta","anuncia","estrena","llega","despliega","reabre","reapertura",
    # premios/listas
    "ganador","premio","premios","finalista","estrella michelin","michelin","50 best","ranking","lista",
    # formato/colabo
    "pop-up","residencia","colaboración","capsule","drop","flagship","members","club",
]
NEG_WORDS = ["receta","recetas","cómo hacer","truco","trucos","paso a paso","oferta","descuento","rebajas"]

SOURCE_WEIGHTS = {
    # ajusta a tu gusto
    "Skift": 2.0, "HospitalityNet": 1.8, "WWD": 1.8, "50 Best": 2.0, "MICHELIN": 2.0,
    "Gastroeconomy": 1.6, "Dezeen":1.5, "Wallpaper":1.4, "Hypebeast":1.3, "Highsnobiety":1.3
}

def score_article(a: Dict[str, Any]) -> Dict[str, Any]:
    t = (a.get("title","") + " " + a.get("summary","")).lower()
    score = 0.0; reasons = []
    if any(w in t for w in POS_WORDS):
        score += 2; reasons.append("acción/premio")
    if any(w in t for w in NEG_WORDS):
        score -= 3; reasons.append("genérico/how-to")

    # recency boost
    ep = a.get("epoch")
    if ep:
        age = int(time.time()) - int(ep)
        if age <= 24*3600: score += 3; reasons.append("muy reciente")
        elif age <= 7*24*3600: score += 2; reasons.append("reciente")

    # authority boost
    src = a.get("feed_title") or a.get("_source_name","")
    for k, w in SOURCE_WEIGHTS.items():
        if k.lower() in (src or "").lower():
            score += (w-1); reasons.append(f"autoridad:{k}")
            break

    return {"trend_score": round(score,2), "reasons": reasons}

STOP = set("""a al algo algun alguna algunos algunas ante bajo cabe con contra de del desde donde
el la los las en entre hacia hasta para por segun sin sobre tras un una unos unas y o u e que como 
consejo esto esta este estos estas fue son ser es fue era han hay sus sus su tu tus mi mis lo le les
""".split())

def topic_key(a: Dict[str,Any]) -> str:
    # Clave de tema simple a partir del título
    title = (a.get("title") or "").lower()
    words = [re.sub(r"[^a-záéíóúñ0-9]+","",w) for w in title.split()]
    words = [w for w in words if len(w)>=4 and w not in STOP]
    key = "-".join(words[:4]) or hashlib.md5(title.encode("utf-8")).hexdigest()[:8]
    return key

def aggregate_trends(items: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    buckets: Dict[str, Dict[str,Any]] = {}
    now = int(time.time())
    for a in items:
        sc = score_article(a)
        a["_trend_score"] = sc["trend_score"]
        a["_reasons"] = sc["reasons"]
        k = topic_key(a)
        b = buckets.setdefault(k, {
            "topic": k, "best_item": None, "items":[], "max_score": -999, "sources":set(), "recent":0
        })
        b["items"].append(a)
        srcname = (a.get("feed_title") or a.get("_source_name") or "").strip()
        if srcname: b["sources"].add(srcname)
        if a.get("epoch") and (now - int(a["epoch"]) <= 14*24*3600):
            b["recent"] += 1
        if a["_trend_score"] > b["max_score"]:
            b["max_score"] = a["_trend_score"]
            b["best_item"] = a
    # compute aggregate score
    out = []
    for k, b in buckets.items():
        agg = b["max_score"] + 0.7*len(b["sources"]) + 0.3*b["recent"]
        out.append({
            "topic": k,
            "score": round(agg,2),
            "sources_n": len(b["sources"]),
            "recent_n": b["recent"],
            "best": b["best_item"],
            "items": sorted(b["items"], key=lambda x: x["_trend_score"], reverse=True)[:5]
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out

# ---------- IA opcional ----------
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY","")
_SDK_OK = False
try:
    import google.generativeai as genai
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY); _SDK_OK=True
except Exception:
    _SDK_OK=False

@st.cache_data(ttl=3*24*3600)
def ai_insight(text: str, model="gemini-1.5-flash") -> str:
    if not GEMINI_KEY:
        return ""
    prompt = (
      "Eres analista de tendencias. Resume en 1 frase clara el patrón de tendencia y el 'por qué importa' para hospitality/luxe. "
      "Español, 18-24 palabras, sin emojis ni enlaces.\n\nTexto:\n" + text[:2200]
    )
    try:
        if _SDK_OK:
            m = genai.GenerativeModel(model)
            resp = m.generate_content(prompt)
            return (resp.text or "").strip()
        else:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
            payload = {"contents":[{"parts":[{"text":prompt}]}]}
            r = requests.post(url, headers={"Content-Type":"application/json"}, data=json.dumps(payload), timeout=20)
            if r.status_code!=200: return ""
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return ""

# ---------- UI ----------
sources = load_sources()
if not sources:
    st.error("Sube un sources.yaml con tus fuentes (RSS o scrape:gastroeconomy)."); st.stop()

cats = sorted({s["category"] for s in sources})
sel_cats = st.sidebar.multiselect("Categorías", cats, default=cats)
max_per_src = st.sidebar.slider("Máximo por fuente", 3, 30, 10, 1)
use_ai = st.sidebar.toggle("Añadir insight IA (Gemini)", value=False)
trend_threshold = st.sidebar.slider("Umbral Trend Score (artículo)", -2.0, 8.0, 2.0, 0.5)

if st.sidebar.button("🧹 Limpiar caché"):
    load_sources.clear(); fetch_rss.clear(); scrape_gastroeconomy.clear(); ai_insight.clear()
    st.success("Caché limpia. Pulsa Rerun.")

# Colecta artículos
raw_items: List[Dict[str,Any]] = []
for src in sources:
    if src["category"] not in sel_cats: continue
    for e in (fetch_entries(src["url"])[:max_per_src] or []):
        e["_source_name"] = src["name"]
        e["_category"] = src["category"]
        if not e.get("image"): e["image"] = DEFAULT_THUMB
        raw_items.append(e)

# Filtra por score de artículo
scored = []
for a in raw_items:
    sc = score_article(a)
    if sc["trend_score"] >= trend_threshold:
        a["_trend_score"] = sc["trend_score"]; a["_reasons"] = sc["reasons"]
        scored.append(a)

# Agrega en temas
clusters = aggregate_trends(scored)

st.markdown("## 🔥 Tendencias detectadas")
if not clusters:
    st.info("No hay suficientes señales bajo el umbral actual. Baja el umbral o añade más fuentes.")
else:
    for c in clusters[:30]:
        b = c["best"]
        with st.container(border=True):
            cols = st.columns([1,3])
            with cols[0]:
                st.image(b["image"] or DEFAULT_THUMB, use_container_width=True)
            with cols[1]:
                st.markdown(f"### {b['title']}")
                st.caption(f"{b.get('_category','')} · {b.get('feed_title') or b.get('_source_name','')} · {freshness_label(b.get('epoch'))}")
                if b.get("summary"):
                    st.write(b["summary"][:260] + ("..." if len(b["summary"])>260 else ""))
                st.write(f"**Trend score** (tema): {c['score']} · **Fuentes**: {c['sources_n']} · **Recientes**: {c['recent_n']}")
                st.markdown(f"[Abrir artículo]({b['link']})")

                if use_ai and GEMINI_KEY:
                    txt = (b["title"] + ". " + (b.get("summary") or ""))
                    insight = ai_insight(txt)
                    if insight:
                        st.success("Insight IA: " + insight)

            # Enlaces relacionados
            if len(c["items"])>1:
                with st.expander("Más señales relacionadas"):
                    for x in c["items"][1:]:
                        st.markdown(f"- [{x['title']}]({x['link']}) — {x.get('feed_title') or x.get('_source_name','')} · {freshness_label(x.get('epoch'))}")
