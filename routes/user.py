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
# 票品详情
# ----------------------------------------------------------------------
@user_bp.route('/ticket/<int:ticket_id>')
def ticket_detail(ticket_id):
    ticket = db.query_one('SELECT * FROM tickets WHERE id=%s', (ticket_id,))
    if not ticket or ticket['status'] == 0:
        flash('票品不存在或已下架', 'danger')
        return redirect(url_for('user.index'))
    sessions = db.query(
        'SELECT *, (SELECT COUNT(*) FROM seats WHERE session_id=sessions.id AND status=0) AS avail '
        'FROM sessions WHERE ticket_id=%s AND status=1 ORDER BY show_time', (ticket_id,))
    return render_template('ticket_detail.html', ticket=ticket, sessions=sessions)


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

# ----------------------------------------------------------------------
# 订单确认页
# ----------------------------------------------------------------------
@user_bp.route('/order/<int:order_id>/confirm')
@login_required
def order_confirm(order_id):
    release_timeout_orders()
    order = _get_own_order(order_id)
    if not order:
        flash('订单不存在', 'danger')
        return redirect(url_for('user.my_orders'))
    if order['status'] != 0:
        flash('订单状态已变化，无法继续支付', 'warning')
        return redirect(url_for('user.my_orders'))
    detail = _order_detail(order_id)
    return render_template('order_confirm.html', order=detail)


# ----------------------------------------------------------------------
# 模拟支付（真实环境在此对接微信/支付宝支付渠道）
# ----------------------------------------------------------------------
@user_bp.route('/order/<int:order_id>/pay', methods=['POST'])
@login_required
def pay(order_id):
    release_timeout_orders()
    order = _get_own_order(order_id)
    if not order:
        return jsonify(success=False, msg='订单不存在')
    if order['status'] != 0:
        return jsonify(success=False, msg='订单状态已变化')

    try:
        # 生成订单级统一核销码（一个订单无论几张票，只用一个核销码），标记已支付
        verify_code = gen_ticket_code()
        db.execute('UPDATE orders SET status=1, paid_at=NOW(), verify_code=%s WHERE id=%s',
                   (verify_code, order_id))
        # 座位置为已售
        db.execute(
            'UPDATE seats SET status=2 WHERE id IN '
            '(SELECT seat_id FROM order_seats WHERE order_id=%s)', (order_id,))
        # 生成电子票记录（每座一条，用于记录座位核销状态；核销码统一在订单）
        seat_rows = db.query(
            'SELECT os.seat_id FROM order_seats os WHERE os.order_id=%s', (order_id,))
        for sr in seat_rows:
            db.execute('INSERT INTO e_tickets (order_id, seat_id) VALUES (%s,%s)',
                       (order_id, sr['seat_id']))
        db.commit()
    except Exception:
        db.rollback()
        return jsonify(success=False, msg='支付失败，请重试')
    return jsonify(success=True, order_id=order_id)


# ----------------------------------------------------------------------
# 我的订单
# ----------------------------------------------------------------------
@user_bp.route('/my_orders')
@login_required
def my_orders():
    release_timeout_orders()
    uid = session['user_id']
    status = request.args.get('status', type=int)   # 筛选
    sql = ('SELECT o.*, t.title, t.type, s.show_time '
           'FROM orders o JOIN sessions s ON o.session_id=s.id '
           'JOIN tickets t ON s.ticket_id=t.id WHERE o.user_id=%s')
    params = [uid]
    if status is not None:
        sql += ' AND o.status=%s'
        params.append(status)
    sql += ' ORDER BY o.created_at DESC'
    orders = db.query(sql, params)
    return render_template('my_orders.html', orders=orders, cur=status)


# ----------------------------------------------------------------------
# 订单详情
# ----------------------------------------------------------------------
@user_bp.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    release_timeout_orders()
    order = _get_own_order(order_id)
    if not order:
        flash('订单不存在', 'danger')
        return redirect(url_for('user.my_orders'))
    return render_template('order_detail.html', order=_order_detail(order_id))

# ----------------------------------------------------------------------
# 电子票券页（含核销码 / 二维码）
# ----------------------------------------------------------------------
@user_bp.route('/order/<int:order_id>/ticket')
@login_required
def electronic_ticket(order_id):
    order = _get_own_order(order_id)
    if not order or order['status'] not in (1, 2, 6):
        flash('订单未支付，无法查看电子票', 'warning')
        return redirect(url_for('user.my_orders'))
    detail = _order_detail(order_id)
    return render_template('electronic_ticket.html', order=detail)














