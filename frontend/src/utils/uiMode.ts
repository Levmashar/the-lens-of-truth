/** Production builds use the public interface; release qualification stays on the server. */
export function showDevelopmentUi(): boolean {
  return import.meta.env.DEV && import.meta.env.VITE_SHOW_DEVELOPMENT_UI !== "false";
}
