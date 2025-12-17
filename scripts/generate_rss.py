def parse_article(article_url, school_name):
    html_doc = fetch(article_url)
    soup = BeautifulSoup(html_doc, "html.parser")

    h1_title = first_text(soup.find("h1")) or "Новость"
    title = f"[{school_name}] {h1_title}"

    # Ищем разумный контейнер вокруг h1 (как было)
    h1 = soup.find("h1")
    container = h1
    for _ in range(10):
        if not container:
            break
        txt = first_text(container)
        if len(txt) > 250:
            break
        container = container.parent

    if not container:
        container = soup.find("main") or soup.body

    # 1) Пытаемся вырезать типовые “не-статья” блоки
    drop_selectors = [
        ".breadcrumb", "nav[aria-label='breadcrumb']", "ol.breadcrumb", "ul.breadcrumb", ".gw-breadcrumbs",
        "header", "footer", "nav", "aside",
        ".bvi-panel", ".bvi-body", ".bvi-open", ".special-version", ".visually-impaired",
    ]
    for sel in drop_selectors:
        for el in container.select(sel):
            el.decompose()

    text = first_text(container)

    # 2) Гарантированно отрезаем всё, что было до заголовка статьи
    pos = text.find(h1_title)
    if pos != -1:
        text = text[pos:]

    # 3) Чтобы не дублировать заголовок в description (он уже в <title>)
    if text.startswith(h1_title):
        text = text[len(h1_title):].lstrip(" \t\r\n-–—:|")

    # Дата
    pub_dt = None
    m = DATE_RE.search(text)
    if m:
        day = int(m.group(1))
        mon = RU_MONTHS.get(m.group(2).lower())
        year = int(m.group(3))
        hour = int(m.group(4))
        minute = int(m.group(5))
        if mon:
            pub_dt = datetime(year, mon, day, hour, minute, tzinfo=LOCAL_TZ)

    LIMIT = 800
    desc = (text[:LIMIT] + "…") if len(text) > LIMIT else text

    return {
        "title": title,
        "link": article_url,
        "description": desc,
        "pubDate": to_rfc822(pub_dt) if pub_dt else None,
        "_dt": pub_dt,
    }
