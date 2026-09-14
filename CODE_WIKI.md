# 露营装备租赁平台 Code Wiki

> 本文档全面介绍 `Camping_gear_rental`（露营装备租赁平台）后端架构、数据模型、API 接口及运行方式，并包含前端对接开发指南，供开发与维护参考。

---

## 1. 项目概述

### 1.1 项目定位
面向个人用户的露营装备在线租赁平台，支持装备浏览、购物车、下单租赁、在线支付、归还结算、装备买断、逾期管理及管理员后台运营等完整业务流程。

### 1.2 技术栈

| 层级 | 技术选型 | 版本/说明 |
|------|----------|-----------|
| Web 框架 | Django | 4.2.30 |
| API 框架 | Django REST Framework (DRF) | - |
| 认证方案 | JWT (simplejwt) | access=1天 / refresh=7天 + 黑名单 |
| 数据库 | MySQL（生产）/ SQLite（本地已有 db.sqlite3） | 库名：`camping_info` |
| 缓存/消息 | Redis（目录内有 redis.zip，待启用） | - |
| 图片存储 | Django MEDIA (`media/equipment_img/`) | 本地文件系统 |
| 支付 | 内置 `PaymentService` 模拟 | 便于 MVP 开发，预留真实支付接入位 |
| 前端（独立仓库） | Vue 3 + TypeScript + Vue Router + Pinia（推测，当前仓库未包含） | - |

### 1.3 前端说明
**当前 Git 仓库仅包含后端 Django 项目**，前端 Vue 项目未纳入本仓库。根据项目记忆，前端使用 Vue 3 + TypeScript，项目结构约定为：`types/`（TS 接口）、`api/`（请求函数）、`store/`（状态管理）、`views/`（页面组件）、`utils/`（通用工具如 axios 封装）。

---

## 2. 整体架构

### 2.1 分层架构

```
┌──────────────────────────────────────────────────────┐
│                    API Layer (views)                  │
│   DRF ViewSet / APIView  ──  接收请求、权限校验       │
├──────────────────────────────────────────────────────┤
│                 Serializer Layer                      │
│   DRF Serializers  ──  数据校验、序列化/反序列化       │
├──────────────────────────────────────────────────────┤
│                 Service Layer                         │
│   OrderService / PaymentService  ──  核心业务逻辑     │
│   事务控制、并发锁、状态流转、费用计算                 │
├──────────────────────────────────────────────────────┤
│                 Model Layer (ORM)                     │
│   Django Models  ──  数据结构、数据库交互              │
├──────────────────────────────────────────────────────┤
│                 Database (MySQL)                      │
└──────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
Camping_gear_rental/
├── Camping_gear_rental/        # Django 项目配置包
│   ├── settings.py             # 全局配置（数据库、JWT、DRF、MEDIA）
│   ├── urls.py                 # 根路由（分发到 /api/）
│   ├── asgi.py / wsgi.py       # 部署入口
│   └── __init__.py
├── api/                        # 统一路由分发入口（空 views）
│   └── urls.py                 # 聚合 users/equipment/orders/common 路由
├── users/                      # 用户模块
│   ├── models.py               # UserInfo 自定义用户模型
│   ├── serializers.py          # 注册/登录/修改密码/用户信息序列化器
│   ├── views.py                # 注册、登录、验证码、改密、登出、管理员冻结
│   ├── urls.py                 # 用户模块路由
│   └── migrations/
├── equipment/                  # 装备与分类模块
│   ├── models.py               # Category（自关联）、Equipment
│   ├── serializers.py          # 分类/装备的展示、详情、管理员序列化器
│   ├── views.py                # 分类、装备展示与管理员 CRUD ViewSet
│   ├── urls.py                 # 使用 DefaultRouter 注册
│   └── migrations/
├── orders/                     # 订单与购物车模块（核心业务）
│   ├── models.py               # Order、OrderItem、Cart、CartItem
│   ├── serializers.py          # 订单、订单项、创建订单、退款、购物车等序列化器
│   ├── services.py             # ★ OrderService：所有订单核心业务逻辑
│   ├── views.py                # 用户订单视图、管理员订单视图、购物车视图
│   ├── urls.py                 # 订单 + 购物车路由
│   └── migrations/
├── common/                     # 通用模块
│   ├── services/
│   │   └── payment_service.py  # ★ PaymentService：模拟第三方支付
│   ├── views.py                # ImageUploadView 管理员图片上传
│   ├── urls.py                 # 图片上传路由
│   └── models.py / admin.py    # （空，预留）
├── media/
│   └── equipment_img/          # 装备封面图片存储目录
├── redis/
│   └── redis.zip               # Redis 压缩包（待启用）
├── manage.py                   # Django 管理脚本
├── db.sqlite3                  # SQLite 数据库文件（本地开发使用）
└── CODE_WIKI.md                # ★ 本文档
```

### 2.3 应用依赖关系

```
users ─────────┐
               │
equipment ◄────┤
               ├──► orders ◄── common (PaymentService / ImageUpload)
               │
api (路由聚合) ─┘
```

- `users`：独立模块，被 `orders`（订单归属用户）引用
- `equipment`：独立模块，被 `orders`（订单项关联装备）引用
- `orders`：核心模块，依赖 `users`、`equipment`、`common.services.payment_service`
- `common`：公共服务层，被 `orders` 依赖
- `api`：仅做路由聚合，无业务逻辑

---

## 3. 数据模型详解

### 3.1 ER 关系图

```
UserInfo (1) ──── (N) Order (1) ──── (N) OrderItem (N) ──── (1) Equipment
     │                                                        │
     │ (1:1)                                                  │ (N:1)
     └─── Cart (1) ──── (N) CartItem ────────────────────────┘

Category (1) ──── (N) Equipment
     │ (1:N 自关联)
     └─── children: Category
```

### 3.2 UserInfo（用户表）
**文件**：[users/models.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/users/models.py)

继承 Django `AbstractUser`，扩展自定义字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| username | CharField | 用户名（继承）|
| password | CharField | 密码哈希（继承）|
| email | CharField | 邮箱（继承）|
| phone | CharField(20) | 手机号，长度 11 位校验 |
| is_frozen | BooleanField | 账户是否冻结，默认 False |
| frozen_reason | CharField(255) | 冻结原因 |
| frozen_time | DateTimeField | 冻结时间 |
| is_staff | BooleanField | 是否管理员（继承，决定后台权限）|

### 3.3 Category（装备分类表）
**文件**：[equipment/models.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/equipment/models.py#L6-L30)

支持父子层级的自关联分类：

| 字段 | 类型 | 说明 |
|------|------|------|
| name | CharField(32) | 分类名称 |
| parent | FK→self, null=True | 父分类，`related_name='children'`，级联删除 |
| sort | PositiveIntegerField | 排序，数字越小越靠前，默认 99 |
| is_show | BooleanField | 是否前端显示，默认 True |
| created_time | DateTimeField | 创建时间（自动添加）|

### 3.4 Equipment（装备表）
**文件**：[equipment/models.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/equipment/models.py#L34-L68)

| 字段 | 类型 | 说明 |
|------|------|------|
| category | FK→Category, null=True | 所属分类，`related_name='equipments_category'` |
| name | CharField(10) | 装备名称 |
| price | Decimal(8,2) | 装备原价（买断计算用）|
| daily_rental | Decimal(8,2) | 日租金 |
| deposit | Decimal(8,2) | 押金（按件计）|
| stock | PositiveIntegerField | 实物库存数量 |
| cover_img | ImageField | 封面图，上传至 `equipment_img/` |
| desc | TextField | 装备简介 |
| is_shelf | BooleanField | 是否上架（租赁可用），默认 True |
| is_show | BooleanField | 是否前端显示，默认 True |
| is_sold_out | BooleanField | 是否已买断售罄（库存为 0 自动标记）|
| created_time | DateTimeField | 创建时间 |

**约束**：`unique_together = ('category', 'name')` 同一分类下装备名不重复。

### 3.5 Order（订单表）
**文件**：[orders/models.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/orders/models.py#L6-L75)

订单状态流转是本项目的业务核心：

```
        ┌──────────────────────────────────────┐
        │                                      ▼
  1 待支付 ──► 2 已支付 ──► 3 租赁中 ──► 4 待归还 ──► 5 已归还
       │          │          │
       │          │          └──► 7 已买断（逾期≥15天强制买断）
       │          │
       │          └──► 6 已取消（退款）
       │          └──► 7 已买断（主动买断，未发货）
       │
       └──► 6 已取消（未支付超时自动取消，默认72小时）
```

| 状态码 | 中文含义 | 说明 |
|--------|----------|------|
| 1 | 待支付 | 订单已创建，等待付款 |
| 2 | 已支付待发货 | 已付款，等待管理员发货出库 |
| 3 | 租赁中 | 装备已出库，用户持有中 |
| 4 | 待归还 | 用户申请归还，等待管理员确认 |
| 5 | 已归还 | 管理员已确认归还，押金已结算 |
| 6 | 已取消 | 订单取消（含退款成功）|
| 7 | 已买断 | 用户买断装备，不再归还 |

**核心字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| order_sn | CharField(64) | 订单号，格式：`ORD{YYYYMMDDHHMMSS}{user_id}{4位随机}` |
| order_status | IntegerField, choices | 订单状态 1~7 |
| user | FK→UserInfo | 下单用户，`related_name='orders_user'` |
| rental_days | IntegerField | 最长租赁天数（订单项最大天数）|
| rental_amount | Decimal(10,2) | 租金合计 |
| deposit_amount | Decimal(10,2) | 押金合计 |
| total_amount | Decimal(10,2) | 订单总价 = rental_amount + deposit_amount |
| deposit_status | IntegerField | 押金状态：0未付 / 1已冻结 / 2已退还 / 3扣除 |
| overdue_rate | Decimal(5,2) | 逾期费率，默认 150.0%（租金比例/天）|
| return_time | DateTimeField | 实际归还时间 |
| overdue_days | IntegerField | 逾期天数（向上取整天）|
| overdue_fee | Decimal(10,2) | 逾期费（封顶15天）|
| overdue_debt | Decimal(10,2) | 逾期欠费（押金不足以覆盖逾期费时的欠款）|
| actual_return_amount | Decimal(10,2) | 实际退还押金金额 |
| is_buyout | BooleanField | 是否买断 |
| buyout_amount | Decimal(10,2) | 买断金额 |
| start_time / end_time | DateTimeField | 租赁起止时间 |
| contact_name / contact_phone | CharField | 联系人信息 |
| create_time / pay_time | DateTimeField | 创建/支付时间 |

**退款相关字段**：refund_status(0未退/1退款中/2成功/3失败)、refund_amount、refund_reason_type、refund_reason_custom、refund_apply_time、refund_success_time、refund_fail_time、refund_fail_reason。

### 3.6 OrderItem（订单项表）
**文件**：[orders/models.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/orders/models.py#L78-L86)

| 字段 | 类型 | 说明 |
|------|------|------|
| order | FK→Order | 所属订单，`related_name='items'` |
| equipment | FK→Equipment | 租赁装备 |
| price | Decimal(8,2) | 下单时的日租金快照（避免后续改价影响历史订单）|
| rental_days | IntegerField | 单项租赁天数 |
| count | PositiveIntegerField | 租赁数量 |
| subtotal | Decimal(10,2) | 单项小计 = price × rental_days × count |

### 3.7 Cart & CartItem（购物车）
**文件**：[orders/models.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/orders/models.py#L88-L108)

- **Cart**：每个用户仅 1 个（`OneToOneField`），含 create_time / update_time
- **CartItem**：`unique_together = ('cart', 'equipment')` 同一装备购物车内不重复

| CartItem 字段 | 类型 | 说明 |
|------|------|------|
| cart | FK→Cart | 所属购物车 |
| equipment | FK→Equipment | 装备 |
| count | PositiveIntegerField | 数量，默认 1 |
| rental_days | IntegerField | 租赁天数，默认 1 |
| add_time | DateTimeField | 添加时间 |

---

## 4. 模块职责与关键类/函数

### 4.1 users 模块

#### 4.1.1 序列化器（[users/serializers.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/users/serializers.py)）

| 类名 | 用途 | 关键字段/逻辑 |
|------|------|---------------|
| `UserRegisterSerializer` | 用户注册 | username(3-12 字母数字)、password(≥6)、phone(11位数字)、email、re_password（校验两次一致）|
| `UserLoginSerializer` | 登录参数校验 | username、password |
| `UserPublicSerializer` | 用户自查询/改资料 | id、username、phone、email、is_staff（只读）|
| `AdminUserSerializer` | 管理员管理用户 | `__all__` 字段，含冻结相关 |
| `ChangePasswordSerializer` | 修改密码 | old_password 校验当前密码、new+confirm 一致，save() 加密保存 |

#### 4.1.2 视图（[users/views.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/users/views.py)）

| 类名 | 权限 | 关键方法/说明 |
|------|------|---------------|
| `UserRegisterView` | AllowAny | POST 注册，`@csrf_exempt` |
| `UserLoginView` | AllowAny | POST 登录：先校验图形验证码 → authenticate → 检查 is_frozen → 返回 JWT 双 token |
| `CaptchaView` | AllowAny | GET 生成图形验证码（PIL 动态绘制 4 位 + 干扰线 + 噪点，base64 返回）；`verify_captcha(key, code)` 内存校验，用完即删 |
| `UserViewSet` | IsAuthenticated | GET/PUT/PATCH `/profile/`，`get_object()` 直接返回 `request.user`，仅看自己 |
| `ChangePwdView` | IsAuthenticated | POST 修改密码（校验序列化器 + 二次 authenticate 旧密码）|
| `UserLogoutView` | IsAuthenticated | POST 登出：refresh token 加入黑名单；token 无效仍返回成功（保证体验）|
| `UserAdminViewSet` | IsAdminUser+IsAuthenticated | 管理员用户管理；`freeze(pk)` 冻结账户；`unfreeze(pk)` 解冻 |

### 4.2 equipment 模块

#### 4.2.1 序列化器（[equipment/serializers.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/equipment/serializers.py)）

| 类名 | 用途 | 说明 |
|------|------|------|
| `CategoryListSerializer` | 前端分类展示 | 递归 `get_children()` 渲染树形结构（仅 is_show=True）|
| `CategoryAdminSerializer` | 管理员分类CRUD | `__all__` 字段 |
| `EquipmentListSerializer` | 前端装备列表 | 含 category_name、cover_img_url 绝对路径 |
| `EquipmentDetailSerializer` | 前端装备详情 | 包含 is_shelf、is_show、created_time 等完整字段 |
| `EquipmentAdminSerializer` | 管理员装备CRUD | 支持 `cover_img_url_input` URL 字段 → `_download_image_from_url()` 自动下载图片；price/daily_rental/deposit 非负校验；上架时库存 >0 否则自动下架 |

#### 4.2.2 视图（[equipment/views.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/equipment/views.py)）

| ViewSet | 权限 | 说明 |
|---------|------|------|
| `CategoryViewSet` | list/retrieve=AllowAny, 其余=IsAdminUser | 前端仅显示 is_show=True 且 parent=None（顶级）的分类，按 sort 排序 |
| `CategoryAdminViewSet` | IsAdminUser | 管理员对分类的完整 CRUD |
| `EquipmentViewSet` | list/retrieve=AllowAny, 其余=IsAdminUser | 前端装备列表（仅 is_shelf=True+is_show=True），支持 `category_id` 过滤、`keyword` 模糊搜索 |
| `EquipmentDetailViewSet` | list/retrieve=AllowAny | 装备详情视图 |
| `EquipmentAdminViewSet` | IsAdminUser | 管理员装备完整 CRUD，支持 keyword 搜索 |

### 4.3 orders 模块（★ 核心业务）

#### 4.3.1 序列化器（[orders/serializers.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/orders/serializers.py)）

| 类名 | 用途 | 关键校验 |
|------|------|----------|
| `OrderSerializer` | 订单详情展示（只读）| 嵌套 items，含 status_display / user_name 等衍生字段 |
| `CreateOrderItemSerializer` | 下单明细 | equipment_id、count≥1、rental_days≥1 |
| `CreateOrderSerializer` | 创建订单 | 明细非空+不重复；start_time < end_time |
| `UpdateOrderStatusSerializer` | 管理员改状态 | 合法目标状态 ∈ {2,3,4,5,6,7}；按当前状态映射 `allowed` 集合做流转校验（与 service 分发逻辑一致）|
| `CreateRefundSerializer` | 退款申请 | 仅 order_status=2 可申请；refund_status 必须为 0（未申请过）；reason_type='other' 时 custom 必填 |
| `CartSerializer` + `CartItemSerializer` | 购物车展示 | 动态计算 total_count / total_rental / total_deposit |
| `AddCartItemSerializer` | 添加购物车 | equipment_id、count≥1、rental_days≥1 |
| `UpdateCartItemSerializer` | 修改购物车项 | count≥1、rental_days≥1 |

#### 4.3.2 OrderService（[orders/services.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/orders/services.py)）

**业务核心全部集中在此类（静态方法）**，View 层只做参数转发与异常捕获。

| 方法 | 功能 | 关键设计 |
|------|------|----------|
| `generate_order_sn(user_id)` | 生成订单号 | 格式 `ORD{YYYYMMDDHHMMSS}{user_id}{随机4位}` |
| `calculate_rental_days(s,e)` | 计算租赁天数 | 有秒数余数 +1 天，最少 1 天 |
| `_calculate_overdue(order, now)` | 计算逾期 | 逾期秒向上取整天；逾期费 = rental_amount × 150% × capped_days；**封顶15天**（超15天走强制买断）|
| `create_order(user, data)` | 创建订单（状态1）| ★ 事务 + `select_for_update()` 悲观锁防超卖；**时间段占用校验**（状态1/2/3/4 都算占用，仅5/6释放）；计算 rental/deposit/total；批量 bulk_create OrderItem |
| `pay_order(order, method)` | 支付（1→2）| 调 PaymentService.pay → 事务内二次校验 → 状态改为2、deposit_status=1、写 pay_time |
| `confirm_outbound(order)` | 确认出库扣库存（2→3）| 事务+行锁；遍历 items 逐个扣 `equipment.stock`（真正扣减实物库存是此时，而非创建订单时）|
| `deliver_order(order, is_admin)` | 管理员发货 | 等价于 confirm_outbound，权限包装 |
| `apply_return(order, user)` | 用户申请归还（3→4）| 仅本人；事务+行锁二次校验 |
| `confirm_return(order, user, is_admin)` | 管理员确认归还（4→5）| 计算逾期费；**押金结算**：deposit - overdue_fee，≥0则退还(deposit_status=2/3)，<0则欠费(overdue_debt)；归还实物：`equipment.stock += count` |
| `auto_confirm_return(order)` | 状态4逾期≥15天系统自动确认归还 | 与 confirm_return 逻辑相同，区别是系统兜底（管理员拖着不操作时）|
| `cancel_order(order, user, is_admin)` | 取消订单 | 状态1→6（无退款）；状态2→6：先**事务外**调 PaymentService.refund（避免长事务），成功后事务内改状态+记录退款信息；行锁+二次校验防并发 |
| `refund_order(order, ...)` | 退款流程 | refund_status=1→2(成功)或3(失败)；退款成功状态改为6；**仅原状态≥3（已出库）时恢复库存** |
| `buyout_order(order, user, is_admin)` | 主动买断（2→7）| 事务外先退租金；事务内：扣库存→标记 is_sold_out（库存=0时）；买断款 = 装备总价 - 押金（押金转货款补差价）|
| `force_buyout_overdue(order, is_admin)` | 逾期强制买断（3→7，需≥15天）| 买断款 = 装备总价 - 押金 + 逾期费；状态3已扣过库存故只标记售出；随附 `freeze_user()` 冻结用户 |
| `freeze_user(order, is_admin)` | 冻结关联用户 | 写 is_frozen + frozen_reason + frozen_time |
| `pay_overdue_debt(order, user)` | 支付逾期欠费 | 调 PaymentService → 成功则 overdue_debt=0 |
| `update_order_status(order, new, is_admin)` | 管理员通用改状态入口 | 按 (current,new) 分发到上述专用方法，避免重复写逻辑 |
| `auto_cancel_unpaid_orders(expire_hours=72)` | 自动取消超时未支付订单 | 过滤状态1且 create_time ≤ now-72h，批量调用 cancel_order（is_admin=True）|
| `check_overdue_orders()` | 检查并自动处理所有逾期订单 | 遍历状态3/4订单：先更新逾期字段；≥15天时：状态3→强制买断+冻结用户，状态4→自动确认归还 |

**并发安全要点**：
- 库存扣减/恢复均在事务内使用 `select_for_update()` 行级锁
- 所有状态变更入口均做「事务内二次校验」，防止并发请求导致状态跳变
- 第三方支付/退款调用置于事务外部，避免长事务锁库
- `auto_cancel_unpaid_orders` 使用 `.iterator(chunk_size=20)` 控制内存

#### 4.3.3 视图（[orders/views.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/orders/views.py)）

| ViewSet | 权限 | 关键 Action |
|---------|------|-------------|
| `OrderViewSet` | IsAuthenticated（用户订单）| `create` 下单；`pay(pk)` 支付；`cancel(pk)` 取消；`refund(pk)` 申请退款；`apply_return(pk)` 申请归还；`pay_overdue_debt(pk)` 付欠费；`list` 时先自动清理超时未支付订单 |
| `OrderAdminViewSet` | IsAdminUser（管理员订单）| `update-status(pk)` 通用状态更新；`deliver(pk)` 发货；`confirm_return(pk)` 确认归还；`buyout(pk)` 买断；`force_buyout(pk)` 强制买断；`cancel/refund/freeze_user`；`check_overdue()` 手动触发全量逾期检查；支持 keyword（订单号/用户名）+ status 过滤 |
| `CartViewSet` | IsAuthenticated | `list` 查询购物车（动态计算合计）；`add` 添加；`update_item` 修改数量/天数；`remove_item/{item_id}` 删除单项；`clear` 清空 |

### 4.4 common 模块

#### 4.4.1 PaymentService（[common/services/payment_service.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/common/services/payment_service.py)）

模拟第三方支付平台，MVP 阶段全部本地实现，后续接入真实支付只需替换本文件：

| 方法 | 返回 | 说明 |
|------|------|------|
| `pay(order_id, amount, method)` | `{success, trade_no, pay_time, ...}` | 支付一步成功；生成 `PAY{时间戳+随机}` 交易号 |
| `refund(order_id, amount)` | `{success, refund_no/error}` | 90% 成功率（模拟真实失败场景）|
| `settlement(order_id, return_time, ...)` | 结算信息 | 计算押金实际退还金额 |
| `pay_overdue_debt(order_id, amount)` | 支付成功 | 欠费缴纳，交易号前缀 `DEBT` |

#### 4.4.2 ImageUploadView（[common/views.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/common/views.py)）

| 项 | 说明 |
|----|------|
| 方法 | POST `/api/common/upload/image/` |
| 权限 | IsAdminUser |
| 校验 | 文件 ≤5MB，类型 ∈ {jpeg/png/gif/webp} |
| 存储 | UUID 重命名 → MEDIA_ROOT 根目录 |
| 返回 | 绝对 URL + 文件名 |

---

## 5. API 路由总览

所有接口统一挂载在 `/api/` 前缀下（见 [api/urls.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/api/urls.py)）。

### 5.1 认证接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/token/` | 获取 JWT（simplejwt 原生）| - |
| POST | `/api/token/refresh/` | 刷新 access_token | - |
| POST | `/api/users/register/` | 用户注册 | - |
| POST | `/api/users/login/` | 用户登录（含图形验证码）| - |
| GET  | `/api/users/captcha/` | 获取图形验证码 | - |
| POST | `/api/users/logout/` | 登出（refresh 黑名单）| ✅ |
| GET/PUT/PATCH | `/api/users/profile/` | 查看/修改个人资料 | ✅ |
| POST | `/api/users/change-password/` | 修改密码 | ✅ |
| GET  | `/api/users/admin/` | 管理员：用户列表 | 管理员 |
| POST | `/api/users/admin/{id}/freeze/` | 管理员：冻结用户 | 管理员 |
| POST | `/api/users/admin/{id}/unfreeze/` | 管理员：解冻用户 | 管理员 |

### 5.2 装备与分类接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET  | `/api/equipment/category/` | 分类树形列表（含 children）| - |
| GET  | `/api/equipment/equipment/` | 装备列表（支持 ?category_id=&keyword=）| - |
| GET  | `/api/equipment/equipment/{id}/` | 装备详情 | - |
| GET/POST/PUT/DELETE | `/api/equipment/category-admin/` | 管理员：分类 CRUD | 管理员 |
| GET/POST/PUT/DELETE | `/api/equipment/equipment-admin/` | 管理员：装备 CRUD（支持 ?keyword=）| 管理员 |

### 5.3 订单接口

#### 用户端

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/orders/` | 我的订单列表 / 创建订单 |
| GET  | `/api/orders/{id}/` | 订单详情 |
| POST | `/api/orders/{id}/pay/` | 支付订单 |
| POST | `/api/orders/{id}/cancel/` | 取消订单 |
| POST | `/api/orders/{id}/refund/` | 申请退款 |
| POST | `/api/orders/{id}/apply_return/` | 申请归还 |
| POST | `/api/orders/{id}/pay_overdue_debt/` | 支付逾期欠费 |

#### 管理员端

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/orders/admin/` | 全部订单（?keyword=&status=）|
| POST | `/api/orders/admin/{id}/update-status/` | 通用状态更新 |
| POST | `/api/orders/admin/{id}/deliver/` | 发货（2→3）|
| POST | `/api/orders/admin/{id}/confirm_return/` | 确认归还（4→5）|
| POST | `/api/orders/admin/{id}/cancel/` | 取消订单 |
| POST | `/api/orders/admin/{id}/refund/` | 处理退款 |
| POST | `/api/orders/admin/{id}/buyout/` | 买断 |
| POST | `/api/orders/admin/{id}/force_buyout/` | 强制买断 |
| POST | `/api/orders/admin/{id}/freeze_user/` | 冻结用户 |
| POST | `/api/orders/admin/check_overdue/` | 手动触发逾期检查 |

#### 购物车

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/orders/cart/` | 查看购物车 |
| POST | `/api/orders/cart/` | 添加商品 |
| PUT | `/api/orders/cart/` | 修改数量/天数（body: item_id, count, rental_days）|
| DELETE | `/api/orders/cart/remove/{item_id}/` | 删除单项 |
| POST | `/api/orders/cart/clear/` | 清空购物车 |

### 5.4 通用接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/common/upload/image/` | 管理员上传图片 | 管理员 |

> 所有需要认证的接口请求头需携带：`Authorization: Bearer <access_token>`
> POST/PUT/PATCH/DELETE 请求 URL **必须以 `/` 结尾**，否则 Django APPEND_SLASH 重定向会破坏请求。

---

## 6. 关键业务流程

### 6.1 用户租赁主流程

```
浏览装备 → 加入购物车 → 下单(状态1) → 支付(状态2) → 发货出库(状态3,扣库存)
→ 租赁使用 → 用户申请归还(状态4) → 管理员确认归还(状态5,加库存+押金结算)
```

### 6.2 订单状态合法流转表

| 当前状态 | 可转为 | 触发方 / 操作 |
|----------|--------|---------------|
| 1 待支付 | 2, 6 | 用户支付 / 用户取消 或 超时72h自动取消 |
| 2 已支付 | 3, 6, 7 | 管理员发货 / 取消(退款) / 用户或管理员主动买断 |
| 3 租赁中 | 4, 7 | 用户申请归还 / 逾期≥15天强制买断+冻结 |
| 4 待归还 | 5 | 管理员确认归还 或 逾期≥15天系统自动确认归还 |
| 5 已归还 | - | 终态 |
| 6 已取消 | - | 终态 |
| 7 已买断 | - | 终态 |

### 6.3 押金结算公式（确认归还时）

```
实际退还 = 押金总额 - 逾期费
if 实际退还 >= 0:
    actual_return_amount = 实际退还
    overdue_debt = 0
    deposit_status = 2 (已退还)  或 3 (扣除部分逾期费)
else:
    actual_return_amount = 0
    overdue_debt = |实际退还|   # 用户还欠平台的钱
    deposit_status = 3
```

### 6.4 买断金额公式

| 场景 | 公式 |
|------|------|
| 主动买断（状态2，未发货）| 买断款 = Σ(数量 × 装备原价) - 押金（押金转货款，补差价）；租金全额退 |
| 强制买断（状态3，逾期≥15天）| 买断款 = Σ(数量 × 装备原价) - 押金 + 逾期费（租金不退）|

---

## 7. 配置与运行

### 7.1 依赖（settings.py 中可推断）

```
Django==4.2.30
djangorestframework
djangorestframework-simplejwt
Pillow              # 验证码 PIL、图片处理
requests            # 装备图片 URL 下载
mysqlclient         # MySQL 驱动（或 PyMySQL）
```

> 项目未附带 `requirements.txt`，需按上列表安装。

### 7.2 数据库配置（[settings.py](file:///c:/Users/孙伟杰/PycharmProjects/Camping_gear_rental/Camping_gear_rental/settings.py#L82-L92)）

当前配置为 MySQL：
```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "camping_info",
        "USER": "root",
        "PASSWORD": "swj123",
        "HOST": "127.0.0.1",
        "PORT": 3306,
        "CHARSET": "utf-8"
    }
}
```
若本地只想快速启动，可改为 SQLite：使用仓库根目录已有 `db.sqlite3`。

### 7.3 JWT 配置

```python
ACCESS_TOKEN_LIFETIME = 1 天
REFRESH_TOKEN_LIFETIME = 7 天
BLACKLIST_AFTER_ROTATION = True   # 启用 refresh 黑名单
```
已注册 `rest_framework_simplejwt.token_blacklist`，需执行 migrate 建表。

### 7.4 媒体文件

```python
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
```
开发环境下 settings.DEBUG=True 时，根 urls.py 自动挂载静态文件服务；生产环境需 Nginx/CDN。

### 7.5 本地启动步骤

```bash
# 1. 进入项目目录
cd Camping_gear_rental

# 2. 安装依赖（示例，按需调整）
pip install django==4.2.30 djangorestframework djangorestframework-simplejwt pillow requests mysqlclient

# 3. 准备数据库
# 方案A MySQL：提前创建数据库 camping_info，配置正确账号密码
# 方案B SQLite（快速）：修改 settings.py DATABASES 为 django.db.backends.sqlite3, NAME=BASE_DIR/'db.sqlite3'

# 4. 执行数据迁移
python manage.py migrate

# 5. 创建管理员
python manage.py createsuperuser

# 6. 启动开发服务器
python manage.py runserver 0.0.0.0:8000
```

启动后：
- Django Admin：`http://127.0.0.1:8000/admin/`
- API 根路径：`http://127.0.0.1:8000/api/`

### 7.6 定时任务建议

`OrderService` 提供了两个需要周期性触发的方法，建议使用 Django APScheduler / Celery Beat 或系统 crontab 定时执行：

| 方法 | 建议频率 | 作用 |
|------|----------|------|
| `OrderService.auto_cancel_unpaid_orders()` | 每 10 分钟 | 清理超时(72h)未支付订单 |
| `OrderService.check_overdue_orders()` | 每小时 | 更新所有逾期订单字段；≥15天自动强制买断或自动归还 |

也可临时调用管理员接口：`POST /api/orders/admin/check_overdue/` 手动触发。

---

## 8. 工程约定与注意事项

1. **自定义用户模型**：`AUTH_USER_MODEL = 'users.UserInfo'`，所有外键关联用户必须使用 `users.UserInfo`，不要使用内置 User。
2. **Service 层优先**：所有订单业务逻辑必须在 `OrderService` 中实现，View 层只做参数转发 + 异常转 Response。禁止在 View/Serializer 中直接写状态变更或库存变更。
3. **事务与锁**：库存修改、状态变更必须包裹 `transaction.atomic()` + `select_for_update()` 行锁 + 二次状态校验。
4. **支付外置**：第三方支付/退款调用放在事务外部，成功后再进入事务更新本地状态。
5. **DRF 注册顺序**：DefaultRouter 中「带特定前缀（如 `admin/`）」ViewSet 必须注册在「空前缀」ViewSet 之前，否则路由冲突。
6. **URL 尾斜杠**：所有写操作请求 URL 必须以 `/` 结尾。
7. **时间段占用检查**：创建订单时库存判断不仅看 `equipment.stock`，还需聚合状态 1/2/3/4 中相同时段的占用数量。
8. **幂等性**：状态变更方法均在事务内二次校验，避免重复请求导致数据错乱。
9. **验证码存储**：图形验证码使用内存 dict `captcha_storage`（进程内），多进程部署时需迁移至 Redis。
10. **买断售罄**：装备只有在 stock 被扣减为 0 时才标记 `is_sold_out=True`，防止误售清库。

---

## 9. 前端开发指南

> 本项目前端为独立 Vue 3 仓库，未包含在当前后端代码库中。本章基于后端 API 契约和项目工程约定，为前端开发提供规范化的对接指南。

### 9.1 技术栈与项目初始化

| 技术 | 说明 |
|------|------|
| Vue 3 | 组合式 API（`<script setup>`）|
| TypeScript | 全量类型，接口必须与后端响应严格对齐 |
| Vue Router 4 | 路由 + 全局守卫（鉴权）|
| Pinia | 状态管理（用户、购物车等）|
| Axios | 封装为 `utils/request.ts`，统一处理 token 与错误 |

```bash
# 初始化项目（参考）
npm create vite@latest camping-frontend -- --template vue-ts
cd camping-frontend
npm install vue-router@4 pinia axios
```

### 9.2 目录结构规范

```
camping-frontend/
├── src/
│   ├── api/              # ★ 请求函数层：每个模块一个文件
│   │   ├── user.ts
│   │   ├── equipment.ts
│   │   ├── order.ts
│   │   └── cart.ts
│   ├── types/            # ★ TypeScript 接口定义：与后端序列化器一一对应
│   │   ├── user.ts
│   │   ├── equipment.ts
│   │   ├── order.ts
│   │   └── cart.ts
│   ├── store/            # Pinia 状态管理
│   │   ├── user.ts
│   │   └── cart.ts
│   ├── views/            # 页面组件
│   │   ├── LoginView.vue
│   │   ├── RegisterView.vue
│   │   ├── EquipmentListView.vue
│   │   ├── CartView.vue
│   │   ├── OrderListView.vue
│   │   └── admin/
│   ├── router/           # 路由配置
│   │   └── index.ts
│   ├── utils/            # 通用工具
│   │   └── request.ts    # ★ Axios 封装实例
│   ├── components/       # 公共组件
│   ├── App.vue
│   └── main.ts
├── vite.config.ts
└── package.json
```

### 9.3 请求层封装（utils/request.ts）

**硬性要求**：前端必须使用本项目封装的 `request` 工具，禁止直接使用 `fetch` 或裸 `axios`，以确保 JWT 自动注入与 401 自动跳转登录。

```typescript
// src/utils/request.ts
import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import router from '@/router'

const request: AxiosInstance = axios.create({
  baseURL: 'http://127.0.0.1:8000/api/',
  timeout: 10000,
})

// 请求拦截器：自动注入 JWT
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器：统一错误处理
request.interceptors.response.use(
  (response) => response.data,  // 直接返回 data，剥离 Axios 外层
  (error) => {
    if (error.response?.status === 401) {
      // token 失效，清除并跳转登录
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      router.push({ name: 'login' })
    }
    return Promise.reject(error.response?.data || error)
  }
)

export default request
```

> **注意**：由于响应拦截器剥离了 `response.data`，TypeScript 无法自动推断返回类型，因此 API 函数必须**显式声明返回类型**（见 9.5）。

### 9.4 TypeScript 类型定义规范（types/）

**核心原则**：`types/` 中的接口必须与后端序列化器字段**完全匹配**，不可多写或漏写。

#### 9.4.1 用户相关类型

```typescript
// src/types/user.ts

// 对应后端 UserPublicSerializer
export interface UserInfo {
  id: number
  username: string
  phone: string
  email: string
  is_staff: boolean
}

// 登录响应
export interface LoginResult {
  message: string
  access: string
  refresh: string
}

// 验证码响应
export interface CaptchaResult {
  key: string
  image: string  // data:image/png;base64,...
}

// 注册 / 修改密码请求体
export interface RegisterData {
  username: string
  password: string
  phone: string
  email: string
  re_password: string
}

export interface ChangePasswordData {
  old_password: string
  new_password: string
  confirm_password: string
}
```

#### 9.4.2 装备相关类型

```typescript
// src/types/equipment.ts

// 对应后端 EquipmentListSerializer（列表页）
export interface EquipmentListItem {
  id: number
  name: string
  price: string          // Decimal → 后端返回字符串
  daily_rental: string
  deposit: string
  stock: number
  is_sold_out: boolean
  category: number | null
  category_name: string
  cover_img_url: string
  desc: string | null
}

// 对应后端 EquipmentDetailSerializer（详情页）
export interface EquipmentDetail extends EquipmentListItem {
  is_shelf: boolean
  is_show: boolean
  created_time: string
}

// 对应后端 CategoryListSerializer（树形递归）
export interface CategoryNode {
  id: number
  name: string
  sort: number
  children: CategoryNode[]
}
```

> **Decimal 字段**：后端 `DecimalField` 序列化后为字符串（如 `"150.00"`），前端类型应声明为 `string`，在计算时再 `parseFloat`，避免浮点精度问题。

#### 9.4.3 订单相关类型

```typescript
// src/types/order.ts

// 对应后端 OrderItemSerializer
export interface OrderItem {
  id: number
  equipment_id: number
  equipment_name: string
  price: string
  rental_days: number
  count: number
  subtotal: string
}

// 对应后端 OrderSerializer
export interface Order {
  id: number
  order_sn: string
  user_name: string
  order_status: number        // 1~7
  order_status_display: string  // "待支付" / "已支付" ...
  rental_days: number
  rental_amount: string
  deposit_amount: string
  total_amount: string
  deposit_status: number     // 0~3
  deposit_status_display: string
  overdue_rate: string
  return_time: string | null
  overdue_days: number
  overdue_fee: string
  overdue_debt: string
  actual_return_amount: string
  is_buyout: boolean
  buyout_amount: string
  start_time: string
  end_time: string
  contact_name: string
  contact_phone: string
  create_time: string
  pay_time: string | null
  items: OrderItem[]
  refund_status: number
  refund_status_display: string
  refund_amount: string
  refund_reason_type: string | null
  refund_reason_custom: string | null
  refund_apply_time: string | null
  refund_success_time: string | null
  refund_fail_time: string | null
  refund_fail_reason: string | null
}

// 创建订单请求体
export interface CreateOrderData {
  create_order_items: {
    equipment_id: number
    count: number
    rental_days: number
  }[]
  start_time: string
  end_time: string
  contact_name: string
  contact_phone: string
}

// 退款原因类型枚举
export type RefundReasonType =
  | 'change_mind' | 'schedule_conflict' | 'equipment_issue'
  | 'price_concern' | 'other'
```

#### 9.4.4 购物车相关类型

```typescript
// src/types/cart.ts

// 对应后端 CartItemSerializer
export interface CartItem {
  id: number
  equipment_id: number
  equipment_name: string
  equipment_price: string
  daily_rental: string
  deposit: string
  count: number
  rental_days: number
  cover_img_url: string
  category_name: string
  stock: number
}

// 对应后端 CartSerializer（含视图层动态追加的合计字段）
export interface Cart {
  id: number
  items: CartItem[]
  total_count: number
  total_rental: string
  total_deposit: string
}
```

### 9.5 API 函数层规范（api/）

**核心原则**：每个函数必须**显式声明返回类型**，解决响应拦截器剥离 data 后的 TS 类型推断问题。URL 参数交给 `params` 字段，不要手动拼 `?`。

```typescript
// src/api/user.ts
import request from '@/utils/request'
import type { UserInfo, LoginResult, CaptchaResult, RegisterData, ChangePasswordData } from '@/types/user'

// 登录（无需 token）
export function login(data: { username: string; password: string; captcha_key: string; captcha_code: string }): Promise<LoginResult> {
  return request.post('/users/login/', data)
}

// 获取验证码
export function getCaptcha(): Promise<CaptchaResult> {
  return request.get('/users/captcha/')
}

// 注册
export function register(data: RegisterData): Promise<{ message: string }> {
  return request.post('/users/register/', data)
}

// 获取个人信息
export function getProfile(): Promise<UserInfo> {
  return request.get('/users/profile/')
}

// 修改密码
export function changePassword(data: ChangePasswordData): Promise<{ message: string }> {
  return request.post('/users/change-password/', data)
}

// 登出
export function logout(refresh: string): Promise<{ message: string }> {
  return request.post('/users/logout/', { refresh })
}
```

```typescript
// src/api/order.ts
import request from '@/utils/request'
import type { Order, CreateOrderData } from '@/types/order'

// 我的订单列表
export function getOrders(): Promise<Order[]> {
  return request.get('/orders/')
}

// 创建订单
export function createOrder(data: CreateOrderData): Promise<{ message: string; order_id: number; order_sn: string }> {
  return request.post('/orders/', data)
}

// 支付订单
export function payOrder(orderId: number, payment_method = 'alipay'): Promise<{
  message: string; trade_no: string; pay_time: string; method: string
  amount: string; order_status: number; order_status_display: string
}> {
  return request.post(`/orders/${orderId}/pay/`, { payment_method })
}

// 申请归还
export function applyReturn(orderId: number): Promise<{
  message: string; order_status: number; order_status_display: string
}> {
  return request.post(`/orders/${orderId}/apply_return/`)
}
```

### 9.6 路由配置与鉴权守卫

```typescript
// src/router/index.ts
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',              // ★ 使用 name，router.push 时也用 name
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/equipment',
    name: 'equipment-list',
    component: () => import('@/views/EquipmentListView.vue'),
    meta: { requiresAuth: false }  // 装备浏览无需登录
  },
  {
    path: '/cart',
    name: 'cart',
    component: () => import('@/views/CartView.vue'),
    meta: { requiresAuth: true }   // ★ 需登录
  },
  {
    path: '/orders',
    name: 'order-list',
    component: () => import('@/views/OrderListView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/admin',
    name: 'admin',
    component: () => import('@/views/admin/AdminView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 全局前置守卫
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.meta.requiresAuth && !token) {
    next({ name: 'login' })  // ★ 用 name 而非 path 字符串
  } else if (to.meta.requiresAdmin) {
    // 额外检查 is_staff
    next()
  } else {
    next()
  }
})

export default router
```

**路由约定**：
- 所有需要登录的路由必须设置 `meta.requiresAuth: true`
- 页面跳转使用 `router.push({ name: '路由名' })` 而非 `router.push('/path')`，提升可维护性与重构安全性
- 管理员页面额外设置 `meta.requiresAdmin: true`

### 9.7 状态管理（Pinia）

```typescript
// src/store/user.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getProfile, login as loginApi, logout as logoutApi } from '@/api/user'
import type { UserInfo } from '@/types/user'

export const useUserStore = defineStore('user', () => {
  const userInfo = ref<UserInfo | null>(null)
  const isLoggedIn = ref(false)

  async function login(data: { username: string; password: string; captcha_key: string; captcha_code: string }) {
    const res = await loginApi(data)
    localStorage.setItem('access_token', res.access)
    localStorage.setItem('refresh_token', res.refresh)
    isLoggedIn.value = true
    await fetchProfile()
  }

  async function fetchProfile() {
    userInfo.value = await getProfile()
  }

  async function logout() {
    const refresh = localStorage.getItem('refresh_token')
    if (refresh) await logoutApi(refresh)
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    userInfo.value = null
    isLoggedIn.value = false
  }

  return { userInfo, isLoggedIn, login, fetchProfile, logout }
})
```

### 9.8 UI / UX 交互规范

| 场景 | 规范 | 说明 |
|------|------|------|
| 登录页风格 | 紫色渐变背景 + 动态粒子效果 | 不使用静态/基础动画 |
| 登录/注册卡片 | 卡片尺寸适配内容区域，非全屏 | 约红框尺寸 |
| 表单错误提示 | 输入框下方橙色字体实时显示 | 持续显示直至修正，**不使用 alert** |
| 保存失败提示 | 表单内部提示，5 秒自动消失 | **不使用弹窗** |
| 成功反馈（注册） | 居中绿色对勾提示 | 延时 0.5s 后跳转，**不使用 alert** |
| 确认操作 | 页内 Modal 对话框 | **不使用浏览器原生 confirm** |
| 用户信息/改密表单 | 默认隐藏，点击「修改」按钮后展开 | 避免页面信息过载 |

### 9.9 前后端对接注意事项

1. **URL 尾斜杠**：所有 POST/PUT/PATCH/DELETE 请求路径必须以 `/` 结尾（如 `/orders/`），否则 Django APPEND_SLASH 会 301 重定向导致方法变 GET。
2. **参数序列化**：查询参数交给 axios 的 `params` 字段处理，不要手动拼接 `?`，否则会产生重复问号。
3. **Token 前缀**：请求头格式为 `Authorization: Bearer <access_token>`，注意 `Bearer` 后有空格。
4. **Decimal 类型**：后端金额字段（price、rental_amount 等）序列化为字符串，前端在展示时直接渲染，在计算时用 `parseFloat()` 转换，避免 JS 浮点精度问题。
5. **时间格式**：后端 DateTimeField 返回 ISO 8601 字符串（如 `"2026-08-29T10:30:00+08:00"`），前端可用 `new Date(str)` 直接解析。
6. **状态码约定**：后端错误返回 400（业务校验失败）/ 401（未认证）/ 403（无权限）/ 404（不存在）。前端统一在响应拦截器中处理 401，其余在调用处 try-catch。
7. **验证码一次性**：图形验证码同一个 `key` 只能验证一次，失败后需重新获取。
8. **CORS 跨域**：开发环境前后端分离运行时，后端需配置 `django-cors-headers` 或在 Vite 的 `vite.config.ts` 中配置代理：

```typescript
// vite.config.ts 代理方案（替代后端 CORS）
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
})
```

---

## 10. 常见问题排查

| 现象 | 可能原因 | 解决 |
|------|----------|------|
| 创建订单报"时间段仅余 N 件" | 其他订单的同时间段占用了库存 | 让用户换时段或减少数量 |
| 管理员改状态返回"当前状态不允许该操作" | `UpdateOrderStatusSerializer.validate` 限制了合法流转 | 对照 §6.2 状态表确认 |
| 登录返回验证码错误 | 同一 captcha_key 只能用一次；或内存重启后清空 | 重新 GET 获取验证码 |
| 图片上传返回 403 | 仅管理员可调用 `/api/common/upload/image/` | 使用管理员 token |
| 装备上架失败 | stock ≤ 0 时强制下架 | 先增加库存再上架 |
| `APPEND_SLASH` 301 重定向后 POST 变 GET | URL 未尾带 / | 所有 API 路径末尾加 `/` |

---

*文档版本：v1.1 · 生成日期：2026-08-29 · 新增第 9 章前端开发指南 · 对应仓库状态：当前本地 commit*
