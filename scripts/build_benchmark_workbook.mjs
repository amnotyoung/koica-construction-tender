import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

process.on("uncaughtException", (error) => {
  console.error(`WORKBOOK_BUILD_ERROR: ${error?.message || error}`);
  console.error(String(error?.stack || "").split("\n").slice(0, 8).join("\n"));
  process.exit(1);
});

const projectRoot = process.cwd();
const manifestsDir = path.join(projectRoot, "data", "manifests");
const outputDir = path.join(projectRoot, "outputs", "koica-construction-history");
const previewDir = path.join(outputDir, "previews");

const readJson = async (name) =>
  JSON.parse(await fs.readFile(path.join(manifestsDir, name), "utf8"));

const [
  bids,
  projects,
  attachmentsObject,
  evidence,
  fileIndex,
  unitCosts,
  feeBenchmarks,
  checklist,
] = await Promise.all([
  readJson("bids.json"),
  readJson("projects.json"),
  readJson("attachments.json"),
  readJson("construction_evidence.json"),
  readJson("file_index.json"),
  readJson("curated_unit_costs_expanded.json"),
  readJson("curated_fee_benchmarks.json"),
  readJson("survey_checklist.json"),
]);

const attachments = Object.values(attachmentsObject).flatMap((bid) =>
  (bid.files || []).map((file) => ({
    bid_no: bid.bid_no,
    name: file.ATCHMNFL_NM || "",
    bytes: Number(file.FILE_CPCTY || 0),
    extension: path.extname(file.ATCHMNFL_NM || "").toLowerCase(),
    status: file.status || "",
    sha256: file.sha256 || "",
    local_path: file.local_path || "",
    registered_at: /^\d{14}$/.test(String(file.REGIST_DT || ""))
      ? String(file.REGIST_DT).replace(
          /^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$/,
          "$1-$2-$3 $4:$5:$6",
        )
      : String(file.REGIST_DT || ""),
  })),
);
const analysisFiles = fileIndex
  .filter((row) =>
    !row.source_file.split("/").some((part) => part.startsWith(".") || part.startsWith("~$")),
  )
  .sort((a, b) => b.bid_no.localeCompare(a.bid_no) || a.source_file.localeCompare(b.source_file));
const categoryOrder = new Map([
  ["공사비", 1], ["설계비", 2], ["감리·CM비", 3], ["연면적·면적", 4],
  ["총사업비·예산", 5], ["부가세·예비비", 6], ["기간", 7],
]);
const evidenceSorted = [...evidence].sort(
  (a, b) =>
    (categoryOrder.get(a.category) || 99) - (categoryOrder.get(b.category) || 99)
    || b.bid_no.localeCompare(a.bid_no)
    || a.source_file.localeCompare(b.source_file),
);

const workbook = Workbook.create();
workbook.comments.setSelf({ displayName: "User" });

const COLORS = {
  navy: "#17365D",
  blue: "#1F4E78",
  teal: "#0F6B78",
  paleBlue: "#D9EAF7",
  paleGreen: "#E2F0D9",
  paleYellow: "#FFF2CC",
  paleRed: "#FCE4D6",
  gray: "#F2F2F2",
  line: "#D9E2F3",
  white: "#FFFFFF",
  text: "#1F2937",
};

const colLetter = (number) => {
  let value = number;
  let letters = "";
  while (value > 0) {
    value -= 1;
    letters = String.fromCharCode(65 + (value % 26)) + letters;
    value = Math.floor(value / 26);
  }
  return letters;
};

const xmlSafe = (value) =>
  typeof value === "string"
    ? value.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\uFFFE\uFFFF]/g, "")
    : value;

function addDataSheet(name, title, headers, rows, options = {}) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  const lastCol = colLetter(headers.length);
  sheet.getRange(`A1:${lastCol}1`).merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1").format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white, size: 14 },
    verticalAlignment: "center",
  };
  sheet.getRange("A1").format.rowHeight = 30;
  sheet.getRange(`A2:${lastCol}2`).values = [headers.map(xmlSafe)];
  sheet.getRange(`A2:${lastCol}2`).format = {
    fill: COLORS.blue,
    font: { bold: true, color: COLORS.white },
    wrapText: true,
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: COLORS.line },
  };
  sheet.getRange(`A2:${lastCol}2`).format.rowHeight = 34;
  if (rows.length) {
    sheet.getRange(`A3:${lastCol}${rows.length + 2}`).values =
      rows.map((row) => row.map(xmlSafe));
    sheet.getRange(`A3:${lastCol}${rows.length + 2}`).format = {
      font: { color: COLORS.text, size: 9 },
      verticalAlignment: "top",
      borders: {
        insideHorizontal: { style: "thin", color: "#E8EDF3" },
      },
    };
    if (options.wrapColumns) {
      for (const column of options.wrapColumns) {
        sheet.getRange(`${column}3:${column}${rows.length + 2}`).format.wrapText = true;
      }
    }
    sheet.tables.add(
      `A2:${lastCol}${rows.length + 2}`,
      true,
      options.tableName || `${name.replace(/\s/g, "")}Table`,
    );
  }
  sheet.freezePanes.freezeRows(2);
  if (options.freezeColumns) sheet.freezePanes.freezeColumns(options.freezeColumns);
  for (const [column, width] of Object.entries(options.widths || {})) {
    sheet.getRange(`${column}:${column}`).format.columnWidth = width;
  }
  return sheet;
}

const summary = workbook.worksheets.add("요약");
summary.showGridLines = false;
summary.getRange("A1:H2").merge();
summary.getRange("A1").values = [["KOICA 과거 건축사업 조사 참고 데이터 (2021–2025 공고)"]];
summary.getRange("A1").format = {
  fill: COLORS.navy,
  font: { bold: true, color: COLORS.white, size: 18 },
  verticalAlignment: "center",
};
summary.getRange("A1").format.rowHeight = 34;
summary.getRange("A3:H3").merge();
summary.getRange("A3").values = [[
  "공개 현지입찰 436건을 기준으로 건축 후보 240건과 첨부 707개를 수집·검증하고, 문서 내 수치 근거를 보수적으로 구조화한 연구용 자료입니다.",
]];
summary.getRange("A3").format = { fill: COLORS.paleBlue, wrapText: true, font: { color: COLORS.text } };
summary.getRange("A3").format.rowHeight = 36;

const kpis = [
  ["전체 공고", bids.length, "검색기간 2021-01-01~2025-12-31"],
  ["건축 후보", projects.length, "제목·계약유형 키워드 기반"],
  ["원 첨부파일", attachments.length, "크기·SHA-256 검증"],
  ["분석 파일", analysisFiles.length, "ZIP 내부 문서 포함(숨김·임시파일 제외)"],
  ["수치 근거", evidence.length, "파일·페이지/문단/시트 위치 포함"],
  ["선별 단가", unitCosts.length, "A/B/C 근거등급을 부여한 확장 사례"],
];
summary.getRange("A5:C10").values = kpis;
summary.getRange("A5:A10").format = { fill: COLORS.blue, font: { bold: true, color: COLORS.white } };
summary.getRange("B5:B10").format = {
  fill: COLORS.paleGreen,
  font: { bold: true, color: COLORS.navy, size: 14 },
  numberFormat: "#,##0",
};
summary.getRange("C5:C10").format = { fill: COLORS.gray, wrapText: true };

summary.getRange("E5:H5").values = [["국가", "사례수", "평균 USD/㎡", "범위 USD/㎡"]];
summary.getRange("E5:H5").format = {
  fill: COLORS.teal,
  font: { bold: true, color: COLORS.white },
};
const countries = [...new Set(
  unitCosts.filter((row) => row.summary_include).map((row) => row.country),
)].sort();
summary.getRange(`E6:E${countries.length + 5}`).values = countries.map((country) => [country]);
summary.getRange(`G6:G${countries.length + 5}`).format.numberFormat = '"$"#,##0';
summary.getRange(`E5:H${countries.length + 5}`).format.borders = {
  insideHorizontal: { style: "thin", color: COLORS.line },
  outside: { style: "thin", color: COLORS.line },
};

const noteRow = Math.max(13, countries.length + 7);
summary.getRange(`A${noteRow}:H${noteRow}`).merge();
summary.getRange(`A${noteRow}`).values = [["해석 주의"]];
summary.getRange(`A${noteRow}`).format = {
  fill: COLORS.paleYellow,
  font: { bold: true, color: COLORS.navy },
};
summary.getRange(`A${noteRow + 1}:H${noteRow + 4}`).merge();
summary.getRange(`A${noteRow + 1}`).values = [[
  "① 단가는 계약 실적이 아니라 공고 상세의 집행한도 또는 기획·설계 단계 추정액입니다. ② A는 동일 공고의 명시 연면적, B는 면적 합산·동일사업 문서 연결·특수시설, C는 개보수·토목 등 범위 차이가 큰 참고값입니다. ③ ‘요약포함=예’만 국가 통계에 반영했습니다. ④ VAT·관세·장비·외부공사 포함범위, 기준연도·환율·물가를 미래 조사에서 반드시 재보정하세요.",
]];
summary.getRange(`A${noteRow + 1}`).format = {
  fill: COLORS.paleRed,
  wrapText: true,
  verticalAlignment: "top",
};
summary.getRange(`A${noteRow + 1}`).format.rowHeight = 70;
summary.getRange("A:H").format.columnWidth = 16;
summary.getRange("A:A").format.columnWidth = 18;
summary.getRange("C:C").format.columnWidth = 36;
summary.getRange("E:E").format.columnWidth = 18;
summary.getRange("H:H").format.columnWidth = 18;
summary.freezePanes.freezeRows(3);

const unitHeaders = [
  "공고번호", "사업번호", "연도", "국가", "지역", "시설유형", "사업유형",
  "근거등급", "요약포함", "연면적(㎡)", "공사비(USD)",
  "직접제시 단가(USD/㎡)", "적용 단가(USD/㎡)", "면적기준", "비용단계",
  "비용범위·주의", "세금", "면적근거파일", "근거위치", "비용근거URL", "근거요약",
];
const unitRows = unitCosts.map((row) => [
  row.bid_no, row.project_no || "", row.year, row.country, row.region,
  row.facility_type, row.work_type, row.benchmark_grade,
  row.summary_include ? "예" : "아니오",
  row.gross_floor_area_m2, row.construction_cost_usd, row.direct_unit_usd_m2,
  null, row.area_basis, row.cost_stage, row.cost_scope_note || row.caution,
  row.tax_note, row.source_file, row.source_locator, row.cost_source_url,
  row.evidence_summary,
]);
const unitSheet = addDataSheet(
  "단가 벤치마크",
  "검토 선별 건축 공사비 단가",
  unitHeaders,
  unitRows,
  {
    tableName: "UnitCostBenchmarks",
    freezeColumns: 3,
    wrapColumns: ["E", "F", "N", "O", "P", "Q", "R", "T", "U"],
    widths: { A: 17, B: 14, C: 8, D: 15, E: 18, F: 26, G: 15, H: 10, I: 11, J: 13, K: 16, L: 17, M: 17, N: 24, O: 22, P: 34, Q: 22, R: 48, S: 14, T: 46, U: 48 },
  },
);
for (let row = 3; row <= unitRows.length + 2; row += 1) {
  unitSheet.getRange(`M${row}`).formulas = [[`=IF(L${row}<>"",L${row},IFERROR(K${row}/J${row},""))`]];
}
unitSheet.getRange(`J3:J${unitRows.length + 2}`).format.numberFormat = '#,##0.0';
unitSheet.getRange(`K3:M${unitRows.length + 2}`).format.numberFormat = '"$"#,##0';
unitSheet.getRange(`H3:H${unitRows.length + 2}`).conditionalFormats.add(
  "containsText",
  { text: "B", format: { fill: COLORS.paleYellow, font: { color: "#9C6500" } } },
);
unitSheet.getRange(`H3:H${unitRows.length + 2}`).conditionalFormats.add(
  "containsText",
  { text: "C", format: { fill: COLORS.paleRed, font: { color: "#9C0006" } } },
);

const feeHeaders = [
  "공고번호", "국가", "시설유형", "연면적(㎡)", "공사비(USD)",
  "설계비(USD)", "감리비(USD)", "합계 용역비(USD)",
  "설계비율", "감리비율", "합계비율", "설계비 USD/㎡", "감리비 USD/㎡",
  "세금", "근거파일", "근거위치", "근거요약",
];
const feeRows = feeBenchmarks.map((row) => [
  row.bid_no, row.country, row.facility_type, row.gross_floor_area_m2,
  row.construction_cost_usd, row.design_fee_usd, row.supervision_fee_usd,
  row.combined_fee_usd, row.design_rate, row.supervision_rate, row.combined_rate,
  null, null, row.tax_note, row.source_file, row.source_locator, row.evidence_summary,
]);
const feeSheet = addDataSheet(
  "설계감리 벤치마크",
  "설계·감리·CM 비용 사례",
  feeHeaders,
  feeRows,
  {
    tableName: "FeeBenchmarks",
    freezeColumns: 3,
    wrapColumns: ["C", "N", "O", "Q"],
    widths: { A: 17, B: 15, C: 28, D: 13, E: 15, F: 15, G: 15, H: 17, I: 12, J: 12, K: 12, L: 15, M: 15, N: 18, O: 48, P: 14, Q: 46 },
  },
);
for (let row = 3; row <= feeRows.length + 2; row += 1) {
  feeSheet.getRange(`L${row}`).formulas = [[`=IF(OR(F${row}="",D${row}=""),"",F${row}/D${row})`]];
  feeSheet.getRange(`M${row}`).formulas = [[`=IF(OR(G${row}="",D${row}=""),"",G${row}/D${row})`]];
}
feeSheet.getRange(`D3:D${feeRows.length + 2}`).format.numberFormat = '#,##0.0';
feeSheet.getRange(`E3:H${feeRows.length + 2}`).format.numberFormat = '"$"#,##0';
feeSheet.getRange(`I3:K${feeRows.length + 2}`).format.numberFormat = '0.0%';
feeSheet.getRange(`L3:M${feeRows.length + 2}`).format.numberFormat = '"$"#,##0.0';

const projectHeaders = [
  "공고번호", "사업번호", "국가(한글)", "국가(영문)", "지역", "사업명",
  "입찰명(국문)", "입찰명(영문)", "시설유형", "사업유형", "계약구분",
  "계약방법", "낙찰자선정", "집행한도(USD 원문)", "집행한도(KRW 원문)",
  "공고일", "상세URL",
];
const projectRows = projects.map((row) => [
  row.bid_no, row.project_no, row.country_ko, row.country_en, row.region,
  row.project_name, row.bid_title_ko, row.bid_title_en, row.facility_type,
  row.work_type, row.contract_type, row.contract_method, row.selection_method,
  row.ceiling_usd_raw, row.ceiling_krw_raw, row.notice_date, row.detail_url,
]);
addDataSheet("공고별 사업", "건축 후보 공고별 사업 메타데이터", projectHeaders, projectRows, {
  tableName: "ProjectBids",
  freezeColumns: 4,
  wrapColumns: ["F", "G", "H", "M", "N", "O"],
  widths: { A: 17, B: 14, C: 14, D: 16, E: 16, F: 40, G: 42, H: 44, I: 20, J: 16, K: 12, L: 14, M: 24, N: 20, O: 18, P: 12, Q: 46 },
});

const evidenceHeaders = [
  "공고번호", "분류", "매칭키워드", "면적표현", "금액표현", "비율표현",
  "근거파일", "근거위치", "근거문장", "검토상태",
];
const evidenceRows = evidenceSorted.map((row) => [
  row.bid_no, row.category, row.matched_keywords, row.area_mentions,
  row.currency_mentions, row.percentage_mentions, row.source_file,
  row.source_locator, row.evidence_text, row.review_status,
]);
addDataSheet("수치 근거", "문서에서 자동 추출한 수치 근거 — 원문 검토용", evidenceHeaders, evidenceRows, {
  tableName: "NumericEvidence",
  freezeColumns: 2,
  wrapColumns: ["C", "D", "E", "F", "G", "I"],
  widths: { A: 17, B: 16, C: 24, D: 28, E: 28, F: 18, G: 54, H: 16, I: 70, J: 20 },
});

const attachmentHeaders = [
  "공고번호", "파일명", "확장자", "크기(Byte)", "상태", "SHA-256", "로컬경로", "등록일시",
];
const attachmentRows = attachments.map((row) => [
  row.bid_no, row.name, row.extension, row.bytes, row.status,
  row.sha256, row.local_path, row.registered_at,
]);
const attachmentSheet = addDataSheet("첨부파일", "원 첨부파일 다운로드·무결성 목록", attachmentHeaders, attachmentRows, {
  tableName: "Attachments",
  freezeColumns: 2,
  wrapColumns: ["B", "G"],
  widths: { A: 17, B: 50, C: 12, D: 15, E: 14, F: 68, G: 72, H: 18 },
});
attachmentSheet.getRange(`D3:D${attachmentRows.length + 2}`).format.numberFormat = '#,##0';

const fileHeaders = ["공고번호", "분석파일", "확장자", "크기(Byte)", "텍스트 청크", "근거수"];
const fileRows = analysisFiles.map((row) => [
  row.bid_no, row.source_file, row.extension, row.bytes, row.text_chunks, row.evidence_count,
]);
const fileSheet = addDataSheet("파일 인덱스", "ZIP 내부 파일 포함 분석 인덱스", fileHeaders, fileRows, {
  tableName: "AnalysisFiles",
  freezeColumns: 2,
  wrapColumns: ["B"],
  widths: { A: 17, B: 72, C: 12, D: 15, E: 15, F: 12 },
});
fileSheet.getRange(`D3:F${fileRows.length + 2}`).format.numberFormat = '#,##0';

const checklistHeaders = ["조사항목", "확인내용", "활용"];
const checklistSheet = addDataSheet("조사 체크리스트", "건축분야 심층기획조사 적용 체크리스트", checklistHeaders, checklist, {
  tableName: "SurveyChecklist",
  wrapColumns: ["A", "B", "C"],
  widths: { A: 22, B: 70, C: 42 },
});
checklistSheet.getRange(`A3:A${checklist.length + 2}`).format = {
  fill: COLORS.paleBlue,
  font: { bold: true, color: COLORS.navy },
};

// Cross-sheet formulas are added only after every referenced worksheet exists.
for (let row = 6; row < countries.length + 6; row += 1) {
  const country = countries[row - 6];
  const countryUnits = unitCosts
    .filter((item) => item.country === country && item.summary_include)
    .map((item) =>
      item.direct_unit_usd_m2
      ?? (item.construction_cost_usd / item.gross_floor_area_m2),
    )
    .filter((value) => Number.isFinite(value));
  summary.getRange(`F${row}`).formulas = [[
    `=COUNTIFS('단가 벤치마크'!$D$3:$D$${unitCosts.length + 2},E${row},'단가 벤치마크'!$I$3:$I$${unitCosts.length + 2},"예")`,
  ]];
  summary.getRange(`G${row}`).formulas = [[
    `=AVERAGEIFS('단가 벤치마크'!$M$3:$M$${unitCosts.length + 2},'단가 벤치마크'!$D$3:$D$${unitCosts.length + 2},E${row},'단가 벤치마크'!$I$3:$I$${unitCosts.length + 2},"예")`,
  ]];
  // MINIFS/MAXIFS are not available in some Excel-compatible viewers and
  // recalculate as #NAME?. Keep the auditable count/average formulas live,
  // but write this display-only range from the same source rows.
  const minUnit = Math.min(...countryUnits);
  const maxUnit = Math.max(...countryUnits);
  summary.getRange(`H${row}`).values = [[
    `${Math.round(minUnit).toLocaleString("en-US")}–${Math.round(maxUnit).toLocaleString("en-US")}`,
  ]];
}

await fs.mkdir(previewDir, { recursive: true });
const previewRanges = {
  "요약": `A1:H${noteRow + 4}`,
  "단가 벤치마크": `A1:U${unitRows.length + 2}`,
  "설계감리 벤치마크": `A1:Q${feeRows.length + 2}`,
  "공고별 사업": "A1:J18",
  "수치 근거": "A1:J18",
  "첨부파일": "A1:H18",
  "파일 인덱스": "A1:F18",
  "조사 체크리스트": `A1:C${checklist.length + 2}`,
};
for (const [sheetName, range] of Object.entries(previewRanges)) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(
    path.join(previewDir, `${sheetName.replace(/\s/g, "_")}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const checks = [];
checks.push((await workbook.inspect({
  kind: "table",
  range: `단가 벤치마크!A1:U${unitRows.length + 2}`,
  include: "values,formulas",
  tableMaxRows: 20,
  tableMaxCols: 21,
})).ndjson);
checks.push((await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
})).ndjson);
await fs.writeFile(path.join(outputDir, "verification.ndjson"), checks.join("\n"), "utf8");

const output = await SpreadsheetFile.exportXlsx(workbook);
const outputPath = path.join(outputDir, "KOICA_건축사업_과거단가_참고자료_2021-2025.xlsx");
await output.save(outputPath);
console.log(JSON.stringify({
  outputPath,
  sheets: Object.keys(previewRanges),
  projects: projectRows.length,
  attachments: attachmentRows.length,
  files: fileRows.length,
  evidence: evidenceRows.length,
  unitBenchmarks: unitRows.length,
  feeBenchmarks: feeRows.length,
}, null, 2));
