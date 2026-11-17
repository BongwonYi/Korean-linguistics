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

    const sf = $(".sfeat", node);
    (s.sentence_features || []).forEach((f) => {
      const b = document.createElement("span");
      b.className = "sf" + (f.estimated ? " est" : "");
      b.textContent = f.value + (f.estimated ? "?" : "");
      b.title = `${f.cat}: ${f.note || ""}`;
      sf.appendChild(b);
    });

    const E = s.eojeols;
    const box = $(".eojeols", node), detail = $(".detail", node);
    const btns = {};
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
      btns[e.idx] = b;
      box.appendChild(b);
    });

    const cl = $(".clauses", node);
    const clauses = s.clauses || [];
    if (clauses.length) {
      // 괄호 표시: 절마다 [ … ]절이름 (바깥 절부터 열고 안쪽 절부터 닫음)
      const shortName = (c) => (c.group === "안긴문장" ? c.type : `${c.type}적 앞 절`);
      const lo = (c) => Math.min(...c.span), hi = (c) => Math.max(...c.span);
      const words = E.filter((e) => e.role).map((e) => {
        const opens = clauses.filter((c) => lo(c) === e.idx).sort((a, b) => hi(b) - hi(a));
        const closes = clauses.filter((c) => hi(c) === e.idx).sort((a, b) => lo(b) - lo(a));
        return opens.map(() => '<span class="br">[</span>').join("") + esc(e.text.replace(/[.,!?]+$/, "")) +
          closes.map((c) => `<span class="br">]</span><sub>${esc(shortName(c))}</sub>`).join("");
      });
      const b = document.createElement("div");
      b.className = "bracket";
      b.innerHTML = words.join(" ");
      cl.appendChild(b);
    }
    clauses.forEach((c) => {
      const d = document.createElement("div");
      d.className = "clause";
      d.style.marginLeft = `${(c.depth || 0) * 16}px`;
      const inSpan = new Set(c.span);
      const html = E.filter((e) => e.role).map((e) => inSpan.has(e.idx) ? `<mark>${esc(e.text)}</mark>` : esc(e.text)).join(" ");
      let label = c.group === "안긴문장" ? `${c.type} (안긴문장)` : `${c.type}적으로 이어진 앞 절`;
      if (c.depth) label = "└ " + label;
      const meaning = c.meaning ? `<span class="cm">${esc(c.meaning)}</span>` : "";
      d.innerHTML = `<span class="ct">${esc(label)}</span>${meaning}${html}` + (c.note ? `<div class="muted small">${esc(c.note)}</div>` : "");
      cl.appendChild(d);
    });

    renderArgs($(".args", node), s.argument_structure || [], E, btns);

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

  // 서술어별 논항 구조: 격틀의 자리마다 채운 어절, 비어 있는 필수 자리(∅), 수의적 부사어
  const caseLabel = (sl) => {
    if (sl.case && sl.case.length) return sl.case.map((c) => (c.startsWith("-") ? c : "~" + c)).join("/");
    return { 주어: "~이/가", 목적어: "~을/를", 보어: "~이/가" }[sl.role] || "";
  };

  function renderArgs(wrap, AS, E, btns) {
    const list = $(".args-list", wrap);
    list.innerHTML = "";
    const preds = [...AS].sort((a, b) => a.main - b.main);
    if (!preds.length) { wrap.hidden = true; return; }
    wrap.hidden = false;
    const select = (idx) => { if (btns[idx]) btns[idx].click(); };

    preds.forEach((a) => {
      const card = document.createElement("div");
      card.className = "pred";
      const words = [E[a.main].text];
      if (a.predicate !== a.main) words.push(E[a.predicate].text);
      const predTxt = words.join(" ").replace(/[.,!?]+$/, "");

      const head = document.createElement("div");
      head.className = "pred-h";
      head.innerHTML =
        `<button type="button" class="pw">${esc(predTxt)}</button>` +
        `<span class="lemma">${esc(a.lemma || "")}</span>` +
        (a.frame_found
          ? `<span class="places">${a.places}자리 서술어</span>`
          : `<span class="places none">격틀 정보 없음</span>`);
      $(".pw", head).addEventListener("click", () => select(a.main));
      card.appendChild(head);

      if (a.frame_found) {
        const slots = document.createElement("div");
        slots.className = "slots";
        const rel = a.relative;
        const gaps = rel && rel.type === "관계" ? rel.gap_candidates || [] : [];
        const headNoun = rel && rel.head_noun != null && rel.head_noun >= 0 ? E[rel.head_noun].text.replace(/[.,!?]+$/, "") : "";
        a.slots.forEach((sl) => {
          const el = document.createElement(sl.filled_by != null ? "button" : "span");
          if (sl.filled_by != null) { el.type = "button"; el.addEventListener("click", () => select(sl.filled_by)); }
          const filled = sl.filled_by != null;
          const isGap = !filled && sl.required && gaps.length === 1 && gaps[0] === sl.role;
          let val;
          if (filled) val = esc(E[sl.filled_by].text.replace(/[.,!?]+$/, ""));
          else if (isGap) val = `↪ ${esc(headNoun)}`;
          else if (sl.required) val = "∅ 생략";
          else val = "—";
          el.className = `slot ${roleClass(sl.role)} ${sl.required ? "req" : "opt"}` +
            (!filled && !isGap ? " empty" : "") + (isGap ? " gap" : "");
          el.innerHTML = `<span class="sr">${esc(sl.role)}${sl.required ? "" : "(수의)"} <span class="cs">${esc(caseLabel(sl))}</span></span>` +
            `<span class="sv">${val}</span>`;
          slots.appendChild(el);
        });
        card.appendChild(slots);

        const notes = [];
        if (rel) {
          if (rel.type === "동격") notes.push(`관형절이 '${headNoun}'의 내용을 나타냄(동격 관형절, 빈자리 없음)`);
          else if (gaps.length > 1) notes.push(`꾸밈을 받는 '${headNoun}'가 ${gaps.join("·")} 자리 중 하나를 채움(관계 관형절)`);
          else if (gaps.length === 1) notes.push(`꾸밈을 받는 '${headNoun}'가 ${gaps[0]} 자리를 채움(관계 관형절)`);
        }
        const adj = (a.adjuncts || []).map((k) => E[k].text.replace(/[.,!?]+$/, ""));
        if (adj.length) notes.push(`수의적 부사어: ${adj.join(", ")}`);
        const extra = (a.unmatched || []).map((k) => E[k].text.replace(/[.,!?]+$/, ""));
        if (extra.length) notes.push(`격틀에 맞는 자리가 없는 성분: ${extra.join(", ")}`);
        if (a.pattern) notes.push(`사전 문형: ${a.pattern}`);
        if (notes.length) {
          const n = document.createElement("div");
          n.className = "pred-n muted small";
          n.innerHTML = notes.map(esc).join("<br>");
          card.appendChild(n);
        }
      }
      renderFeats(card, a.features || []);
      if (a.voice) renderVoice(card, a.voice);
      list.appendChild(card);
    });
  }

  // 사동·피동: 되돌린 주동문·능동문과 논항 변화
  function renderVoice(card, v) {
    const box = document.createElement("div");
    box.className = "voice" + (v.estimated ? " est" : "");
    const pair = v.type === "사동" ? "사동문 ↔ 주동문" : "피동문 ↔ 능동문";
    box.innerHTML =
      `<div class="vh"><b>${esc(pair)}</b> <span class="muted small">${esc(v.form)}${v.estimated ? " · 추정" : ""}</span></div>` +
      `<div class="vc">${esc(v.counterpart_label)}: <b>${esc(v.counterpart)}</b></div>` +
      `<ul>${v.changes.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` +
      (v.base_pattern ? `<div class="muted small">'${esc(v.base_lemma)}'의 사전 문형: ${esc(v.base_pattern)}</div>` : "") +
      (v.note ? `<div class="muted small">${esc(v.note)}</div>` : "");
    card.appendChild(box);
  }

  // 서술어별 문법 요소 칩: 누르면 근거 형태와 설명을 보여 준다
  function renderFeats(card, feats) {
    if (!feats.length) return;
    const row = document.createElement("div");
    row.className = "feats";
    const note = document.createElement("div");
    note.className = "feat-note small";
    note.hidden = true;
    feats.forEach((f) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "feat" + (f.estimated ? " est" : "") + (f.warn ? " warn" : "");
      const mk = (f.markers || []).join(", ");
      b.innerHTML = `<b>${esc(f.cat)}</b> ${esc(f.value)}${f.estimated ? "?" : ""}` + (mk ? ` <span class="mk">${esc(mk)}</span>` : "");
      b.addEventListener("click", () => {
        const open = b.classList.toggle("on");
        row.querySelectorAll(".feat").forEach((x) => { if (x !== b) x.classList.remove("on"); });
        note.hidden = !open;
        note.textContent = `${f.cat} ${f.value}: ` + (mk ? `근거 ${mk}. ` : "") + (f.note || "");
      });
      row.appendChild(b);
    });
    card.appendChild(row);
    card.appendChild(note);
    // 높임 표현 확인 같은 경고는 처음부터 펼쳐 둔다
    const w = feats.findIndex((f) => f.warn);
    if (w >= 0) row.children[w].click();
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
