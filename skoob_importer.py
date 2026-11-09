import csv
import io
import json
import re
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

SKOOB_STATUS_MAP = {
    1: "concluido",      # Lido
    2: "em_andamento",   # Lendo
    3: "quero",          # Vou ler / Quero ler
    4: "em_andamento",   # Relendo
    5: "abandonado",     # Abandonei
}


def normalize_rating(val: Any) -> float:
    if val is None or val == "":
        return 0.0
    try:
        num = float(str(val).replace(",", ".").strip())
        if num > 5.0 and num <= 10.0:
            num = num / 2.0
        elif num > 10.0 and num <= 100.0:
            num = num / 20.0
        return max(0.0, min(5.0, round(num * 2) / 2))
    except Exception:
        return 0.0


def normalize_status(raw: Any) -> str:
    if raw is None:
        return "concluido"
    if isinstance(raw, int) or str(raw).isdigit():
        return SKOOB_STATUS_MAP.get(int(raw), "concluido")
    s = str(raw).strip().lower()
    if any(k in s for k in ["lendo", "assistindo", "reading", "watching", "relendo", "andamento"]):
        return "em_andamento"
    if any(k in s for k in ["quero", "vou ler", "to-read", "want", "desejado", "lista"]):
        return "quero"
    if any(k in s for k in ["abandon", "dropped", "parei"]):
        return "abandonado"
    return "concluido"


def extract_skoob_user_id(url_or_id: str) -> Optional[str]:
    text = url_or_id.strip()
    if text.isdigit():
        return text
    # Padrões comuns de URL de usuário/estante no Skoob:
    # /usuario/123456-nome  |  /estante/livros/todos/123456  |  /v1/bookcase/books/123456/...
    patterns = [
        r"/usuario/(\d+)",
        r"/estante/(?:livros|resenhas)/(?:todos|\d+)/(\d+)",
        r"/estante/resenhas/(\d+)",
        r"/bookcase/books/(\d+)",
        r"skoob\.com\.br/u/(\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


def parse_skoob_bookcase_json(data: Any) -> List[Dict[str, Any]]:
    """Converte o JSON da API interna do Skoob (/v1/bookcase/books/...) em lista de itens."""
    items = []
    response_list = []
    if isinstance(data, dict):
        response_list = data.get("response") or data.get("books") or data.get("items") or []
    elif isinstance(data, list):
        response_list = data

    for entry in response_list:
        if not isinstance(entry, dict):
            continue
        edicao = entry.get("edicao") if isinstance(entry.get("edicao"), dict) else entry
        title = (
            edicao.get("titulo")
            or edicao.get("nome_portugues")
            or entry.get("title")
            or entry.get("work_title")
            or ""
        ).strip()
        if not title:
            continue

        author = (
            edicao.get("autor")
            or entry.get("author")
            or entry.get("work_creator")
            or "Autor desconhecido"
        ).strip()
        cover = (
            edicao.get("capa_grande")
            or edicao.get("capa_media")
            or edicao.get("capa_pequena")
            or entry.get("cover_url")
            or entry.get("capa")
            or ""
        ).strip()
        year = str(edicao.get("ano") or entry.get("year") or entry.get("work_year") or "").strip()
        genre = str(edicao.get("genero") or entry.get("genre") or "").strip()
        rating = normalize_rating(entry.get("ranking") or entry.get("rating") or entry.get("nota") or 0)
        status = normalize_status(entry.get("tipo") or entry.get("status") or 1)
        is_fav = bool(entry.get("favorito") or entry.get("is_favorite"))
        finished_at = str(entry.get("dt_leitura") or entry.get("dt_resenha") or entry.get("finished_at") or "").strip()

        # Texto da resenha se presente no objeto
        resenha_obj = entry.get("resenha")
        review_text = ""
        review_title = ""
        has_spoiler = False
        if isinstance(resenha_obj, dict):
            review_text = str(resenha_obj.get("resenha") or resenha_obj.get("texto") or "").strip()
            review_title = str(resenha_obj.get("titulo") or "").strip()
            has_spoiler = bool(resenha_obj.get("spoiler"))
        elif isinstance(resenha_obj, str):
            review_text = resenha_obj.strip()
        else:
            review_text = str(entry.get("content") or entry.get("review") or entry.get("comentario") or "").strip()
            review_title = str(entry.get("review_title") or entry.get("titulo_resenha") or "").strip()

        book_id = str(edicao.get("livro_id") or edicao.get("id") or entry.get("id") or "").strip()
        url = edicao.get("url") or entry.get("skoob_url") or ""
        if url and url.startswith("/"):
            url = f"https://www.skoob.com.br{url}"
        elif book_id and not url:
            url = f"https://www.skoob.com.br/livro/{book_id}"

        items.append(
            {
                "category": str(entry.get("category") or "livro"),
                "work_title": title,
                "work_creator": author,
                "work_genre": genre,
                "work_year": year,
                "cover_url": cover,
                "rating": rating if rating > 0 else 5.0,
                "status": status,
                "title": review_title,
                "content": review_text or f"Avaliação importada do Skoob ({rating if rating > 0 else 5.0:g} ★).",
                "has_spoiler": has_spoiler,
                "is_favorite": is_fav,
                "finished_at": finished_at[:10] if finished_at else "",
                "skoob_book_id": book_id or f"skoob-{title[:40].lower()}",
                "skoob_url": url,
            }
        )
    return items


def parse_skoob_html(html: str, source_url: str = "") -> List[Dict[str, Any]]:
    """Extrai uma ou várias resenhas/livros de uma página HTML do Skoob."""
    soup = BeautifulSoup(html, "html.parser")
    items: List[Dict[str, Any]] = []

    # 1. Verifica se é uma página de lista de resenhas ou estante com múltiplos cards
    review_cards = soup.select(
        ".resenha-lista, .box-resenha, .curva-resenha, div[id^='resenha'], .clivro, .livro-estante"
    )
    if len(review_cards) > 1:
        for card in review_cards:
            title_el = card.select_one("h3, h4, .titulo, a[href*='/livro/'], strong")
            title = title_el.get_text(" ", strip=True) if title_el else ""
            if not title or len(title) < 2:
                continue
            author_el = card.select_one(".autor, .subtitulo, span.cinza, i")
            author = author_el.get_text(" ", strip=True) if author_el else ""
            img_el = card.select_one("img")
            cover = (img_el.get("src") or img_el.get("data-src") or "") if img_el else ""
            text_el = card.select_one(".texto-resenha, .resenha-texto, p, .descricao")
            content = text_el.get_text("\n", strip=True) if text_el else ""

            # Tenta extrair estrelas
            stars = 5.0
            star_el = card.select_one("[class*='star'], [title*='estrela'], [alt*='estrela']")
            if star_el:
                m = re.search(r"(\d+(?:[.,]\d+)?)", (star_el.get("title") or star_el.get("alt") or star_el.get_text()))
                if m:
                    stars = normalize_rating(m.group(1))

            link_el = card.select_one("a[href*='/livro/'], a[href*='/resenha']")
            link = link_el.get("href", "") if link_el else source_url
            if link.startswith("/"):
                link = f"https://www.skoob.com.br{link}"

            items.append(
                {
                    "category": "livro",
                    "work_title": title[:250],
                    "work_creator": author[:180],
                    "work_genre": "",
                    "work_year": "",
                    "cover_url": cover,
                    "rating": stars if stars > 0 else 5.0,
                    "status": "concluido",
                    "title": "",
                    "content": content or "Avaliação importada do Skoob.",
                    "has_spoiler": False,
                    "is_favorite": False,
                    "finished_at": "",
                    "skoob_book_id": f"skoob-{title[:40].lower()}",
                    "skoob_url": link,
                }
            )
        if items:
            return items

    # 2. Caso seja uma página de resenha única ou livro único no Skoob
    og_title = soup.find("meta", property="og:title")
    og_image = soup.find("meta", property="og:image")
    og_desc = soup.find("meta", property="og:description")

    raw_title = (
        (og_title.get("content") if og_title else None)
        or (soup.title.get_text(strip=True) if soup.title else "")
    )
    # Limpa sufixos comuns do Skoob ("Resenha de ... - Skoob", "... - Skoob")
    clean_title = re.sub(r"\s*[-|]\s*Skoob.*$", "", raw_title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r"^Resenhas?\s+de\s+", "", clean_title, flags=re.IGNORECASE).strip()

    # Tenta achar título do livro especificamente na página
    book_h1 = soup.select_one(
        "#pg-livro-titulo h1, .livro-titulo, h1[itemprop='name'], .detalhes-livro h1, h1"
    )
    if book_h1 and book_h1.get_text(strip=True):
        clean_title = book_h1.get_text(" ", strip=True)

    author = ""
    author_el = soup.select_one(
        "a[href*='/autor/'], [itemprop='author'], .livro-autor, #pg-livro-titulo h2"
    )
    if author_el:
        author = author_el.get_text(" ", strip=True)

    cover_url = og_image.get("content", "") if og_image else ""
    if not cover_url:
        cover_img = soup.select_one("img[src*='skoob'], .capa-livro img, #capa img")
        if cover_img:
            cover_url = cover_img.get("src", "")

    # Corpo da resenha
    review_body_el = soup.select_one(
        "[itemprop='reviewBody'], .texto-resenha, #resenha, .resenha-conteudo, .curva-resenha p, article"
    )
    review_content = ""
    if review_body_el:
        review_content = review_body_el.get_text("\n", strip=True)
    elif og_desc and og_desc.get("content"):
        review_content = og_desc.get("content").strip()

    rating = 5.0
    rating_el = soup.select_one("[itemprop='ratingValue'], .rating, .nota, star-rating")
    if rating_el:
        val = rating_el.get("content") or rating_el.get("rating") or rating_el.get_text(strip=True)
        parsed = normalize_rating(val)
        if parsed > 0:
            rating = parsed

    if clean_title:
        items.append(
            {
                "category": "livro",
                "work_title": clean_title[:250],
                "work_creator": author[:180],
                "work_genre": "",
                "work_year": "",
                "cover_url": cover_url,
                "rating": rating,
                "status": "concluido",
                "title": "",
                "content": review_content or "Resenha importada do Skoob.",
                "has_spoiler": False,
                "is_favorite": False,
                "finished_at": "",
                "skoob_book_id": f"skoob-{clean_title[:40].lower()}",
                "skoob_url": source_url,
            }
        )
    return items


async def fetch_skoob_from_url_or_id(url_or_id: str, max_items: int = 100) -> List[Dict[str, Any]]:
    """
    Busca dados do Skoob a partir de:
    - ID numérico do usuário (ex: '123456')
    - URL do perfil ou estante do Skoob (ex: 'https://www.skoob.com.br/usuario/123456-...')
    - URL direta de uma resenha ou livro no Skoob
    """
    raw = url_or_id.strip()
    user_id = extract_skoob_user_id(raw)

    async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True, timeout=15.0) as client:
        # 1. Se detectou ID de usuário, tenta primeiro o endpoint JSON da estante do Skoob
        if user_id and ("/resenha/" not in raw):
            collected: List[Dict[str, Any]] = []
            page = 1
            limit = min(50, max_items)
            while len(collected) < max_items and page <= 10:
                api_url = f"https://www.skoob.com.br/v1/bookcase/books/{user_id}/shelf_id:0/page:{page}/limit:{limit}/"
                try:
                    resp = await client.get(api_url)
                    if resp.status_code == 200:
                        data = resp.json()
                        batch = parse_skoob_bookcase_json(data)
                        if not batch:
                            break
                        collected.extend(batch)
                        paging = data.get("paging", {}) if isinstance(data, dict) else {}
                        if not paging.get("next_page") and len(batch) < limit:
                            break
                        page += 1
                    else:
                        break
                except Exception:
                    break

            if collected:
                return collected[:max_items]

            # Fallback HTML da página de resenhas do usuário
            try:
                resenhas_url = f"https://www.skoob.com.br/estante/resenhas/{user_id}"
                resp = await client.get(resenhas_url)
                if resp.status_code == 200:
                    parsed = parse_skoob_html(resp.text, resenhas_url)
                    if parsed:
                        return parsed[:max_items]
            except Exception:
                pass

        # 2. Se for uma URL completa (de resenha, livro ou perfil)
        target_url = raw if raw.startswith("http") else f"https://www.skoob.com.br/usuario/{raw}"
        resp = await client.get(target_url)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type or resp.text.strip().startswith("{"):
            try:
                return parse_skoob_bookcase_json(resp.json())[:max_items]
            except Exception:
                pass

        # Se a página do perfil tiver link com o ID do usuário, tenta extrair o ID e buscar a estante JSON
        if not user_id:
            found_id = extract_skoob_user_id(str(resp.url)) or extract_skoob_user_id(resp.text[:25000])
            if found_id and "/livro/" not in target_url and "/resenha/" not in target_url:
                try:
                    api_url = f"https://www.skoob.com.br/v1/bookcase/books/{found_id}/shelf_id:0/page:1/limit:{min(50, max_items)}/"
                    api_resp = await client.get(api_url)
                    if api_resp.status_code == 200:
                        batch = parse_skoob_bookcase_json(api_resp.json())
                        if batch:
                            return batch[:max_items]
                except Exception:
                    pass

        return parse_skoob_html(resp.text, str(resp.url))[:max_items]


def parse_uploaded_file(filename: str, raw_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Suporta importação de histórico completo ou avaliações via arquivo:
    - CSV (exportações do Skoob, Goodreads, planilhas pessoais)
    - JSON (backup da API do Skoob `/v1/bookcase/books/...` ou array de objetos)
    - HTML (página de estante ou resenhas do Skoob salva pelo navegador)
    """
    text = ""
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    lower_name = (filename or "").lower()
    stripped = text.strip()

    # 1. JSON
    if lower_name.endswith(".json") or stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(stripped)
            return parse_skoob_bookcase_json(data)
        except Exception:
            pass

    # 2. HTML
    if lower_name.endswith((".html", ".htm")) or "<html" in stripped[:500].lower() or "<!doctype html" in stripped[:500].lower():
        return parse_skoob_html(stripped)

    # 3. CSV / TSV
    items: List[Dict[str, Any]] = []
    # Detecta delimitador (; ou , ou \t)
    first_line = stripped.splitlines()[0] if stripped.splitlines() else ""
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    if first_line.count("\t") > max(first_line.count(";"), first_line.count(",")):
        delimiter = "\t"

    reader = csv.DictReader(io.StringIO(stripped), delimiter=delimiter)
    for row in reader:
        if not row:
            continue
        # Normaliza chaves do CSV para minúsculas sem acento básico
        norm = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in row.items()
            if k is not None
        }

        title = (
            norm.get("titulo")
            or norm.get("título")
            or norm.get("title")
            or norm.get("livro")
            or norm.get("obra")
            or norm.get("nome")
            or ""
        )
        if not title:
            continue

        author = (
            norm.get("autor")
            or norm.get("author")
            or norm.get("autora")
            or norm.get("diretor")
            or norm.get("criador")
            or ""
        )
        genre = norm.get("genero") or norm.get("gênero") or norm.get("genre") or ""
        year = norm.get("ano") or norm.get("year") or norm.get("year published") or ""
        cover = norm.get("capa") or norm.get("cover") or norm.get("cover_url") or norm.get("imagem") or ""
        raw_rating = (
            norm.get("nota")
            or norm.get("avaliacao")
            or norm.get("avaliação")
            or norm.get("ranking")
            or norm.get("rating")
            or norm.get("my rating")
            or "5"
        )
        rating = normalize_rating(raw_rating)
        status = normalize_status(
            norm.get("status")
            or norm.get("estante")
            or norm.get("exclusive shelf")
            or norm.get("bookshelves")
            or "concluido"
        )
        review_title = norm.get("titulo_resenha") or norm.get("título da resenha") or ""
        content = (
            norm.get("resenha")
            or norm.get("review")
            or norm.get("my review")
            or norm.get("comentario")
            or norm.get("comentário")
            or norm.get("opiniao")
            or norm.get("opinião")
            or ""
        )
        finished_at = (
            norm.get("data_leitura")
            or norm.get("data")
            or norm.get("date read")
            or norm.get("finished_at")
            or ""
        )
        cat_raw = (norm.get("categoria") or norm.get("category") or norm.get("tipo") or "livro").lower()
        category = "livro"
        if "filme" in cat_raw or "movie" in cat_raw:
            category = "filme"
        elif "serie" in cat_raw or "série" in cat_raw or "tv" in cat_raw:
            category = "serie"

        skoob_id = norm.get("id") or norm.get("book id") or norm.get("skoob_id") or f"csv-{title[:40].lower()}"
        skoob_url = norm.get("url") or norm.get("link") or norm.get("skoob_url") or ""

        items.append(
            {
                "category": category,
                "work_title": title[:250],
                "work_creator": author[:180],
                "work_genre": genre[:100],
                "work_year": year[:20],
                "cover_url": cover,
                "rating": rating if rating > 0 else 5.0,
                "status": status,
                "title": review_title[:250],
                "content": content or f"Avaliação importada ({rating if rating > 0 else 5.0:g} ★).",
                "has_spoiler": norm.get("spoiler", "").lower() in ("sim", "true", "1", "yes"),
                "is_favorite": norm.get("favorito", "").lower() in ("sim", "true", "1", "yes"),
                "finished_at": finished_at[:20],
                "skoob_book_id": str(skoob_id),
                "skoob_url": skoob_url,
            }
        )

    return items


async def search_media_catalog(query: str, category: str = "livro") -> List[Dict[str, Any]]:
    """
    Busca automática de capa, autor/diretor e ano para facilitar o preenchimento da resenha!
    - Livros: Google Books API (pública, sem chave) + OpenLibrary fallback
    - Filmes e Séries: iTunes Search API / TVMaze API (públicas, sem chave)
    """
    q = query.strip()
    if not q:
        return []

    results: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=8.0) as client:
        if category == "livro":
            # Tenta Google Books API em Português
            try:
                resp = await client.get(
                    "https://www.googleapis.com/books/v1/volumes",
                    params={"q": q, "maxResults": 6, "langRestrict": "pt"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("items", []):
                        info = item.get("volumeInfo", {})
                        title = info.get("title", "")
                        authors = ", ".join(info.get("authors", []))
                        categories = ", ".join(info.get("categories", []))
                        pub_date = info.get("publishedDate", "")[:4]
                        images = info.get("imageLinks", {})
                        cover = (
                            images.get("thumbnail")
                            or images.get("smallThumbnail")
                            or ""
                        ).replace("http://", "https://")
                        if title:
                            results.append(
                                {
                                    "category": "livro",
                                    "work_title": title,
                                    "work_creator": authors,
                                    "work_genre": categories,
                                    "work_year": pub_date,
                                    "cover_url": cover,
                                }
                            )
            except Exception:
                pass

            if not results:
                # Fallback OpenLibrary
                try:
                    resp = await client.get(
                        "https://openlibrary.org/search.json",
                        params={"q": q, "limit": 6},
                    )
                    if resp.status_code == 200:
                        for doc in resp.json().get("docs", [])[:6]:
                            cover_i = doc.get("cover_i")
                            cover = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg" if cover_i else ""
                            results.append(
                                {
                                    "category": "livro",
                                    "work_title": doc.get("title", ""),
                                    "work_creator": ", ".join(doc.get("author_name", [])[:2]),
                                    "work_genre": "",
                                    "work_year": str(doc.get("first_publish_year", "")),
                                    "cover_url": cover,
                                }
                            )
                except Exception:
                    pass

        elif category == "filme":
            try:
                resp = await client.get(
                    "https://itunes.apple.com/search",
                    params={"term": q, "media": "movie", "country": "BR", "limit": 6},
                )
                if resp.status_code == 200:
                    for item in resp.json().get("results", []):
                        cover = (item.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
                        results.append(
                            {
                                "category": "filme",
                                "work_title": item.get("trackName", ""),
                                "work_creator": item.get("artistName", ""),
                                "work_genre": item.get("primaryGenreName", ""),
                                "work_year": (item.get("releaseDate") or "")[:4],
                                "cover_url": cover,
                            }
                        )
            except Exception:
                pass

        elif category == "serie":
            try:
                resp = await client.get(
                    "https://api.tvmaze.com/search/shows",
                    params={"q": q},
                )
                if resp.status_code == 200:
                    for entry in resp.json()[:6]:
                        show = entry.get("show", {})
                        img = show.get("image") or {}
                        network = (show.get("network") or show.get("webChannel") or {}).get("name", "")
                        results.append(
                            {
                                "category": "serie",
                                "work_title": show.get("name", ""),
                                "work_creator": network,
                                "work_genre": ", ".join(show.get("genres", [])[:2]),
                                "work_year": (show.get("premiered") or "")[:4],
                                "cover_url": img.get("medium") or img.get("original") or "",
                            }
                        )
            except Exception:
                pass

    return results
