# -*- coding: utf-8 -*-
"""
수집한 글을 클로드로 요약/평가한다.

AI 호출 통로(둘 중 하나 자동 선택):
  1) 클로드 코드 CLI (claude -p)  ← API 키 불필요, 기존 구독 사용 (기본)
  2) ANTHROPIC_API_KEY 환경변수가 있으면 API 사용
둘 다 없으면 미리보기 텍스트를 그대로 사용.
"""
import os
import json
import shutil
import subprocess

_CLAUDE = shutil.which("claude")
MODEL = "claude-haiku-4-5-20251001"  # API 경로에서만 사용


def ai_mode():
    """현재 사용 가능한 AI 경로를 반환: 'cli' | 'api' | None"""
    if _CLAUDE:
        return "cli"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "api"
    return None


def _ask(prompt, timeout=150):
    """프롬프트를 클로드에 보내 텍스트 응답을 받는다."""
    mode = ai_mode()
    if mode == "cli":
        try:
            r = subprocess.run(
                [_CLAUDE, "-p"], input=prompt,
                capture_output=True, text=True, encoding="utf-8", timeout=timeout,
            )
            return (r.stdout or "").strip()
        except Exception as e:
            print(f"[claude CLI 실패] {e}")
            return ""
    if mode == "api":
        try:
            import anthropic
            client = anthropic.Anthropic()
            msg = client.messages.create(
                model=MODEL, max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip()
        except Exception as e:
            print(f"[API 실패] {e}")
            return ""
    return ""


def _extract_json(text):
    """응답 텍스트에서 JSON 배열만 뽑아 파싱."""
    try:
        s, e = text.find("["), text.rfind("]")
        return json.loads(text[s:e + 1])
    except Exception:
        return None


def expand_queries(product, appeal):
    """제품 + 소구로 검색어 세트를 만든다."""
    base = [
        product,
        f"{product} 후기",
        f"{product} 추천",
        f"{product} 가격",
        f"{product} 단점",
        f"{product} {appeal}".strip(),
    ]
    if ai_mode():
        prompt = (
            f"제품: {product}\n소구점: {appeal}\n"
            "위 제품을 시장조사할 때 쓸 한국어 검색어 6개를 만들어줘. "
            "경쟁사명, 연관 트렌드어, 소비자 후기 관점을 섞어. "
            '설명 없이 JSON 배열로만 답해. 예: ["검색어1","검색어2"]'
        )
        arr = _extract_json(_ask(prompt, timeout=90))
        if arr:
            return list(dict.fromkeys(base + [str(x) for x in arr]))
    return base


def summarize(items, product, appeal):
    """
    각 항목에 relevance(1-5), appeal_fit(1-5), summary 추가.
    AI 없으면 snippet을 요약으로 사용.
    """
    if not ai_mode():
        for it in items:
            it["relevance"] = ""
            it["appeal_fit"] = ""
            it["summary"] = it.get("snippet", "")[:200]
        return items

    BATCH = 10
    out = []
    for i in range(0, len(items), BATCH):
        chunk = items[i:i + BATCH]
        listing = "\n".join(
            f"[{j}] 제목:{it['title']} | 미리보기:{it.get('snippet','')[:200]}"
            for j, it in enumerate(chunk)
        )
        prompt = (
            f"우리 제품: {product}\n우리가 강조하려는 소구점: {appeal}\n\n"
            f"아래 검색결과 각각을 평가해줘:\n{listing}\n\n"
            "각 항목에 대해 설명 없이 JSON 배열로만 답해. 각 원소는 "
            '{"i":번호, "relevance":1~5(제품 관련성), "appeal_fit":1~5(소구점 부합도), '
            '"summary":"핵심 2줄 요약(한국어)"}. 미리보기가 빈약하면 제목 기준으로 판단. '
            "동음이의어(예: 무관한 가게명·취미글)는 relevance를 1로."
        )
        arr = _extract_json(_ask(prompt)) or []
        by_i = {d.get("i"): d for d in arr if isinstance(d, dict)}
        for j, it in enumerate(chunk):
            d = by_i.get(j, {})
            it["relevance"] = d.get("relevance", "")
            it["appeal_fit"] = d.get("appeal_fit", "")
            it["summary"] = d.get("summary", it.get("snippet", "")[:200])
            out.append(it)
    # 관련성 높은 순 정렬
    out.sort(key=lambda x: ((x.get("relevance") or 0), (x.get("appeal_fit") or 0)), reverse=True)
    return out


def deep_summarize(items, product, appeal, fulltext_map):
    """상위 글의 본문 전체를 읽어 깊은 요약을 추가한다.
    fulltext_map: {url: 본문텍스트}. 본문 있는 항목에만 deep_summary 채움."""
    if not ai_mode():
        return items
    for it in items:
        body = it.get("fulltext") or fulltext_map.get(it["url"], "")
        if not body or len(body) < 200:
            continue
        prompt = (
            f"우리 제품: {product}\n우리 소구점: {appeal}\n\n"
            f"아래는 '{it['title']}' 글의 본문이다:\n{body[:6000]}\n\n"
            "마케터 시장조사용으로 핵심만 정리해줘. 설명머리말 없이 아래 형식으로:\n"
            "- 핵심내용: (3줄)\n- 소비자 반응/감성: (긍정/부정/중립 + 이유)\n"
            "- 우리 소구점 관점 시사점: (1~2줄)"
        )
        it["deep_summary"] = _ask(prompt, timeout=120)
    return items
