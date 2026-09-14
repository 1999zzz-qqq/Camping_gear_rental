Markdown

# 露营装备租赁平台

一个面向个人用户的露营装备在线租赁平台，支持装备浏览、下单租赁、支付、发货、归还、买断、退款全流程。

## 技术栈

| 层级 | 技术 |
|------|------|
| Web框架 | Django 4.2 |
| API框架 | Django REST Framework |
| 认证 | SimpleJWT（access 1天 / refresh 7天 + 黑名单） |
| 数据库 | MySQL |
| 支付 | 内置 PaymentService 模拟 |
| 前端 | Vue 3 + TypeScript（独立仓库） |

## 功能模块

- **用户模块**：注册、登录、JWT认证、修改密码、个人信息管理、管理员冻结账户
- **装备模块**：分类管理、装备CRUD、日租金/押金自动计算、图片上传
- **订单模块**：订单创建、支付、取消、发货、归还、买断、退款、逾期处理
- **评论模块**：租后评论、XSS过滤、分页

## 核心特性

- 订单状态机：7个状态流转，Service层统一管理
- 并发控制：`select_for_update()` 行锁 + 事务内二次校验，防止库存超卖
- 事务优化：第三方支付调用移至事务外，缩短行锁持有时间
- 幂等设计：状态前置校验防止重复扣款/退款
- 权限隔离：自定义权限类实现用户/管理员数据隔离
- 查询优化：`select_related`/`prefetch_related` 解决N+1

## 快速开始

### 环境要求
- Python 3.9+
- MySQL 5.7+

### 安装依赖
```bash
pip install -r requirements.txt


Plain Text


### 配置数据库
在项目根目录创建 `.env` 文件：
MYSQL_PASSWORD=你的数据库密码


Plain Text


### 数据库迁移
```bash
python manage.py makemigrations python manage.py migrate


Plain Text


### 启动服务
```bash
python manage.py runserver


Plain Text


### 访问地址
- 后端接口：http://127.0.0.1:8000
- Django后台：http://127.0.0.1:8000/admin

## 项目结构
Camping_gear_rental/ ├── Camping_gear_rental/ # 项目配置 ├── users/ # 用户模块 ├── equipment/ # 装备与分类模块 ├── orders/ # 订单与购物车模块（核心） ├── comments/ # 评论模块 ├── common/ # 通用模块（支付模拟、图片上传） ├── api/ # 路由聚合 ├── manage.py ├── requirements.txt └── .env # 环境变量（需自行创建）


Plain Text


## 订单状态流转
待支付 → 已支付 → 租赁中 → 待归还 → 已归还 ↓ ↓ ↓ 取消 取消/买断 强制买断（逾期15天）


Plain Text

undefined