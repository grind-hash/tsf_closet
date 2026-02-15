const CONSENT_STORAGE_KEY = "novelai_api_key_consent";

export function hasApiKeyConsent(): boolean {
  try {
    const consent = localStorage.getItem(CONSENT_STORAGE_KEY);
    return consent === "true";
  } catch {
    return false;
  }
}

export function saveApiKeyConsent(): void {
  try {
    localStorage.setItem(CONSENT_STORAGE_KEY, "true");
  } catch {
    console.error("Failed to save API key consent");
  }
}

export function clearApiKeyConsent(): void {
  try {
    localStorage.removeItem(CONSENT_STORAGE_KEY);
  } catch {
    console.error("Failed to clear API key consent");
  }
}
