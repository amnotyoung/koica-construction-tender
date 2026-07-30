import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const outputDir = path.join(root, "outputs", "koica-construction-distribution");
const previewDir = path.join(outputDir, "previews");
const cases = JSON.parse(
  await fs.readFile(path.join(outputDir, "reviewed_cases_2016_2025.json"), "utf8"),
);
const priceIndexCsv = await fs.readFile(
  path.join(outputDir, "KOICA_국가별_가격지수_적용현황_28개국.csv"),
  "utf8",
);
const priceIndexCsvWorkbook = await Workbook.fromCSV(priceIndexCsv, {
  sheetName: "국가지수현황",
});
const priceIndexMatrix = priceIndexCsvWorkbook.worksheets
  .getItem("국가지수현황")
  .getUsedRange(true)
  .values;
const priceIndexHeaders = priceIndexMatrix[0].map((value, index) => (
  index === 0 ? String(value).replace(/^\uFEFF/, "") : value
));
const priceIndexRows = priceIndexMatrix.slice(1);

const COLORS = {
  navy: "#17365D",
  teal: "#0F6B78",
  blue: "#1F4E78",
  paleBlue: "#D9EAF7",
  paleGreen: "#E2F0D9",
  paleYellow: "#FFF2CC",
  paleRed: "#FCE4D6",
  gray: "#F2F2F2",
  white: "#FFFFFF",
  text: "#1F2937",
  line: "#D9E2F3",
};

const workbook = Workbook.create();
workbook.comments.setSelf({ displayName: "User" });

const colLetter = (number) => {
  let value = number;
  let result = "";
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
};

function addTableSheet(name, title, headers, rows, options = {}) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  const lastCol = colLetter(headers.length);
  sheet.getRange(`A1:${lastCol}1`).merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1").format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white, size: 15 },
    verticalAlignment: "center",
  };
  sheet.getRange("A1").format.rowHeight = 30;
  sheet.getRange(`A2:${lastCol}2`).values = [headers];
  sheet.getRange(`A2:${lastCol}2`).format = {
    fill: COLORS.blue,
    font: { bold: true, color: COLORS.white },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange(`A2:${lastCol}2`).format.rowHeight = 34;
  if (rows.length) {
    sheet.getRange(`A3:${lastCol}${rows.length + 2}`).values = rows;
    sheet.getRange(`A3:${lastCol}${rows.length + 2}`).format = {
      font: { color: COLORS.text, size: 9 },
      verticalAlignment: "top",
      borders: { insideHorizontal: { style: "thin", color: "#E8EDF3" } },
    };
    sheet.tables.add(
      `A2:${lastCol}${rows.length + 2}`,
      true,
      options.tableName,
    );
  }
  for (const column of options.wrapColumns || []) {
    sheet.getRange(`${column}3:${column}${rows.length + 2}`).format.wrapText = true;
  }
  for (const [column, width] of Object.entries(options.widths || {})) {
    sheet.getRange(`${column}:${column}`).format.columnWidth = width;
  }
  sheet.freezePanes.freezeRows(2);
  if (options.freezeColumns) sheet.freezePanes.freezeColumns(options.freezeColumns);
  return sheet;
}

const guide = workbook.worksheets.add("사용안내");
guide.showGridLines = false;
guide.getRange("A1:H2").merge();
guide.getRange("A1").values = [["KOICA 건축사업 사례 라이브러리 — 배포용 스냅샷"]];
guide.getRange("A1").format = {
  fill: COLORS.navy,
  font: { bold: true, color: COLORS.white, size: 18 },
  verticalAlignment: "center",
};
guide.getRange("A1").format.rowHeight = 36;
guide.getRange("A4:H5").merge();
guide.getRange("A4").values = [[
  "이 파일은 사례 열람용입니다. 원본 데이터는 SQLite이며, 여기에 미래 사업 권고단가는 없습니다.",
]];
guide.getRange("A4").format = {
  fill: COLORS.paleRed,
  font: { bold: true, color: "#9C0006", size: 13 },
  wrapText: true,
  verticalAlignment: "center",
};
guide.getRange("A7:B11").values = [
  ["수동 검토 사례", cases.length],
  ["권고단가", 0],
  ["가격 정규화 완료", 0],
  ["최초 공고일", cases.map((row) => row.notice_date).sort()[0]],
  ["최종 공고일", cases.map((row) => row.notice_date).sort().at(-1)],
];
guide.getRange("A7:A11").format = {
  fill: COLORS.blue,
  font: { bold: true, color: COLORS.white },
};
guide.getRange("B7:B11").format = {
  fill: COLORS.paleGreen,
  font: { bold: true, color: COLORS.navy, size: 13 },
};
guide.getRange("D7:H7").merge();
guide.getRange("D7").values = [["허용되는 활용"]];
guide.getRange("D7").format = {
  fill: COLORS.teal,
  font: { bold: true, color: COLORS.white },
};
guide.getRange("D8:H11").merge();
guide.getRange("D8").values = [[
  "• 유사사업 검색과 원문 근거 추적\n• 현지 QS·시공사 견적의 상하한 교차검증\n• 조사 질문과 비용범위 체크리스트 작성\n• 보고서의 과거 KOICA 사례 제시",
]];
guide.getRange("D8").format = { fill: COLORS.paleBlue, wrapText: true, verticalAlignment: "top" };
guide.getRange("A14:H14").merge();
guide.getRange("A14").values = [["금지되는 활용"]];
guide.getRange("A14").format = {
  fill: COLORS.paleYellow,
  font: { bold: true, color: COLORS.navy },
};
guide.getRange("A15:H18").merge();
guide.getRange("A15").values = [[
  "• 국가별 사례 평균을 미래 사업 권고단가로 사용\n• 2016년과 2025년 명목 USD/㎡를 보정 없이 평균\n• 집행한도를 계약·준공 실적으로 표현\n• 신축·개보수·외부토목·장비 포함범위를 구분하지 않고 비교",
]];
guide.getRange("A15").format = { fill: COLORS.paleRed, wrapText: true, verticalAlignment: "top" };
guide.getRange("A15").format.rowHeight = 72;
guide.getRange("A21:H21").merge();
guide.getRange("A21").values = [["국가별 적용 분기"]];
guide.getRange("A21").format = {
  fill: COLORS.teal,
  font: { bold: true, color: COLORS.white },
};
guide.getRange("A22:H27").merge();
guide.getRange("A22").values = [[
  "• 동일 국가 사례+공식 건설지수: 범위·기간을 맞춘 뒤 교차검증\n• 동일 국가 사례만 있음: 현지 견적을 주자료로 하고 지수 부재를 명시\n• 동일 국가 사례 없음: 타 국가 사례는 설계·공종 참고에만 사용\n• 수입재 비중 큼: 현지비와 수입비를 통화·공급국별로 분리\n• 기준일까지 지수 미공개: 관측종료일까지만 계산하고 이후는 시나리오",
]];
guide.getRange("A22").format = { fill: COLORS.paleBlue, wrapText: true, verticalAlignment: "top" };
guide.getRange("A22").format.rowHeight = 90;
guide.getRange("A30:H30").merge();
guide.getRange("A30").values = [["미래 사업 조사 절차"]];
guide.getRange("A30").format = {
  fill: COLORS.teal,
  font: { bold: true, color: COLORS.white },
};
guide.getRange("A31:H36").merge();
guide.getRange("A31").values = [[
  "1) 국가별 템플릿의 사업 입력·비용경계 작성 → 2) SQLite에서 국가·시설·사업유형이 유사한 사례 검색 → 3) A/B등급 원문과 가격단계·세금·범위 확인 → 4) 현지 QS 개략견적·BOQ 및 시공사 견적 2~3개 확보 → 5) 실제 관측 지수의 원래 기간·잠정상태·관측종료일 기록 → 6) 통화·수입재 구성 확인 후 보정 → 7) 복수변수 시나리오와 불확실성 보고",
]];
guide.getRange("A31").format = { fill: COLORS.gray, wrapText: true, verticalAlignment: "top" };
guide.getRange("A31").format.rowHeight = 82;
guide.getRange("A:H").format.columnWidth = 16;
guide.getRange("A:A").format.columnWidth = 24;
guide.getRange("D:H").format.columnWidth = 18;
guide.freezePanes.freezeRows(2);

const caseHeaders = [
  "공고번호", "사업번호", "공고일", "연속연도", "국가", "지역", "시설유형",
  "사업유형", "연면적(㎡)", "명목 공사비(USD)", "명목 USD/㎡", "근거등급",
  "면적기준", "비용단계", "범위·주의", "가격보정", "권고단가", "허용용도",
  "수집구간", "근거파일", "근거위치", "상세URL", "근거요약",
];
const caseRows = cases.map((row) => [
  row.bid_no, row.project_no, row.notice_date, row.price_year_decimal,
  row.country, row.region, row.facility_type, row.work_type,
  row.gross_floor_area_m2, row.cost_usd_nominal, row.unit_usd_m2_nominal,
  row.evidence_grade, row.area_basis, row.cost_stage, row.scope_caution,
  row.normalization_status, row.recommended_unit_rate, row.allowed_use,
  row.source_period, row.source_file, row.source_locator, row.source_url,
  row.evidence_summary,
]);
const caseSheet = addTableSheet(
  "검토사례",
  "2016–2025 수동 검토 건축 사례 — 명목단가, 권고단가 아님",
  caseHeaders,
  caseRows,
  {
    tableName: "ReviewedCases",
    freezeColumns: 4,
    wrapColumns: ["G", "H", "M", "N", "O", "R", "T", "V", "W"],
    widths: {
      A: 17, B: 14, C: 12, D: 11, E: 16, F: 16, G: 27, H: 17, I: 14,
      J: 18, K: 16, L: 10, M: 24, N: 22, O: 34, P: 12, Q: 12, R: 28,
      S: 17, T: 52, U: 14, V: 46, W: 48,
    },
  },
);
caseSheet.getRange(`D3:D${caseRows.length + 2}`).format.numberFormat = "0.000";
caseSheet.getRange(`I3:I${caseRows.length + 2}`).format.numberFormat = "#,##0.0";
caseSheet.getRange(`J3:K${caseRows.length + 2}`).format.numberFormat = '"$"#,##0';
caseSheet.getRange(`L3:L${caseRows.length + 2}`).conditionalFormats.add(
  "containsText",
  { text: "C", format: { fill: COLORS.paleRed, font: { color: "#9C0006" } } },
);

const groups = new Map();
for (const row of cases) {
  const key = [row.country, row.facility_type, row.work_type].join("\u0001");
  const group = groups.get(key) || {
    country: row.country,
    facility: row.facility_type,
    work: row.work_type,
    rows: [],
  };
  group.rows.push(row);
  groups.set(key, group);
}
const coverage = [...groups.values()]
  .map((group) => {
    const units = group.rows
      .map((row) => row.unit_usd_m2_nominal)
      .filter((value) => Number.isFinite(value));
    const count = group.rows.length;
    return [
      group.country, group.facility, group.work, count,
      group.rows.filter((row) => row.evidence_grade === "A").length,
      group.rows.map((row) => row.notice_date).sort()[0],
      group.rows.map((row) => row.notice_date).sort().at(-1),
      Math.min(...units), Math.max(...units),
      count === 1 ? "개별 사례만" : count <= 4 ? "잠정 범위만" : "보정 후 예비검토 가능",
      "권고단가 아님",
    ];
  })
  .sort((a, b) => b[3] - a[3] || a[0].localeCompare(b[0]));
const coverageSheet = addTableSheet(
  "표본현황",
  "국가 × 시설유형 × 사업유형 표본현황",
  ["국가", "시설유형", "사업유형", "사례수", "A등급수", "최초일", "최종일", "명목최소", "명목최대", "해석", "주의"],
  coverage,
  {
    tableName: "SampleCoverage",
    freezeColumns: 3,
    wrapColumns: ["B", "C", "J", "K"],
    widths: { A: 17, B: 30, C: 18, D: 11, E: 11, F: 12, G: 12, H: 16, I: 16, J: 24, K: 18 },
  },
);
coverageSheet.getRange(`H3:I${coverage.length + 2}`).format.numberFormat = '"$"#,##0';
coverageSheet.getRange(`D3:D${coverage.length + 2}`).conditionalFormats.add(
  "cellIs",
  { operator: "lessThan", formula: 5, format: { fill: COLORS.paleYellow, font: { color: "#9C6500" } } },
);

const priceIndexSheet = addTableSheet(
  "국가지수현황",
  "28개국 가격지수 후보·현재 선택·관측상태",
  priceIndexHeaders,
  priceIndexRows,
  {
    tableName: "CountryPriceIndexStatus",
    freezeColumns: 3,
    wrapColumns: ["E", "F", "G", "H", "J", "K", "L", "Q", "S", "T"],
    widths: {
      A: 18, B: 9, C: 12, D: 13, E: 34, F: 28, G: 34, H: 46, I: 13,
      J: 30, K: 42, L: 30, M: 12, N: 14, O: 13, P: 13, Q: 16, R: 22,
      S: 46, T: 42,
    },
  },
);
priceIndexSheet.getRange(`N3:N${priceIndexRows.length + 2}`).format.numberFormat = "#,##0";
priceIndexSheet.getRange(`R3:R${priceIndexRows.length + 2}`).format.numberFormat = "yyyy-mm-dd hh:mm";
priceIndexSheet.getRange(`Q3:Q${priceIndexRows.length + 2}`).conditionalFormats.add(
  "containsText",
  { text: "provisional", format: { fill: COLORS.paleYellow, font: { color: "#9C6500" } } },
);

const dictionaryRows = [
  ["datasets", "수집기간별 품질·건수 메타데이터", "dataset_id"],
  ["bids", "공개 현지입찰 목록 575건", "bid_no"],
  ["details", "상세페이지 필드와 첨부그룹", "bid_no"],
  ["projects", "건축 후보 사업·입찰 메타데이터", "bid_no, project_no"],
  ["attachments", "원 첨부 1,000개의 경로·크기·SHA-256", "bid_no, attachment_sn"],
  ["documents", "ZIP 내부 포함 분석문서 인덱스", "dataset_id, bid_no, source_file"],
  ["evidence", "자동 추출 수치근거 3,563건", "evidence_id, bid_no"],
  ["reviewed_cases", "수동 검토 단가사례 66건", "bid_no"],
  ["fee_benchmarks", "설계·감리 비용 검토사례", "fee_id, bid_no"],
  ["price_index_sources", "국가별 가격지수 출처·범위·우선순위", "source_id"],
  ["price_index_values", "분석용 기간·원래 기간·값·잠정/수정 상태·공개 URL", "source_id, period"],
  ["v_price_index_coverage", "국가·지수별 실제 관측기간과 최신값 상태", "조회용 VIEW"],
  ["v_best_available_price_index", "국가별 현재 선택 가능한 최고 우선순위 실제 지수", "조회용 VIEW"],
  ["v_sample_coverage", "국가×시설×유형 표본수와 명목범위", "조회용 VIEW"],
  ["v_yearly_inventory", "연도별 검토사례·미보정 건수", "조회용 VIEW"],
  ["v_duplicate_attachments", "동일 SHA-256 첨부파일", "조회용 VIEW"],
];
addTableSheet(
  "데이터사전",
  "SQLite 테이블·뷰 데이터사전",
  ["테이블·뷰", "내용", "주요 키"],
  dictionaryRows,
  {
    tableName: "DataDictionary",
    wrapColumns: ["B", "C"],
    widths: { A: 28, B: 66, C: 32 },
  },
);

const sqlRows = [
  ["국가·시설 유사사례", "WITH p(country_name, facility_keyword) AS (VALUES ('Nepal','교육')) SELECT r.* FROM reviewed_cases r CROSS JOIN p WHERE r.country=p.country_name ORDER BY CASE WHEN r.facility_type LIKE '%'||p.facility_keyword||'%' THEN 0 ELSE 1 END, r.notice_date DESC;"],
  ["국가별 표본수", "WITH p(country_name) AS (VALUES ('Nepal')) SELECT c.* FROM v_sample_coverage c CROSS JOIN p WHERE c.country=p.country_name ORDER BY reviewed_case_count DESC;"],
  ["국가별 지수 선택", "WITH p(country_name) AS (VALUES ('Nepal')) SELECT b.* FROM v_best_available_price_index b CROSS JOIN p WHERE b.country=p.country_name;"],
  ["지수 원래 기간·상태", "SELECT period, native_period, value, observation_status, release_url, retrieved_at FROM price_index_values WHERE source_id='NSO_NPL_IPICS_OVERALL' ORDER BY period;"],
  ["근거 추적", "SELECT category, source_file, source_locator, evidence_text FROM evidence WHERE bid_no = '<공고번호>';"],
  ["첨부 확인", "SELECT original_name, bytes, sha256, relative_path FROM attachments WHERE bid_no = '<공고번호>';"],
  ["연도별 현황", "SELECT * FROM v_yearly_inventory ORDER BY notice_year;"],
];
addTableSheet(
  "SQL 예시",
  "SQLite 기본 조회 예시",
  ["목적", "SQL"],
  sqlRows,
  {
    tableName: "SqlExamples",
    wrapColumns: ["B"],
    widths: { A: 24, B: 110 },
  },
);

await fs.mkdir(previewDir, { recursive: true });
const renderRanges = {
  "사용안내": "A1:H37",
  "검토사례": `A1:W${caseRows.length + 2}`,
  "표본현황": `A1:K${coverage.length + 2}`,
  "국가지수현황": `A1:T${priceIndexRows.length + 2}`,
  "데이터사전": `A1:C${dictionaryRows.length + 2}`,
  "SQL 예시": `A1:B${sqlRows.length + 2}`,
};
for (const [sheetName, range] of Object.entries(renderRanges)) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(
    path.join(previewDir, `${sheetName.replace(/\s/g, "_")}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}
const checks = [];
checks.push((await workbook.inspect({
  kind: "table",
  range: "사용안내!A1:H37",
  include: "values,formulas",
  tableMaxRows: 40,
  tableMaxCols: 8,
})).ndjson);
checks.push((await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
})).ndjson);
await fs.writeFile(path.join(outputDir, "workbook_verification.ndjson"), checks.join("\n"), "utf8");

const output = await SpreadsheetFile.exportXlsx(workbook);
const outputPath = path.join(outputDir, "KOICA_건축사업_사례라이브러리_2016-2025.xlsx");
await output.save(outputPath);
console.log(JSON.stringify({
  outputPath,
  sheets: Object.keys(renderRanges),
  reviewedCases: caseRows.length,
  coverageGroups: coverage.length,
}, null, 2));
