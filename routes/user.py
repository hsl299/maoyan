# -*- coding: utf-8 -*-
"""
用户端模块：浏览票品、选座、下单、支付、订单、电子票券、退票
"""
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, jsonify)

import config
import db
from utils.decorators import login_required
from utils.helpers import gen_order_no, gen_ticket_code, order_is_timeout

user_bp = Blueprint('user', __name__)

# ----------------------------------------------------------------------
# 辅助：取消超时待支付订单并释放座位
# ----------------------------------------------------------------------
def release_timeout_orders():
    """把所有超过支付时限仍未支付的订单置为已取消(4)，并释放其座位"""
    timeout_ids = [r['id'] for r in db.query(
        "SELECT id FROM orders WHERE status=0 AND "
        "created_at < DATE_SUB(NOW(), INTERVAL %s SECOND)",
        (config.ORDER_TIMEOUT,))]
    if not timeout_ids:
        return 0
    placeholders = ','.join(['%s'] * len(timeout_ids))
    try:
        # 释放座位
        db.execute(
            f'UPDATE seats SET status=0 WHERE id IN '
            f'(SELECT seat_id FROM order_seats WHERE order_id IN ({placeholders}))',
            timeout_ids)
        # 订单置为已取消
        db.execute(
            f'UPDATE orders SET status=4 WHERE id IN ({placeholders})',
            timeout_ids)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return len(timeout_ids)


# ----------------------------------------------------------------------
# 首页：浏览票品（支持分类筛选）
# ----------------------------------------------------------------------
@user_bp.route('/')
def index():
    ttype = request.args.get('type', type=int)      # 0电影 1演出 空=全部
    kw = request.args.get('kw', '').strip()
    sql = ('SELECT t.*, '
           '(SELECT COUNT(*) FROM sessions s WHERE s.ticket_id=t.id AND s.status=1) AS session_count, '
           '(SELECT MIN(s2.base_price) FROM sessions s2 WHERE s2.ticket_id=t.id AND s2.status=1) AS min_price '
           'FROM tickets t WHERE t.status=1')
    params = []
    if ttype is not None:
        sql += ' AND t.type=%s'
        params.append(ttype)
    if kw:
        sql += ' AND (t.title LIKE %s OR t.actors LIKE %s)'
        like = f'%{kw}%'
        params += [like, like]
    sql += ' ORDER BY t.created_at DESC'
    tickets = db.query(sql, params)
    return render_template('index.html', tickets=tickets, ttype=ttype, kw=kw)


# ----------------------------------------------------------------------
# 选座页
# ----------------------------------------------------------------------
@user_bp.route('/select_seat/<int:session_id>')
@login_required
def seat_select(session_id):
    release_timeout_orders()  # 先清理超时订单，保证座位状态干净
    sess = db.query_one('SELECT * FROM sessions WHERE id=%s', (session_id,))
    if not sess or sess['status'] != 1:
        flash('场次不存在或已停售', 'danger')
        return redirect(url_for('user.index'))
    ticket = db.query_one('SELECT * FROM tickets WHERE id=%s', (sess['ticket_id'],))
    seats = db.query(
        'SELECT s.id, s.seat_row, s.seat_col, s.price, s.status '
        'FROM seats s WHERE s.session_id=%s ORDER BY s.seat_row, s.seat_col',
        (session_id,))
    # 计算每排列数用于前端布局
    cols = max((s['seat_col'] for s in seats), default=0)
    return render_template('seat_select.html', sess=sess, ticket=ticket,
                           seats=seats, cols=cols)


# ----------------------------------------------------------------------
# 锁定座位并创建待支付订单（AJAX）
# ----------------------------------------------------------------------
@user_bp.route('/api/lock_seats', methods=['POST'])
@login_required
def lock_seats():
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id')
    seat_ids = data.get('seat_ids') or []       # 座位主键列表
    if not session_id or not seat_ids:
        return jsonify(success=False, msg='参数错误')
    seat_ids = list(set(int(x) for x in seat_ids))
    uid = session['user_id']

    release_timeout_orders()

    sess = db.query_one('SELECT * FROM sessions WHERE id=%s AND status=1', (session_id,))
    if not sess:
        return jsonify(success=False, msg='场次不存在或已停售')

    # 校验所选座位都属于该场次
    qs = ','.join(['%s'] * len(seat_ids))
    rows = db.query(
        f'SELECT id, seat_row, seat_col, price, status FROM seats '
        f'WHERE id IN ({qs}) AND session_id=%s', seat_ids + [session_id])
    if len(rows) != len(seat_ids):
        return jsonify(success=False, msg='包含无效座位')

    # 校验全部可售
    for r in rows:
        if r['status'] != 0:
            return jsonify(success=False, msg=f"座位 {r['seat_row']}{r['seat_col']} 已被他人购买或锁定，请重选")

    try:
        # 锁座 + 建单（同一事务）
        for r in rows:
            db.execute('UPDATE seats SET status=1 WHERE id=%s AND status=0', (r['id'],))
        order_no = gen_order_no()
        total = sum(r['price'] for r in rows)
        db.execute(
            'INSERT INTO orders (order_no, user_id, session_id, total_price, status) '
            'VALUES (%s,%s,%s,%s,0)', (order_no, uid, session_id, total))
        order_id = db.last_insert_id()
        for r in rows:
            db.execute('INSERT INTO order_seats (order_id, seat_id) VALUES (%s,%s)',
                       (order_id, r['id']))
        db.commit()
    except Exception:
        db.rollback()
        return jsonify(success=False, msg='锁定失败，请重试')

    return jsonify(success=True, order_id=order_id)


















