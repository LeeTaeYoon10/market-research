# -*- coding: utf-8 -*-
"""조사 개요(출처·방법 표기) + 발행/언급 추이 집계."""
from collections import defaultdict


def build_overview(results, queries):
    """소스별로 '어떤 검색어로 몇 건 분석했는지' 집계.
    반환 예: [{source:'디시인사이드', count:8, queries:['그래니 샐러드', ...]}]"""
    by_src = defaultdict(lambda: {"count": 0, "queries": set()})
    for it in results:
        s = by_src[it["source"]]
        s["count"] += 1
        if it.get("query"):
            s["queries"].add(it["query"])
    overview = []
    for src, v in by_src.items():
        qs = sorted(v["queries"])
        overview.append({
            "source": src,
            "count": v["count"],
            "queries": qs,
            # 사람이 읽는 한 줄: "디시인사이드 — '그래니 샐러드' 외 2개 검색어로 8건 분석"
            "line": _overview_line(src, qs, v["count"]),
        })
    overview.sort(key=lambda x: x["count"], reverse=True)
    return overview


def _overview_line(src, queries, count):
    if not queries:
        return f"{src} — {count}건 분석"
    head = queries[0]
    if len(queries) == 1:
        return f"{src} — '{head}' 검색으로 {count}건 분석"
    return f"{src} — '{head}' 외 {len(queries)-1}개 검색어로 {count}건 분석"


def build_trend(results):
    """수집글의 발행월(date) 분포로 언급량 추이 생성.
    반환: {labels:[...월], counts:[...], dated:n, total:n}"""
    buckets = defaultdict(int)
    dated = 0
    for it in results:
        d = it.get("date")
        if d:
            buckets[d] += 1
            dated += 1
    labels = sorted(buckets.keys())
    counts = [buckets[m] for m in labels]
    return {"labels": labels, "counts": counts, "dated": dated, "total": len(results)}
