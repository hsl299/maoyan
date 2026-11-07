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



















