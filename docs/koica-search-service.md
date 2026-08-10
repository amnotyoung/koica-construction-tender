# KOICA 건축사례 검색 서비스

## 구성

```text
GitHub 공개 SQLite (기준 데이터·원 첨부 제외)
  -> 공개 검색 스냅샷 생성
  -> service-role 전용 동기화 RPC
  -> Supabase 비공개 저장 스키마 + 공개 읽기 전용 뷰/RPC
  -> publishable key를 쓰는 공개 클라이언트
  -> 구성된 실행 환경의 MCP 도구
  -> MCP 도구를 제공하는 플러그인
```

SQLite의 `attachments`, `documents`, `evidence`, 로컬 상대경로와 해시는
Supabase에 올리지 않는다. GitHub에서는 기준 SQLite를 내려받아 전체 색인과
추출근거를 조회할 수 있고, Supabase에는 세 도구에 필요한 축약 검색 데이터만
공개한다. 공개 사례의 고정 근거등급과 검색 요청별 동적 우선순위도 분리한다.

SQLite 1.9에 추가된 `evaluation_*` 테이블과
`v_project_evaluation_findings`도 현재 검색 스냅샷·동기화 RPC의 범위 밖이다.
종료평가 페이지 근거는 SQLite에서만 조회하며, 별도의 RLS·권한·공개 뷰 설계
없이 `public` 스키마에 새 테이블을 자동 노출하지 않는다.

## 1. 검색 데이터 생성

```bash
python3 scripts/export_koica_search_data.py
```

생성 파일은 `outputs/koica-search/`의 CSV 두 개와 JSON 스냅샷이다. 사례 단위는
재공고를 합친 `bid_base_no`이며 현재 DB에서는 건축공사 공고군 156건이다.

## 2. Supabase 스키마 적용

대상 프로젝트를 연결한 뒤 마이그레이션을 적용한다.

```bash
supabase link --project-ref PROJECT_REF
supabase db push
```

마이그레이션은 `koica_search` 저장 스키마, RLS, PGroonga 한국어 검색 인덱스,
조회 RPC와 동기화 RPC를 만든다. 저장 스키마는 Data API의 exposed schema에
추가하지 않는다. 대신 `public`의 다음 두 `security_invoker` 뷰만 직접 조회할 수
있다.

- `koica_construction_cases`: 발행된 사례의 공개 필드
- `koica_construction_related_notices`: 발행된 관련 공고의 공개 필드

`anon`과 `authenticated`에는 발행된 행의 `SELECT`만 허용한다. `INSERT`,
`UPDATE`, `DELETE`와 동기화 RPC는 계속 `service_role` 전용이다.

## 3. 데이터 동기화

먼저 변이 없는 검증을 실행한다.

```bash
python3 scripts/sync_koica_search_to_supabase.py
```

검증 후 비밀키를 셸 환경변수로만 제공하고 적용한다.

```bash
export KOICA_CONSTRUCTION_SUPABASE_URL="https://PROJECT_REF.supabase.co"
export KOICA_CONSTRUCTION_SUPABASE_SECRET_KEY="sb_secret_..."
python3 scripts/sync_koica_search_to_supabase.py --apply
```

동기화 RPC는 전체 스냅샷을 한 트랜잭션에서 upsert하고 사라진 공고군을 정리한다.
빈 사례 배열은 원격 데이터 오삭제를 막기 위해 거부한다.

## 4. 공개 읽기

공개 클라이언트에는 secret/service-role 키가 아니라 `sb_publishable_...` 키만
사용한다. 세 도구와 Supabase RPC의 대응은 다음과 같다.

실제 Project URL, publishable key와 호출 예제는
[`public-data-access.md`](public-data-access.md)에 공개한다.

| 도구 | 공개 RPC |
|---|---|
| `koica_construction_data_status` | `get_koica_search_status()` |
| `search_koica_construction_cases` | `search_koica_construction_cases(...)` |
| `get_koica_construction_case` | `get_koica_reference_case(p_case_id)` |

예를 들어 상태는 다음처럼 조회한다.

```bash
curl "$KOICA_CONSTRUCTION_SUPABASE_URL/rest/v1/rpc/get_koica_search_status" \
  -H "apikey: $KOICA_CONSTRUCTION_SUPABASE_PUBLISHABLE_KEY"
```

공개 뷰는 `/rest/v1/koica_construction_cases`와
`/rest/v1/koica_construction_related_notices`에서 조회할 수 있다. publishable
키는 비밀이 아니며, 이 키를 가진 누구나 공개 행을 읽을 수 있다는 전제로 RLS와
권한을 설정한다.

## 5. MCP·플러그인 연동과 실패 처리

MCP·플러그인이 구성된 실행 환경에서는 위 세 검색 도구가 공개 읽기 RPC만
호출하게 한다. 도구의 설치·배포 상태는 실행 환경에 따라 다르며, 도구가 없거나
호출이 실패해도 공개 Supabase RPC 또는 GitHub·로컬 SQLite로 조회할 수 있다.
GitHub 웹 리더의 robots 정책이나 바이너리 처리 실패를 저장소 비공개 또는
데이터 부재로 일반화하지 않는다.

배포 서버의 공개 조회에는 위 URL과 publishable key를 설정하고 고정된 Supabase
RPC만 호출하게 한다. 동기화 작업만 별도의 secret key를 사용한다. MCP 도구
인수에는 URL·키·RPC 이름을 받지 않으며 임의 SQL이나 동기화 RPC도 노출하지
않는다.

플러그인 저장소·설정·실행 산출물에는 secret/service-role 키를 넣지 않는다.

## 검색 결과 해석

- `priority`, `match_score`, `match_reason`: 국가·시설기능·공종·연면적을 반영한 요청별 순위
- `evidence_grade`: 원자료 준비도와 검토상태에 대한 고정 등급
- `nominal_unit_usd_m2`: 물가·환율·세금·범위 보정 전 스크리닝 값
- `scope_note`, `evidence_note`: 비교 사용 시 확인할 범위와 근거

명목 USD/㎡는 미래 사업비의 직접 산정값이 아니다. 현지 QS 견적, BOQ, 물가,
환율, 세금과 공사범위를 함께 검토해야 한다.
