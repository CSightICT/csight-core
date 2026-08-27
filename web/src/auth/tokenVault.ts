let accessToken: string | null = null;
let expiresAt = 0;

export const tokenVault = {
  set(token: string, expiresInSeconds: number): void {
    accessToken = token;
    expiresAt = Date.now() + Math.max(0, expiresInSeconds - 10) * 1000;
  },
  get(): string | null {
    if (!accessToken || Date.now() >= expiresAt) {
      accessToken = null;
      expiresAt = 0;
      return null;
    }
    return accessToken;
  },
  clear(): void {
    accessToken = null;
    expiresAt = 0;
  },
  isAuthenticated(): boolean {
    return this.get() !== null;
  },
};
