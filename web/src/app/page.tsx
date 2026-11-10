"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ChevronRight,
  CircleAlert,
  CloudUpload,
  FileText,
  FileUp,
  FolderOpen,
  Layers,
  LoaderCircle,
  Plus,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";

import Reader from "@/components/workspace/reader";
import {
  type Doc,
  size,
  status,
  url,
  request,
  message,
} from "@/components/workspace/client";
function upload(file: File, onProgress: (n: number) => void): Promise<Doc> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/workspace-api/documents");
    xhr.responseType = "json";
    xhr.setRequestHeader("Content-Type", "application/pdf");
    xhr.setRequestHeader("X-Filename", encodeURIComponent(file.name));
    xhr.setRequestHeader("X-Folio-Request", "1");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable)
        onProgress(Math.round((100 * e.loaded) / e.total));
    };
    xhr.onerror = () =>
      reject(new Error("Upload interrupted. Check your connection and retry."));
    xhr.onload = () =>
      xhr.status === 202
        ? resolve(xhr.response)
        : reject(
            new Error(xhr.response?.error || "Upload failed. Please retry."),
          );
    xhr.send(file);
  });
}
function Brand() {
  return (
    <span className="brand">
      <img src="/folio.svg" width="33" height="33" alt="" />
      Folio
    </span>
  );
}
export default function Workspace() {
  const [docs, setDocs] = useState<Doc[]>([]),
    [ready, setReady] = useState(false),
    [route, setRoute] = useState("");
  const [error, setError] = useState(""),
    [working, setWorking] = useState(""),
    [progress, setProgress] = useState(0),
    [drag, setDrag] = useState(false),
    [limit, setLimit] = useState(50000000);
  const [remove, setRemove] = useState<Doc | null>(null);
  const input = useRef<HTMLInputElement>(null),
    dialog = useRef<HTMLDialogElement>(null),
    depth = useRef(0),
    busy = useRef(false);
  const refresh = useCallback(async () => {
    const response = await request<{ documents: Doc[]; maxBytes: number }>(
      "/workspace-api/documents",
    );
    setDocs(response.documents);
    setLimit(response.maxBytes);
    setReady(true);
  }, []);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        if (alive) await refresh();
      } catch (e) {
        if (alive) setError(message(e));
      }
      if (alive) timer = setTimeout(poll, document.hidden ? 7000 : 2200);
    }
    void poll();
    const hash = () => {
      setRoute(location.hash.slice(1));
      setError("");
      window.scrollTo(0, 0);
    };
    hash();
    window.addEventListener("hashchange", hash);
    return () => {
      alive = false;
      clearTimeout(timer);
      window.removeEventListener("hashchange", hash);
    };
  }, [refresh]);
  useEffect(() => {
    if (remove) dialog.current?.showModal();
    else dialog.current?.close();
  }, [remove]);
  const selected = docs.find((d) => route === "document/" + d.id);
  function go(where: string) {
    location.hash = where;
  }
  async function add(file?: File, sample = false) {
    if (busy.current || (!file && !sample)) return;
    setError("");
    if (file && (!/\.pdf$/i.test(file.name) || file.size > limit)) {
      setError("Choose a PDF up to " + size(limit) + ".");
      return;
    }
    busy.current = true;
    setWorking(sample ? "Opening sample" : "Uploading PDF");
    setProgress(0);
    try {
      const doc = sample
        ? await request<Doc>("/workspace-api/sample", "POST")
        : await upload(file!, setProgress);
      setDocs((prev) => [doc, ...prev.filter((x) => x.id !== doc.id)]);
      go("document/" + doc.id);
      await refresh();
    } catch (e) {
      setError(message(e));
    } finally {
      busy.current = false;
      setWorking("");
      if (input.current) input.current.value = "";
    }
  }
  function choose() {
    input.current?.click();
  }
  const library = route === "library";
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="top-inner">
          <a href="#workspace" aria-label="Folio home">
            <Brand />
          </a>
          <span className="brand-divider" />
          <nav aria-label="Primary">
            <a href="#workspace" aria-current={!library ? "page" : undefined}>
              <Layers size={16} /> Workspace
            </a>
            <a href="#library" aria-current={library ? "page" : undefined}>
              <FolderOpen size={16} /> Library
            </a>
          </nav>
          <div className="session">
            <i /> Private session
          </div>
        </div>
      </header>
      <main>
        <input
          ref={input}
          type="file"
          className="visually-hidden"
          accept=".pdf,application/pdf"
          tabIndex={-1}
          aria-label="Choose PDF to upload"
          onChange={(e) => void add(e.target.files?.[0])}
        />
        {error && (
          <div className="alert" role="alert">
            <CircleAlert size={17} />
            <span>{error}</span>
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={15} />
            </button>
          </div>
        )}
        {working && (
          <div className="activity" role="status">
            <LoaderCircle className="spin" size={16} />
            {working}
            {!working.includes("sample") && " · " + progress + "%"}
          </div>
        )}
        {selected ? (
          <Reader
            key={selected.id}
            doc={selected}
            onBack={() => go("workspace")}
            refresh={refresh}
          />
        ) : (
          <div className="landing">
            <div className="intro">
              <div className="eyebrow">
                <span className="tiny-line" />
                {library ? "YOUR COLLECTION" : "SEARCH WORKSPACE"}
              </div>
              <h1>
                {library ? "Document library" : "Document search"}
                <span className="blue-period">.</span>
              </h1>
              <p>
                {library
                  ? "Open a PDF to search its contents and read the matching pages."
                  : "Upload a PDF. Search by words, meaning, or visuals. Go straight to the source page."}
              </p>
            </div>
            {!library && (
              <section className="launch-grid" aria-label="Start searching">
                <div
                  className={"drop-area" + (drag ? " dragging" : "")}
                  onDragOver={(e) => e.preventDefault()}
                  onDragEnter={(e) => {
                    e.preventDefault();
                    depth.current++;
                    setDrag(true);
                  }}
                  onDragLeave={(e) => {
                    e.preventDefault();
                    if (--depth.current <= 0) setDrag(false);
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    depth.current = 0;
                    setDrag(false);
                    void add(e.dataTransfer.files[0]);
                  }}
                >
                  <div className="paper-glyph" aria-hidden="true">
                    <div className="mini-paper back-paper" />
                    <div className="mini-paper front-paper">
                      <span />
                      <span />
                      <span />
                    </div>
                    <div className="up-dot">
                      <FileUp size={16} />
                    </div>
                  </div>
                  <h2>{drag ? "Drop your PDF here" : "Upload a document"}</h2>
                  <p>Drag and drop your PDF here, or choose a file.</p>
                  <button
                    className="primary"
                    disabled={!!working || !ready}
                    onClick={choose}
                  >
                    <CloudUpload size={17} /> Choose PDF
                  </button>
                  <small>PDF files up to {size(limit).replace(".0", "")}</small>
                </div>
                <div className="sample-card">
                  <div className="sample-art" aria-hidden="true">
                    <div className="art-grid" />
                    <div className="sheet s3">
                      <img src="/sample/page-3.png" alt="" />
                    </div>
                    <div className="sheet s2">
                      <img src="/sample/page-2.png" alt="" />
                    </div>
                    <div className="sheet s1">
                      <img src="/sample/page-1.png" alt="" />
                    </div>
                  </div>
                  <div className="sample-foot">
                    <div>
                      <div className="sample-kicker">SAMPLE DOCUMENT</div>
                      <h2>Northline Field Report</h2>
                      <span>
                        4 pages <b>·</b> Tables, charts &amp; scans
                      </span>
                    </div>
                    <button
                      className="round"
                      disabled={!!working || !ready}
                      aria-label="Open sample report"
                      title="Open sample report"
                      onClick={() => void add(undefined, true)}
                    >
                      <ArrowRight size={20} />
                    </button>
                  </div>
                </div>
              </section>
            )}
            <section className="library">
              <div className="section-head">
                <h2>
                  {library ? "All documents" : "Recent documents"}{" "}
                  <span className="count">{docs.length}</span>
                </h2>
                {library ? (
                  <button
                    className="primary small"
                    disabled={!!working || !ready}
                    onClick={choose}
                  >
                    <Plus size={16} /> Upload PDF
                  </button>
                ) : (
                  docs.length > 3 && (
                    <a href="#library" className="text-link">
                      View all <ArrowRight size={14} />
                    </a>
                  )
                )}
              </div>
              {docs.length ? (
                <div className="doc-list">
                  {(library ? docs : docs.slice(0, 3)).map((d) => (
                    <div key={d.id} className="doc-row">
                      <a href={"#document/" + d.id}>
                        <span className="file-icon">
                          <FileText size={20} />
                        </span>
                        <div>
                          <strong>{d.name}</strong>
                          <small>
                            {size(d.size)}
                            {d.total ? " · " + d.total + " pages" : ""}
                          </small>
                        </div>
                        <span className={"pill " + d.status}>{status(d)}</span>
                        <ChevronRight size={16} />
                      </a>
                      <button
                        className="icon-button delete"
                        title="Remove document"
                        aria-label={"Remove " + d.name}
                        onClick={() => setRemove(d)}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-library">
                  <span className="file-icon muted">
                    <FolderOpen size={22} />
                  </span>
                  <div>
                    <strong>
                      {ready ? "No documents yet" : "Loading your library…"}
                    </strong>
                    <p>Your uploaded PDFs will appear here.</p>
                  </div>
                </div>
              )}
            </section>
          </div>
        )}
      </main>
      <footer>
        <span>
          <ShieldCheck size={14} /> PDFs are private to this browser session and
          expire after 24 hours.
        </span>
        <span>
          Folio <span className="foot-slash">/</span> Document workspace
        </span>
      </footer>
      <dialog ref={dialog} onCancel={() => setRemove(null)} className="confirm">
        <h2>Remove document?</h2>
        <p>
          {remove?.name} and its indexed pages will be removed from this
          workspace.
        </p>
        <div>
          <button className="secondary" onClick={() => setRemove(null)}>
            Cancel
          </button>
          <button
            className="danger"
            onClick={async () => {
              if (!remove) return;
              try {
                await request(url(remove.id), "DELETE");
                setRemove(null);
                await refresh();
              } catch (e) {
                setRemove(null);
                setError(message(e));
              }
            }}
          >
            Remove PDF
          </button>
        </div>
      </dialog>
    </div>
  );
}
