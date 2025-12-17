import re
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element, SubElement, tostring

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 25

# Список новостей (на страницах школ)
ARTICLE_RE = re.compile(r"/roditelyam-i-uchenikam/novosti/novosti_\d+\.html$")
ID_RE = re.compile(r"novosti_(\d+)\.html$")

# Дата на страницах новостей часто встречается как: "11 декабря 2025, 10:28"
DATE_RE = re.compile(r"(\d{1,2})\s+([А-Яа-яёЁ]+)\s+(\d{4}),\s*(\d{1,2}):(\d{2})")
RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

# Иркутск (UTC+8)
LOCAL_TZ = timezone(timedelta(hours=8))


def abs_url(base, href):
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return base.rstrip("/") + href


def fetch(url):
    return requests.get(url, headers=HEADERS, timeout=TIMEOUT).text


def first_text(el):
    return el.get_text(" ", strip=True) if el else ""


def rss_date_now():
    # RFC-822-ish (валидно для RSS)
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def to_rfc822(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def make_rss(items, out_title, out_link):
    rss = Element("rss", version="2.0")
    ch = SubElement(rss, "channel")
    SubElement(ch, "title").text = out_title
    SubElement(ch, "link").text = out_link
    SubElement(ch, "description").text = out_title
    SubElement(ch, "lastBuildDate").text = rss_date_now()

    for it in items:
        item = SubElement(ch, "item")
        SubElement(item, "title").text = it["title"]
        SubElement(item, "link").text = it["link"]
        SubElement(item, "guid").text = it["link"]
        SubElement(item, "pubDate").text = it.get("pubDate") or rss_date_now()
        SubElement(item, "description").text = it.get("description") or ""

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(rss, encoding="utf-8")


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

    # Пытаемся вырезать типовые “не-статья” блоки
    drop_selectors = [
        ".breadcrumb", "nav[aria-label='breadcrumb']", "ol.breadcrumb", "ul.breadcrumb", ".gw-breadcrumbs",
        "header", "footer", "nav", "aside",
        ".bvi-panel", ".bvi-body", ".bvi-open", ".special-version", ".visually-impaired",
    ]
    for sel in drop_selectors:
        for el in container.select(sel):
            el.decompose()

    text = first_text(container)

    # Гарантированно отрезаем всё, что было до заголовка статьи
    pos = text.find(h1_title)
    if pos != -1:
        text = text[pos:]

    # Чтобы не дублировать заголовок в description (он уже в <title>)
    if text.startswith(h1_title):
        text = text[len(h1_title):].lstrip(" \t\r\n-–—:|")

    # Парсим дату публикации
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
        "_dt": pub_dt,  # служебное поле для сортировки
    }


def parse_school_news_list(list_url, school_name, per_school=2):
    host = list_url.split("/")[2]
    base = "https://" + host

    html_doc = fetch(list_url)
    soup = BeautifulSoup(html_doc, "html.parser")

    links = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if ARTICLE_RE.search(href):
            links.append(abs_url(base, href))

    # уникализируем
    uniq = []
    for u in links:
        if u and u not in uniq:
            uniq.append(u)

    # новые -> старые по номеру novosti_XXX
    uniq.sort(key=lambda u: int(ID_RE.search(u).group(1)) if ID_RE.search(u) else 0, reverse=True)

    items = []
    for u in uniq[:per_school]:
        try:
            items.append(parse_article(u, school_name=school_name))
            time.sleep(0.3)
        except Exception:
            continue

    return items


def main():
    # Формат schools.txt:
    # Лицей №1|https://irk-lic1.gosuslugi.ru/roditelyam-i-uchenikam/novosti/
    schools = []
    with open("schools.txt", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                # на всякий случай: если попалась строка "только URL"
                schools.append((line, line))
                continue
            name, url = line.split("|", 1)
            schools.append((name.strip(), url.strip()))

    all_items = []
    for school_name, url in schools:
        try:
            all_items.extend(parse_school_news_list(url, school_name=school_name, per_school=2))
            time.sleep(0.5)
        except Exception:
            continue

    # дедуп по ссылке
    seen = set()
    dedup = []
    for it in all_items:
        if it["link"] not in seen:
            seen.add(it["link"])
            dedup.append(it)

    # сортировка: новые сверху
    min_dt = datetime.min.replace(tzinfo=timezone.utc)
    dedup.sort(key=lambda it: (it.get("_dt") or min_dt).astimezone(timezone.utc), reverse=True)

    # убираем служебное поле
    for it in dedup:
        it.pop("_dt", None)

    rss_bytes = make_rss(
        dedup[:300],
        out_title="Новости школ Иркутска",
        out_link="https://eduirk.ru/"
    )

    with open("docs/schools.xml", "wb") as f:
        f.write(rss_bytes)


if __name__ == "__main__":
    main()
