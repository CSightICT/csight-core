import { BookOpenText } from "lucide-react";

import type { PolicyCitationSnapshot } from "../api/contracts";

export function PolicyCitationList({ citations }: { citations: PolicyCitationSnapshot[] }) {
  if (citations.length === 0) return null;
  return <div className="policy-citation-pack" data-testid="policy-citation-pack">
    <div className="policy-citation-pack-heading">
      <BookOpenText aria-hidden="true" size={18} />
      <div><strong>고정된 정책 근거</strong><span>인용 당시 제목·본문·문서 버전</span></div>
      <span className="synthetic-policy-badge" data-testid="synthetic-policy-badge">가상 사내 정책 · PoC 전용</span>
    </div>
    <ol className="policy-citation-list">
      {citations.map((citation) => <li key={citation.citation_id}>
        <header>
          <div><span>{citation.citation_id}</span><strong>{citation.title}</strong></div>
          <span>문서 버전 {citation.document_version}</span>
        </header>
        <p>{citation.text}</p>
        <small>{citation.section_path.join(" › ")} · {citation.policy_clause_id}</small>
      </li>)}
    </ol>
    <p className="policy-citation-boundary">이 인용은 정책 판단 근거를 보여주는 변경 불가 스냅샷이며, 그 자체로 승인·환불·교환 결정을 만들지 않습니다.</p>
  </div>;
}
