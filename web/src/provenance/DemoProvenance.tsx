import { ShieldAlert, Tags } from "lucide-react";

const RIGHTS_STATUS = "INTERNAL_RESTRICTED_PROVENANCE_UNVERIFIED";
const POLICY_LINKAGE = "NOT_LINKED_TO_POLICY_INPUT";
const CUSTOMER_STATEMENT_BOUNDARY = "CUSTOMER_STATEMENT_ONLY_FOR_NON_VISIBLE_FACTS";
const SOURCE_GRADES = new Set([
  "KAPUTT_SELECTED_CORRECT_POSITIVE",
  "USER_SUPPLIED_NORMAL_REFERENCE",
]);

type ProvenanceSourceGrade =
  | "KAPUTT_SELECTED_CORRECT_POSITIVE"
  | "USER_SUPPLIED_NORMAL_REFERENCE";

export interface DemoProvenanceView {
  status: "VALID" | "UNKNOWN";
  sourceGrade: ProvenanceSourceGrade | null;
  sourceLabel: string;
  selectionSummary: string;
  scenarioLabel: string;
  schemaVersion: "1.0" | "2.0" | "3.0" | null;
}

const PROVENANCE_CONTRACTS = {
  "1.0": {
    datasetId: "realistic-internal-demo-v1",
    scenarioScope: "INTERNAL_CURATED_6_DEFECT_4_BELOW_THRESHOLD",
    scenarioLabel: "선별 이미지 문의 v1",
  },
  "2.0": {
    datasetId: "realistic-internal-demo-v2",
    scenarioScope: "INTERNAL_CURATED_ECOMMERCE_INQUIRY_6_DEFECT_4_BELOW_THRESHOLD",
    scenarioLabel: "이커머스 상품 문의 v2",
    narrativeRevisions: new Set(["VISUAL_ALIGNED_R1", "COMMERCE_CONTEXT_R2", "COMMERCE_CONTEXT_R2_E3"]),
  },
  "3.0": {
    datasetId: "realistic-internal-demo-v3",
    scenarioScope: "INTERNAL_CURATED_ECOMMERCE_EXPANSION_12_DEFECT_8_REFERENCE_TOTAL",
    scenarioLabel: "이커머스 상품 문의 확장 v3",
    narrativeRevisions: new Set(["CLOSED_SET_EXPANSION_R3"]),
  },
} as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sourceLabel(grade: ProvenanceSourceGrade): string {
  return grade === "KAPUTT_SELECTED_CORRECT_POSITIVE"
    ? "Kaputt 선별 정답 양성 표본"
    : "사용자 제공 정상 참조 표본";
}

function selectionSummary(grade: ProvenanceSourceGrade): string {
  return grade === "KAPUTT_SELECTED_CORRECT_POSITIVE"
    ? "결함 양성·정답 사례 중심으로 선별된 표본입니다."
    : "사용자가 제공한 소수 정상 참조 표본입니다.";
}

export function readDemoProvenance(attributes: Record<string, unknown>): DemoProvenanceView | null {
  const raw = isRecord(attributes.realistic_demo)
    ? attributes.realistic_demo
    : isRecord(attributes.curated_demo)
      ? attributes.curated_demo
      : null;
  if (raw === null) return null;

  const sourceGrade = typeof raw.source_grade === "string" && SOURCE_GRADES.has(raw.source_grade)
    ? raw.source_grade as ProvenanceSourceGrade
    : null;
  const schemaVersion = raw.schema_version === "1.0" || raw.schema_version === "2.0" || raw.schema_version === "3.0"
    ? raw.schema_version
    : null;
  const contract = schemaVersion === null ? null : PROVENANCE_CONTRACTS[schemaVersion];
  const datasetMatches = contract !== null
    && (raw.dataset_id === contract.datasetId || (schemaVersion === "1.0" && raw.dataset_id === undefined));
  const revisionMatches = schemaVersion === "1.0"
    || ((schemaVersion === "2.0" || schemaVersion === "3.0")
      && typeof raw.narrative_revision === "string"
      && PROVENANCE_CONTRACTS[schemaVersion].narrativeRevisions.has(raw.narrative_revision));
  const valid = contract !== null
    && raw.scenario_scope === contract.scenarioScope
    && datasetMatches
    && revisionMatches
    && sourceGrade !== null
    && typeof raw.selection_bias === "string"
    && raw.selection_bias.trim().length > 0
    && raw.rights_status === RIGHTS_STATUS
    && raw.policy_input_linkage === POLICY_LINKAGE;

  if (!valid || sourceGrade === null) {
    return {
      status: "UNKNOWN",
      sourceGrade: null,
      sourceLabel: "출처 등급 확인 필요",
      selectionSummary: "예상한 provenance 계약과 달라 선택·권리·정책 연결 상태를 신뢰할 수 없습니다.",
      scenarioLabel: "출처 계약 확인 필요",
      schemaVersion: null,
    };
  }
  return {
    status: "VALID",
    sourceGrade,
    sourceLabel: sourceLabel(sourceGrade),
    selectionSummary: selectionSummary(sourceGrade),
    scenarioLabel: contract.scenarioLabel,
    schemaVersion,
  };
}

export function readDemoImageObservation(attributes: Record<string, unknown>): string | null {
  const provenance = readDemoProvenance(attributes);
  const observation = attributes.demo_image_observation;
  if (
    provenance?.status !== "VALID"
    || (provenance.schemaVersion !== "2.0" && provenance.schemaVersion !== "3.0")
    || attributes.demo_claim_boundary !== CUSTOMER_STATEMENT_BOUNDARY
    || typeof observation !== "string"
    || observation.trim().length === 0
  ) return null;
  return observation.trim();
}

export function DemoProvenance({ attributes }: { attributes: Record<string, unknown> }) {
  const provenance = readDemoProvenance(attributes);
  if (provenance === null) return null;

  if (provenance.status === "UNKNOWN") {
    return <div className="provenance-panel provenance-panel-warning" data-testid="demo-provenance-unknown">
      <ShieldAlert aria-hidden="true" size={18} />
      <div><strong>데이터 출처 상태 확인 필요</strong><p>{provenance.selectionSummary}</p></div>
    </div>;
  }

  return <div className="provenance-panel" data-testid="demo-provenance">
    <div className="provenance-heading"><Tags aria-hidden="true" size={18} /><strong>데이터 출처 정보</strong></div>
    <div className="provenance-badges" aria-label="데이터 출처 범위">
      <span>{provenance.scenarioLabel}</span>
      <span>선별 데이터</span>
      <span>재사용 권리 미확인</span>
      <span>Vision은 정책 판단 입력과 연결되지 않음</span>
    </div>
    <p><strong>출처 등급:</strong> {provenance.sourceLabel}</p>
    <p>{provenance.selectionSummary} 원본 식별자와 해시는 화면에 표시하지 않습니다.</p>
  </div>;
}
