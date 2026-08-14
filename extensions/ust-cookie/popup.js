// UST Cookie Sender — popup
// 读取当前站点（SIS / USTspace）的登录 cookie（含 httpOnly），
// 仅通过本机回环 POST 到 cookies_setup.py --listen 的接收端。
// cookie 不落扩展存储（不写 chrome.storage，只存端口/连接码）。

const SIS_HOST = "sisprod.psft.ust.hk";
const UST_HOST = "ust.space";
const SOURCE_KEYS = {
  sis: ["PS_TOKEN", "JSESSIONID", "PS_TOKENEXPIRE"],
  ustspace: ["ustspace_session"],
};
const SITE_ORIGINS = {
  sis: ["https://sisprod.psft.ust.hk/*"],
  ustspace: ["https://ust.space/*", "https://*.ust.space/*"],
};

const $ = (id) => document.getElementById(id);

function detectSource(url) {
  try {
    const u = new URL(url);
    if (u.hostname === SIS_HOST || u.hostname.endsWith("." + SIS_HOST)) return "sis";
    if (u.hostname === UST_HOST || u.hostname.endsWith("." + UST_HOST)) return "ustspace";
  } catch (e) { /* ignore */ }
  return null;
}

const SITE_NAME = { sis: "SIS（PS_TOKEN）", ustspace: "USTspace（ustspace_session）" };

async function init() {
  const saved = await chrome.storage.local.get(["port", "token"]);
  if (saved.port) $("port").value = saved.port;
  if (saved.token) $("token").value = saved.token;

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const src = detectSource(tab && tab.url);
  if (src) {
    $("site").textContent = "当前页面：" + SITE_NAME[src] + " → 点下方按钮即可发送";
    $("send").disabled = !(saved.token);
  } else {
    $("site").textContent = "当前页面不是 SIS / ust.space。请先登录后再点按钮。";
    $("send").disabled = true;
  }
}

async function grabCookies(source, tabUrl) {
  const out = {};
  for (const name of SOURCE_KEYS[source]) {
    const c = await chrome.cookies.get({ url: tabUrl, name });
    if (c && c.value) out[name] = c.value;
  }
  return out;
}

async function send() {
  const port = ($("port").value || "8765").trim();
  const token = $("token").value.trim();
  const status = $("status");
  status.className = "";
  status.textContent = "发送中…";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const src = detectSource(tab && tab.url);
    if (!src) throw new Error("当前页面不是 SIS / ust.space");
    const granted = await chrome.permissions.contains({ origins: SITE_ORIGINS[src] });
    if (!granted) {
      throw new Error("扩展没有读取该站点 cookie 的权限。请到 chrome://extensions 点该扩展的「重新加载」，或重启浏览器后重试。");
    }
    const cookies = await grabCookies(src, tab.url);
    if (Object.keys(cookies).length === 0) {
      const names = (await chrome.cookies.getAll({ url: tab.url }))
        .map((c) => c.name).join(", ") || "(空)";
      throw new Error("未找到登录 cookie（当前页面可见 cookie: " + names +
        "；若已登录仍为空，请重载扩展并确认站点权限）");
    }
    const r = await fetch(`http://127.0.0.1:${port}/submit`, {
      method: "POST",
      headers: { "X-Token": token, "Content-Type": "application/json" },
      body: JSON.stringify({ source: src, cookies }),
    });
    const text = await r.text();
    if (r.ok) {
      status.className = "ok";
      status.textContent = "✓ " + text + "\n如还需另一个站点，登录后再次点击。";
    } else {
      throw new Error(text || ("HTTP " + r.status));
    }
  } catch (e) {
    let msg = (e && e.message) ? e.message : String(e);
    if (/no host permissions|host permission/i.test(msg) && !msg.includes("权限。请")) {
      msg = "扩展没有读取该站点 cookie 的权限。请到 chrome://extensions 点该扩展的「重新加载」，或重启浏览器后重试。";
    }
    status.className = "err";
    status.textContent = "✗ 失败：" + msg +
      "\n请确认已运行 cookies_setup.py --listen 且端口/连接码一致。";
  }
}

$("save").addEventListener("click", async () => {
  const port = ($("port").value || "8765").trim();
  const token = $("token").value.trim();
  if (!/^\d+$/.test(port) || !/^\d{4}$/.test(token)) {
    $("status").className = "err";
    $("status").textContent = "端口需为数字，连接码为 4 位数字（AI 会告诉你，保存一次即可）。";
    return;
  }
  await chrome.storage.local.set({ port, token });
  $("status").className = "ok";
  $("status").textContent = "已保存（端口 " + port + "）。到 SIS / ust.space 页面点按钮发送。";
  $("send").disabled = false;
});

$("send").addEventListener("click", send);

init();
