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

const $ = (id) => document.getElementById(id);

function detectSource(url) {
  try {
    const u = new URL(url);
    if (u.hostname.includes(SIS_HOST)) return "sis";
    if (u.hostname.includes(UST_HOST)) return "ustspace";
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
  // 依次查询并去重：当前 URL（未分区）→ 按名字（未分区）→ 带 partitionKey
  // 查全部分区（Chrome 119+：默认只读未分区 cookie，分区存储的必须显式指定）。
  const queries = [{ url: tabUrl }];
  for (const key of SOURCE_KEYS[source]) queries.push({ name: key });
  queries.push({ partitionKey: {} });
  const seen = new Set();
  const cookies = [];
  for (const q of queries) {
    let got = [];
    try { got = await chrome.cookies.getAll(q); } catch (e) { /* 旧版不支持 partitionKey 时忽略 */ }
    for (const c of got) {
      const id = c.name + "@" + c.domain + "@" +
        (c.partitionKey ? JSON.stringify(c.partitionKey) : "unpartitioned");
      if (!seen.has(id)) { seen.add(id); cookies.push(c); }
    }
  }
  const out = {};
  for (const c of cookies) {
    if (SOURCE_KEYS[source].includes(c.name)) out[c.name] = c.value;
  }
  return out;
}

// 深度抓取：chrome.debugger 读标签页真实请求头里的 Cookie（含 HttpOnly）。
// 当 cookies API 读不到时兜底（某些环境/分区下 cookies API 不可见，但请求头一定有）。
async function debuggerGrabCookies(tabId, source) {
  return new Promise((resolve, reject) => {
    const HOST = source === "sis" ? "sisprod.psft.ust.hk" : "ust.space";
    let done = false;
    const timeout = setTimeout(() => {
      cleanup();
      reject(new Error("深度抓取超时（15s）"));
    }, 15000);

    const onEvent = (debuggeeId, message, params) => {
      if (done || message !== "Network.requestWillBeSent" || !params || !params.request) return;
      const url = params.request.url || "";
      if (!url.includes(HOST)) return;
      const cookieHeader = params.request.headers && params.request.headers.Cookie;
      if (!cookieHeader) return;
      const out = {};
      for (const key of SOURCE_KEYS[source]) {
        const m = new RegExp("(?:^|;\\s*)" + key + "=([^;]*)").exec(cookieHeader);
        if (m && m[1] !== undefined) out[key] = m[1];
      }
      if (Object.keys(out).length) {
        done = true;
        cleanup();
        resolve(out);
      }
    };

    function cleanup() {
      clearTimeout(timeout);
      chrome.debugger.onEvent.removeListener(onEvent);
      chrome.debugger.detach({ tabId }, () => { /* 忽略 detach 错误 */ });
    }

    chrome.debugger.onEvent.addListener(onEvent);
    chrome.debugger.attach({ tabId }, "1.3", () => {
      if (chrome.runtime.lastError) {
        cleanup();
        reject(new Error("无法附加调试器: " + chrome.runtime.lastError.message));
        return;
      }
      chrome.debugger.sendCommand({ tabId }, "Network.enable", {}, () => {
        chrome.tabs.reload(tabId, { bypassCache: true });
      });
    });
  });
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
    const cookies = await grabCookies(src, tab.url);
    if (Object.keys(cookies).length === 0) {
      // cookies API 读不到 → 用调试器读真实请求头（浏览器顶部会出现调试提示条）
      status.textContent = "常规读取为空，尝试深度抓取（调试器）…\n页面会刷新一次，属正常。";
      try {
        const [tab2] = await chrome.tabs.query({ active: true, currentWindow: true });
        const deep = await debuggerGrabCookies(tab2.id, src);
        if (Object.keys(deep).length === 0) throw new Error("调试器也未捕获到 cookie");
        status.textContent = "深度抓取成功，正在发送…";
        const r2 = await fetch(`http://127.0.0.1:${port}/submit`, {
          method: "POST",
          headers: { "X-Token": token, "Content-Type": "application/json" },
          body: JSON.stringify({ source: src, cookies: deep }),
        });
        const t2 = await r2.text();
        if (!r2.ok) throw new Error(t2 || ("HTTP " + r2.status));
        status.className = "ok";
        status.textContent = "✓ " + t2 + "\n如还需另一个站点，登录后再次点击。";
        return;
      } catch (e2) {
        status.className = "err";
        status.textContent = "✗ 深度抓取也失败：" + e2.message;
        return;
      }
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
    status.className = "err";
    status.textContent = "✗ 失败：" + e.message +
      "\n请确认已运行 cookies_setup.py --listen 且端口/连接码一致。";
  }
}

$("save").addEventListener("click", async () => {
  const port = ($("port").value || "8765").trim();
  const token = $("token").value.trim();
  if (!/^\d+$/.test(port) || !/^\d{6}$/.test(token)) {
    $("status").className = "err";
    $("status").textContent = "端口需为数字，连接码为 6 位数字（--listen 终端显示）。";
    return;
  }
  await chrome.storage.local.set({ port, token });
  $("status").className = "ok";
  $("status").textContent = "已保存（端口 " + port + "）。到 SIS / ust.space 页面点按钮发送。";
  $("send").disabled = false;
});

$("send").addEventListener("click", send);

init();
