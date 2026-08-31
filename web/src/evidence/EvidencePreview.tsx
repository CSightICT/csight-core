import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileImage, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { Evidence } from "../api/contracts";

function EvidenceFallback({ loading, canRetry, onRetry }: {
  loading: boolean;
  canRetry: boolean;
  onRetry: () => void;
}) {
  return <div className="evidence-preview-fallback" role="status">
    <FileImage aria-hidden="true" size={28} />
    <span>{loading
      ? "보호된 미리보기를 불러오는 중입니다."
      : "미리보기를 표시할 수 없어 파일 정보만 제공합니다."}</span>
    {canRetry && <button className="button button-ghost button-small" type="button" onClick={onRetry}>
      <RefreshCw size={14} /> 다시 시도
    </button>}
  </div>;
}

export type EvidencePreviewStatus = "LOADING" | "READY" | "FAILED" | "NOT_APPLICABLE";

function EvidenceBlobImage({ content, evidence, failed, onFailed, onReady, onRetry }: {
  content: Blob;
  evidence: Evidence;
  failed: boolean;
  onFailed: () => void;
  onReady: () => void;
  onRetry: () => void;
}) {
  const linkRef = useRef<HTMLAnchorElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  useEffect(() => {
    if (failed) return undefined;
    const nextObjectUrl = URL.createObjectURL(content);
    linkRef.current?.setAttribute("href", nextObjectUrl);
    imageRef.current?.setAttribute("src", nextObjectUrl);
    return () => URL.revokeObjectURL(nextObjectUrl);
  }, [content, failed]);

  if (failed) return <EvidenceFallback loading={false} canRetry onRetry={onRetry} />;
  return <a
    ref={linkRef}
    className="evidence-preview-image"
    target="_blank"
    rel="noopener noreferrer"
    aria-label={`${evidence.original_filename} 원본 새 탭에서 열기`}
  >
    <img
      ref={imageRef}
      alt={`${evidence.original_filename} 증거 미리보기`}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onLoad={onReady}
      onError={onFailed}
    />
    <span><ExternalLink size={16} /> 원본 열기</span>
  </a>;
}

export function EvidencePreview({ caseId, evidence, onStatusChange }: {
  caseId: string;
  evidence: Evidence;
  onStatusChange?: (evidenceId: string, status: EvidencePreviewStatus) => void;
}) {
  const availableImage = evidence.upload_status === "AVAILABLE" && evidence.evidence_type === "IMAGE";
  const contentQuery = useQuery({
    queryKey: ["evidence-content", caseId, evidence.evidence_id],
    queryFn: () => api.getEvidenceContent(caseId, evidence.evidence_id),
    enabled: availableImage,
    retry: false,
    staleTime: Infinity,
    gcTime: 0,
  });
  const [imageOutcome, setImageOutcome] = useState<{ key: number; status: "READY" | "FAILED" } | null>(null);
  const contentKey = contentQuery.dataUpdatedAt;
  const decodeStatus = imageOutcome?.key === contentKey ? imageOutcome.status : "LOADING";
  const status: EvidencePreviewStatus = evidence.evidence_type !== "IMAGE"
    ? "NOT_APPLICABLE"
    : !availableImage || contentQuery.isError
      ? "FAILED"
      : contentQuery.isPending || contentQuery.isFetching || !contentQuery.data
        ? "LOADING"
        : decodeStatus;
  useEffect(() => {
    onStatusChange?.(evidence.evidence_id, status);
  }, [evidence.evidence_id, onStatusChange, status]);
  const retry = () => {
    setImageOutcome(null);
    void contentQuery.refetch();
  };

  return <article className="evidence-preview" data-testid={`evidence-preview-${evidence.evidence_id}`}>
    {contentQuery.data && !contentQuery.isError ? <EvidenceBlobImage
      content={contentQuery.data}
      evidence={evidence}
      failed={decodeStatus === "FAILED"}
      key={contentQuery.dataUpdatedAt}
      onFailed={() => setImageOutcome({ key: contentKey, status: "FAILED" })}
      onReady={() => setImageOutcome({ key: contentKey, status: "READY" })}
      onRetry={retry}
    /> : <EvidenceFallback
      loading={contentQuery.isPending && availableImage}
      canRetry={availableImage && contentQuery.isError}
      onRetry={retry}
    />}
    <div className="evidence-preview-meta">
      <strong>{evidence.original_filename}</strong>
      <small>{Math.ceil(evidence.size_bytes / 1024)} KB · {evidence.width}×{evidence.height}</small>
      <small>인증된 same-origin 원본 · 페이지를 벗어나면 임시 미리보기 폐기</small>
    </div>
  </article>;
}
