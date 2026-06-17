# -*- coding: utf-8 -*-
"""
시장조사 도구 - 로컬 웹 UI
실행: python app.py  →  브라우저에서 http://127.0.0.1:5000
"""
import csv
import io
from flask import Flask, render_template, request, Response, jsonify

import collector
import summarizer
import analytics
import report
import review_collector

app = Flask(__name__)
LAST = {}  # 마지막 결과 보관 (CSV/리포트/노션용)


@app.route("/")
def index():
    return render_template(
        "index.html",
        sources=collector.SOURCES,
        ai_mode=summarizer.ai_mode(),
        notion_ready=report.notion_ready(),
    )


@app.route("/plan", methods=["POST"])
def plan():
    """제품·제품설명·소구점을 분석해 조사 전략(키워드/사이트/타겟층)을 제안."""
    data = request.get_json()
    product = (data.get("product") or "").strip()
    product_desc = (data.get("product_desc") or "").strip()
    appeal = (data.get("appeal") or "").strip()
    if not product and not product_desc:
        return jsonify({"error": "제품명이나 제품 설명을 입력해주세요."}), 400
    if not summarizer.ai_mode():
        return jsonify({"error": "전략 제안은 AI(클로드 코드)가 필요합니다. 설치·로그인 후 사용하세요."}), 400
    strat = summarizer.plan_strategy(product, product_desc, appeal)
    if not strat:  # 간헐적 빈응답 1회 재시도
        strat = summarizer.plan_strategy(product, product_desc, appeal)
    if not strat:
        return jsonify({"error": "전략 생성에 실패했어요. 잠시 후 다시 시도해주세요."}), 500
    LAST.update(product=product, product_desc=product_desc, appeal=appeal, strategy=strat)
    return jsonify({"strategy": strat, "notion_ready": report.notion_ready()})


@app.route("/plan.md")
def plan_md():
    strat = LAST.get("strategy")
    if not strat:
        return Response("아직 전략을 생성하지 않았습니다.", mimetype="text/plain")
    md = report.build_strategy_markdown(LAST.get("product", ""), LAST.get("appeal", ""), strat)
    return Response(md, mimetype="text/markdown",
                    headers={"Content-Disposition": "attachment; filename=research_strategy.md"})


@app.route("/plan_notion", methods=["POST"])
def plan_to_notion():
    strat = LAST.get("strategy")
    if not strat:
        return jsonify({"ok": False, "msg": "먼저 '조사 전략 제안받기'를 실행하세요."})
    res = report.push_strategy_to_notion(LAST.get("product", ""), LAST.get("appeal", ""), strat)
    return jsonify(res)


@app.route("/search", methods=["POST"])
def search():
    data = request.get_json()
    # product 필드 = 내 제품/카테고리(검색 대상 아님, 맥락·노이즈거르기용)
    category = (data.get("product") or "").strip()
    product_desc = (data.get("product_desc") or "").strip()
    appeal = (data.get("appeal") or "").strip()
    competitors_in = (data.get("competitors") or "").strip()
    source_keys = data.get("sources") or ["naver_blog", "naver_cafe", "naver_news", "daum"]
    per_source = int(data.get("per_source") or 8)
    deep = bool(data.get("deep"))
    custom_urls = [u.strip() for u in (data.get("custom_urls") or "").splitlines() if u.strip()]

    if not appeal and not custom_urls:
        return jsonify({"error": "소구점을 입력하거나 직접 링크를 넣어주세요. (이 도구는 소구·경쟁사에 대한 소비자 반응을 찾습니다)"}), 400

    # 1) 소구·경쟁사 중심 검색 설계 (내 제품은 검색하지 않음)
    plan = summarizer.plan_consumer_search(appeal, category, competitors_in, product_desc) if appeal else \
        {"competitors": [], "consumer_queries": [], "competitor_queries": []}
    competitors = plan.get("competitors", [])
    cq = [d.get("q", "") for d in plan.get("consumer_queries", []) if d.get("q")]
    kq = [d.get("q", "") for d in plan.get("competitor_queries", []) if d.get("q")]
    queries = list(dict.fromkeys(cq + kq))  # 소구 소비자언어 + 경쟁사 반응
    # 2) 검색 수집 + 직접 링크 수집
    raw = collector.search(queries, source_keys, per_source=per_source, headless=True) if queries else []
    custom = collector.fetch_custom(custom_urls, headless=True)
    allitems = custom + raw
    # 3) 진짜 소비자글 + 소구 관련성 평가
    results = summarizer.summarize(allitems, appeal, category, competitors)
    # 4) (옵션) 상위 글 본문 깊은 요약
    if deep and summarizer.ai_mode():
        top = [it for it in results if (it.get("authentic") or 0) >= 4][:6]
        need = [it["url"] for it in top if not it.get("fulltext")]
        ft = collector.fetch_fulltext_many(need, headless=True)
        summarizer.deep_summarize(top, category, appeal, ft)
    # 5) 조사 개요 + 추이 + VOC 집계
    overview = analytics.build_overview(results, queries)
    trend = analytics.build_trend(results)
    voc = summarizer.build_voc(results, appeal, competitors)

    LAST.update(product=category, product_desc=product_desc, appeal=appeal,
                results=results, overview=overview, trend=trend,
                competitors=competitors, voc=voc)
    return jsonify({"count": len(results), "queries": queries, "results": results,
                    "overview": overview, "trend": trend, "voc": voc,
                    "competitors": competitors,
                    "consumer_queries": plan.get("consumer_queries", []),
                    "competitor_queries": plan.get("competitor_queries", [])})


@app.route("/reviews", methods=["POST"])
def reviews():
    """쿠팡·스마트스토어 상품 리뷰를 로그인 크롬(9222)으로 최신순 수집·평가."""
    data = request.get_json()
    appeal = (data.get("appeal") or LAST.get("appeal") or "").strip()
    category = (data.get("product") or LAST.get("product") or "").strip()
    competitors = LAST.get("competitors", [])
    review_urls = [u.strip() for u in (data.get("review_urls") or "").splitlines() if u.strip()]
    per = int(data.get("per_review") or 20)
    latest_first = data.get("latest_first", True)
    if not review_urls:
        return jsonify({"error": "쿠팡·스마트스토어 상품 URL을 넣어주세요."}), 400

    try:
        raw = review_collector.collect_reviews(review_urls, limit=per, latest_first=latest_first)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    if not raw:
        return jsonify({"error": "리뷰를 가져오지 못했습니다. 로그인 상태·상품 URL을 확인하거나, 쿠팡 봇차단일 수 있어요."}), 200

    # 평가(진짜소비자/감성/인용) + 기존 결과에 합치기
    evaluated = summarizer.summarize(raw, appeal or "(리뷰)", category, competitors)
    merged = evaluated + LAST.get("results", [])
    # url+제목 기준 중복 제거
    seen, dedup = set(), []
    for it in merged:
        k = (it.get("url"), it.get("title"))
        if k in seen:
            continue
        seen.add(k)
        dedup.append(it)
    dedup.sort(key=lambda x: ((x.get("authentic") or 0) + (x.get("relevance") or 0)), reverse=True)
    overview = analytics.build_overview(dedup, [])
    trend = analytics.build_trend(dedup)
    voc = summarizer.build_voc(dedup, appeal, competitors)
    LAST.update(results=dedup, overview=overview, trend=trend, voc=voc)
    return jsonify({"count": len(dedup), "added": len(evaluated), "results": dedup,
                    "overview": overview, "trend": trend, "voc": voc,
                    "competitors": competitors})


@app.route("/export.csv")
def export_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["소스", "제목", "소구관련", "진짜소비자", "감성", "발행월", "요약", "소비자원문", "심층요약", "링크", "검색어"])
    for it in LAST.get("results", []):
        w.writerow([it.get("source"), it.get("title"), it.get("relevance"),
                    it.get("authentic"), it.get("sentiment"), it.get("date"), it.get("summary"),
                    " / ".join(it.get("quotes") or []),
                    (it.get("deep_summary") or "").replace("\n", " "), it.get("url"), it.get("query")])
    out = "﻿" + buf.getvalue()
    return Response(out, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=market_research.csv"})


@app.route("/report.md")
def report_md():
    md = report.build_markdown(LAST.get("product", ""), LAST.get("appeal", ""),
                               LAST.get("results", []), LAST.get("overview", []),
                               LAST.get("trend", {"labels": [], "counts": [], "dated": 0, "total": 0}),
                               LAST.get("competitors", []))
    return Response(md, mimetype="text/markdown",
                    headers={"Content-Disposition": "attachment; filename=market_research.md"})


@app.route("/notion", methods=["POST"])
def to_notion():
    if not LAST.get("results"):
        return jsonify({"ok": False, "msg": "먼저 조사를 실행하세요."})
    res = report.push_to_notion(LAST.get("product", ""), LAST.get("appeal", ""),
                                LAST.get("results", []), LAST.get("overview", []),
                                LAST.get("trend", {"labels": [], "counts": [], "dated": 0, "total": 0}),
                                LAST.get("competitors", []))
    return jsonify(res)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
