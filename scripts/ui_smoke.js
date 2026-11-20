const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");
const BASE = process.env.BASE || "http://127.0.0.1:8088";
const FRONT = path.resolve(__dirname, "../frontend");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const html = fs
    .readFileSync(path.join(FRONT, "index.html"), "utf8")
    .replace(/<script[^>]*><\/script>/g, "");
  const dom = new JSDOM(html, {
    url: BASE + "/",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });

  const w = dom.window,
    d = w.document,
    errs = [];

  w.fetch = (u, o) => fetch(String(u).startsWith("/") ? BASE + u : u, o);
  w.scrollTo = () => {};
  w.prompt = () => "test reason";
  w.confirm = () => true;
  w.console.error = (...a) => errs.push(a.join(" "));
  w.addEventListener("error", (e) => errs.push("ERR " + e.message));
  w.eval(fs.readFileSync(path.join(FRONT, "app.js"), "utf8"));

  const q = (s) => d.querySelectorAll(s),
    txt = (s) => (d.querySelector(s) || {}).textContent || "";
  const nav = async (hash, ms = 1200) => {
    w.location.hash = hash;
    await sleep(ms);
  };

  let fails = 0;

  const ok = (cond, msg) => {
    console.log((cond ? "  ✓ " : "  ✗ FAIL: ") + msg);
    if (!cond) fails++;
  };

  const login = async (email) => {
    await nav("#/login", 600);

    const f = d.querySelector("form.form");

    const inputs = f.querySelectorAll("input");
    inputs[0].value = email;
    inputs[1].value = "demo12345";

    f.dispatchEvent(new w.Event("submit", { cancelable: true, bubbles: true }));

    await sleep(1500);
  };

  await sleep(1500);
  ok(q(".card").length >= 5, `главная: ${q(".card").length} карточек видео`);
  ok(txt("#topbar").includes("Войти"), "аноним видит кнопку «Войти»");

  await nav("#/search/" + encodeURIComponent("Тест"));
  ok(q(".row").length >= 1, `поиск «Тест»: ${q(".row").length} результатов`);

  await nav("#/search/" + encodeURIComponent("zzzzнетТакого"));
  ok(txt("#app").includes("Ничего не найдено"), "поиск: пустая выдача");

  await nav("#/channel/alice");
  ok(
    txt("#app").includes("Alice") && q(".tabs button").length === 2,
    "канал: шапка и вкладки",
  );
  ok(
    q(".channel-head .btn").length >= 1 &&
      txt(".channel-head").includes("Подписаться"),
    "канал: кнопка подписки",
  );

  await nav("#/");
  const href = d.querySelector(".card a").getAttribute("href");
  await nav(href, 1800);

  ok(
    q(".watch h1").length === 1 && q(".player").length === 1,
    "просмотр: плеер и заголовок",
  );
  ok(
    q(".comment").length >= 1,
    `просмотр: ${q(".comment").length} комментариев`,
  );
  ok(q(".row.small").length >= 1, "просмотр: рекомендации справа");

  await nav("#/upload");
  ok(txt("#app").includes("войти"), "загрузка без входа просит войти");

  await login("alice@demo.local");
  ok(txt("#topbar").includes("Выйти"), "вход: шапка показывает «Выйти»");

  await nav("#/studio");
  ok(
    q("table tbody tr").length >= 3,
    `студия: ${q("table tbody tr").length} видео alice`,
  );

  await nav("#/upload");
  ok(
    q("input[type=file]").length === 1 && q("select option").length === 3,
    "загрузка: форма",
  );

  await nav("#/subs");
  ok(q(".card").length >= 1, `подписки: ${q(".card").length} видео`);

  await nav(href, 1800);

  const likeBtn = d.querySelector(".pill .btn");
  const before = likeBtn.textContent;
  likeBtn.click();

  await sleep(900);
  ok(
    d.querySelector(".pill .btn").textContent !== before,
    `лайк: «${before}» → «${d.querySelector(".pill .btn").textContent}»`,
  );

  const ta = d.querySelector(".comment-form textarea");
  ta.value = "jsdom <b>тест</b>";
  d.querySelector(".comment-form .btn").click();
  await sleep(1200);

  const mine = [...q(".comment .text")].some(
    (e) => e.textContent === "jsdom <b>тест</b>",
  );

  ok(
    mine && q(".comment .text b").length === 0,
    "комментарий добавлен, HTML не интерпретируется (XSS)",
  );

  await nav("#/moderation");
  ok(
    txt("#app").includes("Раздел доступен модераторам"),
    "обычному пользователю модерация закрыта",
  );

  await nav("#/admin");
  ok(
    txt("#app").includes("администраторам"),
    "обычному пользователю админка закрыта",
  );

  d.querySelector("#topbar .btn.small").click();
  await sleep(1000);
  ok(txt("#topbar").includes("Войти"), "выход");

  await login("moderator@demo.local");
  await nav("#/moderation");
  ok(
    txt("#app").includes("Открытые жалобы") && q("table").length >= 1,
    `модерация: таблиц ${q("table").length}`,
  );

  await login("admin@demo.local");
  await nav("#/admin");
  ok(
    q("table tbody tr").length >= 5,
    `админка: ${q("table tbody tr").length} пользователей`,
  );

  await nav("#/nonexistent");
  ok(txt("#app").includes("не найдена"), "404 для неизвестного маршрута");

  console.log("JS errors:", errs.length ? errs : "нет");
  process.exit(fails ? 1 : 0);
})();
