// Stats, recent leads, demo chips and table styling. Navigation lives inline in index.html.
(function () {
  const $ = (id) => document.getElementById(id);
  const el = (tag, text, cls) =>
    Object.assign(document.createElement(tag), {
      textContent: text,
      className: cls || "",
    });

  // Stats and recent leads come from the real /api/leads response only.
  function unavailable() {
    ["stat-total", "stat-qualified", "stat-demo"].forEach((id) => {
      $(id).textContent = "—";
    });
    $("stat-note").textContent =
      "Lead statistics are unavailable right now. A dash means no data, not zero.";
    $("recent-list").replaceChildren(
      el("li", "Recent leads are unavailable right now.", "recent-empty"),
    );
  }
  async function loadStats() {
    try {
      const response = await fetch("/api/leads");
      if (!response.ok) throw new Error("bad response");
      const payload = await response.json();
      const leads = Array.isArray(payload.leads) ? payload.leads : [];
      $("stat-total").textContent = leads.length;
      $("stat-qualified").textContent = leads.filter(
        (l) => l.qualification_status === "Qualified",
      ).length;
      $("stat-demo").textContent = leads.filter(
        (l) => l.interested_in_demo,
      ).length;
      $("stat-note").textContent = "Calculated from saved leads.";
      const items = [...leads]
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
        .slice(0, 4)
        .map((lead) => {
          const li = document.createElement("li");
          const btn = el("button", "", "recent-item");
          btn.type = "button";
          const when = el(
            "time",
            new Date(lead.created_at).toLocaleString([], {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            }),
          );
          btn.append(
            el("span", lead.company_name),
            el(
              "span",
              `${lead.customer_name} · score ${lead.lead_score}`,
              "muted",
            ),
            when,
          );
          btn.addEventListener("click", () => {
            const row = document.querySelector(
              `#leads-body tr[data-id="${lead.id}"]`,
            );
            if (row) row.click();
          });
          li.append(btn);
          return li;
        });
      $("recent-list").replaceChildren(
        ...(items.length
          ? items
          : [
              el(
                "li",
                "No leads yet. Saved leads will appear here.",
                "recent-empty",
              ),
            ]),
      );
    } catch (_error) {
      unavailable();
    }
  }
  new MutationObserver(loadStats).observe($("leads-count"), {
    childList: true,
    characterData: true,
    subtree: true,
  });
  loadStats();

  // Demo lines fill the message box.
  document.querySelectorAll(".demo-lines li").forEach((li) => {
    li.tabIndex = 0;
    li.setAttribute("role", "button");
    const fill = () => {
      const input = $("message-input");
      input.value = li.textContent;
      input.focus();
    };
    li.addEventListener("click", fill);
    li.addEventListener("keydown", (e) => {
      if (e.key === "Enter") fill();
    });
  });

  // Table cell styling (display only).
  function decorateRows() {
    document.querySelectorAll("#leads-body tr").forEach((row) => {
      const c = row.cells;
      if (c.length < 7 || row.dataset.styled) return;
      row.dataset.styled = "1";
      c[3].classList.add("score-cell");
      const s = c[4].textContent.trim();
      c[4].classList.add(
        "badge",
        s === "Qualified"
          ? "badge-qualified"
          : s === "Potential"
            ? "badge-potential"
            : "badge-no",
      );
    });
  }
  new MutationObserver(decorateRows).observe($("leads-body"), {
    childList: true,
  });
  decorateRows();
})();
