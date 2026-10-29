import { createRoot } from "react-dom/client";
import App from "./App";
import { setRequestToken } from "./api";
import styles from "./styles.css?inline";

export type WorkspaceView = "ribbon" | "ribbon-admin";

// The host owns navigation and authentication; this island owns only ribbon UI.
export function mount(host: HTMLElement, getToken: () => string) {
  const shadow = host.shadowRoot || host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = styles;
  const container = document.createElement("div");
  shadow.replaceChildren(style, container);
  setRequestToken(getToken);
  const root = createRoot(container);
  let active = true;
  let view: WorkspaceView = "ribbon";
  const render = () => root.render(<App active={active} view={view} />);
  render();
  return {
    setView(next: WorkspaceView, isActive = true) {
      active = isActive;
      view = next;
      render();
    },
    unmount() { root.unmount(); shadow.replaceChildren(); },
  };
}
