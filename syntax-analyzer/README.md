---
title: 한국어 문장 분석기
emoji: 🌳
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# 한국어 문장 분석기 (시제품)

바른(Bareun) 형태소 분석 결과를 바탕으로 **학교문법의 문장 성분과 문장 구조**를 판정하고,
**의존 관계**를 참고 정보로 보여 주는 수업용 웹앱입니다. 스마트폰 브라우저에서 쓸 수 있습니다.

```
스마트폰 브라우저 ──▶ 이 서버(/api/analyze) ──▶ 바른 API(형태소 분석)
                          │
                          └─ 학교문법 규칙 엔진(app/grammar.py) → 문장 성분·절·의존 관계 + 판정 근거
```

- API 키는 서버 환경 변수(`BAREUN_API_KEY`)에만 있고 브라우저에는 전달되지 않습니다.
- 웹앱은 MCP가 아니라 바른 HTTP API(`POST /bareun.LanguageService/AnalyzeSyntax`)를 직접 호출합니다.
  바른 MCP는 Claude Code 같은 AI 도구에서 분석 결과를 시험해 볼 때 쓰면 됩니다.

## 판정하는 내용

| 구분 | 판정 근거(바른 태그) |
|---|---|
| 주어 | 주격 조사 JKS(이/가/께서), 보조사 JX(은/는/도 …)는 '추정' |
| 목적어 | 목적격 조사 JKO(을/를), 명사절+을/를 |
| 보어 | 보격 조사 JKC(되다/아니다 앞의 이/가) |
| 서술어 | 용언 어간(VV·VA·VX·VCN), 체언+이다(VCP), 본용언+보조 용언은 묶어서 처리 |
| 관형어 | 관형사(MM*), 관형격 조사 JKG, 관형사형 어미 ETM(관형절), 체언 단독 |
| 부사어 | 부사(MAG), 부사격 조사 JKB, 인용절(JKQ), 부사절(-게/-도록, 없이/같이/달리) |
| 독립어 | 감탄사(IC), 호격 조사(JKV), 접속 부사(MAJ: 교재에 따라 독립어/부사어) |
| 문장 구조 | 홑문장/겹문장, 이어진문장(대등·종속), 안은문장(명사절·관형절·부사절·서술절·인용절) |

형태 정보만으로 정할 수 없는 경우(조사 생략, 보조사 결합 등)는 점선 테두리와 '?'로 **추정**임을 표시합니다.
교재마다 처리가 다른 항목(예: '-고'의 대등/종속, 종속절과 부사절, '-게'의 어미 처리, 접속 부사)은 판정 근거에 주석을 붙였습니다.

## 서술어 격틀(논항 구조)

서술어마다 어떤 자리를 어떤 조사로 요구하는지 적은 격틀 사전으로 자릿수, 필수적 부사어, 생략된 자리,
관형절의 빈자리(관계/동격)를 판정합니다. 결과는 문장별 `argument_structure`에 들어갑니다.

| 파일 | 내용 |
|---|---|
| `app/frames_krdict.json` | **기본 격틀.** 국립국어원 「한국어기초사전」 전체 내려받기(2026-10-19)의 문형(예: '1이 2에/에게 3을 주다')을 자동 변환한 것. 동사·형용사 13,230개, 격틀 17,491개. 사람 검토 없음 |
| `app/frames_override.json` | 표제어 단위로 기본 격틀을 바꿔 끼우는 교사 판정. 지금은 서술격 조사 '이다'(기초사전은 용언으로 싣지 않음) |
| `app/frames_v0.json` | 처음 손으로 만든 37개 서술어 격틀(비교·평가용) |

- 다른 격틀 파일로 시험하려면 환경 변수 `SYNTAX_FRAMES`에 경로를 줍니다(이때는 덮어쓰기 파일을 쓰지 않음).
- 기초사전과 교재(학교 문법)의 판정이 다른 곳이 있습니다. 예: 기초사전은 '다르다·닮다·관련되다'의 '와/과' 자리를
  수의적(괄호)으로 표시하지만, 교재는 필수적 부사어로 봅니다. 기준이 정해지면 `frames_override.json`에 반영합니다.
- 격틀을 다시 만들려면 저장소 밖의 변환 도구(기초사전 전체 내려받기 → 문형 추출 → `make_auto_frames.py`)를 씁니다.

**출처와 이용 조건**: `frames_krdict.json`은 국립국어원 한국어기초사전(https://krdict.korean.go.kr)의
문형 정보를 가공한 2차 저작물이며, 원 자료의 이용 조건에 따라 **CC BY-SA 2.0 KR**로 배포합니다.

## 바른 무료 구간 보호 장치

클라우드 무료 구간은 5만 어절입니다(바른 라이선스 정책 문서 기준). 이를 아끼기 위해 다음을 둡니다.

| 환경 변수 | 기본값 | 뜻 |
|---|---|---|
| `MAX_CHARS` | 200 | 한 번에 분석할 수 있는 글자 수 |
| `PER_IP_PER_MIN` | 15 | 접속자 한 명이 1분에 보낼 수 있는 요청 수 |
| `DAILY_EOJEOL_LIMIT` | 2000 | 하루 최대 분석 어절 수(서버 재시작 시 초기화) |
| `CACHE_SIZE` | 1000 | 같은 문장은 저장된 결과를 다시 사용 |

예문 25개는 `tests/fixtures`에 저장된 바른 분석 결과를 쓰므로 사용량이 차감되지 않습니다.
사용량은 서버 `/healthz`와 bareun.ai 로그인 화면에서 확인할 수 있습니다.

## Hugging Face Space에 올리기

1. Hugging Face에서 **New Space** → SDK는 **Docker** → Blank 선택. 하드웨어는 무료 CPU로 충분합니다.
2. Space의 **Settings → Variables and secrets → New secret**에서 `BAREUN_API_KEY`를 등록합니다.
   (Secret은 등록 후 설정 화면에서 다시 읽을 수 없고, 앱 실행 시 환경 변수로 전달됩니다.)
3. 이 폴더(`syntax-analyzer/`)의 내용을 Space 저장소 **최상위**에 올립니다.
   ```bash
   git clone https://huggingface.co/spaces/<아이디>/<스페이스이름> space
   cp -r syntax-analyzer/* space/
   cd space && git add . && git commit -m "한국어 문장 분석기" && git push
   ```
4. 빌드가 끝나면 `https://huggingface.co/spaces/<아이디>/<스페이스이름>` 주소로 접속합니다.

git 인증이 번거로우면 Hub API로 올리는 스크립트를 씁니다(쓰기 권한 토큰 필요).
토큰은 Windows 자격 증명 관리자(keyring 서비스 `huggingface`, 이름 `api_key`)나 환경 변수 `HF_TOKEN`에서 읽습니다.
```bash
pip install huggingface_hub keyring
python -m tools.deploy_space            # 기본: bongwonyi/syntax-analyzer
python -m tools.deploy_space --space <아이디>/<스페이스이름>
```

## 로컬에서 실행·검사

```bash
pip install -r requirements.txt pytest
BAREUN_API_KEY=발급받은키 uvicorn app.main:app --port 7860   # http://localhost:7860
python -m pytest tests                                          # 바른 API를 호출하지 않는 규칙 검사
python -m tools.show                                            # 예문 25개의 판정 결과 출력
```

## 파일 구성

```
app/main.py        웹 서버(FastAPI): 바른 호출, 캐시·사용량 제한, 예문 제공
app/grammar.py     학교문법 규칙 엔진(격틀로 자리 채우기 포함)
app/frames_*.json  서술어 격틀 사전(위 '서술어 격틀' 참고)
app/tags.py        바른 47품사 태그 이름과 학교문법 품사 대응
static/            스마트폰용 화면(HTML·CSS·JS)
tests/             예문(sentences.txt), 바른 분석 결과(fixtures), 규칙 검사
tools/show.py      예문 판정 결과를 표로 출력
```

## 알려진 한계

- 부사어를 서술어에 연결할 때는 아직 격틀을 쓰지 않아서, '학교에 간 사람', '발에 땀이 나도록'처럼
  안긴 절 안의 부사어를 주절 서술어에 연결할 수 있습니다.
- 보조사(은/는/도)가 붙은 체언은 격틀의 빈자리로 성분을 추정합니다('사과는 내가 먹었다' → 목적어). 문맥이 필요한 경우는 틀릴 수 있습니다.
- 한 서술어에 뜻이 여럿이면 문장에 가장 잘 맞는 격틀을 고르지만, 논항이 많이 생략된 절에서는 자리가 적은 뜻을 고르기 쉽습니다.
- 형태소 분석이 틀리면 성분 판정도 틀립니다(예: 띄어쓰기 오류가 많은 문장).

## 참고 자료

- 바른 형태소 분석 API: https://bareun.ai/docs/ko/3.4.0/howtouse/api-analyze
- 바른 프로토콜 선택(REST 경로): https://bareun.ai/docs/ko/3.4.0/howtouse/integration/protocol-choice
- 바른 라이선스 정책: https://bareun.ai/docs/ko/3.4.0/faq/license-policy
- Hugging Face Docker Spaces: https://huggingface.co/docs/hub/spaces-sdks-docker
