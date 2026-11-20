# 本地检查记录

日期：2026-11-20。环境：Windows，Python 3.13.9。

- `python -m unittest discover -s tests -v`：22 项测试通过。
- 其中独立递归穷举对照覆盖 100 个固定种子的四动作随机模型。
- CLI 退出码 0/1/2/3、UTF-8 中文输出、BOM、非法输入、搜索截断均有测试。
- 所有 Markdown 本地文件链接已核验存在。
- 本地 Git 已初始化为 main；没有远程地址或推送。
- Python 3.11、Linux 和 GitHub Actions 尚未实际运行；已提供 CI 矩阵。
- 尚无真实用户试用或真实密室模型，不能将测试通过解释为市场验证。

## 五个示例实测

| 示例 | 状态数 | 结果 | 检查码 |
|---|---:|---|---|
| bypass.json | 4 | issues | REQUIRED_BYPASS |
| circular.json | 1 | issues | NO_SOLUTION, DEAD_END, UNREACHABLE_ACTION |
| digital.json | 10 | ok | 无 |
| physical.json | 7 | ok | 无 |
| softlock.json | 3 | issues | DEAD_END, SOFTLOCK |
