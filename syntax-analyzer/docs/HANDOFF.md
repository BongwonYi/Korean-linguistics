# 작업 인계 문서 (클라우드 세션 → 컴퓨터 세션)

작성: 2026-11-10. 새 세션은 이 문서를 먼저 읽고 이어서 작업합니다.

## 1. 프로젝트 개요
- **이름**: 한국어 문장 분석기 (수업용 웹앱, 스마트폰 접속)
- **용도**: 대학 한국어학 수업. 학교문법을 기본으로 하고 의존문법은 참고로 보여 줍니다.
- **구조**: 바른(Bareun) 형태소 분석 API → 학교문법 규칙 엔진 → 문장 성분, 문장 구조, 의존 관계(참고)와 판정 근거 표시
- **장기 목표**: 논항 중심 분석으로 확장. 설계는 `docs/extension-design.md`에 있습니다.

## 2. 현재 상태
| 항목 | 위치 / 상태 |
|---|---|
| 코드 | GitHub `BongwonYi/Korean-linguistics`, 브랜치 `syntax-analyzer-prototype`, 폴더 `syntax-analyzer/` (main에는 아직 합치지 않음) |
| 배포 | Hugging Face Space `bongwonyi/syntax-analyzer`(공개, Docker, 무료 CPU) → https://bongwonyi-syntax-analyzer.hf.space |
| 바른 API 키 | Space Secret `BAREUN_API_KEY`에 사용자가 직접 등록해야 함(등록 여부 확인 필요) |
| 검사 | `python -m pytest tests`: 예문 25개, 28개 검사 통과(바른 호출 없음) |
| 확인 못 한 것 | 배포된 웹앱의 실제 화면(클라우드 세션의 네트워크 제한 때문) |

## 3. 지금까지 결정된 사항
- 웹앱은 바른 **HTTP API**(`POST https://api.bareun.ai/bareun.LanguageService/AnalyzeSyntax`, 헤더 `api-key`)를 서버에서 호출합니다. API 키는 브라우저에 노출하지 않습니다.
- 바른 **MCP**는 개발 중 분석 결과를 시험할 때 사용합니다(웹앱에는 쓰지 않음).
- 호스팅은 Hugging Face Space로 정했습니다. GitHub Pages는 서버를 실행할 수 없어 키를 숨길 수 없으므로 쓰지 않습니다.
- 이름은 '한국어 문장 분석기'로 정했습니다. 접속 주소와 폴더 이름(`syntax-analyzer`)은 유지합니다.
- 바른 무료 구간(클라우드 5만 어절)을 아끼기 위해 결과 캐시, 200자 제한, 1인당 분당 15회, 하루 2,000어절 제한을 두었습니다.

## 4. 주의 사항
- **바른 이용 조건**: 라이선스 정책은 "비상업 목적이라도 사용자 대상 상시 운영 서비스"를 상용으로 봅니다. 정식 수업 운영 전에 바른 측 문의나 연구 목적 무료 신청을 검토해야 합니다.
- **저작권**: GitHub 저장소는 **공개 저장소**입니다. 교재 원문 등 저작권 자료는 올리지 않습니다. 교재에서 뽑은 예문을 평가 세트로 쓸 때도 공개 범위를 사용자와 상의합니다.
- **교재마다 다른 판정**: '-고'의 대등/종속, 종속절과 부사절, '-게'의 어미 처리, 접속 부사의 성분은 화면에 주석으로 표시합니다. 기준 교재가 정해지면 그 기준에 맞춥니다.
- **사용자 응답 원칙**: 확인한 사실, 추론, 제안을 구분합니다. 출처를 밝히고, 확인할 수 없으면 "확인할 수 없습니다"라고 말합니다.

## 5. 다음 할 일 (사용자 결정 대기)
`docs/extension-design.md` 5절의 결정 사항:
1. 분석 범위(의미역까지 갈지)
2. 기준 문법(교재·문법서)
3. 격틀 사전 작성 방식(교사 직접 작성 또는 반자동 후보 생성)
4. 우선순위(분석 엔진 개선 또는 학습 모드)

'한국어학' 폴더 자료로 할 수 있는 일:
- 교재 예문을 모아 평가 세트(정답: 성분, 자릿수, 논항)를 만듭니다. 형식은 `tests/test_grammar.py` 참고
- 교재에 나오는 서술어로 격틀 사전 v0 후보를 만듭니다. 형식은 설계 문서 A1 참고
- 교재의 문법 기준을 확인해 기준 교재 결정을 돕습니다.

## 6. 새 세션에서 준비할 것
1. 저장소 받기
   ```bash
   git clone -b syntax-analyzer-prototype https://github.com/BongwonYi/Korean-linguistics.git
   ```
2. 실행에 필요한 패키지 설치
   ```bash
   pip install -r Korean-linguistics/syntax-analyzer/requirements.txt pytest
   ```
3. 바른 API 키
   - 클라우드 환경에 저장한 키는 컴퓨터 세션에서 쓸 수 없습니다.
   - 로컬 실행 시에는 환경 변수 `BAREUN_API_KEY`로 설정합니다.
4. (선택) 바른 MCP 연결. 공식 문서의 Claude Code 연결 방법:
   ```bash
   claude mcp add --transport http bareun https://api.bareun.ai:443/mcp --header "api-key: 발급받은_API_키"
   ```

## 7. 주요 파일
- `app/grammar.py`: 학교문법 규칙 엔진(판정 규칙과 근거 문장)
- `app/main.py`: 웹 서버(바른 호출, 캐시, 사용량 제한)
- `static/`: 스마트폰 화면
- `tests/fixtures/`: 바른 분석 결과 예문 25개
- `docs/extension-design.md`: 논항 중심 확장 설계안
