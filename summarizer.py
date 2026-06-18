# -*- coding: utf-8 -*-
"""
수집한 글을 클로드로 요약/평가한다.

AI 호출 통로(둘 중 하나 자동 선택):
  1) 클로드 코드 CLI (claude -p)  ← API 키 불필요, 기존 구독 사용 (기본)
  2) ANTHROPIC_API_KEY 환경변수가 있으면 API 사용
둘 다 없으면 미리보기 텍스트를 그대로 사용.
"""
import os
import re
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


def _extract_obj(text):
    """응답 텍스트에서 JSON 객체({...})만 뽑아 파싱."""
    try:
        s, e = text.find("{"), text.rfind("}")
        return json.loads(text[s:e + 1])
    except Exception:
        return None


def plan_strategy(product, product_desc, appeal):
    """제품·제품설명·소구점을 받아 '조사 전략'을 만든다.
    반환: {product_understanding, target{age,personality,needs}, keywords[], sites[], self_method}
    AI 없으면 None."""
    if not ai_mode():
        return None
    prompt = (
        f"너는 마케팅 시장조사 전략가다.\n"
        f"제품명: {product}\n"
        f"제품 설명: {product_desc or '(설명 없음 - 제품명으로 추정)'}\n"
        f"강조하려는 소구점: {appeal or '(미입력 - 네가 가장 효과적인 소구 방향을 제안)'}\n\n"
        "이 제품과 소구점을 시장조사하기 위한 전략을 세워라. 다음을 깊이 분석해:\n"
        "1) 이 제품이 어떤 제품인지 한 문단으로 정의.\n"
        "2) 이 소구점에 반응할 핵심 타겟층 — 나이대, 성격/라이프스타일, 그들이 가진 '결핍·니즈'(왜 이 제품을 원하는가).\n"
        "3) 어떤 검색어로 찾으면 좋을지 8~12개 — 각 키워드마다 '왜 이 키워드인지' 이유. "
        "경쟁사·후기·결핍감정·트렌드·상황(언제 쓰나) 관점을 섞어.\n"
        "4) 어떤 사이트/커뮤니티를 조사하면 좋을지 6~10개 — 그 소구의 타겟층(나이대·성격·결핍이 많은 사람들)이 모이는 곳 위주로. "
        "국내(네이버카페·디시 특정갤·인스타 등)와 해외(Reddit 서브레딧·Quora·전문 포럼 등)를 모두 포함. "
        "각 사이트마다 '거기에 어떤 사람이 모이는지'와 '왜 우리 조사에 유용한지' 이유.\n"
        "5) 앞으로 스스로 새 소구점을 발굴하려면 어떤 키워드·사이트를 어떤 순서로 조사하면 좋을지(2~4줄).\n\n"
        "반드시 아래 JSON 객체 하나로만, 설명 머리말 없이 답해(한국어):\n"
        "{\n"
        '  "product_understanding": "...",\n'
        '  "target": {"age":"...", "personality":"...", "needs":"..."},\n'
        '  "keywords": [{"keyword":"...","reason":"..."}],\n'
        '  "sites": [{"name":"...","region":"국내|해외","where":"URL이나 갤러리/서브레딧명","audience":"모이는 사람","reason":"왜 유용한가"}],\n'
        '  "self_method": "..."\n'
        "}"
    )
    return _extract_obj(_ask(prompt, timeout=150))


def expand_queries(product, appeal, product_desc=""):
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
            f"제품: {product}\n제품 설명: {product_desc or '(없음)'}\n소구점: {appeal}\n"
            "위 제품을 시장조사할 때 쓸 한국어 검색어 6개를 만들어줘. "
            "경쟁사명, 연관 트렌드어, 소비자 후기 관점을 섞어. "
            '설명 없이 JSON 배열로만 답해. 예: ["검색어1","검색어2"]'
        )
        arr = _extract_json(_ask(prompt, timeout=90))
        if arr:
            return list(dict.fromkeys(base + [str(x) for x in arr]))
    return base


def plan_consumer_search(appeal, category="", competitors="", product_desc=""):
    """소구점 중심으로 '진짜 소비자 반응'을 찾기 위한 검색 설계.
    내 제품이 아니라 (1) 소구에 대한 소비자 언어 (2) 경쟁사 제품 반응을 검색한다.
    반환 dict: {competitors[], consumer_queries[{q,why}], competitor_queries[{q,why}]} (AI 없으면 규칙기반)."""
    comp_in = [c.strip() for c in re.split(r"[,\n]", competitors or "") if c.strip()]
    if ai_mode():
        prompt = (
            "너는 소비자 인사이트 리서처다. 우리는 '우리 제품'을 검색하려는 게 아니라, "
            "아래 '소구점'에 대한 진짜 소비자의 반응·욕구·결핍과, '경쟁사 제품'에 대한 소비자 반응을 찾으려 한다.\n\n"
            f"소구점(핵심): {appeal}\n"
            f"제품 카테고리/맥락(검색대상 아님, 노이즈 거르기용): {category or '(미입력)'} {('- ' + product_desc) if product_desc else ''}\n"
            f"경쟁사(입력됨): {', '.join(comp_in) if comp_in else '(없음 - 네가 직접 도출)'}\n\n"
            "다음을 만들어라:\n"
            "1) competitors: 이 카테고리·소구의 대표 경쟁사/대체재 제품·브랜드 5~7개(입력이 있으면 그걸 포함·보완). 우리 제품명은 넣지 마라.\n"
            "2) consumer_queries: 소구점에 대한 '진짜 소비자'가 커뮤니티·블로그에 쓸 법한 검색어 8개. "
            "제품명/브랜드명 없이, 감정·상황·결핍·욕구의 소비자 언어로(예: '자취 끼니 귀찮아', '다이어트 작심삼일', '바쁜데 건강하게'). 각 why(왜 이 검색이 소구 반응을 드러내는지).\n"
            "3) competitor_queries: 경쟁사 제품에 대한 소비자 반응을 찾는 검색어 8개. "
            "'경쟁사명 + 후기/단점/별로/실망/재구매/맛없' 식으로 솔직한 반응을 노린다. 각 why.\n\n"
            "반드시 JSON 객체 하나로만(설명 없이, 한국어):\n"
            '{"competitors":["..."],'
            '"consumer_queries":[{"q":"...","why":"..."}],'
            '"competitor_queries":[{"q":"...","why":"..."}]}'
        )
        obj = _extract_obj(_ask(prompt, timeout=150))
        if obj and (obj.get("consumer_queries") or obj.get("competitor_queries")):
            obj.setdefault("competitors", comp_in)
            return obj
    # 폴백(AI 없음): 규칙 기반 최소 검색어
    cq = [f"{appeal}", f"{appeal} 후기", f"{appeal} 고민", f"{category} 후기".strip(),
          f"{category} 단점".strip()]
    kq = [f"{c} 후기" for c in comp_in] + [f"{c} 단점" for c in comp_in]
    return {
        "competitors": comp_in,
        "consumer_queries": [{"q": q, "why": ""} for q in cq if q],
        "competitor_queries": [{"q": q, "why": ""} for q in kq if q],
    }


def summarize(items, appeal, category="", competitors=None):
    """
    각 항목에 relevance(소구 관련성 1-5), authentic(진짜 소비자글 1-5),
    sentiment(긍/부/중/혼합), summary(소비자가 무엇을 느끼는지) 추가.
    AI 없으면 snippet을 요약으로 사용.
    """
    competitors = competitors or []
    if not ai_mode():
        for it in items:
            it["relevance"] = ""
            it["authentic"] = ""
            it["appeal_fit"] = ""   # 하위호환
            it["sentiment"] = ""
            it["summary"] = it.get("snippet", "")[:200]
        return items

    comp_str = ", ".join(competitors) if competitors else "(미지정)"
    BATCH = 10
    out = []
    for i in range(0, len(items), BATCH):
        chunk = items[i:i + BATCH]
        listing = "\n".join(
            f"[{j}] 제목:{it['title']} | 미리보기:{it.get('snippet','')[:200]}"
            for j, it in enumerate(chunk)
        )
        prompt = (
            f"우리가 찾는 소구점(소비자 반응 대상): {appeal}\n"
            f"카테고리/맥락: {category or '(미입력)'}\n경쟁사: {comp_str}\n\n"
            "우리는 이 소구점에 대한 '진짜 소비자'의 솔직한 글과, 경쟁사 제품에 대한 소비자 반응을 모은다. "
            "광고·협찬·체험단·기자단·판매홍보·제휴 글은 가짜로 보고 낮게 평가한다.\n\n"
            f"아래 검색결과 각각을 평가해줘:\n{listing}\n\n"
            "각 항목 설명 없이 JSON 배열로만 답해. 각 원소는 "
            '{"i":번호, "relevance":1~5(소구점/소비자결핍 관련성), '
            '"authentic":1~5(진짜 소비자 글일수록 높게; 광고·체험단·판매글은 1~2), '
            '"sentiment":"긍정|부정|중립|혼합", '
            '"summary":"이 소비자가 무엇을 느끼고 원하는지/경쟁사에 대해 뭐라는지 2줄(한국어)", '
            '"quotes":["소비자가 실제 쓴 듯한 날것의 표현 0~2개(미리보기에 근거; 꾸미지 말 것). 없으면 빈 배열"]}. '
            "미리보기가 빈약하면 제목 기준 판단. 무관한 동음이의·잡글은 relevance 1."
        )
        arr = _extract_json(_ask(prompt)) or []
        by_i = {d.get("i"): d for d in arr if isinstance(d, dict)}
        for j, it in enumerate(chunk):
            d = by_i.get(j, {})
            it["relevance"] = d.get("relevance", "")
            it["authentic"] = d.get("authentic", "")
            it["appeal_fit"] = d.get("authentic", "")  # 하위호환(CSV/리포트 옛 컬럼)
            it["sentiment"] = d.get("sentiment", "")
            it["summary"] = d.get("summary", it.get("snippet", "")[:200])
            it["quotes"] = [str(q) for q in (d.get("quotes") or []) if q][:2]
            out.append(it)
    # 진짜 소비자글 + 소구 관련성 높은 순 정렬
    out.sort(key=lambda x: ((x.get("authentic") or 0) + (x.get("relevance") or 0)), reverse=True)
    return out


def parse_pasted_reviews(text, appeal, category="", competitors=None, source="붙여넣은 리뷰"):
    """쇼핑몰 리뷰 페이지에서 복사한 통 텍스트를 개별 리뷰로 분리하고 각각 평가한다.
    봇차단과 무관(이미 사람이 본 텍스트). 반환: 평가된 리뷰 item 리스트."""
    competitors = competitors or []
    text = (text or "").strip()
    if not text:
        return []
    if not ai_mode():
        # AI 없으면 빈 줄 기준으로만 분리
        chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if len(c.strip()) > 15]
        return [{"source": source, "title": c[:40], "url": "", "snippet": c[:300],
                 "summary": c[:200], "relevance": "", "authentic": "", "sentiment": "",
                 "quotes": [], "date": "", "query": "(붙여넣기)"} for c in chunks]

    out = []
    # 너무 길면 잘라서 여러 번
    MAXC = 7000
    parts = [text[i:i + MAXC] for i in range(0, len(text), MAXC)] or [text]
    for part in parts:
        prompt = (
            f"우리 소구점: {appeal}\n카테고리: {category or '(미입력)'}\n경쟁사: {', '.join(competitors) if competitors else '(미지정)'}\n\n"
            "아래는 쇼핑몰 상품 리뷰 페이지에서 복사한 텍스트다. 별점·날짜·작성자·도움돼요 수 등이 섞여 있다.\n"
            "여기서 '개별 소비자 리뷰'만 정확히 분리해서 각각 평가해라. 메뉴·버튼·광고문구는 버려라.\n\n"
            f"텍스트:\n{part}\n\n"
            "설명 없이 JSON 배열로만. 각 원소는 "
            '{"content":"리뷰 본문(원문 그대로)", "date":"YYYY-MM 또는 빈칸", "rating":"별점 숫자 또는 빈칸", '
            '"relevance":1~5(소구점 관련), "authentic":1~5(진짜 소비자 리뷰면 높게), '
            '"sentiment":"긍정|부정|중립|혼합", "summary":"이 소비자가 느낀 점 1~2줄", '
            '"quotes":["인상적인 원문 표현 0~2개"]}. 리뷰가 없으면 빈 배열 [].'
        )
        arr = _extract_json(_ask(prompt)) or []
        for d in arr:
            if not isinstance(d, dict):
                continue
            content = (d.get("content") or "").strip()
            if not content:
                continue
            out.append({
                "source": source,
                "title": content[:40] + ("..." if len(content) > 40 else ""),
                "url": "",
                "snippet": content[:300],
                "summary": d.get("summary", content[:200]),
                "relevance": d.get("relevance", ""),
                "authentic": d.get("authentic", ""),
                "appeal_fit": d.get("authentic", ""),
                "sentiment": d.get("sentiment", ""),
                "quotes": [str(q) for q in (d.get("quotes") or []) if q][:2],
                "date": d.get("date", "") or "",
                "rating": d.get("rating", ""),
                "query": "(붙여넣은 리뷰)",
            })
    out.sort(key=lambda x: ((x.get("authentic") or 0) + (x.get("relevance") or 0)), reverse=True)
    return out


def build_voc(results, appeal, competitors=None):
    """수집된 소비자 글 전체에서 VOC(불만 top·욕구 top·자주 쓰는 표현)를 집계.
    반환 dict 또는 None(AI 없음)."""
    if not ai_mode() or not results:
        return None
    lines = []
    for it in results[:45]:
        if (it.get("relevance") or 0) < 2:
            continue
        q = " / ".join(it.get("quotes", []) or [])
        lines.append(f"- [{it.get('sentiment','')}] {it.get('summary','')}"
                     + (f" (원문: {q})" if q else ""))
    blob = "\n".join(lines)
    if not blob:
        return None
    prompt = (
        f"소구점: {appeal}\n경쟁사: {', '.join(competitors) if competitors else '(미지정)'}\n\n"
        "아래는 이 소구점에 대한 소비자 글·경쟁사 반응의 요약·원문 모음이다:\n"
        f"{blob}\n\n"
        "마케터가 소비자 언어를 파악하도록 종합해라. 설명 없이 JSON 객체 하나로만(한국어):\n"
        '{"complaints":[{"text":"대표 불만/결핍","note":"근거·맥락 한줄"}],'
        '"desires":[{"text":"소비자가 원하는 것","note":"한줄"}],'
        '"phrases":["소비자가 자주/인상적으로 쓰는 날것의 표현"],'
        '"insight":"소구 관점 핵심 시사점 2~3줄"}. '
        "complaints·desires는 각 4~7개, phrases는 6~12개. 꾸미지 말고 소비자 실제 언어로."
    )
    return _extract_obj(_ask(prompt, timeout=150))


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
