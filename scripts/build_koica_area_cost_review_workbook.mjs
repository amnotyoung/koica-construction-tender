import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const outputDir = path.join(root, "outputs", "koica-area-cost-review");
const dataPath = path.join(outputDir, "KOICA_면적금액_170공고_91사업_구조화.json");
const outputPath = path.join(outputDir, "KOICA_면적금액_170공고_91사업_전수재검토.xlsx");
const previewDir = path.join(outputDir, ".preview");

await fs.mkdir(previewDir, { recursive: true });
const data = JSON.parse(await fs.readFile(dataPath, "utf8"));
const {
  summary,
  notices,
  bid_base_groups: groups,
  projects,
  attachment_signals: attachments,
  crosswalk_reviewed66: cross66,
  crosswalk_candidate127: cross127,
} = data;

const COLORS = {
  navy: "#16324F",
  blue: "#285D7B",
  teal: "#0F6D73",
  green: "#3D7D58",
  amber: "#A96E16",
  red: "#B42318",
  gray: "#667784",
  paleBlue: "#EAF2F7",
  paleGreen: "#EAF4EC",
  paleYellow: "#FFF3D6",
  paleRed: "#FDEBE9",
  paleGray: "#F3F5F7",
  white: "#FFFFFF",
  text: "#24313D",
  line: "#D8E0E7",
};

const workbook = Workbook.create();
workbook.comments.setSelf({ displayName: "KOICA 건축조사" });

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
  sheet.getRange("A2").format.rowHeight = 42;
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
  range.format.rowHeight = 32;
}

function styleBody(range, { wrap = false, size = 8 } = {}) {
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

const dashboard = workbook.worksheets.add("요약");
const projectSheet = workbook.worksheets.add("91사업");
const noticeSheet = workbook.worksheets.add("170공고");
const groupSheet = workbook.worksheets.add("154공고군");
const attachmentSheet = workbook.worksheets.add("BOQ탐색");
const legacySheet = workbook.worksheets.add("기존66교차");
const candidateSheet = workbook.worksheets.add("기존127교차");
const criteriaSheet = workbook.worksheets.add("판정기준");

// 91 projects - primary decision table.
setTitle(
  projectSheet,
  "Y",
  "KOICA 면적·금액 91사업 재검토",
  "91개 사업번호는 91개 독립 비용표본이 아닙니다. 여러 시설·Lot·설계·감리·공사 패키지를 유지하고 대표 근거만 별도 표시했습니다.",
);
const projectHeaders = [
  "최고등급", "국가", "사업번호", "사업·대표제목", "공고수", "공고군수", "유효 면적·금액 공고수",
  "표시대표공고", "기술근거공고", "가격근거공고", "검증수준", "범위상태", "대표면적㎡",
  "대표공사금액USD", "가격단계", "명목USD/㎡", "허용용도", "직접산정", "스크리닝표본가중치",
  "다른패키지등급", "다른패키지공고", "중복·범위경고", "판정근거", "전체공고번호", "KOICA URL",
];
projectSheet.getRange("A4:Y4").values = [projectHeaders];
styleHeader(projectSheet.getRange("A4:Y4"));
const projectStart = 5;
const projectLast = projectStart + projects.length - 1;
projectSheet.getRange(`A${projectStart}:Y${projectLast}`).values = projects.map((row) => [
  row.best_grade, row.country_ko, row.project_no, row.project_name, row.notice_count,
  row.bid_base_group_count, row.valid_area_cost_notice_count, row.display_representative_bid,
  row.technical_evidence_bid, row.price_evidence_bid, row.verification_level, row.scope_status,
  row.representative_area_m2, row.representative_construction_cost_usd, row.representative_amount_stage,
  null, row.unit_cost_allowed_use, row.direct_future_estimate_ready, row.screening_sample_weight,
  row.related_other_package_grade, row.related_other_package_bid, row.duplicate_and_scope_warning,
  row.grade_detail, row.all_bid_nos, row.source_url,
]);
for (let row = projectStart; row <= projectLast; row += 1) {
  projectSheet.getRange(`P${row}`).formulas = [[`=IFERROR(N${row}/M${row},"")`]];
}
styleBody(projectSheet.getRange(`A${projectStart}:Y${projectLast}`));
projectSheet.getRange(`D${projectStart}:D${projectLast}`).format.wrapText = true;
projectSheet.getRange(`V${projectStart}:Y${projectLast}`).format.wrapText = true;
projectSheet.getRange(`E${projectStart}:G${projectLast}`).format.numberFormat = "#,##0";
projectSheet.getRange(`M${projectStart}:M${projectLast}`).format.numberFormat = "#,##0.00";
projectSheet.getRange(`N${projectStart}:N${projectLast}`).format.numberFormat = '"$"#,##0.00';
projectSheet.getRange(`P${projectStart}:P${projectLast}`).format.numberFormat = '"$"#,##0.00';
projectSheet.getRange(`R${projectStart}:S${projectLast}`).format.numberFormat = "#,##0";
gradeFormatting(projectSheet.getRange(`A${projectStart}:A${projectLast}`));
projectSheet.tables.add(`A4:Y${projectLast}`, true, "KOICAProject91");
projectSheet.freezePanes.freezeRows(4);
projectSheet.freezePanes.freezeColumns(3);
setWidths(projectSheet, {
  A: 11, B: 14, C: 14, D: 42, E: 9, F: 9, G: 13, H: 16, I: 16, J: 16,
  K: 20, L: 25, M: 14, N: 17, O: 23, P: 14, Q: 22, R: 9, S: 12, T: 20,
  U: 16, V: 38, W: 38, X: 42, Y: 28,
}, projectLast);

// 170 notices - audit trail and formula-based unit screening.
setTitle(
  noticeSheet,
  "AM",
  "KOICA 면적·금액 170공고 전수 재검토",
  "상세페이지 공고금액, 첨부 속 건축공사 예산, 면적 의미, 같은 범위 여부를 분리했습니다. T열 명목 원단위는 A/B/C/C? 검토 보조값이며 미래 견적값이 아닙니다.",
);
const noticeHeaders = [
  "등급", "사업번호", "공고번호", "공고군", "공고일", "국가", "공고명", "저장계약유형", "실제역할",
  "공고금액의미", "공고수준범위", "증거수준범위", "상세페이지한도USD", "선택공사금액USD", "가격단계",
  "한도-선택차이%", "선택면적㎡", "면적의미", "면적집계", "명목USD/㎡", "검증수준", "허용용도",
  "공고군대표", "사업대표", "기존66", "엄격첨부검증", "색인첨부", "스프레드시트", "BOQ명칭", "수량표신호",
  "가격표신호", "판정근거", "수동주의", "금액근거파일", "금액위치", "면적근거파일", "면적위치", "근거문맥",
  "KOICA URL",
];
noticeSheet.getRange("A4:AM4").values = [noticeHeaders];
styleHeader(noticeSheet.getRange("A4:AM4"));
const noticeStart = 5;
const noticeLast = noticeStart + notices.length - 1;
noticeSheet.getRange(`A${noticeStart}:AM${noticeLast}`).values = notices.map((row) => [
  row.final_grade, row.project_no, row.bid_no, row.bid_base_no, row.notice_date, row.country_ko,
  row.title, row.stored_contract_type, row.scope_role, row.record_cost_semantics, row.record_scope_status,
  row.same_scope_status, row.notice_ceiling_usd, row.selected_construction_cost_usd, row.amount_stage,
  null, row.selected_area_m2, row.area_semantics, row.area_aggregation, null, row.verification_level,
  row.unit_cost_allowed_use, row.is_bid_base_representative, row.is_project_display_representative,
  row.legacy_reviewed_case, row.strict_attachment_review, row.indexed_attachment_count, row.spreadsheet_count,
  row.boq_named_file_count, row.quantity_table_file_count, row.priced_table_file_count, row.grade_detail,
  row.manual_note, row.amount_source_file, row.amount_source_locator, row.area_source_file,
  row.area_source_locator, row.area_quote, row.source_url,
]);
for (let row = noticeStart; row <= noticeLast; row += 1) {
  noticeSheet.getRange(`P${row}`).formulas = [[`=IF(AND(M${row}<>"",N${row}<>"",O${row}<>"NOTICE_EXECUTION_CEILING"),M${row}/N${row}-1,"")`]];
  noticeSheet.getRange(`T${row}`).formulas = [[`=IFERROR(N${row}/Q${row},"")`]];
}
styleBody(noticeSheet.getRange(`A${noticeStart}:AM${noticeLast}`), { size: 8 });
noticeSheet.getRange(`G${noticeStart}:G${noticeLast}`).format.wrapText = true;
noticeSheet.getRange(`AF${noticeStart}:AM${noticeLast}`).format.wrapText = true;
noticeSheet.getRange(`M${noticeStart}:N${noticeLast}`).format.numberFormat = '"$"#,##0.00';
noticeSheet.getRange(`P${noticeStart}:P${noticeLast}`).format.numberFormat = "0.00%";
noticeSheet.getRange(`Q${noticeStart}:Q${noticeLast}`).format.numberFormat = "#,##0.00";
noticeSheet.getRange(`T${noticeStart}:T${noticeLast}`).format.numberFormat = '"$"#,##0.00';
noticeSheet.getRange(`W${noticeStart}:AE${noticeLast}`).format.numberFormat = "#,##0";
gradeFormatting(noticeSheet.getRange(`A${noticeStart}:A${noticeLast}`));
noticeSheet.tables.add(`A4:AM${noticeLast}`, true, "KOICANotices170");
noticeSheet.freezePanes.freezeRows(4);
noticeSheet.freezePanes.freezeColumns(3);
setWidths(noticeSheet, {
  A: 10, B: 14, C: 16, D: 15, E: 12, F: 14, G: 44, H: 11, I: 23, J: 22,
  K: 18, L: 29, M: 16, N: 17, O: 24, P: 13, Q: 14, R: 27, S: 24, T: 14,
  U: 24, V: 22, W: 10, X: 10, Y: 9, Z: 11, AA: 10, AB: 11, AC: 10, AD: 11,
  AE: 11, AF: 36, AG: 42, AH: 44, AI: 20, AJ: 44, AK: 20, AL: 48, AM: 28,
}, noticeLast);

// 154 bid-base groups.
setTitle(groupSheet, "P", "KOICA 154개 공고군", "동일 bid_base_no의 재공고를 묶었습니다. 다른 공고번호라도 같은 패키지일 수 있으므로 사업표의 경고를 함께 확인하십시오.");
const groupHeaders = [
  "공고군", "사업번호", "국가", "공고수", "공고번호", "대표공고", "최신일", "대표제목",
  "등급", "역할", "범위", "면적㎡", "공사금액USD", "명목USD/㎡", "중복규칙", "표본가중치",
];
groupSheet.getRange("A4:P4").values = [groupHeaders];
styleHeader(groupSheet.getRange("A4:P4"));
const groupStart = 5;
const groupLast = groupStart + groups.length - 1;
groupSheet.getRange(`A${groupStart}:P${groupLast}`).values = groups.map((row) => [
  row.bid_base_no, row.project_no, row.country_ko, row.notice_count, row.bid_nos,
  row.representative_bid_no, row.latest_notice_date, row.representative_title, row.best_grade,
  row.scope_role, row.same_scope_status, row.area_m2, row.construction_cost_usd, null,
  row.duplicate_rule, 1,
]);
for (let row = groupStart; row <= groupLast; row += 1) {
  groupSheet.getRange(`N${row}`).formulas = [[`=IFERROR(M${row}/L${row},"")`]];
}
styleBody(groupSheet.getRange(`A${groupStart}:P${groupLast}`));
groupSheet.getRange(`E${groupStart}:H${groupLast}`).format.wrapText = true;
groupSheet.getRange(`O${groupStart}:O${groupLast}`).format.wrapText = true;
groupSheet.getRange(`L${groupStart}:L${groupLast}`).format.numberFormat = "#,##0.00";
groupSheet.getRange(`M${groupStart}:N${groupLast}`).format.numberFormat = '"$"#,##0.00';
gradeFormatting(groupSheet.getRange(`I${groupStart}:I${groupLast}`));
groupSheet.tables.add(`A4:P${groupLast}`, true, "KOICABidGroups154");
groupSheet.freezePanes.freezeRows(4);
groupSheet.freezePanes.freezeColumns(2);
setWidths(groupSheet, { A: 16, B: 14, C: 14, D: 9, E: 34, F: 16, G: 12, H: 42, I: 10, J: 23, K: 26, L: 14, M: 17, N: 14, O: 45, P: 10 }, groupLast);

// Attachment table signals.  These are never promoted automatically.
setTitle(attachmentSheet, "U", "170공고 연결 첨부의 BOQ 표 신호", "첨부는 공고와 1:N입니다. 가격표·수량표 자동검출은 상품표·감리 인력표를 포함할 수 있으므로 최종 A/B가 아닙니다.");
const attachmentHeaders = [
  "사업번호", "공고번호", "역할", "파일", "확장자", "용량", "SHA256", "BOQ명칭", "blank명칭",
  "표수", "최대수량행", "최대가격행", "강한가격표", "최적시트", "시트상태", "헤더행",
  "가격행비율", "스캔오류", "잠정파일신호", "최종승격규칙", "데이터기간",
];
attachmentSheet.getRange("A4:U4").values = [attachmentHeaders];
styleHeader(attachmentSheet.getRange("A4:U4"));
const attachmentStart = 5;
const attachmentLast = attachmentStart + attachments.length - 1;
attachmentSheet.getRange(`A${attachmentStart}:U${attachmentLast}`).values = attachments.map((row) => [
  row.project_no, row.bid_no, row.scope_role, row.source_file, row.extension, row.bytes, row.sha256,
  row.boq_filename_candidate, row.blank_or_unpriced_filename, row.table_count, row.quantity_rows_max,
  row.priced_rows_max, row.strong_priced_table, row.best_sheet, row.best_sheet_state, row.best_header_row,
  row.best_priced_ratio, row.scan_error, row.provisional_file_signal, row.final_grade_rule, row.dataset_id,
]);
styleBody(attachmentSheet.getRange(`A${attachmentStart}:U${attachmentLast}`), { size: 8 });
attachmentSheet.getRange(`D${attachmentStart}:D${attachmentLast}`).format.wrapText = true;
attachmentSheet.getRange(`R${attachmentStart}:T${attachmentLast}`).format.wrapText = true;
attachmentSheet.getRange(`F${attachmentStart}:M${attachmentLast}`).format.numberFormat = "#,##0";
attachmentSheet.getRange(`Q${attachmentStart}:Q${attachmentLast}`).format.numberFormat = "0.0%";
gradeFormatting(attachmentSheet.getRange(`S${attachmentStart}:S${attachmentLast}`));
attachmentSheet.tables.add(`A4:U${attachmentLast}`, true, "KOICAAttachmentSignals");
attachmentSheet.freezePanes.freezeRows(4);
attachmentSheet.freezePanes.freezeColumns(2);
setWidths(attachmentSheet, { A: 14, B: 16, C: 23, D: 58, E: 9, F: 12, G: 22, H: 9, I: 10, J: 9, K: 11, L: 11, M: 10, N: 24, O: 11, P: 10, Q: 12, R: 30, S: 13, T: 32, U: 12 }, attachmentLast);

// Legacy 66 crosswalk.
setTitle(legacySheet, "M", "기존 reviewed_cases 66건 교차검증", "기존 A/B/C는 비교가능성 등급이므로 새 산정준비도 A/B/C로 승계하지 않았습니다.");
const legacyHeaders = [
  "공고번호", "사업번호", "기존등급", "기존면적㎡", "기존금액USD", "기존가격단계", "기존권장단가",
  "새공고등급", "새사업등급", "새범위", "매핑", "불일치규칙", "검토상태",
];
legacySheet.getRange("A4:M4").values = [legacyHeaders];
styleHeader(legacySheet.getRange("A4:M4"));
const legacyStart = 5;
const legacyLast = legacyStart + cross66.length - 1;
legacySheet.getRange(`A${legacyStart}:M${legacyLast}`).values = cross66.map((row) => [
  row.bid_no, row.project_no, row.legacy_evidence_grade, row.legacy_area_m2, row.legacy_cost_usd,
  row.legacy_cost_stage, row.legacy_recommended_unit_rate, row.new_notice_grade, row.new_project_grade,
  row.new_scope_status, row.mapping_method, row.discrepancy_rule, "재검토완료",
]);
styleBody(legacySheet.getRange(`A${legacyStart}:M${legacyLast}`));
legacySheet.getRange(`F${legacyStart}:M${legacyLast}`).format.wrapText = true;
legacySheet.getRange(`D${legacyStart}:D${legacyLast}`).format.numberFormat = "#,##0.00";
legacySheet.getRange(`E${legacyStart}:E${legacyLast}`).format.numberFormat = '"$"#,##0.00';
gradeFormatting(legacySheet.getRange(`H${legacyStart}:I${legacyLast}`));
legacySheet.tables.add(`A4:M${legacyLast}`, true, "KOICALegacy66Crosswalk");
legacySheet.freezePanes.freezeRows(4);
setWidths(legacySheet, { A: 16, B: 14, C: 10, D: 14, E: 16, F: 26, G: 14, H: 12, I: 12, J: 28, K: 16, L: 44, M: 13 }, legacyLast);

// 127 universe crosswalk.
setTitle(candidateSheet, "L", "기존 공식 원기록 127행과 새 170공고 모집단 교차", "127행·96프로젝트와 170공고·91사업은 서로 다른 모집단입니다. exact bid/project 연결만 표시했습니다.");
const candidateHeaders = [
  "원기록ID", "유효사업번호", "국가", "원기록명", "기존레코드상태", "기존프로젝트기술상태",
  "170포함", "정확공고교집합", "새사업등급", "매핑", "주의", "검토상태",
];
candidateSheet.getRange("A4:L4").values = [candidateHeaders];
styleHeader(candidateSheet.getRange("A4:L4"));
const candidateStart = 5;
const candidateLast = candidateStart + cross127.length - 1;
candidateSheet.getRange(`A${candidateStart}:L${candidateLast}`).values = cross127.map((row) => [
  row.source_record_id, row.project_no_effective, row.country_ko, row.record_title,
  row.old_record_cost_status, row.old_project_technical_status, row.in_170_universe,
  row.exact_bid_overlap, row.new_project_grade, row.mapping_method, row.warning, "교차완료",
]);
styleBody(candidateSheet.getRange(`A${candidateStart}:L${candidateLast}`));
candidateSheet.getRange(`D${candidateStart}:L${candidateLast}`).format.wrapText = true;
gradeFormatting(candidateSheet.getRange(`I${candidateStart}:I${candidateLast}`));
candidateSheet.tables.add(`A4:L${candidateLast}`, true, "KOICACandidate127Crosswalk");
candidateSheet.freezePanes.freezeRows(4);
setWidths(candidateSheet, { A: 18, B: 15, C: 14, D: 46, E: 20, F: 20, G: 10, H: 34, I: 12, J: 28, K: 38, L: 12 }, candidateLast);

// Criteria and audit findings.
setTitle(criteriaSheet, "H", "판정기준·한계", "면적과 금액의 같은 범위 여부, 가격단계, 검증수준을 등급과 분리했습니다.");
criteriaSheet.getRange("A4:H4").values = [["등급", "필수근거", "허용용도", "금지", "검증", "범위표시", "가격단계", "비고"]];
styleHeader(criteriaSheet.getRange("A4:H4"));
const criteriaRows = [
  ["A", "실제 BOQ 수량+양수 단가/금액", "검증된 범위의 BOQ 산정", "부분 Bill을 전체사업으로 환산", "V3", "FULL/PARTIAL", "설계견적 등", "A-부분은 해당 Bill만"],
  ["B", "실제 blank/unpriced BOQ 수량", "현지단가 결합 수량모델", "단가 없이 총액 확정", "V3", "FULL/PARTIAL", "가격 없음", "원천등급은 단가결합 후에도 B"],
  ["C", "같은/제한 범위 공사금액+면적", "명목 USD/㎡ 초기 스크리닝", "미래사업 견적에 직접 투입", "V3 재검토", "MATCH/PARTIAL", "한도·기초·설계예산", "계약·준공가 아님"],
  ["C?", "추출자료 기반 잠정 범위일치", "원본 V3 확인 대기", "직접 계산·의사결정", "V2R", "MATCH", "주로 집행한도", "잠정후보"],
  ["U", "면적·금액 한쪽 또는 범위충돌", "추가조사", "단가 계산", "V0~V3", "UNKNOWN/NO", "혼합", "0원으로 해석 금지"],
  ["X", "설계·감리·물품·비건축·면적오탐", "제외 근거", "건축공사비 표본 사용", "V3 범위검토", "NO", "서비스/물품", "사업 자체가 무가치하다는 뜻 아님"],
];
criteriaSheet.getRange("A5:H10").values = criteriaRows;
styleBody(criteriaSheet.getRange("A5:H10"), { wrap: true, size: 9 });
gradeFormatting(criteriaSheet.getRange("A5:A10"));
styleSection(criteriaSheet.getRange("A13:H13"), COLORS.teal);
criteriaSheet.getRange("A13").values = [["전수감사에서 확인한 데이터 문제"]];
criteriaSheet.getRange("A14:H23").merge(true);
criteriaSheet.getRange("A14:A23").values = [
  ["1. 170공고는 154 bid_base 공고군과 91 project_no로 연결되지만, 사업번호 하나에 여러 package/Lot이 있을 수 있습니다."],
  ["2. 최근 130건의 저장 계약유형은 원문과 다른 2건이 있었습니다: L2022-00034-1은 실제 공사, L2024-00076-1은 실제 설계용역."],
  ["3. 최근 130건의 공고금액 의미는 works 74, service 54, goods 2입니다."],
  ["4. 최근 공고수준 같은 범위는 MATCH 63, PARTIAL 8, NO 59입니다."],
  ["5. 역사 40건은 공사비+GFA 일치 23, 혼합/미해결 2, 서비스·비건축 제외 15입니다."],
  ["6. 집행한도와 기초·광고예산은 별도 가격단계이며 확인 사례에서 대체로 약 2~3% 차이가 났습니다."],
  ["7. 계약가·낙찰가·변경계약가·준공정산가는 현재 0건입니다."],
  ["8. HWP는 라벨과 값이 인접 문단으로 분리될 수 있어 ±2~3문단과 표 헤더를 함께 확인했습니다."],
  ["9. 자동 가격표 35건은 물품표·인력표 오탐 가능성이 있어 최종 A로 승격하지 않았습니다."],
  ["10. 기존 reviewed_cases A/B/C와 기존 127 프로젝트 C 묶음을 새 등급으로 승계하지 않았습니다."],
];
styleBody(criteriaSheet.getRange("A14:H23"), { wrap: true, size: 9 });
criteriaSheet.getRange("A14:H23").format.rowHeight = 31;
styleSection(criteriaSheet.getRange("A26:H26"), COLORS.red);
criteriaSheet.getRange("A26").values = [["미래사업 산정 사용순서"]];
criteriaSheet.getRange("A27:H31").merge(true);
criteriaSheet.getRange("A27:A31").values = [
  ["1) 91사업에서 시설·국가·공사범위가 유사한 A/B/C 기준점을 선택합니다."],
  ["2) 170공고에서 면적·금액 단계·같은 범위·근거파일을 다시 확인합니다."],
  ["3) B는 BOQ 수량에 현지 재료·노무·장비 단가를 결합하고, C는 초기 상한 스크리닝에만 씁니다."],
  ["4) 면적·시설·외부공사·세금·예비비·물가·환율을 보정하고 보정 가정을 별도 run으로 저장합니다."],
  ["5) 계약·준공 실적을 확보하기 전 결과는 예산범위이며 확정 견적이 아닙니다."],
];
styleBody(criteriaSheet.getRange("A27:H31"), { wrap: true, size: 9 });
criteriaSheet.getRange("A27:H31").format.rowHeight = 32;
criteriaSheet.freezePanes.freezeRows(4);
setWidths(criteriaSheet, { A: 13, B: 30, C: 28, D: 29, E: 14, F: 18, G: 22, H: 31 }, 31);

// Formula-driven dashboard, consuming the project and notice tables.
setTitle(dashboard, "L", "KOICA 면적·금액 전수감사 요약", "170공고 → 154공고군 → 91사업을 분리했습니다. 가장 중요한 결과는 ‘직접 산정 가능’과 ‘스크리닝 가능’을 구분하는 것입니다.");
kpiCard(dashboard, "A4:B4", "A5:B6", "공고", COLORS.blue, `=COUNTA('170공고'!$C$${noticeStart}:$C$${noticeLast})`);
kpiCard(dashboard, "D4:E4", "D5:E6", "공고군", COLORS.teal, `=COUNTA('154공고군'!$A$${groupStart}:$A$${groupLast})`);
kpiCard(dashboard, "G4:H4", "G5:H6", "사업", COLORS.navy, `=COUNTA('91사업'!$C$${projectStart}:$C$${projectLast})`);
kpiCard(dashboard, "J4:L4", "J5:L6", "직접산정 A-FULL 사업", COLORS.green, `=COUNTIF('91사업'!$R$${projectStart}:$R$${projectLast},1)`);

dashboard.getRange("A9:F9").merge();
dashboard.getRange("A9").values = [["91사업 산정준비도"]];
styleSection(dashboard.getRange("A9:F9"), COLORS.teal);
dashboard.getRange("A10:C10").values = [["등급", "사업수", "해석"]];
styleHeader(dashboard.getRange("A10:C10"));
dashboard.getRange("A11:A16").values = [["A"], ["B"], ["C"], ["C?"], ["U"], ["X"]];
dashboard.getRange("B11:B16").values = [
  [summary.project_grade_counts.A],
  [summary.project_grade_counts.B],
  [summary.project_grade_counts.C],
  [summary.project_grade_counts["C?"]],
  [summary.project_grade_counts.U],
  [summary.project_grade_counts.X],
];
dashboard.getRange("C11:C16").values = [
  ["가격 BOQ"], ["수량 BOQ"], ["수동검토 면적·금액 스크리닝"], ["원본 확인 대기"], ["추가조사"], ["공사비 표본 제외"],
];
styleBody(dashboard.getRange("A11:C16"));
gradeFormatting(dashboard.getRange("A11:A16"));
dashboard.getRange("B11:B16").format.numberFormat = "#,##0";

dashboard.getRange("E9:L9").merge();
dashboard.getRange("E9").values = [["핵심 판정"]];
styleSection(dashboard.getRange("E9:L9"), COLORS.red);
dashboard.getRange("E10:L16").merge(true);
dashboard.getRange("E10:E16").values = [
  ["직접 미래사업 산정 준비가 된 A-FULL은 1개 사업뿐입니다."],
  ["A-부분은 전체사업이 아니라 검증된 Bill 범위만 계산할 수 있습니다."],
  ["B는 BOQ 수량이 있으나 현지단가가 없어 금액을 확정할 수 없습니다."],
  ["C/C?는 공사금액÷면적 초기 스크리닝이며 계약·준공 실적이 아닙니다."],
  ["91사업을 91개 독립 단가표본으로 세면 재공고·복수 package가 중복됩니다."],
  ["서비스 공고라도 첨부에 별도 건축공사 예산이 수동 확인된 6건은 C 근거로 분리했습니다."],
  ["현지단가·물가·환율·세금·공사범위 보정 없이는 미래 견적값으로 직접 쓰지 않습니다."],
];
styleBody(dashboard.getRange("E10:L16"), { wrap: true, size: 9 });
dashboard.getRange("E10:L16").format.rowHeight = 30;

dashboard.getRange("A19:F19").merge();
dashboard.getRange("A19").values = [["2021–2025 공고금액·범위 재분류"]];
styleSection(dashboard.getRange("A19:F19"), COLORS.blue);
dashboard.getRange("A20:D20").values = [["구분", "공사", "서비스", "물품"]];
styleHeader(dashboard.getRange("A20:D20"));
dashboard.getRange("A21:D21").values = [[
  "공고금액 의미", summary.recent_2021_2025_role_counts.works,
  summary.recent_2021_2025_role_counts.service_or_other, summary.recent_2021_2025_role_counts.goods,
]];
styleBody(dashboard.getRange("A21:D21"));
dashboard.getRange("A23:D23").values = [["범위", "MATCH", "PARTIAL", "NO"]];
styleHeader(dashboard.getRange("A23:D23"));
dashboard.getRange("A24:D24").values = [[
  "공고수준", summary.recent_2021_2025_record_scope_counts.MATCH,
  summary.recent_2021_2025_record_scope_counts.PARTIAL_SCOPE,
  summary.recent_2021_2025_record_scope_counts.NO_MATCH,
]];
styleBody(dashboard.getRange("A24:D24"));
dashboard.getRange("B21:D24").format.numberFormat = "#,##0";

dashboard.getRange("F19:L19").merge();
dashboard.getRange("F19").values = [["가격단계·첨부감사"]];
styleSection(dashboard.getRange("F19:L19"), COLORS.amber);
dashboard.getRange("F20:I20").values = [["계약·준공가", "첨부행", "스프레드시트", "자동가격표신호"]];
styleHeader(dashboard.getRange("F20:I20"));
dashboard.getRange("F21:I21").values = [[
  summary.price_stage_finding.contract_or_award_or_final_cost_rows,
  summary.attachment_audit.indexed_attachment_rows,
  summary.attachment_audit.spreadsheet_rows,
  summary.attachment_audit.priced_table_signal_rows,
]];
styleBody(dashboard.getRange("F21:I21"));
dashboard.getRange("F23:L26").merge(true);
dashboard.getRange("F23:F26").values = [
  ["상세페이지 집행한도와 원문 기초·광고예산을 별도 보존했습니다."],
  ["확인 사례에서 집행한도는 기초·광고예산보다 대체로 약 2~3% 높았습니다."],
  ["자동가격표 신호는 최종 A가 아니라 탐색 후보입니다."],
  ["계약·낙찰·변경·준공 실적 확보가 다음 데이터 수집 우선순위입니다."],
];
styleBody(dashboard.getRange("F23:L26"), { wrap: true, size: 9 });
dashboard.getRange("F23:L26").format.rowHeight = 29;

dashboard.getRange("A29:L29").merge();
dashboard.getRange("A29").values = [["사용 순서"]];
styleSection(dashboard.getRange("A29:L29"), COLORS.navy);
dashboard.getRange("A30:L34").merge(true);
dashboard.getRange("A30:A34").values = [
  ["① 91사업에서 유사 시설·국가·공사범위의 기준점을 찾습니다."],
  ["② 170공고에서 공사금액·면적·가격단계·같은 범위 근거를 확인합니다."],
  ["③ A는 검증범위 BOQ, B는 수량+현지단가, C는 초기 상한 스크리닝으로만 사용합니다."],
  ["④ 면적·시설·외부공사·세금·예비비·물가·환율 보정 run을 별도로 저장합니다."],
  ["⑤ 현지 견적과 계약·준공 실적으로 교차검증하기 전 결과를 확정 견적으로 표현하지 않습니다."],
];
styleBody(dashboard.getRange("A30:L34"), { wrap: true, size: 9 });
dashboard.getRange("A30:L34").format.rowHeight = 30;
dashboard.freezePanes.freezeRows(2);
setWidths(dashboard, { A: 15, B: 13, C: 27, D: 14, E: 15, F: 15, G: 15, H: 15, I: 15, J: 15, K: 15, L: 18 }, 34);

workbook.comments.addThread(
  { cell: dashboard.getRange("J5") },
  "Source: 91사업 시트 R열 direct_future_estimate_ready. A-부분은 제외하여 A-FULL 1건만 집계합니다.",
);
workbook.comments.addThread(
  { cell: dashboard.getRange("B21") },
  "Source: 170공고 원문·제목 교차검토. 저장 계약유형 오류 L2022-00034-1, L2024-00076-1을 보정했습니다.",
);
workbook.comments.addThread(
  { cell: dashboard.getRange("F21") },
  "Source: KOICA 공개 공고·첨부. 현재 데이터에는 계약·낙찰·변경·준공 가격단계가 없습니다.",
);

// Verification: inspect key ranges, formula errors, and render major sheets.
const keyInspection = await workbook.inspect({
  kind: "table",
  range: "요약!A1:L34",
  include: "values,formulas",
  tableMaxRows: 40,
  tableMaxCols: 12,
  maxChars: 18000,
});
const projectInspection = await workbook.inspect({
  kind: "table",
  range: "91사업!A1:Y16",
  include: "values,formulas",
  tableMaxRows: 18,
  tableMaxCols: 25,
  maxChars: 20000,
});
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});

const previewSpecs = [
  ["요약", "A1:L34", "요약"],
  ["91사업", "A1:Y18", "91사업"],
  ["170공고", "A1:T18", "170공고-앞"],
  ["170공고", "U1:AM18", "170공고-근거"],
  ["154공고군", "A1:P18", "154공고군"],
  ["BOQ탐색", "A1:U18", "BOQ탐색"],
  ["기존66교차", "A1:M18", "기존66교차"],
  ["판정기준", "A1:H31", "판정기준"],
];
const rendered = [];
for (const [sheetName, range, label] of previewSpecs) {
  const blob = await workbook.render({ sheetName, range, scale: 1.0, format: "png" });
  const previewPath = path.join(previewDir, `${label}.png`);
  await fs.writeFile(previewPath, new Uint8Array(await blob.arrayBuffer()));
  rendered.push({ sheetName, range, label });
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
await fs.writeFile(
  path.join(outputDir, "workbook_verification.json"),
  `${JSON.stringify({
    keyInspection: keyInspection.ndjson,
    projectInspection: projectInspection.ndjson,
    formulaErrors: formulaErrors.ndjson,
    rendered,
    outputPath,
  }, null, 2)}\n`,
  "utf8",
);
if (process.env.KEEP_PREVIEWS !== "1") {
  await fs.rm(previewDir, { recursive: true, force: true });
}

console.log(JSON.stringify({
  outputPath,
  sheets: workbook.worksheets.items.map((sheet) => sheet.name),
  noticeRows: notices.length,
  groupRows: groups.length,
  projectRows: projects.length,
  attachmentSignalRows: attachments.length,
  crosswalk66Rows: cross66.length,
  crosswalk127Rows: cross127.length,
  formulaErrors: formulaErrors.ndjson,
  rendered,
}, null, 2));
