"use strict";
/* DosyaKit arayüzü — bağımlılıksız düz JavaScript */

const TOKEN = document.querySelector('meta[name="dk-token"]').content;
const $ = (s, el = document) => el.querySelector(s);
const view = $("#view");

const S = {
  tools: [], categories: [], byId: {}, status: null,
  cat: "all", query: "",
  files: [],          // {kind:'u'|'l'|'j', file?, ref?, name, size}
  pending: null,      // ana sayfada araç seçilmeyi bekleyen dosyalar
  job: null, pollTimer: null,
};

// ------------------------------------------------------------------ yardımcılar
async function api(path, opts = {}) {
  opts.headers = Object.assign({ "X-Token": TOKEN }, opts.headers || {});
  const r = await fetch(path, opts);
  let data = null;
  try { data = await r.json(); } catch { /* boş */ }
  if (!r.ok) throw new Error((data && data.error) || `Sunucu hatası (${r.status})`);
  return data;
}
const postJSON = (p, body) => api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
}
const svg = (inner, cls = "") => { const s = h("span", { class: cls }); s.innerHTML = `<svg viewBox="0 0 24 24">${inner}</svg>`; return s.firstChild; };
const ICON = {
  back: '<path d="M15 18l-6-6 6-6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  down: '<path d="M12 4v12m0 0-5-5m5 5 5-5M5 20h14"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M7 7l10 10M17 7L7 17"/>',
  redo: '<path d="M4 12a8 8 0 1 0 2.3-5.7M4 4v4h4"/>',
};

function fmtSize(n) {
  if (n == null) return "";
  const u = ["B", "KB", "MB", "GB"]; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i ? n.toFixed(1) : n) + " " + u[i];
}
const ext = (name) => { const m = /\.[^.]+$/.exec(name || ""); return m ? m[0].toLowerCase() : ""; };
const EXT_COLOR = {
  ".pdf": "#e5322d", ".doc": "#2b579a", ".docx": "#2b579a", ".odt": "#2b579a", ".rtf": "#2b579a",
  ".ppt": "#d24726", ".pptx": "#d24726", ".odp": "#d24726", ".xls": "#217346", ".xlsx": "#217346",
  ".ods": "#217346", ".csv": "#217346", ".jpg": "#f0a30a", ".jpeg": "#f0a30a", ".png": "#f0a30a",
  ".webp": "#f0a30a", ".gif": "#f0a30a", ".bmp": "#f0a30a", ".tif": "#f0a30a", ".tiff": "#f0a30a",
  ".txt": "#607d8b", ".zip": "#795548",
};
const accepts = (t, name) => t.accepts.includes("*") || t.accepts.includes(ext(name));

function toast(msg, ms = 3200) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), ms);
}
function badge(t, big = false, px = 48) {
  // rozet metnini uzunluğuna göre küçült ki kutuya sığsın
  const txt = t.badge || t.title[0];
  const n = [...txt].length;
  const size = big ? 64 : px;
  const fs = (n <= 1 ? 0.46 : n <= 3 ? 0.3 : n <= 5 ? 0.23 : 0.19) * size;
  return h("div", { class: "badge" + (big ? " big" : ""), style: { background: t.color, fontSize: fs.toFixed(1) + "px" } }, txt);
}
function officeMissing(t) { return t.requires === "office" && S.status && !S.status.office.available; }

// ------------------------------------------------------------------ yönlendirme
function go(hash) { if (location.hash === hash) render(); else location.hash = hash; }
window.addEventListener("hashchange", render);
document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-nav]");
  if (a) { e.preventDefault(); stopPoll(); S.files = []; go("#/"); }
});

function render() {
  const m = /^#\/tool\/([\w-]+)/.exec(location.hash);
  if (m && S.byId[m[1]]) return renderTool(S.byId[m[1]]);
  renderHome();
}

// ------------------------------------------------------------------ ana sayfa
function renderHome() {
  stopPoll();
  const pend = S.pending;
  const frag = [];
  if (pend && pend.length) {
    frag.push(h("section", { class: "hero" },
      h("h1", {}, `${pend.length} dosya seçildi`),
      h("p", {}, pend.map(f => f.name).slice(0, 3).join(", ") + (pend.length > 3 ? ` ve ${pend.length - 3} dosya daha` : "") + " — ne yapmak istersiniz?"),
      h("p", { style: { marginTop: "10px" } }, h("button", { class: "link", onclick: () => { S.pending = null; renderHome(); } }, "Seçimi temizle"))));
  } else {
    frag.push(h("section", { class: "hero" },
      h("h1", {}, "Dosyalarınız için tüm araçlar tek yerde"),
      h("p", {}, "PDF, Word, PowerPoint, Excel ve görselleri dönüştürün, birleştirin, düzenleyin — tamamen çevrimdışı.")));
  }
  const chips = h("div", { class: "chips", role: "toolbar" },
    [{ id: "all", title: "Tümü" }, ...S.categories].map(c =>
      h("button", { class: "chip", "aria-pressed": String(S.cat === c.id), onclick: () => { S.cat = c.id; renderHome(); } }, c.title)));
  frag.push(chips);

  const q = S.query.trim().toLocaleLowerCase("tr");
  let list = S.tools.filter(t =>
    (S.cat === "all" || t.category === S.cat) &&
    (!q || (t.title + " " + t.description + " " + t.accepts.join(" ")).toLocaleLowerCase("tr").includes(q)));
  if (pend && pend.length) list = list.filter(t => pend.every(f => accepts(t, f.name)) && (t.mode === "each" || pend.length >= (t.min_files || 1)));

  const wrap = h("div", {});
  if (!list.length) wrap.append(h("p", { class: "empty" }, pend ? "Bu dosyalar için uygun araç yok." : "Aramanızla eşleşen araç yok."));
  for (const c of S.categories) {
    const items = list.filter(t => t.category === c.id);
    if (!items.length) continue;
    if (S.cat === "all") wrap.append(h("h2", { class: "cat-title" }, c.title));
    wrap.append(h("div", { class: "grid" }, items.map(toolCard)));
  }
  frag.push(wrap);
  view.replaceChildren(...frag);
}

function toolCard(t) {
  return h("button", {
    class: "card", onclick: () => {
      if (S.pending) { S.files = S.pending.slice(); S.pending = null; } else S.files = [];
      go("#/tool/" + t.id);
    }
  },
    badge(t), h("h3", {}, t.title), h("p", {}, t.description),
    officeMissing(t) ? h("span", { class: "warn-dot", title: "Microsoft Office veya LibreOffice gerekli" }, "Ofis gerekli") : null);
}

// ------------------------------------------------------------------ araç sayfası
function renderTool(t) {
  stopPoll();
  const input = h("input", { type: "file", multiple: true, hidden: true, accept: t.accepts.includes("*") ? null : t.accepts.join(",") });
  input.addEventListener("change", () => { addFiles(t, [...input.files]); input.value = ""; });
  const pick = () => input.click();

  const head = h("div", { class: "tool-head" },
    h("button", { class: "back", onclick: () => { S.files = []; go("#/"); } }, svg(ICON.back), "Tüm araçlar"),
    badge(t, true), h("h1", {}, t.title), h("p", {}, t.description));

  if (!S.files.length) {
    const drop = h("div", { class: "drop" },
      h("button", { class: "btn primary xl", onclick: pick }, svg(ICON.plus), t.mode === "all" ? "Dosyaları seç" : "Dosya seç"),
      h("p", {}, "veya dosyaları buraya sürükleyip bırakın"),
      h("p", { class: "accepts" }, "Kabul edilen: " + (t.accepts.includes("*") ? "tüm dosyalar" : t.accepts.join(" ").toUpperCase().replaceAll(".", ""))));
    dropZone(drop, (fs) => addFiles(t, fs));
    const kids = [head, drop, input];
    if (officeMissing(t)) kids.splice(1, 0, h("p", { class: "notice", style: { maxWidth: "640px", margin: "0 auto 18px" } },
      "Bu araç için Microsoft Office veya ücretsiz LibreOffice kurulu olmalı. Hiçbiri bulunamadı; LibreOffice'i libreoffice.org adresinden kurup DosyaKit'i yeniden başlatın."));
    view.replaceChildren(...kids);
    return;
  }

  // dosya listesi
  const sortable = t.mode === "all" && S.files.length > 1;
  const ul = h("ul", { class: "flist" });
  S.files.forEach((f, i) => {
    const ok = accepts(t, f.name);
    const li = h("li", { class: "fitem" + (sortable ? " draggable" : "") + (ok ? "" : " bad"), draggable: sortable ? "true" : null, title: ok ? f.name : "Bu araç bu dosya türünü kabul etmiyor" },
      sortable ? h("span", { class: "fnum" }, String(i + 1)) : null,
      h("button", { class: "fdel", title: "Kaldır", onclick: () => { S.files.splice(i, 1); renderTool(t); } }, "×"),
      h("div", { class: "fthumb" }, h("span", { style: { background: EXT_COLOR[ext(f.name)] || "#888" } }, ext(f.name).slice(1).toUpperCase() || "?")),
      h("div", { class: "fname" }, f.name), h("div", { class: "fsize" }, fmtSize(f.size)));
    if (sortable) sortableItem(li, i, t);
    ul.append(li);
  });
  const panel = h("section", { class: "files-panel" },
    h("div", { class: "bar" }, h("h2", {}, `${S.files.length} dosya`),
      h("button", { class: "btn ghost", onclick: pick }, svg(ICON.plus), "Dosya ekle")),
    sortable ? h("p", { class: "hint" }, "Sırayı değiştirmek için dosyaları sürükleyin.") : null,
    ul);
  dropZone(panel, (fs) => addFiles(t, fs));

  // seçenekler
  const form = h("form", { class: "opts", onsubmit: (e) => { e.preventDefault(); start(t, form); } }, h("h2", {}, t.title));
  const exts = new Set(S.files.map(f => ext(f.name)));
  for (const o of t.options) {
    if (o.when_ext && !o.when_ext.some(x => exts.has(x))) continue;
    form.append(optionField(o, exts));
  }
  const bad = S.files.filter(f => !accepts(t, f.name));
  const few = S.files.length < (t.min_files || 1);
  if (bad.length) form.append(h("p", { class: "notice err" }, `${bad.length} dosya bu araçla kullanılamaz; kırmızı işaretlileri kaldırın.`));
  if (few) form.append(h("p", { class: "notice" }, `Bu araç için en az ${t.min_files} dosya ekleyin.`));
  if (officeMissing(t)) form.append(h("p", { class: "notice err" }, "Microsoft Office veya LibreOffice bulunamadı."));
  form.append(h("button", { class: "btn primary", type: "submit", disabled: bad.length || few || null }, actionLabel(t)));

  view.replaceChildren(head, h("div", { class: "work" }, panel, form), input);
}

function actionLabel(t) {
  const m = { merge: "Birleştir", split: "Böl", compress: "Sıkıştır", rotate: "Döndür", protect: "Şifrele", unlock: "Şifreyi kaldır",
    watermark: "Filigran ekle", page_numbers: "Numara ekle", delete_pages: "Sayfaları sil", extract_pages: "Sayfaları çıkar", reorder: "Sırala" };
  return m[t.id] || "Dönüştür";
}

function optionField(o, exts = new Set()) {
  const id = "o_" + o.name;
  let ctrl;
  let def = o.default;
  // hedef biçim seçimlerinde, kaynakla aynı biçimi varsayılan yapma (DOCX → DOCX anlamsız)
  if (o.type === "select" && o.when_ext) {
    const own = o.when_ext.filter(x => exts.has(x));
    if (own.length === 1 && own[0] === def) def = (o.choices.find(c => c.value !== def) || {}).value;
  }
  if (o.type === "select") ctrl = h("select", { name: o.name, id }, o.choices.map(c => h("option", { value: c.value, selected: c.value === def || null }, c.label)));
  else if (o.type === "checkbox") return h("label", { class: "check" }, h("input", { type: "checkbox", name: o.name, checked: o.default || null }), o.label);
  else if (o.type === "number") ctrl = h("input", { type: "number", name: o.name, id, value: o.default, min: o.min, max: o.max, step: o.step || 1 });
  else if (o.type === "color") ctrl = h("input", { type: "color", name: o.name, id, value: o.default });
  else ctrl = h("input", { type: o.type === "password" ? "password" : "text", name: o.name, id, value: o.default || "", placeholder: o.placeholder || null, autocomplete: o.type === "password" ? "new-password" : "off" });
  return h("label", { class: "field", for: id }, h("span", {}, o.label), ctrl, o.help ? h("small", {}, o.help) : null);
}

function collectOptions(t, form) {
  const out = {};
  for (const o of t.options) {
    const el = form.elements[o.name];
    if (!el) continue;
    out[o.name] = o.type === "checkbox" ? el.checked : o.type === "number" ? (el.value === "" ? null : Number(el.value)) : el.value;
  }
  return out;
}

function addFiles(t, list) {
  const items = list.map(f => ({ kind: "u", file: f, name: f.name, size: f.size }));
  S.files.push(...items);
  if (t) renderTool(t); else { S.pending = S.files.slice(); S.files = []; renderHome(); }
}

function dropZone(el, onFiles) {
  el.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); el.classList.add("over"); } });
  el.addEventListener("dragleave", (e) => { if (!el.contains(e.relatedTarget)) el.classList.remove("over"); });
  el.addEventListener("drop", (e) => {
    if (!e.dataTransfer.files.length) return;
    e.preventDefault(); e.stopPropagation(); el.classList.remove("over"); onFiles([...e.dataTransfer.files]);
  });
}
// sayfanın herhangi bir yerine bırakılan dosyalar
document.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); });
document.addEventListener("drop", (e) => {
  if (!e.dataTransfer.files.length) return;
  e.preventDefault();
  const m = /^#\/tool\/([\w-]+)/.exec(location.hash);
  const t = m && S.byId[m[1]];
  if (t && !S.job) addFiles(t, [...e.dataTransfer.files]);
  else if (!m) { S.pending = [...(S.pending || []), ...[...e.dataTransfer.files].map(f => ({ kind: "u", file: f, name: f.name, size: f.size }))]; renderHome(); }
});

let dragIdx = null;
function sortableItem(li, i, t) {
  li.addEventListener("dragstart", (e) => { dragIdx = i; li.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", String(i)); });
  li.addEventListener("dragend", () => { li.classList.remove("dragging"); dragIdx = null; });
  li.addEventListener("dragover", (e) => { if (dragIdx !== null) { e.preventDefault(); e.stopPropagation(); li.classList.add("drop-target"); } });
  li.addEventListener("dragleave", () => li.classList.remove("drop-target"));
  li.addEventListener("drop", (e) => {
    if (dragIdx === null) return;
    e.preventDefault(); e.stopPropagation();
    const [moved] = S.files.splice(dragIdx, 1); S.files.splice(i, 0, moved); dragIdx = null; renderTool(t);
  });
}

// ------------------------------------------------------------------ çalıştırma
async function start(t, form) {
  const fd = new FormData();
  fd.append("tool", t.id);
  fd.append("options", JSON.stringify(collectOptions(t, form)));
  const order = [];
  let up = 0;
  for (const f of S.files) {
    if (f.kind === "u") { fd.append("files", f.file, f.name); order.push("u:" + up++); }
    else order.push((f.kind === "l" ? "l:" : "j:") + f.ref);
  }
  fd.append("order", JSON.stringify(order));

  renderProgress(t, 0, up ? "Dosyalar hazırlanıyor…" : "Başlıyor…");
  try {
    const r = await api("/api/run", { method: "POST", body: fd });
    S.job = r.job;
    poll(t);
  } catch (e) {
    toast(e.message, 5000);
    renderTool(t);
  }
}

function renderProgress(t, p, msg) {
  let box = $("#prog");
  if (!box) {
    view.replaceChildren(h("section", { class: "status", id: "prog" },
      badge(t, true), h("h1", { style: { marginTop: "14px" } }, `${t.title} işleniyor…`),
      h("p", { class: "sub" }, "Lütfen bekleyin; büyük dosyalar biraz sürebilir."),
      h("div", { class: "progress indet" }, h("div", {})), h("p", { class: "msg" }, msg)));
    box = $("#prog");
  }
  const bar = $(".progress", box);
  if (p > 0.02) { bar.classList.remove("indet"); bar.firstChild.style.width = Math.round(p * 100) + "%"; }
  $(".msg", box).textContent = msg || "";
}

function stopPoll() { clearTimeout(S.pollTimer); S.pollTimer = null; S.job = null; }

async function poll(t) {
  if (!S.job) return;
  try {
    const j = await api("/api/jobs/" + S.job);
    if (j.status === "running") {
      renderProgress(t, j.progress, j.message);
      S.pollTimer = setTimeout(() => poll(t), 400);
    } else {
      renderResult(t, j);
    }
  } catch (e) {
    S.pollTimer = setTimeout(() => poll(t), 1000);
  }
}

function renderResult(t, j) {
  S.job = null;
  S.files = [];
  const ok = j.status === "done";
  const q = "?t=" + encodeURIComponent(TOKEN);
  const els = [];
  els.push(h("div", { class: "done-icon" + (ok ? "" : " fail") }, svg(ok ? ICON.check : ICON.x)));
  els.push(h("h1", {}, ok ? (j.errors.length ? "Kısmen tamamlandı" : "İşlem tamamlandı") : "İşlem başarısız"));
  if (ok) els.push(h("p", { class: "sub" }, `${j.results.length} dosya hazır · ${j.elapsed ?? ""} sn` + (j.saved_to ? ` · kopyası çıktı klasörüne kaydedildi` : "")));

  if (ok) {
    const main = j.results.length === 1
      ? h("a", { class: "btn primary xl", href: `/api/jobs/${j.id}/file/0${q}` }, svg(ICON.down), "İndir")
      : h("a", { class: "btn primary xl", href: `/api/jobs/${j.id}/zip${q}` }, svg(ICON.down), "Tümünü indir (ZIP)");
    els.push(main);
    els.push(h("ul", { class: "results" }, j.results.map((r, i) =>
      h("li", {}, h("span", { class: "n" }, r.name), h("span", { class: "s" }, fmtSize(r.size)),
        h("a", { href: `/api/jobs/${j.id}/file/${i}${q}` }, "İndir")))));
  }
  const notes = h("div", { class: "notes" },
    j.errors.map(e => h("p", { class: "notice err" }, e)), j.notes.map(n => h("p", { class: "notice" }, n)));
  els.push(notes);
  els.push(h("div", { class: "row-actions" },
    ok ? h("button", { class: "btn ghost", onclick: () => postJSON("/api/open", { what: "job:" + j.id }).catch(e => toast(e.message)) }, svg(ICON.folder), "Klasörü aç") : null,
    h("button", { class: "btn ghost", onclick: () => { S.files = []; renderTool(t); } }, svg(ICON.redo), ok ? "Yeni dosya" : "Tekrar dene"),
    h("button", { class: "btn ghost", "data-nav": "home" }, "Tüm araçlar")));

  // sonucu başka bir araçla işle
  if (ok) {
    const resFiles = j.results.map((r, i) => ({ kind: "j", ref: `${j.id}:${i}`, name: r.name, size: r.size }));
    const next = S.tools.filter(x => x.id !== t.id && resFiles.every(f => accepts(x, f.name)) &&
      (x.mode === "each" || resFiles.length >= (x.min_files || 1))).slice(0, 8);
    if (next.length) els.push(h("div", { class: "chain" }, h("h3", {}, "Sonucu başka bir araçla işleyin"),
      h("div", { class: "mini" }, next.map(x => h("button", { onclick: () => { S.files = resFiles.slice(); go("#/tool/" + x.id); } }, badge(x, false, 28), x.title)))));
  }
  view.replaceChildren(h("section", { class: "status" }, ...els));
}

// ------------------------------------------------------------------ üst çubuk
$("#search").addEventListener("input", (e) => {
  S.query = e.target.value;
  if (location.hash.startsWith("#/tool/")) { S.files = []; location.hash = "#/"; } else renderHome();
});
$("#btn-output").addEventListener("click", () => postJSON("/api/open", { what: "output" }).catch(e => toast(e.message)));
$("#btn-quit").addEventListener("click", async () => {
  if (!confirm("DosyaKit kapatılsın mı? Tekrar açmak için masaüstü kısayolunu kullanın.")) return;
  try { await postJSON("/api/shutdown", {}); } catch { /* kapanıyor */ }
  stopPoll();
  view.replaceChildren(h("section", { class: "bye" }, h("h1", {}, "DosyaKit kapatıldı"), h("p", { class: "sub" }, "Bu sekmeyi kapatabilirsiniz.")));
});

const dlg = $("#settings");
$("#btn-settings").addEventListener("click", async () => {
  S.status = await api("/api/status");
  const s = S.status.settings, f = dlg.querySelector("form");
  f.output_dir.value = s.output_dir; f.save_copy.checked = s.save_copy;
  f.office_engine.value = s.office_engine; f.libreoffice_path.value = s.libreoffice_path || "";
  const o = S.status.office, ms = o.msoffice;
  const row = (label, okv, detail) => h("div", {}, `${label}: `, h("span", { class: okv ? "ok" : "no" }, okv ? "bulundu" : "yok"), detail ? ` (${detail})` : "");
  $("#engines").replaceChildren(
    row("Microsoft Word", ms.word), row("Microsoft PowerPoint", ms.powerpoint), row("Microsoft Excel", ms.excel),
    row("LibreOffice", !!o.libreoffice, o.libreoffice || ""));
  dlg.showModal();
});
dlg.addEventListener("close", async () => {
  if (dlg.returnValue !== "save") return;
  const f = dlg.querySelector("form");
  try {
    await postJSON("/api/settings", { output_dir: f.output_dir.value.trim(), save_copy: f.save_copy.checked,
      office_engine: f.office_engine.value, libreoffice_path: f.libreoffice_path.value.trim() });
    S.status = await api("/api/status");
    toast("Ayarlar kaydedildi");
    render();
  } catch (e) { toast(e.message); }
});
dlg.querySelectorAll("[data-open]").forEach(b => b.addEventListener("click", () => postJSON("/api/open", { what: b.dataset.open }).catch(e => toast(e.message))));

// ------------------------------------------------------------------ başlangıç
(async function init() {
  try {
    const [tl, st] = await Promise.all([api("/api/tools"), api("/api/status")]);
    S.tools = tl.tools; S.categories = tl.categories; S.status = st;
    for (const t of S.tools) S.byId[t.id] = t;
    if (tl.load_errors && tl.load_errors.length) {
      console.warn("Yüklenemeyen araçlar:", tl.load_errors);
      toast(`${tl.load_errors.length} araç yüklenemedi (ayrıntı: kayıt dosyası).`, 6000);
    }
    const pid = new URLSearchParams(location.search).get("preload");
    if (pid) {
      try {
        const p = await api("/api/preload/" + pid);
        S.pending = p.files.map(f => ({ kind: "l", ref: f.ref, name: f.name, size: f.size }));
      } catch { /* süresi dolmuş */ }
      history.replaceState(null, "", "/" + location.hash);
      if (S.pending && S.pending.length) location.hash = "#/";
    }
    render();
  } catch (e) {
    view.replaceChildren(h("p", { class: "empty" }, "DosyaKit'e bağlanılamadı: " + e.message));
  }
})();
