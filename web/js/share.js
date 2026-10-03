// Logika udostępniania linku. Brak dostępu do navigator/document przy imporcie.

export async function shareUrl(url, title, opts = {}) {
  const nav = opts.nav ?? (typeof navigator !== "undefined" ? navigator : {});
  const notify = opts.notify ?? (() => {});
  const promptFn = opts.promptFn ?? globalThis.prompt;
  if (typeof nav.share === "function") {
    try {
      await nav.share({ title, url });
      return "shared";
    } catch (e) {
      if (e?.name === "AbortError") return "aborted";
    }
  }
  if (nav.clipboard && typeof nav.clipboard.writeText === "function") {
    try {
      await nav.clipboard.writeText(url);
      notify("Skopiowano link");
      return "copied";
    } catch {
      /* spadamy do prompt() */
    }
  }
  if (typeof promptFn === "function") promptFn("Skopiuj link:", url);
  return "prompted";
}
