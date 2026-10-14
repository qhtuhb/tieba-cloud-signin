# 百度贴吧云端每日签到

GitHub Actions 按北京时间每天 **06:30** 触发，独立于你的电脑运行。
一次启动处理全部关注贴吧，自动翻页，逐个提交签到请求；不再打开每个吧的网页。
每次签到请求结束后等待 5 秒，再提交下一个贴吧；第一轮结束后，仅对普通失败贴吧补签一轮，补签同样间隔 5 秒。110 个吧仅等待时间约 9 分钟，总耗时还取决于网络与补签数量。
遇到验证码、登录失效或限流立即停止，不执行补签；降低请求频率不能保证不会出现验证码。

## 首次配置

1. 将本项目放入自己的**私有 GitHub 仓库**，工作流文件必须位于 `.github/workflows/daily-sign.yml`。
2. 在仓库的 **Settings → Secrets and variables → Actions → New repository secret** 中添加 `TIEBA_COOKIE`。
3. 值使用已登录百度贴吧的请求 Cookie，必须包含 `BDUSS=...`。它是登录凭据，只有你选择存放在 GitHub Secret 中后，云端才可使用。
4. 在 **Actions → 百度贴吧每日签到 → Run workflow** 中手动运行一次，检查结果摘要。

获取 Cookie：在自己电脑浏览器登录 `https://tieba.baidu.com/`，按 F12 打开开发者工具，进入 Network（网络），刷新页面，选择发往 `tieba.baidu.com` 的页面请求，在 Request Headers（请求头）里复制 Cookie。不要复制响应头 Set-Cookie，也不要把 Cookie 写进仓库代码、Issue 或运行日志。内置浏览器如果无法打开开发者工具，可在自己的 Edge/Chrome 中登录后取得 Cookie。

## 运行行为

- 自动读取所有关注贴吧和分页；当天已经签到视为完成。
- 不保存账号密码，不输出 Cookie、接口原始响应或关注列表。
- 登录凭据仅发送给 `https://tieba.baidu.com`；拒绝重定向。
- 网络失败有限重试，安全验证、登录失效、限流则停止并让 Actions 报错。
- 工作流摘要记录成功、已签、失败数量；失败通知使用 GitHub 自身的 Actions 通知设置。
- 不解决或绕过验证码，不保证百度永远不会触发风控。

## 实际限制

GitHub cron 不是精确闹钟，可能晚于 06:30 运行；平台故障可能导致漏跑。
Cookie 会过期，云端 IP 也可能触发百度验证，届时需要更新 Secret。
私有仓库的 Actions 使用额度取决于你的 GitHub 套餐；超出额度可能停止运行或按你的账户计费设置处理。
本项目使用百度贴吧网页接口，接口变化也可能导致运行失败。

本地无额外依赖，可用 Python 3.12 运行 `python sign.py`，登录 Cookie 通过环境变量 `TIEBA_COOKIE` 提供。
