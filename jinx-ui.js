/* PasarGuard dashboard add-on (Super JinX build)
   Looks and behaves like a built-in part of the panel: uses only the panel's own theme tokens,
   follows light/dark, the selected accent color and the panel language.
   1) Sidebar shows only: Dashboard, Users, API Keys, Templates, Bulk Actions, Settings, Support
      (+ Admins for the owner only, to create resellers).
   2) Owner only: two items inside the panel's own menu (desktop and the mobile menu):
      Change password, Proxy IP. The pages live outside the panel's React tree, so the panel
      can re-render freely without wiping what you type, and panel hotkeys never swallow your keys.
   3) Sidebar footer: Telegram channel as a normal menu item. */
(function () {
  "use strict";
  function norm(t) { return String(t || "").split(String.fromCharCode(8204)).join(" ").replace(/\s+/g, " ").trim().toLowerCase(); }

  /* ---------- 1) sidebar filter ---------- */
  var HIDE = [
    "نودها", "نود", "Nodes", "Node",
    "هاست‌ها", "هاست ها", "هاستها", "میزبان‌ها", "Hosts", "Host Settings",
    "هسته‌ها", "هسته", "پیکربندی هسته", "تنظیمات هسته", "Cores", "Core", "Core Settings", "Core Config",
    "گروه‌ها", "گروه ها", "گروهها", "Groups",
    "نقش‌ها", "نقش ها", "Roles", "Admin Roles",
    "آمار", "Statistics", "Stats",
    /* Русский / 中文 (the panel ships these languages too) */
    "Ноды", "Узлы", "Хосты", "Ядра", "Ядро", "Настройки ядра", "Группы", "Роли", "Статистика",
    "节点", "主机", "核心", "核心设置", "核心配置", "分组", "群组", "角色", "统计"
  ].map(norm);
  /* the same pages by address, so the filter works in every language and after panel updates */
  var HIDE_HREF = /\/(nodes?|hosts?|cores?|core-?settings|groups?|roles?|admin-?roles|statistics|stats)(\/|\?|#|$)/i;
  var ADMINS_HREF = /\/admins?(\/|\?|#|$)/i;
  /* "Admins" is only for the owner (to create resellers); resellers never see it */
  var ADMINS = ["مدیران", "ادمین‌ها", "ادمین ها", "Admins", "Администраторы", "Админы", "管理员"].map(norm);
  var OWNER = null, askedFor = null, busy = false;
  function whoAmI() {                      /* asks once per login token, never spams the API */
    var t = findToken();
    if (!t) { OWNER = null; askedFor = null; return; }
    if (t === askedFor || busy) return;
    busy = true;
    fetch("/api/admin", { headers: { Authorization: "Bearer " + t } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (me) {
        busy = false; askedFor = t;
        OWNER = me ? !!((me.role && (me.role.is_owner || me.role.owner)) || me.is_owner === true) : null;   /* expired token: unknown, not "reseller" */
        schedule();
      })
      .catch(function () { busy = false; setTimeout(schedule, 30000); });
  }
  function hidden(txt, href) {
    txt = txt.replace(/[0-9۰-۹]+/g, "").trim();                 /* "Nodes 3" (badge counters) */
    var path = "";
    try { if (href) path = new URL(href, location.href).pathname + new URL(href, location.href).hash; } catch (e) {}
    if (HIDE.indexOf(txt) > -1 || (path && HIDE_HREF.test(path))) return true;
    return OWNER !== true && (ADMINS.indexOf(txt) > -1 || (path && ADMINS_HREF.test(path)));
  }
  function sweep() {
    whoAmI();
    var nodes = document.querySelectorAll('aside a, aside button, nav a, nav button, [data-sidebar="menu-button"], [data-sidebar="menu-sub-button"]');
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].classList.contains("jx-btn")) continue;
      var item = nodes[i].closest('[data-sidebar="menu-sub-item"], [data-sidebar="menu-item"], li') || nodes[i];
      var a = nodes[i].closest("a") || nodes[i].querySelector("a"), href = a && a.getAttribute("href") || "", txt = norm(nodes[i].textContent);
      var key = txt + "|" + href + "|" + OWNER;
      if (nodes[i].getAttribute("data-jxk") === key && item.style.display === (item.getAttribute("data-jxw") || "")) continue;   /* nothing changed */
      nodes[i].setAttribute("data-jxk", key);
      var want = hidden(txt, href) ? "none" : "";
      item.setAttribute("data-jxw", want);
      if (item.style.display !== want) item.style.display = want; item.dataset.jx = "1";
    }
  }

  function findToken() {
    var jwt = /(eyJ[\w-]+\.[\w-]+\.[\w-]+)/, stores = [];
    try { stores.push(localStorage); } catch (e) {}
    try { stores.push(sessionStorage); } catch (e) {}
    for (var s = 0; s < stores.length; s++) {
      for (var i = 0; i < stores[s].length; i++) {
        var m = jwt.exec(String(stores[s].getItem(stores[s].key(i)) || ""));
        if (m) return m[1];
      }
    }
    var c = jwt.exec(document.cookie || ""); return c ? c[1] : null;
  }
  function fa(n) { return String(n).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; }); }

  /* ---------- i18n: follows the panel language (fa / en) ---------- */
  var LANG = null;
  function lang() { if (LANG) return LANG; LANG = lang0(); return LANG; }
  function lang0() {
    /* the panel flips <html dir> when the language changes: that is the most reliable signal */
    var d = (document.documentElement.getAttribute("dir") || document.body && document.body.getAttribute("dir") || "").toLowerCase();
    var l = "";
    try { l = localStorage.getItem("i18nextLng") || localStorage.getItem("i18n") || localStorage.getItem("language") || localStorage.getItem("lang") || ""; } catch (e) {}
    l = (l || document.documentElement.lang || "").toLowerCase();
    if (d === "rtl") return "fa";
    if (d === "ltr") return "en";
    return l.indexOf("fa") === 0 ? "fa" : "en";
  }
  var STR = {
    fa: {
      title: "دسترسی مالک", desc: "تغییر رمز مالک پنل با کلید یک‌بارمصرف یا به‌صورت مستقیم، و مدیریت لوکیشن‌ها.",
      tKey: "کلید موقت", tPass: "تغییر رمز", tLoc: "لوکیشن‌ها",
      s1: "کلید رو بگیر", s2: "توی صفحه‌ی ورود «دسترسی مالک» رو بزن", s3: "کلید رو وارد کن و رمز جدید بذار",
      getKey: "دریافت کلید", yourKey: "کلید شما", copy: "کپی", copied: "کپی شد", hide: "مخفی", show: "نمایش", newKey: "کلید جدید",
      expired: "منقضی شد", left: "باقی‌مونده", keyNote: "این کلید یک‌بارمصرفه و بعد از ۵ دقیقه باطل میشه.",
      np: "رمز جدید", np2: "تکرار رمز جدید", save: "ذخیره", gen: "ساخت رمز قوی", genOk: "رمز ساخته و کپی شد",
      st: ["", "ضعیف", "متوسط", "خوب", "قوی"], stIdle: "قدرت رمز", rLen: "حداقل ۸ کاراکتر", rMix: "حرف و عدد با هم", rSp: "بدون فاصله", rEq: "تکرار یکسان", vOk: "رمز جدید با موفقیت امتحان شد و کار می‌کنه.",
      saved: "رمز مالک تغییر کرد", savedD: "از این به بعد با رمز جدید وارد شو.",
      eShort: "رمز جدید حداقل ۸ کاراکتر باشه.", eMix: "رمز رو ترکیبی از حرف و عدد بذار.", eSpace: "رمز نباید فاصله داشته باشه.", eSame: "تکرار رمز یکی نیست.",
      auth: "برای ادامه، نام کاربری و رمز فعلی مالک رو وارد کن.", user: "نام کاربری", pass: "رمز فعلی", ok: "تأیید", eFill: "نام کاربری و رمز رو وارد کن.",
      eNet: "ارتباط با سرور برقرار نشد.", eGen: "خطایی پیش اومد، دوباره امتحان کن.", eWrong: "نام کاربری یا رمز اشتباهه.", wait: "لطفاً صبر کنید...",
      hist: "فعالیت‌های اخیر", hEmpty: "هنوز فعالیتی ثبت نشده.", hKey: "دریافت کلید موقت", hPass: "تغییر مستقیم رمز",
      now: "همین الان", m: " دقیقه پیش", h: " ساعت پیش", d: " روز پیش",
      main: "اصلی", noDom: "دامنه هنوز ساخته نشده", lEmpty: "هنوز لوکیشن دیگه‌ای وصل نشده.", loading: "در حال بارگذاری...",
      add: "افزودن لوکیشن", refresh: "بروزرسانی", connected: "متصل", connecting: "در حال اتصال", offline: "قطع",
      rmAsk: "برای حذف دوباره بزن", code: "کد اتصال", codeOk: "کد اتصال کپی شد", needDom: "اول برای پنل دامنه بساز (پورت 8080).",
      g1: "توی همین پروژه‌ی Railway یه سرویس جدید از همین ریپو بساز.",
      g2: "از Settings، بخش Region رو روی لوکیشن دلخواه بذار.",
      g3: "توی Variables بذار: ", g4: "از Networking یه دامنه روی پورت 8080 و یه TCP Proxy روی پورت 62050 بساز.",
      g5: "حدود یه دقیقه بعد لوکیشن اینجا نشون داده میشه و کانفیگ‌هاش به اشتراک کاربرها اضافه میشه.",
      channel: "کانال تلگرام", grp: "مدیریت پیشرفته", pOwner: "امنیت مالک", pPass: "تغییر رمز", dPass: "رمز ورود مالک پنل رو مستقیم عوض کن. رمز قوی بذار و جایی امن نگهش دار.", pLoc: "لوکیشن‌ها", pIp: "آی‌پی پروکسی",
      dOwner: "کلید موقت ورود، تغییر مستقیم رمز مالک و فعالیت‌های اخیر.", dLoc: "سرورهای لوکیشن‌های دیگه رو به همین پنل وصل کن.", dIp: "آی‌پی بده؛ هر کدوم با یک اتصال واقعی کانفیگ تست میشه، کشورش خودکار پیدا میشه و فقط سالم‌ها روی کانفیگ‌ها میرن.",
      tIp: "آی‌پی تمیز", ipD: "یک یا چند آی‌پی بنویس یا فایل بده. سرور هر آی‌پی رو با دست‌دادن واقعی کانفیگ تست می‌کنه، کشور و شهرش رو پیدا می‌کنه و سالم‌ها رو با اسم همون کشور روی کانفیگ‌ها می‌ذاره. اگه توی اون کشور لوکیشن داشته باشی، کانفیگ‌ها از همون لوکیشن میان.",
      ipUp: "آپلود فایل", ipTest: "تست و ذخیره", ipPh: "هر خط یه آی‌پی، آی‌پی:پورت یا رنج CIDR", ipTesting: "در حال تست", ipOk: " سالم", ipNone: "هیچ آی‌پی‌ای به این پنل نرسید.",
      ipSaved: "لیست آی‌پی ذخیره شد", ipApplied: "روی کانفیگ‌ها اعمال شد", ipS1: "آی‌پی فعال", ipS2: "کشور", ipS3: "بهترین پینگ", ipS4: "آخرین بررسی", phTest: "تست اتصال و کانفیگ", phGeo: "پیدا کردن کشور آی‌پی‌ها", phLoc: "وصل کردن به لوکیشن همون کشور", ipLive: "سریع‌ترین‌ها تا الان", ipOkN: " سالم", ipBadN: " رد شده", wTcp: "به سرور نرسید", wTls: "گواهی نامعتبر", wHttp: "مال این سرویس نیست", wWs: "کانفیگ جواب نداد", ipBadT: "آی‌پی‌های رد شده", ipList: "آی‌پی‌های روی کانفیگ‌ها", ipRetest: "بررسی دوباره", ipRetOk: "همه دوباره بررسی شدن", ipRm: "حذف", ipVia: "لوکیشن ", ipMain: "سرور اصلی", ipPrev: "اسم کانفیگ‌ها: ", ipAuto: "آی‌پی‌های روی کانفیگ هر ۱۰ دقیقه خودکار بررسی میشن و اگه یکی خراب بشه، بعدی جاش میاد.", ipUse: "روی کانفیگ", ipSpare: "ذخیره", ms: " ms", ipGroup: "گروه", ipGroupD: "خودکار ساخته شد. به هر کاربری این گروه رو بدی، کانفیگ‌های آی‌پی هم می‌گیره. قالب‌های ◈ Phantom هم آماده‌ان.", ipPer: "آی‌پی برای هر کانفیگ", ipShare: "برای همه‌ی کاربرها فعال باشه", ipClear: "حذف لیست", ipEmpty: "هنوز لیستی ذخیره نشده.", ipCount: " آی‌پی فعال"
    },
    en: {
      title: "Owner access", desc: "Change the owner password with a one-time key or directly, and manage locations.",
      tKey: "Temporary key", tPass: "Change password", tLoc: "Locations",
      s1: "Get a key", s2: "Open \"Owner access\" on the login page", s3: "Enter the key and set a new password",
      getKey: "Get key", yourKey: "Your key", copy: "Copy", copied: "Copied", hide: "Hide", show: "Show", newKey: "New key",
      expired: "Expired", left: "left", keyNote: "One-time key, expires after 5 minutes.",
      np: "New password", np2: "Repeat new password", save: "Save", gen: "Generate", genOk: "Password generated and copied",
      st: ["", "Weak", "Fair", "Good", "Strong"], stIdle: "Strength", rLen: "8+ characters", rMix: "Letters and numbers", rSp: "No spaces", rEq: "Both match", vOk: "The new password was tested and works.",
      saved: "Owner password changed", savedD: "Use the new password from now on.",
      eShort: "At least 8 characters.", eMix: "Use letters and numbers.", eSpace: "No spaces allowed.", eSame: "Passwords do not match.",
      auth: "To continue, enter the current owner username and password.", user: "Username", pass: "Current password", ok: "Confirm", eFill: "Enter username and password.",
      eNet: "Could not reach the server.", eGen: "Something went wrong, try again.", eWrong: "Wrong username or password.", wait: "Please wait...",
      hist: "Recent activity", hEmpty: "No activity yet.", hKey: "Temporary key issued", hPass: "Password changed",
      now: "just now", m: "m ago", h: "h ago", d: "d ago",
      main: "Main", noDom: "No domain yet", lEmpty: "No other locations connected yet.", loading: "Loading...",
      add: "Add location", refresh: "Refresh", connected: "Connected", connecting: "Connecting", offline: "Offline",
      rmAsk: "Click again to remove", code: "Join code", codeOk: "Join code copied", needDom: "Generate a domain for the panel first (port 8080).",
      g1: "In the same Railway project, create a new service from this repo.",
      g2: "In Settings, set Region to the location you want.",
      g3: "In Variables set: ", g4: "In Networking, generate a domain on port 8080 and a TCP Proxy on port 62050.",
      g5: "About a minute later the location shows up here and its configs are added to every subscription.",
      channel: "Telegram channel", grp: "Advanced", pOwner: "Owner security", pPass: "Change password", dPass: "Change the panel owner password directly. Use a strong one and keep it safe.", pLoc: "Locations", pIp: "Proxy IP",
      dOwner: "Temporary login key, direct owner password change and recent activity.", dLoc: "Connect servers in other regions to this panel.", dIp: "Add IPs; each one is tested with a real config handshake, its country is found automatically and only working ones go on the configs.",
      tIp: "Clean IP", ipD: "Type one or more IPs or upload a file. The server tests each IP with a real config handshake, finds its country and city, and puts the working ones on the configs under that country's name. If you have a location in that country, the configs come from that location.",
      ipUp: "Upload file", ipTest: "Test and save", ipPh: "One IP per line, ip:port or CIDR", ipTesting: "Testing", ipOk: " working", ipNone: "None of these IPs reach this panel.",
      ipSaved: "IP list saved", ipApplied: "Applied to the configs", ipS1: "Active IPs", ipS2: "Countries", ipS3: "Best ping", ipS4: "Last check", phTest: "Testing connection and config", phGeo: "Finding each IP's country", phLoc: "Linking to the location in that country", ipLive: "Fastest so far", ipOkN: " working", ipBadN: " failed", wTcp: "Unreachable", wTls: "Bad certificate", wHttp: "Not this service", wWs: "Config did not answer", ipBadT: "Failed IPs", ipList: "IPs on the configs", ipRetest: "Check again", ipRetOk: "All checked again", ipRm: "Remove", ipVia: "Location ", ipMain: "Main server", ipPrev: "Config names: ", ipAuto: "IPs on the configs are checked every 10 minutes; a dead one is replaced by the next best automatically.", ipUse: "On configs", ipSpare: "Spare", ms: " ms", ipGroup: "Group", ipGroupD: "was created automatically. Give it to any user and they get the clean IP configs too. ◈ Phantom templates are ready.", ipPer: "IPs per config", ipShare: "Enable for all users", ipClear: "Remove list", ipEmpty: "No list saved yet.", ipCount: " active IPs"
    }
  };
  var IPJ = null;   /* running clean IP test: survives a language rebuild of the page */
  function T(k) { var L = STR[lang()] || STR.en; return L[k] != null ? L[k] : STR.en[k]; }
  function num(n) { return lang() === "fa" ? fa(n) : String(n); }
  function ago(t) {
    var s = Math.max(0, Math.round(Date.now() / 1000 - t));
    if (s < 60) return T("now");
    if (s < 3600) return num(Math.floor(s / 60)) + T("m");
    if (s < 86400) return num(Math.floor(s / 3600)) + T("h");
    return num(Math.floor(s / 86400)) + T("d");
  }
  function strength(p) {
    if (!p) return 0;
    var sc = 0;
    if (p.length >= 8) sc++;
    if (p.length >= 12) sc++;
    if (/[a-z]/.test(p) && /[A-Z]/.test(p)) sc++;
    if (/\d/.test(p) && /[^A-Za-z0-9]/.test(p)) sc++;
    if (/^\d+$/.test(p) || /^[A-Za-z]+$/.test(p) || p.length < 8) sc = Math.min(sc, 1);
    return Math.max(1, Math.min(4, sc));
  }
  function genPass() {
    var A = "ABCDEFGHJKLMNPQRSTUVWXYZ", a = "abcdefghijkmnpqrstuvwxyz", d = "23456789", x = "!@#$%*?-_", all = A + a + d + x, out = [];
    var rnd = function (n) { try { var u = new Uint32Array(1); crypto.getRandomValues(u); return u[0] % n; } catch (e) { return Math.floor(Math.random() * n); } };
    out.push(A[rnd(A.length)], a[rnd(a.length)], d[rnd(d.length)], x[rnd(x.length)]);
    while (out.length < 14) out.push(all[rnd(all.length)]);
    for (var i = out.length - 1; i > 0; i--) { var j = rnd(i + 1), t = out[i]; out[i] = out[j]; out[j] = t; }
    return out.join("");
  }

  /* ---------- native look: only the panel's own theme tokens (shadcn), no custom colors ---------- */
  var CSS =
    ".pg-ok{min-width:0;max-width:100%;margin:0 0 16px;border-radius:calc(var(--radius) + 4px);border:1px solid hsl(var(--border));background:hsl(var(--card));color:hsl(var(--card-foreground));box-shadow:0 1px 2px 0 rgb(0 0 0/.05);font:inherit;position:relative}" +
    ".pg-ok *{box-sizing:border-box}" +
    ".pg-ok .hd{display:flex;align-items:flex-start;gap:12px;padding:20px 20px 0}" +
    ".pg-ok .ic{width:36px;height:36px;flex-shrink:0;border-radius:var(--radius);display:grid;place-items:center;background:hsl(var(--primary)/.1);color:hsl(var(--primary))}" +
    ".pg-ok svg{width:16px;height:16px;flex-shrink:0}" +
    ".pg-ok .hd h3{margin:0;font-size:16px;font-weight:600;line-height:1.4;letter-spacing:-.01em}" +
    ".pg-ok .hd p{margin:2px 0 0;font-size:13px;line-height:1.6;color:hsl(var(--muted-foreground))}" +
    ".pg-ok .bd{display:block;height:auto;border-radius:0;background:none;color:inherit;font-size:inherit;font-weight:inherit;padding:16px 20px 20px}" +
    /* tabs (TabsList / TabsTrigger) */
    ".pg-ok .tb{display:inline-flex;align-items:center;gap:2px;height:36px;padding:3px;border-radius:var(--radius);background:hsl(var(--muted));color:hsl(var(--muted-foreground));max-width:100%;overflow-x:auto;scrollbar-width:none}" +
    ".pg-ok .tb::-webkit-scrollbar{display:none}" +
    ".pg-ok .tb button{display:inline-flex;align-items:center;justify-content:center;gap:6px;height:30px;padding:0 12px;border:0;border-radius:calc(var(--radius) - 2px);background:none;color:inherit;font:inherit;font-size:13px;font-weight:500;white-space:nowrap;cursor:pointer;transition:background .15s,color .15s,box-shadow .15s}" +
    ".pg-ok .tb button.on{background:hsl(var(--background));color:hsl(var(--foreground));box-shadow:0 1px 3px 0 rgb(0 0 0/.1)}" +
    ".pg-ok .pn{display:none;margin-top:16px}.pg-ok .pn.on{display:block}" +
    /* buttons */
    ".pg-ok .bt{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:36px;padding:0 16px;border-radius:calc(var(--radius) - 2px);border:1px solid transparent;font:inherit;font-size:13.5px;font-weight:500;white-space:nowrap;cursor:pointer;background:hsl(var(--primary));color:hsl(var(--primary-foreground));box-shadow:0 1px 2px 0 rgb(0 0 0/.05);transition:background .15s,opacity .15s}" +
    ".pg-ok .bt:hover{background:hsl(var(--primary)/.9)}.pg-ok .bt[disabled]{opacity:.5;pointer-events:none}" +
    ".pg-ok .bt:focus-visible,.pg-ok .tb button:focus-visible,.pg-ok input:focus-visible{outline:none;box-shadow:0 0 0 2px hsl(var(--background)),0 0 0 4px hsl(var(--ring))}" +
    ".pg-ok .bt.ol{background:hsl(var(--background));color:hsl(var(--foreground));border-color:hsl(var(--input, var(--border)))}.pg-ok .bt.ol:hover{background:hsl(var(--accent));color:hsl(var(--accent-foreground))}" +
    ".pg-ok .bt.gh{background:none;color:hsl(var(--foreground));box-shadow:none}.pg-ok .bt.gh:hover{background:hsl(var(--accent))}" +
    ".pg-ok .bt.sm{height:32px;padding:0 12px;font-size:13px}" +
    ".pg-ok .bt.icn{width:32px;height:32px;padding:0}" +
    ".pg-ok .sp{width:14px;height:14px;border-radius:50%;border:2px solid currentColor;border-top-color:transparent;animation:pgsp .7s linear infinite}@keyframes pgsp{to{transform:rotate(360deg)}}" +
    ".pg-ok .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}" +
    /* steps */
    ".pg-ok .stp{list-style:none;margin:0 0 16px;padding:0;display:flex;flex-direction:column;gap:8px}" +
    ".pg-ok .stp li{display:flex;align-items:center;gap:10px;font-size:13px;color:hsl(var(--muted-foreground))}" +
    ".pg-ok .stp i{width:22px;height:22px;flex-shrink:0;border-radius:50%;display:grid;place-items:center;font-style:normal;font-size:11.5px;font-weight:600;border:1px solid hsl(var(--border));color:hsl(var(--muted-foreground));transition:.2s}" +
    ".pg-ok .stp li.on{color:hsl(var(--foreground))}.pg-ok .stp li.on i{background:hsl(var(--primary));border-color:hsl(var(--primary));color:hsl(var(--primary-foreground))}" +
    /* key box */
    ".pg-ok .kv{display:none;padding:14px;border-radius:var(--radius);border:1px solid hsl(var(--border));background:hsl(var(--muted)/.4)}" +
    ".pg-ok .lb{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px;font-size:12.5px;font-weight:500}" +
    ".pg-ok .bdg{display:inline-flex;align-items:center;gap:5px;height:22px;padding:0 8px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid hsl(var(--border));background:hsl(var(--background));font-variant-numeric:tabular-nums;white-space:nowrap}" +
    ".pg-ok .bdg.ok{color:#16a34a;border-color:rgb(22 163 74/.35);background:rgb(22 163 74/.08)}.pg-ok .bdg.warn{color:#d97706;border-color:rgb(217 119 6/.35);background:rgb(217 119 6/.08)}.pg-ok .bdg.bad{color:hsl(var(--destructive, 0 84% 60%));border-color:hsl(var(--destructive, 0 84% 60%)/.35);background:hsl(var(--destructive, 0 84% 60%)/.08)}" +
    ".pg-ok .bdg .dt{width:6px;height:6px;border-radius:50%;background:currentColor}" +
    ".pg-ok .kc{display:flex;align-items:center;gap:8px}" +
    ".pg-ok code{flex:1;min-width:0;display:block;padding:8px 12px;border-radius:calc(var(--radius) - 2px);border:1px solid hsl(var(--border));background:hsl(var(--background));font:600 14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;direction:ltr;text-align:left;word-break:break-all;cursor:pointer;transition:filter .2s}" +
    ".pg-ok code.bl{filter:blur(5px)}.pg-ok .kv.dead code{opacity:.45;text-decoration:line-through}" +
    ".pg-ok .pr{height:4px;margin:12px 0;border-radius:999px;background:hsl(var(--primary)/.15);overflow:hidden}.pg-ok .pr > i{display:block;height:100%;width:100%;background:hsl(var(--primary));border-radius:inherit;transition:width .5s linear}" +
    ".pg-ok .kv.warn .pr > i{background:#d97706}.pg-ok .kv.bad .pr > i{background:hsl(var(--destructive, 0 84% 60%))}" +
    ".pg-ok .mt{margin:10px 0 0;font-size:12px;color:hsl(var(--muted-foreground))}" +
    /* form */
    ".pg-ok .fm{display:flex;flex-direction:column;gap:12px;max-width:440px}" +
    ".pg-ok .fl{display:flex;flex-direction:column;gap:6px}.pg-ok .fl > span{font-size:13px;font-weight:500}" +
    ".pg-ok .ip{position:relative}" +
    ".pg-ok input{width:100%;height:36px;padding:0 12px;border-radius:calc(var(--radius) - 2px);border:1px solid hsl(var(--input, var(--border)));background:transparent;color:inherit;font:inherit;font-size:14px;direction:ltr;box-shadow:0 1px 2px 0 rgb(0 0 0/.05);transition:border-color .15s}" +
    ".pg-ok .ip input{padding-left:40px}.pg-ok input.bad{border-color:hsl(var(--destructive, 0 84% 60%))}" +
    ".pg-ok .ip .bt{position:absolute;left:2px;top:2px;width:32px;height:32px;padding:0;color:hsl(var(--muted-foreground))}" +
    ".pg-ok .sm2{display:flex;align-items:center;gap:10px;font-size:12px;color:hsl(var(--muted-foreground))}.pg-ok .sm2 .br{flex:1;display:grid;grid-template-columns:repeat(4,1fr);gap:4px}" +
    ".pg-ok .sm2 .br i{height:4px;border-radius:999px;background:hsl(var(--muted))}" +
    ".pg-ok .sm2[data-l='1'] .br i:nth-child(-n+1){background:hsl(var(--destructive, 0 84% 60%))}.pg-ok .sm2[data-l='2'] .br i:nth-child(-n+2){background:#d97706}" +
    ".pg-ok .sm2[data-l='3'] .br i:nth-child(-n+3){background:hsl(var(--primary))}.pg-ok .sm2[data-l='4'] .br i{background:#16a34a}" +
    ".pg-ok .rq{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:6px 12px}.pg-ok .rq li{display:flex;align-items:center;gap:6px;font-size:12.5px;color:hsl(var(--muted-foreground));transition:color .2s}" +
    ".pg-ok .rq li svg{width:14px;height:14px;padding:2px;border-radius:50%;border:1px solid hsl(var(--border));color:transparent;transition:.2s}.pg-ok .rq li.ok{color:hsl(var(--foreground))}.pg-ok .rq li.ok svg{background:#16a34a;border-color:#16a34a;color:#fff}" +
    /* alerts */
    ".pg-ok .al{display:none;align-items:flex-start;gap:10px;margin-top:14px;padding:12px 14px;border-radius:var(--radius);border:1px solid hsl(var(--border));font-size:13px;line-height:1.6}" +
    ".pg-ok .al b{display:block;font-weight:600}.pg-ok .al svg{margin-top:2px}" +
    ".pg-ok .al.er{color:hsl(var(--destructive, 0 84% 60%));border-color:hsl(var(--destructive, 0 84% 60%)/.5)}" +
    ".pg-ok .al.sc{border-color:rgb(22 163 74/.4)}.pg-ok .al.sc svg{color:#16a34a}" +
    ".pg-ok .au{display:none;margin-top:14px;padding:14px;border-radius:var(--radius);border:1px solid hsl(var(--border));background:hsl(var(--muted)/.4)}" +
    ".pg-ok .au p{margin:0 0 12px;font-size:13px;color:hsl(var(--muted-foreground))}" +
    ".pg-ok .au .g2x{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}" +
    /* lists */
    ".pg-ok .ls{display:flex;flex-direction:column;border:1px solid hsl(var(--border));border-radius:var(--radius);overflow:hidden}" +
    ".pg-ok .li{display:flex;align-items:center;gap:12px;padding:10px 12px;font-size:13px}.pg-ok .li + .li{border-top:1px solid hsl(var(--border))}" +
    ".pg-ok .li .fg{width:32px;height:32px;flex-shrink:0;border-radius:calc(var(--radius) - 2px);display:grid;place-items:center;font-size:17px;background:hsl(var(--muted))}" +
    ".pg-ok .li .tx{flex:1;min-width:0}.pg-ok .li .tx b{display:flex;flex-wrap:wrap;align-items:center;gap:6px;font-weight:500;line-height:1.5}" +
    ".pg-ok .hs .li .tx b{display:block;overflow-wrap:anywhere}@media(max-width:380px){.pg-ok .hs .li code{display:none}}" +
    ".pg-ok .hd,.pg-ok .ls,.pg-ok .li,.pg-ok .row,.pg-ok .fm,.pg-ok .fl,.pg-ok .hs,.pg-ok .lb{height:auto;background-color:transparent;font-size:inherit}.pg-ok .ls{background:none}" +
    ".pg-ok .li .tx small{display:block;font-size:12px;color:hsl(var(--muted-foreground));direction:ltr;text-align:start;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
    ".pg-ok .li time{font-size:12px;color:hsl(var(--muted-foreground));white-space:nowrap}" +
    ".pg-ok .em{padding:14px 12px;font-size:13px;color:hsl(var(--muted-foreground))}" +
    ".pg-ok .jc{display:none;margin-top:12px;padding:14px;border-radius:var(--radius);border:1px solid hsl(var(--border));background:hsl(var(--muted)/.4)}" +
    ".pg-ok .jc code{max-height:60px;overflow:hidden;font-size:11px;font-weight:500;filter:blur(4px)}.pg-ok .jc code.sh{filter:none;max-height:none}" +
    ".pg-ok .jc ol{margin:12px 0 0;padding-inline-start:18px;display:flex;flex-direction:column;gap:6px;font-size:13px;line-height:1.7;color:hsl(var(--muted-foreground))}" +
    ".pg-ok .jc ol kbd{direction:ltr;unicode-bidi:embed;font:500 12px ui-monospace,Menlo,Consolas,monospace;padding:1px 6px;border-radius:4px;border:1px solid hsl(var(--border));background:hsl(var(--background));color:hsl(var(--foreground))}" +
    ".pg-ok .hs{margin-top:16px;padding-top:16px;border-top:1px solid hsl(var(--border))}" +
    ".pg-ok .hs h4{margin:0 0 10px;font-size:13.5px;font-weight:600;display:flex;align-items:center;gap:8px}" +
    ".pg-ok .hs .li i{width:8px;height:8px;border-radius:50%;flex-shrink:0;background:hsl(var(--primary))}.pg-ok .hs .li.lp i{background:#16a34a}" +
    ".pg-ok .hs .li code{flex:none;display:inline;padding:0;border:0;background:none;font-size:12px;font-weight:500;color:hsl(var(--muted-foreground));cursor:default}" +
    ".pg-ok .toast{position:absolute;top:16px;inset-inline-end:16px;display:flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:calc(var(--radius) - 2px);border:1px solid hsl(var(--border));background:hsl(var(--popover, var(--background)));color:hsl(var(--popover-foreground, var(--foreground)));font-size:12.5px;font-weight:500;box-shadow:0 4px 12px rgb(0 0 0/.1);opacity:0;transform:translateY(-4px);transition:.2s;pointer-events:none}.pg-ok .toast.on{opacity:1;transform:none}" +
    ".pg-ok .toast svg{color:#16a34a}" +
    ".pg-ok textarea{width:100%;min-height:110px;padding:8px 12px;border-radius:calc(var(--radius) - 2px);border:1px solid hsl(var(--input, var(--border)));background:transparent;color:inherit;font:13px/1.7 ui-monospace,Menlo,Consolas,monospace;resize:vertical;box-shadow:0 1px 2px 0 rgb(0 0 0/.05)}" +
    ".pg-ok textarea:focus-visible{outline:none;box-shadow:0 0 0 2px hsl(var(--background)),0 0 0 4px hsl(var(--ring))}" +
    ".pg-ok select{height:32px;padding:0 8px;border-radius:calc(var(--radius) - 2px);border:1px solid hsl(var(--input, var(--border)));background:hsl(var(--background));color:inherit;font:inherit;font-size:13px}" +
    ".pg-ok .shr{display:inline-flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;margin-inline-start:auto}.pg-ok .shr input{width:16px;height:16px;accent-color:hsl(var(--primary))}" +
    ".pg-ok .ist{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0 0 14px}" +
    ".pg-ok .ist > div{min-width:0;padding:10px 12px;border:1px solid hsl(var(--border));border-radius:var(--radius);background:hsl(var(--muted)/.35)}" +
    ".pg-ok .ist small{display:block;font-size:11.5px;color:hsl(var(--muted-foreground));white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
    ".pg-ok .ist b{display:block;margin-top:2px;font-size:17px;font-weight:600;line-height:1.4;font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
    ".pg-ok .ipj{display:none;margin-top:12px;padding:12px;border:1px solid hsl(var(--border));border-radius:var(--radius)}" +
    ".pg-ok .iph{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:13px}.pg-ok .iph b{font-weight:500}" +
    ".pg-ok .iph .spn{width:14px;height:14px;flex-shrink:0;border-radius:50%;border:2px solid hsl(var(--primary)/.25);border-top-color:hsl(var(--primary));animation:jxspin .8s linear infinite}" +
    "@keyframes jxspin{to{transform:rotate(360deg)}}@keyframes jxin{from{opacity:0;transform:translateY(-3px)}}" +
    ".pg-ok .iph .ipc{margin-inline-start:auto;font-size:12px;color:hsl(var(--muted-foreground));font-variant-numeric:tabular-nums}" +
    ".pg-ok .ipj .pr{margin:10px 0}.pg-ok .ipv:empty{display:none}.pg-ok .ipv .li{animation:jxin .25s ease}" +
    ".pg-ok .ipj h5{margin:0 0 6px;font-size:12px;font-weight:500;color:hsl(var(--muted-foreground))}" +
    ".pg-ok .h4r{display:flex;align-items:center;gap:8px;margin:16px 0 8px}.pg-ok .h4r .bt{display:inline-flex!important;flex:none;flex-direction:row;flex-wrap:nowrap;width:auto}.pg-ok .h4r .bt[style*='none']{display:none!important}.pg-ok .h4r h4{flex:1;margin:0;font-size:13.5px;font-weight:600}" +
    ".pg-ok .li .tx b .bdg{height:18px;padding:0 6px;font-size:10.5px;font-weight:500}" +
    ".pg-ok .li .rm{width:30px;height:30px;color:hsl(var(--muted-foreground))}.pg-ok .li .rm:hover{color:hsl(var(--destructive, 0 84% 60%))}" +
    ".pg-ok .li.sp2{opacity:.7}.pg-ok .why{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}" +
    ".pg-ok .ibd{display:none;margin-top:12px;padding:10px 12px;border:1px solid hsl(var(--border));border-radius:var(--radius);font-size:13px}" +
    ".pg-ok .ibd summary{cursor:pointer;display:flex;align-items:center;gap:8px;list-style:none}.pg-ok .ibd summary::-webkit-details-marker{display:none}" +
    ".pg-ok .ibd .bl{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}.pg-ok .ibd .bl code{flex:none;display:inline-block;padding:2px 8px;font-size:12px;font-weight:500;cursor:default}" +
    ".pg-ok .ipv2{margin-top:8px;font-size:12px;color:hsl(var(--muted-foreground));line-height:1.8;overflow-wrap:anywhere}" +
    "@media(max-width:640px){.pg-ok .ist{grid-template-columns:repeat(2,minmax(0,1fr))}}" +
    "@media(max-width:640px){.pg-ok .shr{margin-inline-start:0;width:100%}.pg-ok .hd{padding:16px 16px 0}.pg-ok .bd{padding:14px 16px 16px}.pg-ok .tb{display:flex;width:100%}.pg-ok .tb button{flex:1 1 0;min-width:0;padding:0 6px;gap:5px;font-size:12px}.pg-ok .tb button span{overflow:hidden;text-overflow:ellipsis}.pg-ok .tb button:not(.on) svg{display:none}.pg-ok .au .g2x{grid-template-columns:1fr}.pg-ok .row .bt{flex:1}}" +
    "@media(prefers-reduced-motion:reduce){.pg-ok *{transition:none!important}}";
  function svg(p, w) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' + (w || 2) + '" stroke-linecap="round" stroke-linejoin="round">' + p + '</svg>'; }
  /* lucide icons (same set the panel uses) */
  var I = {
    x: svg('<path d="M18 6 6 18"/><path d="m6 6 12 12"/>'),
    key: svg('<path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4"/><path d="m21 2-9.6 9.6"/><circle cx="7.5" cy="15.5" r="5.5"/>'),
    shield: svg('<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'),
    lock: svg('<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>'),
    globe: svg('<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>'),
    copy: svg('<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>'),
    eye: svg('<path d="M2.06 12.35a1 1 0 0 1 0-.7 10.75 10.75 0 0 1 19.88 0 1 1 0 0 1 0 .7 10.75 10.75 0 0 1-19.88 0"/><circle cx="12" cy="12" r="3"/>'),
    eyeOff: svg('<path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.53 13.53 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><path d="m2 2 20 20"/><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/>'),
    refresh: svg('<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>'),
    wand: svg('<path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72"/><path d="m14 7 3 3"/><path d="M5 6v4"/><path d="M19 14v4"/><path d="M10 2v2"/><path d="M7 8H3"/><path d="M21 16h-4"/><path d="M11 3H9"/>'),
    check: svg('<path d="M20 6 9 17l-5-5"/>'),
    checkC: svg('<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>'),
    alert: svg('<circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>'),
    clock: svg('<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'),
    plus: svg('<path d="M5 12h14"/><path d="M12 5v14"/>'),
    trash: svg('<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>'),
    send: svg('<path d="M14.54 21.69a.5.5 0 0 0 .94-.03l6.5-19a.5.5 0 0 0-.64-.64l-19 6.5a.5.5 0 0 0-.03.94l7.93 3.18a2 2 0 0 1 1.11 1.11z"/><path d="m21.85 2.15-10.94 10.93"/>')
  };
  var SKEY = "pg-ok-live";

  /* ---------- owner access card on the API Keys page ---------- */
  function build(mode) {
    if (!document.getElementById("pg-ok-css")) { var st = document.createElement("style"); st.id = "pg-ok-css"; st.textContent = CSS; document.head.appendChild(st); }
    var box = document.createElement("section"); box.className = "pg-ok"; box.dataset.lang = lang(); box.dataset.mode = mode;
    box.dir = lang() === "fa" ? "rtl" : "ltr";
    var eyeBtn = '<button class="bt gh eye" type="button" aria-label="' + T("show") + '">' + I.eye + '</button>';
    box.innerHTML =
      '<div class="toast">' + I.check + '<span></span></div>' +
      '<div class="hd"><span class="ic">' + (mode === "loc" ? I.globe : mode === "ip" ? I.wand : I.shield) + '</span><div><h3>' + T(mode === "loc" ? "tLoc" : mode === "ip" ? "pIp" : mode === "pass" ? "pPass" : "title") + '</h3><p>' + T(mode === "loc" ? "dLoc" : mode === "ip" ? "dIp" : mode === "pass" ? "dPass" : "dOwner") + '</p></div></div>' +
      '<div class="bd">' +
        '<div class="tb" role="tablist">' +
          '<button type="button" role="tab" class="on" data-t="k">' + I.key + '<span>' + T("tKey") + '</span></button>' +
          '<button type="button" role="tab" data-t="p">' + I.lock + '<span>' + T("tPass") + '</span></button>' +
          '<button type="button" role="tab" data-t="l">' + I.globe + '<span>' + T("tLoc") + '</span></button>' +
          '<button type="button" role="tab" data-t="i">' + I.wand + '<span>' + T("tIp") + '</span></button>' +
        '</div>' +
        /* key */
        '<div class="pn on" data-p="k">' +
          '<ol class="stp"><li class="on"><i>' + num(1) + '</i>' + T("s1") + '</li><li><i>' + num(2) + '</i>' + T("s2") + '</li><li><i>' + num(3) + '</i>' + T("s3") + '</li></ol>' +
          '<button class="bt g1" type="button">' + I.key + '<span>' + T("getKey") + '</span></button>' +
          '<div class="kv"><div class="lb"><span>' + T("yourKey") + '</span><span class="bdg ok tm"><span class="dt"></span><span>5:00</span></span></div>' +
            '<div class="kc"><code></code><button class="bt ol icn cp" type="button" aria-label="' + T("copy") + '">' + I.copy + '</button></div>' +
            '<div class="pr"><i></i></div>' +
            '<div class="row"><button class="bt ol sm hd2" type="button">' + I.eyeOff + '<span>' + T("hide") + '</span></button><button class="bt ol sm nw" type="button">' + I.refresh + '<span>' + T("newKey") + '</span></button></div>' +
            '<p class="mt">' + T("keyNote") + '</p></div>' +
        '</div>' +
        /* password */
        '<div class="pn" data-p="p"><div class="fm">' +
          '<label class="fl"><span>' + T("np") + '</span><div class="ip"><input class="n1" type="password" autocomplete="new-password" spellcheck="false">' + eyeBtn + '</div></label>' +
          '<div class="sm2" data-l="0"><div class="br"><i></i><i></i><i></i><i></i></div><b>' + T("stIdle") + '</b></div>' +
          '<ul class="rq"><li data-r="len">' + I.check + T("rLen") + '</li><li data-r="mix">' + I.check + T("rMix") + '</li><li data-r="sp">' + I.check + T("rSp") + '</li><li data-r="eq">' + I.check + T("rEq") + '</li></ul>' +
          '<label class="fl"><span>' + T("np2") + '</span><div class="ip"><input class="n2" type="password" autocomplete="new-password" spellcheck="false">' + eyeBtn + '</div></label>' +
          '<div class="row"><button class="bt g3" type="button">' + I.check + '<span>' + T("save") + '</span></button><button class="bt ol gp" type="button">' + I.wand + '<span>' + T("gen") + '</span></button></div>' +
        '</div><div class="al sc dn">' + I.checkC + '<div><b>' + T("saved") + '</b>' + T("savedD") + '</div></div></div>' +
        /* locations */
        '<div class="pn" data-p="l">' +
          '<div class="ls lc"><div class="em">' + T("loading") + '</div></div>' +
          '<div class="row" style="margin-top:12px"><button class="bt g4" type="button">' + I.plus + '<span>' + T("add") + '</span></button><button class="bt ol g5" type="button">' + I.refresh + '<span>' + T("refresh") + '</span></button></div>' +
          '<div class="jc"><div class="lb"><span>' + T("code") + '</span></div><div class="kc"><code class="jcc"></code><button class="bt ol icn cp2" type="button" aria-label="' + T("copy") + '">' + I.copy + '</button><button class="bt ol icn sh2" type="button" aria-label="' + T("show") + '">' + I.eye + '</button></div>' +
            '<ol><li>' + T("g1") + '</li><li>' + T("g2") + '</li><li>' + T("g3") + '<kbd>JINX_MODE=node</kbd> <kbd>JINX_CODE=…</kbd></li><li>' + T("g4") + '</li><li>' + T("g5") + '</li></ol></div>' +
        '</div>' +
        /* clean IP (for everyone) */
        '<div class="pn" data-p="i">' +
          '<div class="ist"><div><small>' + T("ipS1") + '</small><b class="sv1">-</b></div><div><small>' + T("ipS2") + '</small><b class="sv2">-</b></div><div><small>' + T("ipS3") + '</small><b class="sv3">-</b></div><div><small>' + T("ipS4") + '</small><b class="sv4">-</b></div></div>' +
          '<p class="mt" style="margin:0 0 12px;line-height:1.8">' + T("ipD") + '</p>' +
          '<textarea class="ipt" dir="ltr" spellcheck="false" placeholder="' + T("ipPh") + '"></textarea>' +
          '<div class="row" style="margin-top:10px"><button class="bt ig" type="button">' + I.check + '<span>' + T("ipTest") + '</span></button><label class="bt ol iu2">' + I.plus + '<span>' + T("ipUp") + '</span><input type="file" class="ipf" accept=".txt,.csv,.json,text/plain" multiple hidden></label>' +
          '<label class="shr"><span>' + T("ipPer") + '</span><select class="ipr2"><option value="1">' + num(1) + '</option><option value="2" selected>' + num(2) + '</option><option value="3">' + num(3) + '</option><option value="5">' + num(5) + '</option><option value="10">' + num(10) + '</option></select></label>' +
          '<label class="shr" style="margin-inline-start:0"><input type="checkbox" class="ish" checked><span>' + T("ipShare") + '</span></label></div>' +
          '<div class="ipj"><div class="iph"><i class="spn"></i><b class="ipn"></b><span class="ipc"></span></div><div class="pr"><i class="ippb" style="width:0"></i></div><h5 class="ipvh">' + T("ipLive") + '</h5><div class="ls ipv"></div></div>' +
          '<details class="ibd"><summary>' + I.alert + '<b class="ibn"></b><span class="why"></span></summary><div class="bl"></div></details>' +
          '<div class="al sc igp">' + I.checkC + '<div><b class="ign"></b><span class="igd"></span></div></div>' +
          '<div class="h4r"><h4>' + T("ipList") + '</h4><button class="bt ol sm irt" type="button" style="display:none">' + I.refresh + '<span>' + T("ipRetest") + '</span></button></div>' +
          '<div class="ls ipl2"><div class="em">' + T("ipEmpty") + '</div></div>' +
          '<p class="ipv2"></p><p class="mt ipm"></p>' +
          '<div class="row" style="margin-top:10px"><button class="bt ol sm ic2" type="button" style="display:none">' + I.trash + '<span>' + T("ipClear") + '</span></button></div>' +
        '</div>' +
        /* shared */
        '<div class="au"><p>' + T("auth") + '</p><div class="g2x">' +
          '<label class="fl"><span>' + T("user") + '</span><input class="u" autocomplete="username" spellcheck="false"></label>' +
          '<label class="fl"><span>' + T("pass") + '</span><div class="ip"><input class="p" type="password" autocomplete="current-password">' + eyeBtn + '</div></label></div>' +
          '<button class="bt g2" type="button">' + I.check + '<span>' + T("ok") + '</span></button></div>' +
        '<div class="al er e">' + I.alert + '<div class="et"></div></div>' +
        '<div class="hs"><h4>' + I.clock + T("hist") + '</h4><div class="ls hl"><div class="em">' + T("hEmpty") + '</div></div></div>' +
      '</div>';
    /* one page = one part of the card */
    var only = mode === "loc" ? "l" : mode === "ip" ? "i" : mode === "pass" ? "p" : null;
    box.querySelectorAll(".tb button").forEach(function (b) { if (only ? true : (b.dataset.t === "l" || b.dataset.t === "i")) b.style.display = "none"; });
    if (only) {
      box.querySelector(".tb").style.display = "none"; if (mode !== "pass") box.querySelector(".hs").style.display = "none";
      box.querySelectorAll(".pn").forEach(function (pn) { pn.classList.toggle("on", pn.dataset.p === only); });
      box.querySelector(".pn[data-p=\"" + only + "\"]").style.marginTop = "0";
    }
    var q = function (s) { return box.querySelector(s); };
    var g1 = q(".g1"), g2 = q(".g2"), g3 = q(".g3"), gp = q(".gp"), au = q(".au"),
        iu = q(".u"), ip = q(".p"), n1 = q(".n1"), n2 = q(".n2"), sm = q(".sm2"), dn = q(".dn"),
        err = q(".e"), et = q(".et"), kv = q(".kv"), code = q(".kv code"), bar = q(".pr > i"), tm = q(".tm"), tmt = q(".tm span:last-child"),
        toast = q(".toast"), hl = q(".hl"), steps = box.querySelectorAll(".stp li"), tabs = box.querySelectorAll(".tb button"),
        timer, KEY = "", CREDS = null, pending = null;
    function step(n) { for (var i = 0; i < steps.length; i++) steps[i].classList.toggle("on", i < n); }
    function busy(btn, on) {
      var sp = btn.querySelector("span"); btn.disabled = on;
      if (on) { if (sp) { btn.dataset.l = sp.textContent; sp.textContent = T("wait"); } var s = document.createElement("i"); s.className = "sp"; btn.insertBefore(s, btn.firstChild); var sv = btn.querySelector("svg"); if (sv) sv.style.display = "none"; }
      else { if (sp && btn.dataset.l) sp.textContent = btn.dataset.l; var x = btn.querySelector(".sp"); if (x) x.remove(); var sv2 = btn.querySelector("svg"); if (sv2) sv2.style.display = ""; }
    }
    function fail(t) { et.textContent = t; err.style.display = "flex"; }
    function clear() { err.style.display = "none"; }
    function flash(t) { toast.querySelector("span").textContent = t || T("copied"); toast.classList.add("on"); clearTimeout(flash.t); flash.t = setTimeout(function () { toast.classList.remove("on"); }, 1600); }
    function copyText(txt, el, msg) {
      if (!txt) return;
      var done = function () { flash(msg); };
      var fb = function () { var r = document.createRange(); r.selectNodeContents(el); var s = getSelection(); s.removeAllRanges(); s.addRange(r); try { document.execCommand("copy"); done(); } catch (e) {} };
      try { if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(txt).then(done, fb); else fb(); } catch (e) { fb(); }
    }
    function copyKey() { copyText(KEY, code); }
    function history(list) {
      if (!list || !list.length) return;
      hl.textContent = "";
      list.slice().reverse().forEach(function (x) {
        var li = document.createElement("div"); li.className = "li" + (x.kind === "password" ? " lp" : "");
        li.innerHTML = '<i></i><div class="tx"><b></b></div><code></code><time></time>';
        li.querySelector("b").textContent = x.kind === "password" ? T("hPass") : T("hKey");
        li.querySelector("code").textContent = x.ip || "";
        li.querySelector("time").textContent = ago(x.t);
        hl.appendChild(li);
      });
    }
    /* one request helper: panel token first, owner login only if needed, then retry the same action */
    function call(path, body, btn, ok) {
      clear(); busy(btn, true);
      var tok = CREDS ? null : findToken(), hd = { "Content-Type": "application/json" }, b = {};
      if (tok) hd.Authorization = "Bearer " + tok;
      if (CREDS) { b.username = CREDS.u; b.password = CREDS.p; }
      for (var k in body) b[k] = body[k];
      return fetch(path, { method: "POST", headers: hd, body: JSON.stringify(b), credentials: "same-origin" })
        .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return [r.status, j || {}]; }); })
        .then(function (x) {
          busy(btn, false);
          if (x[0] === 200) { au.style.display = "none"; if (x[1].recent) history(x[1].recent); return ok(x[1]); }
          if (x[0] === 401 && x[1].need_login) {
            var had = !!CREDS; CREDS = null; pending = function () { call(path, body, btn, ok); };
            au.style.display = "block"; setTimeout(function () { (had ? ip : iu).focus(); }, 50);
            if (had) fail(lang() === "fa" ? (x[1].detail || T("eWrong")) : T("eWrong"));
            return;
          }
          fail(lang() === "fa" ? (x[1].detail || T("eGen")) : T("eGen"));
        })
        .catch(function () { busy(btn, false); fail(T("eNet")); });
    }
    function show(j, keep) {
      g1.style.display = "none"; kv.style.display = "block"; kv.classList.remove("dead", "warn", "bad");
      KEY = String(j.key); code.textContent = KEY; code.classList.remove("bl"); step(2);
      var total = j.ttl || 300, end = j.end || (Date.now() + total * 1000);
      try { sessionStorage.setItem(SKEY, JSON.stringify({ key: KEY, ttl: total, end: end })); } catch (e) {}
      if (!keep) copyKey();
      clearInterval(timer);
      function tk() {
        if (!document.body.contains(box)) { clearInterval(timer); return; }
        var s = Math.max(0, Math.round((end - Date.now()) / 1000)), f = s / total;
        bar.style.width = (f * 100).toFixed(2) + "%";
        var lvl = f > .4 ? "ok" : f > .15 ? "warn" : "bad";
        tm.className = "bdg tm " + lvl; kv.classList.toggle("warn", lvl === "warn"); kv.classList.toggle("bad", lvl === "bad");
        tmt.textContent = Math.floor(s / 60) + ":" + ("0" + s % 60).slice(-2);
        if (!s) { clearInterval(timer); kv.classList.add("dead"); tmt.textContent = T("expired"); KEY = ""; try { sessionStorage.removeItem(SKEY); } catch (e) {} }
      }
      tk(); timer = setInterval(tk, 500);
    }
    function getKey() { call("/jinx/key", {}, g1, function (j) { show(j); }); }
    var rq = box.querySelector(".rq");
    function rate() {
      var a = n1.value, b2 = n2.value, l = strength(a); sm.dataset.l = String(l);
      sm.querySelector("b").textContent = a ? T("st")[l] : T("stIdle");
      n2.classList.toggle("bad", !!b2 && b2 !== a);
      var R = { len: a.length >= 8, mix: /[A-Za-z]/.test(a) && /\d/.test(a), sp: !!a && !/\s/.test(a), eq: !!a && a === b2 };
      if (rq) rq.querySelectorAll("li").forEach(function (li) { li.classList.toggle("ok", !!R[li.dataset.r]); });
    }
    function savePass() {
      var a = n1.value, b = n2.value;
      if (a.length < 8) { fail(T("eShort")); n1.focus(); return; }
      if (/^\d+$/.test(a) || /^[A-Za-z]+$/.test(a)) { fail(T("eMix")); n1.focus(); return; }
      if (/\s/.test(a)) { fail(T("eSpace")); n1.focus(); return; }
      if (a !== b) { fail(T("eSame")); n2.focus(); return; }
      call("/jinx/password", { new_password: a }, g3, function (j) {
        var dd = dn.querySelector("div"); if (dd) { dd.innerHTML = "<b></b>"; dd.firstChild.textContent = T("saved"); dd.appendChild(document.createTextNode(j && j.verified ? T("vOk") + " " + T("savedD") : T("savedD"))); }
        dn.style.display = "flex"; if (CREDS) CREDS = { u: CREDS.u, p: a }; n1.value = n2.value = ""; n1.type = n2.type = "password"; rate();
        setTimeout(function () { dn.style.display = "none"; }, 9000);
      });
    }
    function login() {
      var u = iu.value.trim(), p = ip.value;
      if (!u || !p) { fail(T("eFill")); return; }
      CREDS = { u: u, p: p }; ip.value = "";
      if (pending) { var f = pending; pending = null; au.style.display = "none"; f(); }
    }
    /* locations */
    var lc = q(".lc"), g4 = q(".g4"), g5 = q(".g5"), jc = q(".jc"), jcc = q(".jcc"), JCODE = "", locLoaded = false;
    function badge(l, me) {
      if (l.stale) return '<span class="bdg bad"><span class="dt"></span>' + T("offline") + '</span>';
      if (l.status === "connected") return '<span class="bdg ok"><span class="dt"></span>' + T("connected") + '</span>';
      return '<span class="bdg warn"><span class="dt"></span>' + T("connecting") + '</span>';
    }
    function row(l, me) {
      var r = document.createElement("div"); r.className = "li";
      r.innerHTML = '<span class="fg"></span><div class="tx"><b><span class="nm"></span></b><small></small></div>' + badge(l, me);
      r.querySelector(".fg").textContent = l.flag || "🌐";
      r.querySelector(".nm").textContent = l.loc || "—";
      if (me) { var e = document.createElement("span"); e.className = "bdg"; e.textContent = T("main"); r.querySelector("b").appendChild(e); }
      r.querySelector("small").textContent = (l.domain || T("noDom")) + (l.last && !me ? "  ·  " + ago(l.last) : "");
      if (!me) {
        var x = document.createElement("button"); x.type = "button"; x.className = "bt gh icn rm"; x.innerHTML = I.trash; x.setAttribute("aria-label", "remove");
        x.onclick = function () {
          if (x.dataset.c !== "1") { x.dataset.c = "1"; x.style.color = "hsl(var(--destructive, 0 84% 60%))"; flash(T("rmAsk")); setTimeout(function () { x.dataset.c = ""; x.style.color = ""; }, 2500); return; }
          call("/jinx/locations", { remove: l.id }, g5, renderLoc);
        };
        r.appendChild(x);
      }
      return r;
    }
    function renderLoc(j) {
      locLoaded = true; lc.textContent = ""; JCODE = j.code || "";
      if (j.here) lc.appendChild(row(j.here, true));
      (j.locations || []).forEach(function (l) { lc.appendChild(row(l, false)); });
      if (!(j.locations || []).length) { var m = document.createElement("div"); m.className = "em"; m.textContent = T("lEmpty"); lc.appendChild(m); }
      if (JCODE) jcc.textContent = JCODE;
    }
    function loadLoc() { call("/jinx/locations", {}, g5, renderLoc); }
    g5.onclick = loadLoc;
    g4.onclick = function () {
      var open = function () { if (!JCODE) { fail(T("needDom")); return; } jc.style.display = "block"; jcc.textContent = JCODE; copyText(JCODE, jcc, T("codeOk")); };
      if (locLoaded && JCODE) open(); else call("/jinx/locations", {}, g4, function (j) { renderLoc(j); open(); });
    };
    jcc.onclick = function () { copyText(JCODE, jcc, T("codeOk")); };
    q(".cp2").onclick = function () { copyText(JCODE, jcc, T("codeOk")); };
    var sh2 = q(".sh2"); sh2.onclick = function () { var on = jcc.classList.toggle("sh"); sh2.innerHTML = on ? I.eyeOff : I.eye; };
    /* clean IP (owner list): test, find country, link to a location, live progress, remove one, re-check */
    var ipr2 = q(".ipr2"), igp = q(".igp"), ipt = q(".ipt"), ig = q(".ig"), ipf = q(".ipf"), ish = q(".ish"), ipj = q(".ipj"),
        ippb = q(".ippb"), ipn = q(".ipn"), ipc = q(".ipc"), ipv = q(".ipv"), ipvh = q(".ipvh"), ibd = q(".ibd"), ipl2 = q(".ipl2"),
        ic2 = q(".ic2"), irt = q(".irt"), ipm = q(".ipm"), ipv2 = q(".ipv2"), ipLoaded = false, quiet = document.createElement("button");
    var IPX = {};
    function cName(x) { return lang() === "fa" ? (x.fa || x.en || x.cc || "") : (x.en || x.cc || ""); }
    function msCls(ms) { return ms < 150 ? "ok" : ms < 400 ? "warn" : "bad"; }
    function el(tag, cls, txt) { var e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; }
    function ipRow(x, opt) {
      var r = el("div", "li" + (opt && opt.spare ? " sp2" : "")), f = el("span", "fg");
      if (x.flag) f.textContent = x.flag; else f.innerHTML = I.globe;
      var tx = el("div", "tx"), b = el("b"), place = [cName(x), x.city].filter(Boolean).join(" · ");
      b.appendChild(el("span", null, place || (x.ip + "")));
      if (x.via) b.appendChild(el("span", "bdg", T("ipVia") + x.via));
      if (opt && opt.state) b.appendChild(el("span", "bdg" + (opt.spare ? "" : " ok"), opt.state));
      var sm2 = el("small", null, place ? x.ip + (x.port && x.port !== 443 ? ":" + x.port : "") + (x.isp ? " · " + x.isp : "") : (x.port && x.port !== 443 ? "port " + x.port : "TLS · WebSocket"));
      tx.appendChild(b); tx.appendChild(sm2); r.appendChild(f); r.appendChild(tx);
      var bd = el("span", "bdg " + msCls(x.ms)); bd.appendChild(el("i", "dt")); bd.appendChild(document.createTextNode(num(x.ms) + T("ms"))); r.appendChild(bd);
      if (opt && opt.rm) {
        var rb = el("button", "bt gh icn rm"); rb.type = "button"; rb.setAttribute("aria-label", T("ipRm")); rb.innerHTML = I.x;
        rb.onclick = function () {
          if (rb.dataset.c !== "1") { rb.dataset.c = "1"; flash(T("rmAsk")); setTimeout(function () { rb.dataset.c = ""; }, 2500); return; }
          call("/jinx/ip/remove", { ip: x.ip, port: x.port }, rb, function (j) { ipRender(j.mine); flash(T("ipApplied")); });
        };
        r.appendChild(rb);
      }
      return r;
    }
    function ipStats(m) {
      var ips = (m && m.ips) || [], per = (m && m.per) || 2, use = ips.slice(0, per), cc = {};
      use.forEach(function (x) { if (x.cc) cc[x.cc] = 1; });
      q(".sv1").textContent = num(use.length) + (ips.length > use.length ? (lang() === "fa" ? " از " : " / ") + num(ips.length) : "");
      q(".sv2").textContent = Object.keys(cc).length ? num(Object.keys(cc).length) : "-";
      q(".sv3").textContent = ips.length ? num(Math.min.apply(null, ips.map(function (x) { return x.ms; }))) + T("ms") : "-";
      q(".sv4").textContent = m && m.checked ? ago(m.checked) : "-";
    }
    function ipRender(m) {
      ipLoaded = true; ipl2.textContent = ""; ipStats(m); ipv2.textContent = "";
      if (!m || !m.count) { igp.style.display = "none"; ipl2.appendChild(el("div", "em", T("ipEmpty"))); ic2.style.display = irt.style.display = "none"; ipm.textContent = ""; return; }
      if (m.share != null) ish.checked = !!m.share;
      if (m.per) ipr2.value = String(m.per);
      igp.style.display = "flex"; q(".ign").textContent = T("ipGroup") + " ◈ JinX Phantom"; q(".igd").textContent = " " + T("ipGroupD");
      var per = m.per || 2;
      m.ips.forEach(function (x, i) { ipl2.appendChild(ipRow(x, { rm: true, spare: i >= per, state: i < per ? T("ipUse") + " · IP" + num(i + 1) : T("ipSpare") })); });
      var x0 = m.ips[0], smp = (IPX.sample || "Pro"), ttl = IPX.title || "";
      ipv2.textContent = T("ipPrev") + (x0.flag ? x0.flag + " " : "") + "◈ " + smp + (x0.fa || x0.en ? " · " + (x0.fa || x0.en) : "") + " · IP1" + (ttl ? " | " + ttl : "");
      ic2.style.display = irt.style.display = ""; ipm.textContent = T("ipAuto");
    }
    function ipLoad() { call("/jinx/ip/get", {}, quiet, function (j) { IPX = j || {}; ipRender(j.mine); if (IPJ) ipPoll(IPJ); }); }
    function phase(s) { return s.phase === "geo" ? T("phGeo") : s.phase === "loc" ? T("phLoc") : T("phTest"); }
    function whyName(k) { return T({ tcp: "wTcp", tls: "wTls", http: "wHttp", ws: "wWs" }[k] || "eGen"); }
    function showBad(s) {
      var n = 0, w = ibd.querySelector(".why"), bl = ibd.querySelector(".bl"); w.textContent = ""; bl.textContent = "";
      for (var k in s.fails || {}) { n += s.fails[k]; w.appendChild(el("span", "bdg bad", whyName(k) + " " + num(s.fails[k]))); }
      if (!n) { ibd.style.display = "none"; return; }
      ibd.querySelector(".ibn").textContent = num(n) + T("ipBadN");
      (s.bad || []).forEach(function (x) { var c = el("code", null, x.ip + (x.port !== 443 ? ":" + x.port : "")); c.title = whyName(x.why); bl.appendChild(c); });
      ibd.style.display = "block";
    }
    function ipPoll(jid) {
      IPJ = jid; ipj.style.display = "block"; ig.disabled = true; ibd.style.display = "none";
      var got = false;
      var pr = call("/jinx/ip/job", { job: jid }, quiet, function (s2) { got = true;
        var pct = s2.phase === "test" ? Math.round(100 * s2.tested / Math.max(1, s2.total)) : 100;
        ippb.style.width = Math.max(3, pct) + "%"; ipn.textContent = phase(s2);
        ipc.textContent = (lang() === "fa" ? num(s2.tested) + " از " + num(s2.total) : s2.tested + "/" + s2.total) + " · " + num(s2.ok) + T("ipOkN") + " · " + num(s2.tested - s2.ok) + T("ipBadN");
        ipv.textContent = ""; (s2.live || []).forEach(function (x) { ipv.appendChild(ipRow(x)); }); ipvh.style.display = ipv.childNodes.length ? "" : "none";
        if (!s2.done) { setTimeout(function () { if (IPJ === jid && document.body.contains(ipj)) ipPoll(jid); }, 900); return; }
        IPJ = null; ig.disabled = false; ipj.style.display = "none"; showBad(s2);
        if (!s2.results.length) { fail(T("ipNone")); return; }
        call("/jinx/ip/save", { ips: s2.results.slice(0, 40), mode: "both", per: +ipr2.value, share: ish.checked }, ig, function (r) { ipt.value = ""; ipRender(r.mine); flash(T("ipApplied")); });
      });
      if (pr && pr.then) pr.then(function () { if (!got && IPJ === jid) { IPJ = null; ig.disabled = false; ipj.style.display = "none"; } });
    }
    function ipRun(text) {
      if (!text.trim()) { fail(T("ipPh")); ipt.focus(); return; }
      call("/jinx/ip/test", { text: text }, ig, function (j) { ippb.style.width = "3%"; ipv.textContent = ""; ipPoll(j.job); });
    }
    ig.onclick = function () { ipRun(ipt.value); };
    ipt.onkeydown = function (e) { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) ipRun(ipt.value); };
    ipf.onchange = function () {
      var fs = Array.prototype.slice.call(ipf.files || []).slice(0, 10);
      Promise.all(fs.map(function (f) { return f.size > 1048576 ? "" : f.text ? f.text() : ""; })).then(function (ts) { ipf.value = ""; ipt.value = ts.join("\n"); ipRun(ipt.value); });
    };
    ish.onchange = ipr2.onchange = function () { call("/jinx/ip/get", {}, quiet, function (j) { var m = j.mine; if (m && m.count) call("/jinx/ip/save", { ips: m.ips, mode: m.mode, per: +ipr2.value, share: ish.checked }, quiet, function (r) { ipRender(r.mine); flash(T("ipApplied")); }); }); };
    irt.onclick = function () { call("/jinx/ip/retest", {}, irt, function (j) { ipRender(j.mine); flash(T("ipRetOk")); }); };
    ic2.onclick = function () {
      if (ic2.dataset.c !== "1") { ic2.dataset.c = "1"; flash(T("rmAsk")); setTimeout(function () { ic2.dataset.c = ""; }, 2500); return; }
      call("/jinx/ip/clear", {}, ic2, function (r) { ipRender(r.mine); });
    };
    /* wiring */
    for (var t = 0; t < tabs.length; t++) tabs[t].onclick = function () {
      var w = this.dataset.t; clear();
      for (var i = 0; i < tabs.length; i++) { tabs[i].classList.toggle("on", tabs[i] === this); tabs[i].setAttribute("aria-selected", tabs[i] === this ? "true" : "false"); }
      box.querySelectorAll(".pn").forEach(function (p) { p.classList.toggle("on", p.dataset.p === w); });
      if (w === "p") setTimeout(function () { n1.focus(); }, 60);
      if (w === "l" && !locLoaded) loadLoc();
      if (w === "i" && !ipLoaded) ipLoad();
    };
    box.querySelectorAll(".eye").forEach(function (e) { e.onclick = function () { var i = e.parentNode.querySelector("input"); var on = i.type === "password"; i.type = on ? "text" : "password"; e.innerHTML = on ? I.eyeOff : I.eye; }; });
    g1.onclick = getKey; g2.onclick = login; g3.onclick = savePass;
    gp.onclick = function () { var p = genPass(); n1.value = n2.value = p; n1.type = n2.type = "text"; rate(); clear(); copyText(p, n1, T("genOk")); };
    n1.oninput = rate; n2.oninput = rate;
    n2.onkeydown = function (e) { if (e.key === "Enter") savePass(); }; n1.onkeydown = function (e) { if (e.key === "Enter") n2.focus(); };
    ip.onkeydown = function (e) { if (e.key === "Enter") login(); }; iu.onkeydown = function (e) { if (e.key === "Enter") ip.focus(); };
    code.onclick = copyKey; q(".cp").onclick = copyKey;
    var hb = q(".hd2"); hb.onclick = function () { var b = code.classList.toggle("bl"); hb.innerHTML = (b ? I.eye : I.eyeOff) + '<span>' + (b ? T("show") : T("hide")) + '</span>'; };
    q(".nw").onclick = function () { clearInterval(timer); kv.style.display = "none"; try { sessionStorage.removeItem(SKEY); } catch (e) {} step(1); g1.style.display = ""; getKey(); };
    try { var live = JSON.parse(sessionStorage.getItem(SKEY) || "null"); if (live && live.end > Date.now() + 2000) show(live, true); } catch (e) {}
    var tk0 = findToken();
    if (tk0) fetch("/jinx/history", { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + tk0 }, body: "{}", credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; }).then(function (j) { if (j && j.recent) history(j.recent); }).catch(function () {});
    if (only === "l") setTimeout(loadLoc, 0);
    if (only === "i") setTimeout(ipLoad, 0);
    if (only === "p") setTimeout(function () { try { if (window.matchMedia && matchMedia("(hover:hover)").matches) n1.focus({ preventScroll: true }); } catch (e) {} }, 80);
    return box;
  }

  /* ---------- 2) owner items inside the panel's own menu ("Change password", "Proxy IP") + their pages ---------- */
  var PAGES = [["pass", "lock", "pPass"], ["ip", "globe", "pIp"]];
  var SETTINGS = ["تنظیمات", "settings", "настройки", "设置"].map(norm);
  var CUR = null, host = null, openedAt = "", placeT = 0, PKEY = "jx-page";
  try { CUR = sessionStorage.getItem(PKEY) || null; if (CUR && !/^(pass|ip)$/.test(CUR)) CUR = null; } catch (e) {}
  function cls(el) { return el ? String(el.className && el.className.baseVal != null ? el.className.baseVal : el.className || "") : ""; }
  function makeItem(pg, ti, tb) {
    var li = document.createElement("li"); li.className = (cls(ti) + " jx-li").trim(); li.setAttribute("data-sidebar", "menu-item"); li.dataset.jxp = pg[0]; li.dataset.lang = lang();
    var bt = document.createElement("button"); bt.type = "button"; bt.className = (cls(tb) + " jx-btn").trim(); bt.setAttribute("data-sidebar", "menu-button");
    if (tb && tb.getAttribute("data-size")) bt.setAttribute("data-size", tb.getAttribute("data-size"));
    bt.dataset.jxp = pg[0]; bt.setAttribute("data-active", CUR === pg[0] ? "true" : "false");
    bt.innerHTML = I[pg[1]] + "<span>" + T(pg[2]) + "</span>";
    bt.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); openPage(pg[0]); closeMobileMenu(); });
    li.appendChild(bt); return li;
  }
  function settingsItem(menu) {
    var lis = menu.querySelectorAll('[data-sidebar="menu-item"]:not(.jx-li)');
    for (var i = 0; i < lis.length; i++) {
      var a = lis[i].querySelector("a"), h = a && a.getAttribute("href") || "";
      if (/\/settings?(\/|\?|#|$)/i.test(h) || SETTINGS.indexOf(norm(lis[i].textContent).replace(/[0-9۰-۹]+/g, "").trim()) > -1) return lis[i];
    }
    return null;
  }
  function sidebarGroup() {
    var all = document.querySelectorAll("li.jx-li");
    if (OWNER !== true) { for (var r = 0; r < all.length; r++) all[r].remove(); return; }
    var cs = document.querySelectorAll('[data-sidebar="content"]');
    for (var i = 0; i < cs.length; i++) {
      var c = cs[i], mine = c.querySelectorAll("li.jx-li");
      if (mine.length === PAGES.length && mine[0].dataset.lang === lang()) {   /* already in place: never move it (no jumping) */
        for (var k = 0; k < mine.length; k++) { var b = mine[k].firstChild, on = mine[k].dataset.jxp === CUR ? "true" : "false"; if (b && b.getAttribute("data-active") !== on) b.setAttribute("data-active", on); }
        continue;
      }
      for (var m = 0; m < mine.length; m++) mine[m].remove();
      var menus = c.querySelectorAll('[data-sidebar="menu"]'), menu = null, anchor = null;
      for (var j = 0; j < menus.length && !anchor; j++) { anchor = settingsItem(menus[j]); if (anchor) menu = menus[j]; }
      if (!menu) menu = menus[0];
      if (!menu || !menu.querySelector('[data-sidebar="menu-button"]')) continue;   /* menu not drawn yet */
      var ti = menu.querySelector('[data-sidebar="menu-item"]:not(.jx-li)'), tb = menu.querySelector('[data-sidebar="menu-button"]:not(.jx-btn)');
      var ref = anchor ? anchor.nextSibling : null;
      PAGES.forEach(function (pg) { var li = makeItem(pg, ti, tb); if (ref) menu.insertBefore(li, ref); else menu.appendChild(li); });
    }
    if (!document.getElementById("jx-grp-css")) {
      var st = document.createElement("style"); st.id = "jx-grp-css";
      st.textContent = ".jx-li .jx-btn svg{width:16px;height:16px;flex-shrink:0}.jx-li .jx-btn span{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}" +
        "#jx-page{position:fixed;z-index:40;overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;background:hsl(var(--background));color:hsl(var(--foreground));font-family:inherit}" +
        "#jx-page .jxw{max-width:880px;margin:0 auto;padding:24px 16px 56px}#jx-page .jxh{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 18px}" +
        "#jx-page .jxh h1{margin:0;font-size:22px;font-weight:700;line-height:1.35;letter-spacing:-.01em}#jx-page .jxh p{margin:2px 0 0;font-size:13.5px;color:hsl(var(--muted-foreground))}" +
        "#jx-page .jxx{display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;flex-shrink:0;border-radius:calc(var(--radius) - 2px);border:1px solid hsl(var(--border));background:hsl(var(--background));color:hsl(var(--foreground));cursor:pointer}#jx-page .jxx:hover{background:hsl(var(--accent))}#jx-page .jxx svg{width:16px;height:16px}" +
        "@media(max-width:640px){#jx-page .jxw{padding:16px 12px 48px}#jx-page .jxh h1{font-size:19px}}";
      document.head.appendChild(st);
    }
  }
  function closeMobileMenu() {
    /* the mobile menu is a dialog (sheet): Escape closes it the same way the panel does */
    var m = document.querySelector('[data-sidebar="sidebar"][data-mobile="true"]');
    if (!m) return;
    try { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, which: 27, bubbles: true })); } catch (e) {}
    try { var ov = document.querySelector("[data-radix-dialog-overlay], [data-state=open][data-slot=sheet-overlay]"); if (ov && document.querySelector('[data-sidebar="sidebar"][data-mobile="true"]')) ov.click(); } catch (e) {}
  }
  function ensureHost() {
    if (host && document.body.contains(host)) return host;
    host = document.createElement("div"); host.id = "jx-page"; host.setAttribute("role", "region");
    /* typing here belongs to us: never let panel-wide hotkeys see these keys */
    ["keydown", "keyup", "keypress"].forEach(function (ev) { host.addEventListener(ev, function (e) { e.stopPropagation(); }); });
    document.body.appendChild(host); return host;
  }
  function visible(el) { if (!el) return false; var r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }
  function place() {
    if (!host || !CUR) return;
    var m = document.querySelector("main"), r = m && visible(m) ? m.getBoundingClientRect() : null, W = window.innerWidth, H = window.innerHeight;
    var left = 0, width = W, top = 0;
    if (r) { left = Math.max(0, r.left); width = Math.max(240, Math.min(W - left, r.right - left)); top = Math.max(0, r.top); }
    else { var sb = document.querySelector('[data-sidebar="sidebar"]:not([data-mobile="true"])'); if (visible(sb)) { var q = sb.getBoundingClientRect(); if (q.left < W / 2) { left = q.right; width = W - q.right; } else width = q.left; } }
    /* keep the panel's own top bar (with the menu button) visible */
    var bars = [], trs = document.querySelectorAll('[data-sidebar="trigger"]');
    for (var i = 0; i < trs.length; i++) if (!trs[i].closest('[data-sidebar="sidebar"]') && !trs[i].closest("#jx-page")) bars.push(trs[i].closest("header") || trs[i].parentElement);
    if (m) { var mh = m.querySelector("header"); if (mh) bars.push(mh); }
    for (var j = 0; j < bars.length; j++) {
      var bar = bars[j]; if (!visible(bar)) continue; var br = bar.getBoundingClientRect();
      if (br.height < 140 && br.top <= top + 12 && br.bottom > 0 && br.bottom < H / 2 && br.left < left + width && br.right > left) top = Math.max(top, br.bottom);
    }
    var s = host.style, v = [Math.round(top) + "px", Math.round(left) + "px", Math.round(width) + "px"];
    if (s.top !== v[0]) s.top = v[0]; if (s.left !== v[1]) s.left = v[1]; if (s.width !== v[2]) s.width = v[2]; if (s.bottom !== "0px") s.bottom = "0px";
  }
  function render() {
    ensureHost(); host.dir = lang() === "fa" ? "rtl" : "ltr";
    var cur = host.querySelector(".pg-ok");
    if (cur && cur.dataset.mode === CUR && cur.dataset.lang === lang()) return;
    var keep = {};
    if (cur && cur.dataset.mode === CUR) [".n1", ".n2", ".ipt"].forEach(function (k) { var e = cur.querySelector(k); if (e && e.value) keep[k] = e.value; });
    host.textContent = "";
    var w = document.createElement("div"); w.className = "jxw";
    var pg = PAGES.filter(function (x) { return x[0] === CUR; })[0];
    var hd = document.createElement("div"); hd.className = "jxh";
    hd.innerHTML = "<div><h1></h1></div>" + '<button type="button" class="jxx" aria-label="close">' + svg('<path d="M18 6 6 18"/><path d="m6 6 12 12"/>') + "</button>";
    hd.querySelector("h1").textContent = T(pg[2]); hd.querySelector(".jxx").onclick = function () { closePage(false); };
    w.appendChild(hd);
    var box = build(CUR); var inner = box.querySelector(".hd"); if (inner) inner.style.display = "none";
    var desc = document.createElement("p"); desc.textContent = T(CUR === "loc" ? "dLoc" : CUR === "ip" ? "dIp" : CUR === "pass" ? "dPass" : "dOwner"); hd.firstChild.appendChild(desc);
    box.querySelector(".bd").style.paddingTop = "20px";
    w.appendChild(box); host.appendChild(w); host.scrollTop = 0;
    for (var k in keep) { var e = box.querySelector(k); if (e) { e.value = keep[k]; try { e.dispatchEvent(new Event("input")); } catch (x) {} } }
  }
  function dimNative(on, restore) {
    var bs = document.querySelectorAll('[data-sidebar="menu-button"]:not(.jx-btn)');
    for (var i = 0; i < bs.length; i++) {
      var b = bs[i];
      if (on) { if (b.getAttribute("data-active") === "true") { b.setAttribute("data-jx-was", "1"); b.setAttribute("data-active", "false"); } }
      else if (b.getAttribute("data-jx-was")) { b.removeAttribute("data-jx-was"); if (restore) b.setAttribute("data-active", "true"); }
    }
  }
  function openPage(id) {
    CUR = id; openedAt = location.pathname + location.hash; try { sessionStorage.setItem(PKEY, id); } catch (e) {}
    render(); host.style.display = "block"; place(); sidebarGroup(); dimNative(true);
    clearInterval(placeT); placeT = setInterval(function () { if (!CUR) { clearInterval(placeT); return; } place(); }, 400);
  }
  function closePage(byPanel) {
    if (!CUR) return; CUR = null; clearInterval(placeT); try { sessionStorage.removeItem(PKEY); } catch (e) {}
    dimNative(false, !byPanel);
    if (host) { host.style.display = "none"; host.textContent = ""; }
    sidebarGroup();
  }
  /* any normal menu click (or the panel changing page) closes our page */
  document.addEventListener("click", function (e) {
    if (!CUR) return; var t = e.target;
    if (!t || !t.closest || t.closest(".jx-li") || t.closest("#jx-page")) return;
    var hit = t.closest('[data-sidebar="menu-button"], [data-sidebar="menu-sub-button"], aside a, nav a');
    if (hit) closePage(true);
  }, true);
  addEventListener("popstate", function () { if (CUR) closePage(true); });
  addEventListener("resize", function () { if (CUR) place(); });
  function pages() {
    sidebarGroup();
    if (!CUR) return;
    if (OWNER === false || !findToken()) { closePage(true); return; }  /* logged out or reseller */
    if (OWNER !== true) return;                                         /* still checking who you are */
    if (openedAt && openedAt !== location.pathname + location.hash) { closePage(true); return; }
    if (!host || !document.body.contains(host) || host.style.display === "none") { openPage(CUR); return; }
    render(); place(); dimNative(true);
  }

  /* ---------- sidebar: Telegram channel, as a normal menu item ---------- */
  var CHANNEL = "https://t.me/+WvKFv0lU_i5lNGE0";
  function channelItem() {
    var foot = document.querySelector('[data-sidebar="footer"]');
    var old = document.getElementById("pg-ch");
    if (old && old.dataset.lang === lang()) return;
    if (old) old.remove();
    if (!foot) return;
    if (!document.getElementById("pg-ch-css")) {
      var st = document.createElement("style"); st.id = "pg-ch-css";
      st.textContent = "#pg-ch{display:flex;align-items:center;gap:8px;height:32px;margin:0 0 4px;padding:0 8px;border-radius:calc(var(--radius) - 2px);color:hsl(var(--sidebar-foreground, var(--foreground)));text-decoration:none;font-size:14px;transition:background .15s}" +
        "#pg-ch:hover{background:hsl(var(--sidebar-accent, var(--accent)));color:hsl(var(--sidebar-accent-foreground, var(--accent-foreground)))}" +
        "#pg-ch svg{width:16px;height:16px;flex-shrink:0}#pg-ch span{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}" +
        "[data-state=collapsed] #pg-ch{justify-content:center;padding:0}[data-state=collapsed] #pg-ch span{display:none}";
      document.head.appendChild(st);
    }
    var a = document.createElement("a"); a.id = "pg-ch"; a.dataset.lang = lang(); a.href = CHANNEL; a.target = "_blank"; a.rel = "noopener noreferrer";
    a.innerHTML = I.send + '<span>' + T("channel") + '</span>';
    foot.insertBefore(a, foot.firstChild);
  }

  /* ---------- run + keep up with page changes ---------- */
  var queued = false;
  function tick() {
    try { sweep(); } catch (e) { /* never break the panel */ }
    try { pages(); } catch (e) {}
    try { channelItem(); } catch (e) {}
  }
  var lastRun = 0;
  function run() { queued = false; lastRun = Date.now(); LANG = null; tick(); }
  function schedule() {             /* at most ~8 times a second, so busy panel pages and language switches stay smooth */
    if (queued) return; queued = true;
    var wait = Math.max(0, 120 - (Date.now() - lastRun));
    setTimeout(function () { if (document.hidden) run(); else requestAnimationFrame(run); }, wait);
  }
  function outside(recs) { for (var i = 0; i < recs.length; i++) { var t = recs[i].target; if (!(host && (t === host || host.contains(t))) && !(t.closest && t.closest(".jx-li")) && !(t.id === "pg-ch")) return true; } return false; }
  function start() { tick(); new MutationObserver(function (r) { if (outside(r)) schedule(); }).observe(document.body, { childList: true, subtree: true }); addEventListener("popstate", schedule); addEventListener("storage", schedule);
    new MutationObserver(schedule).observe(document.documentElement, { attributes: true, attributeFilter: ["dir", "lang", "class"] }); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
