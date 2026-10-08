/** The server explicitly authorizes runtime diagnostics; release gates stay on the server. */
export function showDevelopmentUi(backendDebugEnabled = false): boolean {
  return (import.meta.env.DEV || backendDebugEnabled === true)
    && import.meta.env.VITE_SHOW_DEVELOPMENT_UI !== "false";
}
