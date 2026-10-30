import { useEffect, useRef, useState, type CSSProperties } from "react";
import { api, ApiError } from "./api";

export type LayoutExample = {
  id: string;
  title: string;
  code: string;
  description: string;
  look_for: string | string[];
  mode_tags: string[];
  reference_only: boolean;
  width: number;
  height: number;
  image_url: string | null;
  available: boolean;
};

export type LayoutExamplesCatalog = {
  modes: {
    mode: string;
    name: string;
    summary: string;
    note: string;
    example_ids: string[];
  }[];
  examples: LayoutExample[];
  source_name: string;
  note: string;
};

type Props = {
  mode: string | null;
  cache: { current: LayoutExamplesCatalog | null };
  onUnauthorized: () => void;
  onViewAll: () => void;
};

// Case images stay behind the host's employee session. Never load a gallery URL
// or a provider URL supplied in place of the configured, authenticated endpoint.
function exampleImageUrl(value: string | null) {
  if (!value?.startsWith("/api/ribbon/layout-examples/")) return null;
  try {
    const url = new URL(value, location.href);
    return url.origin === location.origin && url.pathname.endsWith("/image")
      ? url.href
      : null;
  } catch {
    return null;
  }
}

function ExampleImage({ example }: { example: LayoutExample }) {
  const [zoomed, setZoomed] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const viewport = useRef<HTMLDivElement>(null);
  const url = example.available ? exampleImageUrl(example.image_url) : null;

  useEffect(() => {
    setFailed(false);
    setZoomed(false);
    setAttempt(0);
  }, [example.id, example.image_url, example.available]);

  if (!url || failed) {
    return (
      <div className="layout-example-unavailable" role="status">
        <p>{failed ? "案例图片没有加载成功，排版说明仍可查看。" : "这张案例图暂未加载，排版说明仍可查看。"}</p>
        {url && (
          <button type="button" className="secondary" onClick={() => {
            setFailed(false);
            setAttempt((value) => value + 1);
          }}>重试图片</button>
        )}
      </div>
    );
  }

  return (
    <>
      <div className="layout-example-image-tools">
        <button
          type="button"
          className="text-button"
          aria-pressed={zoomed}
          aria-label={`${zoomed ? "查看整条" : "放大查看"} ${example.code}`}
          onClick={() => {
            setZoomed((value) => !value);
            if (viewport.current) viewport.current.scrollLeft = 0;
          }}
        >{zoomed ? "查看整条" : "放大查看"}</button>
        {zoomed && <span>可左右滚动查看</span>}
      </div>
      <div
        ref={viewport}
        className={`layout-example-viewport${zoomed ? " is-zoomed" : ""}`}
        role="region"
        aria-label={`${example.code} 案例图${zoomed ? "，可左右滚动" : ""}`}
        tabIndex={zoomed ? 0 : -1}
        style={{ "--example-width": `${example.width}px` } as CSSProperties}
      >
        <img
          key={`${example.id}-${example.image_url}-${attempt}`}
          src={url}
          width={example.width}
          height={example.height}
          alt={`${example.title}，图库图号 ${example.code}`}
          loading="lazy"
          decoding="async"
          referrerPolicy="same-origin"
          onError={() => setFailed(true)}
        />
      </div>
    </>
  );
}

export default function LayoutExamples({ mode, cache, onUnauthorized, onViewAll }: Props) {
  const [catalog, setCatalog] = useState<LayoutExamplesCatalog | null>(() => cache.current);
  const [loading, setLoading] = useState(!cache.current);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const authFailure = useRef(onUnauthorized);
  authFailure.current = onUnauthorized;
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (cache.current) {
      setCatalog(cache.current);
      setLoading(false);
      return;
    }
    const abort = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError("");
    api<LayoutExamplesCatalog>("/layout-examples", { signal: abort.signal })
      .then((value) => {
        if (cancelled) return;
        cache.current = value;
        setCatalog(value);
      })
      .catch((reason) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "请稍后重新加载案例。");
        if (reason instanceof ApiError && reason.status === 401) authFailure.current();
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; abort.abort(); };
  }, [cache, attempt]);

  useEffect(() => {
    // Switching the read-only view does not move the employee's workspace or
    // selection. Only bring the new case list back to its own beginning.
    list.current?.closest(".modal")?.scrollTo({ top: 0 });
  }, [mode]);

  function reload() {
    cache.current = null;
    setCatalog(null);
    setAttempt((value) => value + 1);
  }

  if (loading) {
    return <div className="layout-examples-loading" role="status"><span className="spinner" />正在加载排版案例…</div>;
  }
  if (error || !catalog) {
    return <div className="layout-examples-error" role="alert"><p>案例暂时无法打开：{error || "请稍后再试。"}</p><button type="button" className="secondary" onClick={reload}>重新加载案例</button></div>;
  }

  const currentMode = catalog.modes.find((item) => item.mode === mode);
  const examples = mode
    ? catalog.examples.filter((item) => currentMode?.example_ids.includes(item.id))
    : catalog.examples;

  return (
    <div className="layout-examples" ref={list}>
      <div className="layout-examples-intro">
        {currentMode && <p className="layout-mode-summary">{currentMode.summary}</p>}
        {currentMode?.note && <p className="layout-mode-note">{currentMode.note}</p>}
        {!mode && <p className="layout-mode-summary">先看排列方式，再选择适合的排版。案例只说明结构，生成时使用你自己选择的素材。</p>}
        {mode && !currentMode && <p>当前排版暂无对应的公司案例，可先查看其他排法。</p>}
        <div className="layout-examples-tools">
          {mode && <button type="button" className="secondary" onClick={onViewAll}>查看全部案例</button>}
          <button type="button" className="text-button" onClick={reload}>重新加载</button>
        </div>
      </div>
      <div className="layout-examples-list">
        {examples.map((example) => (
          <article className="layout-example" key={example.id}>
            <div className="layout-example-heading">
              <h3>{example.title}</h3>
              <div>
                {example.reference_only && <span className="layout-reference-tag">延展参考</span>}
                <span className="layout-example-code">{example.code}</span>
              </div>
            </div>
            <p className="layout-example-description">{example.description}</p>
            {!mode && catalog.modes
              .filter((guide) => guide.example_ids.includes(example.id))
              .map((guide) => (
                <p className="layout-mode-note" key={guide.mode}>
                  <strong>{guide.name}：</strong>{guide.note}
                </p>
              ))}
            <ExampleImage example={example} />
            <p className="layout-example-look"><strong>看点：</strong>{Array.isArray(example.look_for) ? example.look_for.join("；") : example.look_for}</p>
            {example.reference_only && <p className="layout-example-reference">当前没有单独的对应排版选项，不会因查看案例自动生成这种效果。</p>}
          </article>
        ))}
      </div>
      {!examples.length && <p className="layout-example-unavailable">暂时没有对应案例，请查看全部案例或稍后重新加载。</p>}
      <p className="layout-examples-source">{catalog.source_name} · {catalog.note}</p>
    </div>
  );
}
