# -*- coding: utf-8 -*-
"""결과를 마크다운 리포트로 만들고, (설정 시) 노션 페이지로 자동 생성한다."""
import os
import json
import urllib.request
from datetime import datetime


def _notion_cfg():
    """노션 토큰/부모페이지 ID를 환경변수 또는 config.py에서 읽는다."""
    token = os.environ.get("NOTION_TOKEN", "")
    parent = os.environ.get("NOTION_PARENT", "")
    if not token or not parent:
        try:
            import config
            token = token or getattr(config, "NOTION_TOKEN", "")
            parent = parent or getattr(config, "NOTION_PARENT", "")
        except Exception:
            pass
    return token, parent


def notion_ready():
    t, p = _notion_cfg()
    return bool(t and p)


def build_markdown(product, appeal, results, overview, trend):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [f"# 시장조사 — {product}", "",
         f"- 소구점: {appeal or '(미입력)'}",
         f"- 작성: {now}",
         f"- 분석한 글: 총 {len(results)}건", ""]

    L.append("## 조사 개요 (어디서 어떻게 조사했나)")
    for o in overview:
        L.append(f"- {o['line']}")
    L.append("")

    if trend["labels"]:
        L.append("## 발행/언급 추이 (수집글 기준)")
        L.append(f"- 날짜 확인된 글 {trend['dated']}/{trend['total']}건")
        for lab, cnt in zip(trend["labels"], trend["counts"]):
            L.append(f"  - {lab}: {cnt}건 {'█' * cnt}")
        L.append("")

    L.append("## 분석 결과 (관련성 높은 순)")
    for it in results:
        rel = it.get("relevance", "")
        fit = it.get("appeal_fit", "")
        score = f"관련{rel}/소구{fit}" if rel != "" else ""
        L.append(f"### [{it['source']}] {it['title']}  {score}")
        if it.get("summary"):
            L.append(f"- 요약: {it['summary']}")
        if it.get("deep_summary"):
            L.append(f"- 심층:\n{_indent(it['deep_summary'])}")
        L.append(f"- 링크: {it['url']}")
        L.append("")
    return "\n".join(L)


def _indent(text):
    return "\n".join("  " + ln for ln in (text or "").splitlines())


# ---------- 노션 ----------
def _nreq(path, payload, token):
    req = urllib.request.Request(
        "https://api.notion.com/v1/" + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _rt(text):
    """노션 rich_text (2000자 제한)."""
    return [{"type": "text", "text": {"content": (text or "")[:1900]}}]


def _blocks(product, appeal, results, overview, trend):
    b = []

    def h2(t): b.append({"object": "block", "type": "heading_2",
                         "heading_2": {"rich_text": _rt(t)}})

    def h3(t): b.append({"object": "block", "type": "heading_3",
                         "heading_3": {"rich_text": _rt(t)}})

    def para(t): b.append({"object": "block", "type": "paragraph",
                          "paragraph": {"rich_text": _rt(t)}})

    def bullet(t): b.append({"object": "block", "type": "bulleted_list_item",
                            "bulleted_list_item": {"rich_text": _rt(t)}})

    para(f"소구점: {appeal or '(미입력)'} · 분석 {len(results)}건 · {datetime.now():%Y-%m-%d %H:%M}")
    h2("조사 개요 (어디서 어떻게 조사했나)")
    for o in overview:
        bullet(o["line"])
    if trend["labels"]:
        h2(f"발행/언급 추이 (날짜확인 {trend['dated']}/{trend['total']}건)")
        for lab, cnt in zip(trend["labels"], trend["counts"]):
            bullet(f"{lab}: {cnt}건 {'█'*cnt}")
    h2("분석 결과 (관련성 높은 순)")
    for it in results[:40]:   # 노션 블록 수 제한 고려
        rel, fit = it.get("relevance", ""), it.get("appeal_fit", "")
        score = f"  (관련{rel}/소구{fit})" if rel != "" else ""
        h3(f"[{it['source']}] {it['title']}{score}")
        if it.get("summary"):
            bullet("요약: " + it["summary"])
        if it.get("deep_summary"):
            bullet("심층: " + it["deep_summary"].replace("\n", " "))
        bullet("링크: " + it["url"])
    return b


def push_to_notion(product, appeal, results, overview, trend):
    """노션에 페이지 생성. 성공 시 URL 반환, 실패 시 예외 메시지 문자열."""
    token, parent = _notion_cfg()
    if not (token and parent):
        return {"ok": False, "msg": "노션 토큰/부모페이지가 설정되지 않음"}
    title = f"시장조사 — {product} ({datetime.now():%m/%d})"
    payload = {
        "parent": {"page_id": parent},
        "properties": {"title": {"title": _rt(title)}},
        "children": _blocks(product, appeal, results, overview, trend)[:100],
    }
    try:
        res = _nreq("pages", payload, token)
        return {"ok": True, "url": res.get("url", ""), "id": res.get("id", "")}
    except Exception as e:
        return {"ok": False, "msg": str(e)}
