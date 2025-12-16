import re, html, time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element, SubElement, tostring

HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 25

ARTICLE_RE = re.compile(r"/roditelyam-i-uchenikam/novosti/novosti_\d+\.html$")

def abs_url(base, href):
    if href.startswith("http"):
        return href
    return base.rstrip("/") + href

def fetch(url):
    return requests.get(url, headers=HEADERS, timeout=TIMEOUT).text

def first_text(el):
    return el.get_text(" ", strip=True) if el else ""

def rss_date_now():
    # RFC822-ish, enough for most readers
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

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

def parse_article(article_url):
    html_doc = fetch(article_url)
    soup = BeautifulSoup(html_doc, "html.parser")

    # Часто заголовок в <h1>
    title = first_text(soup.find("h1")) or "Новость"
    # Описание: первые ~300 символов текста статьи
    main = soup.find("article") or soup.find("main") or soup.body
    text = first_text(main)
    desc = (text[:300] + "…") if len(text) > 300 else text

    return {"title": title, "link": article_url, "description": desc, "pubDate": None}

def parse_school_news_list(list_url, per_school=2):
    base = "https://" + list_url.split("/")[2]
    html_doc = fetch(list_url)
    soup = BeautifulSoup(html_doc, "html.parser")

    links = []
    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        if ARTICLE_RE.search(href):
            links.append(abs_url(base, href))

    # уникализируем, берём первые N
    uniq = []
    for u in links:
        if u not in uniq:
            uniq.append(u)

    items = []
    for u in uniq[:per_school]:
        try:
            items.append(parse_article(u))
            time.sleep(0.3)  # чуть мягче к сайтам
        except Exception:
            continue

    return items

def main():
    with open("schools.txt", "r", encoding="utf-8") as f:
        школ = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    all_items = []
    for url in школ:
        try:
            all_items.extend(parse_school_news_list(url, per_school=2))
            time.sleep(0.5)
        except Exception:
            continue

    # сортировки по дате нет (если даты не парсятся); зато ссылки уникальные
    seen = set()
    dedup = []
    for it in all_items:
        if it["link"] not in seen:
            seen.add(it["link"])
            dedup.append(it)

    rss_bytes = make_rss(
        dedup[:300],  # ограничим объём
        out_title="Новости школ Иркутска (агрегатор)",
        out_link="https://github.com/"
    )

    with open("docs/schools.xml", "wb") as f:
        f.write(rss_bytes)

if __name__ == "__main__":
    main()
