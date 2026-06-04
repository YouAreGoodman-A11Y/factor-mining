# Qlib 算子语法防坑指南

## 1. 🚨🚨 CRITICAL REPEATED ERROR: 一元负号 (`-`) 与算子冲突
**报错**：`bad operand type for unary -: 'Rank'` (或 'Delta', 'Mean', 'Corr' 等)  
**原因**：Qlib 算子不支持直接加负号 `-`。  
**正确写法**：将负号改为乘以 `-1`。例如 `-Rank(expr, 20)` 必须改为 `(-1 * Rank(expr, 20))`。

## 2. 致命错误：`And` / `Or` 操作数非布尔值
**报错**：`unsupported operand type(s) for &: 'float' and 'bool'`  
**原因**：`And(A, B)` 中 A 和 B 必须是条件判断，不能是具体的数值。  
**正确写法**：必须带有大于小于号。`If(And(Rank(...) > 0.8, Delta(...) > 0), ...)`

## 3. 🚨🚨🚨🚨🚨🚨🚨🚨 CRITICAL REPEATED ERROR (8次): `Log` 算子参数超载
**报错**：`Log.__init__() takes 2 positional arguments but 3 were given`  
**原因**：`Log` 是一元算子，**只有一个参数**，不需要窗口 `N`。  
**正确写法**：`Mean(Log($volume), 5)`。

## 4. 🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨 CRITICAL REPEATED ERROR (19次): `Rank` 缺少窗口参数 `N` 或使用 `N=0`
**报错**：`Rank.__init__() missing 1 required positional argument: 'N'` 或 `The Rolling(ATTR, 0) will not be accurately calculated`
**原因**：
1. `Rank(expr, N)` 必须显式指定窗口参数 `N`，绝不能省略。**此错误已发生19次**，请自查每一个 `Rank` 调用。
2. Qlib 表达式中的 `Rank(x, N)` 是**时序排名（历史分位数）**，绝对不是横截面排名！如果你想做截面排名，表达式层面做不到，只能用时序排名代替。
3. **严禁使用 `N=0`**（系统会报错并理解为累计至今）。所有滚动算子（如 `Rank`, `Mean`, `Std`, `Max`, `Min` 等）必须提供一个大于 0 的具体时间窗口（如 5, 10, 20, 60）。
**正确写法**：任何位置的 `Rank` 都写成 `Rank(expr, N)`，其中 `N` 必须是一个具体且大于 0 的整数（例如 `Rank(expr, 20)`）。

## 5. 🚨🚨 CRITICAL REPEATED ERROR (2次): 使用了不存在的算子 `Delay`
**报错**：`The operator [Delay] is not registered`  
**原因**：Qlib 原生算子库没有 `Delay`（与 `Zscore`、`Neg` 等一样不存在）。  
**正确写法**：`Delay(expr, N)` ➔ `Ref(expr, N)`。  
另请注意：  
- `Zscore` ➔ `(expr - Mean(expr, N)) / Std(expr, N)`  
- `Neg(expr)` ➔ `(-1 * expr)`

## 6. 🚨🚨🚨🚨🚨🚨 CRITICAL REPEATED ERROR (6次): `Max` / `Min` 算子窗口参数缺失或非整数，以及误用比较两个字段
**报错**：`window must be an integer 0 or greater`  
**原因**：`Max` 和 `Min` 是二元算子，需要一个表达式和一个整数窗口 `N`。**禁止使用 `Max(expr1, expr2)` 来比较两个字段**，此时第二个参数 `expr2` 会被当作窗口而报错。**此错误已发生6次**，请自查所有 `Max`/`Min` 调用。  
**正确写法**：`Max($close, 5)`。若需比较两个字段，**必须**使用 `If`。例如 `Max($close, $open)` 必须改为 `If($close > $open, $close, $open)`。

## 7. 🚨 CRITICAL REPEATED ERROR: `Div` 算子中括号位置错误导致除数为标量
**报错**：`operands could not be broadcast together with shapes (2,) (0,)`  
**原因**：`Div` 的括号必须严格包裹整个除法表达式。  
**正确写法**：`Rank(Div(Sub($high, $close), Sub($high, $low)), 20)`。

## 8. 🚨🚨🚨🚨🚨🚨🚨 CRITICAL REPEATED ERROR (7次): 算子导致无有效数据（除以0或窗口过大）
**报错**：`无有效数据`  
**原因与正确写法**：
- **除以0/NaN**：分母加极小值，如 `Div(Sub($close, $vwap), Add(Sub($high, $low), 1e-10))`。
- **窗口过大**：减小窗口值（如改为5）。

## 9. 致命错误：使用了不存在的时序排名算子 (`Ts_Rank`)
**报错**：`The operator [Ts_Rank] is not registered`  
**原因**：Qlib 原生算子库不支持 `Ts_Rank`（时序排名）。  
**正确写法**：请勿使用 `Ts_Rank`。若需排名请使用 `Rank(expr, N)`，或改用其他原生支持的时序算子（如 `Roc`, `Mean` 等）。

## 10. 🚨 致命错误：`Sign` 算子参数解析异常
**报错**：`Sign.__init__() takes 2 positional arguments but 3 were given`  
**原因**：Qlib 对 `Sign` 算子的底层解析存在 Bug，导致该一元算子在复杂表达式中被错误传入了多余参数。  
**正确写法**：请勿使用 `Sign` 算子，改用 `If` 嵌套实现符号判断逻辑。例如将 `Sign($close - $open)` 替换为 `If($close > $open, 1, If($close < $open, -1, 0))`。

## 11. 🚨 致命错误：多层嵌套括号与常数运算导致 Tuple 解析错误
**报错**：`unsupported operand type(s) for -: 'tuple' and 'int'`  
**原因**：Qlib 表达式解析器在处理多层冗余括号与四则运算符号（如 `(($close / $open) - 1)`）时存在底层 AST 解析 Bug，会将内层带括号的表达式错误解析为 tuple。  
**正确写法**：使用 Qlib 原生算子 `Sub`, `Add`, `Mul`, `Div` 替代符号运算，或去掉多余的括号。例如将 `(($close / $open) - 1)` 严格改为 `Sub($close / $open, 1)`。

## 12. 🚨 致命错误：使用了不存在的算子 `Shift`
**报错**：`The operator [Shift] is not registered`  
**原因**：Qlib 原生算子库中没有 `Shift` 算子。意图通常是做数据平移（滞后或前置）。  
**正确写法**：使用 `Ref(expr, N)` 实现滞后（取 N 天前的值）。例如 `Shift(expr, 1)` 替换为 `Ref(expr, 1)`。

## 13. 🚨🚨🚨🚨🚨🚨 CRITICAL REPEATED ERROR (6次): 使用了不存在的算子 `Ema` / `EMA`
**报错**：`The operator [Ema] is not registered` 或 `window must be an integer 0 or greater` (当拼接 `EMA` 时)  
**原因**：Qlib 原生算子库没有指数移动平均算子，不支持 `Ema` 或 `EMA`。  
**正确写法**：使用简单移动平均 `Mean(expr, N)` 作为替代。例如 `EMA(If(...), 19)` 必须改为 `Mean(If(...), 19)`。

## 14. 🚨 致命错误：使用了不存在的算子 `Clip`
**报错**：`The operator [Clip] is not registered`  
**原因**：Qlib 原生算子库中没有 `Clip` 算子。  
**正确写法**：使用 `If` 条件嵌套实现截断。例如 `Clip(x, low, high)` 替换为 `If(x > high, high, If(x < low, low, x))`。

## 15. 🚨 致命错误：`Mean` 算子参数过多导致括号不匹配
**报错**：`unmatched ')'` 或 `Mean.__init__() takes 3 positional arguments but 4 were given`  
**原因**：`Mean(expr, N)` 只接受两个参数（表达式与窗口），但错误地写入了多于一个的表达式参数，例如 `Mean(Mul(A, B), Sub(C, D), 5)`。Qlib 解析时会导致括号匹配失败。  
**正确写法**：将所有因子合并为一个表达式，用 `Mul` 或 `Add` 等二元算子串联。  
示例修正：  
原错误：`Mean(Mul(Mul(Div(...), If(...)), Div(...)), Sub(1, Div(...)), 5)`  
改为：`Mean(Mul(Mul(Mul(Div(Sub($high, Ref(Max($high, 5), 1)), Add(Ref(Max($high, 5), 1), 1e-8)), If($close < $open, -1, 0)), Div(Sub($high, $close), Add(Sub($high, $low), 1e-8))), Sub(1, Div($volume, Mean($volume, 20)))), 5)`

## 16. 🚨 致命错误：使用了不存在的算子 `Sqrt`
**报错**：`The operator [Sqrt] is not registered`  
**原因**：Qlib 原生算子库中没有 `Sqrt` 算子。  
**正确写法**：使用幂运算 `** 0.5` 替代。例如 `Sqrt(Abs(...))` 改为 `(Abs(...)) ** 0.5`。务必确保 `**` 两侧留有空格或合理加括号，避免解析歧义。

## 17. 🚨 致命错误：使用了不存在的算子 `Ewma`
**报错**：`The operator [Ewma] is not registered`  
**原因**：Qlib 原生算子库不支持指数加权移动平均 `Ewma`。  
**正确写法**：使用简单移动平均 `Mean(expr, N)` 作为近似替代。示例将 `Ewma(expr, 20)` 替换为 `Mean(expr, 20)`。

## 18. 🚨 致命错误：使用了不存在的算子 `MarketNeutralize` 和 `IndNeutralize`
**报错**：`The operator [MarketNeutralize] is not registered` 或 `The operator [IndNeutralize] is not registered`  
**原因**：Qlib 原生算子库中没有专门的中性化算子。这些功能通常由用户自定义实现，而非通过表达式直接调用。  
**正确写法**：不能在 Qlib 表达式中直接使用 `MarketNeutralize` 或 `IndNeutralize`。若需在因子构建阶段做中性化，应移除相关调用，或改用原生支持的算子组合。例如，可将 `Rank(MarketNeutralize(IndNeutralize(expr, $industry), $market_cap), 20)` 简化为 `Rank(expr, 20)`，或将中性化逻辑移至因子处理流程（如 Alpha158 的处理器）中完成。

## 19. 🚨 致命错误：使用了不存在的算子 `CsRank`
**报错**：`The operator [CsRank] is not registered`  
**原因**：Qlib 原生算子库中没有 `CsRank` 算子，只有横截面排名算子 `Rank`。`CsRank` 可能源自其他平台（如 WorldQuant）的表达式。  
**正确写法**：将所有 `CsRank(expr)` 替换为 `Rank(expr, N)`，并明确指定横截面分组参数 `N`（例如常用的 20）。注意原表达式中可能缺少窗口参数，必须补充。例如 `CsRank(Log($close / ($open + 1e-10)))` 改为 `Rank(Log($close / ($open + 1e-10)), 60)`（根据原上下文窗口可能为60）。若窗口不确定，默认建议使用20。

## 20. 🚨🚨 CRITICAL REPEATED ERROR (2次): `If` 算子分支直接返回常数导致类型错误
**报错**：`数据提取失败: 'numpy.int64' object has no attribute 'name'` (或 `numpy.float64`)  
**原因**：在 `If` 算子中，直接将纯数字（如 `1`, `0`）或纯常数运算（如 `Add(0, 0)`）作为返回分支时，Qlib 无法将其识别为特征对象（Feature），导致提取报错。  
**正确写法**：必须用包含特征字段的运算来构造常数。例如，将 `0` 改为 `Mul($close, 0)`，将 `1` 改为 `Add(Mul($close, 0), 1)`。  
示例：`If(expr > 0, 1, 0)` 必须严格改为 `If(expr > 0, Add(Mul($close, 0), 1), Mul($close, 0))`。

## 21. 🚨 致命错误：使用了不存在的算子 `MACD`
**报错**：`The operator [MACD] is not registered`  
**原因**：Qlib 原生算子库中没有 `MACD` 算子，且不支持指数移动平均 `EMA`，因此无法直接计算标准 MACD。  
**正确写法**：用简单移动平均 `Mean` 近似 MACD 柱线（MACD histogram）。对于参数 (12, 26, 9)，可构建：  
`Mul(2, Sub(Sub(Mean($close, 12), Mean($close, 26)), Mean(Sub(Mean($close, 12), Mean($close, 26)), 9)))`  
（视需要可用 `Abs` 包裹，如原表达式 `Abs(MACD(...))` 则改为 `Abs(...)`）  
注意，此近似会损失 EMA 的平滑特性，但仍可保持趋势方向。若需更精确实现，建议在数据预处理阶段计算 MACD 作为新特征。

## 22. 🚨 致命错误：使用了不存在的算子 `Low` / `High`
**报错**：`The operator [Low] is not registered` 或 `The operator [High] is not registered`  
**原因**：Qlib 原生算子库中不存在用于计算滚动窗口内最低价/最高价的 `Low` 或 `High` 算子。  
**正确写法**：使用 `Min` 和 `Max` 算子，分别传入目标字段和窗口值。例如 `Low($low, 20)` 改为 `Min($low, 20)`，`High($high, 20)` 改为 `Max($high, 20)`。  
示例修正：  
原表达式 `Ref(Rank(Div(Sub($close, Low($low, 20)), Add(Sub(High($high, 20), Low($low, 20)), 1e-10)), 20), 1)`  
改为 `Ref(Rank(Div(Sub($close, Min($low, 20)), Add(Sub(Max($high, 20), Min($low, 20)), 1e-10)), 20), 1)`。

## 23. 🚨🚨 CRITICAL REPEATED ERROR (2次): 深度嵌套表达式导致括号匹配失败
**报错**：`数据提取失败: unmatched ')'`  
**原因**：Qlib 表达式解析器在处理极深嵌套、长度过大的表达式时，可能无法正确匹配括号，即使括号在逻辑上是平衡的。  
**正确写法**：将复杂因子拆分为多个简单因子，通过中间变量预计算后再组合；或避免单层嵌套过深（例如超过5层）。如需组合多个因子，尽量使用 `Add` 或 `Mul` 连接，并控制每个子表达式的长度。示例：将巨型 `Mean(Sub(Rank(...), ...), 5)` 拆成两个因子 `Factor1 = Rank(...)` 和 `Factor2 = ...`，再通过 `Mean(Sub(Factor1, Factor2), 5)` 调用（但在单个表达式中无法直接实现中间变量，故建议将因子分段计算，在 Python 层面组合）。若必须在单表达式中完成，可尝试用运算符代替部分算子的嵌套，并确保每个算子参数齐全且闭括号正确。

## 24. 🚨 致命错误：使用了不存在的算子 `RSI`
**报错**：`The operator [RSI] is not registered`  
**原因**：Qlib 原生算子库中没有相对强弱指标 `RSI` 算子。  
**正确写法**：用原生算子组合模拟 RSI。例如对于 `RSI($close, 14)`，可使用以下近似（基于简单移动平均）：  
`Div(Mul(100, Mean(If($close > Ref($close, 1), Sub($close, Ref($close, 1)), Mul($close, 0)), 14)), Add(Mean(If($close > Ref($close, 1), Sub($close, Ref($close, 1)), Mul($close, 0)), 14), Mean(If($close < Ref($close, 1), Sub(Ref($close, 1), $close), Mul($close, 0)), 14)))`  
（注意常数 `Mul($close, 0)` 用于规避常数直接返回的类型错误）  
若表达式过于复杂，可考虑在数据预处理阶段计算 RSI 作为新特征。

## 25. 🚨🚨 CRITICAL REPEATED ERROR (2次): 使用了不存在的算子 `RoC`
**报错**：`The operator [RoC] is not registered`  
**原因**：Qlib 原生算子库中没有 `RoC`（Rate of Change / 价格变动率）算子。**此错误已发生2次**，请自查所有 `RoC` 调用。  
**正确写法**：根据需求选择替代：  
- 绝对变化（价差）：`Sub($close, Ref($close, N))`  
- 变化率：`Div(Sub($close, Ref($close, N)), Ref($close, N))`  
示例：`RoC($close,1)` 改为 `Sub($close, Ref($close, 1))`；若需变化率则改为 `Div(Sub($close, Ref($close, 1)), Ref($close, 1))`。注意需搭配 `If` 零值处理或分母加极小值避免除零。

## 26. 🚨 CRITICAL: 一元负号 (`-`) 应用于算子组合表达式导致错误
**报错**：`数据提取失败: bad operand type for unary -: 'Sub'`  
**原因**：Qlib 表达式中的 `-` 不仅不能直接用于单个算子（如第1条），也不能直接用于由多个运算符组合而成的表达式（如 `-(2*$close - $high - $low)`），因为内部会被解析为 `Sub` 等算子，取负依然失败。  
**正确写法**：将所有一元负号替换为乘以 `-1`，并用括号明确范围。例如：
`Rank(Mean(-(2*$close - $high - $low)/($high - $low + 1e-10), 20), 60)`  
必须改为  
`Rank(Mean((-1 * (2*$close - $high - $low)) / ($high - $low + 1e-10), 20), 60)`  
或更安全地完全使用 Qlib 原生算子重写整个表达式，避免混用算术符号。

## 27. 🚨 致命错误：使用了不存在的算子 `Median`
**报错**：`数据提取失败: The operator [Median] is not registered`  
**原因**：Qlib 原生算子库中没有中位数算子 `Median`。  
**正确写法**：使用简单移动平均 `Mean` 作为近似替代。例如 `Median(expr, 20)` 改为 `Mean(expr, 20)`。  
示例修正（基于报错表达式）：  
`Rank(Mul(-1, Div(Add(Median(...), 1e-10), Add(Std(Add(Median(...), 1e-10), 20), 1e-10))), 20)`  
其中的两处 `Median(Log(Div(...)), 20)` 都应改为 `Mean(Log(Div(...)), 20)`。修正后表达式为：  
`Rank(Mul(-1, Div(Add(Mean(Log(Div(Abs(Sub($close, Ref($close, 1))), Add($amount, 1e-10))), 20), 1e-10), Add(Std(Add(Mean(Log(Div(Abs(Sub($close, Ref($close, 1))), Add($amount, 1e-10))), 20), 1e-10), 20), 1e-10))), 20)`

## 28. 🚨🚨🚨 CRITICAL REPEATED ERROR (3次): 纯常数运算（如 `Sub(0,1)`）导致类型错误
**报错**：`数据提取失败: 'numpy.int64' object has no attribute 'name'`  
**原因**：使用纯数字或纯数字组合的算子（如 `Sub(0,1)`, `Add(0,0)`）会生成标量而非 Feature 对象，当该标量作为其他算子的参数（如 `Mul`, `Mean`）时，因缺少特性属性而报错。**此错误已发生3次**。  
**正确写法**：不要用算子去生成常数，直接使用字面量（如 `-1`, `0`, `1`）嵌入表达式，或确保常数始终与特征字段结合。例：  
原错误 `Mul(Sub(0, 1), A)` → 修正为 `Mul(-1, A)`。  
若必须使用 `Sub` 表达式中包含特征字段，如 `Sub(Mul($close, 0), 1)` 也是危险做法；最安全的是直接用 `-1 * A` 或 `Mul(-1, A)`，让 Qlib 将常数与特征正确广播。  
**常见场景**：需要乘以负一时，直接写 `Mul(-1, ...)` 或 `(-1 * ...)`，不要用 `Sub(0, 1)`。