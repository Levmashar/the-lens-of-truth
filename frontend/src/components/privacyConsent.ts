import { PRIVACY_NOTICE_VERSION } from "../api/analyses";
import { append, element } from "../utils/dom";

export function createPrivacyConsent(onChange: () => void): { node: HTMLElement; input: HTMLInputElement } {
  const label = element("label", "consent-row");
  const input = element("input");
  input.type = "checkbox";
  input.name = "consent";
  input.addEventListener("change", onChange);
  const text = element("span", "consent-copy",
    "I understand this content will be processed for verification. Uploaded images are temporarily retained under the privacy notice; I will not include unnecessary personal information.");
  const version = element("small", "consent-version", `Privacy notice version ${PRIVACY_NOTICE_VERSION}`);
  text.append(version);
  append(label, input, text);
  return { node: label, input };
}
