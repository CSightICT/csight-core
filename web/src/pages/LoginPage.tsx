import { ArrowRight, LockKeyhole, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { friendlyError } from "../components/Ui";

export function LoginPage() {
  const { user, busy, login, startOidcLogin, sessionExpired, oidcAvailable, legacyPasswordAvailable } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) navigate((location.state as { from?: string } | null)?.from ?? "/cases", { replace: true });
  }, [location.state, navigate, user]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const data = new FormData(event.currentTarget);
    try {
      await login({
        tenant_slug: String(data.get("tenant_slug") ?? ""),
        email: String(data.get("email") ?? ""),
        password: String(data.get("password") ?? ""),
      });
    } catch (cause) {
      setError(friendlyError(cause));
    }
  }

  return <main id="main-content" className="login-page" tabIndex={-1}>
    <section className="login-story" aria-label="CSight 소개">
      <div className="login-brand"><span className="brand-mark"><ShieldCheck size={22} /></span><strong>CSight</strong></div>
      <div className="story-copy">
        <p className="eyebrow"><Sparkles size={15} /> 설명 가능한 고객 대응</p>
        <h1>사진과 문의 내용에서<br />정책 근거까지 한 흐름으로.</h1>
        <p>AI는 증거를 정리하고, 버전이 고정된 정책과 담당자의 판단이 최종 결정을 만듭니다.</p>
      </div>
      <div className="trust-row"><LockKeyhole size={18} /><span>로그인 정보와 접근 토큰은 브라우저 저장소에 남기지 않습니다.</span></div>
    </section>
    <section className="login-panel">
      {oidcAvailable && <div className="login-card oidc-login-card">
        <div><p className="eyebrow">권장 로그인</p><h2>조직 계정으로 계속</h2><p>승인된 회사 계정으로 인증한 뒤 원래 업무 화면으로 돌아옵니다.</p></div>
        <button className="button button-primary button-large" disabled={busy} type="button" onClick={() => startOidcLogin((location.state as { from?: string } | null)?.from ?? "/cases")}>조직 계정 로그인<ArrowRight size={18} /></button>
      </div>}
      {legacyPasswordAvailable && <form className="login-card" onSubmit={submit}>
        <div><p className="eyebrow">전환 기간 호환</p><h2>기존 파일럿 로그인</h2><p>OIDC 전환을 마칠 때까지 기존 계정을 한 릴리스 동안 지원합니다.</p></div>
        {sessionExpired && <div className="inline-alert" role="alert">세션이 만료되었습니다. 로그인하면 진행 중이던 실행 ID로 이어서 확인합니다.</div>}
        {error && <div className="inline-alert inline-alert-danger" role="alert">{error}</div>}
        <label>조직 슬러그<input name="tenant_slug" autoComplete="organization" required placeholder="예: csight-demo" /></label>
        <label>이메일<input name="email" type="email" autoComplete="username" required placeholder="name@company.com" /></label>
        <label>비밀번호<input name="password" type="password" autoComplete="current-password" required /></label>
        <button className="button button-primary button-large" disabled={busy} type="submit">{busy ? "확인 중…" : "로그인"}<ArrowRight size={18} /></button>
      </form>}
      {!oidcAvailable && !legacyPasswordAvailable && <div className="login-card"><div className="inline-alert inline-alert-danger" role="alert">이 서버에 사용할 수 있는 로그인 방식이 없습니다. 운영자에게 인증 설정을 요청해 주세요.</div></div>}
    </section>
  </main>;
}
