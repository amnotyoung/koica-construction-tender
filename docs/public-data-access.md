# KOICA 건축사업 공개 데이터 이용 안내

이 프로젝트는 같은 KOICA 건축사업 데이터를 네 가지 방식으로 이용할 수 있게
제공한다. 대부분의 사용자에게는 별도 DB 다운로드나 SDK 설치 없이 공개 검색용
읽기 전용 데이터에 접근하는 Supabase 방식을 권장한다. 전체 기준 DB와 자동 추출
근거가 필요하거나 오프라인에서 자유롭게 SQL을 실행하려면 SQLite를 선택적으로
이용한다.

## 1. Supabase 공개 DB 이용 (권장)

### 접속 정보

```text
Project URL: https://syzvicjmwnqennthhhcv.supabase.co
Publishable key: sb_publishable_N2e3PjwiSxGl3MkJokCD-Q_ap6BkmMb
```

publishable key는 공개 클라이언트용 식별자이며 비밀키가 아니다. 실제 데이터
접근 범위는 Postgres 권한과 RLS가 제한한다. secret/service-role 키는 공개하지
않으며 동기화 작업에만 사용한다. 웹 브라우저, `curl` 등 HTTP를 지원하는 도구로
호출할 수 있으며 Supabase SDK, CLI와 PostgreSQL 드라이버는 필수가 아니다.

### 공개 뷰

| 뷰 | 내용 |
|---|---|
| `koica_construction_cases` | 공사 공고군 156건 + 검증된 설계·감리 참고사례 5건 |
| `koica_construction_related_notices` | 같은 사업의 설계·감리 등 관련 공고 295건 |
| `koica_evaluation_projects` | 고유 사업번호 175개의 종료평가 대조 상태 |
| `koica_evaluation_reports` | 채택된 종료평가 보고서 42개의 공개 메타데이터 |
| `koica_evaluation_findings` | 46개 매칭에서 추출·승인한 건축 근거 158건 |

`case_kind`가 `CONSTRUCTION_NOTICE`이면 공사 공고군이고,
`DESIGN_SUPERVISION_REFERENCE`이면 면적·공사비·근거등급이 검토된 설계·감리
단계 참고사례다. 후자의 `construction_cost_usd`는 공사계약액이 아니며
`amount_stage_code`의 `DESIGN_ESTIMATE` 또는 `CONSTRUCTION_BUDGET`과 함께
해석한다. `facility_family`는 `facility_type`이 `기타·미분류`처럼 거친 경우를
보완하는 대분류다.

위 사례·평가 데이터는 이 버전의 동기화 대상이다. 실제 원격 배포 상태는
`get_koica_search_status()`의 전체·유형별 건수와 원본 DB 버전·SHA-256으로
확인한다. 평가 공개 뷰에는 보고서 제목, 공식 원문 URL이 있는 경우 그 URL,
물리 PDF 페이지, 구조화 요약과 공개 승인 근거 발췌가 포함된다. 로컬 파일경로,
파일 해시, OCR 다이제스트와 내부 검토 메모는 포함하지 않는다.

```bash
SUPABASE_URL="https://syzvicjmwnqennthhhcv.supabase.co"
SUPABASE_KEY="sb_publishable_N2e3PjwiSxGl3MkJokCD-Q_ap6BkmMb"

curl -sS --get \
  "$SUPABASE_URL/rest/v1/koica_construction_cases" \
  -H "apikey: $SUPABASE_KEY" \
  --data-urlencode "select=case_id,case_kind,country_ko,facility_type,facility_family,gross_floor_area_m2,construction_cost_usd,amount_stage_code,nominal_unit_usd_m2,evidence_grade,procurement_url" \
  --data-urlencode "country_ko=eq.우간다" \
  --data-urlencode "limit=10"
```

### 공개 읽기 RPC

| 도구 | Supabase RPC |
|---|---|
| `koica_construction_data_status` | `get_koica_search_status()` |
| `search_koica_construction_cases` | `search_koica_construction_cases(...)` |
| `get_koica_construction_case` | `get_koica_reference_case(p_case_id)` |
| 종료평가 근거 검색 | `search_koica_evaluation_findings(...)` |
| 사업별 종료평가 상세 | `get_koica_project_evaluation_findings(p_project_no)` |

```bash
# 원본 DB 버전·SHA-256·감사일·동기화일·유형별 건수
curl -sS -X POST \
  "$SUPABASE_URL/rest/v1/rpc/get_koica_search_status" \
  -H "apikey: $SUPABASE_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'

# 국가·시설유형·공사유형·연면적·검색어 기반 유사사례 검색
curl -sS -X POST \
  "$SUPABASE_URL/rest/v1/rpc/search_koica_construction_cases" \
  -H "apikey: $SUPABASE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "p_target_text": "학교",
    "p_target_country": "우간다",
    "p_target_facility_type": "교육시설",
    "p_target_work_type": "신축",
    "p_target_area_m2": 3000,
    "p_max_results": 10
  }'

# 사례 상세, 같은 사업의 관련 공고와 종료평가 근거
curl -sS -X POST \
  "$SUPABASE_URL/rest/v1/rpc/get_koica_reference_case" \
  -H "apikey: $SUPABASE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"p_case_id":"L2019-00016"}'

# 국가·검색어·근거유형으로 종료평가의 건축 근거 검색
curl -sS -X POST \
  "$SUPABASE_URL/rest/v1/rpc/search_koica_evaluation_findings" \
  -H "apikey: $SUPABASE_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "p_query": "병원 유지관리",
    "p_country": "캄보디아",
    "p_category": "operations_maintenance",
    "p_max_results": 20
  }'

# 사업번호 하나의 대조 상태·보고서·공개 승인 근거 전체
curl -sS -X POST \
  "$SUPABASE_URL/rest/v1/rpc/get_koica_project_evaluation_findings" \
  -H "apikey: $SUPABASE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"p_project_no":"2013-00007"}'
```

사례 검색 결과는 최대 50건, 종료평가 근거 검색은 최대 100건으로 제한된다.
`anon`과 `authenticated`에는 `SELECT`와
위 조회 RPC 실행 권한만 있고 `INSERT`, `UPDATE`, `DELETE`와 동기화 RPC 실행
권한은 없다. 검색 인수는 순위 신호이지 SQL의 엄격한 필터가 아니므로, 답변에
사용할 행의 국가·시설대분류·공종·면적과 `case_kind`를 다시 확인한다.

## 2. SQLite DB 직접 이용 (선택)

### 다운로드와 검증

- [KOICA 건축사업 사례DB 2016-2025](../outputs/koica-construction-distribution/KOICA_건축사업_사례DB_2016-2025.sqlite)
- 파일 크기: 8,290,304 bytes
- SHA-256: `9546ff7f35ebbb42c5b3f7a068a42e2059e507b4a77cc5bb331dc9c2284a538d`

```bash
shasum -a 256 "KOICA_건축사업_사례DB_2016-2025.sqlite"
sqlite3 "KOICA_건축사업_사례DB_2016-2025.sqlite"
```

기준 DB에는 공고 575건, 건축 후보 379건, 첨부파일 색인 1,000건, 분석문서
색인 3,698건, 자동 추출 근거 4,402건과 91개 사업의 면적·공사비 재검토 결과가
들어 있다. 또한 로컬 종료평가 PDF 333개의 무결성·텍스트 상태와
[KOICA 공식 평가정보 목록](https://www.koica.go.kr/sites/evaluation_kr/article/list/15/1)
586건의 게시물 ID·목록 페이지·제목 스냅샷과 인덱스 다이제스트를 기록하고,
DB 고유 사업번호 175개 전체를 스크리닝했다. 동일사업 보고서 42개(로컬
22개·공식 첨부 20개)를 45개 사업에 46건 연결한 건축 페이지 근거 158건을
포함한다. 175개 모집단에는 비용감사 표본 91개, 공사계약 보유 109개,
건축후보 149개 여부를 각각 표시했다. 원 첨부파일과 종료평가 PDF 자체는
포함하지 않는다.

### 예제 쿼리

```sql
-- 테이블과 뷰 확인
.tables

-- 면적·공사비 근거가 준비된 사업
SELECT project_no,
       country_ko,
       project_name,
       best_grade,
       representative_area_m2,
       representative_construction_cost_usd,
       screening_unit_usd_m2,
       display_representative_bid
FROM v_area_cost_ready_projects
ORDER BY country_ko, best_grade, project_no;

-- 특정 국가의 유사사례
SELECT bid_no,
       notice_date,
       country,
       facility_type,
       work_type,
       gross_floor_area_m2,
       unit_usd_m2_nominal,
       evidence_grade,
       source_url
FROM reviewed_cases
WHERE country = 'Nepal'
ORDER BY notice_date DESC;

-- 특정 공고의 추출 근거
SELECT category, source_file, source_locator, evidence_text
FROM evidence
WHERE bid_no = 'L2022-00029-1';

-- 종료평가의 건축 주요 내용과 물리 PDF 페이지 근거
SELECT project_no, country_ko, project_name, report_title,
       category, field_code, summary_text,
       pdf_page_start, evidence_excerpt
FROM v_project_evaluation_findings
WHERE project_no = '2013-00007'
ORDER BY pdf_page_start, finding_id;

-- 고유 사업번호 175개 전체의 종료평가 대조 상태
SELECT status, COUNT(*)
FROM evaluation_project_screening
GROUP BY status;
```

전체 테이블 사전과 해석 원칙은
[`outputs/koica-construction-distribution/README.md`](../outputs/koica-construction-distribution/README.md)에
정리되어 있다.

## 3. MCP 도구로 LLM 자연어 조회

지원 환경에 다음 MCP 도구가 노출되어 있으면 공개 검색 RPC를 감싼 읽기 전용
자연어 조회 경로로 사용한다.

- `koica_construction_data_status`
- `search_koica_construction_cases`
- `get_koica_construction_case`

공개 Supabase RPC가 기본 조회 경로다. MCP가 있는 환경에서는 상태 도구로
`data_status`, `observed_at`, `missing_is_zero`를 확인하고 검색한 뒤 답변에 실제
사용할 사례만 상세조회하는 편의 경로로 쓸 수 있다. MCP 도구가 보이지 않거나
호출에 실패하면 이 문서의 Supabase RPC를 직접 호출한다. 네트워크 자체를 사용할
수 없고 저장소 체크아웃이 있으면 SQLite를 읽기 전용으로 조회한다.

## 4. 플러그인으로 LLM 자연어 조회

`ODA Survey Agents` 또는 위 세 도구를 제공하는 호환 플러그인이 설치된 Codex 등
지원 환경에서는 대화형으로 조회할 수 있다. 플러그인 배포·설치 상태는 실행
환경의 기능이며 공개 데이터의 가용성과는 별개다. 플러그인이 없어도 Supabase와
SQLite 공개 경로는 그대로 사용할 수 있다.

## 에이전트 실패 처리 원칙

- 이 GitHub 저장소와 기준 SQLite는 공개 자료다.
- GitHub 웹 리더의 robots 정책 또는 바이너리 처리 오류는 해당 리더의 실패일
  뿐, 저장소 비공개나 데이터 부재의 근거가 아니다.
- 공개 Supabase RPC를 먼저 호출하고, 전용 MCP 도구, 로컬 SQLite, GitHub raw
  파일 중 사용할 수 있는 다음 경로로 재시도한다.
- 모든 경로가 실패한 경우에만 판단을 유보하며, 시도한 경로와 실제 오류를 각각
  밝힌다.
- 성공한 검색 결과는 `project_no`로 재공고를 묶고, 같은 진행 문구를 반복하는
  대신 실제 사례와 근거를 제시한다.
- `facility_type`만으로 의료·교육 사례를 제외하지 않는다. `facility_family`와
  검색어를 함께 보고, `case_kind`로 공사 공고와 설계·감리 참고사례를 구분한다.
- 감사일이 같아도 DB 스키마 버전이 같다는 뜻은 아니다. 상태 RPC의
  `source_schema_version`과 `source_db_sha256`을 확인한다.

## 데이터 이용 시 주의

- 공사비와 명목 USD/㎡는 물가·환율·세금·사업범위 보정 전 참고값이다.
- 미래 사업비는 현지 QS 견적, BOQ, 시공사 견적과 국가별 실제 가격지수를
  주자료로 산정한다.
- SQLite의 `evidence`에는 공개 조달문서에서 자동 추출한 근거 문장과 원문에
  기재된 담당자명·이메일·전화번호가 포함될 수 있다. 원문 근거 확인 외의
  목적으로 연락처를 사용하지 않는다.
- Supabase 공개 데이터에는 공개 승인된 종료평가 발췌와 물리 페이지는 포함하지만,
  조달 원문 근거, 로컬 파일경로, 개별 파일·첨부 SHA-256, OCR 다이제스트와 내부
  검토 메모는 포함하지 않는다. 상태 RPC에는 현재 원본 SQLite를 식별하는 DB
  SHA-256만 공개한다.
- `no_accepted_same_project_report`는 이 코퍼스에서 동일사업 매칭을 채택하지
  않았다는 의미일 뿐, 종료평가 보고서의 부재를 입증하지 않는다. OCR 필요 파일과
  코퍼스 밖 자료는 별도 확인해야 한다.
