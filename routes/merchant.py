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


# ----------------------------------------------------------------------
# 场次管理
# ----------------------------------------------------------------------
@merchant_bp.route('/tickets/<int:tid>/sessions')
@merchant_required
def session_manage(tid):
    ticket = _get_own_ticket(tid)
    if not ticket:
        flash('票品不存在', 'danger')
        return redirect(url_for('merchant.ticket_list'))
    sessions = db.query(
        'SELECT s.*, (SELECT COUNT(*) FROM seats WHERE session_id=s.id) AS seat_count, '
        '(SELECT COUNT(*) FROM seats WHERE session_id=s.id AND status IN (1,2)) AS sold_count '
        'FROM sessions s WHERE s.ticket_id=%s ORDER BY s.show_time', (tid,))
    return render_template('merchant/session_manage.html', ticket=ticket, sessions=sessions)


@merchant_bp.route('/tickets/<int:tid>/sessions/add', methods=['POST'])
@merchant_required
def session_add(tid):
    if not _get_own_ticket(tid):
        flash('票品不存在', 'danger')
        return redirect(url_for('merchant.ticket_list'))

    # 规范化时间：浏览器 datetime-local 可能提交 '2026-11-05T14:30' 或带秒，统一转标准格式
    show_time = request.form.get('show_time', '').strip().replace('T', ' ')
    try:
        parsed = datetime.strptime(show_time, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            parsed = datetime.strptime(show_time, '%Y-%m-%d %H:%M')
            show_time = parsed.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            flash('演出时间格式不正确，请重新选择', 'danger')
            return redirect(url_for('merchant.session_manage', tid=tid))

    base_price = request.form.get('base_price', type=float) or 0
    rows = request.form.get('seat_rows', type=int) or 8
    cols = request.form.get('seat_cols', type=int) or 10
    # 座位行数受英文字母表限制（A-Z），列数给一个合理上限，避免生成失败/异常
    if rows < 1 or rows > 26:
        flash('座位行数需在 1~26 之间', 'danger')
        return redirect(url_for('merchant.session_manage', tid=tid))
    if cols < 1 or cols > 30:
        flash('座位列数需在 1~30 之间', 'danger')
        return redirect(url_for('merchant.session_manage', tid=tid))
    try:
        db.execute(
            'INSERT INTO sessions (ticket_id, show_time, base_price, seat_rows, seat_cols) '
            'VALUES (%s,%s,%s,%s,%s)', (tid, show_time, base_price, rows, cols))
        sid = db.last_insert_id()
        # 生成座位（前三排+30%，中排+15%）
        import string as _s
        for r in range(rows):
            row_letter = _s.ascii_uppercase[r]
            for c in range(1, cols + 1):
                price = base_price * (1.30 if r < 3 else (1.15 if r < rows / 2 else 1.00))
                db.execute(
                    'INSERT INTO seats (session_id, seat_row, seat_col, price) VALUES (%s,%s,%s,%s)',
                    (sid, row_letter, c, round(price, 2)))
        db.commit()
        flash('场次及座位添加成功', 'success')
    except Exception:
        db.rollback()
        flash('添加场次失败，请重试', 'danger')
    return redirect(url_for('merchant.session_manage', tid=tid))


@merchant_bp.route('/sessions/<int:sid>/toggle', methods=['POST'])
@merchant_required
def session_toggle(sid):
    s = db.query_one('SELECT * FROM sessions WHERE id=%s', (sid,))
    if not s or not _get_own_ticket(s['ticket_id']):
        flash('场次不存在', 'danger')
        return redirect(url_for('merchant.dashboard'))
    db.execute('UPDATE sessions SET status=%s WHERE id=%s', (0 if s['status'] == 1 else 1, sid))
    db.commit()
    flash('场次状态已切换', 'success')
    return redirect(url_for('merchant.session_manage', tid=s['ticket_id']))


# ----------------------------------------------------------------------
# 座位/票价管理
# ----------------------------------------------------------------------
@merchant_bp.route('/sessions/<int:sid>/seats')
@merchant_required
def seat_manage(sid):
    s = db.query_one('SELECT * FROM sessions WHERE id=%s', (sid,))
    if not s or not _get_own_ticket(s['ticket_id']):
        flash('场次不存在', 'danger')
        return redirect(url_for('merchant.dashboard'))
    ticket = db.query_one('SELECT * FROM tickets WHERE id=%s', (s['ticket_id'],))
    seats = db.query(
        'SELECT * FROM seats WHERE session_id=%s ORDER BY seat_row, seat_col', (sid,))
    cols = max((x['seat_col'] for x in seats), default=0)
    return render_template('merchant/seat_manage.html', sess=s, ticket=ticket,
                           seats=seats, cols=cols)


@merchant_bp.route('/sessions/<int:sid>/seats/update', methods=['POST'])
@merchant_required
def seat_update(sid):
    s = db.query_one('SELECT * FROM sessions WHERE id=%s', (sid,))
    if not s or not _get_own_ticket(s['ticket_id']):
        return jsonify(success=False, msg='场次不存在')

    action = request.form.get('action')
    try:
        if action == 'price_row':      # 按行调价
            row = request.form.get('seat_row', '').strip().upper()
            price = request.form.get('price', type=float)
            if not row or price is None:
                return jsonify(success=False, msg='参数错误')
            db.execute('UPDATE seats SET price=%s WHERE session_id=%s AND seat_row=%s AND status=0',
                       (price, sid, row))
        elif action == 'price_all':    # 全场统一定价
            price = request.form.get('price', type=float)
            if price is None:
                return jsonify(success=False, msg='参数错误')
            db.execute('UPDATE seats SET price=%s WHERE session_id=%s AND status=0',
                       (price, sid))
        elif action == 'reset':        # 重置本场所有座位为可售（清空锁/售）
            db.execute('UPDATE seats SET status=0 WHERE session_id=%s', (sid,))
        else:
            return jsonify(success=False, msg='未知操作')
        db.commit()
    except Exception:
        db.rollback()
        return jsonify(success=False, msg='操作失败')
    return jsonify(success=True)

# ----------------------------------------------------------------------
# 销售订单
# ----------------------------------------------------------------------
@merchant_bp.route('/orders')
@merchant_required
def orders():
    mid = session['user_id']
    status = request.args.get('status', type=int)
    tid = request.args.get('tid', type=int)
    kw = request.args.get('kw', '').strip()
    sql = ('SELECT o.*, t.title, t.type, s.show_time, u.nickname, u.phone '
           'FROM orders o JOIN sessions s ON o.session_id=s.id '
           'JOIN tickets t ON s.ticket_id=t.id JOIN users u ON o.user_id=u.id '
           'WHERE t.merchant_id=%s')
    params = [mid]
    if status is not None:
        sql += ' AND o.status=%s'
        params.append(status)
    if tid:
        sql += ' AND t.id=%s'
        params.append(tid)
    if kw:
        sql += ' AND (u.nickname LIKE %s OR u.phone LIKE %s OR o.order_no LIKE %s)'
        like = f'%{kw}%'
        params += [like, like, like]
    sql += ' ORDER BY o.created_at DESC'
    orders = db.query(sql, params)
    # 聚合每个订单的座位
    order_seats = {}
    if orders:
        ids = [str(o['id']) for o in orders]
        seat_rows = db.query(
            'SELECT os.order_id, st.seat_row, st.seat_col FROM order_seats os '
            'JOIN seats st ON os.seat_id=st.id WHERE os.order_id IN (%s)' % ','.join(['%s'] * len(ids)),
            ids)
        for sr in seat_rows:
            order_seats.setdefault(sr['order_id'], []).append(sr)
    tickets = db.query(
        'SELECT id, title FROM tickets WHERE merchant_id=%s ORDER BY created_at DESC', (mid,))
    return render_template('merchant/orders.html', orders=orders, tickets=tickets,
                           cur_status=status, cur_tid=tid, kw=kw, order_seats=order_seats)


# ----------------------------------------------------------------------
# 退票审核
# ----------------------------------------------------------------------
@merchant_bp.route('/refunds')
@merchant_required
def refunds():
    mid = session['user_id']
    refunds = db.query(
        'SELECT r.*, o.order_no, o.total_price, t.title, u.nickname, u.phone '
        'FROM refunds r JOIN orders o ON r.order_id=o.id '
        'JOIN sessions s ON o.session_id=s.id JOIN tickets t ON s.ticket_id=t.id '
        'JOIN users u ON r.user_id=u.id WHERE t.merchant_id=%s ORDER BY r.created_at DESC',
        (mid,))
    return render_template('merchant/refunds.html', refunds=refunds)


@merchant_bp.route('/refunds/<int:rid>/handle', methods=['POST'])
@merchant_required
def refund_handle(rid):
    refund = db.query_one('SELECT * FROM refunds WHERE id=%s', (rid,))
    if not refund or refund['status'] != 0:
        flash('退票申请不存在或已处理', 'warning')
        return redirect(url_for('merchant.refunds'))
    order = db.query_one('SELECT * FROM orders WHERE id=%s', (refund['order_id'],))
    if not order:
        flash('关联订单不存在', 'danger')
        return redirect(url_for('merchant.refunds'))
    action = request.form.get('action')
    reply = request.form.get('reply', '').strip()
    try:
        if action == 'approve':    # 审核通过：退款 + 回收座位 + 订单已退票 + 票券作废
            db.execute('UPDATE refunds SET status=1, reply=%s, handled_at=NOW() WHERE id=%s',
                       (reply, rid))
            db.execute('UPDATE orders SET status=3 WHERE id=%s', (order['id'],))
            db.execute(
                'UPDATE seats SET status=0 WHERE id IN '
                '(SELECT seat_id FROM order_seats WHERE order_id=%s)', (order['id'],))
        else:                       # 不通过：恢复订单为已支付
            db.execute('UPDATE refunds SET status=2, reply=%s, handled_at=NOW() WHERE id=%s',
                       (reply, rid))
            db.execute('UPDATE orders SET status=1 WHERE id=%s', (order['id'],))
        db.commit()
        flash('退票申请已处理', 'success')
    except Exception:
        db.rollback()
        flash('处理失败', 'danger')
    return redirect(url_for('merchant.refunds'))