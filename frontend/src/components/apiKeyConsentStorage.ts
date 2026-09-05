import {
  readStorageFlag,
  removeStorage,
  writeStorageFlag,
} from "../utils/storage";

const CONSENT_STORAGE_KEY = "novelai_api_key_consent";

export function hasApiKeyConsent(): boolean {
  return readStorageFlag("local", CONSENT_STORAGE_KEY);
}

export function saveApiKeyConsent(): void {
  if (!writeStorageFlag("local", CONSENT_STORAGE_KEY, true)) {
    console.error("Failed to save API key consent");
  }
}

export function clearApiKeyConsent(): void {
  removeStorage("local", CONSENT_STORAGE_KEY);
}
