# -*- coding: utf-8 -*-
"""
登录与权限装饰器
"""
from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(f):
    """要求登录"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            flash('请先登录', 'warning')
            return redirect(url_for('auth.login', next=url_for('user.index')))
        return f(*args, **kwargs)
    return wrapper


def merchant_required(f):
    """要求商家登录"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            flash('请先登录', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 1:
            flash('无权限，该操作需要商家账号', 'danger')
            return redirect(url_for('user.index'))
        return f(*args, **kwargs)
    return wrapper
