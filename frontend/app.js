"use strict";

const $ = (s) => document.querySelector(s);

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);

  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) {
      continue;
    }

    if (k === "class") {
      el.className = v;
    } else if (k.startsWith("on")) {
      el.addEventListener(k.slice(2), v);
    } else if (k in el && k !== "list") {
      el[k] = v;
    } else {
      el.setAttribute(k, v === true ? "" : v);
    }
  }

  for (const kid of kids.flat()) {
    if (kid != null && kid !== false) {
      el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
  }

  return el;
}
const mount = (el, ...kids) =>
  el.replaceChildren(...kids.flat().filter(Boolean));

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => t.classList.remove("show"), 3500);
}

function plural(n, one, few, many) {
  const m10 = n % 10;
  const m100 = n % 100;

  return m10 === 1 && m100 !== 11
    ? one
    : m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)
      ? few
      : many;
}

function fmtViews(n) {
  if (n >= 1e6) {
    return (n / 1e6).toFixed(1).replace(".", ",") + " млн просмотров";
  }

  if (n >= 1e3) {
    return (n / 1e3).toFixed(1).replace(".", ",") + " тыс. просмотров";
  }

  return n + " " + plural(n, "просмотр", "просмотра", "просмотров");
}

function ago(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);

  const units = [
    [31536000, "год", "года", "лет"],
    [2592000, "месяц", "месяца", "месяцев"],
    [86400, "день", "дня", "дней"],
    [3600, "час", "часа", "часов"],
    [60, "минуту", "минуты", "минут"],
  ];

  for (const [sec, a, b, c] of units) {
    const n = Math.floor(s / sec);

    if (n >= 1) {
      return `${n} ${plural(n, a, b, c)} назад`;
    }
  }

  return "только что";
}

function fmtDur(sec) {
  if (sec == null) {
    return "";
  }

  const m = Math.floor(sec / 60);
  const s = sec % 60;

  return `${m}:${String(s).padStart(2, "0")}`;
}

function color(name) {
  let x = 0;

  for (const ch of name) {
    x = (x * 31 + ch.charCodeAt(0)) % 360;
  }

  return `hsl(${x},55%,42%)`;
}

function avatar(name, big) {
  const a = h(
    "span",
    { class: "avatar" + (big ? " big" : "") },
    (name || "?")[0],
  );
  a.style.background = color(name || "?");

  return a;
}

let token = null;
let me = null;

class ApiError extends Error {
  constructor(status, msg) {
    super(msg);
    this.status = status;
  }
}

async function refresh() {
  try {
    const r = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
    });

    if (!r.ok) {
      throw 0;
    }

    token = (await r.json()).access_token;

    const m = await fetch("/api/auth/me", {
      headers: { Authorization: "Bearer " + token },
    });
    me = m.ok ? await m.json() : null;

    return !!me;
  } catch {
    token = null;
    me = null;

    return false;
  }
}

async function api(path, { method = "GET", body, retried } = {}) {
  const headers = {};

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  if (token) {
    headers.Authorization = "Bearer " + token;
  }

  const r = await fetch("/api" + path, {
    method,
    headers,
    credentials: "same-origin",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (r.status === 401 && token && !retried && (await refresh()))
    return api(path, { method, body, retried: true });

  if (!r.ok) {
    let msg = "Ошибка запроса (" + r.status + ")";

    try {
      const j = await r.json();

      if (typeof j.detail === "string") {
        msg = j.detail;
      } else if (Array.isArray(j.detail)) {
        msg = "Проверьте введеенные данные";
      }
    } catch {}

    throw new ApiError(r.status, msg);
  }

  return r.status === 204 ? null : r.json();
}

const isStaff = () => me && (me.role === "moderator" || me.role === "admin");
const go = (hash) => {
  location.hash = hash;
};

function renderChrome() {
  const q = h("input", {
    type: "text",
    placeholder: "Введите запрос",
    "aria-label": "Поиск",
    maxLength: 100,
  });

  const search = h(
    "form",
    {
      class: "search",
      onsubmit: (e) => {
        e.preventDefault();
        if (q.value.trim())
          go("#/search/" + encodeURIComponent(q.value.trim()));
      },
    },
    q,
    h("button", { type: "submit", "aria-label": "Найти" }, "🔍"),
  );

  const right = me
    ? [
        h(
          "a",
          { class: "icon-btn", href: "#/upload", title: "Загрузить видео" },
          "＋",
        ),
        h(
          "a",
          { href: "#/channel/" + me.username, title: me.username },
          avatar(me.username),
        ),
        h("button", { class: "btn small", onclick: logout }, "Выйти"),
      ]
    : [h("a", { class: "btn blue", href: "#/login" }, "👤 Войти")];

  mount(
    $("#topbar"),
    h(
      "div",
      { class: "tb-left" },
      h(
        "button",
        {
          class: "icon-btn",
          "aria-label": "Меню",
          onclick: () => document.body.classList.toggle("mini"),
        },
        "☰",
      ),
      h(
        "a",
        { class: "logo", href: "#/" },
        h("span", { class: "logo-mark" }, "▶"),
        "TubeClone",
      ),
    ),
    search,
    h("div", { class: "tb-right" }, right),
  );

  const cur = location.hash || "#/";
  const item = (href, ico, label) =>
    h(
      "a",
      { href, class: cur === href ? "on" : "" },
      h("span", { class: "ico" }, ico),
      h("span", { class: "nav-label" }, label),
    );

  mount(
    $("#sidebar"),
    h(
      "div",
      { class: "nav" },
      item("#/", "🏠", "Главная"),
      me && item("#/subs", "📺", "Подписки"),
      me && h("div", { class: "sep" }),
      me && item("#/channel/" + me.username, "👤", "Мой канал"),
      me && item("#/studio", "🎞", "Студия"),
      me && item("#/upload", "⬆", "Загрузить"),
      isStaff() && h("div", { class: "sep" }),
      isStaff() && item("#/moderation", "🛡", "Модерация"),
      me && me.role === "admin" && item("#/admin", "⚙", "Пользователи"),
    ),
  );
}

async function logout() {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch {}

  token = null;
  me = null;

  renderChrome();
  go("#/");
  route();
}

function statusBadges(v) {
  const b = [];

  if (v.visibility === "private") {
    b.push(h("span", { class: "badge" }, "🔒 Приватное"));
  }

  if (v.visibility === "unlisted") {
    b.push(h("span", { class: "badge" }, "🔗 По ссылке"));
  }

  if (v.status === "uploading") {
    b.push(h("span", { class: "badge warn" }, "Загрузка не завершена"));
  }

  if (v.status === "processing") {
    b.push(h("span", { class: "badge warn" }, "Обрабатывается"));
  }

  if (v.status === "failed") {
    b.push(h("span", { class: "badge bad" }, "Ошибка обработки"));
  }

  if (v.is_hidden) {
    b.push(h("span", { class: "badge bad" }, "Скрыто модератором"));
  }

  return b;
}

function thumb(v) {
  return h(
    "div",
    { class: "thumb" },
    v.thumb_url
      ? h("img", { src: v.thumb_url, alt: "", loading: "lazy" })
      : h(
          "div",
          { class: "noimg" },
          v.status === "ready" ? "Нет превью" : "Видео обрабатывается",
        ),
    v.duration_sec != null &&
      h("span", { class: "dur" }, fmtDur(v.duration_sec)),
  );
}

function metaLine(v) {
  return `${fmtViews(v.views_count)} · ${ago(v.created_at)}`;
}

function videoCard(v) {
  return h(
    "div",
    { class: "card" },
    h("a", { href: "#/watch/" + v.id }, thumb(v)),
    h(
      "div",
      { class: "meta" },
      h("a", { href: "#/channel/" + v.channel.handle }, avatar(v.channel.name)),
      h(
        "div",
        {},
        h(
          "a",
          { href: "#/watch/" + v.id, class: "title", title: v.title },
          v.title,
        ),
        h(
          "div",
          { class: "sub" },
          h("a", { href: "#/channel/" + v.channel.handle }, v.channel.name),
        ),
        h("div", { class: "sub" }, metaLine(v)),
        statusBadges(v),
      ),
    ),
  );
}

function videoRow(v, small) {
  return h(
    "div",
    { class: "row" + (small ? " small" : "") },
    h("a", { href: "#/watch/" + v.id }, thumb(v)),
    h(
      "div",
      {},
      h("a", { href: "#/watch/" + v.id, class: "title" }, v.title),
      h("div", { class: "sub" }, metaLine(v)),
      h(
        "div",
        { class: "sub" },
        h("a", { href: "#/channel/" + v.channel.handle }, v.channel.name),
      ),
      !small && h("div", { class: "sub" }, (v.description || "").slice(0, 140)),
      statusBadges(v),
    ),
  );
}

const grid = (videos) =>
  videos.length
    ? h("div", { class: "grid" }, videos.map(videoCard))
    : h("div", { class: "empty" }, "Здесь пока нет видео");
const loading = () => h("div", { class: "empty" }, "Загрузка…");

function needLogin() {
  return h(
    "div",
    { class: "empty" },
    "Для этого раздела нужно ",
    h("a", { href: "#/login", class: "sub" }, "войти"),
    ".",
  );
}

const cleanups = [];
const onLeave = (fn) => cleanups.push(fn);
const app = () => $("#app");

async function pageHome() {
  mount(app(), loading());
  mount(app(), grid(await api("/feed?limit=50")));
}

async function pageSubs() {
  if (!me) {
    return mount(app(), needLogin());
  }

  mount(
    app(),
    h("h2", { class: "section" }, "Подписки"),
    grid(await api("/feed/subscriptions?limit=50")),
  );
}

async function pageSearch(q) {
  q = decodeURIComponent(q);
  mount(app(), loading());

  const res = await api("/search?q=" + encodeURIComponent(q) + "&limit=50");
  mount(
    app(),
    h("h2", { class: "section" }, `Результаты по запросу «${q}»`),
    res.length
      ? res.map((v) => videoRow(v))
      : h("div", { class: "empty" }, "Ничего не найдено"),
  );
}

function authForm(kind) {
  const reg = kind === "register";
  const email = h("input", {
    type: "email",
    required: true,
    autocomplete: "email",
  });

  const user =
    reg &&
    h("input", {
      type: "text",
      required: true,
      pattern: "[A-Za-z0-9_]{3,40}",
      title: "Латиница, цифры, _ (3–40 символов)",
      autocomplete: "username",
    });
  const pass = h("input", {
    type: "password",
    required: true,
    minLength: 8,
    autocomplete: reg ? "new-password" : "current-password",
  });

  const err = h("div", { class: "err" });
  const form = h(
    "form",
    {
      class: "form",
      onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";

        try {
          if (reg)
            await api("/auth/register", {
              method: "POST",
              body: {
                email: email.value,
                username: user.value,
                password: pass.value,
              },
            });

          const t = await api("/auth/login", {
            method: "POST",
            body: { email: email.value, password: pass.value },
          });
          token = t.access_token;
          me = await api("/auth/me");
          renderChrome();
          go("#/");
        } catch (ex) {
          err.textContent = ex.message;
        }
      },
    },
    h("h1", {}, reg ? "Регистрация" : "Вход"),
    h("label", {}, "Email", email),
    reg && h("label", {}, "Имя пользователя (станет адресом канала)", user),
    h("label", {}, "Пароль" + (reg ? " (минимум 8 символов)" : ""), pass),
    err,
    h(
      "button",
      { class: "btn primary", type: "submit" },
      reg ? "Создать аккаунт" : "Войти",
    ),
    h(
      "div",
      { class: "sub" },
      reg ? "Уже есть аккаунт? " : "Нет аккаунта? ",
      h(
        "a",
        { href: reg ? "#/login" : "#/register", class: "sub" },
        reg ? "Войти" : "Зарегистрироваться",
      ),
    ),
  );

  return form;
}

async function pageWatch(id) {
  mount(app(), loading());
  let v;

  try {
    v = await api("/videos/" + id);
  } catch (e) {
    return mount(
      app(),
      h(
        "div",
        { class: "empty" },
        e.status === 404 ? "Видео не найдено или недоступно" : e.message,
      ),
    );
  }
  const ch = await api("/channels/" + v.channel.handle);
  const msg = h("div", { class: "msg" });
  const player = h("div", { class: "player" });

  if (v.status === "ready" && v.hls_url) {
    const video = h("video", {
      controls: true,
      autoplay: true,
      playsInline: true,
      poster: v.thumb_url || "",
    });
    player.append(video);

    let hls = false;
    let counted = false;

    if (window.Hls && Hls.isSupported()) {
      hls = new Hls();
      hls.loadSource(v.hls_url);
      hls.attachMedia(video);
      onLeave(() => hls.destroy());
    } else {
      video.src = v.hls_url;
    }

    video.addEventListener("play", () => {
      if (!counted) {
        counted = true;
        api("/videos/" + id + "/view", { method: "POST" }).catch(() => {});
      }
    });

    onLeave(() => {
      video.pause();
      video.removeAttribute("src");
    });
  } else {
    msg.textContent =
      v.status === "failed"
        ? "Не удалось обработать видео"
        : "Видео обрабатывается, страница обновится сама…";
    player.append(msg);

    if (v.status !== "failed") {
      const t = setInterval(() => route(), 4000);
      onLeave(() => clearInterval(t));
    }
  }

  const likeBtn = h("button", { class: "btn" }),
    disBtn = h("button", { class: "btn" });

  const paint = (s) => {
    likeBtn.textContent = "👍 " + s.likes;
    disBtn.textContent = "👎 " + s.dislikes;
    likeBtn.classList.toggle("active", s.my_like === 1);
    disBtn.classList.toggle("active", s.my_like === -1);
  };
  paint(v);

  const rate = (val) => async () => {
    if (!me) {
      return go("#/login");
    }

    try {
      paint(
        await api(`/videos/${id}/like`, {
          method: "PUT",
          body: { value: v.my_like === val ? 0 : val },
        }),
      );
      v.my_like = v.my_like === val ? 0 : val;
    } catch (e) {
      toast(e.message);
    }
  };

  likeBtn.onclick = rate(1);
  disBtn.onclick = rate(-1);

  const subBtn = h("button", { class: "btn" });
  const paintSub = (c) => {
    subBtn.textContent = c.subscribed ? "🔔 Вы подписаны" : "Подписаться";
    subBtn.className = "btn " + (c.subscribed ? "" : "primary");
    subCount.textContent = `${c.subscribers} ${plural(c.subscribers, "подписчик", "подписчика", "подписчиков")}`;
    ch.subscribed = c.subscribed;
  };
  const subCount = h("div", { class: "sub" });
  paintSub(ch);
  const own = me && me.username === v.channel.handle;

  subBtn.onclick = async () => {
    if (!me) {
      return go("#/login");
    }

    try {
      paintSub(
        await api(`/channels/${ch.handle}/subscribe`, {
          method: ch.subscribed ? "DELETE" : "POST",
        }),
      );
    } catch (e) {
      toast(e.message);
    }
  };

  const reportBtn = h(
    "button",
    {
      class: "btn",
      onclick: async () => {
        if (!me) {
          return go("#/login");
        }

        const reason = prompt("Опишите причину жалобы");

        if (!reason) {
          return;
        }

        try {
          await api(`/videos/${id}/report`, {
            method: "POST",
            body: { reason },
          });
          toast("Жалоба отправлена модераторам");
        } catch (e) {
          toast(e.message);
        }
      },
    },
    "⚑ Пожаловаться",
  );

  const list = h("div", {});
  const input = h("textarea", {
    placeholder: "Введите комментарий",
    maxLength: 2000,
    rows: 1,
  });
  async function loadComments() {
    const cs = await api(`/videos/${id}/comments?limit=100`).catch(() => []);
    const tops = cs.filter((c) => !c.parent_id);
    mount(
      list,
      tops.flatMap((c) => [
        commentEl(c, false),
        ...cs
          .filter((r) => r.parent_id === c.id)
          .reverse()
          .map((r) => commentEl(r, true)),
      ]),
    );
    commentsTitle.textContent = `${cs.length} ${plural(cs.length, "комментарий", "комментария", "комментариев")}`;
  }

  function commentEl(c, reply) {
    const canDel = me && (me.username === c.username || isStaff());
    const replyBox = h("div", {});

    return h(
      "div",
      { class: "comment" + (reply ? " reply" : "") },
      avatar(c.username),
      h(
        "div",
        { class: "body" },
        h(
          "div",
          {},
          h("b", {}, "@" + c.username),
          " ",
          h("span", { class: "sub" }, ago(c.created_at)),
        ),
        h("div", { class: "text" }, c.text),
        h(
          "div",
          { class: "inline" },
          me &&
            !reply &&
            h(
              "button",
              {
                class: "btn small",
                onclick: () => {
                  const t = h("input", {
                    type: "text",
                    placeholder: "Ответить…",
                    maxLength: 2000,
                  });
                  mount(
                    replyBox,
                    h(
                      "div",
                      { class: "inline" },
                      t,
                      h(
                        "button",
                        {
                          class: "btn small primary",
                          onclick: async () => {
                            try {
                              await api(`/videos/${id}/comments`, {
                                method: "POST",
                                body: { text: t.value, parent_id: c.id },
                              });
                              loadComments();
                            } catch (e) {
                              toast(e.message);
                            }
                          },
                        },
                        "Отправить",
                      ),
                    ),
                  );
                  t.focus();
                },
              },
              "Ответить",
            ),
          canDel &&
            h(
              "button",
              {
                class: "btn small",
                onclick: async () => {
                  try {
                    await api("/comments/" + c.id, { method: "DELETE" });
                    loadComments();
                  } catch (e) {
                    toast(e.message);
                  }
                },
              },
              "Удалить",
            ),
        ),
        replyBox,
      ),
    );
  }

  const commentsTitle = h("h3", {}, "");
  const form = me
    ? h(
        "div",
        { class: "comment-form" },
        avatar(me.username),
        input,
        h(
          "button",
          {
            class: "btn primary",
            onclick: async () => {
              if (!input.value.trim()) {
                return;
              }

              try {
                await api(`/videos/${id}/comments`, {
                  method: "POST",
                  body: { text: input.value },
                });

                input.value = "";
                loadComments();
              } catch (e) {
                toast(e.message);
              }
            },
          },
          "Отправить",
        ),
      )
    : h(
        "div",
        { class: "sub" },
        h("a", { href: "#/login", class: "sub" }, "Войдите"),
        ", чтобы оставить комментарий",
      );

  const related = h("div", {});
  api("/feed?limit=20").then((vs) =>
    mount(
      related,
      vs.filter((x) => x.id !== id).map((x) => videoRow(x, true)),
    ),
  );

  mount(
    app(),
    h(
      "div",
      { class: "watch" },
      h(
        "div",
        {},
        player,
        h("h1", {}, v.title),
        statusBadges(v),
        h(
          "div",
          { class: "actions" },
          h(
            "a",
            { href: "#/channel/" + v.channel.handle },
            avatar(v.channel.name),
          ),
          h(
            "div",
            {},
            h(
              "a",
              { href: "#/channel/" + v.channel.handle },
              h("b", {}, v.channel.name),
            ),
            subCount,
          ),
          !own && subBtn,
          h("div", { class: "spacer" }),
          h("div", { class: "pill" }, likeBtn, disBtn),
          !own && reportBtn,
        ),
        h(
          "div",
          { class: "desc" },
          h("b", {}, metaLine(v)),
          "\n",
          v.description || "Без описания",
        ),
        commentsTitle,
        form,
        list,
      ),
      h("div", {}, related),
    ),
  );
  loadComments();
}

async function pageChannel(handle, tab) {
  mount(app(), loading());
  let ch;

  try {
    ch = await api("/channels/" + handle);
  } catch (e) {
    return mount(app(), h("div", { class: "empty" }, "Канал не найден"));
  }

  const own = me && me.username === ch.handle;
  const body = h("div", {});
  const tabs = h("div", { class: "tabs" });
  const subBtn = h("button", { class: "btn primary" });
  const subCount = h("span", { class: "sub" });

  const paintSub = (c) => {
    ch = c;
    subBtn.textContent = c.subscribed ? "🔔 Вы подписаны" : "Подписаться";
    subBtn.className = "btn " + (c.subscribed ? "" : "primary");
    subCount.textContent = `@${c.handle} · ${c.subscribers} ${plural(c.subscribers, "подписчик", "подписчика", "подписчиков")}`;
  };
  paintSub(ch);

  subBtn.onclick = async () => {
    if (!me) {
      return go("#/login");
    }

    try {
      paintSub(
        await api(`/channels/${ch.handle}/subscribe`, {
          method: ch.subscribed ? "DELETE" : "POST",
        }),
      );
    } catch (e) {
      toast(e.message);
    }
  };

  async function show(which) {
    for (const b of tabs.children) {
      b.classList.toggle("on", b.dataset.k === which);
    }

    mount(body, loading());

    if (which === "videos") {
      mount(body, grid(await api(`/channels/${handle}/videos`)));
    } else {
      const pls = await api(`/channels/${handle}/playlists`);
      const nameIn = h("input", {
        type: "text",
        placeholder: "Название нового плейлиста",
        maxLength: 150,
      });

      mount(
        body,
        own &&
          h(
            "div",
            { class: "inline" },
            nameIn,
            h(
              "button",
              {
                class: "btn",
                onclick: async () => {
                  if (!nameIn.value.trim()) {
                    return;
                  }

                  try {
                    await api("/playlists", {
                      method: "POST",
                      body: { title: nameIn.value.trim() },
                    });

                    show("playlists");
                  } catch (e) {
                    toast(e.message);
                  }
                },
              },
              "Создать плейлист",
            ),
          ),
        pls.length
          ? pls.map((p) =>
              h(
                "div",
                { class: "row small" },
                h(
                  "a",
                  { href: "#/playlist/" + p.id, class: "title" },
                  "📃 " + p.title,
                ),
                p.visibility !== "public" &&
                  h("span", { class: "badge" }, p.visibility),
              ),
            )
          : h("div", { class: "empty" }, "Плейлистов пока нет"),
      );
    }
  }

  for (const [k, label] of [
    ["videos", "Видео"],
    ["playlists", "Плейлисты"],
  ])
    tabs.append(h("button", { "data-k": k, onclick: () => show(k) }, label));

  const edit = () => {
    const n = h("input", { type: "text", value: ch.name, maxLength: 100 });
    const d = h("textarea", { rows: 3, maxLength: 5000 }, ch.description);
    d.value = ch.description;

    mount(
      info,
      h(
        "div",
        { class: "form wide" },
        h("label", {}, "Название", n),
        h("label", {}, "Описание", d),
        h(
          "div",
          { class: "inline" },
          h(
            "button",
            {
              class: "btn primary",
              onclick: async () => {
                try {
                  ch = await api("/channels/me", {
                    method: "PATCH",
                    body: { name: n.value, description: d.value },
                  });
                  pageChannel(handle, tab);
                } catch (e) {
                  toast(e.message);
                }
              },
            },
            "Сохранить",
          ),
        ),
      ),
    );
  };

  const info = h(
    "div",
    {},
    h("h1", {}, ch.name),
    subCount,
    h("div", { class: "sub" }, ch.description),
    own
      ? h("button", { class: "btn small", onclick: edit }, "Изменить")
      : subBtn,
  );

  mount(
    app(),
    h("div", { class: "channel-head" }, avatar(ch.name, true), info),
    tabs,
    body,
  );
  show(tab || "videos");
}

async function pagePlaylist(id) {
  mount(app(), loading());
  let p;

  try {
    p = await api("/playlists/" + id);
  } catch {
    return mount(app(), h("div", { class: "empty" }, "Плейлист не найден"));
  }

  const own = me && me.username === p.channel_handle;

  mount(
    app(),
    h("h2", { class: "section" }, "📃 " + p.title),
    h(
      "div",
      { class: "sub" },
      h("a", { href: "#/channel/" + p.channel_handle }, "@" + p.channel_handle),
    ),
    h("br"),
    p.videos.length
      ? p.videos.map((v) =>
          h(
            "div",
            {},
            videoRow(v),
            own &&
              h(
                "button",
                {
                  class: "btn small",
                  onclick: async () => {
                    await api(`/playlists/${id}/items/${v.id}`, {
                      method: "DELETE",
                    });
                    pagePlaylist(id);
                  },
                },
                "Убрать",
              ),
          ),
        )
      : h("div", { class: "empty" }, "В плейлисте пока нет видео"),
  );
}

const routes = [
  [/^\/?$/, pageHome],
  [/^\/subs$/, pageSubs],
  [/^\/search\/(.+)$/, pageSearch],
  [/^\/watch\/([\w-]+)$/, pageWatch],
  [/^\/channel\/(\w+)(?:\/(\w+))?$/, pageChannel],
  [/^\/playlist\/([\w-]+)$/, pagePlaylist],
  [/^\/login$/, () => mount(app(), authForm("login"))],
  [/^\/register$/, () => mount(app(), authForm("register"))],
];

async function route() {
  while (cleanups.length) {
    try {
      cleanups.pop()();
    } catch {}
  }

  renderChrome();
  const path = (location.hash || "#/").slice(1);

  for (const [re, fn] of routes) {
    const m = path.match(re);
    if (m) {
      try {
        await fn(...m.slice(1));
      } catch (e) {
        mount(app(), h("div", { class: "empty" }, "Ошибка: " + e.message));
      }

      window.scrollTo(0, 0);
      return;
    }
  }

  mount(app(), h("div", { class: "empty" }, "Страница не найдена"));
}

window.addEventListener("hashchange", route);
(async () => {
  await refresh();
  route();
  setInterval(
    () => {
      if (token) refresh().then(() => renderChrome());
    },
    10 * 60 * 1000,
  );
})();
