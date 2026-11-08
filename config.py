# -*- coding: utf-8 -*-
"""
项目配置文件
"""

# ==================== MySQL 数据库配置 ====================
# 请根据你的本机 MySQL 实际配置修改
DB_HOST = '127.0.0.1'
DB_PORT = 3306
DB_USER = 'root'
DB_PASSWORD = '2005'          # 本机 MySQL root 密码
DB_NAME = 'maoyan_ticket'

# ==================== Flask 配置 ====================
# session 加密密钥（生产环境请换成随机字符串）
SECRET_KEY = 'maoyan-ticket-2026-secret-key'

# 订单待支付超时时间（秒），超时自动取消并释放座位
ORDER_TIMEOUT = 15 * 60

# ==================== 票品封面上传配置 ====================
UPLOAD_FOLDER = 'static/uploads'          # 相对项目根目录的封面上传目录
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
