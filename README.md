# 炉温试验线交班复盘

带材热处理试验线的两个炉区各有一条相对分钟时轴。采集质量不齐、炉区时钟有待对齐，勘误又可能在交班后发生。本工程供日班仪表员、炉区组长、夜班工艺分析员和次班工程师核定各自的工作记录。

1. 仪表员在各站登记校准，提交采集器的原读、时段和质量状态。系统整批核验，保存原读及校准后的有效段。
2. 组长按录制批号封存初版，清册提供可选择的修订号。
3. 有实测依据的勘误明确选择父版。新修订带父号和勘误依据，父版继续可查。
4. 组长以指定修订和现场阈值核定单站暴露，领取站件与同件号的回执。
5. 两站关闭数据库，夜班只带实际移交的两个件进入中心。
6. 夜班提交两件、事后选择的阈值和闭时差窗，中心核算共同超限。
7. 中心将参数、结论、有序父件和成功回执一并定稿。两站按甲乙顺序提交，时差加到乙站的时间上。
8. 次班重开报告库按号领取，并可使用新勘误件另签一份报告对照。

## 运行

要求 Python 3.11，只使用标准库。控制台物化提供标准回归入口。

```sh
python3 -B check_project.py
python3 -B -m unittest discover -s tests -t . -v
python3 -B demo.py
```

演示在临时目录录制、封存、发行并移动两站数据库，离线签报后再做勘误和历史对照。`samples/station-a.json` 和 `samples/station-b.json` 是有限的采集输入。演示按真实回执传递编号。编号是不可预测的不透明标识，计算结果对固定输入是确定的。

中心也可用文件操作入口领取和发布。选项的等号写法支持负有理数。成功输出 JSON，坏件、无效参数、未知报告或写入失败以非零状态退出。

```sh
python3 -B demo.py sign review.sqlite a.json b.json --threshold=4 --lag-min=-4 --lag-max=1
python3 -B demo.py read review.sqlite REPORT_ID
```

## Python 接口

使用 `sqlite3.connect` 打开每个站库及中心报告库。初始化站库时分别调用 `CalibrationRegistry(db).initialize()`、`RecordingStore(db).initialize()`、`SnapshotStore(db).initialize()` 和 `StationPieceStore(db).initialize()`。中心调用 `initialize_archive(db)`。初始化保留既有记录及调用者创建的内容。写接口自行提交，调用前请结束调用者自己的事务。

- `intake.calibration.CalibrationRegistry.register(calibration_id, offset)` 登记站库内唯一校准批号。校准温度等于原读加偏移。
- `intake.recording.record(db, station_id, recording_id, rows)` 接纳批次并返回 `StoredRecording`，`read_recording(db, station_id, recording_id)` 按号读取。行包含 `start`、`end` 和 `quality`。`valid` 行必有 `calibration_id`、`raw_start` 和 `raw_end`。`missing` 行可携带校准批号，两个原读必须为空或省略。明确缺测与未覆盖时间均无有效段。全部输入行须互不重叠，允许相邻和乱序输入。
- `revision.freeze.freeze(db, station_id, recording_id=...)` 封存录制。`freeze(db, station_id, parent_revision_id=..., correction=...)` 封存一条子修订。`Correction(start, end, segments, reason)` 用给出的校准安定段替换整个指定窗口，其余窗口内时间为缺测。窗口之外保留父版温度，包括切开的斜段。`revision.catalog.list_frozen_revisions` 和 `select_frozen_revision` 负责查册及按号选取。
- `issue.receipts.issue(db, station_id, revision_id, threshold)` 返回 `IssueReceipt`，包含 `piece_bytes`、`piece_id`、`revision_id`、`receipt_id` 和精确 `exposure`。`StationPieceStore(db).load_issue(piece_id)` 复取原发行字节和回执。
- `review.assemble.sign(db, left_piece, right_piece, threshold, lag_min, lag_max)` 接受两个站件的 UTF-8 JSON 字节，返回 `PublishedReport`，其中 `report` 为已签参数和结论，`parents` 为甲乙顺序的父件，`receipt` 为成功回执。
- `archive.export.read(db, report_id)` 返回相同结构。领取使用已归档数据，旧报告在更正、重新签报和重开后保持原结果及父件。

有理输入支持 Python 整数、`Fraction` 或 `Fraction` 可解析的字符串。JSON 交换使用字符串表示精确有理数。区段用分钟表示，炉温用摄氏度表示。录制与修订的两端读值确定区段内的仿射函数，右端读值是该段的右端极限。重叠时长的计量忽略零长度端点。恒温等于阈值时整段贡献零。时差窗可退化成一点，零重叠时整窗均最优。最优区间按升序存档，孤点表示为两个端点相同的闭区间。

V1 站件外层包含 `version`、`station_id`、`revision_id`、`piece_id`、`body`。当前交换正文使用 `{"affine":[["0","2","1","0"]]}` 表示 `[0,2)` 内 `T(t)=t`，每行依次为开始、结束、斜率及截距。空数组表示空有效域。站件携带派生温度，原读、校准记录、修订勘误依据及现场阈值留在站端。中心校验两份外层、不同站点、有效正文及有序闭窗。输入错误抛出 `ValueError`，不可解析的已有对象编号抛出 `KeyError`，存储失败保留 SQLite 错误。拒收或发布提交失败没有新增成功报告、父件或回执。
