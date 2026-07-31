import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const outputDir = path.join(root, "outputs", "koica-only-pilot");
const previewDir = path.join(outputDir, "ikhcc-previews");
const dataPath = path.join(outputDir, "KOICA_IKHCC_숨김단가_구조화.json");
const auditPath = path.join(outputDir, "KOICA_중첩자료_회수감사.json");
const outputPath = path.join(
  outputDir,
  "KOICA_only_IKHCC_숨김설계단가_복원.xlsx",
);

await fs.mkdir(previewDir, { recursive: true });
const data = JSON.parse(await fs.readFile(dataPath, "utf8"));
const audit = JSON.parse(await fs.readFile(auditPath, "utf8"));
const summary = data.summary;
const boqItems = data.boq_items;
const rateLibrary = data.rate_library;
const sectionRows = data.section_rows;

const COLORS = {
  navy: "#17324D",
  blue: "#285D7B",
  teal: "#0F6D73",
  green: "#3D7D58",
  amber: "#B7791F",
  red: "#B42318",
  paleBlue: "#EAF2F7",
  paleTeal: "#E7F4F3",
  paleGreen: "#EAF4EC",
  paleYellow: "#FFF3D6",
  paleRed: "#FDEBE9",
  paleGray: "#F4F6F8",
  white: "#FFFFFF",
  text: "#24313D",
  muted: "#657482",
  line: "#D7E0E7",
  input: "#FFF2CC",
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
    borders: {
      insideHorizontal: { style: "thin", color: "#E9EEF2" },
    },
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

function kpiCard(sheet, labelRange, valueRange, label, fill, formula, format) {
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

function literalFormula(value) {
  const text = String(value ?? "");
  return text.startsWith("=") ? `'${text}` : text;
}

const verdict = workbook.worksheets.add("판정");
const application = workbook.worksheets.add("미래사업 적용");
const sections = workbook.worksheets.add("시설·공종 요약");
const items = workbook.worksheets.add("BOQ 수량·단가");
const rates = workbook.worksheets.add("숨김 단가 라이브러리");
const auditSheet = workbook.worksheets.add("회수감사·한계");

// BOQ 수량·단가
setTitle(
  items,
  "V",
  "IKHCC 건축 BOQ 수량·숨김 설계단가 결합",
  "보이는 단가열은 모두 공란이지만 품목코드로 숨김 시트의 캐시 설계단가를 결합했습니다. Q열 합계는 수식이며 계약가가 아닙니다.",
);
const itemHeaders = [
  "시설",
  "공종키",
  "공종명",
  "품목",
  "규격",
  "단위",
  "수량",
  "품목코드",
  "단가출처",
  "재료단가 USD",
  "노무단가 USD",
  "경비단가 USD",
  "합계단가 USD",
  "재료금액 USD",
  "노무금액 USD",
  "경비금액 USD",
  "합계금액 USD",
  "복원상태",
  "원본행",
  "원본파일",
  "집계키",
  "복원플래그",
];
items.getRange("A4:V4").values = [itemHeaders];
styleHeader(items.getRange("A4:V4"));
const itemStart = 5;
const itemLast = itemStart + boqItems.length - 1;
const itemValues = boqItems.map((row) => [
  row.facility_ko,
  null,
  row.section_name,
  row.description,
  row.specification,
  row.unit,
  row.quantity,
  row.item_code,
  row.rate_source_type,
  row.recovered_material_rate_usd,
  row.recovered_labor_rate_usd,
  row.recovered_expense_rate_usd,
  null,
  null,
  null,
  null,
  null,
  null,
  row.source_row,
  row.source_file,
  null,
  null,
]);
items.getRange(`A${itemStart}:V${itemLast}`).values = itemValues;
items.getRange(`B${itemStart}:B${itemLast}`).formulas = boqItems.map((row) => [
  `="C-${row.section_code}"`,
]);
for (const [column, formula] of Object.entries({
  M: `=SUM(J${itemStart}:L${itemStart})`,
  N: `=G${itemStart}*J${itemStart}`,
  O: `=G${itemStart}*K${itemStart}`,
  P: `=G${itemStart}*L${itemStart}`,
  Q: `=SUM(N${itemStart}:P${itemStart})`,
  R: `=IF(M${itemStart}>0,"복원","미복원")`,
  U: `=A${itemStart}&"|"&B${itemStart}`,
  V: `=IF(M${itemStart}>0,1,0)`,
})) {
  items.getRange(`${column}${itemStart}`).formulas = [[formula]];
  items.getRange(`${column}${itemStart}:${column}${itemLast}`).fillDown();
}
styleBody(items.getRange(`A${itemStart}:V${itemLast}`), { wrap: false, size: 8 });
items.getRange(`C${itemStart}:E${itemLast}`).format.wrapText = true;
items.getRange(`H${itemStart}:H${itemLast}`).format.wrapText = true;
items.getRange(`A${itemStart}:V${itemLast}`).format.rowHeight = 28;
items.getRange(`G${itemStart}:G${itemLast}`).format.numberFormat = "#,##0.000";
items.getRange(`B${itemStart}:B${itemLast}`).format.numberFormat = "@";
items.getRange(`J${itemStart}:Q${itemLast}`).format.numberFormat = '"$"#,##0.00';
items.getRange(`S${itemStart}:S${itemLast}`).format.numberFormat = "0";
items.getRange(`R${itemStart}:R${itemLast}`).conditionalFormats.add(
  "containsText",
  { text: "복원", format: { fill: COLORS.paleGreen, font: { color: COLORS.green } } },
);
items.tables.add(`A4:V${itemLast}`, true, "IKHCCBOQItems");
items.freezePanes.freezeRows(4);
items.freezePanes.freezeColumns(3);
setWidths(items, {
  A: 11, B: 10, C: 25, D: 34, E: 28, F: 8, G: 11, H: 31, I: 12,
  J: 13, K: 13, L: 13, M: 13, N: 15, O: 15, P: 15, Q: 16, R: 10,
  S: 9, T: 48, U: 18, V: 10,
}, itemLast);

// 숨김 단가 라이브러리
setTitle(
  rates,
  "Q",
  "IKHCC 숨김 설계단가 라이브러리",
  "숨김 시트 ‘일위대가목록’ 298행과 ‘단가대비표’ 346행을 복원했습니다. I열은 F:H의 수식 합계입니다.",
);
const rateHeaders = [
  "단가유형",
  "품목코드",
  "품명",
  "규격",
  "단위",
  "재료비 USD",
  "노무비 USD",
  "경비 USD",
  "합계 USD",
  "가격후보",
  "가격면·쪽",
  "비고",
  "숨김시트",
  "원본행",
  "원본파일",
  "SHA-256",
  "원본 합계수식",
];
rates.getRange("A4:Q4").values = [rateHeaders];
styleHeader(rates.getRange("A4:Q4"), COLORS.teal);
const rateStart = 5;
const rateLast = rateStart + rateLibrary.length - 1;
rates.getRange(`A${rateStart}:Q${rateLast}`).values = rateLibrary.map((row) => [
  row.rate_type,
  row.item_code,
  row.description,
  row.specification,
  row.unit,
  row.material_rate_usd,
  row.labor_rate_usd,
  row.expense_rate_usd,
  null,
  row.source_price_candidates,
  row.source_pages,
  row.source_note,
  row.source_sheet,
  row.source_row,
  row.source_file,
  row.source_sha256,
  literalFormula(row.total_formula),
]);
rates.getRange(`I${rateStart}`).formulas = [[`=SUM(F${rateStart}:H${rateStart})`]];
rates.getRange(`I${rateStart}:I${rateLast}`).fillDown();
styleBody(rates.getRange(`A${rateStart}:Q${rateLast}`), { size: 8 });
rates.getRange(`C${rateStart}:D${rateLast}`).format.wrapText = true;
rates.getRange(`F${rateStart}:I${rateLast}`).format.numberFormat = '"$"#,##0.00';
rates.getRange(`N${rateStart}:N${rateLast}`).format.numberFormat = "0";
rates.tables.add(`A4:Q${rateLast}`, true, "IKHCCRateLibrary");
rates.freezePanes.freezeRows(4);
rates.freezePanes.freezeColumns(2);
setWidths(rates, {
  A: 13, B: 25, C: 38, D: 30, E: 9, F: 13, G: 13, H: 13, I: 13,
  J: 26, K: 15, L: 20, M: 14, N: 9, O: 48, P: 24, Q: 20,
}, rateLast);

// 시설·공종 요약
setTitle(
  sections,
  "J",
  "시설·공종별 복원 설계견적",
  "모든 금액은 BOQ 수량·단가 시트에서 시설·공종키별로 SUMIF 집계됩니다.",
);
sections.getRange("A4:J4").values = [[
  "시설", "공종키", "공종명", "항목수", "복원수", "재료비 USD",
  "노무비 USD", "경비 USD", "합계 USD", "구성비",
]];
styleHeader(sections.getRange("A4:J4"));
const sectionStart = 5;
const sectionLast = sectionStart + sectionRows.length - 1;
sections.getRange(`A${sectionStart}:J${sectionLast}`).values = sectionRows.map((row) => [
  row.facility_ko,
  null,
  row.section_name,
  null,
  null,
  null,
  null,
  null,
  null,
  null,
]);
sections.getRange(`B${sectionStart}:B${sectionLast}`).formulas = sectionRows.map((row) => [
  `="C-${row.section_code}"`,
]);
for (const [column, formula] of Object.entries({
  D: `=COUNTIF('BOQ 수량·단가'!$U$${itemStart}:$U$${itemLast},A${sectionStart}&"|"&B${sectionStart})`,
  E: `=SUMIF('BOQ 수량·단가'!$U$${itemStart}:$U$${itemLast},A${sectionStart}&"|"&B${sectionStart},'BOQ 수량·단가'!$V$${itemStart}:$V$${itemLast})`,
  F: `=SUMIF('BOQ 수량·단가'!$U$${itemStart}:$U$${itemLast},A${sectionStart}&"|"&B${sectionStart},'BOQ 수량·단가'!$N$${itemStart}:$N$${itemLast})`,
  G: `=SUMIF('BOQ 수량·단가'!$U$${itemStart}:$U$${itemLast},A${sectionStart}&"|"&B${sectionStart},'BOQ 수량·단가'!$O$${itemStart}:$O$${itemLast})`,
  H: `=SUMIF('BOQ 수량·단가'!$U$${itemStart}:$U$${itemLast},A${sectionStart}&"|"&B${sectionStart},'BOQ 수량·단가'!$P$${itemStart}:$P$${itemLast})`,
  I: `=SUM(F${sectionStart}:H${sectionStart})`,
  J: `=IFERROR(I${sectionStart}/SUM($I$${sectionStart}:$I$${sectionLast}),0)`,
})) {
  sections.getRange(`${column}${sectionStart}`).formulas = [[formula]];
  sections.getRange(`${column}${sectionStart}:${column}${sectionLast}`).fillDown();
}
styleBody(sections.getRange(`A${sectionStart}:J${sectionLast}`), { wrap: false });
sections.getRange(`C${sectionStart}:C${sectionLast}`).format.wrapText = true;
sections.getRange(`D${sectionStart}:E${sectionLast}`).format.numberFormat = "#,##0";
sections.getRange(`B${sectionStart}:B${sectionLast}`).format.numberFormat = "@";
sections.getRange(`F${sectionStart}:I${sectionLast}`).format.numberFormat = '"$"#,##0';
sections.getRange(`J${sectionStart}:J${sectionLast}`).format.numberFormat = "0.0%";
sections.tables.add(`A4:J${sectionLast}`, true, "IKHCCSectionSummary");
sections.freezePanes.freezeRows(4);
setWidths(sections, { A: 13, B: 11, C: 34, D: 10, E: 10, F: 15, G: 15, H: 15, I: 16, J: 11 }, sectionLast);

// 미래사업 적용
setTitle(
  application,
  "H",
  "KOICA 미래사업 적용 시뮬레이터",
  "노란 셀만 조정하십시오. 결과는 ‘건축 Bill No.01’ 범위의 예비 스크리닝이며 전체 공사비가 아닙니다.",
);
application.getRange("A4:D4").merge();
application.getRange("A4").values = [["기준 벤치마크"]];
styleSection(application.getRange("A4:D4"));
application.getRange("A5:D12").values = [
  ["기준 연면적", summary.gross_floor_area_m2, "㎡", "KOICA 연간발주계획"],
  ["복원 건축 Bill No.01", null, "USD", "561개 항목 수식 합계"],
  ["복원 건축비/㎡", null, "USD/㎡", "건축 Bill만 해당"],
  ["현지입찰 집행한도", summary.local_bid_ceiling_usd, "USD", "L2025-00085-1"],
  ["집행한도/㎡", null, "USD/㎡", "전체 입찰 범위 상한 지표"],
  ["건축 Bill/집행한도", null, "%", "범위 차이 포함"],
  ["계획 입찰한도", summary.planned_bid_ceiling_krw, "KRW", "KOICA 연간발주계획"],
  ["계획 한도/㎡", null, "KRW/㎡", "계획값·변경 가능"],
];
application.getRange("B6").formulas = [[`=SUM('BOQ 수량·단가'!$Q$${itemStart}:$Q$${itemLast})`]];
application.getRange("B7").formulas = [["=B6/B5"]];
application.getRange("B9").formulas = [["=B8/B5"]];
application.getRange("B10").formulas = [["=B6/B8"]];
application.getRange("B12").formulas = [["=B11/B5"]];
application.getRange("A14:D14").merge();
application.getRange("A14").values = [["미래사업 입력"]];
styleSection(application.getRange("A14:D14"), COLORS.amber);
application.getRange("A15:D19").values = [
  ["목표 연면적", 3000, "㎡", "사용자 입력"],
  ["규모 보정계수", 1, "배", "형태·규모 차이"],
  ["국가·입지 보정계수", 1, "배", "시장·물류·치안"],
  ["시점 보정계수", 1, "배", "물가·환율"],
  ["설계범위 보정계수", 1, "배", "사양·복잡도"],
];
application.getRange("B15:B19").format = {
  fill: COLORS.input,
  font: { bold: true, color: COLORS.navy },
  borders: { preset: "outside", style: "thin", color: COLORS.amber },
};
application.getRange("B15").dataValidation = {
  rule: { type: "decimal", operator: "greaterThan", formula1: 0 },
};
application.getRange("B16:B19").dataValidation = {
  rule: { type: "decimal", operator: "between", formula1: 0.1, formula2: 5 },
};
application.getRange("A21:D21").merge();
application.getRange("A21").values = [["산정 결과"]];
styleSection(application.getRange("A21:D21"), COLORS.green);
application.getRange("A22:D23").values = [
  ["보정 건축비/㎡", null, "USD/㎡", "기준×4개 보정계수"],
  ["미래사업 건축 Bill 예비액", null, "USD", "전체 공사비 아님"],
];
application.getRange("B22").formulas = [["=B7*B16*B17*B18*B19"]];
application.getRange("B23").formulas = [["=B15*B22"]];
application.getRange("A25:H27").merge();
application.getRange("A25").values = [[
  "주의: 토목·기계·전기·통신·소방·동원·사인, 세금·예비비·계약변경은 포함되지 않습니다. 실제 사업에서는 현지 견적과 최신 BOQ로 재산정해야 합니다.",
]];
application.getRange("A25:H27").format = {
  fill: COLORS.paleRed,
  font: { bold: true, color: COLORS.red, size: 10 },
  wrapText: true,
  verticalAlignment: "center",
  borders: { preset: "outside", style: "thin", color: COLORS.red },
};
styleBody(application.getRange("A5:D12"), { wrap: true });
styleBody(application.getRange("A15:D19"), { wrap: true });
styleBody(application.getRange("A22:D23"), { wrap: true });
application.getRange("B5:B9").format.numberFormat = '"$"#,##0.00';
application.getRange("B5").format.numberFormat = "#,##0";
application.getRange("B10").format.numberFormat = "0.0%";
application.getRange("B11:B12").format.numberFormat = '"₩"#,##0';
application.getRange("B15").format.numberFormat = "#,##0";
application.getRange("B16:B19").format.numberFormat = "0.00";
application.getRange("B22:B23").format.numberFormat = '"$"#,##0.00';
application.freezePanes.freezeRows(2);
setWidths(application, { A: 28, B: 18, C: 13, D: 34, E: 3, F: 12, G: 12, H: 12 }, 27);
workbook.comments.addThread(
  { cell: application.getRange("B5") },
  `Source: ${summary.official_plan_source_url} — KOICA 연간발주계획의 5,486㎡ 계획값`,
);
workbook.comments.addThread(
  { cell: application.getRange("B8") },
  `Source: ${summary.detail_url} — 현지입찰 집행한도 USD 13,292,831`,
);
workbook.comments.addThread(
  { cell: application.getRange("B6") },
  "Source: KOICA 공개 입찰첨부 숨김 캐시 설계단가 × 보이는 BOQ 수량. 계약가가 아님.",
);

// 판정
setTitle(
  verdict,
  "L",
  "KOICA-only 건축비 데이터 복원 판정",
  "결론: KOICA 공개자료만으로도 수량×설계견적 단가 수준의 벤치마크를 만들 수 있습니다. 실제 계약·준공단가는 아직 별도 확보가 필요합니다.",
);
kpiCard(
  verdict,
  "A4:C4",
  "A5:C7",
  "숨김 단가",
  COLORS.teal,
  `=COUNTA('숨김 단가 라이브러리'!$B$${rateStart}:$B$${rateLast})`,
  "#,##0",
);
kpiCard(
  verdict,
  "D4:F4",
  "D5:F7",
  "BOQ 결합 항목",
  COLORS.blue,
  `=COUNTA('BOQ 수량·단가'!$H$${itemStart}:$H$${itemLast})`,
  "#,##0",
);
kpiCard(
  verdict,
  "G4:I4",
  "G5:I7",
  "항목 복원률",
  COLORS.green,
  `=SUM('BOQ 수량·단가'!$V$${itemStart}:$V$${itemLast})/COUNTA('BOQ 수량·단가'!$H$${itemStart}:$H$${itemLast})`,
  "0.0%",
);
kpiCard(
  verdict,
  "J4:L4",
  "J5:L7",
  "복원 건축 Bill",
  COLORS.amber,
  `=SUM('BOQ 수량·단가'!$Q$${itemStart}:$Q$${itemLast})`,
  '"$"#,##0',
);
verdict.getRange("A9:L11").merge();
verdict.getRange("A9").values = [[
  "핵심 개선: 기존 ‘입찰한도÷연면적’ 수준에서, 355개 고유 품목코드의 재료·노무·경비 단가와 561개 설계수량을 직접 결합하는 단계로 올라갔습니다.",
]];
verdict.getRange("A9:L11").format = {
  fill: COLORS.paleGreen,
  font: { bold: true, color: COLORS.green, size: 11 },
  wrapText: true,
  verticalAlignment: "center",
  borders: { preset: "outside", style: "thin", color: COLORS.green },
};
verdict.getRange("A13:C13").values = [["시설", "항목수", "복원액 USD"]];
styleHeader(verdict.getRange("A13:C13"), COLORS.teal);
const facilityNames = ["병원", "기계·전기동", "연결교량"];
verdict.getRange("A14:C16").values = facilityNames.map((name) => [name, null, null]);
for (let row = 14; row <= 16; row += 1) {
  verdict.getRange(`B${row}`).formulas = [[
    `=COUNTIF('BOQ 수량·단가'!$A$${itemStart}:$A$${itemLast},A${row})`,
  ]];
  verdict.getRange(`C${row}`).formulas = [[
    `=SUMIF('BOQ 수량·단가'!$A$${itemStart}:$A$${itemLast},A${row},'BOQ 수량·단가'!$Q$${itemStart}:$Q$${itemLast})`,
  ]];
}
styleBody(verdict.getRange("A14:C16"));
verdict.getRange("B14:B16").format.numberFormat = "#,##0";
verdict.getRange("C14:C16").format.numberFormat = '"$"#,##0';
const facilityChart = verdict.charts.add("bar", verdict.getRange("A13:C16"));
facilityChart.title = "시설별 건축 Bill No.01 복원액 (USD)";
facilityChart.hasLegend = false;
facilityChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
facilityChart.yAxis = { numberFormatCode: '"$"0.0,,"M"' };
facilityChart.setPosition("E13", "L26");
verdict.getRange("A19:C19").values = [["비교지표", "값", "해석"]];
styleHeader(verdict.getRange("A19:C19"), COLORS.blue);
verdict.getRange("A20:C23").values = [
  ["복원 건축비/㎡", null, "Bill No.01만 포함"],
  ["현지입찰 한도/㎡", null, "전체 입찰 범위 상한"],
  ["건축 Bill/한도", null, "63%는 범위차 포함"],
  ["중첩자료 색인", audit.nested_files_indexed, "중첩 위치 파일 확인·색인"],
];
verdict.getRange("B20").formulas = [["='미래사업 적용'!B7"]];
verdict.getRange("B21").formulas = [["='미래사업 적용'!B9"]];
verdict.getRange("B22").formulas = [["='미래사업 적용'!B10"]];
styleBody(verdict.getRange("A20:C23"), { wrap: true });
verdict.getRange("B20:B21").format.numberFormat = '"$"#,##0.00';
verdict.getRange("B22").format.numberFormat = "0.0%";
verdict.getRange("B23").format.numberFormat = "#,##0";
verdict.freezePanes.freezeRows(2);
setWidths(verdict, { A: 20, B: 16, C: 25, D: 4, E: 13, F: 13, G: 13, H: 13, I: 13, J: 13, K: 13, L: 13 }, 26);

// 회수감사·한계
setTitle(
  auditSheet,
  "H",
  "KOICA 자료 회수감사·해석 경계",
  "‘파일 색인 완료’와 ‘건축비 산정에 의미 있게 활용’을 구분합니다. 오류 0건이어도 스캔·DWG·미가격·계약실적 부재는 남습니다.",
);
auditSheet.getRange("A4:D4").values = [["감사항목", "이전", "현재", "판정"]];
styleHeader(auditSheet.getRange("A4:D4"));
auditSheet.getRange("A5:D10").values = [
  ["색인 파일", audit.pre_recursive_snapshot.indexed_files, audit.current_extraction_summary.indexed_files, "증가"],
  ["중첩 ZIP", 0, audit.nested_archive_targets, "80개 전부 회수"],
  ["중첩 파일", 0, audit.nested_files_indexed, "1,005개 전부 색인"],
  ["추출 오류", audit.pre_recursive_snapshot.errors, audit.current_extraction_summary.errors, "0건"],
  ["중첩 증거", 0, audit.nested_evidence_records, "오탐 제거 후"],
  ["IKHCC 단가 결합", 0, summary.recovered_item_rows, "561/561"],
];
styleBody(auditSheet.getRange("A5:D10"));
auditSheet.getRange("B5:C10").format.numberFormat = "#,##0";
auditSheet.getRange("A12:H12").merge();
auditSheet.getRange("A12").values = [["이번에 실제로 해결한 누락"]];
styleSection(auditSheet.getRange("A12:H12"));
auditSheet.getRange("A13:H17").merge(true);
auditSheet.getRange("A13:A17").values = [
  ["• 최상위 압축 안의 중첩 ZIP 80개를 재귀 해제하고 중첩 위치 파일 1,005개를 확인·색인"],
  ["• 점(.)으로 시작하는 실제 CM 검토폴더를 메타데이터로 오인하던 제외 규칙 수정"],
  ["• 엑셀 절대참조 $F$30을 USD 30으로 읽던 통화 오탐 제거"],
  ["• IKHCC ‘빈 BOQ’의 숨김 캐시단가 644개를 발견·구조화"],
  ["• 최신·재공고 3건의 동일 SHA-256을 확인해 중복 표본화 방지"],
];
styleBody(auditSheet.getRange("A13:H17"), { wrap: true, size: 9 });
auditSheet.getRange("A19:H19").merge();
auditSheet.getRange("A19").values = [["해석 한계"]];
styleSection(auditSheet.getRange("A19:H19"), COLORS.red);
const limits = [
  ...summary.interpretation_limits,
  audit.claim_boundary,
];
const limitStart = 20;
const limitLast = limitStart + limits.length - 1;
auditSheet.getRange(`A${limitStart}:H${limitLast}`).merge(true);
auditSheet.getRange(`A${limitStart}:A${limitLast}`).values = limits.map((text) => [`• ${text}`]);
styleBody(auditSheet.getRange(`A${limitStart}:H${limitLast}`), { wrap: true, size: 9 });
auditSheet.getRange(`A${limitStart}:H${limitLast}`).format.rowHeight = 30;
const sourceStart = limitLast + 2;
auditSheet.getRange(`A${sourceStart}:H${sourceStart}`).merge();
auditSheet.getRange(`A${sourceStart}`).values = [["근거·계보"]];
styleSection(auditSheet.getRange(`A${sourceStart}:H${sourceStart}`), COLORS.blue);
auditSheet.getRange(`A${sourceStart + 1}:B${sourceStart + 5}`).values = [
  ["KOICA 현지입찰", summary.detail_url],
  ["KOICA 연간발주계획", summary.official_plan_source_url],
  ["대표 공고", `${summary.representative_bid_no} / ${summary.notice_date}`],
  ["통화 근거", `${summary.currency_evidence.source_file} / AMOUNT (USD)`],
  ["환율 충돌", `${summary.rate_metadata.comparison_exchange_rate_krw_per_usd} vs ${summary.rate_metadata.settings_exchange_rate_krw_per_usd}`],
];
styleBody(auditSheet.getRange(`A${sourceStart + 1}:B${sourceStart + 5}`), { wrap: true, size: 9 });
auditSheet.getRange(`B${sourceStart + 1}:B${sourceStart + 5}`).format.font = { color: COLORS.blue, size: 9 };
auditSheet.freezePanes.freezeRows(2);
setWidths(auditSheet, { A: 24, B: 42, C: 14, D: 22, E: 14, F: 14, G: 14, H: 14 }, sourceStart + 5);

// Compact verification and visual pass for every sheet.
const keyInspection = await workbook.inspect({
  kind: "table",
  range: "판정!A1:L23",
  include: "values,formulas",
  tableMaxRows: 25,
  tableMaxCols: 12,
  maxChars: 12000,
});
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
const previewSpecs = [
  ["판정", "A1:L26"],
  ["미래사업 적용", "A1:H27"],
  ["시설·공종 요약", `A1:J${Math.min(sectionLast, 45)}`],
  ["BOQ 수량·단가", "A1:V25"],
  ["숨김 단가 라이브러리", "A1:Q25"],
  ["회수감사·한계", `A1:H${sourceStart + 5}`],
];
const previews = [];
for (const [sheetName, range] of previewSpecs) {
  const blob = await workbook.render({ sheetName, range, scale: 1.1, format: "png" });
  const previewPath = path.join(previewDir, `${sheetName}.png`);
  await fs.writeFile(previewPath, new Uint8Array(await blob.arrayBuffer()));
  previews.push({ sheetName, range, previewPath });
}

await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
await fs.writeFile(
  path.join(outputDir, "ikhcc_workbook_verification.json"),
  `${JSON.stringify({
    keyInspection: keyInspection.ndjson,
    formulaErrors: formulaErrors.ndjson,
    previews,
    outputPath,
  }, null, 2)}\n`,
  "utf8",
);

console.log(JSON.stringify({
  outputPath,
  sheets: workbook.worksheets.items.map((sheet) => sheet.name),
  boqItemRows: boqItems.length,
  rateRows: rateLibrary.length,
  sectionRows: sectionRows.length,
  formulaErrors: formulaErrors.ndjson,
  previews,
}, null, 2));
