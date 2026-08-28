import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileImage, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

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

function EvidenceBlobImage({ content, evidence, onRetry }: {
  content: Blob;
  evidence: Evidence;
  onRetry: () => void;
}) {
  const [objectUrl] = useState(() => URL.createObjectURL(content));
  const [imageFailed, setImageFailed] = useState(false);
  useEffect(() => () => URL.revokeObjectURL(objectUrl), [objectUrl]);

  if (imageFailed) return <EvidenceFallback loading={false} canRetry onRetry={onRetry} />;
  return <a
    className="evidence-preview-image"
    href={objectUrl}
    target="_blank"
    rel="noopener noreferrer"
    aria-label={`${evidence.original_filename} 원본 새 탭에서 열기`}
  >
    <img
      src={objectUrl}
      alt={`${evidence.original_filename} 증거 미리보기`}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setImageFailed(true)}
    />
    <span><ExternalLink size={16} /> 원본 열기</span>
  </a>;
}

export function EvidencePreview({ caseId, evidence }: { caseId: string; evidence: Evidence }) {
  const availableImage = evidence.upload_status === "AVAILABLE" && evidence.evidence_type === "IMAGE";
  const contentQuery = useQuery({
    queryKey: ["evidence-content", caseId, evidence.evidence_id],
    queryFn: () => api.getEvidenceContent(caseId, evidence.evidence_id),
    enabled: availableImage,
    retry: false,
    gcTime: 0,
  });
  const retry = () => { void contentQuery.refetch(); };

  return <article className="evidence-preview" data-testid={`evidence-preview-${evidence.evidence_id}`}>
    {contentQuery.data ? <EvidenceBlobImage
      content={contentQuery.data}
      evidence={evidence}
      key={contentQuery.dataUpdatedAt}
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
