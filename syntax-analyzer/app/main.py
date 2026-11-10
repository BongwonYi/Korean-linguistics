"""문장 성분 분석기 웹 서버 (FastAPI).

- 브라우저는 이 서버의 /api/analyze 만 호출하고, 바른 API 키는 서버 환경 변수에만 둔다.
- 무료 구간(5만 어절)을 아끼기 위해 결과 캐시, 입력 길이 제한, 접속자별·하루 사용량 제한을 둔다.
- 예문은 tests/fixtures 에 저장된 바른 분석 결과를 쓰므로 API를 호출하지 않는다.
"""

from __future__ import annotations

import json
import os
import time
from collections import OrderedDict, defaultdict, deque
from datetime import date
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .grammar import analyze_response

BASE = Path(__file__).resolve().parent.parent
STATIC = BASE / "static"
FIXTURES = BASE / "tests" / "fixtures"

BAREUN_URL = os.environ.get("BAREUN_URL", "https://api.bareun.ai").rstrip("/")
BAREUN_API_KEY = os.environ.get("BAREUN_API_KEY", "")
MAX_CHARS = int(os.environ.get("MAX_CHARS", "200"))
PER_IP_PER_MIN = int(os.environ.get("PER_IP_PER_MIN", "15"))
DAILY_EOJEOL_LIMIT = int(os.environ.get("DAILY_EOJEOL_LIMIT", "2000"))
CACHE_SIZE = int(os.environ.get("CACHE_SIZE", "1000"))

app = FastAPI(title="문장 성분 분석기", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_cache: OrderedDict[str, dict] = OrderedDict()
_hits: dict[str, deque] = defaultdict(deque)
_usage = {"day": date.today().isoformat(), "eojeols": 0}


class AnalyzeIn(BaseModel):
    text: str


def _client_ip(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (req.client.host if req.client else "?")


def _rate_ok(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= PER_IP_PER_MIN:
        return False
    q.append(now)
    return True


def _reset_day() -> None:
    today = date.today().isoformat()
    if _usage["day"] != today:
        _usage["day"] = today
        _usage["eojeols"] = 0


async def call_bareun(text: str) -> dict:
    if not BAREUN_API_KEY:
        raise HTTPException(503, "서버에 바른 API 키(BAREUN_API_KEY)가 설정되어 있지 않습니다.")
    body = {
        "document": {"content": text, "language": "ko_KR"},
        "encoding_type": "UTF16",
        "auto_split_sentence": True,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{BAREUN_URL}/bareun.LanguageService/AnalyzeSyntax",
            json=body,
            headers={"api-key": BAREUN_API_KEY},
        )
    if r.status_code in (401, 403):
        raise HTTPException(502, "바른 API 인증에 실패했습니다. API 키를 확인해 주세요.")
    if r.status_code != 200:
        raise HTTPException(502, f"바른 API 오류 (HTTP {r.status_code})")
    return r.json()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
def healthz():
    _reset_day()
    return {"ok": True, "key_configured": bool(BAREUN_API_KEY),
            "today_eojeols": _usage["eojeols"], "daily_limit": DAILY_EOJEOL_LIMIT}


@app.get("/api/examples")
def examples():
    """저장된 예문(바른 분석 결과)을 API 호출 없이 돌려준다."""
    out = []
    for f in sorted(FIXTURES.glob("s*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        res = analyze_response(data)
        text = " ".join(s["text"] for s in res["sentences"])
        out.append({"text": text, "result": res})
    return out


@app.post("/api/analyze")
async def analyze(inp: AnalyzeIn, req: Request):
    text = " ".join(inp.text.split())
    if not text:
        raise HTTPException(400, "문장을 입력해 주세요.")
    if len(text) > MAX_CHARS:
        raise HTTPException(400, f"한 번에 {MAX_CHARS}자까지 분석할 수 있습니다.")

    if text in _cache:
        _cache.move_to_end(text)
        return JSONResponse({**_cache[text], "cached": True})

    if not _rate_ok(_client_ip(req)):
        raise HTTPException(429, "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.")
    _reset_day()
    if _usage["eojeols"] >= DAILY_EOJEOL_LIMIT:
        raise HTTPException(429, "오늘의 분석 한도에 도달했습니다. 내일 다시 이용해 주세요.")

    raw = await call_bareun(text)
    _usage["eojeols"] += int(raw.get("tokensCount", 0) or 0)
    result = analyze_response(raw)
    _cache[text] = result
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return JSONResponse({**result, "cached": False})
