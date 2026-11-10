(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const roleClass = (role) => "r-" + (role || "").split("/")[0];

  const ta = $("#text"), btn = $("#go"), out = $("#out"), msg = $("#msg"), count = $("#count");

  ta.addEventListener("input", () => { count.textContent = `${ta.value.length} / 200자`; });
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); run(); } });
  btn.addEventListener("click", run);

  function showMsg(text) { msg.textContent = text; msg.hidden = !text; }

  async function run() {
    const text = ta.value.trim();
    if (!text) { showMsg("문장을 입력해 주세요."); return; }
    showMsg("");
    btn.disabled = true; btn.textContent = "분석 중…";
    try {
      const r = await fetch("/api/analyze", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || `오류 (HTTP ${r.status})`);
      render(data);
    } catch (e) {
      showMsg(e.message);
    } finally {
      btn.disabled = false; btn.textContent = "분석하기";
    }
  }

  // 예문
  fetch("/api/examples").then((r) => r.json()).then((list) => {
    const box = $("#examples");
    list.forEach((ex) => {
      const b = document.createElement("button");
      b.className = "chip"; b.type = "button"; b.textContent = ex.text;
      b.addEventListener("click", () => {
        ta.value = ex.text; count.textContent = `${ex.text.length} / 200자`;
        showMsg(""); render(ex.result);
        out.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      box.appendChild(b);
    });
  }).catch(() => {});

  function render(data) {
    out.innerHTML = "";
    (data.sentences || []).forEach((s) => out.appendChild(renderSentence(s)));
    // SVG는 화면에 붙은 뒤에 위치를 잴 수 있으므로, 열릴 때 그린다
  }

  function renderSentence(s) {
    const node = $("#sentence-tpl").content.firstElementChild.cloneNode(true);
    $(".kind", node).textContent = s.sentence_kind;
    $(".structure", node).textContent = s.structure.filter((x) => x !== "홑문장").join(" + ") || "주어와 서술어의 관계가 한 번 나타나는 문장";

    const E = s.eojeols;
    const box = $(".eojeols", node), detail = $(".detail", node);
    E.forEach((e) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `ej ${roleClass(e.role)}` + (e.estimated ? " est" : "") + (e.role ? "" : " punct");
      b.innerHTML = `<span class="w">${esc(e.text)}</span><span class="r">${esc(e.role)}${e.estimated ? "?" : ""}</span>`;
      b.addEventListener("click", () => {
        box.querySelectorAll(".ej").forEach((x) => x.classList.remove("sel"));
        b.classList.add("sel");
        showDetail(detail, e, E);
      });
      box.appendChild(b);
    });

    const cl = $(".clauses", node);
    s.clauses.forEach((c) => {
      const d = document.createElement("div");
      d.className = "clause";
      const inSpan = new Set(c.span);
      const html = E.filter((e) => e.role).map((e) => inSpan.has(e.idx) ? `<mark>${esc(e.text)}</mark>` : esc(e.text)).join(" ");
      const label = c.group === "안긴문장" ? `${c.type} (안긴문장)` : `${c.type}적으로 이어진 앞 절`;
      d.innerHTML = `<span class="ct">${esc(label)}</span>${html}` + (c.note ? `<div class="muted small">${esc(c.note)}</div>` : "");
      cl.appendChild(d);
    });

    const tb = $(".morph tbody", node);
    E.forEach((e) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${esc(e.text)}</td><td class="mono">${esc(e.tagged)}</td><td>${esc(e.role)}${e.estimated ? " (추정)" : ""}</td>`;
      tb.appendChild(tr);
    });

    const dep = $(".dep", node);
    dep.addEventListener("toggle", () => { if (dep.open) drawDeps($(".dep-inner", node), E); });
    return node;
  }

  function showDetail(detail, e, E) {
    detail.hidden = false;
    detail.className = `detail ${roleClass(e.role)}`;
    const head = e.head == null || e.head < 0 ? "문장 전체의 중심(뿌리)" : `'${E[e.head].text}'에 연결`;
    const morphs = e.morphemes.map((m) => `${m.form}/${m.tag}(${m.tag_name})`).join(" + ");
    detail.innerHTML =
      `<div class="title">${esc(e.text)} → ${esc(e.role)}${e.estimated ? " (추정)" : ""}</div>` +
      `<div class="morphs">${esc(morphs)}</div>` +
      `<div>${esc(e.reason)}</div>` +
      (e.role_note ? `<div class="note">※ ${esc(e.role_note)}</div>` : "") +
      `<div class="note">의존 관계(참고): ${esc(head)}${e.dep_label ? ` · ${esc(e.dep_label)}` : ""}</div>`;
  }

  function drawDeps(inner, E) {
    inner.innerHTML = "";
    const words = E.filter((e) => e.role);
    const row = document.createElement("div");
    row.className = "dep-row";
    const pos = {};
    words.forEach((e) => {
      const w = document.createElement("span");
      w.className = "dw"; w.textContent = e.text; w.dataset.idx = e.idx;
      row.appendChild(w);
    });
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    inner.appendChild(svg); inner.appendChild(row);

    const base = row.getBoundingClientRect();
    row.querySelectorAll(".dw").forEach((w) => {
      const r = w.getBoundingClientRect();
      pos[w.dataset.idx] = r.left - base.left + r.width / 2;
    });
    const arcs = words.filter((e) => e.head != null && e.head >= 0 && pos[e.head] != null);
    const spanLen = (e) => Math.abs(words.findIndex((x) => x.idx === e.head) - words.findIndex((x) => x.idx === e.idx));
    const maxSpan = Math.max(1, ...arcs.map(spanLen));
    const H = 28 + maxSpan * 22;
    svg.setAttribute("width", row.scrollWidth);
    svg.setAttribute("height", H);
    arcs.forEach((e) => {
      const x1 = pos[e.idx], x2 = pos[e.head];
      const h = 18 + spanLen(e) * 22;
      const p = document.createElementNS(svgNS, "path");
      p.setAttribute("d", `M ${x1} ${H} C ${x1} ${H - h}, ${x2} ${H - h}, ${x2} ${H - 2}`);
      const a = document.createElementNS(svgNS, "path");
      a.setAttribute("d", `M ${x2 - 4} ${H - 8} L ${x2} ${H - 1} L ${x2 + 4} ${H - 8}`);
      const t = document.createElementNS(svgNS, "text");
      t.setAttribute("x", (x1 + x2) / 2); t.setAttribute("y", H - h * 0.75 - 2);
      t.setAttribute("text-anchor", "middle");
      t.textContent = e.role.split("/")[0];
      svg.append(p, a, t);
    });
  }
})();
