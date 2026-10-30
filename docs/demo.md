# 五分钟演示

顺序：ERD → 一条数据质量发现 → 一次加载失败保护 → 一组优化对照。每段写了屏幕上放什么、要说的要点，以及排练时的真实输出。每段一分钟的讲法见 [interview_pitch.md](interview_pitch.md)。

所有命令都在独立的实验集群上运行，不连共享的 PostgreSQL 18。

## 演示前准备（不计时，约 2 分钟）

在仓库根目录的 PowerShell 里执行。

1. 创建实验集群并加载数据（约 45 秒）。它监听 localhost:55433，使用 trust 认证，不需要密码。用完就删。

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\lab_cluster.ps1 create
   ```

2. 按脚本最后一行的提示设置环境变量，然后定义一个 psql 快捷方式：

   ```powershell
   $env:OLIST_DBE_PORT = '55433'; $env:OLIST_DBE_PG_BIN = 'C:\Program Files\PostgreSQL\18\bin'
   function lab-psql { & "$env:OLIST_DBE_PG_BIN\psql.exe" -X -h localhost -p $env:OLIST_DBE_PORT -U dbe_owner -d olist_dbe @args }
   ```

3. 预热一次。集群刚启动时缓存是空的，第一次执行会从磁盘读约 1,000 页，计划里的时间会偏大。

   ```powershell
   lab-psql -f scripts\demo\open_orders_plans.sql > $null
   ```

4. 准备一份坏数据：复制 9 个 CSV，只把一个订单的购买时间改成 25 点。`D:\project` 本身不改。

   ```powershell
   $demo = Join-Path $env:TEMP 'olist-broken'; New-Item -ItemType Directory -Force $demo | Out-Null
   Copy-Item D:\project\*.csv $demo
   $f = Join-Path $demo 'olist_orders_dataset.csv'
   [IO.File]::WriteAllText($f, ([regex]'2017-10-02 10:56:33').Replace([IO.File]::ReadAllText($f), '2017-10-02 25:56:33', 1), (New-Object Text.UTF8Encoding $false))
   ```

5. 打开要展示的页面：
   - [docs/erd.md](erd.md)：在能渲染 Mermaid 的预览里打开；
   - [docs/benchmarks/report.md](benchmarks/report.md)：翻到 E3。

## 0:00–1:00 ERD

**屏幕：** [docs/erd.md](erd.md) 的关系图。

**要说的：**
- `core` 有 10 张表。每条约束都先在数据上验证过；数据会违反的规则只做警告，不做约束（见 [decisions.md](decisions.md)）。
- 指三处设计，后面三段都会回到它们：
  1. **`customers` 和 `orders` 一对一。** `customer_id` 是每单发一个的；真正的人是 `customer_unique_id`。下一段就讲这个。
  2. **评价拆成两张表（2NF）。** 源文件里 789 条评价挂在多个订单上，同一条评价的内容是重复存的。拆成 `reviews` 和 `order_reviews` 之前，阻断检查 `review_content_consistent` 先证明了每份副本内容完全一致，所以拆分不丢信息。
  3. **虚线表示不建外键。** 157 个客户邮编前缀在地理表里不存在，建外键就得拒绝这些客户。
- 除了主键和一个唯一键，没有任何二级索引。这是有意的：二级索引是 benchmark 的实验对象，基准里不能有。

## 1:00–2:00 数据质量发现：谁是客户？

**屏幕：** 运行只读查询。

```powershell
lab-psql -f scripts\demo\customer_identity.sql
```

**排练时的输出：**

```text
 orders | customer_ids | persons
  99441 |        99441 |   96096

 by_customer_id | by_person
              0 |      2997

 persons_with_several_zip_prefixes | persons_with_several_states
                               250 |                          39
```

**要说的：**
- 99,441 个订单对应 99,441 个 `customer_id`，但只有 96,096 个人。所以 `customer_id` 是订单级标识。
- 按 `customer_id` 算复购人数是 0，按人算是 2,997（3.12%）。cohort 留存（Q6）按 `customer_id` 算，每个月都是 0%。
- 250 个人有多个邮编，39 个人跨州，所以地址属于订单而不属于人。决定是：`customers` 保持每单一行；用唯一键把「一单一个 `customer_id`」固定下来；所有按人计数的查询都用 `customer_unique_id`；这个陷阱由测试钉住。

## 2:00–3:30 加载失败保护

**屏幕：** 依次运行下面三条命令。加载约 15 秒，边跑边讲。

```powershell
.venv\Scripts\olist-dbe status
.venv\Scripts\olist-dbe load --data-dir $demo
.venv\Scripts\olist-dbe status
```

**排练时的输出（节选）：**

```text
error: BlockingChecksFailed: blocking checks did not pass: constraint_preconditions, timestamps_parse

load    2  failed    2026-10-29 20:48    14.2s  BlockingChecksFailed: ...
load    1  succeeded 2026-10-29 20:47    26.2s
core.orders                  99,441  md5 2a0ff6035589143621a493e6917a5291   ← 加载前后完全相同
```

需要细节时，运行 `.venv\Scripts\olist-dbe dq-report --load-id 2`：`timestamps_parse` 显示 1 条违规和样本行；`constraint_preconditions` 显示 error，因为它要转换的正是同一个值。

**要说的：**
- 155 万行里只改了一个值。加载在发布之前停下，点名了是哪项检查，退出码 1。`core` 每张表的校验和与加载前一致，正在读的人看到的仍是第 1 版。
- 原理：CSV 先进全文本暂存表，再跑 38 项检查（10 项阻断），最后在一个事务里对每张表做 MERGE。同一个事务把状态写成 `succeeded`，所以这一行就是提交标记。
- 最初的方案是「建 `core_next` 再改名替换」。我写的双连接测试证明它对旧快照不安全：一个 REPEATABLE READ 读者看到 `orders` 是 0 行，而不是 99,441 行。所以改成了现在的方案。
- 提交时如果断线：新开一个连接去确认；5 秒内确认不了，就报「未知」，退出码 3，不去猜。

## 3:30–5:00 优化对照：E3 未完成订单

**屏幕：** 先放 [report.md](benchmarks/report.md) 的 E3 表，再现场跑三个计划。整个脚本在一个最后回滚的事务里执行，不会留下索引。

```powershell
lab-psql -f scripts\demo\open_orders_plans.sql
```

**排练时的输出（两次单独运行的 EXPLAIN ANALYZE；中位数以报告为准）：**

| 计划 | 订单表的读法 | 第 1 次（冷缓存） | 第 2 次（已预热） |
|---|---|---:|---:|
| 1. 基准，只有主键 | Parallel Seq Scan，Gather Merge | 34.4 ms | 131.0 ms |
| 2. 同上，关闭并行（诊断） | Seq Scan，过滤掉 97,712 行 | 17.0 ms | 17.2 ms |
| 3. 加部分索引 | Index Scan using demo_orders_status_open，约 1,340 页 | 9.3 ms | 9.5 ms |

部分索引 32 kB，订单表 11 MB。并行计划两次相差近 4 倍，另外两个计划很稳定；报告里并行基准的 p95 是 135.9 ms，就是这条长尾。现场跑出哪个数都可以，正好说明为什么要看多次运行的中位数和 p95。

**要说的（数字来自报告：3 轮 × 20 次的中位数）：**
- 每个变体只改一个因素，并且结果指纹与基准一致才计时。
- 加索引后 31.63 → 7.86 ms，看起来快了 4 倍。但基准用的是并行计划；关掉并行，同一查询只要 14.81 ms。所以大部分提速来自避开了这台 Windows 机器上很贵的并行计划，索引本身相对串行计划大约快 2 倍。
- 省下的也不是读的页数：开放订单分散在整张表里，索引扫描仍然要碰 1,341/1,419 页。省的是对 97,712 行逐行判断再丢弃的工作。
- 部分索引和全索引一样快，但只有 32 kB 对 696 kB。代价是谓词就是它的契约：状态集合一变就得重建，否则会被悄悄弃用。
- 最后一句：失败的结果也发布了。BRIN 在这个物理布局上完全无效；把条件写成 `::date` 会慢 68%；全量报表上加索引毫无收益。

## 演示后

```powershell
powershell -ExecutionPolicy Bypass -File scripts\lab_cluster.ps1 remove
Remove-Item -Recurse -Force (Join-Path $env:TEMP 'olist-broken')
```

## 时间不够时

先删每段的最后一条要点。ERD 段保底说第 1 点，优化段保底说「4 倍里大部分是并行计划」和「部分索引小 22 倍」。
