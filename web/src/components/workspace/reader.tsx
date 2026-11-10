"use client";
import { useEffect, useState, useRef } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  FileText,
  Layers,
  LoaderCircle,
  Maximize2,
  Search,
  X,
} from "lucide-react";
import {
  type Doc,
  type Hit,
  type Mode,
  url,
  size,
  status,
  request,
  message,
} from "./client";
function highlight(text: string, query: string) {
  const words =
    query.match(/[\p{L}\p{N}]+/gu)?.filter((w) => w.length > 1) || [];
  if (!words.length) return text;
  const matcher = new RegExp(
    "(" + words.sort((a, b) => b.length - a.length).join("|") + ")",
    "gi",
  );
  return text
    .split(matcher)
    .map((t, i) => (i % 2 ? <mark key={i}>{t}</mark> : t));
}
export default function Reader({
  doc: d,
  onBack,
  refresh,
}: {
  doc: Doc;
  onBack: () => void;
  refresh: () => Promise<void>;
}) {
  const [query, setQuery] = useState(""),
    [mode, setMode] = useState<Mode>("hybrid"),
    [searched, setSearched] = useState(""),
    [hits, setHits] = useState<Hit[]>([]),
    [page, setPage] = useState(1),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [notes, setNotes] = useState<string[]>([]),
    [zoom, setZoom] = useState(false);
  const preview = useRef<HTMLDialogElement>(null),
    seq = useRef(0);
  const current = d.pages.includes(page) ? page : d.pages[0] || 1;
  useEffect(() => {
    if (zoom) preview.current?.showModal();
    else preview.current?.close();
  }, [zoom]);
  async function run(term = query, method = mode) {
    if (!term.trim()) return;
    const turn = ++seq.current;
    setLoading(true);
    setError("");
    setNotes([]);
    try {
      const response = await request<{ results: Hit[]; notes: string[] }>(
        url(d.id) + "/search",
        "POST",
        { query: term.trim(), mode: method },
      );
      if (seq.current === turn) {
        setHits(response.results);
        setSearched(term.trim());
        setNotes(response.notes);
        if (response.results[0]) setPage(response.results[0].page);
      }
    } catch (e) {
      if (seq.current === turn) setError(message(e));
    } finally {
      if (seq.current === turn) setLoading(false);
    }
  }
  async function retry() {
    try {
      setError("");
      await request(url(d.id) + "/retry", "POST");
      await refresh();
    } catch (e) {
      setError(message(e));
    }
  }
  function turnPage(delta: number) {
    const next = d.pages[d.pages.indexOf(current) + delta];
    if (next) setPage(next);
  }
  const ready = d.status === "ready";
  const image = url(d.id) + "/pages/" + current;
  const controls = (
    <div className="page-control">
      <button
        className="icon-button"
        disabled={d.pages.indexOf(current) <= 0}
        aria-label="Previous page"
        onClick={() => turnPage(-1)}
      >
        <ChevronLeft size={17} />
      </button>
      <span>
        {current} / {d.total}
      </span>
      <button
        className="icon-button"
        disabled={d.pages.indexOf(current) >= d.pages.length - 1}
        aria-label="Next page"
        onClick={() => turnPage(1)}
      >
        <ChevronRight size={17} />
      </button>
    </div>
  );
  return (
    <section className="reader">
      <button className="back" onClick={onBack}>
        <ArrowLeft size={15} /> Workspace
      </button>
      <div className="reader-title">
        <div className="file-icon big">
          <FileText size={27} />
        </div>
        <div>
          <h1>{d.name}</h1>
          <p>
            {size(d.size)}
            {d.total ? " · " + d.total + " pages" : ""}{" "}
            <span className="dot-sep">/</span> {status(d)}
          </p>
        </div>
      </div>
      {error && (
        <div className="alert" role="alert">
          <CircleAlert size={17} />
          {error}
        </div>
      )}
      {!ready ? (
        <div className="indexing">
          {d.status === "error" ? (
            <CircleAlert size={32} />
          ) : (
            <LoaderCircle className="spin" size={34} />
          )}
          <h2>
            {d.status === "error"
              ? "Couldn’t index this PDF"
              : d.status === "queued"
                ? "Your PDF is in the queue"
                : "Reading your pages"}
          </h2>
          <p>
            {d.error ||
              "Extracting text, running OCR where needed, and preparing page previews."}
          </p>
          {d.status === "error" && (
            <button onClick={retry} className="secondary">
              Retry indexing
            </button>
          )}
        </div>
      ) : (
        <>
          <form
            className="search-form"
            onSubmit={(e) => {
              e.preventDefault();
              void run();
            }}
          >
            <Search size={21} />
            <input
              aria-label="Search this PDF"
              maxLength={500}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search this PDF or ask a question…"
            />
            <div className="mode">
              <select
                aria-label="Search mode"
                value={mode}
                onChange={(e) => {
                  const m = e.target.value as Mode;
                  setMode(m);
                  if (searched && query.trim()) void run(query, m);
                }}
              >
                <option value="hybrid">Hybrid</option>
                <option value="text">Text</option>
                <option value="visual" disabled={!d.visualCount}>
                  Visual
                </option>
              </select>
              <ChevronDown size={13} />
            </div>
            <button className="primary" disabled={loading || !query.trim()}>
              {loading ? (
                <LoaderCircle size={16} className="spin" />
              ) : (
                <Search size={16} />
              )}{" "}
              Search
            </button>
          </form>
          <div className="index-line">
            <span>
              <Check size={14} /> Text indexed
            </span>
            <i />{" "}
            <span>
              {d.visualStatus === "pending" ? (
                <LoaderCircle className="spin" size={13} />
              ) : (
                <Layers size={13} />
              )}{" "}
              Visual index {d.visualCount}/{d.pages.length}
            </span>
            {d.visualStatus === "partial" && (
              <button onClick={retry}>Retry visual indexing</button>
            )}
          </div>
          {d.warning && <p className="notice">{d.warning}</p>}
          <div className="reader-grid">
            <section className="matches">
              <div className="panel-head">
                <h2>{searched ? "Matching pages" : "Find a page"}</h2>
                {searched && <span className="count">{hits.length}</span>}
              </div>
              {notes.map((n) => (
                <p className="notice" key={n}>
                  {n}
                </p>
              ))}
              {loading && (
                <p className="notice" role="status">
                  Searching the document…
                </p>
              )}
              {!searched ? (
                <div className="search-empty">
                  <Search size={27} />
                  <h3>Search this document</h3>
                  <p>
                    Enter a phrase or question to find the most relevant pages.
                  </p>
                  {d.sample && (
                    <div className="suggestions">
                      {[
                        "What is the procurement budget?",
                        "Where are the monitors stored?",
                        "Solar energy by month",
                      ].map((q) => (
                        <button
                          key={q}
                          onClick={() => {
                            setQuery(q);
                            void run(q);
                          }}
                        >
                          {q}
                          <ArrowRight size={13} />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <>
                  <p className="results-for">Results for “{searched}”</p>
                  {!hits.length ? (
                    <p className="notice">
                      No matching pages. Try another phrase.
                    </p>
                  ) : (
                    hits.map((hit, i) => (
                      <button
                        className={
                          "hit" + (current === hit.page ? " selected" : "")
                        }
                        key={hit.page}
                        onClick={() => setPage(hit.page)}
                      >
                        <span className="hit-top">
                          <span className="page-tag">Page {hit.page}</span>
                          <span>#{i + 1}</span>
                        </span>
                        <strong>{hit.heading || "Page " + hit.page}</strong>
                        <p>
                          {highlight(
                            hit.snippet || "Visual match on this page.",
                            searched,
                          )}
                        </p>
                        <small>{hit.signals.join(" · ")}</small>
                      </button>
                    ))
                  )}
                </>
              )}
            </section>
            <section className="preview-panel">
              <div className="panel-head">
                <h2>
                  <BookOpen size={17} /> Page preview
                </h2>
                <div>
                  {controls}
                  <button
                    className="icon-button"
                    title="Expand preview"
                    aria-label="Expand preview"
                    onClick={() => setZoom(true)}
                  >
                    <Maximize2 size={16} />
                  </button>
                </div>
              </div>
              <div className="page-canvas">
                <img
                  key={image}
                  src={image}
                  alt={"Original PDF page " + current}
                />
              </div>
              <PageDetails key={image} address={image + "/details"} />
              <a
                className="preview-download"
                href={image}
                download={"page-" + current + ".png"}
              >
                <ArrowDownToLine size={13} /> Save page image
              </a>
            </section>
          </div>
        </>
      )}
      <dialog
        ref={preview}
        className="wide-dialog"
        onCancel={() => setZoom(false)}
      >
        <div className="panel-head">
          <h2>Page preview</h2>
          <div>
            {controls}
            <button
              aria-label="Close preview"
              className="icon-button"
              onClick={() => setZoom(false)}
            >
              <X size={18} />
            </button>
          </div>
        </div>
        {zoom && <img src={image} alt={"Expanded PDF page " + current} />}
      </dialog>
    </section>
  );
}

type Extracted = {
  method: string;
  confidence: number | null;
  text: string;
  tables: { table_id: string; rows: string[][] }[];
};
function PageDetails({ address }: { address: string }) {
  const [open, setOpen] = useState(false),
    [data, setData] = useState<Extracted | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    if (!open || data) return;
    let live = true;
    request<Extracted>(address)
      .then((values) => {
        if (live) {
          setData(values);
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(message(e));
      });
    return () => {
      live = false;
    };
  }, [open, data, address]);
  return (
    <details
      className="page-details"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>Extracted text &amp; tables</summary>
      {open && (
        <div className="details-body">
          {data ? (
            <>
              <small>
                Extraction: {data.method}
                {data.confidence !== null
                  ? " · OCR confidence " + Math.round(data.confidence) + "%"
                  : ""}
              </small>
              <p>{data.text || "No readable text on this page."}</p>
              {data.tables.map((table, i) => (
                <div className="table-scroll" key={table.table_id}>
                  <table>
                    <caption>Table {i + 1}</caption>
                    <tbody>
                      {table.rows.map((r, j) => (
                        <tr key={j}>
                          {r.map((c, k) => (
                            <td key={k}>{c}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </>
          ) : (
            error || "Loading page content…"
          )}
        </div>
      )}
    </details>
  );
}
