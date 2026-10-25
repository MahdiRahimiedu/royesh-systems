/** Storage can be unavailable in private/embedded browsers; the active tab can still log in. */
export const session = {
  read(key: string): string | null {
    try {
      return sessionStorage.getItem(key);
    } catch {
      return null;
    }
  },
  write(key: string, token: string): void {
    try {
      sessionStorage.setItem(key, token);
    } catch {}
  },
  remove(key: string): void {
    try {
      sessionStorage.removeItem(key);
    } catch {}
  },
};
