# UST Cookie Sender（浏览器扩展）

把 SIS / USTspace 的登录 cookie（**含 httpOnly 的 PS_TOKEN**）一键安全发送到
本机 ustplan 接收端。cookie 只在内存中转，**不落扩展存储、不留存**。

## 安装（一次性，约 1 分钟）

1. 浏览器打开 `chrome://extensions`（Edge 用 `edge://extensions`）
2. 右上角开启"开发者模式"
3. 点"加载已解压的扩展程序" → 选择本目录（`extensions/ust-cookie/`）

## 使用

1. 终端运行：`python3 scripts/cookies_setup.py --listen`
2. 记下终端显示的**端口**与 **6 位连接码**
3. 点扩展图标 → 填入端口与连接码 → "保存设置"（只此一次）
4. 浏览器登录 SIS（含 MFA）→ 点扩展图标 → "抓取并发送当前站点 cookie"
5. 浏览器登录 ust.space → 再点一次
6. 终端自动验证通过，流程继续

## 安全说明

- 只连接 `http://127.0.0.1`（本机回环），配合一次性连接码校验；
- 只发送当前站点已知键（SIS: PS_TOKEN/JSESSIONID/PS_TOKENEXPIRE；
  USTspace: ustspace_session），其余 cookie 不发送；
- 不记录、不上传任何数据；卸载扩展即完全移除。
