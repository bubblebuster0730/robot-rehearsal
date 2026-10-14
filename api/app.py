"""로봇 입주 리허설 — AI 서버 (Render 웹 서비스)
역할: 웹페이지가 보낸 '재료'(기록·결과 요약)를 정해진 틀에 넣어 Claude에게 묻고, JSON만 돌려준다.
- API 키는 이 서버의 환경변수(ANTHROPIC_API_KEY)에만 있다. 페이지에는 없다.
- 자유 문장을 그대로 Claude에 보내지 않는다(틀 고정, 길이 제한).
- 남용 방지: IP당 분당·일당 횟수, 하루 전체 횟수 제한.
"""
import os, json, time
from collections import defaultdict, deque
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from anthropic import Anthropic

MODEL = os.environ.get("MODEL", "claude-haiku-5-5")
ORIGINS = [o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
PER_IP_MIN = int(os.environ.get("PER_IP_PER_MIN", "6"))
PER_IP_DAY = int(os.environ.get("PER_IP_PER_DAY", "60"))
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "500"))

app = FastAPI(title="robot-rehearsal-ai")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
_client = None


def client():
    global _client
    if _client is None:
        _client = Anthropic()  # ANTHROPIC_API_KEY 환경변수를 읽는다
    return _client


# ---------------- 남용 방지(메모리, 서버가 잠들면 초기화) ----------------
_hits = defaultdict(deque)
_day = {"date": "", "n": 0, "ip": defaultdict(int)}


def allow(ip: str) -> bool:
    today = time.strftime("%Y-%m-%d")
    if _day["date"] != today:
        _day.update(date=today, n=0, ip=defaultdict(int))
    if _day["n"] >= DAILY_LIMIT or _day["ip"][ip] >= PER_IP_DAY:
        return False
    q, now = _hits[ip], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= PER_IP_MIN:
        return False
    q.append(now); _day["n"] += 1; _day["ip"][ip] += 1
    return True


def ip_of(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (req.client.host if req.client else "?")


def s(v, n=600) -> str:
    return str(v if v is not None else "")[:n]


# ---------------- 틀(웹페이지 T_DIARY / T_PROPOSE와 같은 내용) ----------------
def t_diary(p):
    recs = []
    for i, r in enumerate((p.get("records") or [])[:6]):
        if isinstance(r, dict):
            recs.append(json.dumps({"i": i, "who": s(r.get("who"), 40), "기록": s(r.get("기록"), 200), "voice": s(r.get("voice"), 120)}, ensure_ascii=False))
    if not recs:
        return None
    return ("너는 건물 입주민의 일지를 대신 쓰는 작가다. 아래 [기록]만 근거로 각 항목마다 1~2문장 일지를 한국어 구어체로 써라.\n"
            "- 기록에 있는 시각·층·시간만 쓴다. 기록에 없는 원인이나 숫자를 지어내지 마라.\n"
            "- voice는 그 유형의 평소 생각이다. 말투와 관심사만 참고한다.\n"
            "- 시간은 '1분 13초'처럼 말하듯 쓴다.\n"
            f"[건물] {s(p.get('building'), 400)}\n[기록]\n" + "\n".join(recs) +
            '\n[출력 — JSON만] {"diaries":[{"i":0,"text":"..."}]}')


def t_propose(p):
    try:
        ncar, fleet = int(p.get("ncar")), int(p.get("fleet"))
    except (TypeError, ValueError):
        return None
    return ("너는 건물 운영 컨설턴트다. 로봇 도입 시뮬레이션 결과를 보고 사람의 불편을 줄일 운영안 3개를 제안하라.\n"
            "결과 수치를 예측하지 마라. 각 안은 시뮬레이터가 같은 입주민 30세트로 다시 계산해 검증한다.\n"
            f"[건물] {s(p.get('building'), 400)}\n[현재 계획] {s(p.get('plan'), 300)}\n[결과 · 30번 평균] {s(p.get('results'), 500)}\n"
            f"[대기가 많이 늘어난 유형] {s(p.get('top'), 300)}\n[허용 기준] {s(p.get('crit'), 120)}\n"
            "[쓸 수 있는 설정 — 이 키만]\n"
            '- order: "fifo"(도착 순) | "people_first"(같은 층에서 사람 먼저)\n'
            "- robot_max_people: 0~15 정수 | null — 엘리베이터 안 사람이 이 인원 이하일 때만 로봇 탑승\n"
            f"- robot_cars: 로봇이 쓸 호기 번호 배열(1~{max(1, min(ncar, 6))}) | null\n"
            f'- clean_start: "HH:MM" | "default" — 청소로봇 출발 시각 ({s(p.get("clean"), 80)})\n'
            "- batch: 1~4 — 배송로봇 1회 최대 주문 수\n"
            f"- delivery_robots: 1~6 — 배송로봇 대수(현재 {max(1, min(fleet, 6))}대). 늘리면 비용이 든다. 3개 안 중 최대 1개에만 쓴다\n"
            "[규칙] 서로 다른 아이디어 3개. 각 안은 현재 계획에서 바꿀 키만 적는다. name은 18자 이내, why는 위 결과의 어떤 수치 때문인지 한 줄.\n"
            '[출력 — JSON만] {"proposals":[{"name":"...","settings":{...},"why":"..."}]}')


def ask(prompt: str, max_tokens: int):
    msg = client().messages.create(model=MODEL, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no json")
    return json.loads(text[a:b + 1])


async def handle(req: Request, build, max_tokens: int):
    if not allow(ip_of(req)):
        return JSONResponse({"error": "rate_limited"}, status_code=429)
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    prompt = build(body) if isinstance(body, dict) else None
    if not prompt or len(prompt) > 6000:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    try:
        return ask(prompt, max_tokens)
    except ValueError:
        return JSONResponse({"error": "invalid_json"}, status_code=422)
    except Exception as e:  # API 키 없음·한도 초과·네트워크 등
        print("upstream error:", type(e).__name__, str(e)[:200])
        return JSONResponse({"error": "upstream_error"}, status_code=502)


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL, "key": bool(os.environ.get("ANTHROPIC_API_KEY")), "today": _day["n"]}


@app.post("/diary")
async def diary(req: Request):
    return await handle(req, t_diary, 700)


@app.post("/propose")
async def propose(req: Request):
    return await handle(req, t_propose, 900)
