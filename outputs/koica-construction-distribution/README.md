# KOICA 건축사업 사례 데이터 배포 패키지

## 무엇을 배포하는가

배포의 기준 파일은 `KOICA_건축사업_사례DB_2016-2025.sqlite`이다.
XLSX는 비전문가 열람용 스냅샷이며 수정 원본으로 사용하지 않는다.

| 파일 | 용도 |
|---|---|
| `KOICA_건축사업_사례DB_2016-2025.sqlite` | 기준 데이터베이스·검색·근거 추적 |
| `KOICA_건축사업_사례라이브러리_2016-2025.xlsx` | 회의·검토·비전문가 열람 |
| `KOICA_건축사업_검토사례_2016-2025.csv` | R·Python·통계도구 분석 |
| `KOICA_국가별_가격지수_적용현황_28개국.csv` | 28개국 공식지수 후보·적재상태·현재 대체지수 확인 |
| `reviewed_cases_2016_2025.json` | API·웹서비스 연계용 검토사례 |
| `DEMO_네팔_직업교육시설_3000m2.md` | DB 검색부터 보고서 문구까지의 시연 |
| `README.md` | 활용법·제약·데이터 구조 |

원 첨부파일 약 1.67GB는 이 경량 배포 ZIP에 포함하지 않는다. 원문 보존용
내부 아카이브로 별도 관리하며, DB의 `attachments.relative_path`,
`attachments.sha256`, `details.detail_url`로 추적한다.

## 데이터 규모

- 공개 현지입찰 목록: 575건
- 상세페이지가 수집된 건축 후보: 379건
- 원 첨부파일: 1,000개
- ZIP 내부 포함 분석 문서: 2,692개
- 자동 추출 수치 근거: 3,563건
- 수동 검토 단가사례: 66건
- 설계·감리 비용 검토사례: 7건
- 미래 사업 권고단가: 0건
- 가격지수 우선순위: 5단계
- 가격지수 국가 감사: 28개국
- 실제 가격·환율 관측값: DB의 `price_index_values` 참조

## 핵심 원칙

1. 2016~2020과 2021~2025는 수집 작업 구간일 뿐 분석 집단이 아니다.
2. 모든 사례는 정확한 공고일과 연속연도 값을 보존한다.
3. 현재 USD/㎡는 물가·환율·범위 보정 전 명목값이다.
4. 집행한도·설계추정액을 계약 또는 준공 실적으로 표현하면 안 된다.
5. 사례 수가 적은 국가·시설유형의 평균을 미래 사업 권고단가로 사용하지 않는다.
6. 미래 단가는 현지 QS 개략견적·BOQ·시공사 견적을 주자료로 산정하고,
   과거 KOICA 사례는 교차검증에만 사용한다.
7. 고정 연 상승률을 사용하지 않고 실제 국가 지수의 관측값 비율을 사용한다.
8. 실제 관측기간 밖의 값을 임의 외삽하거나 전망값을 실제값으로 표시하지 않는다.
9. `현재선택`은 국가에 영구 고정된 지수가 아니다. 사업 공고일과 기준일에
   실제 관측값이 모두 있는 최고 우선순위 지수를 실행 때 다시 선택한다.

## SQLite 주요 테이블

| 테이블 | 내용 |
|---|---|
| `datasets` | 수집기간별 건수와 품질 메타데이터 |
| `bids` | 공개 현지입찰 목록 |
| `details` | 상세페이지 필드와 첨부그룹 |
| `projects` | 건축 후보 사업·입찰 메타데이터 |
| `attachments` | 첨부파일 경로·크기·SHA-256 |
| `documents` | ZIP 내부 포함 분석문서 인덱스 |
| `evidence` | 자동 추출 수치와 원문 위치 |
| `reviewed_cases` | 수동 검토 단가사례 |
| `fee_benchmarks` | 설계·감리 비용사례 |
| `price_index_policy` | 건설지수부터 CPI까지 5단계 선택 원칙 |
| `price_index_sources` | 국가·지수별 제공기관·주기·URL·품질정보 |
| `price_index_values` | 실제 지수와 환율 관측값 |
| `national_index_source_audit` | 28개국 공식 건설지수 후보·적재 상태 |
| `normalization_runs` | 사업별 보정 실행값·산식·제약사항 |

조회용 VIEW는 `v_sample_coverage`, `v_yearly_inventory`,
`v_duplicate_attachments`, `v_price_index_coverage`,
`v_best_available_price_index`이다.

## 기본 조회

DB Browser for SQLite에서 데이터베이스를 열거나 다음처럼 조회한다.

```sql
-- 국가·시설·사업유형별 표본수 확인
SELECT *
FROM v_sample_coverage
WHERE country = 'Nepal'
ORDER BY reviewed_case_count DESC;

-- 유사사례 검색
SELECT bid_no, notice_date, country, facility_type, work_type,
       gross_floor_area_m2, unit_usd_m2_nominal, evidence_grade,
       normalization_status, source_url
FROM reviewed_cases
WHERE country = 'Nepal'
ORDER BY notice_date DESC;

-- 선택 사례의 원문 근거 확인
SELECT category, source_file, source_locator, evidence_text
FROM evidence
WHERE bid_no = 'L2022-00029-1';

-- 국가별 현재 선택 가능한 최고 우선순위 실제 지수
SELECT country, priority, index_class, series_name,
       earliest_period, latest_period, provider_url
FROM v_best_available_price_index
ORDER BY country;
```

## 미래 사업 건축조사에서의 사용 절차

1. `v_sample_coverage`에서 비교 가능한 사례 수부터 확인한다.
2. `reviewed_cases`에서 국가·시설유형·신축/개보수가 유사한 사례를 찾는다.
3. A/B등급 사례의 `source_file`, `source_locator`, `source_url`을 확인한다.
4. 현지 QS 개략견적·BOQ 및 시공사 예산견적 2~3개를 확보한다.
5. 국가 건설지수 → BOQ 가중합 → 건설자재 PPI/WPI → GDP 디플레이터
   → CPI 순으로 실제 관측값이 있는 최고 우선순위 지수를 선택한다.
6. 원금액의 현지통화·수입재 구성과 당시 환율을 확인한 후 가격을 보정한다.
7. 과거 사례는 현지 견적의 상하한 교차검증에만 사용한다.
8. 최종 적용단가와 불확실성은 사업별 조사보고서에 별도로 기록한다.

## 갱신 규칙

- 신규 수집·검토 결과는 SQLite에 먼저 반영한다.
- `bid_no`를 공고 기본키로 사용한다.
- 동일 파일은 SHA-256으로 확인한다.
- 재공고와 동일 사업의 설계·시공 단계는 별도 공고로 저장하되
  분석 시 중복 여부를 표시한다.
- XLSX와 CSV는 SQLite 갱신 후 다시 생성하는 배포 스냅샷이다.
