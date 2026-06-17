# -*- coding: utf-8 -*-
"""
크롬(Playwright)으로 직접 검색해서 결과 링크/제목/요약문을 수집한다.
API 키 없이 동작. 네이버 + 구글 검색을 사용.

네이버는 CSS 클래스명이 매 빌드마다 랜덤이라, 안정적인 'URL 패턴'으로 결과를 거른다.
"""
import re
import time
import urllib.parse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# 소스 정의: 검색 URL + 결과로 인정할 링크의 URL 패턴
SOURCES = {
    "naver_blog": {
        "name": "네이버 블로그",
        "url": "https://search.naver.com/search.naver?where=blog&query={q}",
        "pattern": r"^https?://blog\.naver\.com/[\w\-]+/\d+",
    },
    "naver_cafe": {
        "name": "네이버 카페",
        "url": "https://search.naver.com/search.naver?where=article&query={q}",
        "pattern": r"^https?://cafe\.naver\.com/[\w\-]+/\d+",
    },
    "naver_news": {
        "name": "네이버 뉴스",
        "url": "https://search.naver.com/search.naver?where=news&query={q}",
        "pattern": r"^https?://n\.news\.naver\.com/.*article|^https?://[\w.]+/.*/article/\d+",
    },
    "naver_shop": {
        "name": "네이버 쇼핑",
        "url": "https://search.naver.com/search.naver?where=shop&query={q}",
        "pattern": r"smartstore\.naver\.com|brand\.naver\.com|shopping\.naver\.com/catalog",
    },
    "daum": {
        "name": "다음/웹문서",
        "url": "https://search.daum.net/search?w=tot&q={q}",
        "pattern": None,  # 다음은 외부링크 일반 추출로 처리
    },
    "dcinside": {
        "name": "디시인사이드",
        "url": "https://search.dcinside.com/combine/q/{q}",
        "pattern": None,  # 디시는 전용 파서 사용
    },
}

# 결과로 인정하지 않는 잡음 도메인 (광고/검색엔진 내부)
NOISE = ("ader.naver.com", "google.com", "search.naver.com", "search.daum.net",
         "daum.net", "kakao.com", "accounts.", "nid.naver.com", "help.naver.com")


def _clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


# 제목으로 부적절한 일반 UI 문구 / 사이트 라벨
GENERIC_TITLES = {"네이버뉴스", "네이버뉴스 키워드", "Keep에 저장", "관련뉴스", "동영상"}


def _bad_title(title):
    """사이트 라벨(blog.naver.com xxx)이나 일반 UI 문구면 True."""
    if not title or title in GENERIC_TITLES:
        return True
    first = title.split(" ", 1)[0]
    if "." in first and "/" not in first:   # 첫 토큰이 도메인처럼 보이면 결과 제목이 아님
        return True
    return False


def _norm(url):
    """추적 파라미터/앵커 제거해 중복 판정용으로 정규화."""
    return url.split("#")[0].split("?")[0]


from datetime import datetime, timedelta


def extract_date(text):
    """텍스트에서 발행 시점을 찾아 'YYYY-MM' 문자열로 반환(없으면 '')."""
    if not text:
        return ""
    now = datetime.now()
    # 절대 날짜: 2026.04.14 / 2026-04-14 / 2026.4.14.
    m = re.search(r"(20\d{2})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    # 상대 날짜
    if "오늘" in text or "방금" in text:
        return now.strftime("%Y-%m")
    if "어제" in text or "그제" in text:
        return (now - timedelta(days=1)).strftime("%Y-%m")
    m = re.search(r"(\d+)\s*(분|시간)\s*전", text)
    if m:
        return now.strftime("%Y-%m")
    m = re.search(r"(\d+)\s*일\s*전", text)
    if m:
        return (now - timedelta(days=int(m.group(1)))).strftime("%Y-%m")
    m = re.search(r"(\d+)\s*주\s*전", text)
    if m:
        return (now - timedelta(weeks=int(m.group(1)))).strftime("%Y-%m")
    m = re.search(r"(\d+)\s*(개월|달)\s*전", text)
    if m:
        months = int(m.group(1))
        y, mo = now.year, now.month - months
        while mo <= 0:
            mo += 12
            y -= 1
        return f"{y}-{mo:02d}"
    return ""


def _container_text(a, depth=4):
    """앵커의 상위 컨테이너에서 미리보기 텍스트를 추출."""
    node = a
    for _ in range(depth):
        if node.parent is None:
            break
        node = node.parent
        t = _clean(node.get_text(" "))
        if len(t) > 40:
            return t[:300]
    return _clean(a.get_text(" "))[:300]


def _date_near(a, depth=8):
    """앵커 주변(상위 컨테이너)에서 날짜를 찾아 'YYYY-MM' 반환."""
    node = a
    for _ in range(depth):
        if node.parent is None:
            break
        node = node.parent
        d = extract_date(_clean(node.get_text(" ")))
        if d:
            return d
    return ""


def _parse_naver(html, source_key, limit):
    pat = re.compile(SOURCES[source_key]["pattern"])
    soup = BeautifulSoup(html, "lxml")
    by_url = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not pat.search(href):
            continue
        key = _norm(href)
        title = _clean(a.get_text(" "))
        rec = by_url.get(key)
        if rec is None:
            by_url[key] = {"url": href, "title": title, "anchor": a}
        elif len(title) > len(rec["title"]):
            rec["title"] = title  # 같은 글의 여러 링크 중 제목이 가장 긴 것 선택
    items = []
    for rec in by_url.values():
        if _bad_title(rec["title"]):
            continue
        snip = _container_text(rec["anchor"])
        items.append({
            "source": SOURCES[source_key]["name"],
            "title": rec["title"][:120],
            "url": rec["url"],
            "snippet": snip,
            "date": extract_date(snip) or _date_near(rec["anchor"]),
        })
        if len(items) >= limit:
            break
    return items


def _parse_dc(html, limit):
    """디시인사이드 통합검색 결과 파싱 (a.tit_txt 제목 + p.link_txt 미리보기)."""
    soup = BeautifulSoup(html, "lxml")
    items = []
    seen = set()
    for a in soup.select("a.tit_txt"):
        href = a.get("href", "")
        if not href.startswith("http"):
            continue
        key = _norm(href)
        if key in seen:
            continue
        seen.add(key)
        # 미리보기와 날짜
        li = a.find_parent("li")
        snip = _clean(li.get_text(" "))[:300] if li else _clean(a.get_text(" "))
        items.append({
            "source": SOURCES["dcinside"]["name"],
            "title": _clean(a.get_text(" "))[:120],
            "url": href,
            "snippet": snip,
            "date": extract_date(snip),
        })
        if len(items) >= limit:
            break
    return items


def _parse_daum(html, limit):
    """다음 통합검색: 외부 사이트(블로그·티스토리·커뮤니티 등) 링크를 일반 추출."""
    soup = BeautifulSoup(html, "lxml")
    by_url = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            continue
        if any(n in href for n in NOISE):
            continue
        title = _clean(a.get_text(" "))
        if len(title) < 12 or _bad_title(title):
            continue
        key = _norm(href)
        rec = by_url.get(key)
        if rec is None:
            by_url[key] = {"url": href, "title": title, "anchor": a}
        elif len(title) > len(rec["title"]):
            rec["title"] = title
    items = []
    for rec in by_url.values():
        snip = _container_text(rec["anchor"])
        items.append({
            "source": SOURCES["daum"]["name"],
            "title": rec["title"][:120],
            "url": rec["url"],
            "snippet": snip,
            "date": extract_date(snip) or _date_near(rec["anchor"]),
        })
        if len(items) >= limit:
            break
    return items


def search(queries, source_keys, per_source=8, headless=True):
    """queries 검색어들을 source_keys 소스에서 검색해 중복 제거된 결과 리스트 반환."""
    results = []
    seen_urls = set()
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=headless)
        except Exception:
            browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            locale="ko-KR",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"),
        )
        page = ctx.new_page()
        for q in queries:
            eq = urllib.parse.quote(q)
            for sk in source_keys:
                url = SOURCES[sk]["url"].format(q=eq)
                try:
                    wait = "networkidle" if sk == "daum" else "domcontentloaded"
                    page.goto(url, timeout=20000, wait_until=wait)
                    time.sleep(1.5)  # 동적 로딩 대기
                    html = page.content()
                    if sk == "daum":
                        found = _parse_daum(html, per_source)
                    elif sk == "dcinside":
                        found = _parse_dc(html, per_source)
                    else:
                        found = _parse_naver(html, sk, per_source)
                    for it in found:
                        nu = _norm(it["url"])
                        if nu in seen_urls:
                            continue
                        seen_urls.add(nu)
                        it["query"] = q
                        results.append(it)
                except Exception as e:
                    print(f"[수집실패] {sk} / {q}: {e}")
        browser.close()
    return results


def fetch_page_text(url, timeout=15000):
    """요약용으로 페이지 본문 텍스트를 가져온다."""
    text = ""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_context(locale="ko-KR").new_page()
        try:
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            time.sleep(0.8)
            soup = BeautifulSoup(page.content(), "lxml")
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            text = _clean(soup.get_text(" "))[:4000]
        except Exception as e:
            print(f"[본문실패] {url}: {e}")
        browser.close()
    return text


def _page_title_text(page, url, timeout=15000):
    """열린 페이지로 url을 방문해 (제목, 본문) 반환. 리다이렉트/로드오류에 강건."""
    target = url
    # 네이버 블로그는 본문이 iframe → 모바일판이 inline이라 수집이 쉽다
    m = re.search(r"blog\.naver\.com/([\w\-]+)/(\d+)", url)
    if m:
        target = f"https://m.blog.naver.com/{m.group(1)}/{m.group(2)}"
    try:
        page.goto(target, timeout=timeout, wait_until="domcontentloaded")
    except Exception:
        pass  # 리다이렉트로 중단돼도 일단 현재 내용을 읽는다
    time.sleep(1.2)
    try:
        html = page.content()
    except Exception:
        html = ""
    soup = BeautifulSoup(html, "lxml")
    title = _clean(soup.title.get_text()) if soup.title else url
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    body = _clean(soup.get_text(" "))
    return title[:120], body


def fetch_custom(urls, headless=True):
    """사용자가 직접 넣은 링크들을 방문해 분석용 결과 항목으로 변환."""
    items = []
    if not urls:
        return items
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=headless)
        except Exception:
            browser = p.chromium.launch(headless=headless)
        page = browser.new_context(locale="ko-KR").new_page()
        for url in urls:
            url = url.strip()
            if not url.startswith("http"):
                continue
            try:
                title, body = _page_title_text(page, url)
                items.append({
                    "source": "직접 추가",
                    "title": title,
                    "url": url,
                    "snippet": body[:300],
                    "fulltext": body[:6000],   # 본문 요약용
                    "date": extract_date(body[:500]),
                    "query": "(직접 추가한 링크)",
                })
            except Exception as e:
                print(f"[직접링크 실패] {url}: {e}")
        browser.close()
    return items


def fetch_fulltext_many(urls, headless=True):
    """여러 URL의 본문을 한 브라우저로 가져와 {url: text} 반환 (깊은 요약용)."""
    out = {}
    if not urls:
        return out
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=headless)
        except Exception:
            browser = p.chromium.launch(headless=headless)
        page = browser.new_context(locale="ko-KR").new_page()
        for url in urls:
            try:
                _, body = _page_title_text(page, url)
                out[url] = body[:6000]
            except Exception as e:
                print(f"[본문실패] {url}: {e}")
                out[url] = ""
        browser.close()
    return out
