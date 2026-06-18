# -*- coding: utf-8 -*-
"""
쿠팡·스마트스토어 상품 리뷰를 '로그인된 실제 크롬'을 직접 조작해 수집한다.

봇차단(WAF)·로그인벽 때문에 헤드리스로는 막히므로, 사용자가 디버그 포트로 띄워
로그인해 둔 크롬에 CDP로 붙는다(데일리 액션과 동일한 방식).

준비:
  1) '로그인크롬_켜기.bat' 실행 → 크롬이 9222 포트로 열림
  2) 그 창에서 쿠팡·네이버에 로그인(처음 1회). 이후 프로필에 저장돼 자동 유지.
  3) 도구에서 상품 URL을 넣고 '리뷰 수집'

connect_over_cdp 로 붙으므로 사용자의 로그인 세션을 그대로 사용한다.
"""
import re
import time
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9222"


def _clean(t):
    return re.sub(r"\s+", " ", (t or "")).strip()


def connect():
    """디버그 포트로 열린 크롬에 붙어 (playwright, browser, page) 반환. 실패 시 예외."""
    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(CDP_URL)
    except Exception:
        try:
            p.stop()
        except Exception:
            pass
        raise
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return p, browser, page


def _kind(url):
    if "coupang.com" in url:
        return "coupang"
    if "smartstore.naver.com" in url or "brand.naver.com" in url:
        return "smartstore"
    return "unknown"


# ---------- 쿠팡 ----------
def collect_coupang(page, url, limit=20, latest_first=True):
    """쿠팡 상품페이지의 리뷰를 수집. (별점/날짜/내용)"""
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    time.sleep(2)
    # 리뷰 영역으로 스크롤(상품평 탭 로딩 유도)
    try:
        page.evaluate("document.querySelector('#sdpReview, .sdp-review')?.scrollIntoView()")
    except Exception:
        pass
    time.sleep(1.5)
    # 최신순 정렬
    if latest_first:
        try:
            # 정렬 드롭다운 안의 '최신순'
            page.click("text=최신순", timeout=3000)
            time.sleep(1.5)
        except Exception:
            pass
    items, seen = [], set()
    pages_scanned = 0
    while len(items) < limit and pages_scanned < 8:
        time.sleep(1.2)
        soup = BeautifulSoup(page.content(), "lxml")
        arts = soup.select("article.sdp-review__article__list")
        for a in arts:
            content = _clean(a.select_one(".sdp-review__article__list__review__content").get_text(" ")) \
                if a.select_one(".sdp-review__article__list__review__content") else ""
            if not content or content in seen:
                continue
            seen.add(content)
            date = a.select_one(".sdp-review__article__list__info__product-info__reg-date")
            star = a.select_one(".sdp-review__article__list__info__product-info__star-orange")
            rating = ""
            if star and star.has_attr("style"):
                m = re.search(r"width:\s*([\d.]+)%", star["style"])
                if m:
                    rating = round(float(m.group(1)) / 20, 1)  # 100%→5점
            items.append({
                "source": "쿠팡 리뷰",
                "title": (content[:40] + ("..." if len(content) > 40 else "")),
                "url": url,
                "snippet": content[:300],
                "rating": rating,
                "date": _norm_date(date.get_text() if date else ""),
                "query": "(쿠팡 상품리뷰)",
            })
            if len(items) >= limit:
                break
        # 다음 페이지
        nxt = page.query_selector(".sdp-review__article__page__next:not(.sdp-review__article__page__next--disable)")
        if nxt:
            try:
                nxt.click()
                pages_scanned += 1
                continue
            except Exception:
                break
        break
    return items


# ---------- 스마트스토어 ----------
def collect_smartstore(page, url, limit=20, latest_first=True):
    """스마트스토어 상품페이지의 리뷰를 수집. 네이버는 클래스가 난수라 구조·텍스트 기반."""
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    time.sleep(2)
    # 리뷰 섹션으로 이동
    try:
        page.click("a:has-text('리뷰'), button:has-text('리뷰')", timeout=3000)
        time.sleep(1.5)
    except Exception:
        pass
    try:
        page.evaluate("document.querySelector('#REVIEW')?.scrollIntoView()")
    except Exception:
        pass
    time.sleep(1.5)
    if latest_first:
        try:
            page.click("text=최신순", timeout=3000)
            time.sleep(1.5)
        except Exception:
            pass
    items, seen = [], set()
    for _ in range(8):
        if len(items) >= limit:
            break
        page.mouse.wheel(0, 3000)
        time.sleep(1.0)
        soup = BeautifulSoup(page.content(), "lxml")
        # 리뷰 텍스트로 보이는 긴 문단들을 구조적으로 추출
        for li in soup.find_all(["li", "div"]):
            cls = " ".join(li.get("class") or [])
            if "review" not in cls.lower():
                continue
            txt = _clean(li.get_text(" "))
            # 리뷰 본문스러운 길이 + 중복 제거
            if len(txt) < 25 or txt in seen:
                continue
            # 별점/날짜 흔적
            if not re.search(r"\d{2,4}[.\-]\d{1,2}[.\-]\d{1,2}|\d{1,2}\.\d{1,2}\.", txt) and "평점" not in txt:
                pass
            seen.add(txt)
            items.append({
                "source": "스마트스토어 리뷰",
                "title": txt[:40] + ("..." if len(txt) > 40 else ""),
                "url": url,
                "snippet": txt[:300],
                "rating": "",
                "date": _norm_date(txt),
                "query": "(스마트스토어 상품리뷰)",
            })
            if len(items) >= limit:
                break
    return items


def _norm_date(text):
    m = re.search(r"(20\d{2})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})", text or "")
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{2})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})", text or "")
    if m:
        return f"20{m.group(1)}-{int(m.group(2)):02d}"
    return ""


def read_open_reviews(limit=40):
    """[봇차단 우회] 사용자가 디버그 크롬에서 '직접 연' 쿠팡·스마트스토어 리뷰 페이지들을
    이동(goto) 없이 현재 DOM 그대로 읽는다. 사람이 연 페이지라 봇탐지를 피한다."""
    out = []
    p = browser = None
    try:
        p, browser, page = connect()
    except Exception as e:
        raise RuntimeError(
            "로그인된 크롬에 연결하지 못했습니다. '로그인크롬_켜기.bat'을 먼저 실행하세요. "
            f"(상세: {e})"
        )
    try:
        ctx = browser.contexts[0] if browser.contexts else None
        pages = ctx.pages if ctx else []
        for pg in pages:
            url = pg.url
            k = _kind(url)
            if k == "unknown":
                continue
            try:
                # 리뷰 더 로드되도록 살짝 스크롤(이동 아님)
                for _ in range(4):
                    pg.mouse.wheel(0, 2500)
                    time.sleep(0.8)
                html = pg.content()
            except Exception:
                continue
            if k == "coupang":
                out += _parse_coupang_html(html, url, limit)
            elif k == "smartstore":
                out += _parse_smartstore_html(html, url, limit)
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if p:
                p.stop()
        except Exception:
            pass
    return out


def _parse_coupang_html(html, url, limit):
    soup = BeautifulSoup(html, "lxml")
    items, seen = [], set()
    for a in soup.select("article.sdp-review__article__list"):
        cnode = a.select_one(".sdp-review__article__list__review__content")
        content = _clean(cnode.get_text(" ")) if cnode else ""
        if not content or content in seen:
            continue
        seen.add(content)
        date = a.select_one(".sdp-review__article__list__info__product-info__reg-date")
        items.append({"source": "쿠팡 리뷰", "title": content[:40], "url": url,
                      "snippet": content[:300], "rating": "",
                      "date": _norm_date(date.get_text() if date else ""),
                      "query": "(쿠팡 상품리뷰)"})
        if len(items) >= limit:
            break
    return items


def _parse_smartstore_html(html, url, limit):
    soup = BeautifulSoup(html, "lxml")
    items, seen = [], set()
    for li in soup.find_all(["li", "div"]):
        cls = " ".join(li.get("class") or [])
        if "review" not in cls.lower():
            continue
        txt = _clean(li.get_text(" "))
        if len(txt) < 25 or txt in seen:
            continue
        seen.add(txt)
        items.append({"source": "스마트스토어 리뷰", "title": txt[:40], "url": url,
                      "snippet": txt[:300], "rating": "",
                      "date": _norm_date(txt), "query": "(스마트스토어 상품리뷰)"})
        if len(items) >= limit:
            break
    return items


def collect_reviews(urls, limit=20, latest_first=True):
    """여러 상품 URL의 리뷰를 수집해 리스트 반환. 크롬(9222) 연결 필요."""
    out = []
    p = browser = None
    try:
        p, browser, page = connect()
    except Exception as e:
        raise RuntimeError(
            "로그인된 크롬에 연결하지 못했습니다. '로그인크롬_켜기.bat'을 먼저 실행하고 "
            f"쿠팡·네이버에 로그인했는지 확인하세요. (상세: {e})"
        )
    try:
        for url in urls:
            url = url.strip()
            if not url.startswith("http"):
                continue
            k = _kind(url)
            try:
                if k == "coupang":
                    out += collect_coupang(page, url, limit, latest_first)
                elif k == "smartstore":
                    out += collect_smartstore(page, url, limit, latest_first)
            except Exception as e:
                print(f"[리뷰수집 실패] {url}: {e}")
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if p:
                p.stop()
        except Exception:
            pass
    return out
