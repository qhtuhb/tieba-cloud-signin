"""Sign all followed Tieba forums. Credentials come only from the environment."""
import json
import os
import re
import sys
import time
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE = "https://tieba.baidu.com"


class SignError(Exception):
    pass


class StopVerification(SignError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise StopVerification("百度要求跳转验证或重新登录，请更新登录 Cookie。")


class FollowParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forums = {}
        self.pages = {1}
        self.in_row = False
        self.cell = 0
        self.anchor = None
        self.name = ""
        self.token = ""
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.in_row, self.cell, self.name, self.token = True, 0, "", ""
        elif tag == "td" and self.in_row:
            self.cell += 1
        elif tag == "span" and self.in_row and attrs.get("tbs"):
            self.token = attrs["tbs"]
        elif tag == "a":
            href = attrs.get("href", "")
            parsed = urlparse(urljoin(BASE, href))
            if parsed.hostname == "tieba.baidu.com" and parsed.path == "/f/like/mylike":
                page = parse_qs(parsed.query).get("pn", ["1"])[0]
                if page.isdigit():
                    self.pages.add(int(page))
            if self.in_row and self.cell == 1 and parsed.path == "/f" and "kw" in parse_qs(parsed.query):
                self.anchor = attrs.get("title", "")
                self.text = []

    def handle_data(self, data):
        if self.anchor is not None:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            self.name = (self.anchor or "".join(self.text)).strip()
            self.anchor = None
        if tag == "tr" and self.in_row:
            if self.name:
                self.forums[self.name] = self.token
            self.in_row = False


def check_verification(text):
    if any(marker in text for marker in ("百度安全验证", "请完成下方验证", "扫码验证", "访问过于频繁")):
        raise StopVerification("百度触发安全验证，任务已停止；需要人工验证或更新 Cookie。")


class Client:
    def __init__(self, cookie):
        if "\n" in cookie or "\r" in cookie:
            raise SignError("Cookie 不能包含换行。")
        self.opener = build_opener(NoRedirects())
        self.headers = {
            "Cookie": cookie,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
            "Referer": BASE + "/",
        }

    def request(self, path, data=None):
        url = urljoin(BASE, path)
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "tieba.baidu.com":
            raise SignError("拒绝向百度贴吧以外的域名发送登录凭据。")
        body = urlencode(data).encode("utf-8") if data is not None else None
        req = Request(url, data=body, headers=self.headers)
        # A sign POST may have succeeded even when its response is lost.
        # Do not immediately resubmit it after a timeout or server error.
        attempts = 1 if parsed.path == "/sign/add" else 3
        for attempt in range(attempts):
            try:
                with self.opener.open(req, timeout=30) as response:
                    raw = response.read()
                    charset = response.headers.get_content_charset()
                    if charset is None:
                        match = re.search(br"charset\s*=\s*[\"']?([a-zA-Z0-9_-]+)", raw[:8192])
                        charset = match.group(1).decode("ascii") if match else "utf-8"
                    text = raw.decode(charset, errors="replace")
                    check_verification(text)
                    return text
            except HTTPError as exc:
                if exc.code in (401, 403, 429):
                    raise StopVerification("登录失效、访问受限或请求过于频繁；任务已停止。") from None
                if attempt == attempts - 1 or exc.code < 500:
                    raise SignError("百度接口返回 HTTP " + str(exc.code)) from None
            except (URLError, TimeoutError):
                if attempt == attempts - 1:
                    raise SignError("网络请求失败，有限重试后仍无法连接百度。") from None
            time.sleep(2 ** attempt)

    def json(self, path, data=None):
        text = self.request(path, data)
        try:
            value = json.loads(text)
        except ValueError:
            raise SignError("百度接口未返回 JSON，可能需要重新登录或验证。") from None
        if not isinstance(value, dict):
            raise SignError("百度接口响应格式发生变化。")
        return value

    def token(self):
        # POST avoids the web GET endpoint's legacy HTTP redirect.
        value = self.json("/dc/common/tbs", {})
        if str(value.get("is_login")) != "1" or not value.get("tbs"):
            raise StopVerification("登录 Cookie 已失效，请重新登录百度并更新 TIEBA_COOKIE。")
        return value["tbs"]

    def followed(self):
        pending, seen, forums = {1}, set(), {}
        while pending:
            page = min(pending)
            pending.remove(page)
            if page in seen:
                continue
            seen.add(page)
            parser = FollowParser()
            parser.feed(self.request("/f/like/mylike?" + urlencode({"pn": page})))
            if not parser.forums:
                raise SignError("关注列表为空或页面格式发生变化；不会将其报告为签到成功。")
            forums.update(parser.forums)
            if max(parser.pages) > 100:
                raise SignError("关注列表页数异常，任务停止。")
            pending.update(set(range(1, max(parser.pages) + 1)) - seen)
            if pending:
                time.sleep(0.5)
        return forums


def classify(value):
    message = str(value.get("error", value.get("error_msg", "")))
    code = value.get("no", value.get("error_code", value.get("errno")))
    if str(code) == "2150040" or any(word in message.lower() for word in ("验证", "验证码", "登录", "频繁", "风控", "vcode", "captcha")):
        raise StopVerification("百度要求验证码或重新登录，任务停止；不会自动绕过验证码。")
    if any(word in message for word in ("已经签", "已签到", "已签过")):
        return "already"
    code = value.get("no", value.get("error_code", value.get("errno")))
    if str(code) == "0" and message in ("", "0", "None", "success", "成功"):
        return "signed"
    # 未返回明确的零错误码时不猜测成功。
    return "failed"


def summary(signed, already, failed, total, status):
    text = ("## 百度贴吧签到\n\n"
            f"状态：{status}\n\n"
            f"关注贴吧：{total}；本次成功：{signed}；今日已签：{already}；失败：{failed}；未完成核验：{max(0, total-signed-already-failed)}。\n")
    print(text)
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as stream:
            stream.write(text)


def save_report(details, status, reason):
    directory = os.environ.get("TIEBA_REPORT_DIR")
    if not directory:
        return
    from datetime import datetime, timezone, timedelta
    from pathlib import Path
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    report = {"time": datetime.now(timezone(timedelta(hours=8))).isoformat(),
              "status": status, "reason": reason, "forums": details}
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    labels = {"signed": "签到成功", "already": "今日已签", "failed": "失败", "unverified": "未核验", "verification": "要求人工验证"}
    text = "\n### 逐吧签到详情\n\n| 贴吧 | 最终结果 | 提交次数 |\n|---|---|---|\n"
    for name, item in details.items():
        safe_name = name.replace("|", "／").replace("\n", " ").replace("\r", " ").replace("<", "&lt;").replace(">", "&gt;")
        text += f"| {safe_name} | {labels[item['status']]} | {item['attempts']} |\n"
    (root / "details.md").write_text(text, encoding="utf-8")
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as stream:
            stream.write(text)


def main():
    signed = already = failed = total = 0
    details = {}
    report_status = "中断"
    reason = ""
    try:
        cookie = os.environ.get("TIEBA_COOKIE", "").strip()
        if not cookie or not re.search(r"(?:^|;\s*)BDUSS=", cookie):
            raise SignError("缺少 TIEBA_COOKIE Secret；请保存包含 BDUSS 的百度贴吧 Cookie。")
        client = Client(cookie)
        token = client.token()
        forums = client.followed()
        total = len(forums)
        details = {name: {"status": "unverified", "attempts": 0} for name in forums}
        print(f"已读取 {total} 个关注贴吧；不会输出 Cookie 或关注列表。")
        pending = list(forums.items())
        attempted = False
        for round_no in (1, 2):
            retry = []
            if round_no == 2 and pending:
                print(f"开始一轮补签：{len(pending)} 个普通失败贴吧。")
            for index, (name, row_token) in enumerate(pending, 1):
                if attempted:
                    time.sleep(5.0)
                attempted = True
                details[name]["attempts"] += 1
                try:
                    status = classify(client.json("/sign/add", {"ie": "utf-8", "kw": name, "tbs": row_token or token}))
                except StopVerification:
                    details[name]["status"] = "verification"
                    raise
                except SignError:
                    status = "failed"
                details[name]["status"] = status
                if status == "failed":
                    retry.append((name, row_token))
                    if round_no == 1:
                        failed += 1
                else:
                    signed += status == "signed"
                    already += status == "already"
                    if round_no == 2:
                        failed -= 1
                print(f"第 {round_no} 轮 {index}/{len(pending)}，成功 {signed}，已签 {already}，未解决失败 {failed}", flush=True)
            pending = retry
            if not pending:
                break
        report_status = "完成" if not failed else "部分失败"
        summary(signed, already, failed, total, report_status)
        return 1 if failed else 0
    except SignError as exc:
        reason = str(exc)
        summary(signed, already, failed, total, "中断")
        print("原因：" + reason, file=sys.stderr)
        return 1
    finally:
        save_report(details, report_status, reason)


if __name__ == "__main__":
    sys.exit(main())
