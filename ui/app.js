(function () {
  "use strict";

  // Set by the server when we are hosted in the native window, so the page
  // fills it instead of looking like a document on a background.
  if (window.ZIL_IN_APP) document.body.classList.add("in-app");

  var lang = "tr";
  var T = window.I18N.tr;
  var settings = null, schedule = null, state = null;
  var currentDay = "Monday";

  // ---- plumbing ------------------------------------------------------

  function api(path, body) {
    var opts = { headers: { "X-Zil-Token": window.ZIL_TOKEN } };
    if (body !== undefined) {
      opts.method = "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (r) {
      if (!r.ok) return r.json().catch(function () { return {}; })
        .then(function (j) { throw new Error(j.error || ("HTTP " + r.status)); });
      return r.json();
    });
  }

  var toastTimer = null;
  function toast(msg, bad) {
    var el = document.getElementById("toast");
    el.textContent = msg;
    el.className = "toast" + (bad ? " bad" : "");
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, 2600);
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function label(key) { return T[key] || key; }

  // ---- i18n ----------------------------------------------------------

  function applyLang() {
    T = window.I18N[lang];
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach(function (n) {
      n.textContent = T[n.getAttribute("data-i18n")] || n.textContent;
    });
    buildButtons();
    buildMelodyRows();
    buildVolumeRows();
    renderDaySelects();
    renderTimetable();
    renderSpecial();
    if (state) renderState(state);
  }

  // ---- dashboard -----------------------------------------------------

  function buildButtons() {
    [["grp-bells", "bells"], ["grp-ceremony", "ceremony"],
     ["grp-emergency", "emergency"]].forEach(function (pair) {
      var host = document.getElementById(pair[0]);
      host.innerHTML = "";
      window.SOUND_GROUPS[pair[1]].forEach(function (s) {
        var b = el("button", "act " + s[1], label(s[0]));
        b.type = "button";
        b.onclick = function () { play(s[0]); };
        host.appendChild(b);
      });
    });
  }

  function play(key) {
    api("/api/play", { key: key }).then(function (r) {
      if (!r.ok) toast(r.message === "blocked by higher-priority audio (" +
        (r.audio && r.audio.label) + ")" ? T.blocked : r.message, true);
      renderState(r);
    }).catch(function (e) { toast(e.message, true); });
  }

  document.getElementById("stop-btn").onclick = function () {
    api("/api/stop", {}).then(renderState).catch(function (e) { toast(e.message, true); });
  };

  function renderState(s) {
    state = s;
    var now = new Date(s.now);
    document.getElementById("clock").textContent =
      now.toLocaleTimeString(lang === "tr" ? "tr-TR" : "en-GB", { hour12: false });
    document.getElementById("date").textContent =
      now.toLocaleDateString(lang === "tr" ? "tr-TR" : "en-GB",
        { weekday: "long", year: "numeric", month: "long", day: "numeric" });

    document.getElementById("school-name").textContent = s.school_name || "Zil";

    var nx = document.getElementById("next");
    if (!s.enabled) nx.textContent = "— " + T.paused + " —";
    else if (s.next) {
      var w = new Date(s.next.when);
      var sameDay = w.toDateString() === now.toDateString();
      nx.textContent = T.next_is + ": " + (sameDay ? "" :
        w.toLocaleDateString(lang === "tr" ? "tr-TR" : "en-GB", { weekday: "short" }) + " ") +
        s.next.time + " — " + label(s.next.key) + (s.next.name ? " (" + s.next.name + ")" : "");
    } else nx.textContent = T.next_none;

    var hb = document.getElementById("holiday-banner");
    if (s.holiday) {
      hb.hidden = false;
      hb.textContent = (s.holiday.from_time
        ? T.half_day_after.replace("{t}", s.holiday.from_time)
        : T.holiday_today) + (s.holiday.name ? " — " + s.holiday.name : "");
    } else hb.hidden = true;

    var warn = document.getElementById("engine-warn");
    if (s.audio && s.audio.audio_error) {
      warn.hidden = false;
      warn.textContent = T.audio_problem + ": " + s.audio.audio_error;
    } else warn.hidden = true;

    // Audio that is actually playing outranks the paused badge: manual sirens
    // still work while the scheduler is paused, and the pill must say so.
    var pill = document.getElementById("status-pill");
    if (s.audio && s.audio.playing) {
      pill.textContent = T.playing + ": " + label(s.audio.label);
      pill.className = "status playing";
    } else if (!s.enabled) {
      pill.textContent = T.paused; pill.className = "status paused";
    } else { pill.textContent = T.tracking; pill.className = "status"; }

    var tl = document.getElementById("timeline");
    tl.innerHTML = "";
    if (!s.today_events.length) tl.appendChild(el("div", "empty", T.no_events));
    s.today_events.forEach(function (e) {
      var d = el("div", "ev " + (e.source === "ceremony" ? "ceremony" : e.key) +
        (e.past ? " past" : ""));
      d.appendChild(el("b", null, e.time));
      d.appendChild(el("span", "k", label(e.key)));
      tl.appendChild(d);
    });
  }

  // ---- timetable -----------------------------------------------------

  function renderDaySelects() {
    var ds = document.getElementById("day-select");
    var ct = document.getElementById("copy-target");
    ds.innerHTML = ""; ct.innerHTML = "";
    window.DAY_KEYS.forEach(function (d) {
      var o = el("option", null, T.days[d]); o.value = d;
      if (d === currentDay) o.selected = true;
      ds.appendChild(o);
      var o2 = el("option", null, T.days[d]); o2.value = d;
      ct.appendChild(o2);
    });
    ds.onchange = function () { currentDay = ds.value; renderTimetable(); };
  }

  function renderTimetable() {
    if (!schedule) return;
    var tb = document.querySelector("#tt-table tbody");
    tb.innerHTML = "";
    var rows = schedule.weekly[currentDay] || [];
    rows.forEach(function (ev, i) {
      var tr = el("tr");

      var tdL = el("td", "tiny");
      var inL = el("input"); inL.type = "number"; inL.min = 1; inL.value = ev.lesson || "";
      inL.onchange = function () { ev.lesson = parseInt(inL.value, 10) || null; };
      tdL.appendChild(inL); tr.appendChild(tdL);

      var tdT = el("td", "narrow");
      var sel = el("select");
      ["student", "teacher", "exit"].forEach(function (k) {
        var o = el("option", null, label(k)); o.value = k;
        if (k === ev.type) o.selected = true;
        sel.appendChild(o);
      });
      sel.onchange = function () { ev.type = sel.value; };
      tdT.appendChild(sel); tr.appendChild(tdT);

      var tdTime = el("td", "narrow");
      var inT = el("input"); inT.type = "time"; inT.value = ev.time || "";
      inT.onchange = function () { ev.time = inT.value; };
      tdTime.appendChild(inT); tr.appendChild(tdTime);

      var tdA = el("td", "tiny");
      var cb = el("input"); cb.type = "checkbox"; cb.checked = ev.enabled !== false;
      cb.onchange = function () { ev.enabled = cb.checked; };
      tdA.appendChild(cb); tr.appendChild(tdA);

      var tdD = el("td", "tiny");
      var del = el("button", "btn del", "✕"); del.type = "button";
      del.onclick = function () { rows.splice(i, 1); renderTimetable(); };
      tdD.appendChild(del); tr.appendChild(tdD);

      tb.appendChild(tr);
    });
    if (!rows.length) {
      var tr2 = el("tr");
      var td = el("td", "empty", T.no_events); td.colSpan = 5;
      tr2.appendChild(td); tb.appendChild(tr2);
    }
  }

  document.getElementById("add-row").onclick = function () {
    schedule.weekly[currentDay] = schedule.weekly[currentDay] || [];
    schedule.weekly[currentDay].push({ lesson: null, type: "student", time: "08:00", enabled: true });
    renderTimetable();
  };

  document.getElementById("copy-btn").onclick = function () {
    var targets = Array.prototype.filter.call(
      document.getElementById("copy-target").options, function (o) { return o.selected; })
      .map(function (o) { return o.value; });
    if (!targets.length) return;
    targets.forEach(function (d) {
      if (d === currentDay) return;
      schedule.weekly[d] = JSON.parse(JSON.stringify(schedule.weekly[currentDay] || []));
    });
    toast(T.copy + " ✓");
  };

  document.getElementById("save-tt").onclick = saveSchedule;

  function sortDay(list) {
    return (list || []).slice().sort(function (a, b) {
      return String(a.time).localeCompare(String(b.time));
    });
  }

  function saveSchedule() {
    window.DAY_KEYS.forEach(function (d) { schedule.weekly[d] = sortDay(schedule.weekly[d]); });
    api("/api/schedule", schedule).then(function (r) {
      schedule = r.schedule; renderTimetable(); renderSpecial(); toast(T.saved);
    }).catch(function (e) { toast(T.save_failed + ": " + e.message, true); });
  }

  // ---- special days --------------------------------------------------

  function simpleTable(tbodySel, list, cols, onAdd) {
    var tb = document.querySelector(tbodySel);
    tb.innerHTML = "";
    list.forEach(function (item, i) {
      var tr = el("tr");
      cols.forEach(function (c) {
        var td = el("td", c.cls || "");
        var input;
        if (c.type === "select") {
          input = el("select");
          c.options().forEach(function (opt) {
            var o = el("option", opt[1]); o.value = opt[0];
            if (opt[0] === item[c.key]) o.selected = true;
            input.appendChild(o);
          });
        } else {
          input = el("input"); input.type = c.type;
          input.value = item[c.key] || "";
        }
        input.onchange = function () {
          item[c.key] = input.value;
          if (c.after) c.after(item);
        };
        td.appendChild(input); tr.appendChild(td);
      });
      var tdD = el("td", "tiny");
      var del = el("button", "btn del", "✕"); del.type = "button";
      del.onclick = function () { list.splice(i, 1); renderSpecial(); };
      tdD.appendChild(del); tr.appendChild(tdD);
      tb.appendChild(tr);
    });
  }

  function renderSpecial() {
    if (!schedule) return;
    simpleTable("#hol-table tbody", schedule.holidays,
      [{ key: "date", type: "date", cls: "narrow",
         // A one-day holiday should say so on both sides rather than leaving a
         // blank box that looks like missing data.
         after: function (item) {
           if (!item.end_date || item.end_date < item.date) {
             item.end_date = item.date;
             renderSpecial();
           }
         } },
       { key: "end_date", type: "date", cls: "narrow" },
       { key: "from_time", type: "time", cls: "narrow" },
       { key: "name", type: "text" }]);

    simpleTable("#ovr-table tbody", schedule.overrides,
      [{ key: "date", type: "date", cls: "narrow" },
       { key: "use_day", type: "select", cls: "narrow",
         options: function () { return window.DAY_KEYS.map(function (d) { return [d, T.days[d]]; }); } }]);

    simpleTable("#cer-table tbody", schedule.ceremonies,
      [{ key: "date", type: "date", cls: "narrow" },
       { key: "time", type: "time", cls: "narrow" },
       { key: "sound", type: "select", cls: "narrow",
         options: function () {
           return Object.keys(window.SOUND_FOLDER).map(function (k) { return [k, label(k)]; });
         } },
       { key: "name", type: "text" }]);
  }

  document.getElementById("add-hol").onclick = function () {
    schedule.holidays.push({ date: today(), end_date: today(), name: "" });
    renderSpecial();
  };
  document.getElementById("add-ovr").onclick = function () {
    schedule.overrides.push({ date: today(), use_day: "Monday" }); renderSpecial();
  };
  document.getElementById("add-cer").onclick = function () {
    schedule.ceremonies.push({ date: today(), time: "09:00", sound: "anthem_only",
                               name: "", enabled: true });
    renderSpecial();
  };
  document.getElementById("save-special").onclick = saveSchedule;

  function today() { return new Date().toISOString().slice(0, 10); }

  // ---- settings ------------------------------------------------------

  var audioFiles = { bells: [], anthems: [], sirens: [] };

  function buildMelodyRows() {
    if (!settings) return;
    var host = document.getElementById("melody-rows");
    host.innerHTML = "";
    Object.keys(window.SOUND_FOLDER).forEach(function (key) {
      var folder = window.SOUND_FOLDER[key];
      host.appendChild(el("label", null, label(key)));
      var sel = el("select");
      sel.id = "mel-" + key;
      var cur = (settings.melodies || {})[key] || "";
      var opts = audioFiles[folder] || [];
      if (cur && opts.indexOf(cur) === -1) opts = [cur].concat(opts);
      var blank = el("option", "—"); blank.value = ""; sel.appendChild(blank);
      opts.forEach(function (f) {
        var o = el("option", null, f); o.value = f;
        if (f === cur) o.selected = true;
        sel.appendChild(o);
      });
      host.appendChild(sel);
    });
  }

  function buildVolumeRows() {
    if (!settings) return;
    var host = document.getElementById("vol-rows");
    host.innerHTML = "";
    ["bell", "ceremony", "emergency"].forEach(function (k) {
      var wrap = el("div", "volrow");
      var lab = el("div", "lbl");
      lab.appendChild(el("span", null, T["vol_" + k]));
      var val = el("span", null, String((settings.volumes || {})[k]));
      lab.appendChild(val);
      var r = el("input"); r.type = "range"; r.min = 0; r.max = 100;
      r.value = (settings.volumes || {})[k];
      r.id = "vol-" + k;
      r.oninput = function () { val.textContent = r.value; };
      wrap.appendChild(lab); wrap.appendChild(r);
      host.appendChild(wrap);
    });
  }

  function fillSettings() {
    document.getElementById("s-school").value = settings.school_name || "";
    document.getElementById("s-catchup").value = settings.catchup_seconds;
    document.getElementById("s-enabled").checked = settings.enabled !== false;
    buildVolumeRows();
    buildMelodyRows();
  }

  document.getElementById("save-settings").onclick = function () {
    var mel = {};
    Object.keys(window.SOUND_FOLDER).forEach(function (k) {
      mel[k] = document.getElementById("mel-" + k).value;
    });
    var body = {
      school_name: document.getElementById("s-school").value.trim(),
      catchup_seconds: parseInt(document.getElementById("s-catchup").value, 10),
      enabled: document.getElementById("s-enabled").checked,
      language: lang,
      melodies: mel,
      volumes: {
        bell: parseInt(document.getElementById("vol-bell").value, 10),
        ceremony: parseInt(document.getElementById("vol-ceremony").value, 10),
        emergency: parseInt(document.getElementById("vol-emergency").value, 10)
      }
    };
    api("/api/settings", body).then(function (r) {
      settings = r.settings; fillSettings(); toast(T.saved);
    }).catch(function (e) { toast(T.save_failed + ": " + e.message, true); });
  };

  // ---- log -----------------------------------------------------------

  function loadLog() {
    api("/api/log").then(function (rows) {
      var tb = document.querySelector("#log-table tbody");
      tb.innerHTML = "";
      rows.forEach(function (r) {
        var tr = el("tr");
        tr.appendChild(el("td", "narrow", r.ts.replace("T", " ")));
        tr.appendChild(el("td", "narrow", r.kind));
        tr.appendChild(el("td", null, label(r.key)));
        tr.appendChild(el("td", null, r.detail || ""));
        tb.appendChild(tr);
      });
    });
  }
  document.getElementById("refresh-log").onclick = loadLog;

  // ---- tabs ----------------------------------------------------------

  document.getElementById("tabs").addEventListener("click", function (e) {
    var btn = e.target.closest(".tab");
    if (!btn) return;
    document.querySelectorAll(".tab").forEach(function (t) { t.classList.remove("active"); });
    document.querySelectorAll(".pane").forEach(function (p) { p.classList.remove("active"); });
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "log") loadLog();
    // Re-scan audio/ on entering settings: a file copied in seconds ago should
    // appear in the dropdowns without reopening the window.
    if (btn.dataset.tab === "settings") {
      api("/api/audio-files").then(function (files) {
        audioFiles = files;
        buildMelodyRows();
      }).catch(function () {});
    }
  });

  document.getElementById("lang-toggle").onclick = function () {
    lang = lang === "tr" ? "en" : "tr";
    applyLang();
  };

  // ---- boot ----------------------------------------------------------

  Promise.all([api("/api/settings"), api("/api/schedule"), api("/api/audio-files")])
    .then(function (r) {
      settings = r[0]; schedule = r[1]; audioFiles = r[2];
      lang = settings.language === "en" ? "en" : "tr";
      applyLang();
      fillSettings();
      return api("/api/state");
    })
    .then(renderState)
    .catch(function (e) { toast("init: " + e.message, true); });

  setInterval(function () {
    api("/api/state").then(renderState).catch(function () {});
  }, 1000);
})();
