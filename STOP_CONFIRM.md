# 停热确认交班

本功能在原炉温试验线项目上增加一份独立报告。现有录制、校准、温度封存、V1 发行与共同超限签发沿 `README.md`。各站的控制台交班时提供本次完整的实记停热指令列表。带材批号由两站使用同一值，站内录制号仍按原接口管理。

## 站件发行

`issue.receipts.issue_stop(db, station_id, revision_id, batch_id, commands) -> bytes`

`db` 为按原方式初始化的站库。用指定站点的确切封存修订发行 UTF-8 JSON 原文。每次发行取得独立件号。`commands` 为列表或元组，每行按 `(command_id, time)` 给出，可用列表或元组。时间为原站相对分钟。命令 ID 及批号沿 V1 非空文本规则。件内指令 ID 唯一，允许不同指令同刻。空清单有效。保留完整输入次序。即使某条指令目前没有足够温度证据，也保留这条实记记录，由中心按事后参数裁决。不存在指定站点和修订的组合时报 `KeyError`，非法入参报 `ValueError`。

V2 外层字段沿 V1，`version` 为整数 2。正文由 `batch_id`、`commands`、`affine` 组成。`affine` 每行为 `[start, end, slope, intercept]`，按时间排序，段长为正，段之间不重叠。它保存指定修订的有效温度曲线，缺测处没有有效段。每段在 `[start,end)` 上给出 `slope * t + intercept`。命令行和仿射行的有理数在 JSON 中用字符串表示。空命令或空有效域各用空数组。原读、校准和勘误记录留在站库。

下面是一份可独立提交的乙炉来件。

```json
{"version":2,"station_id":"B","revision_id":"rev-demo-b","piece_id":"piece-demo-b","body":{"batch_id":"coil-stop-01","commands":[["b0","0"]],"affine":[["-4","12","0","5"]]}}
```

## 中心签发与领取

`review.assemble.sign_stop(db, left_piece, right_piece, threshold, dwell, tolerance, lag_min, lag_max) -> dict`

`archive.export.read_stop(db, report_id) -> dict`

中心仍用 `archive.publish.initialize_archive(db)` 初始化，支持在已有中心库上重复调用。写入口沿 V1 使用空闲连接。签发使用甲、乙顺序提交的两份站件字节，其批号一致，站点和件号各自互异。两侧同名指令分别属于各自的站。中心直接核对来件，拒绝错版、错误字段、重复 JSON 键、重叠或无效仿射段及重复指令 ID。非法请求、坏件或失配报 `ValueError`。读取不存在的本类报告号报 `KeyError`。原 V1 入口和交换格式继续有效。

请求沿 `exact.rational` 接受整数、`Fraction` 和可解析的有理字符串。`dwell > 0`、`tolerance >= 0`、`lag_min <= lag_max`。时长和时差以分钟计，阈值为摄氏度。对于站件中每条时刻为 `t` 的实记指令，只有当 `[t, t + dwell)` 全程有有效温度且处处小于或等于 `threshold` 时，才列为合格指令。等阈有效，缺测使整条指令失去资格。驻留右端之后的温度不影响该条指令的资格。

在闭窗 `[lag_min, lag_max]` 内，对每个可用的时差 `lag`，乙炉所有合格指令统一平移 `lag`。一对须由两侧各一条合格指令组成，且 `abs(t_left - (t_right + lag)) <= tolerance`。一份指派中每条指令至多出现一次。签出闭窗内最多可同时成立的对数及达到该对数的全部时差。最优集合用升序的闭区间表示，重叠或相接的区间合并，孤点写成同端点区间。最大数为零时集合为整个请求窗。

签发与领取返回同结构的字典，成员如下。

| 成员 | 值 |
| --- | --- |
| `report_id`、`batch_id` | 固定报告号和带材批号，均为字符串 |
| `threshold`、`dwell`、`tolerance`、`lag_min`、`lag_max` | 实际采用的请求值，均为 `Fraction` |
| `max_pairs` | 最大同时配对数，整数 |
| `optimal_lags` | 闭区间元组，每项是 `(Fraction, Fraction)` |
| `eligible_commands` | 两侧清单的元组。每侧为 `(command_id, Fraction)` 行组成的元组，保持该站件中合格记录的原序和原站时刻 |
| `parents` | 甲、乙顺序的两个 `archive.provenance.ParentPieceRef`，含来件的站点、确切修订和件号 |
| `receipt` | `archive.receipts.PublicationReceipt`，包含本报告号和成功回执号 |

正文、所用父件和成功回执同次提交。失败不增加上述成果，解除写入故障后同一请求可重试。温度勘误可另发站件和报告。两站关闭或中心重开后，原报告按号领取固定正文、父件和回执。

## 样例及运行

`stop_examples.py` 提供 `SOURCES` 和 `CASES`。每个 `CASES` 项的左右 `source` 选取 `SOURCES` 的原测行，`commands` 作为该侧控制记录。按 `tests.fixtures.prepare_station` 分别组装甲乙站的冻结温度，样例阈值与时差参数由 `request` 给出。模块直接运行时通过 V1 录制、封存、发行和解码核对样例温度的有效域。

`shared-command` 的两条候选边只兑现一对。`empty-log` 和 `missing-evidence` 各签零对。`touching-at-zero` 的唯一最优时差为 0，签两对。`split-optimum` 只在 1、2 两点各可配一对，时差 3/2 无可用边。`excluded-right-end` 的乙炉只应列 `b0`，因为温度在第 1 分钟跳高，已在 `b0` 的驻留右端之外。

核对更正时，可从 `missing-evidence` 的乙炉父版出发，按 V1 勘误接口用恒温 5 的有效段恢复 `[1/2,3/4)`，再用同一控制清单另发行。新结论为 1 对，原报告仍为 0 对。提交失败验证可参考 `tests/test_publication.py` 的延迟外键范例，对新报告的实际提交路径验证回滚和重试。

复用 `.pointwise-runtime.json` 中的版本 1 和现有运行入口。`setup` 是准备命令的 argv 列表，`verify` 和 `demo` 各是一条 argv。沿 `check_project.py` 接通原回归与新业务核验，失败返回非零。沿 `demo.py` 的默认演示接通 V2 断源签发和重开领取，展示实际结果和父件。保留原测试文件及 V1 演示和入口。
