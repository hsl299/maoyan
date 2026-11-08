# -*- coding: utf-8 -*-
"""
端到端验证脚本（标准库实现，不依赖 requests）
覆盖：登录→浏览→选座锁座→下单→支付→电子票→商家核销（含重复拦截）+ 退票全链路
运行：python test_flow.py
"""
import re
import json
import urllib.parse
import urllib.request
import http.cookiejar
import pymysql

BASE = 'http://127.0.0.1:5000'


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, path):
        req = urllib.request.Request(BASE + path, headers={'User-Agent': 'test'})
        with self.opener.open(req) as r:
            return r.status, r.read().decode('utf-8', 'ignore')

    def post(self, path, data=None, as_json=False):
        headers = {'User-Agent': 'test'}
        if as_json:
            body = json.dumps(data or {})
            headers['Content-Type'] = 'application/json'
        else:
            body = urllib.parse.urlencode(data or {})
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        req = urllib.request.Request(BASE + path, data=body.encode('utf-8'), headers=headers)
        with self.opener.open(req) as r:
            return r.status, r.read().decode('utf-8', 'ignore')


def db_get_one(sql, params=()):
    import config
    conn = pymysql.connect(host=config.DB_HOST, port=config.DB_PORT,
                           user=config.DB_USER, password=config.DB_PASSWORD,
                           database=config.DB_NAME, charset='utf8mb4')
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.close()
    return row


def book_and_pay(uid_name='user01', password='123456'):
    """完成一次 登录→选座→锁座→支付→取核销码，返回核销码"""
    u = Client()
    sess = db_get_one('SELECT id FROM sessions WHERE status=1 ORDER BY id LIMIT 1')
    seat = db_get_one('SELECT id FROM seats WHERE session_id=%s AND status=0 ORDER BY id LIMIT 1', (sess['id'],))
    u.post('/login', {'username': uid_name, 'password': password})
    s, res = u.post('/api/lock_seats', as_json=True,
                    data={'session_id': sess['id'], 'seat_ids': [seat['id']]})
    order_id = json.loads(res)['order_id']
    u.post(f'/order/{order_id}/pay')
    s, html = u.get(f'/order/{order_id}/ticket')
    code = re.search(r'class="code">([A-Z0-9]{16})<', html)
    return u, order_id, code.group(1) if code else None


def main():
    # ===== A. 购票 + 核销链路 =====
    u, order_a, code_a = book_and_pay()
    print('[A1] 购票支付完成, 核销码:', code_a)

    s, html = u.get('/')
    print('[A2] 首页', s, 'OK' if s == 200 and '流浪地球' in html else 'FAIL')

    m = Client()
    m.post('/login', {'username': 'shop01', 'password': '123456'})
    s, _ = m.get('/merchant/')
    print('[A3] 商家后台', s, 'OK' if s == 200 else 'FAIL')

    s, res = m.post('/merchant/verify/api', {'code': code_a})
    r = json.loads(res)
    print('[A4] 首次核销:', r.get('msg'))
    assert r.get('success'), '首次核销失败'

    s, res = m.post('/merchant/verify/api', {'code': code_a})
    r = json.loads(res)
    print('[A5] 重复核销:', r.get('msg'))
    assert not r.get('success'), '重复核销未被拦截'

    # ===== B. 退票链路 =====
    _, order_b, code_b = book_and_pay()
    u.post(f'/order/{order_b}/refund', {'reason': '行程冲突，申请退票'})
    print('[B1] 申请退票完成')

    # 退票中的订单应无法核销
    s, res = m.post('/merchant/verify/api', {'code': code_b})
    r = json.loads(res)
    print('[B2] 退票中订单核销应被拦截:', r.get('msg'))
    assert not r.get('success'), '退票中订单应无法核销'

    refund = db_get_one('SELECT id FROM refunds WHERE status=0 ORDER BY id DESC LIMIT 1')
    m.post(f'/merchant/refunds/{refund["id"]}/handle', {'action': 'approve', 'reply': '同意退票'})
    o = db_get_one('SELECT status FROM orders WHERE id=%s', (order_b,))
    print('[B3] 退票审核通过后订单状态:', o['status'], '(3=已退票)')
    assert o['status'] == 3, '退票通过后订单状态错误'

    # 座位应已回收为可售
    seat_b = db_get_one('SELECT s.status FROM seats s JOIN order_seats os ON s.id=os.seat_id '
                        'WHERE os.order_id=%s', (order_b,))
    print('[B4] 退票后座位状态:', seat_b['status'], '(0=可售)')
    assert seat_b['status'] == 0, '退票后座位未回收'

    print('\n===== 全部核心流程验证通过 =====')


if __name__ == '__main__':
    main()
