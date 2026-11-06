import { useEffect, useRef, useState, type CSSProperties } from "react";
import { api, ApiError, isDirectLayoutReference } from "./api";

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
  mode_notes?: Record<string, {look_for: string; difference: string; fit: "direct" | "partial"}>;
};

export type LayoutExamplesCatalog = {
  modes: {
    mode: string;
    name: string;
    summary: string;
    note: string;
    example_ids: string[];
    demo_variants?: {id:string; title:string; image_url:string; description:string}[];
  }[];
  examples: LayoutExample[];
  source_name: string;
  note: string;
};

function DemoImage({url, title}: {url:string; title:string}) {
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  // Public demonstrations are code-generated, never employee assets or company
  // images. Permit only the versioned local preview directory.
  const safe = /^\/static\/ribbon\/layout-v3\/[a-z]+(?:_[a-z]+)*(?:-\d+)?\.webp(?:\?v=[a-z0-9]+)?$/.test(url);
  useEffect(()=>{setFailed(false);setAttempt(0);},[url]);
  if (!safe || failed) return <div className="layout-example-unavailable"><p>程序示例暂未加载。</p>{safe && <button className="secondary small" onClick={()=>{setFailed(false);setAttempt(n=>n+1);}}>重试示例</button>}</div>;
  return <img key={`${url}-${attempt}`} src={url} alt={title} loading="lazy" decoding="async" onError={()=>setFailed(true)} />;
}

type Props = {
  mode: string | null;
  cache: { current: LayoutExamplesCatalog | null };
  onUnauthorized: () => void;
  onViewAll: () => void;
  referenceMode?: string;
  legacyLayout?: boolean;
  onChooseReference?: (example: LayoutExample) => void;
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

export default function LayoutExamples({ mode, cache, onUnauthorized, onViewAll, referenceMode, onChooseReference, legacyLayout = false }: Props) {
  const [catalog, setCatalog] = useState<LayoutExamplesCatalog | null>(() => cache.current);
  const [loading, setLoading] = useState(!cache.current);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const authFailure = useRef(onUnauthorized);
  authFailure.current = onUnauthorized;
  const list = useRef<HTMLDivElement>(null);
  const [caseIndex, setCaseIndex] = useState(0);
  const [filterMode, setFilterMode] = useState("");
  const [exampleView, setExampleView] = useState<"company" | "demo">("company");

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
    setCaseIndex(0);
    setFilterMode("");
    setExampleView("company");
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

  const shownMode = mode || filterMode;
  const currentMode = catalog.modes.find((item) => item.mode === shownMode);
  // Keep the explicitly curated order, rather than the unrelated global order.
  const examples = shownMode
    ? (currentMode?.example_ids || []).flatMap(id => catalog.examples.filter(item => item.id === id))
    : catalog.examples;
  const selectedCaseIndex = Math.min(caseIndex, Math.max(0, examples.length-1));
  const visibleExamples = shownMode ? examples.slice(selectedCaseIndex, selectedCaseIndex+1) : examples;

  return (
    <div className="layout-examples" ref={list}>
      <div className="layout-examples-intro">
        {currentMode && <p className="layout-mode-summary">{currentMode.summary}</p>}
        {currentMode?.note && <p className="layout-mode-note">{currentMode.note}</p>}
        {!mode && <p className="layout-mode-summary">{onChooseReference ? "案例可查看，也可明确选择为 AI 首稿参考。只有与当前排法匹配的可用案例可以选中。" : "先看排列方式，再选择适合的排版。案例只说明结构，生成时使用你自己选择的素材。"}</p>}
        {onChooseReference && <p className="layout-reference-help">查看不会发送案例。只有明确选为参考后，生成 AI 首稿时才把所选案例发送给 Seedream。</p>}
        {mode && !currentMode && <p>当前排版暂无对应的公司案例，可先查看其他排法。</p>}
        <div className="layout-examples-tools">
          {mode && <button type="button" className="secondary" onClick={onViewAll}>查看全部案例</button>}
          {!mode && <label className="case-mode-filter">排版
            <select aria-label="筛选排版案例" value={filterMode} onChange={event => {setFilterMode(event.target.value);setCaseIndex(0);setExampleView("company");}}>
              <option value="">全部</option>
              {catalog.modes.map(guide => <option key={guide.mode} value={guide.mode}>{guide.name}</option>)}
            </select>
          </label>}
          <button type="button" className="text-button" onClick={reload}>重新加载</button>
        </div>
      </div>
      {currentMode?.demo_variants?.length ? <div className="layout-example-kind" role="group" aria-label="参考类型">
        <button className={exampleView==="company"?"selected":""} aria-pressed={exampleView==="company"} onClick={()=>setExampleView("company")}>公司案例（{examples.length}）</button>
        <button className={exampleView==="demo"?"selected":""} aria-pressed={exampleView==="demo"} onClick={()=>setExampleView("demo")}>程序示例（{currentMode.demo_variants.length}）</button>
      </div> : null}
      {exampleView === "demo" && currentMode ? <div className="layout-demos">
        <p className="layout-demo-note">以下用自制素材实际排版，说明素材数量与角色怎样影响结果，不是公司原稿或 AI 生图。</p>
        {legacyLayout && <p className="layout-demo-note">程序示例展示新版排法。当前旧作品继续使用原排版规则，新建作品才会使用新版。</p>}
        {(currentMode.demo_variants || []).map(demo=><figure key={demo.id}><figcaption><strong>{demo.title}</strong><span>{demo.description}</span></figcaption><DemoImage url={demo.image_url} title={demo.title} /></figure>)}
      </div> : <>
      {shownMode && examples.length > 1 && <nav className="layout-case-navigation" aria-label="本排法案例">
        <button className="secondary small" disabled={selectedCaseIndex===0} onClick={()=>setCaseIndex(selectedCaseIndex-1)}>上一例</button>
        <label><span>案例 {selectedCaseIndex+1} / {examples.length}</span>
          <select aria-label="选择案例" value={examples[selectedCaseIndex].id} onChange={event=>setCaseIndex(examples.findIndex(item=>item.id===event.target.value))}>
            {examples.map((example,index)=><option key={example.id} value={example.id}>{index+1}. {example.title}</option>)}
          </select>
        </label>
        <button className="secondary small" disabled={selectedCaseIndex===examples.length-1} onClick={()=>setCaseIndex(selectedCaseIndex+1)}>下一例</button>
      </nav>}
      <div className="layout-examples-list">
        {visibleExamples.map((example) => {
          const modeNote = shownMode ? example.mode_notes?.[shownMode] : undefined;
          return (
          <article className="layout-example" key={example.id}>
            <div className="layout-example-heading">
              <h3>{example.title}</h3>
              <div>
                {example.reference_only && <span className="layout-reference-tag">延展参考</span>}
                {modeNote?.fit === "partial" && <span className="layout-reference-tag">组合参考</span>}
                <span className="layout-example-code">{example.code}</span>
              </div>
            </div>
            <p className="layout-example-description">{example.description}</p>
            {!shownMode && catalog.modes
              .filter((guide) => guide.example_ids.includes(example.id))
              .map((guide) => (
                <p className="layout-mode-note" key={guide.mode}>
                  <strong>{guide.name}：</strong>{guide.note}
                </p>
              ))}
            <ExampleImage example={example} />
            <p className="layout-example-look"><strong>看点：</strong>{modeNote?.look_for || (Array.isArray(example.look_for) ? example.look_for.join("；") : example.look_for)}</p>
            {modeNote?.difference && <p className="layout-example-difference"><strong>与当前排法的区别：</strong>{modeNote.difference}</p>}
            {example.reference_only && <p className="layout-example-reference">当前没有单独的对应排版选项，不会因查看案例自动生成这种效果。</p>}
            {onChooseReference && referenceMode && isDirectLayoutReference(example, referenceMode) && exampleImageUrl(example.image_url) && (
              <button type="button" className="secondary choose-ai-reference" onClick={() => onChooseReference(example)}>用于AI首稿参考</button>
            )}
          </article>
        );})}
      </div>
      {!examples.length && <p className="layout-example-unavailable">暂时没有对应案例，请查看全部案例或稍后重新加载。</p>}
      </>}
      <p className="layout-examples-source">{catalog.source_name} · {catalog.note}</p>
    </div>
  );
}
