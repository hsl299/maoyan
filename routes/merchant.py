# -*- coding: utf-8 -*-
"""
商家端模块：票品/场次/座位管理、销售订单、退票审核、电子票核销
"""
import os
import uuid
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, jsonify, current_app)

import config
import db
from utils.decorators import merchant_required

merchant_bp = Blueprint('merchant', __name__, url_prefix='/merchant')

# 订单状态文本映射（0待支付 1已支付 2已完成 3已退票 4已取消 5退票审核中 6已核销）
STATUS_MAP = {0: '待支付', 1: '已支付', 2: '已完成', 3: '已退票',
              4: '已取消', 5: '退票审核中', 6: '已核销'}


def save_cover(file):
    """保存上传的封面图片，返回相对路径 'uploads/xxx.jpg'。
    无文件返回 ''；文件类型不支持返回 None。"""
    if not file or not file.filename:
        return ''
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in config.ALLOWED_EXTENSIONS:
        return None
    filename = uuid.uuid4().hex + '.' + ext
    upload_dir = os.path.join(current_app.root_path, config.UPLOAD_FOLDER)
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, filename))
    return 'uploads/' + filename


# ----------------------------------------------------------------------
# 后台首页（统计概览）
# ----------------------------------------------------------------------
@merchant_bp.route('/')
@merchant_required
def dashboard():
    mid = session['user_id']
    stats = {
        'ticket_count': db.query_one('SELECT COUNT(*) c FROM tickets WHERE merchant_id=%s', (mid,))['c'],
        'on_count': db.query_one('SELECT COUNT(*) c FROM tickets WHERE merchant_id=%s AND status=1', (mid,))['c'],
        'order_count': db.query_one(
            'SELECT COUNT(*) c FROM orders o JOIN sessions s ON o.session_id=s.id '
            'JOIN tickets t ON s.ticket_id=t.id WHERE t.merchant_id=%s AND o.status IN (1,2,6)', (mid,))['c'],
        'sales': db.query_one(
            'SELECT COALESCE(SUM(o.total_price),0) c FROM orders o JOIN sessions s ON o.session_id=s.id '
            'JOIN tickets t ON s.ticket_id=t.id WHERE t.merchant_id=%s AND o.status IN (1,2,6)', (mid,))['c'],
        'refund_count': db.query_one(
            'SELECT COUNT(*) c FROM refunds r JOIN orders o ON r.order_id=o.id '
            'JOIN sessions s ON o.session_id=s.id JOIN tickets t ON s.ticket_id=t.id '
            'WHERE t.merchant_id=%s AND r.status=0', (mid,))['c'],
    }
    recent = db.query(
        'SELECT o.*, t.title, s.show_time, u.nickname FROM orders o '
        'JOIN sessions s ON o.session_id=s.id JOIN tickets t ON s.ticket_id=t.id '
        'JOIN users u ON o.user_id=u.id WHERE t.merchant_id=%s '
        'ORDER BY o.created_at DESC LIMIT 8', (mid,))
    return render_template('merchant/dashboard.html', stats=stats, recent=recent)


# ----------------------------------------------------------------------
# 票品列表
# ----------------------------------------------------------------------
@merchant_bp.route('/tickets')
@merchant_required
def ticket_list():
    mid = session['user_id']
    kw = request.args.get('kw', '').strip()
    sql = ('SELECT t.*, (SELECT COUNT(*) FROM sessions s WHERE s.ticket_id=t.id) AS session_count, '
           '(SELECT COUNT(*) FROM orders o JOIN sessions s2 ON o.session_id=s2.id '
           'WHERE s2.ticket_id=t.id AND o.status IN (1,2,6)) AS sold_count '
           'FROM tickets t WHERE t.merchant_id=%s')
    params = [mid]
    if kw:
        sql += ' AND t.title LIKE %s'
        params.append(f'%{kw}%')
    # 新增的票品显示在最下面（最旧在最上，最新在最后）
    sql += ' ORDER BY t.created_at ASC, t.id ASC'
    return render_template('merchant/ticket_list.html', tickets=db.query(sql, params), kw=kw)


# ----------------------------------------------------------------------
# 新增票品
# ----------------------------------------------------------------------
@merchant_bp.route('/tickets/new', methods=['GET', 'POST'])
@merchant_required
def ticket_new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('票品名称不能为空', 'danger')
            return render_template('merchant/ticket_edit.html', ticket=None)
        # 封面上传（优先），否则回退到 URL 输入框
        cover_rel = save_cover(request.files.get('cover_file'))
        if cover_rel is None:
            flash('封面格式不支持（仅支持 png/jpg/jpeg/gif/webp）', 'danger')
            return render_template('merchant/ticket_edit.html', ticket=None)
        cover = cover_rel or request.form.get('cover', '').strip()
        db.execute(
            'INSERT INTO tickets (merchant_id, title, type, cover, intro, actors, duration, address) '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
            (session['user_id'], title,
             request.form.get('type', type=int) or 0,
             cover,
             request.form.get('intro', '').strip(),
             request.form.get('actors', '').strip(),
             request.form.get('duration', type=int) or 0,
             request.form.get('address', '').strip()))
        db.commit()
        flash('票品创建成功，请继续添加场次和座位', 'success')
        return redirect(url_for('merchant.ticket_list'))
    return render_template('merchant/ticket_edit.html', ticket=None)


# ----------------------------------------------------------------------
# 编辑票品
# ----------------------------------------------------------------------
@merchant_bp.route('/tickets/<int:tid>/edit', methods=['GET', 'POST'])
@merchant_required
def ticket_edit(tid):
    ticket = _get_own_ticket(tid)
    if not ticket:
        flash('票品不存在', 'danger')
        return redirect(url_for('merchant.ticket_list'))
    if request.method == 'POST':
        # 封面上传（优先）；若未传新文件，则保留原封面或使用 URL 输入框
        cover_rel = save_cover(request.files.get('cover_file'))
        if cover_rel is None:
            flash('封面格式不支持（仅支持 png/jpg/jpeg/gif/webp）', 'danger')
            return render_template('merchant/ticket_edit.html', ticket=ticket)
        cover = cover_rel if cover_rel else request.form.get('cover', '').strip()
        db.execute(
            'UPDATE tickets SET title=%s, type=%s, cover=%s, intro=%s, actors=%s, '
            'duration=%s, address=%s WHERE id=%s',
            (request.form.get('title', '').strip(), request.form.get('type', type=int) or 0,
             cover, request.form.get('intro', '').strip(),
             request.form.get('actors', '').strip(), request.form.get('duration', type=int) or 0,
             request.form.get('address', '').strip(), tid))
        db.commit()
        flash('票品已更新', 'success')
        return redirect(url_for('merchant.ticket_list'))
    return render_template('merchant/ticket_edit.html', ticket=ticket)

# ----------------------------------------------------------------------
# 上架 / 下架
# ----------------------------------------------------------------------
@merchant_bp.route('/tickets/<int:tid>/toggle', methods=['POST'])
@merchant_required
def ticket_toggle(tid):
    ticket = _get_own_ticket(tid)
    if not ticket:
        flash('票品不存在', 'danger')
        return redirect(url_for('merchant.ticket_list'))
    new_status = 0 if ticket['status'] == 1 else 1
    db.execute('UPDATE tickets SET status=%s WHERE id=%s', (new_status, tid))
    db.commit()
    flash('已%s' % ('下架' if new_status == 0 else '上架'), 'success')
    return redirect(url_for('merchant.ticket_list'))