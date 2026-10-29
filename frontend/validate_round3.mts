// simulation_v2 契约离线验证：真实 zod schema parse fixtures + 标签纯函数。
// 运行：node --experimental-strip-types validate_round3.mts（零依赖，仅用项目已有 zod）。
import {
  todayPageSchema,
  researchPageSchema,
  portfolioPageSchema,
  executionPageSchema,
  shellPayloadSchema,
  researchSchema
} from "./src/lib/schemas.ts";
import { sizeTierLabel, sizeRatioText, evidenceQualityLabel, horizonLabel } from "./src/lib/display.ts";
import {
  FIXTURE_DATE,
  fixtureV2Card,
  fixtureLegacyCard,
  fixtureResearch,
  fixturePortfolio,
  fixtureToday,
  fixtureExecutionSync
} from "./test-fixtures/simulation-v2.mjs";

let pass = 0, fail = 0;
function check(name: string, cond: boolean, extra = "") {
  if (cond) { pass++; console.log("PASS " + name); }
  else { fail++; console.log("FAIL " + name + (extra ? " | " + extra : "")); }
}

try {
  const t = todayPageSchema.parse(fixtureToday);
  const cards = t.research.fund_cards;
  check("today schema parse", cards.length === 2, "cards=" + cards.length);
  check("v2 card sizeTier preserved", cards[0].sizeTier === "medium", String(cards[0].sizeTier));
  check("legacy sizeTier='legacy' preserved (not rejected, not inferred)", cards[1].sizeTier === "legacy", String(cards[1].sizeTier));
} catch (e) { check("today schema parse", false, String(e).slice(0, 300)); }

try { researchPageSchema.parse({ selectedDate: FIXTURE_DATE, research: fixtureResearch }); check("research page schema parse", true); }
catch (e) { check("research page schema parse", false, String(e).slice(0, 300)); }

try { portfolioPageSchema.parse({ selectedDate: FIXTURE_DATE, portfolio: fixturePortfolio }); check("portfolio page schema parse", true); }
catch (e) { check("portfolio page schema parse", false, String(e).slice(0, 300)); }

try { executionPageSchema.parse({ selectedDate: FIXTURE_DATE, executionSync: fixtureExecutionSync, portfolio: fixturePortfolio }); check("execution page schema parse", true); }
catch (e) { check("execution page schema parse", false, String(e).slice(0, 300)); }

try { shellPayloadSchema.parse({ selectedDate: FIXTURE_DATE, dates: [FIXTURE_DATE], summary: {}, system: {} }); check("shell schema parse", true); }
catch (e) { check("shell schema parse", false, String(e).slice(0, 300)); }

// 非法 tier → 数组层 catch 清空整组 cards（记录现有行为，非本轮引入）
try {
  const bad = researchSchema.parse({ meta: "", metrics: [], rows: [], fund_cards: [{ ...fixtureV2Card, sizeTier: "weird" }] });
  check("invalid tier: array catch empties cards", bad.fund_cards.length === 0, "len=" + bad.fund_cards.length);
} catch (e) { check("invalid tier behavior", false, String(e).slice(0, 200)); }

check("sizeTierLabel small", sizeTierLabel("small") === "小仓");
check("sizeTierLabel medium", sizeTierLabel("medium") === "中仓");
check("sizeTierLabel large", sizeTierLabel("large") === "大仓");
check("sizeTierLabel none", sizeTierLabel("none") === "持有/观望");
check("sizeRatioText 10%", sizeRatioText(0.10) === "10%");
check("sizeRatioText 25%", sizeRatioText(0.25) === "25%");
check("sizeRatioText 50%", sizeRatioText(0.50) === "50%");
check("sizeRatioText null", sizeRatioText(null) === "");
check("evidenceQualityLabel high", evidenceQualityLabel("high") === "证据充分");
check("evidenceQualityLabel null", evidenceQualityLabel(null) === "证据质量未知");
check("horizonLabel unspecified", horizonLabel("unspecified") === "期限未定");
check("horizonLabel 中期", horizonLabel("中期(3-6月)") === "中期(3-6月)");

// simulationV2 嵌套 schema（camel 键，与实际 API 输出一致）
const sv2Base = { schemaVersion: "simulation_v2", fundingMode: "virtual_external_flows", netExternalFlow: 2000, externalCashflow: 2000, externalCashflowTiming: "end", valuationStatus: "exact", portfolioDate: FIXTURE_DATE };
try {
  const p = portfolioPageSchema.parse({ selectedDate: FIXTURE_DATE, portfolio: { ...fixturePortfolio, simulationV2: sv2Base } });
  check("sv2 v2 mode preserved", p.portfolio.simulationV2?.fundingMode === "virtual_external_flows" && p.portfolio.simulationV2?.netExternalFlow === 2000);
  check("sv2 externalCashflowTiming kept (not stripped)", p.portfolio.simulationV2?.externalCashflowTiming === "end", String(p.portfolio.simulationV2?.externalCashflowTiming));
} catch (e) { check("sv2 v2 mode parse", false, String(e).slice(0, 200)); }
try {
  const p = portfolioPageSchema.parse({ selectedDate: FIXTURE_DATE, portfolio: { ...fixturePortfolio, simulationV2: { schemaVersion: "legacy", fundingMode: null, netExternalFlow: null, externalCashflow: null } } });
  check("sv2 legacy fundingMode=null parses", p.portfolio.simulationV2?.fundingMode === null);
} catch (e) { check("sv2 legacy null fundingMode", false, String(e).slice(0, 200)); }
try {
  const p = portfolioPageSchema.parse({ selectedDate: FIXTURE_DATE, portfolio: { ...fixturePortfolio, simulationV2: { ...sv2Base, netExternalFlow: "oops" } } });
  check("sv2 invalid netExternalFlow coerced to null", p.portfolio.simulationV2?.netExternalFlow === null, String(p.portfolio.simulationV2?.netExternalFlow));
} catch (e) { check("sv2 invalid netExternalFlow coerced to null", false, String(e).slice(0, 200)); }

// 复审门回归：坏卡不再清空整组
try {
  const mixed = researchSchema.parse({
    meta: "fixture", metrics: [], rows: [],
    fund_cards: [fixtureV2Card, fixtureLegacyCard, fixtureV2Card, null, { ...fixtureV2Card, sizeTier: "weird" }]
  });
  check("mixed bad cards: 3 healthy kept", mixed.fund_cards.length === 3, "len=" + mixed.fund_cards.length);
  check("mixed bad cards: dropped_cards=2", mixed.dropped_cards === 2, String(mixed.dropped_cards));
} catch (e) { check("mixed bad cards regression", false, String(e).slice(0, 200)); }

// 持仓坏行：整组 parse 失败（页面明确报错），不静默丢资产
try {
  portfolioPageSchema.parse({ selectedDate: FIXTURE_DATE, portfolio: { ...fixturePortfolio, items: [...fixturePortfolio.items, null] } });
  check("portfolio bad item: parse error (no silent drop)", false, "should have failed");
} catch { check("portfolio bad item: parse error (no silent drop)", true); }

// fundingLineText 纯 helper 验证
import { fundingLineText } from "./src/lib/display.ts";
check("funding v2 flow 2000 shows 净流入", fundingLineText({ fundingMode: "virtual_external_flows", netExternalFlow: 2000 }, "10,000.00").includes("净流入 +2,000"));
check("funding v2 null flow shows 暂无", fundingLineText({ fundingMode: "virtual_external_flows", netExternalFlow: null }, "10,000.00").includes("暂无"));
check("funding legacy keeps 旧版参考 cash", fundingLineText(undefined, "10,000.00") === "现金(旧版参考) 10,000.00");

console.log("\nRESULT pass=" + pass + " fail=" + fail);
process.exit(fail ? 1 : 0);
