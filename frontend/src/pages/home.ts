import { startAnalysis, uploadScreenshot } from "../api/analyses";
import { ApiError, errorMessage } from "../api/errors";
import { createClaimInput } from "../components/claimInput";
import { createPrivacyConsent } from "../components/privacyConsent";
import { createScreenshotUpload } from "../components/screenshotUpload";
import { append, clear, element } from "../utils/dom";
import { SubmissionAttempt } from "../utils/idempotency";
import { navigate } from "../utils/routing";

type Mode = "text" | "screenshot";
const example = "Daily sunscreen use reduces invasive melanoma risk.";

export function createHomePage(): { node: HTMLElement; dispose: () => void } {
  const page = element("div", "home-page");
  const hero = element("section", "hero content-width");
  append(hero,
    element("h1", "hero-title", "Heard a health claim?\nLet's check it."),
    element("p", "hero-copy", "See what the research says, with sources you can explore."),
  );

  const form = element("form", "verification-card");
  form.noValidate = true;
  form.setAttribute("aria-label", "Check a health claim");
  const tabs = element("div", "mode-switch");
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", "Input type");
  const textTab = element("button", "mode-tab", "Write or paste");
  const imageTab = element("button", "mode-tab", "Screenshot");
  textTab.type = imageTab.type = "button";
  textTab.setAttribute("role", "tab");
  imageTab.setAttribute("role", "tab");
  textTab.id = "text-tab";
  imageTab.id = "screenshot-tab";
  const panel = element("div", "input-panel");
  panel.setAttribute("role", "tabpanel");
  panel.id = "input-panel";
  panel.setAttribute("aria-labelledby", textTab.id);
  textTab.setAttribute("aria-controls", panel.id);
  imageTab.setAttribute("aria-controls", panel.id);
  const attempt = new SubmissionAttempt();
  const claim = createClaimInput(onChange);
  const screenshot = createScreenshotUpload(onChange);
  const consent = createPrivacyConsent(updateSubmit);
  const exampleButton = element("button", "text-action", "Try an example");
  exampleButton.type = "button";
  exampleButton.addEventListener("click", () => {
    setMode("text");
    claim.input.value = example;
    claim.input.dispatchEvent(new Event("input", { bubbles: true }));
    claim.input.focus();
  });
  const helper = element("p", "form-helper", "Leave out names and other personal details.");
  const error = element("p", "form-error");
  error.setAttribute("role", "alert");
  error.hidden = true;
  const submit = element("button", "button button-primary", "Check this claim");
  submit.type = "submit";
  const actions = element("div", "form-actions");
  actions.append(submit);
  append(tabs, textTab, imageTab);
  append(form, tabs, panel, exampleButton, helper, consent.node, error, actions);
  const how = element("section", "how-section content-width");
  append(how, element("h2", "section-title", "A clearer answer. A trail of evidence."));
  const steps = [
    ["01", "Find the research", "We identify the claim and look for relevant scientific evidence."],
    ["02", "Check the details", "We compare the findings and check that the sources back them up."],
    ["03", "Explain the answer", "You get a clear result, its limits, and the original sources."],
  ];
  const grid = element("div", "method-grid");
  for (const [number, title, copy] of steps) {
    const step = element("article", "method-step");
    append(step, element("span", "method-number", number), element("h3", "method-title", title), element("p", "method-copy", copy));
    grid.append(step);
  }
  how.append(grid);
  page.append(hero, form, how);

  let mode: Mode = "text";
  let submitting = false;
  let disposed = false;
  let requestController: AbortController | null = null;

  function updateSubmit(): void {
    submit.disabled = submitting || !consent.input.checked || (mode === "text" ? !claim.input.value.trim() : !screenshot.getFile());
  }
  function onChange(): void { attempt.reset(); error.hidden = true; updateSubmit(); }
  function setMode(next: Mode, initial = false): void {
    mode = next;
    if (!initial) attempt.reset();
    clear(panel);
    panel.append(next === "text" ? claim.node : screenshot.node);
    panel.setAttribute("aria-labelledby", next === "text" ? textTab.id : imageTab.id);
    textTab.setAttribute("aria-selected", String(next === "text"));
    imageTab.setAttribute("aria-selected", String(next === "screenshot"));
    textTab.tabIndex = next === "text" ? 0 : -1;
    imageTab.tabIndex = next === "screenshot" ? 0 : -1;
    error.hidden = true;
    updateSubmit();
  }
  textTab.addEventListener("click", () => setMode("text"));
  imageTab.addEventListener("click", () => setMode("screenshot"));
  for (const tab of [textTab, imageTab]) tab.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const next = mode === "text" ? "screenshot" : "text";
      setMode(next);
      (next === "text" ? textTab : imageTab).focus();
    }
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (submitting) return;
    if (!consent.input.checked) { error.textContent = "Please acknowledge the privacy notice."; error.hidden = false; return; }
    const text = claim.input.value.trim();
    const file = screenshot.getFile();
    if (mode === "text" && !text || mode === "screenshot" && !file) {
      error.textContent = mode === "text" ? "Enter a health claim first." : "Choose a screenshot first.";
      error.hidden = false;
      return;
    }
    submitting = true;
    submit.textContent = "Starting your check…";
    submit.classList.add("is-loading");
    updateSubmit();
    requestController = new AbortController();
    void (async () => {
      try {
        const key = await attempt.prepare(mode === "text" ? text : file as File);
        if (disposed) return;
        let input;
        if (mode === "text") input = { type: "text" as const, text };
        else {
          if (!file) return;
          let uploadId = attempt.uploadedId;
          if (!uploadId) {
            const upload = await uploadScreenshot(file, requestController?.signal);
            uploadId = upload.upload_id;
            attempt.uploadedId = uploadId;
          }
          input = { type: "screenshot" as const, upload_id: uploadId };
        }
        const started = await startAnalysis(input, key, requestController?.signal);
        if (!disposed) { attempt.reset(); navigate(`/analysis/${started.analysis_id}`); }
      } catch (caught) {
        if (disposed) return;
        error.textContent = errorMessage(caught);
        error.hidden = false;
        if (caught instanceof ApiError && (caught.status === 409 || caught.status === 410)) attempt.reset();
      } finally {
        if (!disposed) { submitting = false; submit.textContent = "Check this claim"; submit.classList.remove("is-loading"); updateSubmit(); }
      }
    })();
  });
  setMode("text", true);
  return { node: page, dispose: () => { disposed = true; requestController?.abort(); screenshot.dispose(); } };
}
