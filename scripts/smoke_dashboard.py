# -*- coding: utf-8 -*-
"""看板冒烟：**不开浏览器**验证 dashboard.py 真的能跑完一遍。

为什么需要它：看板是项目里唯一依赖可选第三方包（streamlit）的部分，
CI 不装它就完全不回归，而它的 bug 恰恰最难发现——很大一部分出现在
**拖到浏览器里才炸**的地方。用 streamlit 自带的 AppTest 无头执行，
能抓住这几类：

- **相对导入失效**：`streamlit run dashboard.py` 把文件当顶层脚本执行，
  包上下文是丢的，只有这么跑才暴露（正常情况下 `import career_loop` 是好的）。
- **API 变更**：st.iframe / use_container_width 这类签名一改就 AttributeError。
- **数据管线异常**：引擎抛错在看板上往往被降级成 warning，
  这里断言 exception 为空 + 关键元素在位，异常才不会被"静默降级"吞掉。

没装 streamlit 时**默认跳过（退出码 0）**——CI 里它是可选步骤；
本地想强制跑：`python scripts/smoke_dashboard.py --strict`。

自查模式：`python scripts/smoke_dashboard.py --self-test`
——故意喂一个坏 dashboard 源码，确认本脚本**真的能发现**问题
（一个只会说"通过"的检查脚本没有价值）。
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APP = ROOT / "career_loop" / "dashboard.py"


def _load_app_test():
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        return None
    return AppTest


def run_once() -> tuple[bool, str]:
    """跑一遍看板脚本。返回 (是否可用, 说明)。"""
    AppTest = _load_app_test()
    if AppTest is None:
        return True, "skip"
    at = AppTest.from_file(str(APP), default_timeout=180).run()
    if at.exception:
        return False, f"看板脚本抛异常：{at.exception}"
    titles = [t.value for t in at.title]
    if not any("career-loop" in t for t in titles):
        return False, f"标题没渲染出来：{titles}"
    labels = [m.label for m in at.metric]
    for need in ("总投递", "正反馈率", "相关系数 r", "95% 置信区间"):
        if need not in labels:
            return False, f"缺指标卡：{need}（实际 {labels}）"
    tabs = [t.label for t in at.tabs]
    if len(tabs) < 5:
        return False, f"tab 数量不对：{tabs}"
    return True, "ok"


class _SelfTest(unittest.TestCase):
    """证明这个检查脚本本身是有效的——喂坏代码必须被抓出来。"""

    def setUp(self) -> None:
        if _load_app_test() is None:
            self.skipTest("未安装 streamlit")

    def _write_and_run(self, source: str) -> tuple[bool, str]:
        """把一份临时 dashboard 源码当成 APP 跑一遍。"""
        global APP
        old = APP
        try:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "dash.py"
                p.write_text(source, encoding="utf-8")
                APP = p
                return run_once()
        finally:
            APP = old

    def test_catches_runtime_exception(self):
        """脚本抛异常必须报错，不能被当成通过。"""
        ok, msg = self._write_and_run(
            "import streamlit as st\n"
            "raise RuntimeError('boom')\n"
        )
        self.assertFalse(ok)
        self.assertIn("boom", msg)

    def test_catches_missing_metric(self):
        """少画一个指标卡也算失败（防止面板被改残了还显示绿）。"""
        ok, _ = self._write_and_run(
            "import streamlit as st\n"
            "st.title('career-loop x')\n"
            "for name in ('漏斗','校准','缺口','明细','边界'):\n"
            "    st.tabs([name] * 5)\n"
        )
        self.assertFalse(ok)

    def test_accepts_minimal_valid_app(self):
        """最小可用版本必须通过——别把自己写成只会报错的脚本。"""
        ok, msg = self._write_and_run(
            "import streamlit as st\n"
            "st.title('career-loop ok')\n"
            "for lab in ('总投递','正反馈率','相关系数 r','95% 置信区间'):\n"
            "    st.metric(lab, '1')\n"
            "st.tabs(['漏斗','校准','缺口排行','明细','边界'])\n"
        )
        self.assertTrue(ok, msg)


def main() -> int:
    ap = argparse.ArgumentParser(description="看板冒烟测试")
    ap.add_argument("--strict", action="store_true",
                    help="没装 streamlit 时也算失败（本地/CI 想强制跑时用）")
    ap.add_argument("--self-test", action="store_true", help="跑本脚本自身的正确性测试")
    args = ap.parse_args()

    if args.self_test:
        r = unittest.TextTestRunner(verbosity=2).run(
            unittest.TestLoader().loadTestsFromTestCase(_SelfTest)
        )
        return 0 if r.wasSuccessful() else 1

    if _load_app_test() is None:
        msg = "未安装 streamlit，跳过看板冒烟（pip install streamlit 后可跑）。"
        print(msg)
        return 1 if args.strict else 0

    ok, msg = run_once()
    if ok:
        print(f"看板冒烟通过：{msg}")
        return 0
    print(f"看板冒烟失败：{msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
