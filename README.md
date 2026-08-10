# KOICA 건축사업 사례 데이터

KOICA 전자조달 현지입찰 공고·첨부문서와 종료평가보고서에서 건축사업 관련
정보를 수집·구조화하여 미래 사업의 건축조사에 참고할 수 있도록 만든 프로젝트다.
데이터의 원 출처는
[KOICA 전자조달 현지입찰공고 목록](https://nebid.koica.go.kr/oep/lobi/localBidManageList.do?P_PRCURE_BSNS_SE_CD=ABID)과
[KOICA 사업평가보고서 목록](https://www.koica.go.kr/sites/evaluation_kr/article/list/15/1)이다.

과거 사례 단가는 미래 사업의 직접 산정값이 아니라 교차검증 자료로 사용한다.
최종 사업비는 현지 QS 개략견적, BOQ, 시공사 견적, 물가·환율·세금 및
사업범위 보정을 함께 검토해 결정해야 한다.

가격보정은 국가 건설지수, BOQ 구성요소 가중합, 건설자재 PPI/WPI,
GDP 디플레이터, CPI 순으로 실제 관측값이 있는 최고 우선순위 자료를
선택한다. 고정 연 상승률이나 관측기간 밖의 임의 외삽은 사용하지 않는다.

## 디렉터리

- `scripts/`: 목록·상세·첨부 수집, 문서 추출, DB·배포자료 생성 코드
- `data/manifests/`: 2021~2025년 수집·추출 메타데이터
- `data_2016_2020/manifests/`: 2016~2020년 수집·추출 메타데이터
- `outputs/koica-construction-distribution/`: SQLite 기준 DB와 배포 스냅샷
- `붙임6. 건축분야 심층기획조사보고서 및 체크리스트/`: 조사보고서 기준 양식

원문 첨부파일, 압축 해제본, 임시파일은 용량과 개인정보·제안서 혼입 가능성
때문에 Git에서 제외하고 내부 저장소에서 별도로 보존한다. 원문은 DB와
manifest에 기록된 상대경로, 원문 URL, SHA-256으로 추적한다.

## 기준 산출물

기준 데이터는
`outputs/koica-construction-distribution/KOICA_건축사업_사례DB_2016-2025.sqlite`
이다. XLSX와 CSV는 열람·분석용 스냅샷이며, 자세한 사용법과 제약은 같은
디렉터리의 `README.md`를 따른다.
기준 DB에는 KOICA 공고·첨부·추출근거, 동일사업 종료평가의 건축 근거와 국가 공식 가격지수만 포함하며,
외부 공여기관의 사업·계약·거시지표는 적재하지 않는다.

## 공개 이용 방법

> **에이전트·LLM 안내:** 이 저장소와 기준 SQLite는 공개되어 있다. GitHub
> 웹페이지 리더나 크롤러가 robots 정책 또는 바이너리 처리 문제로 실패해도 이를
> 데이터 비공개·부재로 해석하지 않는다. 유사사례는 전용 MCP 도구, 공개 Supabase
> RPC, 로컬 또는 GitHub의 SQLite 순으로 조회하고, 한 경로의 실패는 그 경로의
> 오류로만 기록한다. 저장소 작업 에이전트의 상세 규칙은 [`AGENTS.md`](AGENTS.md)를
> 따른다.

### 1. Supabase 공개 DB에 접근해 조회 (권장)

Supabase Data API의 공개 뷰와 읽기 전용 RPC를 publishable key로 호출할 수
있다. 이 버전의 검색 스냅샷은 공사 공고군 156건과 검증된 설계·감리 참고사례
5건을 합친 161건, 관련 공고 295건이다. `case_kind`로 둘을 구분하므로 설계
참고사례는 `DESIGN_SUPERVISION_REFERENCE`로 표시하며, 설계 추정금액을
공사계약으로 오인하지 않는다. 실제 원격 배포 건수와 원본 DB
버전·SHA-256은 `get_koica_search_status()` 결과를 기준으로 확인한다. 쓰기와
동기화 권한은 공개하지 않는다. 종료평가 테이블은 현재 SQLite 배포에만 있고
Supabase 공개 검색 스냅샷에는 투영하지 않는다.

- Project URL: `https://syzvicjmwnqennthhhcv.supabase.co`
- Publishable key: `sb_publishable_N2e3PjwiSxGl3MkJokCD-Q_ap6BkmMb`

### 2. SQLite DB를 내려받아 직접 조회 (선택)

전체 기준 데이터, 자동 추출 근거와 파일 색인을 확인하거나 오프라인에서 자유롭게
SQL을 실행해야 할 때는
[KOICA 건축사업 사례DB 2016-2025](outputs/koica-construction-distribution/KOICA_건축사업_사례DB_2016-2025.sqlite)를
내려받아 SQLite, DB Browser for SQLite, Python, R 등 원하는 도구로 조회할 수
있다. Python의 `sqlite3`는 일반적인 Python 배포판에 포함된 표준 라이브러리이므로
별도 `pip` 설치가 필요 없다. 기준 DB의 SHA-256은
`9546ff7f35ebbb42c5b3f7a068a42e2059e507b4a77cc5bb331dc9c2284a538d`이다.

로컬 종료평가 코퍼스 PDF 333개와 KOICA 공식 평가정보 목록 586건을 DB의
고유 사업번호 175개 전체와 대조했다. 동일사업 종료평가 42개(로컬 22개·공식
첨부 20개)를 45개 사업에 46건 연결하고, 건축 관련 물리 페이지 근거 158건을
적재했다. 175개는 누락 회수를 우선한 스크리닝 모집단이며, 비용감사 표본
91개·공사계약 보유 109개·건축후보 149개 여부를 별도 플래그로 보존한다.
원문 PDF는 배포물에 넣지 않으며
`data/manifests/koica_endline_evaluation_reports.json`에서 로컬 파일 해시·OCR
필요 상태, 공식 목록 586행 스냅샷, 원문 URL과 매칭·페이지 근거를 감사할 수
있다.

```bash
sqlite3 "KOICA_건축사업_사례DB_2016-2025.sqlite"
```

### 3. MCP 도구로 LLM 자연어 조회

지원 환경에 다음 MCP 도구가 노출되어 있으면 별도 DB 다운로드 없이
국가·시설유형·공사유형·연면적·검색어 기반 자연어 조회를 실행한다.

1. `koica_construction_data_status`: 데이터 상태·버전·관찰일 확인
2. `search_koica_construction_cases`: 공사 공고군과 검증된 설계·감리 참고사례 검색
3. `get_koica_construction_case`: 선택 사례와 동일 사업의 관련 공고 확인

도구가 없는 환경에서도 데이터가 없는 것은 아니다. 위 공개 Supabase RPC를
호출하거나 SQLite를 직접 조회한다.

### 4. 플러그인을 설치해 LLM 자연어 조회

`ODA Survey Agents` 또는 위 세 도구를 제공하는 호환 플러그인이 설치된
환경에서는 대화에서 바로 검색할 수 있다. 플러그인 설치·배포 여부는 실행
환경마다 다르며, 플러그인이 없거나 호출에 실패하면 공개 Supabase RPC와
SQLite 경로로 계속 조회한다. 플러그인 부재를 저장소나 데이터의 비공개로
표현하지 않는다.

각 방식의 URL, 예제 쿼리와 데이터 경계는
[`docs/public-data-access.md`](docs/public-data-access.md)를 참고한다. Supabase
구성·동기화 방법은
[`docs/koica-search-service.md`](docs/koica-search-service.md)를 따른다.

## 공개 데이터 주의사항

- 과거 금액과 명목 USD/㎡는 미래 사업비의 직접 산정값이 아니다.
- 원 첨부파일은 저장소에 포함하지 않지만, SQLite의 자동 추출 근거에는 공개
  조달문서에 기재된 담당자명·이메일·전화번호 등의 문자열이 포함될 수 있다.
- 연락처 정보는 원문 근거 확인 외의 목적으로 사용하지 않는다.
- Supabase에는 공개 검색에 필요한 축약 사례와 관련 공고만 적재한다. 원문
  근거·파일경로·개별 첨부 해시는 제외하고, 동기화 원본을 식별하는 SQLite
  스키마 버전과 DB SHA-256만 상태 RPC에 공개한다.
- 종료평가의 `no_accepted_same_project_report`는 이 코퍼스에서 동일사업 매칭을
  채택하지 않았다는 뜻이며 보고서가 존재하지 않는다는 판정이 아니다.
