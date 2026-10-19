import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { Card, friendlyError } from "./Ui";

export function DemoResetPanel() {
  const client = useQueryClient();
  const [confirmation, setConfirmation] = useState<{ count: number; fingerprint: string } | null>(null);
  const preview = useQuery({ queryKey: ["demo-reset"], queryFn: () => api.previewDemoReset(), retry: false });
  const reset = useMutation({ mutationFn: (fingerprint: string) => api.resetDemoReviews(fingerprint),
    onSuccess: async () => { setConfirmation(null); await client.invalidateQueries(); },
    onError: () => { setConfirmation(null); void preview.refetch(); },
  });
  if (preview.data && !preview.data.enabled) return null;
  return <Card title="시연 다시 시작" className="spaced-card">
    <p>사진·AI 분석·정책 근거는 그대로 두고, 시연 문의를 검토 대기로 되돌립니다.</p>
    <p className="muted-copy">이전 처리 결과는 별도 보관됩니다. 현재 조직의 시연 데이터만 대상이며, 실운영 문의는 변경하지 않습니다.</p>
    {preview.error && <p role="alert">{friendlyError(preview.error)}</p>}
    {reset.error && <p role="alert">{friendlyError(reset.error)} 처리 여부가 불확실하면 대상을 다시 확인해 주세요.</p>}
    {reset.data?.reset_id && <p role="status">{reset.data.count}건을 검토 대기로 되돌렸습니다.</p>}
    <button className="button button-secondary" type="button" disabled={preview.isFetching || reset.isPending} onClick={async () => {
      const result = await preview.refetch();
      if (result.data?.enabled && !result.error) setConfirmation(result.data);
    }}>DB 적재 원복</button>
    {confirmation && <div className="demo-reset-confirm" role="alertdialog" aria-modal="false" aria-labelledby="demo-reset-title">
      <h3 id="demo-reset-title">{confirmation.count}건을 검토 대기로 되돌릴까요?</h3>
      <p>처리 보고서·시뮬레이션·데이터 자산은 현재 집계에서 빠지고 초기화 보관 기록으로 옮겨집니다. 다른 검토 창은 새로고침해 주세요.</p>
      <button type="button" className="button button-primary" disabled={reset.isPending || confirmation.count === 0} onClick={() => reset.mutate(confirmation.fingerprint)}>{reset.isPending ? "원복 중…" : "검토 대기로 원복"}</button>
      <button type="button" className="button button-ghost" disabled={reset.isPending} onClick={() => setConfirmation(null)}>취소</button>
    </div>}
  </Card>;
}
