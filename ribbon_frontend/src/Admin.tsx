import { useEffect, useState, type FormEvent } from "react";
import { api, post, type Overview, type Template } from "./api";
import { Icon, Modal } from "./App";

const modeNames: Record<string, string> = {
  grid: "整齐平铺",
  stagger: "错位平铺",
  scatter: "随机散点",
  single: "单排重复",
  ends: "两端主图",
  panels: "分区拼接",
};
export default function Admin({
  onClose,
  onChanged,
}: {
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const [tab, setTab] = useState<"tasks" | "templates" | "output">("tasks"),
    [data, setData] = useState<Overview | null>(null),
    [error, setError] = useState(""),
    [info, setInfo] = useState(""),
    [busy, setBusy] = useState(false);
  const [templateId, setTemplateId] = useState(""),
    [templateName, setTemplateName] = useState(""),
    [mode, setMode] = useState("grid"),
    [enabled, setEnabled] = useState(true),
    [rules, setRules] = useState("{}");
  const [profileName, setProfileName] = useState("演示输出"),
    [width, setWidth] = useState(1800),
    [height, setHeight] = useState(300),
    [dpi, setDpi] = useState(150),
    [demo, setDemo] = useState(true);
  async function load() {
    try {
      setData(await api<Overview>("/admin/overview"));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }
  useEffect(() => {
    void load();
  }, []);
  function editTemplate(t: Template) {
    setTemplateId(t.id);
    setTemplateName(t.name);
    setMode(t.mode);
    setEnabled(t.enabled);
    setRules(JSON.stringify(t.rules, null, 2));
    setInfo("保存将建立新的配置版本，历史作品不受影响。");
  }
  async function saveTemplate(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const parsed = JSON.parse(rules);
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object")
        throw new Error("模板规则必须为 JSON 对象。");
      await post("/admin/templates", {
        ...(templateId ? { id: templateId } : {}),
        name: templateName,
        mode,
        enabled,
        rules: parsed,
      });
      await Promise.all([load(), onChanged()]);
      setInfo("模板新版本已保存，样式图已同步。");
      setTemplateId("");
      setTemplateName("");
      setRules("{}");
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (width * height > 40000000)
        throw new Error("总像素不可超过 4000 万。");
      await post("/admin/output-profiles", {
        name: profileName,
        width,
        height,
        dpi,
        format: "PNG",
        is_demo: demo,
      });
      await Promise.all([load(), onChanged()]);
      setInfo("新输出配置已启用。已保存的历史版本及其下载文件保持不变。");
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="内部管理" onClose={onClose} wide>
      <div className="admin-tabs">
        {(
          [
            ["tasks", "任务查询"],
            ["templates", "排版模式"],
            ["output", "输出配置"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            className={tab === key ? "active" : ""}
            onClick={() => {
              setTab(key);
              setError("");
              setInfo("");
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {info && (
        <div className="notice success" role="status">
          {info}
        </div>
      )}
      {tab === "tasks" && (
        <>
          <div className="admin-intro">
            <p>查询后台任务、执行阶段与失败原因。</p>
            <button className="secondary small" onClick={() => void load()}>
              刷新任务
            </button>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>任务</th>
                  <th>状态 / 阶段</th>
                  <th>提供商</th>
                  <th>尝试</th>
                  <th>结果 / 错误</th>
                </tr>
              </thead>
              <tbody>
                {data?.jobs.map((j) => (
                  <tr key={j.id}>
                    <td>
                      <strong>{j.kind}</strong>
                      <small title={j.id}>{j.id.slice(0, 12)}…</small>
                    </td>
                    <td>
                      <span className={`job-status ${j.status.toLowerCase()}`}>
                        {j.status}
                      </span>
                      <small>{j.phase}</small>
                    </td>
                    <td>{j.provider}</td>
                    <td>{j.attempt}</td>
                    <td>
                      {j.error ||
                        j.result_version_id?.slice(0, 12) ||
                        j.result_asset_id?.slice(0, 12) ||
                        "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data?.jobs.length && (
              <div className="empty-library">暂无后台任务</div>
            )}
          </div>
          <p className="microcopy">
            素材维护：在工作台素材库中上传或移除；勾选“共享素材”后可供所有账号使用。
          </p>
        </>
      )}
      {tab === "templates" && (
        <div className="admin-columns">
          <div className="admin-existing">
            <h3>已有模式</h3>
            {data?.templates.map((t) => (
              <button
                key={`${t.id}-${t.version}`}
                className={`admin-template ${templateId === t.id ? "selected" : ""}`}
                onClick={() => editTemplate(t)}
              >
                <img src={t.thumbnail_url} alt={t.name} />
                <div>
                  <strong>{t.name}</strong>
                  <small>
                    版本 {t.version} · {t.enabled ? "已启用" : "已停用"}
                  </small>
                </div>
                <Icon name="arrow" size={15} />
              </button>
            ))}
          </div>
          <form onSubmit={saveTemplate} className="admin-form">
            <h3>{templateId ? "创建模式新版本" : "新增排版模式"}</h3>
            <label>
              模式名称
              <input
                value={templateName}
                onChange={(e) => setTemplateName(e.target.value)}
                maxLength={60}
                required
              />
            </label>
            <label>
              排版规则类型
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                {Object.entries(modeNames).map(([k, n]) => (
                  <option key={k} value={k}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <label>
              规则配置（JSON）
              <textarea
                className="code-input"
                value={rules}
                onChange={(e) => setRules(e.target.value)}
                rows={5}
              />
            </label>
            <small>
              支持
              rows（1–4）、step_ratio（0.2–2）、motif_ratio（0.05–0.8）；服务端会校验规则。
            </small>
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              启用此模式
            </label>
            <button className="primary" disabled={busy}>
              {busy ? "保存中…" : "保存新版本"}
            </button>
            {templateId && (
              <button
                type="button"
                className="text-button"
                onClick={() => {
                  setTemplateId("");
                  setTemplateName("");
                  setRules("{}");
                  setEnabled(true);
                }}
              >
                改为新增模式
              </button>
            )}
          </form>
        </div>
      )}
      {tab === "output" && (
        <div className="admin-columns">
          <div className="admin-existing">
            <h3>配置版本</h3>
            <p className="microcopy">
              固定输出规格只在内部维护。每个作品版本会保存使用的配置快照。
            </p>
            {data?.output_profiles.map((p) => (
              <div className="profile-item" key={`${p.id}-${p.version}`}>
                <strong>
                  {p.name}
                  <span className="tiny-pill">V{p.version}</span>
                </strong>
                <small>
                  {p.width} × {p.height} px · {p.dpi} DPI · PNG
                </small>
                <span>
                  {p.is_demo
                    ? "演示配置，未完成业务验收"
                    : "正式配置标记（仍需接收软件验收）"}
                </span>
              </div>
            ))}
          </div>
          <form className="admin-form" onSubmit={saveProfile}>
            <h3>启用新的输出配置</h3>
            <label>
              配置名称
              <input
                value={profileName}
                onChange={(e) => setProfileName(e.target.value)}
                required
                maxLength={60}
              />
            </label>
            <div className="form-two">
              <label>
                宽度（px）
                <input
                  type="number"
                  min={64}
                  max={16000}
                  value={width}
                  onChange={(e) => setWidth(Number(e.target.value))}
                  required
                />
              </label>
              <label>
                高度（px）
                <input
                  type="number"
                  min={64}
                  max={5000}
                  value={height}
                  onChange={(e) => setHeight(Number(e.target.value))}
                  required
                />
              </label>
            </div>
            <label>
              DPI
              <input
                type="number"
                min={72}
                max={1200}
                value={dpi}
                onChange={(e) => setDpi(Number(e.target.value))}
                required
              />
            </label>
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={demo}
                onChange={(e) => setDemo(e.target.checked)}
              />
              演示配置
            </label>
            <p className="microcopy">
              当前支持
              PNG。正式数值以公司现用文件为准；取消演示标记不代表业务输出已经验收。
            </p>
            <button className="primary" disabled={busy}>
              {busy ? "保存中…" : "保存并启用新版本"}
            </button>
          </form>
        </div>
      )}
    </Modal>
  );
}
