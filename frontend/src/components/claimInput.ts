import { element, append } from "../utils/dom";

export function createClaimInput(onChange: () => void): { node: HTMLElement; input: HTMLTextAreaElement } {
  const wrapper = element("div", "field-group");
  const label = element("label", "field-label", "What would you like to check?");
  label.htmlFor = "claim-text";
  const input = element("textarea", "claim-textarea");
  input.id = "claim-text";
  input.name = "claim-text";
  input.rows = 5;
  input.maxLength = 20_000;
  input.placeholder = "For example: Daily sunscreen use reduces invasive melanoma risk.";
  const count = element("p", "field-hint", "0 / 20,000 characters");
  input.addEventListener("input", () => {
    count.textContent = `${input.value.length.toLocaleString()} / 20,000 characters`;
    onChange();
  });
  append(wrapper, label, input, count);
  return { node: wrapper, input };
}
