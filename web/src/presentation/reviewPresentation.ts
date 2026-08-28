import { businessLabel } from "./businessLabels";

export type QualificationPresentationItem = {
  label: string;
  status: string;
  tone: "ready" | "attention" | "neutral";
};

const qualificationLabels: Record<string, string> = {
  llm: "문의 내용 분석",
  vision: "이미지 분석",
  alignment: "문의·이미지 일치 확인",
  grounding: "정책 근거 정합성",
};

const readyScopes = new Set(["QUALIFIED", "FULLY_QUALIFIED", "LOCAL_POC", "MOCK_QUALIFIED", "AVAILABLE"]);
const attentionScopes = new Set(["NOT_AVAILABLE", "UNAVAILABLE", "FAILED", "PARTIAL", "NOT_QUALIFIED"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function scopeOf(value: unknown): string {
  if (isRecord(value) && typeof value.scope === "string") return value.scope;
  return typeof value === "string" ? value : "UNKNOWN";
}

function presentScope(scope: string): Pick<QualificationPresentationItem, "status" | "tone"> {
  if (scope === "MOCK_QUALIFIED" || scope === "LOCAL_POC") {
    return { status: "참고용 분석 결과 준비", tone: "ready" };
  }
  if (scope === "NOT_AVAILABLE" || scope === "UNAVAILABLE") {
    return { status: "담당자 확인 필요", tone: "attention" };
  }
  if (scope === "FAILED" || scope === "NOT_QUALIFIED") {
    return { status: "분석 결과 사용 불가", tone: "attention" };
  }
  if (scope === "PARTIAL") return { status: "일부 결과만 확인됨", tone: "attention" };
  if (readyScopes.has(scope)) return { status: "분석 결과 준비", tone: "ready" };
  if (scope === "SKIPPED") return { status: "이번 검토에서 확인하지 않음", tone: "neutral" };
  return { status: businessLabel(scope), tone: attentionScopes.has(scope) ? "attention" : "neutral" };
}

export function qualificationPresentation(value: unknown): QualificationPresentationItem[] {
  if (!isRecord(value)) {
    const presented = presentScope(scopeOf(value));
    return [{ label: "분석 상태", ...presented }];
  }
  const preferredKeys = ["llm", "vision", "alignment", "grounding"];
  const keys = [
    ...preferredKeys.filter((key) => key in value),
    ...Object.keys(value).filter((key) => !preferredKeys.includes(key)),
  ];
  if (keys.length === 0) return [{ label: "분석 상태", status: "기록된 결과 없음", tone: "neutral" }];
  return keys.map((key) => ({
    label: qualificationLabels[key] ?? businessLabel(key),
    ...presentScope(scopeOf(value[key])),
  }));
}
