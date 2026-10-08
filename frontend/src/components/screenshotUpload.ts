import { append, element } from "../utils/dom";
import { fileSize } from "../utils/format";

const allowed = ["image/png", "image/jpeg", "image/webp"];
const maxBytes = 10 * 1024 * 1024;

export function createScreenshotUpload(onChange: () => void): {
  node: HTMLElement; getFile: () => File | null; setDisabled: (value: boolean) => void; dispose: () => void;
} {
  const group = element("div", "field-group");
  const label = element("label", "field-label", "Screenshot");
  label.htmlFor = "screenshot-file";
  const zone = element("div", "upload-zone");
  const prompt = element("p", "upload-prompt", "Drop an image here, or choose a file");
  const hint = element("p", "field-hint", "PNG, JPEG or WebP · up to 10 MB");
  const input = element("input", "file-input");
  input.type = "file";
  input.id = "screenshot-file";
  input.accept = ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp";
  const preview = element("div", "upload-preview");
  preview.hidden = true;
  const image = element("img", "upload-image");
  image.alt = "Selected screenshot preview";
  const detail = element("p", "upload-detail");
  const actions = element("div", "upload-actions");
  const replace = element("button", "button button-secondary", "Replace image");
  replace.type = "button";
  replace.addEventListener("click", () => input.click());
  const remove = element("button", "button button-quiet", "Remove image");
  remove.type = "button";
  const error = element("p", "field-error");
  error.setAttribute("role", "alert");
  error.hidden = true;
  let file: File | null = null;
  let previewUrl: string | null = null;
  let disabled = false;

  function select(candidate: File | null): void {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    file = null;
    image.removeAttribute("src");
    preview.hidden = true;
    error.hidden = true;
    if (candidate) {
      const supported = allowed.includes(candidate.type) || (!candidate.type && /\.(png|jpe?g|webp)$/i.test(candidate.name));
      if (!supported) {
        error.textContent = "Choose a PNG, JPEG, or WebP screenshot.";
        error.hidden = false;
      } else if (candidate.size === 0) {
        error.textContent = "This image file is empty. Choose another screenshot.";
        error.hidden = false;
      } else if (candidate.size > maxBytes) {
        error.textContent = "Choose a screenshot smaller than 10 MB.";
        error.hidden = false;
      } else {
        file = candidate;
        previewUrl = URL.createObjectURL(candidate);
        image.src = previewUrl;
        detail.textContent = `${candidate.name} · ${fileSize(candidate.size)}`;
        preview.hidden = false;
      }
    }
    onChange();
  }
  input.addEventListener("change", () => {
    if (!disabled && input.files?.[0]) select(input.files[0]);
    input.value = ""; // Allow choosing the same file again after a decoding error.
  });
  image.addEventListener("error", () => {
    if (disabled) return;
    select(null);
    error.textContent = "This image couldn't be opened. Choose another screenshot.";
    error.hidden = false;
  });
  remove.addEventListener("click", () => { input.value = ""; select(null); });
  zone.addEventListener("dragover", (event) => { event.preventDefault(); if (!disabled) zone.classList.add("is-dragging"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("is-dragging"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragging");
    if (!disabled) select(event.dataTransfer?.files[0] ?? null);
  });
  append(actions, replace, remove);
  append(preview, image, detail, actions);
  append(zone, prompt, hint, input, preview);
  append(group, label, zone, error);
  return {
    node: group, getFile: () => file,
    setDisabled: (value) => { disabled = value; input.disabled = replace.disabled = remove.disabled = value; },
    dispose: () => { if (previewUrl) URL.revokeObjectURL(previewUrl); },
  };
}
