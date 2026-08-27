import { clsx } from "clsx";

const labels: Record<string, string> = {
  OPEN: "접수",
  PENDING: "대기",
  QUEUED: "대기",
  RUNNING: "처리 중",
  RETRY_WAITING: "재시도 대기",
  SUCCEEDED: "완료",
  COMPLETED: "완료",
  PARTIAL_SUCCESS: "부분 완료",
  FAILED: "실패",
  CLAIMED: "검토 중",
  WAITING_FOR_EVIDENCE: "추가 자료 필요",
  ESCALATED: "관리자 검토",
  RESOLVED: "결정 완료",
  ACTION_NEEDS_INPUT: "실행 정보 부족",
  ACTION_READY: "실행 준비",
  ACTION_DRY_RUN_PENDING: "모의 실행 대기",
  ACTION_DRY_RUN_VALIDATED: "모의 실행 검증됨",
  ACTION_DRY_RUN_FAILED: "모의 실행 실패",
  LIVE_EXTERNAL_ACTION_DISABLED: "실제 실행 차단",
};

export function StatusBadge({ status, subtle = false }: { status: string; subtle?: boolean }) {
  const normalized = status?.toUpperCase?.() ?? "UNKNOWN";
  const tone = ["SUCCEEDED", "COMPLETED", "RESOLVED", "ACTION_DRY_RUN_VALIDATED"].includes(normalized)
    ? "positive"
    : ["FAILED", "ACTION_DRY_RUN_FAILED"].includes(normalized)
      ? "danger"
      : ["PARTIAL_SUCCESS", "WAITING_FOR_EVIDENCE", "ACTION_NEEDS_INPUT", "ESCALATED"].includes(normalized)
        ? "warning"
        : ["RUNNING", "CLAIMED", "ACTION_READY"].includes(normalized)
          ? "active"
          : "neutral";
  return <span className={clsx("status-badge", `status-${tone}`, subtle && "status-subtle")}>{labels[normalized] ?? normalized}</span>;
}
