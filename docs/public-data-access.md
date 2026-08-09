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
| `koica_construction_cases` | 발행된 건축사례 156건 |
| `koica_construction_related_notices` | 같은 사업의 설계·감리 등 관련 공고 295건 |

```bash
SUPABASE_URL="https://syzvicjmwnqennthhhcv.supabase.co"
SUPABASE_KEY="sb_publishable_N2e3PjwiSxGl3MkJokCD-Q_ap6BkmMb"

curl -sS --get \
  "$SUPABASE_URL/rest/v1/koica_construction_cases" \
  -H "apikey: $SUPABASE_KEY" \
  --data-urlencode "select=case_id,country_ko,facility_type,gross_floor_area_m2,construction_cost_usd,nominal_unit_usd_m2,evidence_grade,procurement_url" \
  --data-urlencode "country_ko=eq.우간다" \
  --data-urlencode "limit=10"
```

### 세 도구에 대응하는 공개 RPC

| 도구 | Supabase RPC |
|---|---|
| `koica_construction_data_status` | `get_koica_search_status()` |
| `search_koica_construction_cases` | `search_koica_construction_cases(...)` |
| `get_koica_construction_case` | `get_koica_reference_case(p_case_id)` |

```bash
# DB 버전·감사일·동기화일·건수
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

# 사례 상세와 같은 사업의 관련 공고
curl -sS -X POST \
  "$SUPABASE_URL/rest/v1/rpc/get_koica_reference_case" \
  -H "apikey: $SUPABASE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"p_case_id":"L2019-00016"}'
```

검색 결과는 최대 50건으로 제한된다. `anon`과 `authenticated`에는 `SELECT`와
위 조회 RPC 실행 권한만 있고 `INSERT`, `UPDATE`, `DELETE`와 동기화 RPC 실행
권한은 없다.

## 2. SQLite DB 직접 이용 (선택)

### 다운로드와 검증

- [KOICA 건축사업 사례DB 2016-2025](../outputs/koica-construction-distribution/KOICA_건축사업_사례DB_2016-2025.sqlite)
- 파일 크기: 7,872,512 bytes
- SHA-256: `641dc86399c3b80be152b3a7a60ab8939349ce153c4957586774dce1150cb3f2`

```bash
shasum -a 256 "KOICA_건축사업_사례DB_2016-2025.sqlite"
sqlite3 "KOICA_건축사업_사례DB_2016-2025.sqlite"
```

기준 DB에는 공고 575건, 건축 후보 379건, 첨부파일 색인 1,000건, 분석문서
색인 3,698건, 자동 추출 근거 4,402건과 91개 사업의 면적·공사비 재검토 결과가
들어 있다. 원 첨부파일 자체는 포함하지 않는다.

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
```

전체 테이블 사전과 해석 원칙은
[`outputs/koica-construction-distribution/README.md`](../outputs/koica-construction-distribution/README.md)에
정리되어 있다.

## 3. MCP 도구로 LLM 자연어 조회

**To be continued.** 현재
[`amnotyoung/oda-survey-team`](https://github.com/amnotyoung/oda-survey-team)은
비공개 저장소다. 공개 전환 후 MCP 서버 설치·연결 방법과 다음 도구를 안내할
예정이다.

- `koica_construction_data_status`
- `search_koica_construction_cases`
- `get_koica_construction_case`

## 4. 플러그인으로 LLM 자연어 조회

**To be continued.** `oda-survey-team` 공개 전환 후 Codex 등 지원 환경에
플러그인을 설치하고 대화형으로 위 세 도구를 사용하는 절차를 제공할 예정이다.

## 데이터 이용 시 주의

- 공사비와 명목 USD/㎡는 물가·환율·세금·사업범위 보정 전 참고값이다.
- 미래 사업비는 현지 QS 견적, BOQ, 시공사 견적과 국가별 실제 가격지수를
  주자료로 산정한다.
- SQLite의 `evidence`에는 공개 조달문서에서 자동 추출한 근거 문장과 원문에
  기재된 담당자명·이메일·전화번호가 포함될 수 있다. 원문 근거 확인 외의
  목적으로 연락처를 사용하지 않는다.
- Supabase 공개 데이터에는 원문 근거, 로컬 파일경로와 SHA-256을 포함하지
  않는다.
