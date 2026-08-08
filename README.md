# KOICA 건축사업 사례 데이터

KOICA 전자조달 현지입찰 공고와 첨부문서에서 건축사업 관련 정보를
수집·구조화하여 미래 사업의 건축조사에 참고할 수 있도록 만든 프로젝트다.
데이터의 원 출처는
[KOICA 전자조달 현지입찰공고 목록](https://nebid.koica.go.kr/oep/lobi/localBidManageList.do?P_PRCURE_BSNS_SE_CD=ABID)이다.

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
기준 DB에는 KOICA 공고·첨부·추출근거와 국가 공식 가격지수만 포함하며,
외부 공여기관의 사업·계약·거시지표는 적재하지 않는다.

## 공개 이용 방법

### 1. SQLite DB를 내려받아 직접 조회

[KOICA 건축사업 사례DB 2016-2025](outputs/koica-construction-distribution/KOICA_건축사업_사례DB_2016-2025.sqlite)를
내려받아 SQLite, DB Browser for SQLite, Python, R 등 원하는 도구로 조회할 수
있다. 기준 DB의 SHA-256은
`81e09f882c2859a06eec85c090ae9c96064686d615710046358703fc0f27fa67`이다.

```bash
sqlite3 "KOICA_건축사업_사례DB_2016-2025.sqlite"
```

### 2. Supabase 공개 DB에 접근해 조회

Supabase Data API의 공개 뷰와 읽기 전용 RPC를 publishable key로 호출할 수
있다. 발행된 사례 156건과 관련 공고 295건이 공개되어 있으며 쓰기와 동기화
권한은 공개하지 않는다.

- Project URL: `https://syzvicjmwnqennthhhcv.supabase.co`
- Publishable key: `sb_publishable_N2e3PjwiSxGl3MkJokCD-Q_ap6BkmMb`

### 3. MCP 도구로 LLM 자연어 조회

**To be continued.** 향후 공개할
[`amnotyoung/oda-survey-team`](https://github.com/amnotyoung/oda-survey-team)의
MCP 도구에서 국가·시설유형·공사유형·연면적·검색어 기반 자연어 조회를 제공할
예정이다.

### 4. 플러그인을 설치해 LLM 자연어 조회

**To be continued.** 같은 저장소에서 배포할 플러그인을 설치하면 LLM 대화에서
건축사례 검색·상세조회·데이터 상태 확인 도구를 사용할 수 있도록 공개할
예정이다.

각 방식의 URL, 예제 쿼리와 데이터 경계는
[`docs/public-data-access.md`](docs/public-data-access.md)를 참고한다. Supabase
구성·동기화 방법은
[`docs/koica-search-service.md`](docs/koica-search-service.md)를 따른다.

## 공개 데이터 주의사항

- 과거 금액과 명목 USD/㎡는 미래 사업비의 직접 산정값이 아니다.
- 원 첨부파일은 저장소에 포함하지 않지만, SQLite의 자동 추출 근거에는 공개
  조달문서에 기재된 담당자명·이메일·전화번호 등의 문자열이 포함될 수 있다.
- 연락처 정보는 원문 근거 확인 외의 목적으로 사용하지 않는다.
- Supabase에는 공개 검색에 필요한 축약 사례와 관련 공고만 적재하며, 원문
  근거·파일경로·해시는 적재하지 않는다.
