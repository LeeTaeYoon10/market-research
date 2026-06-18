# -*- coding: utf-8 -*-
"""
딥 리스닝(스노우볼) 엔진 — 소구점 하나로 '진짜 소비자 언어'를 여러 라운드에 걸쳐 깊고 많이 수집한다.

원리:
  1) 소구를 소비자 문제언어(고통·상황·감정·경쟁사불만·건강)로 분해해 초기 검색어 생성
  2) 라운드마다: 검색 → 진짜 소비자 글만(authentic) → 실제 표현(quotes/phrases) 추출
  3) 그 표현을 '다음 라운드 검색어'로 재투입(이미 쓴 건 제외, 새 각도 우선) = 스노우볼
  4) 새 표현이 거의 안 나오면 수렴으로 보고 종료. 전체를 종합해 소비자 언어 사전 생성.

진행상황은 progress_cb(dict)로 콜백한다(백그라운드 실행용).
"""
import re
import collector
import summarizer as S
import analytics


def _norm_url(u):
    return (u or "").split("#")[0].split("?")[0]


def seed_queries(appeal, category="", competitors=None):
    """소구를 소비자 문제언어 5축으로 분해한 초기 검색어를 만든다."""
    competitors = competitors or []
    if not S.ai_mode():
        return [appeal, f"{appeal} 후기", f"{category} 단점".strip()]
    prompt = (
        "너는 소비자 인사이트 리서처다. 우리는 아래 '소구점'에 대한 진짜 소비자의 말을 들으려 한다.\n"
        f"소구점: {appeal}\n카테고리: {category or '(미입력)'}\n경쟁사: {', '.join(competitors) if competitors else '(없음)'}\n\n"
        "소구를 '소비자가 실제로 쓰는 문제 언어'로 분해해 검색어 12개를 만들어라. "
        "제품명/브랜드명 없이, 다음 5축을 섞어라:\n"
        "1) 고통·결핍 2) 상황·맥락(언제/어디서) 3) 날것 감정어 4) 경쟁사·대체재 불만 5) 건강·동기.\n"
        "광고 언어 말고 커뮤니티에서 칠 법한 구어로. 설명 없이 JSON 배열로만: [\"검색어\", ...]"
    )
    arr = S._extract_json(S._ask(prompt, timeout=90)) or []
    out = [str(x).strip() for x in arr if str(x).strip()]
    return out or [appeal]


def phrases_to_queries(phrases, used, appeal, limit=10):
    """1차에서 나온 소비자 표현을 '검색 가능한 짧은 키워드'로 변환(스노우볼 다음 라운드)."""
    phrases = [p for p in phrases if p]
    if not phrases:
        return []
    if not S.ai_mode():
        # 휴리스틱: 너무 길면 앞부분만
        cand = [re.sub(r"[ㅜㅠㅋㅎ.~!?]+", "", p)[:14].strip() for p in phrases]
        return [c for c in cand if c and c not in used][:limit]
    prompt = (
        f"우리 소구점: {appeal}\n"
        "아래는 소비자가 실제로 쓴 표현들이다:\n"
        + "\n".join(f"- {p}" for p in phrases[:25]) + "\n\n"
        "이 표현들이 가리키는 '소비자 결핍·감정'으로 같은 소비자들이 더 모일 만한 "
        "검색어를 만들어라. 핵심만 담은 2~5어절 구어 키워드로. "
        "표현에서 새로 드러난 각도(예상 못한 불만·상황)를 우선해라. "
        f"이미 검색한 것은 제외: {', '.join(list(used)[:40])}\n"
        "설명 없이 JSON 배열로만 12개: [\"검색어\", ...]"
    )
    arr = S._extract_json(S._ask(prompt, timeout=90)) or []
    out = []
    for x in arr:
        q = str(x).strip()
        if q and q not in used:
            out.append(q)
    return out[:limit]


def deep_listen(appeal, category="", competitors=None,
                rounds=4, per_round=6, per_source=6,
                sources=None, progress_cb=None, max_items=400):
    """멀티라운드 스노우볼로 진짜 소비자 언어를 깊고 많이 수집한다.
    반환: {items, voc, rounds_log, phrases_all, queries_used}"""
    competitors = competitors or []
    sources = sources or ["naver_cafe", "naver_blog", "dcinside", "naver_news"]
    used = set()
    seen_urls = set()
    items = []
    phrases_all = []
    rounds_log = []

    def emit(stage, **kw):
        if progress_cb:
            progress_cb({"stage": stage, "round": kw.get("r"), "items": len(items),
                         "phrases": len(set(phrases_all)), "queries": len(used),
                         **kw})

    # 라운드 0: 소구 5축 시드
    queries = seed_queries(appeal, category, competitors)
    emit("seed", r=0, new_queries=queries)

    for r in range(1, rounds + 1):
        new_q = [q for q in queries if q not in used][:per_round]
        if not new_q:
            emit("converged", r=r)
            break
        used.update(new_q)
        emit("search", r=r, new_queries=new_q)
        raw = collector.search(new_q, sources, per_source=per_source, headless=True)
        # 신규 글만
        fresh = []
        for it in raw:
            nu = _norm_url(it.get("url", ""))
            if nu in seen_urls:
                continue
            seen_urls.add(nu)
            fresh.append(it)
        emit("evaluate", r=r, fresh=len(fresh))
        res = S.summarize(fresh, appeal, category, competitors) if fresh else []
        # 진짜 소비자 글(authentic>=3) 위주로 누적
        keep = [it for it in res if (it.get("authentic") or 0) >= 3 or (it.get("relevance") or 0) >= 4]
        items += keep
        # 표현 수집
        round_phrases = []
        for it in keep:
            round_phrases += [q for q in (it.get("quotes") or []) if q]
        voc = S.build_voc(keep, appeal, competitors) if keep else None
        if voc:
            round_phrases += voc.get("phrases", [])
        before = len(set(phrases_all))
        phrases_all += round_phrases
        after = len(set(phrases_all))
        rounds_log.append({"round": r, "queries": new_q, "fresh": len(fresh),
                           "kept": len(keep), "new_phrases": after - before})
        emit("round_done", r=r, kept=len(keep), new_phrases=after - before)
        if len(items) >= max_items:
            emit("max_items", r=r)
            break
        # 수렴: 새 표현이 거의 없으면 종료
        if r >= 2 and (after - before) < 3:
            emit("converged", r=r)
            break
        # 다음 라운드 검색어 = 이번 표현 재투입
        queries = phrases_to_queries(list(set(phrases_all)), used, appeal, limit=per_round + 4)

    items.sort(key=lambda x: ((x.get("authentic") or 0) + (x.get("relevance") or 0)), reverse=True)
    final_voc = S.build_voc(items, appeal, competitors) if items else None
    overview = analytics.build_overview(items, list(used))
    trend = analytics.build_trend(items)
    emit("done", r=len(rounds_log))
    return {"items": items, "voc": final_voc, "overview": overview, "trend": trend,
            "rounds_log": rounds_log, "phrases_all": sorted(set(phrases_all)),
            "queries_used": sorted(used)}
