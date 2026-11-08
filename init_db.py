# -*- coding: utf-8 -*-
"""
一键初始化脚本：
1. 创建数据库 maoyan_ticket 并执行 db.sql 建表 + 示例票品/场次/座位
2. 使用 werkzeug 正确生成密码哈希，创建两个测试账号（密码均为 123456）
   - shop01 商家账号
   - user01 普通用户账号

用法：在项目目录下运行  python init_db.py
"""
import pymysql
from werkzeug.security import generate_password_hash

import config

# 测试账号（明文密码 123456，这里用 werkzeug 正确生成哈希）
TEST_USERS = [
    dict(username='shop01', nickname='猫眼官方影城', phone='13800000001', role=1),
    dict(username='user01', nickname='影迷小王', phone='13800000002', role=0),
]
TEST_PASSWORD = '123456'


def main():
    print('=' * 60)
    print('开始初始化数据库...')
    print(f'目标库: {config.DB_NAME} @ {config.DB_HOST}:{config.DB_PORT}')
    print('=' * 60)

    # 先连接 MySQL（不指定库）创建数据库
    conn = pymysql.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        user=config.DB_USER, password=config.DB_PASSWORD,
        charset='utf8mb4',
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` '
                f'DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'
            )
        conn.commit()
        print('[1/3] 数据库创建完成')
    finally:
        conn.close()

    # 执行 db.sql 建表 + 示例票品/场次/座位
    with open('db.sql', 'r', encoding='utf-8') as f:
        sql = f.read()

    conn = pymysql.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        user=config.DB_USER, password=config.DB_PASSWORD,
        database=config.DB_NAME,
        charset='utf8mb4',
        client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print('[2/3] 建表及示例票品/场次/座位数据完成')
    except Exception as e:
        conn.rollback()
        print('[错误] 执行 db.sql 失败:', e)
        raise
    finally:
        conn.close()

    # 插入测试账号（正确密码哈希）
    conn = pymysql.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        user=config.DB_USER, password=config.DB_PASSWORD,
        database=config.DB_NAME,
        charset='utf8mb4',
    )
    try:
        hashed = generate_password_hash(TEST_PASSWORD)
        with conn.cursor() as cur:
            for u in TEST_USERS:
                cur.execute(
                    'INSERT IGNORE INTO users (username, password, nickname, phone, role) '
                    'VALUES (%s, %s, %s, %s, %s)',
                    (u['username'], hashed, u['nickname'], u['phone'], u['role'])
                )
        conn.commit()
        print('[3/3] 测试账号创建完成（密码均为 %s）' % TEST_PASSWORD)
    finally:
        conn.close()

    print('=' * 60)
    print('初始化成功！测试账号：')
    print('  商家账号  shop01 / 123456')
    print('  用户账号  user01 / 123456')
    print('接下来请运行:  python app.py')
    print('=' * 60)


if __name__ == '__main__':
    main()
