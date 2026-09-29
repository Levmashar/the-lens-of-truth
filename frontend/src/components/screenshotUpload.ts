import { append, element } from "../utils/dom";
import { fileSize } from "../utils/format";

const allowed = ["image/png", "image/jpeg", "image/webp"];
const maxBytes = 10 * 1024 * 1024;

export function createScreenshotUpload(onChange: () => void): {
  node: HTMLElement; getFile: () => File | null; dispose: () => void;
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

  function select(candidate: File | null): void {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    file = null;
    image.removeAttribute("src");
    preview.hidden = true;
    error.hidden = true;
    if (candidate) {
      if (!allowed.includes(candidate.type)) {
        error.textContent = "Choose a PNG, JPEG, or WebP screenshot.";
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
  input.addEventListener("change", () => select(input.files?.[0] ?? null));
  remove.addEventListener("click", () => { input.value = ""; select(null); });
  zone.addEventListener("dragover", (event) => { event.preventDefault(); zone.classList.add("is-dragging"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("is-dragging"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragging");
    select(event.dataTransfer?.files[0] ?? null);
  });
  append(actions, replace, remove);
  append(preview, image, detail, actions);
  append(zone, prompt, hint, input, preview);
  append(group, label, zone, error);
  return { node: group, getFile: () => file, dispose: () => { if (previewUrl) URL.revokeObjectURL(previewUrl); } };
}
