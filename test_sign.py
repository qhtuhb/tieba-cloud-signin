import unittest
from unittest.mock import patch
import sign


class Tests(unittest.TestCase):
    def test_followed_and_pagination(self):
        parser = sign.FollowParser()
        parser.feed('''<table><tr><td><a href="/f?kw=test" title="测试吧">测试...</a></td>
        <td><span tbs="test_token"></span></td></tr></table>
        <a href="/f/like/mylike?pn=3">尾页</a>''')
        self.assertEqual(parser.forums, {"测试吧": "test_token"})
        self.assertEqual(parser.pages, {1, 3})

    def test_explicit_success(self):
        self.assertEqual(sign.classify({"no": 0, "error": ""}), "signed")
        self.assertEqual(sign.classify({"error_code": "0", "error_msg": "success"}), "signed")

    def test_already_signed(self):
        self.assertEqual(sign.classify({"no": 1101, "error": "您今天已经签过到了"}), "already")

    def test_unknown_response_not_success(self):
        for value in ({}, {"no": 99}, {"error": "服务异常"}, {"no": 0, "error": "异常"}):
            self.assertEqual(sign.classify(value), "failed")

    def test_stop_on_verification(self):
        for text in ("请完成下方验证", "百度安全验证", "访问过于频繁"):
            with self.assertRaises(sign.StopVerification):
                sign.check_verification(text)
        with self.assertRaises(sign.StopVerification):
            sign.classify({"error": "请先登录"})

    def test_english_captcha_stops(self):
        with self.assertRaises(sign.StopVerification):
            sign.classify({"no": 2150040, "error": "need vcode"})

    def test_tbs_uses_post(self):
        client = sign.Client("BDUSS=example")
        with patch.object(client, "json", return_value={"is_login": 1, "tbs": "dummy"}) as mocked:
            self.assertEqual(client.token(), "dummy")
            mocked.assert_called_once_with("/dc/common/tbs", {})

    def test_reject_cookie_header_injection(self):
        with self.assertRaises(sign.SignError):
            sign.Client("BDUSS=example\r\nX: bad")

    def test_never_send_cookie_to_another_host(self):
        client = sign.Client("BDUSS=example")
        for url in ("https://example.com/", "http://tieba.baidu.com/", "//example.com/"):
            with self.assertRaises(sign.SignError):
                client.request(url)

    def test_login_required(self):
        client = sign.Client("BDUSS=example")
        with patch.object(client, "json", return_value={"is_login": 0, "tbs": "dummy"}):
            with self.assertRaises(sign.StopVerification):
                client.token()

    def test_empty_follow_list_not_success(self):
        client = sign.Client("BDUSS=example")
        with patch.object(client, "request", return_value="<html></html>"):
            with self.assertRaises(sign.SignError):
                client.followed()

    def test_redirect_never_forward_credentials(self):
        with self.assertRaises(sign.StopVerification):
            sign.NoRedirects().redirect_request(None, None, 302, "", {}, "https://example.com/")


if __name__ == "__main__":
    unittest.main()
