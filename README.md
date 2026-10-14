# 로봇 입주 리허설

로봇을 들이기 전에 BIM 도면 위에서 미리 살아 보는 웹 시뮬레이터입니다.

- `site/` 웹페이지. 계산은 방문자 브라우저에서 합니다(Pyodide = 브라우저용 Python 3.12, 시뮬레이터 원본 코드 그대로).
- `api/` AI 서버. 입주민 일지와 개선안 제안만 Claude에게 묻습니다. API 키는 이 서버 환경변수에만 둡니다.
- `render.yaml` Render Blueprint(두 서비스를 한 번에 만듦).

## 설정값
- rr-api: `ANTHROPIC_API_KEY`(필수), `MODEL`(기본 claude-haiku-5-5), `DAILY_LIMIT`(하루 전체 요청 수), `PER_IP_PER_DAY`, `PER_IP_PER_MIN`, `ALLOWED_ORIGINS`(기본 *)
- rr-site: `AI_BASE` = rr-api 주소(예: https://rr-api-xxxx.onrender.com). 바꾸면 rr-site를 다시 배포해야 반영됩니다.
