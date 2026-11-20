# RoomCheck · 密室谜题逻辑检查器

用可复现的路径回答：**能否通关？是否有操作顺序会把玩家困住？能否绕过必做谜题？**

An offline, deterministic logic checker for physical escape rooms and digital puzzle adventures. Python standard library only. No API keys, accounts or AI services.

**状态：本地 MVP / 0.1.0。** 以用户明确写出的 JSON 规则为依据，尚未经过真实密室设计者试用。实体密室和线上解谜共用一个抽象模型；所有示例均为原创虚构内容。

## 五分钟运行

需要 Python 3.11 或更高版本。在项目根目录运行，不需要 pip 安装或网络连接：

```powershell
python -m roomcheck examples/physical.json
python -m roomcheck examples/digital.json
python -m roomcheck examples/softlock.json
python -m unittest discover -s tests -v
```

第三个命令故意返回退出码 `1`，表示找到了问题。关键输出：

```text
Winning path: power_exit
[error] DEAD_END: A reachable unfinished state has no enabled actions.
  Trace: play_radio
  Inventory: music
[error] SOFTLOCK: This choice sequence makes the goal unreachable, although another path can win.
  Trace: play_radio
  Inventory: music
```

解释：直接给出口供电可以通关；先把唯一的电池用在收音机上，则无法通关。修复方案可能是让收音机不消耗电池，或增加可达的备用电池来源。修改后重新检查。

## 能检查什么

| 检查 | 结果 |
|---|---|
| 全局通关可达性 | 给出一条最短动作数通关路径，或证明模型无解 |
| 顺序导致的软锁 | 给出进入无法通关状态的操作序列 |
| 未通关死路 | 给出没有可执行动作的状态和库存 |
| 必做谜题被绕过 | 给出通关但遗漏指定动作的路径 |
| 不可达动作 | 列出任何通关前流程都无法执行的动作 |
| 数据错误 | 拒绝拼错字段、重复 ID、未声明事实和错误类型 |
| 搜索过大 | 标记不完整，不作“所有路径安全”的结论 |

`DEAD_END` 是无动作可走；`SOFTLOCK` 是已经无法到达胜利，即使眼前仍有动作可走。两者可能指向同一问题。默认每种动态问题只展示一个代表性反例，不声称列出所有缺陷。

## 写自己的谜题

复制 `examples/physical.json`，修改副本。每个事实表示“玩家当前拥有／知道／已经开启”的一个布尔条件；每个动作最多执行一次。

```json
{
  "version": 1,
  "title": "我的第一间密室",
  "facts": ["key", "escaped"],
  "initial": ["key"],
  "goals": ["escaped"],
  "must_solve": ["open_exit"],
  "actions": [
    {
      "id": "open_exit",
      "label": "用钥匙打开出口",
      "requires_all": ["key"],
      "produces": ["escaped"]
    }
  ]
}
```

- `requires_all`：所有条件都需要；空列表表示无这类限制。
- `requires_any`：非空时至少满足其中一个；和 `requires_all` 同时成立才可执行。
- `consumes`：必须拥有，并在执行后移除；可用于一次性道具。
- `produces`：执行后加入库存的事实，不存在数量累加。
- `goals`：必须同时具备的胜利事实；达到后游戏立即结束。
- `must_solve`：设计者声明的必做动作，**用于检查，不会自动阻止绕过**。
- ID 使用英文小写、数字和下划线，首字符为字母；中文写在 `title`、`label`。反例使用稳定 ID，方便定位原文件。

完整语义、限制和常见建模错误见 [模型说明](docs/MODEL.md)。实体房间进入权限可建模为 `room_open`；线上认证状态可建模为 `logged_in`。它们都是事实，并不自动检查物理空间或游戏源代码。

## 报告和自动化

```powershell
python -m roomcheck examples/physical.json --json
python -m roomcheck examples/physical.json --max-states 50000
```

JSON 输出可保存到你选定的新文件；重复使用重定向路径可能覆盖已有报告。

| 退出码 | 含义 |
|---|---|
| 0 | 搜索完成，无 error；仍可能有不可达动作 warning |
| 1 | 已发现确定错误；另看 `complete` 判断搜索是否完整 |
| 2 | 输入文件、参数或模型无效 |
| 3 | 搜索未完成且尚未发现确定错误 |

`solvable: true` 只表示存在通关路径。更强的 `all_states_can_win: true` 表示所有模型内可达状态仍有通关办法；它不保证玩家愿意执行、看得懂线索或能够在时限内完成。搜索不完整时，未证明的布尔量为 `null`。

## 明确边界

当前不检查谜语答案唯一性、自然语言歧义、谜题难度、玩家知识、时间、物理安全、电子机关故障或多人各自持有道具。不是消防或实体场地检查项目。模型错误或漏掉玩家可做的动作，会造成错误的安全感；仍需真实试玩。

不支持可重复动作、负条件、物品数量、多人隔离库存和概率事件。最多 40 个动作、128 个事实，输入不超过 1 MiB；默认搜索 20,000 个状态，上限可设为 100,000。状态数量可能指数增长，限制是工程保护，不是性能承诺。

## 为什么做这个项目

已有工具支持依赖图、结构检查和模拟。RoomCheck 的候选定位是：**小模型、离线检查、消耗性道具、可复现反例、可放进 GitHub CI 的文本格式**。这是一项待验证的组合定位，不是“首创”，也不把接入 AI 当竞争壁垒。

阅读 [调研与需求证据](docs/RESEARCH.md)、[项目范围与验证计划](docs/PROJECT.md)、[算法与维护指南](docs/ARCHITECTURE.md)。调研依据公开产品说明和项目文档，没有把文档阅读写成实际运行竞品的结果。

## 项目结构

```text
roomcheck/
  core.py              # 校验、状态搜索、反例生成
  __main__.py          # 本地 CLI 和退出码
examples/              # 实体、线上、软锁、循环、绕过案例
tests/test_core.py     # 行为测试 + 独立穷举对照
docs/                  # 需求证据、模型、架构、发布准备
.github/workflows/     # 发布后可运行的自动检查
```

本地已验证平台与测试记录见 [CHECKS.md](docs/CHECKS.md)。GitHub Actions 配置不代表远端已经执行。

## 贡献和许可

代码与示例为本项目新编写，采用 [MIT License](LICENSE)，未复制竞品代码或素材。欢迎提交最小可复现 JSON 和期望行为，参见 [CONTRIBUTING.md](CONTRIBUTING.md)。项目名称暂定，未调查商标或软件包名称可用性；本版本不发布到 PyPI。
