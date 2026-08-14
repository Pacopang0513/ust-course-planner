# UST Cookie Sender（浏览器扩展）

把 SIS / USTspace 的登录 cookie（**含 httpOnly 的 PS_TOKEN**）一键安全发送到
本机 ustplan 接收端。cookie 只在内存中转，**不落扩展存储、不留存**。

## 安装（一次性，约 1 分钟）

1. 浏览器打开 `chrome://extensions`（Edge 用 `edge://extensions`）
2. 右上角开启"开发者模式"
3. 点"加载已解压的扩展程序" → 选择本目录（`extensions/ust-cookie/`）

## 使用（配合 AI 分段式流程）

1. AI 侧运行 `python3 scripts/cookies_setup.py --gen-code` 生成 4 位连接码，
   连同**端口（默认 8765）与安装/登录步骤清单**一起告诉你
2. 点扩展图标 → 填入端口与连接码 → "保存设置"（只此一次，可提前预填）
3. 浏览器登录 SIS（含 MFA）→ 登录 ust.space，回复 AI"准备好了"
4. AI 启动接收端（`cookies_setup.py --listen --code <同一连接码> --user-ready`，
   门禁：码必须由 `--gen-code` 生成且带 `--user-ready`，否则拒绝启动）后，
   在 SIS 页面点扩展图标 → "抓取并发送当前站点 cookie"
5. 在 ust.space 页面再点一次
6. 接收端自动验证通过，流程继续

> 注意：**更新扩展代码/manifest 后，必须到 `chrome://extensions` 点该扩展的
> 「重新加载」**（或重启浏览器），否则新的站点权限不生效。

> 端口被占用时接收端会自动递增（8765→8766…），以接收端提示的端口为准，
> 需在扩展里重新保存。

## 排障

| 现象 | 原因与处理 |
|---|---|
| `可见 cookie: (空)`（USTspace 页） | 几乎可以断定是扩展对 `ust.space` 的 host 权限未生效（`cookies` API 对无权限的 URL 会静默返回空）。**不**是"未登录"——即使未登录，ust.space 也会设置 `XSRF-TOKEN` / `ustspace_session` 访客 cookie。处理：`chrome://extensions` 点「重新加载」→ 重新打开 ust.space 页面 → 再点发送；仍不行则重启浏览器。 |
| `No host permissions` 报错 | 同上，权限缺失；检查扩展「网站访问权限」是否被关掉（点扩展图标 → 权限）。 |
| 连接码不正确 | AI 分段式流程会提前用 `--gen-code` 生成连接码并告知（`--listen --code` 固定同一码）；裸 `--listen`（不带 `--code`）已被脚本禁用（每次随机生成新码、绕过"先给码再接收"门禁），一律以 AI 告知的码为准重新保存。 |
| 端口被占用 | 接收端会自动递增端口（8765→8766…），以终端显示的端口为准。 |

## 安全说明

- 只连接 `http://127.0.0.1`（本机回环），配合一次性连接码校验；
- 只发送当前站点已知键（SIS: PS_TOKEN/JSESSIONID/PS_TOKENEXPIRE；
  USTspace: ustspace_session），其余 cookie 不发送；
- 不记录、不上传任何数据；卸载扩展即完全移除。
