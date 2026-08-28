import { clsx } from "clsx";

const labels: Record<string, string> = {
  RECEIVED: "접수",
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
  EVALUATED: "정책 확인 완료",
  REQUIRES_HUMAN_REVIEW: "담당자 검토 필요",
  REQUIRES_ADDITIONAL_EVIDENCE: "추가 자료 필요",
  NO_APPLICABLE_RULE: "적용 정책 없음",
  BLOCKED_INPUT_INCOMPLETE: "입력 정보 부족",
};

export function StatusBadge({ status, subtle = false }: { status: string; subtle?: boolean }) {
  const normalized = status?.toUpperCase?.() ?? "UNKNOWN";
  const tone = ["SUCCEEDED", "COMPLETED", "RESOLVED", "ACTION_DRY_RUN_VALIDATED"].includes(normalized)
    ? "positive"
    : ["FAILED", "ACTION_DRY_RUN_FAILED"].includes(normalized)
      ? "danger"
    : ["PARTIAL_SUCCESS", "WAITING_FOR_EVIDENCE", "ACTION_NEEDS_INPUT", "ESCALATED", "REQUIRES_HUMAN_REVIEW", "REQUIRES_ADDITIONAL_EVIDENCE", "NO_APPLICABLE_RULE", "BLOCKED_INPUT_INCOMPLETE"].includes(normalized)
        ? "warning"
        : ["RUNNING", "CLAIMED", "ACTION_READY"].includes(normalized)
          ? "active"
          : "neutral";
  return <span className={clsx("status-badge", `status-${tone}`, subtle && "status-subtle")}>{labels[normalized] ?? normalized}</span>;
}
