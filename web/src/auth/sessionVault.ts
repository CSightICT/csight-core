export interface OidcSessionExpiry {
  idle_expires_at: string;
  absolute_expires_at: string;
  effective_expires_at: string;
  expiry_warning_at: string;
  expires_in_seconds: number;
  expires_within_five_minutes: boolean;
}

let csrfToken: string | null = null;
let expiry: OidcSessionExpiry | null = null;

export const sessionVault = {
  set(token: string, nextExpiry: OidcSessionExpiry): void {
    csrfToken = token;
    expiry = nextExpiry;
  },
  csrf(): string | null {
    if (!csrfToken || !expiry || Date.now() >= Date.parse(expiry.effective_expires_at)) {
      this.clear();
      return null;
    }
    return csrfToken;
  },
  currentExpiry(): OidcSessionExpiry | null {
    return this.csrf() ? expiry : null;
  },
  clear(): void {
    csrfToken = null;
    expiry = null;
  },
  isAuthenticated(): boolean {
    return this.csrf() !== null;
  },
};
