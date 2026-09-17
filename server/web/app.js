/* AudioLayers · Servidor — lógica da interface web */
const $ = (sel) => document.querySelector(sel);

const fmtBytes = (n) => {
  if (n == null) return "–";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0, v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(i ? 1 : 0)} ${u[i]}`;
};
const fmtDur = (s) => {
  if (s == null) return "–";
  const m = Math.floor(s / 60), r = Math.round(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
};
const fmtDate = (iso) => {
  if (!iso) return "–";
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const PROC_LABEL = {
  none: "sem processamento", normalize: "normalização", mono: "mono",
  speed: "velocidade", bitrate: "bitrate", convert: "conversão",
};

async function loadStats() {
  try {
    const s = await (await fetch("/api/stats")).json();
    $("#st-total").textContent = s.total_audios;
    $("#st-size").textContent = fmtBytes(s.total_size_bytes);
    $("#st-dur").textContent = fmtDur(s.total_duration_sec);
    const processed = Object.entries(s.processing_counts || {})
      .filter(([k]) => k !== "none").reduce((a, [, v]) => a + v, 0);
    $("#st-proc").textContent = processed;
  } catch { /* ignora */ }
}

async function loadHealth() {
  try {
    const h = await (await fetch("/health")).json();
    const badge = $("#db-badge");
    badge.textContent = `banco: ${h.database}`;
    badge.classList.add("ok");
  } catch {
    $("#db-badge").textContent = "servidor offline";
  }
}

function audioCard(row) {
  const li = document.createElement("li");
  li.className = "audio-item";
  const wfUrl = `/media/${row.path_original ? row.path_original.replace(/audio\.[^.]+$/, "waveform.png") : ""}`;

  li.innerHTML = `
    <div class="cover">
      <img src="${esc(wfUrl)}" alt="waveform" loading="lazy"
           onerror="this.replaceWith(document.createTextNode('🎵'))" />
    </div>
    <div class="audio-main">
      <div class="audio-title" title="${esc(row.original_name)}">${esc(row.original_name)}</div>
      <div class="audio-meta">
        <span class="tag ${row.processing_type !== "none" ? "pink" : ""}">${esc(PROC_LABEL[row.processing_type] || row.processing_type)}</span>
        <span>${fmtDur(row.duration_sec)} · ${fmtBytes(row.size_bytes)}</span>
        <span>${row.sample_rate ?? "–"} Hz · ${row.channels ?? "–"}ch</span>
        <span>${esc(fmtDate(row.created_at))}</span>
      </div>
    </div>
    <div class="audio-side">
      <audio controls preload="none" src="/api/audios/${esc(row.id)}/file?variant=original"></audio>
      ${row.path_processed
        ? `<audio controls preload="none" title="processado" src="/api/audios/${esc(row.id)}/file?variant=processed"></audio>`
        : ""}
      <button class="btn btn-ghost btn-danger" data-del="${esc(row.id)}" title="Mover p/ trash/">🗑</button>
    </div>`;
  return li;
}

async function loadAudios() {
  $("#loading").hidden = false;
  $("#empty").hidden = true;
  try {
    const rows = await (await fetch("/api/audios")).json();
    const list = $("#audio-list");
    list.innerHTML = "";
    $("#loading").hidden = true;
    $("#empty").hidden = rows.length > 0;

    const q = $("#search").value.trim().toLowerCase();
    rows
      .filter((r) => !q || r.original_name.toLowerCase().includes(q))
      .forEach((r) => list.appendChild(audioCard(r)));
  } catch (e) {
    $("#loading").textContent = "Falha ao carregar a lista — servidor respondeu com erro.";
  }
}

async function loadTrash() {
  try {
    const items = await (await fetch("/api/audios/trash")).json();
    const list = $("#trash-list");
    list.innerHTML = "";
    $("#trash-empty").hidden = items.length > 0;
    items.forEach((name) => {
      const li = document.createElement("li");
      li.className = "trash-item";
      li.innerHTML = `<span>📁 ${esc(name)}</span><span>aguardando exclusão</span>`;
      list.appendChild(li);
    });
  } catch { /* ignora */ }
}

document.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("[data-del]");
  if (!btn) return;
  if (!confirm("Mover este áudio para trash/ e remover do banco?")) return;
  await fetch(`/api/audios/${btn.dataset.del}`, { method: "DELETE" });
  loadAudios(); loadTrash(); loadStats();
});

$("#search").addEventListener("input", loadAudios);
$("#btn-refresh").addEventListener("click", () => { loadAudios(); loadTrash(); loadStats(); loadHealth(); });

loadHealth(); loadStats(); loadAudios(); loadTrash();
