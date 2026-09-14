
# 露营装备租赁平台 (后端)

基于 Django + Django REST Framework + MySQL + JWT 的个人露营装备租赁平台。

## 🔗 配套项目
* 前端代码仓库：https://github.com/1999zzz-qqq/camping-gear-rental-vue

## 🛠️ 技术栈
* Python / Django / Django REST Framework
* MySQL
* Redis

## 🚀 本地运行指南

1. 安装依赖
```bash
pip install -r requirements.txt
配置数据库
在项目根目录创建 .env 文件：

text
MYSQL_PASSWORD=你的数据库密码
数据库迁移

bash
python manage.py makemigrations
python manage.py migrate
启动服务

bash
python manage.py runserver
🌐 访问地址
后端接口：http://127.0.0.1:8000

Django后台：http://127.0.0.1:8000/admin

📂 项目结构
text
Camping_gear_rental/
├── Camping_gear_rental/  # 项目配置
├── users/                # 用户模块
├── equipment/            # 装备与分类
├── orders/               # 订单模块
├── comments/             # 评论模块
├── common/               # 公共模块
├── manage.py
└── requirements.txt
text

*(注意：上面代码块里的 ````text` 千万不要被翻译插件翻译，复制到 PyCharm 后，确保它们是半角英文反引号)*

### 🚀 重新推送

保存文件后，在**后端**终端（`PycharmProjects\Camping_gear_rental`）执行：

```bash
git add README.md
git commit -m "修复后端README格式"
git push -u origin main -f