"""One manually authorized pass over a fixed nine-forum allowlist."""
import os
import re
import sys
import time
import sign

ALLOWLIST = ("3dmax", "宋朝", "吐槽", "金铲铲之战", "trollstore", "魔兽世界", "表情包", "表情", "逆水寒手游")


def classify(value):
    # Stop conservatively on any login, verification or rate-limit indication.
    message = str(value.get("error", value.get("error_msg", ""))).lower()
    if any(word in message for word in ("限流", "受限", "安全", "验证", "登录", "频繁", "风控", "captcha", "vcode", "verify", "verification", "login", "rate limit", "too many")):
        raise sign.StopVerification("验证码、登录或限流提示；限定补签立即停止，不再提交后续贴吧。")
    return sign.classify(value)


def main():
    details = {name: {"status": "unverified", "attempts": 0} for name in ALLOWLIST}
    status, reason = "中断", ""
    signed = already = failed = 0
    try:
        cookie = os.environ.get("TIEBA_COOKIE", "").strip()
        if not cookie or not re.search(r"(?:^|;\s*)BDUSS=", cookie):
            raise sign.SignError("缺少有效 TIEBA_COOKIE Secret。")
        client = sign.Client(cookie)
        token = client.token()
        followed = client.followed()
        attempted = False
        for name in ALLOWLIST:
            if name not in followed:
                details[name]["status"] = "failed"
                failed += 1
                continue  # Never submit an unfollowed or guessed forum.
            if attempted:
                time.sleep(3.0)
            attempted = True
            details[name]["attempts"] = 1
            try:
                result = classify(client.json("/sign/add", {"ie": "utf-8", "kw": name, "tbs": followed[name] or token}))
            except sign.StopVerification:
                details[name]["status"] = "verification"
                raise
            except sign.SignError:
                # A malformed response might be a login/verification page.
                # Fail closed, without exposing the response or submitting again.
                details[name]["status"] = "failed"
                failed += 1
                raise sign.SignError("请求失败或响应无法安全确认；本次限定测试停止，不重试。") from None
            details[name]["status"] = result
            signed += result == "signed"
            already += result == "already"
            failed += result == "failed"
        status = "完成" if not failed else "部分失败"
        return 0 if not failed else 1
    except sign.SignError as exc:
        reason = str(exc)
        print("原因：" + reason, file=sys.stderr)
        return 1
    finally:
        sign.summary(signed, already, failed, len(ALLOWLIST), status)
        sign.save_report(details, status, reason)


if __name__ == "__main__":
    sys.exit(main())
