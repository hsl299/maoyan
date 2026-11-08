# -*- coding: utf-8 -*-
"""
数据库连接工具（PyMySQL）
提供线程安全的基础连接管理与常用查询封装
"""
import pymysql
from pymysql.cursors import DictCursor
from flask import g

import config


def get_conn():
    """获取当前请求上下文中的数据库连接（每个请求一个连接，请求结束自动关闭）"""
    if 'db_conn' not in g:
        g.db_conn = pymysql.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            charset='utf8mb4',
            cursorclass=DictCursor,
            autocommit=False,     # 手动提交，便于事务控制
        )
    return g.db_conn


def close_conn(e=None):
    """请求结束时关闭数据库连接"""
    conn = g.pop('db_conn', None)
    if conn is not None:
        conn.close()


def query(sql, params=None):
    """查询多条记录，返回 list[dict]"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def query_one(sql, params=None):
    """查询单条记录，返回 dict 或 None"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def execute(sql, params=None):
    """执行增删改，返回受影响行数（需提交）"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.rowcount


def last_insert_id():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute('SELECT LAST_INSERT_ID() AS id')
        row = cur.fetchone()
        return row['id'] if row else None


def commit():
    get_conn().commit()


def rollback():
    get_conn().rollback()
