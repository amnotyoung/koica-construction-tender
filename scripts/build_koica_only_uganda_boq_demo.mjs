import fs from "node:fs/promises";
import path from "node:path";
import {
  FileBlob,
  SpreadsheetFile,
  Workbook,
} from "@oai/artifact-tool";

const root = process.cwd();
const outputDir = path.join(root, "outputs", "koica-only-pilot");
const previewDir = path.join(outputDir, "previews");
const sourcePreviewDir = path.join(outputDir, "source-previews");
const extractionPath = path.join(outputDir, "KOICA_우간다_BOQ_구조화.json");
const officialCandidatesPath = path.join(
  root,
  "outputs",
  "koica-official-open-data",
  "KOICA_공식데이터_건축관련후보.csv",
);
const officialManifestPath = path.join(
  root,
  "data",
  "manifests",
  "koica_official_open_data.json",
);
const outputPath = path.join(
  outputDir,
  "KOICA_only_우간다_BOQ_건축조사_시연.xlsx",
);

await fs.mkdir(previewDir, { recursive: true });
await fs.mkdir(sourcePreviewDir, { recursive: true });

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field.length || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  const [headers, ...body] = rows.filter(
    (values) => values.some((value) => value !== ""),
  );
  return body.map((values) =>
    Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])),
  );
}

function numberOrBlank(value) {
  if (value === "" || value === null || value === undefined) return "";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : "";
}

function safeFileName(value) {
  return value.replaceAll(/[^\p{L}\p{N}._-]+/gu, "_");
}

const extraction = JSON.parse(await fs.readFile(extractionPath, "utf8"));
const officialCandidates = parseCsv(
  await fs.readFile(officialCandidatesPath, "utf8"),
);
const officialManifest = JSON.parse(
  await fs.readFile(officialManifestPath, "utf8"),
);
const itemRecords = extraction.records.filter((row) =>
  ["item", "item_unquantified"].includes(row.row_type),
);
const strictCostCandidates = officialCandidates.filter(
  (row) => row.unit_cost_potential === "1",
);
const ugandaCandidates = officialCandidates.filter((row) => row.is_uganda === "1");
const notInReviewedCases = new Set([
  "2021-00156",
  "2021-00009",
  "2023-00030",
]);

// Render every source BOQ sheet once before building the derived workbook.
const sourcePath = path.resolve(root, extraction.summary.source_file);
const sourceProbePath = path.join(outputDir, "source_probe.json");
let sourceSheets = [];
try {
  const existingProbe = JSON.parse(await fs.readFile(sourceProbePath, "utf8"));
  const previewsExist = await Promise.all(
    existingProbe.sheets.map(async (sheet) => {
      try {
        await fs.access(sheet.previewPath);
        return true;
      } catch {
        return false;
      }
    }),
  );
  if (
    existingProbe.sourcePath === sourcePath &&
    previewsExist.every(Boolean)
  ) {
    sourceSheets = existingProbe.sheets;
  }
} catch {
  sourceSheets = [];
}
if (!sourceSheets.length) {
  const sourceWorkbook = await SpreadsheetFile.importXlsx(
    await FileBlob.load(sourcePath),
  );
  for (let index = 0; index < sourceWorkbook.worksheets.items.length; index += 1) {
    const sheet = sourceWorkbook.worksheets.getItemAt(index);
    const preview = await sourceWorkbook.render({
      sheetName: sheet.name,
      autoCrop: "all",
      scale: 0.7,
      format: "png",
    });
    const previewPath = path.join(
      sourcePreviewDir,
      `${String(index + 1).padStart(2, "0")}_${safeFileName(sheet.name)}.png`,
    );
    await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
    sourceSheets.push({
      index,
      name: sheet.name,
      usedAddress: sheet.getUsedRange(true)?.address ?? null,
      previewPath,
    });
  }
  await fs.writeFile(
    sourceProbePath,
    `${JSON.stringify({ sourcePath, sheets: sourceSheets }, null, 2)}\n`,
    "utf8",
  );
}

const COLORS = {
  navy: "#16324F",
  blue: "#24557A",
  teal: "#0F6B78",
  green: "#3E7C59",
  amber: "#B7791F",
  red: "#B42318",
  purple: "#6B5B95",
  paleBlue: "#E8F1F8",
  paleTeal: "#E5F3F4",
  paleGreen: "#EAF4EC",
  paleYellow: "#FFF4D6",
  paleRed: "#FDECEB",
  palePurple: "#F0ECF7",
  paleGray: "#F4F6F8",
  white: "#FFFFFF",
  text: "#24313D",
  muted: "#627282",
  line: "#D6DEE5",
  input: "#FFF2CC",
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
  sheet.getRange("A2").format.rowHeight = 36;
}

function styleHeader(range, fill = COLORS.blue) {
  range.format = {
    fill,
    font: { bold: true, color: COLORS.white, size: 9 },
    wrapText: true,
    verticalAlignment: "center",
    horizontalAlignment: "center",
    borders: {
      bottom: { style: "medium", color: fill },
    },
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

function setColumnWidths(sheet, widths, lastRow) {
  for (const [column, width] of Object.entries(widths)) {
    sheet.getRange(`${column}1:${column}${lastRow}`).format.columnWidth = width;
  }
}

function kpiCard(sheet, labelRange, valueRange, label, fill, formulaOrValue) {
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
  if (typeof formulaOrValue === "string" && formulaOrValue.startsWith("=")) {
    sheet.getRange(anchor).formulas = [[formulaOrValue]];
  } else {
    sheet.getRange(anchor).values = [[formulaOrValue]];
  }
  sheet.getRange(valueRange).format = {
    fill: COLORS.white,
    font: { bold: true, color: COLORS.navy, size: 17 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    borders: {
      top: { style: "thin", color: COLORS.line },
      bottom: { style: "thin", color: COLORS.line },
      left: { style: "thin", color: COLORS.line },
      right: { style: "thin", color: COLORS.line },
    },
  };
}

// Create every sheet before cross-sheet formulas.
const verdict = workbook.worksheets.add("판정");
const inputs = workbook.worksheets.add("입력·근거");
const scope = workbook.worksheets.add("시설·공종 요약");
const quantities = workbook.worksheets.add("수량 벤치마크");
const items = workbook.worksheets.add("BOQ 항목");
const official = workbook.worksheets.add("공식 KOICA 후보");
const checklist = workbook.worksheets.add("조사 체크리스트");

// 입력·근거
setTitle(
  inputs,
  "H",
  "KOICA 우간다 건축조사 입력·근거",
  "노란 셀은 사용자가 선택·입력할 수 있는 가정이며, 파생값은 수식으로 계산합니다. 모든 금액 단계는 입찰 집행한도 또는 발주계획 한도입니다.",
);
inputs.getRange("A4:E4").values = [[
  "항목",
  "값",
  "단위",
  "금액·근거 단계",
  "주의사항",
]];
styleHeader(inputs.getRange("A4:E4"));
inputs.getRange("A5:E18").values = [
  ["연면적 - 영문 BDS", 827.4, "㎡", "입찰서류", "현재 사례DB 분모"],
  ["연면적 - 국문 입찰계획", 835.67, "㎡", "입찰계획", "영문값과 불일치"],
  ["연면적 차이율", null, "%", "파생", "두 문서 간 약 1% 차이"],
  ["대지면적", 6070.35, "㎡", "입찰계획", "연면적으로 사용 금지"],
  ["공사 입찰 집행한도", 272603, "USD", "입찰한도", "계약가·준공가 아님"],
  ["공사 입찰 집행한도", 354383562, "KRW", "입찰한도", "계약가·준공가 아님"],
  ["공고 명시 환율", 1299.1, "KRW/USD", "공고환율", "재공고 기준"],
  ["수량 배수 시나리오", "LOW", "LOW/HIGH", "사용자 선택", "시장쉼터 5동/6동 충돌"],
  ["연면적 선택", "EN_BDS", "EN_BDS/KO_PLAN", "사용자 선택", "분모 민감도 확인"],
  ["선택 연면적", null, "㎡", "파생", "선택값에 따라 변경"],
  ["집행한도 원단가", null, "USD/㎡", "파생", "범위·물가 미보정"],
  ["집행한도 원단가", null, "KRW/㎡", "파생", "범위·물가 미보정"],
  ["환율 재계산 금액", null, "KRW", "파생", "USD×공고환율"],
  ["KRW 차이", null, "KRW", "파생", "공고 반올림 검산"],
];
inputs.getRange("B7").formulas = [["=(B6-B5)/B5"]];
inputs.getRange("B14").formulas = [["=IF(B13=\"KO_PLAN\",B6,B5)"]];
inputs.getRange("B15").formulas = [["=B9/B14"]];
inputs.getRange("B16").formulas = [["=B10/B14"]];
inputs.getRange("B17").formulas = [["=B9*B11"]];
inputs.getRange("B18").formulas = [["=B10-B17"]];
styleBody(inputs.getRange("A5:E18"), { wrap: true, size: 9 });
inputs.getRange("B5:B6").format.numberFormat = "#,##0.00";
inputs.getRange("B7").format.numberFormat = "0.00%";
inputs.getRange("B8").format.numberFormat = "#,##0.00";
inputs.getRange("B9").format.numberFormat = '"$"#,##0';
inputs.getRange("B10:B11").format.numberFormat = "#,##0.0";
inputs.getRange("B12:B13").format = {
  fill: COLORS.input,
  font: { bold: true, color: COLORS.navy },
  horizontalAlignment: "center",
};
inputs.getRange("B12").dataValidation = {
  rule: { type: "list", values: ["LOW", "HIGH"] },
};
inputs.getRange("B13").dataValidation = {
  rule: { type: "list", values: ["EN_BDS", "KO_PLAN"] },
};
inputs.getRange("B14").format.numberFormat = "#,##0.00";
inputs.getRange("B15").format.numberFormat = '"$"#,##0.00';
inputs.getRange("B16:B18").format.numberFormat = "#,##0";
inputs.getRange("G4:H4").values = [["원자료", "경로·URL"]];
styleHeader(inputs.getRange("G4:H4"), COLORS.green);
inputs.getRange("G5:H12").values = [
  ["최신 재공고 BOQ", extraction.summary.source_file],
  [
    "초기공고 BOQ",
    extraction.summary.version_comparison?.comparison_source ?? "",
  ],
  [
    "도면 PDF (42쪽)",
    extraction.summary.source_file.replace(
      "Section 4. Bill of Quantities_unpriced.xlsx",
      "Section 5. Drawings.pdf",
    ),
  ],
  [
    "시방서",
    extraction.summary.source_file.replace(
      "Section 4. Bill of Quantities_unpriced.xlsx",
      "Section 6. Specification.pdf",
    ),
  ],
  [
    "KOICA 재공고",
    "https://nebid.koica.go.kr/oep/lobi/localBidManageDetail.do?P_LOAZ_BID_PBLANC_NO=L2023-00009&P_PBLANC_ODR=1",
  ],
  [
    "KOICA 연간발주계획",
    "https://www.data.go.kr/data/15085055/fileData.do",
  ],
  [
    "KOICA 원조조달계약",
    "https://www.data.go.kr/data/15073135/fileData.do",
  ],
  [
    "KOICA 국별사업보고서",
    "https://www.data.go.kr/data/15052832/fileData.do",
  ],
];
styleBody(inputs.getRange("G5:H12"), { wrap: true, size: 8 });
inputs.getRange("H9:H12").format = {
  font: { color: "#0563C1", underline: true, size: 8 },
  wrapText: true,
};
inputs.getRange("G14:H14").merge();
inputs.getRange("G14").values = [["증거 경계"]];
styleSection(inputs.getRange("G14:H14"), COLORS.amber);
inputs.getRange("G15:H18").merge();
inputs.getRange("G15").values = [[
  "BOQ는 공종·단위·수량을 제공하지만 단가와 금액은 비어 있습니다. 따라서 이 파일의 ㎡당 값은 BOQ 합계가 아니라 공고 집행한도를 연면적으로 나눈 원시 지표입니다. 실제 건축비로 쓰려면 현지 단가, 세금, 외부공사 범위, 계약변경과 준공정산을 추가해야 합니다.",
]];
inputs.getRange("G15:H18").format = {
  fill: COLORS.paleYellow,
  font: { color: COLORS.text, size: 9 },
  wrapText: true,
  verticalAlignment: "top",
};
workbook.comments.addThread(
  { cell: inputs.getRange("B5") },
  "Source: L2023-00009-1 Section 2 - Bid Data Sheet, table 5 row 8.",
);
workbook.comments.addThread(
  { cell: inputs.getRange("B6") },
  "Source: L2023-00009-1 국문 입찰계획안, 연면적 835.67㎡. 영문 BDS의 827.40㎡와 불일치.",
);
workbook.comments.addThread(
  { cell: inputs.getRange("B9") },
  "Source: KOICA 현지입찰 재공고 상세페이지. Cost stage is bid execution ceiling, not contract or final cost.",
);
setColumnWidths(
  inputs,
  { A: 25, B: 17, C: 15, D: 18, E: 31, G: 23, H: 62 },
  18,
);
inputs.freezePanes.freezeRows(4);

// 판정
setTitle(
  verdict,
  "H",
  "KOICA 데이터만으로 한 건축조사 시연",
  "우간다 KOICA 공고의 BOQ·도면·입찰한도와 KOICA 공식 공개데이터만 사용했습니다. 세계은행·타 공여기관 값은 포함하지 않았습니다.",
);
kpiCard(verdict, "A4:B4", "A5:B7", "BOQ 세부항목", COLORS.teal, itemRecords.length);
kpiCard(
  verdict,
  "C4:D4",
  "C5:D7",
  "수량 보유 항목",
  COLORS.green,
  extraction.summary.quantified_items,
);
kpiCard(verdict, "E4:F4", "E5:F7", "가격 보유 항목", COLORS.red, extraction.summary.priced_items);
kpiCard(verdict, "G4:H4", "G5:H7", "도면 페이지", COLORS.purple, 42);
verdict.getRange("A9:D9").values = [["질문", "판정", "근거", "미래사업 활용"]];
styleHeader(verdict.getRange("A9:D9"));
verdict.getRange("A10:D14").values = [
  [
    "KOICA만으로 공사범위를 구조화할 수 있나?",
    "YES",
    `${extraction.summary.facility_components}개 시설구성, ${itemRecords.length}개 BOQ 항목, 42쪽 도면`,
    "PoD·기획조사 단계의 누락 공종 점검",
  ],
  [
    "수량 벤치마크를 만들 수 있나?",
    "YES, 조건부",
    `${extraction.summary.quantified_items}개 수량, ${extraction.summary.formula_quantity_items}개 수식 수량`,
    "동일 시설·동일 단위끼리만 비교",
  ],
  [
    "현재 자료만으로 실제 공사비가 나오나?",
    "NO",
    "가격이 입력된 BOQ 항목 0개",
    "현지 단가 또는 낙찰·계약·준공금액 필요",
  ],
  [
    "㎡당 원시 지표는 가능한가?",
    "PARTIAL",
    "입찰 집행한도와 연면적이 있으나 GFA 827.40/835.67㎡ 불일치",
    "범위·세금·물가 미보정 스크리닝에만 사용",
  ],
  [
    "KOICA 공식자료로 표본을 더 찾을 수 있나?",
    "YES",
    `건축 문서추적 ${officialManifest.combined_construction_candidates.row_count}건, 엄격 비용 후보 ${strictCostCandidates.length}건`,
    "누락 BOQ·보고서·계약문서 우선순위화",
  ],
];
styleBody(verdict.getRange("A10:D14"), { wrap: true, size: 9 });
verdict.getRange("B10:B14").format.horizontalAlignment = "center";
verdict.getRange("B10").format = {
  fill: COLORS.paleGreen,
  font: { bold: true, color: COLORS.green },
  horizontalAlignment: "center",
};
verdict.getRange("B11:B12").format = {
  fill: COLORS.paleYellow,
  font: { bold: true, color: COLORS.amber },
  horizontalAlignment: "center",
};
verdict.getRange("B13:B14").format = {
  fill: COLORS.paleBlue,
  font: { bold: true, color: COLORS.blue },
  horizontalAlignment: "center",
};
verdict.getRange("F9:H9").merge();
verdict.getRange("F9").values = [["현재 계산 가능한 값"]];
styleSection(verdict.getRange("F9:H9"), COLORS.blue);
verdict.getRange("F10:G10").values = [["선택 연면적", "집행한도 USD/㎡"]];
styleHeader(verdict.getRange("F10:G10"), COLORS.teal);
verdict.getRange("F11").formulas = [["='입력·근거'!B14"]];
verdict.getRange("G11").formulas = [["='입력·근거'!B15"]];
verdict.getRange("F11").format.numberFormat = "#,##0.00";
verdict.getRange("G11").format.numberFormat = '"$"#,##0.00';
verdict.getRange("F13:H13").merge();
verdict.getRange("F13").values = [["BOQ 단가 입력 후 예상총액 (UGX)"]];
styleSection(verdict.getRange("F13:H13"), COLORS.amber);
verdict.getRange("F14:H15").merge();
verdict.getRange("F14").formulas = [[
  `=IF(SUM('BOQ 항목'!R5:R${itemRecords.length + 4})=0,"가격 입력 전",SUM('BOQ 항목'!R5:R${itemRecords.length + 4}))`,
]];
verdict.getRange("F14:H15").format = {
  fill: COLORS.paleYellow,
  font: { bold: true, color: COLORS.navy, size: 14 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
verdict.getRange("A17:H17").merge();
verdict.getRange("A17").values = [["핵심 발견"]];
styleSection(verdict.getRange("A17:H17"), COLORS.purple);
verdict.getRange("A18:H22").merge();
verdict.getRange("A18").values = [[
  `• KOICA 우간다 공고 하나에서 ${itemRecords.length}개 세부항목과 ${extraction.summary.quantified_items}개 수량을 복원했다.\n` +
    `• BOQ 두 버전은 ${extraction.summary.version_comparison.description_rows_changed}개 설명행이 바뀌었지만 항목 수량 변경은 ${extraction.summary.version_comparison.item_quantity_rows_changed}개다.\n` +
    "• 시장쉼터 수량은 General Summary 5동, 재공고 전기공종 제목 6동으로 충돌한다. 도면 배치도는 반복 모듈을 보여 주므로 계약 전 RFI가 필요한 설계범위 리스크다.\n" +
    "• KOICA 공식 데이터에서 기존 검토사례 밖의 면적+발주한도 후보 3개 사업도 추가 포착했다.\n" +
    "• 결론: KOICA만으로도 범위·수량·조사질문은 크게 개선되지만 실제 단가 확정에는 가격자료가 한 단계 더 필요하다.",
]];
verdict.getRange("A18:H22").format = {
  fill: COLORS.palePurple,
  font: { color: COLORS.text, size: 10 },
  wrapText: true,
  verticalAlignment: "top",
};
setColumnWidths(
  verdict,
  { A: 28, B: 16, C: 35, D: 31, E: 4, F: 21, G: 21, H: 21 },
  22,
);
verdict.freezePanes.freezeRows(2);

// 시설·공종 요약
setTitle(
  scope,
  "R",
  "시설·공종 범위 요약",
  "수량은 미가격 BOQ에서 추출했습니다. 시장쉼터는 5동/6동 충돌 때문에 저·고 배수를 모두 보존합니다.",
);
scope.getRange("A4:H4").values = [[
  "시설구성",
  "원본 시트",
  "저배수",
  "고배수",
  "항목",
  "수량 보유",
  "0 수량",
  "가격 보유",
]];
styleHeader(scope.getRange("A4:H4"));
const sheetStats = extraction.summary.sheet_stats;
scope.getRange(`A5:H${sheetStats.length + 4}`).values = sheetStats.map((row) => [
  row.facility,
  row.sheet,
  row.scope_multiplier_scenario_low,
  row.scope_multiplier_scenario_high,
  row.item_rows,
  row.quantified_items,
  row.zero_quantity_items,
  row.priced_items,
]);
styleBody(scope.getRange(`A5:H${sheetStats.length + 4}`), {
  wrap: true,
  size: 9,
});
scope.getRange(`C5:H${sheetStats.length + 4}`).format.numberFormat = "#,##0";
scope.getRange("J4:K4").values = [["자동 공종분류", "항목 수"]];
styleHeader(scope.getRange("J4:K4"), COLORS.green);
const tradeCounts = extraction.summary.trade_item_counts;
scope.getRange(`J5:K${tradeCounts.length + 4}`).values = tradeCounts.map((row) => [
  row.trade_group,
  row.item_rows,
]);
styleBody(scope.getRange(`J5:K${tradeCounts.length + 4}`), {
  wrap: true,
  size: 9,
});
scope.getRange(`K5:K${tradeCounts.length + 4}`).format.numberFormat = "#,##0";
const tradeChart = scope.charts.add(
  "bar",
  scope.getRange(`J4:K${tradeCounts.length + 4}`),
);
tradeChart.title = "BOQ 항목 수 기준 주요 공종";
tradeChart.titleTextStyle.fontSize = 12;
tradeChart.hasLegend = false;
tradeChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 8 } };
tradeChart.yAxis = { numberFormatCode: "0" };
tradeChart.setPosition("M4", "R22");
scope.getRange(`G5:G${sheetStats.length + 4}`).conditionalFormats.add(
  "cellIs",
  {
    operator: "greaterThan",
    formula: 0,
    format: { fill: COLORS.paleRed, font: { color: COLORS.red, bold: true } },
  },
);
scope.tables.add(
  `A4:H${sheetStats.length + 4}`,
  true,
  "FacilityScopeSummary",
);
setColumnWidths(
  scope,
  { A: 25, B: 31, C: 10, D: 10, E: 11, F: 12, G: 11, H: 11, J: 24, K: 11 },
  22,
);
scope.freezePanes.freezeRows(4);

// 수량 벤치마크
setTitle(
  quantities,
  "H",
  "공종·단위별 수량 벤치마크",
  "서로 다른 단위는 합치지 않습니다. 저·고 수량은 시장쉼터 5동/6동 및 빗물저장시설 2기를 반영한 조사 시나리오입니다.",
);
quantities.getRange("A4:H4").values = [[
  "공종",
  "단위",
  "항목 수",
  "기본 수량",
  "저시나리오",
  "고시나리오",
  "저수량/선택㎡",
  "고수량/선택㎡",
]];
styleHeader(quantities.getRange("A4:H4"));
const unitTotals = extraction.summary.unit_totals;
quantities.getRange(`A5:F${unitTotals.length + 4}`).values = unitTotals.map((row) => [
  row.trade_group,
  row.unit,
  row.item_rows,
  row.base_quantity,
  row.scaled_low_quantity,
  row.scaled_high_quantity,
]);
quantities.getRange("G5").formulas = [["=IFERROR(E5/'입력·근거'!$B$14,\"\")"]];
quantities.getRange(`G5:G${unitTotals.length + 4}`).fillDown();
quantities.getRange("H5").formulas = [["=IFERROR(F5/'입력·근거'!$B$14,\"\")"]];
quantities.getRange(`H5:H${unitTotals.length + 4}`).fillDown();
styleBody(quantities.getRange(`A5:H${unitTotals.length + 4}`), {
  wrap: false,
  size: 9,
});
quantities.getRange(`C5:C${unitTotals.length + 4}`).format.numberFormat = "#,##0";
quantities.getRange(`D5:F${unitTotals.length + 4}`).format.numberFormat = "#,##0.000";
quantities.getRange(`G5:H${unitTotals.length + 4}`).format.numberFormat = "0.000";
quantities.tables.add(
  `A4:H${unitTotals.length + 4}`,
  true,
  "QuantityBenchmark",
);
setColumnWidths(
  quantities,
  { A: 28, B: 12, C: 11, D: 15, E: 15, F: 15, G: 17, H: 17 },
  unitTotals.length + 4,
);
quantities.freezePanes.freezeRows(4);

// BOQ 항목 + editable price inputs
setTitle(
  items,
  "S",
  "KOICA 우간다 BOQ 세부항목",
  "노란색 단가 입력열에 현지견적을 넣으면 선택 시나리오 수량×단가로 예상금액이 계산됩니다. 원본 수량·수식·추적 위치는 보존됩니다.",
);
items.getRange("A4:S4").values = [[
  "원본시트",
  "행",
  "시설",
  "자동공종",
  "요소",
  "세부제목",
  "항목",
  "설명",
  "단위",
  "기본수량",
  "원본수식",
  "저배수",
  "고배수",
  "저수량",
  "고수량",
  "선택수량",
  "현지단가 UGX",
  "예상금액 UGX",
  "검토표시",
]];
styleHeader(items.getRange("A4:S4"));
items.getRange(`A5:O${itemRecords.length + 4}`).values = itemRecords.map((row) => [
  row.source_sheet,
  row.source_row,
  row.facility,
  row.trade_group,
  row.element_context,
  row.heading_context,
  row.item_code,
  row.description,
  row.unit_normalized,
  numberOrBlank(row.quantity_base),
  row.quantity_formula ? `'${row.quantity_formula}` : "",
  row.scope_multiplier_scenario_low,
  row.scope_multiplier_scenario_high,
  numberOrBlank(row.quantity_scaled_low),
  numberOrBlank(row.quantity_scaled_high),
]);
items.getRange("P5").formulas = [[
  "=IF('입력·근거'!$B$12=\"HIGH\",O5,N5)",
]];
items.getRange(`P5:P${itemRecords.length + 4}`).fillDown();
items.getRange(`Q5:Q${itemRecords.length + 4}`).values = itemRecords.map(() => [""]);
items.getRange("R5").formulas = [["=IF(Q5=\"\",\"\",P5*Q5)"]];
items.getRange(`R5:R${itemRecords.length + 4}`).fillDown();
items.getRange(`S5:S${itemRecords.length + 4}`).values = itemRecords.map((row) => [
  row.qc_flag,
]);
styleBody(items.getRange(`A5:S${itemRecords.length + 4}`), {
  wrap: false,
  size: 8,
});
items.getRange(`H5:H${itemRecords.length + 4}`).format.wrapText = true;
items.getRange(`J5:J${itemRecords.length + 4}`).format.numberFormat = "#,##0.000";
items.getRange(`L5:P${itemRecords.length + 4}`).format.numberFormat = "#,##0.000";
items.getRange(`Q5:Q${itemRecords.length + 4}`).format = {
  fill: COLORS.input,
  font: { color: COLORS.navy, size: 8 },
  numberFormat: "#,##0.00",
};
items.getRange(`R5:R${itemRecords.length + 4}`).format.numberFormat = "#,##0";
items.getRange(`P5:P${itemRecords.length + 4}`).conditionalFormats.add(
  "cellIs",
  {
    operator: "equal",
    formula: 0,
    format: { fill: COLORS.paleRed, font: { color: COLORS.red } },
  },
);
items.getRange(`S5:S${itemRecords.length + 4}`).conditionalFormats.add(
  "containsText",
  {
    text: "scope_multiplier_conflict",
    format: { fill: COLORS.paleYellow, font: { color: COLORS.amber, bold: true } },
  },
);
items.tables.add(
  `A4:S${itemRecords.length + 4}`,
  true,
  "KOICAUgandaBOQItems",
);
setColumnWidths(
  items,
  {
    A: 27,
    B: 8,
    C: 24,
    D: 22,
    E: 25,
    F: 31,
    G: 9,
    H: 70,
    I: 10,
    J: 13,
    K: 23,
    L: 9,
    M: 9,
    N: 13,
    O: 13,
    P: 13,
    Q: 15,
    R: 17,
    S: 36,
  },
  itemRecords.length + 4,
);
items.freezePanes.freezeRows(4);
items.freezePanes.freezeColumns(4);

// 공식 KOICA 후보
setTitle(
  official,
  "K",
  "KOICA 공식 공개데이터 추가후보",
  "연간발주계획·원조조달계약·국별사업보고서만 사용했습니다. 계획 한도액을 계약가나 준공가로 해석하지 않습니다.",
);
official.getRange("A4:K4").values = [[
  "사업번호",
  "국가",
  "사업·발주명",
  "공사범위",
  "한도액 KRW",
  "연면적 ㎡",
  "원시 한도/㎡",
  "현재 66사례",
  "기존 공고",
  "금액단계",
  "공식 URL",
]];
styleHeader(official.getRange("A4:K4"), COLORS.blue);
official.getRange(`A5:F${strictCostCandidates.length + 4}`).values =
  strictCostCandidates.map((row) => [
    row.project_no_linked,
    row.country_ko,
    row.record_title,
    row.record_scope,
    numberOrBlank(row.amount_value),
    numberOrBlank(row.gross_floor_area_m2),
  ]);
official.getRange("G5").formulas = [["=IFERROR(E5/F5,\"\")"]];
official.getRange(`G5:G${strictCostCandidates.length + 4}`).fillDown();
official.getRange(`H5:K${strictCostCandidates.length + 4}`).values =
  strictCostCandidates.map((row) => [
    notInReviewedCases.has(row.project_no_linked) ? "없음·우선검토" : "있음",
    row.existing_db_project_bid_nos,
    row.amount_boundary,
    row.official_record_url,
  ]);
styleBody(official.getRange(`A5:K${strictCostCandidates.length + 4}`), {
  wrap: true,
  size: 8,
});
official.getRange(`E5:E${strictCostCandidates.length + 4}`).format.numberFormat =
  "#,##0";
official.getRange(`F5:F${strictCostCandidates.length + 4}`).format.numberFormat =
  "#,##0.0";
official.getRange(`G5:G${strictCostCandidates.length + 4}`).format.numberFormat =
  "#,##0";
official.getRange(`H5:H${strictCostCandidates.length + 4}`).conditionalFormats.add(
  "containsText",
  {
    text: "우선검토",
    format: { fill: COLORS.paleYellow, font: { color: COLORS.amber, bold: true } },
  },
);
const ugandaStart = strictCostCandidates.length + 7;
official.getRange(`A${ugandaStart}:K${ugandaStart}`).merge();
official.getRange(`A${ugandaStart}`).values = [["우간다 공식자료 추가 추적대상"]];
styleSection(official.getRange(`A${ugandaStart}:K${ugandaStart}`), COLORS.teal);
official.getRange(`A${ugandaStart + 1}:I${ugandaStart + 1}`).values = [[
  "사업번호",
  "자료종류",
  "사업·발주명",
  "공사범위",
  "금액",
  "통화",
  "금액경계",
  "기존 공고",
  "다음 조사",
]];
styleHeader(
  official.getRange(`A${ugandaStart + 1}:I${ugandaStart + 1}`),
  COLORS.green,
);
official.getRange(
  `A${ugandaStart + 2}:I${ugandaStart + ugandaCandidates.length + 1}`,
).values = ugandaCandidates.map((row) => [
  row.project_no_linked,
  row.source_dataset,
  row.record_title,
  row.record_scope,
  numberOrBlank(row.amount_value),
  row.amount_currency,
  row.amount_boundary,
  row.existing_db_project_bid_nos,
  row.source_dataset === "annual_procurement_plan"
    ? "설계자료에서 연면적·BOQ 추적"
    : "사업보고서에서 면적·준공범위 추출",
]);
styleBody(
  official.getRange(
    `A${ugandaStart + 2}:I${ugandaStart + ugandaCandidates.length + 1}`,
  ),
  { wrap: true, size: 8 },
);
official.getRange(
  `E${ugandaStart + 2}:E${ugandaStart + ugandaCandidates.length + 1}`,
).format.numberFormat = "#,##0";
setColumnWidths(
  official,
  {
    A: 15,
    B: 15,
    C: 44,
    D: 56,
    E: 17,
    F: 14,
    G: 17,
    H: 18,
    I: 31,
    J: 31,
    K: 42,
  },
  ugandaStart + ugandaCandidates.length + 1,
);
official.freezePanes.freezeRows(4);

// 조사 체크리스트
setTitle(
  checklist,
  "G",
  "미래 KOICA 사업 건축조사 체크리스트",
  "이번 KOICA-only 시연에서 실제 발견된 불일치·누락을 다음 기획조사와 현지조사의 질문으로 전환했습니다.",
);
checklist.getRange("A4:G4").values = [[
  "우선순위",
  "조사질문",
  "이번 근거",
  "필요자료",
  "확인방법",
  "의사결정 영향",
  "상태",
]];
styleHeader(checklist.getRange("A4:G4"));
const checklistRows = [
  [
    "P0",
    "공식 연면적은 827.40㎡인가 835.67㎡인가?",
    "영문 BDS와 국문 입찰계획 불일치",
    "서명 설계도서 면적표·허가도면",
    "공간별 면적 재합산",
    "㎡당 단가 분모 확정",
    "미착수",
  ],
  [
    "P0",
    "시장쉼터는 5동인가 6동인가?",
    "General Summary 5동, 재공고 전기공종 6동",
    "최종 배치도·RFI 답변·계약 BOQ",
    "도면 모듈수와 BOQ 배수 대조",
    "수량·전기공사비 과소/과대 방지",
    "미착수",
  ],
  [
    "P0",
    "BOQ 501개 수량에 적용할 현지 단가는?",
    "미가격 BOQ, 가격항목 0개",
    "노무·재료·장비 현지견적",
    "3개 견적 중앙값과 출처 기록",
    "공종별 직접공사비 산정",
    "미착수",
  ],
  [
    "P1",
    "0으로 남은 수량 39개는 실제 0인가?",
    "수식·설계입력값 0 혼재",
    "최종 계산서·설계수량산출서",
    "수식 선행셀·도면 치수 역산",
    "누락수량 방지",
    "미착수",
  ],
  [
    "P1",
    "가설·일반조건 39개는 어떻게 가격화할 것인가?",
    "수량 없는 allowance 항목",
    "현지 시공사 견적·유사계약",
    "정액/공사비율 항목 분리",
    "간접비·현장경비 반영",
    "미착수",
  ],
  [
    "P1",
    "입찰한도 이후 계약·변경·준공금액은?",
    "현재 USD 272,603은 집행한도",
    "계약서·변경계약·지급증명",
    "금액단계별 원장 구축",
    "예산오차·변경위험 추정",
    "미착수",
  ],
  [
    "P1",
    "마케레레 ICT·연수원 신축의 연면적은?",
    "공식 발주계획 금액은 있으나 면적 없음",
    "기획조사·설계·입찰 첨부",
    "사업번호로 문서 추적",
    "우간다 미래 표본 2건 확대",
    "미착수",
  ],
  [
    "P2",
    "KOICA 공식 비용후보 6건의 범위가 비교 가능한가?",
    "시설유형·외부공사·세금 경계 상이",
    "BOQ·공사범위·가격시점",
    "A/B 등급 증거심사 후 정규화",
    "KOICA-only 비교군 구축",
    "미착수",
  ],
];
checklist.getRange(`A5:G${checklistRows.length + 4}`).values = checklistRows;
styleBody(checklist.getRange(`A5:G${checklistRows.length + 4}`), {
  wrap: true,
  size: 9,
});
checklist.getRange(`A5:A${checklistRows.length + 4}`).format = {
  font: { bold: true, color: COLORS.navy },
  horizontalAlignment: "center",
};
checklist.getRange(`G5:G${checklistRows.length + 4}`).format = {
  fill: COLORS.input,
  font: { color: COLORS.navy },
  horizontalAlignment: "center",
};
checklist.getRange(`G5:G${checklistRows.length + 4}`).dataValidation = {
  rule: { type: "list", values: ["미착수", "확인중", "완료"] },
};
checklist.getRange(`A5:A${checklistRows.length + 4}`).conditionalFormats.add(
  "containsText",
  {
    text: "P0",
    format: { fill: COLORS.paleRed, font: { color: COLORS.red, bold: true } },
  },
);
setColumnWidths(
  checklist,
  { A: 10, B: 34, C: 36, D: 32, E: 31, F: 31, G: 13 },
  checklistRows.length + 4,
);
checklist.freezePanes.freezeRows(4);

// Compact verification.
const inspections = [];
for (const [sheetName, range] of [
  ["판정", "A1:H22"],
  ["입력·근거", "A1:H18"],
  ["시설·공종 요약", `A1:R${Math.max(22, sheetStats.length + 4)}`],
  ["수량 벤치마크", `A1:H${unitTotals.length + 4}`],
  ["BOQ 항목", "A1:S25"],
  [
    "공식 KOICA 후보",
    `A1:K${ugandaStart + ugandaCandidates.length + 1}`,
  ],
  ["조사 체크리스트", `A1:G${checklistRows.length + 4}`],
]) {
  const inspected = await workbook.inspect({
    kind: "table",
    range: `${sheetName}!${range}`,
    include: "values,formulas",
    tableMaxRows: 25,
    tableMaxCols: 20,
    maxChars: 20000,
  });
  inspections.push({ sheetName, range, ndjson: inspected.ndjson });
  const preview = await workbook.render({
    sheetName,
    range,
    scale: sheetName === "BOQ 항목" ? 0.8 : 1.2,
    format: "png",
  });
  await fs.writeFile(
    path.join(previewDir, `${safeFileName(sheetName)}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
await fs.writeFile(
  path.join(outputDir, "workbook_verification.json"),
  `${JSON.stringify(
    {
      outputPath,
      sourceSheetsRendered: sourceSheets.length,
      outputSheetsRendered: inspections.length,
      inspections,
      formulaErrors: formulaErrors.ndjson,
    },
    null,
    2,
  )}\n`,
  "utf8",
);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(
  JSON.stringify(
    {
      outputPath,
      boqItemRows: itemRecords.length,
      strictCostCandidates: strictCostCandidates.length,
      ugandaCandidates: ugandaCandidates.length,
      sourceSheetsRendered: sourceSheets.length,
      outputSheetsRendered: inspections.length,
      formulaErrors: formulaErrors.ndjson,
    },
    null,
    2,
  ),
);
