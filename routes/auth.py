# -*- coding: utf-8 -*-
"""
认证模块：登录 / 注册 / 登出
"""
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash)
from werkzeug.security import generate_password_hash, check_password_hash

import db

auth_bp = Blueprint('auth', __name__)
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = db.query_one(
            'SELECT * FROM users WHERE username = %s', (username,))
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['nickname'] = user['nickname']
            flash('登录成功', 'success')
            nxt = request.args.get('next') or url_for('user.index')
            # 商家登录后直接进后台
            if user['role'] == 1:
                nxt = url_for('merchant.dashboard')
            return redirect(nxt)
        flash('用户名或密码错误', 'danger')
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')
        nickname = request.form.get('nickname', '').strip() or username
        phone = request.form.get('phone', '').strip()
        role = 1 if request.form.get('role') == '1' else 0

        if not username or not password:
            flash('用户名和密码不能为空', 'danger')
        elif password != confirm:
            flash('两次输入的密码不一致', 'danger')
        elif len(password) < 6:
            flash('密码长度至少 6 位', 'danger')
        elif db.query_one('SELECT id FROM users WHERE username=%s', (username,)):
            flash('用户名已被占用', 'danger')
        else:
            hashed = generate_password_hash(password)
            db.execute(
                'INSERT INTO users (username, password, nickname, phone, role) '
                'VALUES (%s,%s,%s,%s,%s)',
                (username, hashed, nickname, phone, role))
            db.commit()
            flash('注册成功，请登录', 'success')
            return redirect(url_for('auth.login'))
    return render_template('register.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('auth.login'))
