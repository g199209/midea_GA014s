# 美的 GA014s 中央空调网关 HTTP 协议文档

## 设备概述

| 项目 | 值 |
|------|-----|
| 设备型号 | GA014s（美的智能网关 / MDV Gateway） |
| 固件版本 | v20 (Mar 24 2022) |
| 设备名称 | MDV Gateway |
| Web 管理界面 | `http://<host>/` (路由设置) + `http://<host>/ac/` (中央空调管理系统 CCM15X) |
| 协议 | HTTP GET，无认证（空调控制 API），管理 API 需 admin 密码登录 |

GA014s 是美的中央空调的 485 总线网关，通过 HTTP 接口暴露局域网内的空调内机控制。一台网关最多可连接 64 台内机（addr 0-63）。

## API 基础格式

所有请求均为 HTTP GET：

```
http://<host>/protocol.csp?fname=<fname>&opt=<opt>&function=<get|set>&<params>
```

| 参数 | 说明 |
|------|------|
| `fname` | 功能模块：`485`（空调控制）、`system`（登录认证）、`net`（网络）、`sys`（时区） |
| `opt` | 操作名称 |
| `function` | `get`（读取）或 `set`（设置） |
| 额外参数 | 操作特定的 query 参数 |

响应为 JSON，结构统一：

```json
{
  "opt": "<echo opt>",
  "fname": "<echo fname>",
  "function": "<echo function>",
  "arg": "<string or object, 操作特定>",
  "error": 0
}
```

`arg` 字段有两种形态：
- **对象**：如 `{"cmd": "getroomlist", "roomlist": "<内嵌JSON字符串>"}`
- **字符串**：如 `"{\"cmd\":\"getaclist\",\"aclist\":[...]}"` （需要二次 JSON 解析）

`error` 为 0 表示成功，非 0 表示错误。

## API 端点清单

### 1. 网关信息 — whois

```
GET /protocol.csp?fname=485&opt=whois&function=get
```

返回网关设备信息。

**响应示例：**
```json
{
  "opt": "whois",
  "fname": "485",
  "function": "get",
  "arg": "{\"cmd\":\"iam\",\"name\":\"MDV Gateway\",\"version\":\"v20\",\"date\":\"Mar 24 2022\",\"time\":\"02:10:55\"}",
  "error": 0
}
```

### 2. 房间/空调列表 — getroomlist

```
GET /protocol.csp?fname=485&opt=getroomlist&function=get
```

返回所有空调内机的名称列表（按 addr 索引）。

**响应结构：**
`arg` 是一个对象，其中 `arg.roomlist` 是内嵌的 JSON 字符串，解析后得到：
```json
{
  "aclist": [
    {"name": "Room 1"},        // addr 0
    {"name": "Room 2"},        // addr 1
    {"name": "Room 3"},        // addr 2
    {"name": "中央空调_03"},   // addr 3 (未连接实际设备)
    ...
    {"name": "中央空调_63"}    // addr 63
  ],
  "roomitem": [],
  "timezone": ""
}
```

`aclist` 数组索引即空调的 `addr`（地址）。本实例中 addr 0-2 有实际设备，3-63 为占位符。

### 3. 空调状态 — getaclist

```
GET /protocol.csp?fname=485&opt=getaclist&function=get&haddr=<start>&taddr=<end>
```

按地址范围批量查询空调状态。由于单次请求有数量限制，前端分 7 次请求覆盖全部 64 个地址：
`haddr=0&taddr=9`, `haddr=10&taddr=19`, ..., `haddr=60&taddr=63`

**响应结构：**
`arg` 是一个 JSON 字符串，解析后得到：
```json
{
  "cmd": "getaclist",
  "aclist": [
    {
      "addr": "0",
      "name": "",
      "error": "0",
      "type": "3",
      "is_new_idu": "1",
      "group": "0",
      "room_temp": "25.5",
      "run_mode": "0",
      "cool_temp_set": "26",
      "heat_temp_set": "0",
      "fan_speed": "0",
      "is_auto_fan": "0",
      "is_auto_mode": "0",
      "is_swing": "0",
      "is_elec_heat": "0",
      "is_have_auto_mode": "0",
      "is_lock_rc": "0",
      "is_lock_cool": "0",
      "is_lock_heat": "0",
      "cool_temp_limit": "0",
      "heat_temp_limit": "0",
      "fan_speed_lock": "0",
      "is_swing_lock": "0",
      "is_on_lock": "0",
      "is_off_lock": "0"
    }
  ]
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `addr` | string(int) | 空调地址（0-63），对应 getroomlist 中的索引 |
| `name` | string | 名称（getaclist 返回为空，需从 getroomlist 取） |
| `error` | string(int) | 错误码，0=正常 |
| `type` | string(int) | 内机类型 |
| `room_temp` | string(float) | 当前室温（°C） |
| `run_mode` | string(int) | 运行模式：0=关, 1=送风, 2=制冷, 3=制热, 4=自动, 5=除湿 |
| `cool_temp_set` | string(int) | 制冷设定温度（°C） |
| `heat_temp_set` | string(int) | 制热设定温度（°C） |
| `fan_speed` | string(int) | 风速：0=关, 1-7=1-7档, 8=自动（当 is_auto_fan=1 时） |
| `is_auto_fan` | string(int) | 是否自动风速：0=否, 1=是 |
| `is_auto_mode` | string(int) | 是否自动模式 |
| `is_swing` | string(int) | 是否扫风/摆风：0=否, 1=是 |
| `is_elec_heat` | string(int) | 是否电辅热：0=否, 1=是 |
| `is_have_auto_mode` | string(int) | 设备是否支持自动模式 |
| `is_lock_rc` | string(int) | 遥控器锁定 |
| `is_lock_cool` | string(int) | 制冷锁定 |
| `is_lock_heat` | string(int) | 制热锁定 |
| `cool_temp_limit` | string(int) | 制冷温度限制 |
| `heat_temp_limit` | string(int) | 制热温度限制 |
| `fan_speed_lock` | string(int) | 风速锁定 |
| `is_swing_lock` | string(int) | 扫风锁定 |
| `is_on_lock` | string(int) | 开机锁定 |
| `is_off_lock` | string(int) | 关机锁定 |

### 4. 设置空调 — setac

```
GET /protocol.csp?fname=485&opt=setac&function=set&addr=<addr>&run_mode=<mode>&fan_speed=<fan>&cooling_temp=<temp>&heating_temp=<temp>&extflag=<flags>
```

**参数说明：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `addr` | int | 空调地址（0-63） |
| `run_mode` | int | 运行模式：0=关, 1=送风, 2=制冷, 3=制热, 4=自动, 5=除湿 |
| `fan_speed` | int | 风速：0-7（档位），自动风由 extflag 控制或 is_auto_fan |
| `cooling_temp` | int | 制冷设定温度（°C） |
| `heating_temp` | int | 制热设定温度（°C） |
| `extflag` | int | 扩展标志位（位运算）：bit1(值2)=电辅热, bit2(值4)=扫风 |

**extflag 位运算：**
```
extflag = 0              # 无电辅热，无扫风
extflag = 2              # 开电辅热
extflag = 4              # 开扫风
extflag = 6              # 开电辅热 + 开扫风
```

**注意：** `cooling_temp` 和 `heating_temp` 总是同时发送。当前是制冷模式时设 `cooling_temp=目标温度, heating_temp=目标温度`（旧插件代码 `set_status` 中两者设为同一个值），非制冷模式时也保持发送。

### 5. 锁定空调 — lockac

```
GET /protocol.csp?fname=485&opt=lockac&function=set&...
```

锁定/解锁空调的某些功能（遥控器锁定、温度限制等）。具体参数需进一步抓包确认。

### 6. 设置房间列表 — setroomlist

```
GET /protocol.csp?fname=485&opt=setroomlist&function=set&...
```

修改空调内机的名称和分组。具体参数需进一步抓包确认。

### 7. 登录/登出（管理 API） — login / logout

```
GET /protocol.csp?fname=system&opt=login&function=set&...
GET /protocol.csp?fname=system&opt=logout&function=set
```

管理界面（路由设置、时区等）需要先登录。空调控制 API（fname=485 的 getaclist/setac/getroomlist/whois）**不需要登录**。

### 8. 网络信息 — wan_info

```
GET /protocol.csp?fname=net&opt=wan_info&function=get
```

返回 WAN 网络配置信息。

### 9. 时区 — timezone

```
GET /protocol.csp?fname=sys&opt=timezone&function=get
GET /protocol.csp?fname=sys&opt=timezone&function=set&...
```

获取/设置网关时区。需要登录。

## 数据获取策略

由于 getaclist 需要按地址范围分批查询，推荐的轮询策略：

1. 启动时调用 `getroomlist` 获取所有空调名称（只需一次）
2. 调用 `getaclist` 分 7 批查询所有地址（`haddr=0&taddr=9` 到 `haddr=60&taddr=63`），确定哪些 addr 有实际设备（aclist 非空）
3. 后续轮询只需查询有设备的地址范围，或一次性查询 `haddr=0&taddr=63`
4. 将 getroomlist 的名称与 getaclist 的状态按 addr 合并

本实例中只有 addr 0-2 有实际设备，可以只轮询 `haddr=0&taddr=9`。

## 与 HA 集成的映射

| GA014s 字段 | HA Climate 属性 | 说明 |
|-------------|-----------------|------|
| `run_mode` | `hvac_mode` | 0→off, 1→fan_only, 2→cool, 3→heat, 4→auto, 5→dry |
| `room_temp` | `current_temperature` | 当前室温 |
| `cool_temp_set` | `target_temperature` | 设定温度（制冷时） |
| `heat_temp_set` | `target_temperature` | 设定温度（制热时） |
| `fan_speed` + `is_auto_fan` | `fan_mode` | 0→off, 1-7→各档, auto |
| `is_swing` | `swing_mode` | 0→off, 1→on |
| `is_elec_heat` | `is_aux_heat` | 0→off, 1→on |
| `addr` | `unique_id` | 实体唯一标识 |
| getroomlist `name` | `name` | 实体名称 |

温度范围：17-30°C（旧插件代码硬编码 min_temp=17, max_temp=30）。
