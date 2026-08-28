import { Eye, MailCheck, ShieldCheck, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { CustomerCommunicationSimulation } from "../api/contracts";
import { Card, Notice, formatDate, friendlyError } from "../components/Ui";

export function CommunicationSimulationPanel({ caseId }: { caseId: string }) {
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<CustomerCommunicationSimulation | null>(null);
  const communications = useQuery({
    queryKey: ["customer-communications", caseId],
    queryFn: () => api.listCustomerCommunications(caseId),
  });
  const create = useMutation({
    mutationFn: () => api.createCustomerCommunication(caseId),
    onSuccess: async (value) => {
      setPreview(value);
      await queryClient.invalidateQueries({ queryKey: ["customer-communications", caseId] });
    },
  });
  const existing = communications.data?.[0] ?? null;

  return <Card className="communication-card" title="고객 안내" description="확정된 검토 보고서를 바탕으로 고객에게 보일 메일을 만들어 확인합니다."
    actions={<button className="button button-primary" type="button" disabled={create.isPending || communications.isLoading}
      onClick={() => existing ? setPreview(existing) : create.mutate()}>
      {existing ? <><Eye size={18} />안내 메일 보기</> : <><MailCheck size={18} />안내 메일 만들기</>}
    </button>}>
    <Notice tone="info" title="외부 메일 시스템 미연결"><span>메일 본문과 발송 기록만 고객사 영역에 고정합니다. SMTP 전송, 고객 연락, 결제 취소는 수행하지 않습니다.</span></Notice>
    {create.error && <div className="inline-alert inline-alert-danger" role="alert">{friendlyError(create.error)}</div>}
    {existing && <p className="communication-history"><ShieldCheck size={16} /> {formatDate(existing.created_at)}에 발송 화면이 생성되었습니다. 실제 발송은 0건입니다.</p>}
    {preview && <div className="mail-preview" role="dialog" aria-modal="true" aria-label="고객 안내 메일 미리보기">
      <div className="mail-preview-head"><div><span>고객 안내 메일</span><strong>실제 발송 없음</strong></div><button className="icon-button" type="button" aria-label="메일 미리보기 닫기" onClick={() => setPreview(null)}><X /></button></div>
      <dl><div><dt>받는 사람</dt><dd>{preview.recipient_label}</dd></div><div><dt>제목</dt><dd>{operationalMailCopy(preview.subject)}</dd></div></dl>
      <pre>{operationalMailCopy(preview.body)}</pre>
      <footer><ShieldCheck size={16} /> 변경 방지 기록 · 외부 메일 시스템 미반영</footer>
    </div>}
  </Card>;
}

function operationalMailCopy(value: string): string {
  return value
    .replaceAll("[CSight 데모]", "[CSight]")
    .replaceAll("시스템 모의 검증", "외부 요청 사전 확인")
    .replaceAll("본 화면은 PoC용 메일 발송 시뮬레이션입니다.", "이 안내 메일은 외부 메일 시스템에 전송되지 않은 내부 확인본입니다.");
}
