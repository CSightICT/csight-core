import type { KeyboardEvent } from "react";

import type { OperatorQueueCounts, OperatorQueueView } from "../api/contracts";

const views: Array<{ value: OperatorQueueView; label: string }> = [
  { value: "all", label: "전체" },
  { value: "my", label: "내 업무" },
  { value: "unassigned", label: "미배정" },
  { value: "urgent", label: "긴급" },
  { value: "waiting_evidence", label: "증거 대기" },
  { value: "complete", label: "완료" },
];

export function OperatorQueueTabs({
  counts,
  idPrefix,
  panelId,
  value,
  onChange,
  allowedViews,
}: {
  counts: OperatorQueueCounts;
  idPrefix: string;
  panelId: string;
  value: OperatorQueueView;
  allowedViews?: OperatorQueueView[];
  onChange(value: OperatorQueueView): void;
}) {
  const visibleViews = allowedViews ? views.filter((item) => allowedViews.includes(item.value)) : views;
  function move(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? visibleViews.length - 1
        : delta
          ? (index + delta + visibleViews.length) % visibleViews.length
          : null;
    if (nextIndex === null) return;
    event.preventDefault();
    const next = visibleViews[nextIndex]!;
    onChange(next.value);
    document.getElementById(`${idPrefix}-${next.value}`)?.focus();
  }

  return <div className="queue-tabs-scroll">
    <div className="queue-tabs" role="tablist" aria-label="업무 보기">
      {visibleViews.map((view, index) => <button
        key={view.value}
        id={`${idPrefix}-${view.value}`}
        className={value === view.value ? "queue-tab queue-tab-active" : "queue-tab"}
        type="button"
        role="tab"
        aria-controls={panelId}
        aria-selected={value === view.value}
        tabIndex={value === view.value ? 0 : -1}
        onClick={() => onChange(view.value)}
        onKeyDown={(event) => move(event, index)}
      >
        <span>{view.label}</span><strong>{counts[view.value]}</strong>
      </button>)}
    </div>
  </div>;
}
