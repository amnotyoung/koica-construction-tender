import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const outputDir = path.join(root, "outputs", "koica-candidate-grading");
const previewDir = path.join(outputDir, "previews");
const dataPath = path.join(outputDir, "KOICA_건축후보_구조화.json");
const outputPath = path.join(outputDir, "KOICA_건축후보_127건_국가별_ABC등급.xlsx");

await fs.mkdir(previewDir, { recursive: true });
const data = JSON.parse(await fs.readFile(dataPath, "utf8"));
const { summary, candidate_records: candidates, projects, countries, attachments } = data;

const COLORS = {
  navy: "#17324D",
  blue: "#285D7B",
  teal: "#0F6D73",
  green: "#3D7D58",
  amber: "#B7791F",
  red: "#B42318",
  gray: "#657482",
  paleBlue: "#EAF2F7",
  paleGreen: "#EAF4EC",
  paleYellow: "#FFF3D6",
  paleRed: "#FDEBE9",
  paleGray: "#F4F6F8",
  white: "#FFFFFF",
  text: "#24313D",
  line: "#D7E0E7",
};

const workbook = Workbook.create();
workbook.comments.setSelf({ displayName: "User" });

function setTitle(sheet, lastColumn, title, subtitle) {
  sheet.showGridLines = false;
  sheet.getRange(`A1:${lastColumn}1`).merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1").format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white, size: 16 },
    verticalAlignment: "center",
  };
  sheet.getRange("A1").format.rowHeight = 34;
  sheet.getRange(`A2:${lastColumn}2`).merge();
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange("A2").format = {
    fill: COLORS.paleBlue,
    font: { color: COLORS.text, italic: true, size: 10 },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange("A2").format.rowHeight = 38;
}

function styleHeader(range, fill = COLORS.blue) {
  range.format = {
    fill,
    font: { bold: true, color: COLORS.white, size: 9 },
    wrapText: true,
    verticalAlignment: "center",
    horizontalAlignment: "center",
    borders: { bottom: { style: "medium", color: fill } },
  };
  range.format.rowHeight = 30;
}

function styleBody(range, { wrap = false, size = 9 } = {}) {
  range.format = {
    font: { color: COLORS.text, size },
    verticalAlignment: "top",
    wrapText: wrap,
    borders: { insideHorizontal: { style: "thin", color: "#E9EEF2" } },
  };
}

function styleSection(range, fill = COLORS.teal) {
  range.format = {
    fill,
    font: { bold: true, color: COLORS.white, size: 10 },
    verticalAlignment: "center",
  };
  range.format.rowHeight = 25;
}

function setWidths(sheet, widths, lastRow) {
  for (const [column, width] of Object.entries(widths)) {
    sheet.getRange(`${column}1:${column}${lastRow}`).format.columnWidth = width;
  }
}

function kpiCard(sheet, labelRange, valueRange, label, fill, formula, format = "#,##0") {
  sheet.getRange(labelRange).merge();
  sheet.getRange(labelRange.split(":")[0]).values = [[label]];
  sheet.getRange(labelRange).format = {
    fill,
    font: { bold: true, color: COLORS.white, size: 9 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
  };
  sheet.getRange(valueRange).merge();
  const anchor = valueRange.split(":")[0];
  sheet.getRange(anchor).formulas = [[formula]];
  sheet.getRange(valueRange).format = {
    fill: COLORS.white,
    font: { bold: true, color: COLORS.navy, size: 17 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: COLORS.line },
    numberFormat: format,
  };
}

function gradeFormatting(range) {
  range.conditionalFormats.add("beginsWith", {
    text: "A",
    format: { fill: COLORS.paleGreen, font: { bold: true, color: COLORS.green } },
  });
  range.conditionalFormats.add("beginsWith", {
    text: "B",
    format: { fill: COLORS.paleYellow, font: { bold: true, color: COLORS.amber } },
  });
  range.conditionalFormats.add("beginsWith", {
    text: "C",
    format: { fill: COLORS.paleBlue, font: { bold: true, color: COLORS.blue } },
  });
  range.conditionalFormats.add("beginsWith", {
    text: "U",
    format: { fill: COLORS.paleGray, font: { bold: true, color: COLORS.gray } },
  });
  range.conditionalFormats.add("beginsWith", {
    text: "X",
    format: { fill: COLORS.paleRed, font: { bold: true, color: COLORS.red } },
  });
}

const dashboard = workbook.worksheets.add("판정요약");
const countrySheet = workbook.worksheets.add("국가별 준비도");
const prioritySheet = workbook.worksheets.add("A·B 우선사업");
const projectSheet = workbook.worksheets.add("프로젝트 등급");
const candidateSheet = workbook.worksheets.add("127건 원기록");
const attachmentSheet = workbook.worksheets.add("첨부검사");
const criteriaSheet = workbook.worksheets.add("등급기준·한계");

// 프로젝트 등급: all formula consumers refer to this source table.
setTitle(
  projectSheet,
  "AJ",
  "KOICA 건축후보 고유 프로젝트 등급",
  "127개 공식 레코드를 사업번호·검증 별칭으로 96개 프로젝트 묶음으로 정리했습니다. A/B/C는 산정능력이고 가격단계·공사범위·검증수준은 별도 축입니다.",
);
const projectHeaders = [
  "프로젝트 최고등급", "기술상태", "국가", "사업번호", "대표 공식기록명",
  "대표 공사공고명", "공사범위", "가격단계", "검증수준", "후보레코드수",
  "연결공고수", "색인첨부수", "공사첨부수", "고유첨부수", "스프레드시트수",
  "BOQ명칭파일수", "수량표파일수", "가격표파일수", "최대수량행", "최대가격행",
  "GFA 값", "직접산정", "현지단가필요", "스크리닝만", "표본가중치",
  "검증금액", "통화", "검증금액/㎡", "검증 품목메모", "근거파일",
  "근거위치", "차단요인", "다음조치", "검토상태", "연결공고번호", "해석경계",
];
projectSheet.getRange("A4:AJ4").values = [projectHeaders];
styleHeader(projectSheet.getRange("A4:AJ4"));
const projectStart = 5;
const projectLast = projectStart + projects.length - 1;
projectSheet.getRange(`A${projectStart}:AJ${projectLast}`).values = projects.map((row) => [
  row.grade, row.technical_status, row.country_ko, row.project_no,
  row.representative_title, row.representative_construction_bid_title,
  row.scope_status, row.price_stage, row.verification_level,
  row.candidate_record_count, row.linked_bid_count, row.indexed_attachment_count,
  row.construction_attachment_count, row.unique_attachment_count, row.spreadsheet_count,
  row.boq_named_file_count, row.quantity_table_file_count, row.priced_table_file_count,
  row.max_quantity_rows_detected, row.max_priced_rows_detected,
  row.gross_floor_area_m2_values, row.direct_project_estimate_ready,
  row.needs_local_rates, row.only_screening_or_trace, row.sample_weight,
  row.verified_cost_amount, row.verified_cost_currency, row.verified_cost_per_gfa_m2,
  row.verified_item_note, row.evidence_file, row.evidence_location,
  row.blocking_issue, row.next_action, row.review_status, row.linked_bid_nos,
  row.claim_boundary,
]);
styleBody(projectSheet.getRange(`A${projectStart}:AJ${projectLast}`), { wrap: false, size: 8 });
projectSheet.getRange(`E${projectStart}:F${projectLast}`).format.wrapText = true;
projectSheet.getRange(`AC${projectStart}:AJ${projectLast}`).format.wrapText = true;
projectSheet.getRange(`J${projectStart}:T${projectLast}`).format.numberFormat = "#,##0";
projectSheet.getRange(`V${projectStart}:Y${projectLast}`).format.numberFormat = "#,##0";
projectSheet.getRange(`Z${projectStart}:Z${projectLast}`).format.numberFormat = "#,##0.00";
projectSheet.getRange(`AB${projectStart}:AB${projectLast}`).format.numberFormat = '"$"#,##0.00';
gradeFormatting(projectSheet.getRange(`A${projectStart}:B${projectLast}`));
projectSheet.tables.add(`A4:AJ${projectLast}`, true, "KOICAProjectGrades");
projectSheet.freezePanes.freezeRows(4);
projectSheet.freezePanes.freezeColumns(4);
setWidths(projectSheet, {
  A: 12, B: 12, C: 13, D: 14, E: 34, F: 34, G: 16, H: 17, I: 10,
  J: 10, K: 10, L: 11, M: 11, N: 11, O: 11, P: 11, Q: 11, R: 11,
  S: 11, T: 11, U: 16, V: 9, W: 11, X: 11, Y: 10, Z: 15, AA: 8,
  AB: 15, AC: 34, AD: 46, AE: 34, AF: 32, AG: 32, AH: 16, AI: 34, AJ: 38,
}, projectLast);

// Country roll-up is formula-driven from the project table.
setTitle(
  countrySheet,
  "L",
  "국가별 건축비 산정 준비도",
  "최고등급은 그 국가에서 확인된 최소 1개 사업의 준비도입니다. 국가 대표단가 또는 충분한 국가표본을 뜻하지 않습니다.",
);
countrySheet.getRange("A4:L4").values = [[
  "국가", "최고 사업등급", "프로젝트수", "A", "B", "C묶음", "C잠정", "U",
  "연결공고", "색인첨부", "표본충분성", "해석",
]];
styleHeader(countrySheet.getRange("A4:L4"));
const countryStart = 5;
const countryLast = countryStart + countries.length - 1;
countrySheet.getRange(`A${countryStart}:L${countryLast}`).values = countries.map((row) => [
  row.country_ko, null, null, null, null, null, null, null, null, null, null,
  "최고등급은 해당 국가의 최소 1개 사업 근거이며 국가 대표단가가 아님",
]);
for (let row = countryStart; row <= countryLast; row += 1) {
  countrySheet.getRange(`B${row}`).formulas = [[`=IF(D${row}>0,"A",IF(E${row}>0,"B","C"))`]];
  countrySheet.getRange(`C${row}`).formulas = [[`=COUNTIF('프로젝트 등급'!$C$${projectStart}:$C$${projectLast},A${row})`]];
  countrySheet.getRange(`D${row}`).formulas = [[`=COUNTIFS('프로젝트 등급'!$C$${projectStart}:$C$${projectLast},A${row},'프로젝트 등급'!$A$${projectStart}:$A$${projectLast},"A")`]];
  countrySheet.getRange(`E${row}`).formulas = [[`=COUNTIFS('프로젝트 등급'!$C$${projectStart}:$C$${projectLast},A${row},'프로젝트 등급'!$A$${projectStart}:$A$${projectLast},"B")`]];
  countrySheet.getRange(`F${row}`).formulas = [[`=COUNTIFS('프로젝트 등급'!$C$${projectStart}:$C$${projectLast},A${row},'프로젝트 등급'!$A$${projectStart}:$A$${projectLast},"C")`]];
  countrySheet.getRange(`G${row}`).formulas = [[`=COUNTIFS('프로젝트 등급'!$C$${projectStart}:$C$${projectLast},A${row},'프로젝트 등급'!$B$${projectStart}:$B$${projectLast},"C?")`]];
  countrySheet.getRange(`H${row}`).formulas = [[`=COUNTIFS('프로젝트 등급'!$C$${projectStart}:$C$${projectLast},A${row},'프로젝트 등급'!$B$${projectStart}:$B$${projectLast},"U")`]];
  countrySheet.getRange(`I${row}`).formulas = [[`=SUMIF('프로젝트 등급'!$C$${projectStart}:$C$${projectLast},A${row},'프로젝트 등급'!$K$${projectStart}:$K$${projectLast})`]];
  countrySheet.getRange(`J${row}`).formulas = [[`=SUMIF('프로젝트 등급'!$C$${projectStart}:$C$${projectLast},A${row},'프로젝트 등급'!$L$${projectStart}:$L$${projectLast})`]];
  countrySheet.getRange(`K${row}`).formulas = [[`=IF(D${row}>=3,"초기 국가모형 가능(독립성 추가검증)",IF(D${row}>0,"가격사례 부족: 사업별 기준점",IF(E${row}>0,"수량사례만: 현지단가 필요","직접 산정근거 없음")))`]];
}
styleBody(countrySheet.getRange(`A${countryStart}:L${countryLast}`), { wrap: false, size: 9 });
countrySheet.getRange(`K${countryStart}:L${countryLast}`).format.wrapText = true;
countrySheet.getRange(`C${countryStart}:J${countryLast}`).format.numberFormat = "#,##0";
gradeFormatting(countrySheet.getRange(`B${countryStart}:B${countryLast}`));
countrySheet.tables.add(`A4:L${countryLast}`, true, "KOICACountryReadiness");
countrySheet.freezePanes.freezeRows(4);
countrySheet.freezePanes.freezeColumns(2);
setWidths(countrySheet, { A: 18, B: 12, C: 11, D: 8, E: 8, F: 10, G: 10, H: 8, I: 11, J: 11, K: 34, L: 38 }, countryLast);

// Verified A/B priority list linked back to the project source rows.
setTitle(
  prioritySheet,
  "L",
  "검증된 A·B 우선사업 8개",
  "A 2개는 KOICA-only 직접 설계견적 기준점, B 6개는 현지단가 결합 즉시 수량기반 견적으로 전환할 수 있는 우선사업입니다.",
);
prioritySheet.getRange("A4:L4").values = [[
  "등급", "기술상태", "국가", "사업번호", "사업명", "범위", "가격단계",
  "검증금액", "통화", "검증금액/㎡", "차단요인", "다음조치",
]];
styleHeader(prioritySheet.getRange("A4:L4"));
const priorityProjects = projects
  .filter((row) => ["A", "B"].includes(row.grade))
  .sort((left, right) => left.grade.localeCompare(right.grade) || left.country_ko.localeCompare(right.country_ko));
const projectRowByKey = new Map(projects.map((row, index) => [row.project_key, projectStart + index]));
const priorityStart = 5;
const priorityLast = priorityStart + priorityProjects.length - 1;
for (let index = 0; index < priorityProjects.length; index += 1) {
  const row = priorityStart + index;
  const sourceRow = projectRowByKey.get(priorityProjects[index].project_key);
  prioritySheet.getRange(`A${row}:G${row}`).formulas = [[
    ...["A", "B", "C", "D", "E", "G", "H"].map(
      (column) => `='프로젝트 등급'!${column}${sourceRow}`,
    ),
  ]];
  prioritySheet.getRange(`H${row}`).formulas = [[`=IF('프로젝트 등급'!Z${sourceRow}="","",'프로젝트 등급'!Z${sourceRow})`]];
  prioritySheet.getRange(`I${row}`).formulas = [[`=IF('프로젝트 등급'!AA${sourceRow}="","",'프로젝트 등급'!AA${sourceRow})`]];
  prioritySheet.getRange(`J${row}`).formulas = [[`=IF('프로젝트 등급'!AB${sourceRow}="","",'프로젝트 등급'!AB${sourceRow})`]];
  prioritySheet.getRange(`K${row}:L${row}`).formulas = [[
    `='프로젝트 등급'!AF${sourceRow}`,
    `='프로젝트 등급'!AG${sourceRow}`,
  ]];
}
styleBody(prioritySheet.getRange(`A${priorityStart}:L${priorityLast}`), { wrap: false, size: 9 });
prioritySheet.getRange(`E${priorityStart}:G${priorityLast}`).format.wrapText = true;
prioritySheet.getRange(`K${priorityStart}:L${priorityLast}`).format.wrapText = true;
prioritySheet.getRange(`H${priorityStart}:H${priorityLast}`).format.numberFormat = "#,##0.00";
prioritySheet.getRange(`J${priorityStart}:J${priorityLast}`).format.numberFormat = '"$"#,##0.00';
prioritySheet.getRange(`A${priorityStart}:L${priorityLast}`).format.rowHeight = 38;
gradeFormatting(prioritySheet.getRange(`A${priorityStart}:B${priorityLast}`));
prioritySheet.tables.add(`A4:L${priorityLast}`, true, "KOICAPriorityProjects");
prioritySheet.freezePanes.freezeRows(4);
setWidths(prioritySheet, { A: 9, B: 11, C: 16, D: 14, E: 42, F: 18, G: 18, H: 16, I: 8, J: 16, K: 34, L: 34 }, priorityLast);

// Original 127 official records.
setTitle(
  candidateSheet,
  "AF",
  "공식 건축관련후보 127건 원기록 감사표",
  "행 ID를 보존하면서 프로젝트 최고등급과 해당 공식기록 자체의 비용표본 상태를 분리했습니다. 보고서 전체사업예산·설계감리비는 건축공사비로 사용하지 않습니다.",
);
const candidateHeaders = [
  "순번", "프로젝트등급", "기술상태", "기록비용상태", "국가", "원천데이터",
  "원천레코드ID", "원사업번호", "유효사업번호", "연결방법", "연결점수",
  "조달구분", "기록명", "공사범위", "금액통화", "금액", "금액역할",
  "연면적㎡", "계획원단위 KRW/㎡", "연결공고수", "연결공고", "색인첨부수",
  "스프레드시트수", "BOQ명칭파일수", "수량표파일수", "가격표파일수",
  "검증금액", "검증통화", "검증금액/㎡", "근거파일", "차단요인", "공식URL",
];
candidateSheet.getRange("A4:AF4").values = [candidateHeaders];
styleHeader(candidateSheet.getRange("A4:AF4"));
const candidateStart = 5;
const candidateLast = candidateStart + candidates.length - 1;
candidateSheet.getRange(`A${candidateStart}:AF${candidateLast}`).values = candidates.map((row) => [
  row.candidate_no, row.project_best_grade, row.project_technical_status,
  row.record_cost_status, row.country_ko, row.source_dataset, row.source_record_id,
  row.project_no_linked, row.project_no_effective, row.project_link_method,
  Number(row.project_link_score || 0), row.procurement_category, row.record_title,
  row.record_scope, row.amount_currency, row.amount_value, row.amount_role,
  row.gross_floor_area_m2, row.raw_ceiling_per_gfa_krw, row.linked_bid_count,
  row.linked_bid_nos, row.indexed_attachment_count, row.spreadsheet_count,
  row.boq_named_file_count, row.quantity_table_file_count, row.priced_table_file_count,
  row.verified_cost_amount, row.verified_cost_currency, row.verified_cost_per_gfa_m2,
  row.evidence_file, row.blocking_issue, row.official_record_url,
]);
styleBody(candidateSheet.getRange(`A${candidateStart}:AF${candidateLast}`), { wrap: false, size: 8 });
candidateSheet.getRange(`M${candidateStart}:N${candidateLast}`).format.wrapText = true;
candidateSheet.getRange(`AD${candidateStart}:AF${candidateLast}`).format.wrapText = true;
candidateSheet.getRange(`K${candidateStart}:K${candidateLast}`).format.numberFormat = "0.000";
candidateSheet.getRange(`P${candidateStart}:P${candidateLast}`).format.numberFormat = "#,##0.00";
candidateSheet.getRange(`R${candidateStart}:S${candidateLast}`).format.numberFormat = "#,##0.00";
candidateSheet.getRange(`AA${candidateStart}:AA${candidateLast}`).format.numberFormat = "#,##0.00";
candidateSheet.getRange(`AC${candidateStart}:AC${candidateLast}`).format.numberFormat = '"$"#,##0.00';
gradeFormatting(candidateSheet.getRange(`B${candidateStart}:D${candidateLast}`));
candidateSheet.tables.add(`A4:AF${candidateLast}`, true, "KOICAOfficial127Audit");
candidateSheet.freezePanes.freezeRows(4);
candidateSheet.freezePanes.freezeColumns(4);
setWidths(candidateSheet, {
  A: 8, B: 11, C: 12, D: 22, E: 15, F: 22, G: 16, H: 14, I: 14, J: 24,
  K: 10, L: 11, M: 42, N: 42, O: 10, P: 15, Q: 20, R: 13, S: 17, T: 10,
  U: 35, V: 11, W: 11, X: 11, Y: 11, Z: 11, AA: 15, AB: 9, AC: 15,
  AD: 46, AE: 34, AF: 38,
}, candidateLast);

// File-level audit inventory.
setTitle(
  attachmentSheet,
  "T",
  "후보 연결 첨부파일 일괄검사",
  "현재 공고 72개의 중첩 파일 1,642개를 색인했고, 공사공고의 스프레드시트에서 BOQ 헤더·수량행·가격행을 검사했습니다. 파일명만으로 등급을 올리지 않습니다.",
);
const attachmentHeaders = [
  "사업키", "공고번호", "계약구분", "공고명", "공사비관련공고", "확장자",
  "원본파일", "바이트", "SHA-256", "중복스캔재사용", "BOQ명칭후보",
  "blank/unpriced", "검출표수", "최대수량행", "최대가격행", "가격행비율",
  "강한가격표", "대표시트", "시트상태", "스캔오류",
];
attachmentSheet.getRange("A4:T4").values = [attachmentHeaders];
styleHeader(attachmentSheet.getRange("A4:T4"));
const attachmentStart = 5;
const attachmentLast = attachmentStart + attachments.length - 1;
attachmentSheet.getRange(`A${attachmentStart}:T${attachmentLast}`).values = attachments.map((row) => [
  row.project_key, row.bid_no, row.bid_contract_type, row.bid_title,
  row.construction_bid_cost_relevant, row.extension, row.source_file, row.bytes,
  row.sha256, row.duplicate_scan_reused, row.boq_filename_candidate,
  row.blank_or_unpriced_filename, row.table_count, row.quantity_rows_max,
  row.priced_rows_max, row.best_priced_ratio, row.strong_priced_table,
  row.best_sheet, row.best_sheet_state, row.scan_error,
]);
styleBody(attachmentSheet.getRange(`A${attachmentStart}:T${attachmentLast}`), { wrap: false, size: 8 });
attachmentSheet.getRange(`D${attachmentStart}:D${attachmentLast}`).format.wrapText = true;
attachmentSheet.getRange(`G${attachmentStart}:G${attachmentLast}`).format.wrapText = true;
attachmentSheet.getRange(`H${attachmentStart}:H${attachmentLast}`).format.numberFormat = "#,##0";
attachmentSheet.getRange(`M${attachmentStart}:O${attachmentLast}`).format.numberFormat = "#,##0";
attachmentSheet.getRange(`P${attachmentStart}:P${attachmentLast}`).format.numberFormat = "0.0%";
attachmentSheet.tables.add(`A4:T${attachmentLast}`, true, "KOICAAttachmentAudit");
attachmentSheet.freezePanes.freezeRows(4);
attachmentSheet.freezePanes.freezeColumns(2);
setWidths(attachmentSheet, {
  A: 15, B: 15, C: 10, D: 38, E: 12, F: 9, G: 58, H: 12, I: 22, J: 12,
  K: 12, L: 13, M: 10, N: 11, O: 11, P: 11, Q: 11, R: 22, S: 11, T: 28,
}, attachmentLast);

// Methodology and claim boundaries.
setTitle(
  criteriaSheet,
  "H",
  "등급기준·가격단계·해석 한계",
  "등급, 가격단계, 공사범위, 검증수준을 분리합니다. A라고 해서 계약·준공 실적이거나 국가 대표가격인 것은 아닙니다.",
);
criteriaSheet.getRange("A4:H4").merge();
criteriaSheet.getRange("A4").values = [["A/B/C 및 보조상태"]];
styleSection(criteriaSheet.getRange("A4:H4"));
criteriaSheet.getRange("A5:D10").values = [
  ["상태", "필수근거", "가능한 활용", "금지 해석"],
  ["A", "품목 설명·단위·수량 + 양수 단가/금액", "수량×단가 상세견적", "계약·준공가 또는 국가 대표단가"],
  ["B", "품목 설명·단위·수량, usable 단가 없음", "현지단가 입력형 수량견적", "현재 직접 공사비 확정"],
  ["C", "범위 일치 공사한도 + GFA", "초기 원단위 스크리닝", "BOQ 합계 또는 실제 공사비"],
  ["U", "건축후보이나 직접 요건 미충족", "추가 첨부·OCR·수동검토", "0 또는 저위험"],
  ["X", "설계·감리·물품·전체사업비", "건축공사비 표본에서 제외", "건축단가 산정"],
];
styleHeader(criteriaSheet.getRange("A5:D5"), COLORS.blue);
styleBody(criteriaSheet.getRange("A6:D10"), { wrap: true });
criteriaSheet.getRange("A12:H12").merge();
criteriaSheet.getRange("A12").values = [["별도 판정축"]];
styleSection(criteriaSheet.getRange("A12:H12"));
criteriaSheet.getRange("A13:D20").values = [
  ["축", "값", "뜻", "적용"],
  ["가격단계", "DESIGN_ESTIMATE", "설계·엔지니어 견적", "가나·IKHCC A"],
  ["가격단계", "PLAN_CEILING", "연간발주계획 한도", "C 잠정후보"],
  ["가격단계", "NONE", "가격 없음", "B"],
  ["공사범위", "FULL", "주요 공종 전체 패키지", "가나 등"],
  ["공사범위", "PARTIAL_BOUNDED", "특정 시설·Bill·공종", "IKHCC·도미니카·자이툰"],
  ["검증수준", "V2", "표·셀 자동추출", "물음표 상태"],
  ["검증수준", "V3", "원문 의미·범위 수동확인", "확정 A/B"],
];
styleHeader(criteriaSheet.getRange("A13:D13"), COLORS.blue);
styleBody(criteriaSheet.getRange("A14:D20"), { wrap: true });
criteriaSheet.getRange("A22:H22").merge();
criteriaSheet.getRange("A22").values = [["검사범위·출처"]];
styleSection(criteriaSheet.getRange("A22:H22"));
criteriaSheet.getRange("A23:B31").values = [
  ["공식 후보", "127행 / 39개 국가·지역"],
  ["유효 프로젝트 묶음", "96개"],
  ["현재 공고 연결", "98개"],
  ["최상위 첨부", "266개"],
  ["첨부·중첩 색인파일", "1,642개"],
  ["KOICA 연간발주계획", "https://www.data.go.kr/data/15085055/fileData.do"],
  ["KOICA 원조조달계약", "https://www.data.go.kr/data/15073135/fileData.do"],
  ["KOICA 국별사업보고서", "https://www.data.go.kr/data/15052832/fileData.do"],
  ["경계", "현재 127 후보집합의 준비도이며 KOICA 전체 사업 모집단이 아님"],
];
styleBody(criteriaSheet.getRange("A23:B31"), { wrap: true });
criteriaSheet.getRange("A33:B33").values = [["검증 메트릭", "값"]];
styleHeader(criteriaSheet.getRange("A33:B33"), COLORS.blue);
criteriaSheet.getRange("A34:B46").values = [
  ["공식 레코드", summary.candidate_records],
  ["프로젝트 묶음", summary.unique_candidate_projects],
  ["국가·지역", summary.countries_including_unknown],
  ["현재공고 연결 레코드", summary.connected_candidate_records],
  ["현재공고 연결 프로젝트", summary.connected_candidate_projects],
  ["현재공고 연결 국가", summary.connected_countries],
  ["현재 연결공고", summary.current_candidate_bids],
  ["첨부보유 레코드", summary.attachment_candidate_records],
  ["첨부보유 프로젝트", summary.attachment_candidate_projects],
  ["첨부보유 국가", summary.attachment_countries],
  ["색인파일 보유 공고", summary.current_bids_with_indexed_files],
  ["색인파일", summary.indexed_candidate_attachments],
  ["최상위 첨부", summary.top_level_candidate_attachments],
];
styleBody(criteriaSheet.getRange("A34:B46"));
criteriaSheet.getRange("B34:B46").format.numberFormat = "#,##0";
criteriaSheet.freezePanes.freezeRows(2);
setWidths(criteriaSheet, { A: 24, B: 42, C: 38, D: 38, E: 14, F: 14, G: 14, H: 14 }, 46);

// Dashboard after source sheets exist so all formulas resolve.
setTitle(
  dashboard,
  "L",
  "KOICA 건축후보 127건 일괄검사 판정",
  "결론: KOICA-only 직접 설계견적 A는 2사업, 수량 BOQ B는 6사업입니다. 127행을 127개 비용표본으로 세면 안 되며, 국가단가를 만들기에는 A 표본이 부족합니다.",
);
kpiCard(dashboard, "A4:C4", "A5:C7", "공식 후보 레코드", COLORS.blue, `=COUNTA('127건 원기록'!$G$${candidateStart}:$G$${candidateLast})`);
kpiCard(dashboard, "D4:F4", "D5:F7", "고유 프로젝트 묶음", COLORS.teal, `=COUNTA('프로젝트 등급'!$A$${projectStart}:$A$${projectLast})`);
kpiCard(dashboard, "G4:I4", "G5:I7", "A 직접설계견적", COLORS.green, `=COUNTIF('프로젝트 등급'!$A$${projectStart}:$A$${projectLast},"A")`);
kpiCard(dashboard, "J4:L4", "J5:L7", "B 수량BOQ", COLORS.amber, `=COUNTIF('프로젝트 등급'!$A$${projectStart}:$A$${projectLast},"B")`);
kpiCard(dashboard, "A9:C9", "A10:C12", "C 잠정 원단위", COLORS.blue, `=COUNTIF('프로젝트 등급'!$B$${projectStart}:$B$${projectLast},"C?")`);
kpiCard(dashboard, "D9:F9", "D10:F12", "U 직접근거 부족", COLORS.gray, `=COUNTIF('프로젝트 등급'!$B$${projectStart}:$B$${projectLast},"U")`);
kpiCard(dashboard, "G9:I9", "G10:I12", "현재 연결공고", COLORS.teal, "='등급기준·한계'!B40");
kpiCard(dashboard, "J9:L9", "J10:L12", "첨부·중첩 색인파일", COLORS.navy, `=COUNTA('첨부검사'!$G$${attachmentStart}:$G$${attachmentLast})`);

dashboard.getRange("A14:B14").values = [["국가 최고등급", "국가수"]];
styleHeader(dashboard.getRange("A14:B14"));
dashboard.getRange("A15:A17").values = [["A"], ["B"], ["C"]];
for (let row = 15; row <= 17; row += 1) {
  dashboard.getRange(`B${row}`).formulas = [[`=COUNTIF('국가별 준비도'!$B$${countryStart}:$B$${countryLast},A${row})`]];
}
styleBody(dashboard.getRange("A15:B17"));
gradeFormatting(dashboard.getRange("A15:A17"));
const countryChart = dashboard.charts.add("bar", dashboard.getRange("A14:B17"));
countryChart.title = "국가별 최고 사업등급 (국가수)";
countryChart.hasLegend = false;
countryChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
countryChart.yAxis = { numberFormatCode: "0" };
countryChart.setPosition("D14", "I27");

dashboard.getRange("J14:L14").values = [["프로젝트 상태", "수", "뜻"]];
styleHeader(dashboard.getRange("J14:L14"));
dashboard.getRange("J15:J18").values = [["A"], ["B"], ["C?"], ["U"]];
dashboard.getRange("L15:L18").values = [["직접 설계견적"], ["현지단가 필요"], ["초기 원단위"], ["추가확인"]];
dashboard.getRange("K15").formulas = [[`=COUNTIF('프로젝트 등급'!$A$${projectStart}:$A$${projectLast},"A")`]];
dashboard.getRange("K16").formulas = [[`=COUNTIF('프로젝트 등급'!$A$${projectStart}:$A$${projectLast},"B")`]];
dashboard.getRange("K17").formulas = [[`=COUNTIF('프로젝트 등급'!$B$${projectStart}:$B$${projectLast},"C?")`]];
dashboard.getRange("K18").formulas = [[`=COUNTIF('프로젝트 등급'!$B$${projectStart}:$B$${projectLast},"U")`]];
styleBody(dashboard.getRange("J15:L18"), { wrap: true });
gradeFormatting(dashboard.getRange("J15:J18"));

dashboard.getRange("A29:L29").merge();
dashboard.getRange("A29").values = [["핵심 판정"]];
styleSection(dashboard.getRange("A29:L29"));
dashboard.getRange("A30:L34").merge(true);
dashboard.getRange("A30:A34").values = [
  ["• A 2사업: 가나 설계·집행예산 USD 4.333m(전체), 이라크 IKHCC USD 8.373m(건축 Bill 부분)"],
  ["• B 6사업: 볼리비아·도미니카공화국·우즈베키스탄·이라크 자이툰·캄보디아·피지"],
  ["• C 잠정 3사업: 인도네시아 2개와 키르기스스탄 1개; BOQ 확인 전 계획한도÷GFA 스크리닝만"],
  ["• 가나와 이라크도 가격 있는 고유 프로젝트가 각 1개뿐이므로 국가 대표단가를 만들기에는 부족"],
  ["• 우간다 기존 B 사례 2019-00005는 공식 127행 밖이므로 이번 집계에서 제외"],
];
styleBody(dashboard.getRange("A30:L34"), { wrap: true, size: 10 });
dashboard.getRange("A30:L34").format.rowHeight = 28;

dashboard.getRange("A36:F36").values = [["첨부 도달 단계", "레코드", "프로젝트", "국가", "공고", "파일"]];
styleHeader(dashboard.getRange("A36:F36"), COLORS.blue);
dashboard.getRange("A37:A39").values = [["공식 후보"], ["현재 공고 연결"], ["실제 첨부·색인"]];
dashboard.getRange("B37:F39").formulas = [
  ["='등급기준·한계'!B34", "='등급기준·한계'!B35", "='등급기준·한계'!B36", null, null],
  ["='등급기준·한계'!B37", "='등급기준·한계'!B38", "='등급기준·한계'!B39", "='등급기준·한계'!B40", null],
  ["='등급기준·한계'!B41", "='등급기준·한계'!B42", "='등급기준·한계'!B43", "='등급기준·한계'!B44", "='등급기준·한계'!B45"],
];
styleBody(dashboard.getRange("A37:F39"));
dashboard.getRange("B37:F39").format.numberFormat = "#,##0";
dashboard.getRange("H36:L36").merge();
dashboard.getRange("H36").values = [["해석 경계"]];
styleSection(dashboard.getRange("H36:L36"), COLORS.red);
dashboard.getRange("H37:L40").merge(true);
dashboard.getRange("H37:H40").values = [
  ["A는 설계견적 산정능력이며 계약·준공 실적을 뜻하지 않습니다."],
  ["B는 수량 기반 템플릿으로, 현지단가 없이는 금액을 확정할 수 없습니다."],
  ["C/U/X를 0원 또는 저비용으로 해석하지 않습니다."],
  ["국가 최고등급은 시설유형·지역·가격시점 전체를 대표하지 않습니다."],
];
styleBody(dashboard.getRange("H37:L40"), { wrap: true, size: 9 });
dashboard.getRange("H37:L40").format.rowHeight = 28;
dashboard.freezePanes.freezeRows(2);
setWidths(dashboard, { A: 16, B: 13, C: 13, D: 13, E: 13, F: 13, G: 13, H: 13, I: 13, J: 15, K: 10, L: 22 }, 40);

// Compact formula audit and visual pass for every sheet.
const keyInspection = await workbook.inspect({
  kind: "table",
  range: "판정요약!A1:L40",
  include: "values,formulas",
  tableMaxRows: 45,
  tableMaxCols: 12,
  maxChars: 18000,
});
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
const previewSpecs = [
  ["판정요약", "A1:L40", "판정요약"],
  ["국가별 준비도", `A1:L${Math.min(countryLast, 30)}`, "국가별 준비도"],
  ["A·B 우선사업", `A1:L${priorityLast}`, "A·B 우선사업"],
  ["프로젝트 등급", "A1:L20", "프로젝트 등급-앞"],
  ["프로젝트 등급", "Y1:AJ20", "프로젝트 등급-근거"],
  ["127건 원기록", "A1:N20", "127건 원기록-앞"],
  ["127건 원기록", "T1:AF20", "127건 원기록-근거"],
  ["첨부검사", "A1:J24", "첨부검사-앞"],
  ["첨부검사", "K1:T24", "첨부검사-검출"],
  ["등급기준·한계", "A1:H46", "등급기준·한계"],
];
const previews = [];
for (const [sheetName, range, label] of previewSpecs) {
  const blob = await workbook.render({ sheetName, range, scale: 1.05, format: "png" });
  const previewPath = path.join(previewDir, `${label}.png`);
  await fs.writeFile(previewPath, new Uint8Array(await blob.arrayBuffer()));
  previews.push({ sheetName, range, previewPath });
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
await fs.writeFile(
  path.join(outputDir, "workbook_verification.json"),
  `${JSON.stringify({ keyInspection: keyInspection.ndjson, formulaErrors: formulaErrors.ndjson, previews, outputPath }, null, 2)}\n`,
  "utf8",
);

console.log(JSON.stringify({
  outputPath,
  sheets: workbook.worksheets.items.map((sheet) => sheet.name),
  candidateRows: candidates.length,
  projectRows: projects.length,
  countryRows: countries.length,
  attachmentRows: attachments.length,
  formulaErrors: formulaErrors.ndjson,
  previews,
}, null, 2));
